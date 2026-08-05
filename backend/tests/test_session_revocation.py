"""
Regression tests for H6: token_version-based session revocation +
self-service password change.

Before this change, an access token was valid for its full 12-hour
lifetime no matter what happened to the account afterward -- changing a
password (self-service or an Administrator's reset) didn't invalidate any
token already issued under the old one. A stolen or shared token kept
working right up to its natural expiry even after the "protecting"
password was changed.
"""
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import User
from app.services import login_throttle
from app.services.auth_service import ALGORITHM, SECRET_KEY, hash_password


@pytest.fixture
def client(tmp_path):
    login_throttle.reset_all()

    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestSessionLocal()
    db.add(User(username="revoke_user", full_name="Revoke User", role="SCIENTIST",
                password_hash=hash_password("original-password123"), is_active=True))
    db.add(User(username="revoke_admin", full_name="Revoke Admin", role="ADMINISTRATOR",
                password_hash=hash_password("admin-password123"), is_active=True))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    login_throttle.reset_all()


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_self_service_password_change_invalidates_the_old_token_but_returns_a_working_new_one(client):
    old_token = _login(client, "revoke_user", "original-password123")
    assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 200

    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "original-password123", "new_password": "brand-new-password123"},
        headers=_auth(old_token),
    )
    assert resp.status_code == 200, resp.text
    new_token = resp.json()["access_token"]
    assert new_token != old_token

    # The token used to MAKE the change request is now stale -- it must stop
    # working immediately, not linger until its natural expiry.
    stale_resp = client.get("/api/auth/me", headers=_auth(old_token))
    assert stale_resp.status_code == 401

    # But the caller isn't locked out of their own session: the fresh token
    # the response handed back works right away.
    assert client.get("/api/auth/me", headers=_auth(new_token)).status_code == 200

    # And the new password is what actually authenticates now.
    relogin_token = _login(client, "revoke_user", "brand-new-password123")
    assert client.get("/api/auth/me", headers=_auth(relogin_token)).status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    token = _login(client, "revoke_user", "original-password123")
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "totally-wrong", "new_password": "brand-new-password123"},
        headers=_auth(token),
    )
    assert resp.status_code == 401
    # The old token must still work -- a failed change attempt is not a
    # security-sensitive event that should revoke anything.
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


def test_change_password_rejects_a_too_short_new_password(client):
    token = _login(client, "revoke_user", "original-password123")
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "original-password123", "new_password": "short"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


def test_administrator_password_reset_invalidates_the_target_users_existing_tokens(client):
    target_token = _login(client, "revoke_user", "original-password123")
    admin_token = _login(client, "revoke_admin", "admin-password123")
    assert client.get("/api/auth/me", headers=_auth(target_token)).status_code == 200

    users = client.get("/api/admin/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "revoke_user")

    resp = client.patch(
        f"/api/admin/users/{target_id}",
        json={"password": "admin-set-password123"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text

    # The target's pre-reset token must stop working immediately.
    assert client.get("/api/auth/me", headers=_auth(target_token)).status_code == 401

    # The Administrator's own token, and a fresh login as the target with
    # the new password, are both unaffected.
    assert client.get("/api/auth/me", headers=_auth(admin_token)).status_code == 200
    new_target_token = _login(client, "revoke_user", "admin-set-password123")
    assert client.get("/api/auth/me", headers=_auth(new_target_token)).status_code == 200


def test_an_edit_that_does_not_touch_password_does_not_revoke_the_existing_token(client):
    target_token = _login(client, "revoke_user", "original-password123")
    admin_token = _login(client, "revoke_admin", "admin-password123")
    users = client.get("/api/admin/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "revoke_user")

    resp = client.patch(
        f"/api/admin/users/{target_id}",
        json={"full_name": "Revoke User Renamed"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert client.get("/api/auth/me", headers=_auth(target_token)).status_code == 200


def test_a_token_with_no_tv_claim_is_rejected(client):
    """Simulates a token minted before H6 existed (no "tv" claim at all) --
    it must not be treated as automatically valid just because there's
    nothing to compare against."""
    login_resp = client.post("/api/auth/login", json={"username": "revoke_user", "password": "original-password123"})
    assert login_resp.status_code == 200
    payload = jwt.decode(login_resp.json()["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    del payload["tv"]
    legacy_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = client.get("/api/auth/me", headers=_auth(legacy_token))
    assert resp.status_code == 401


def test_a_token_with_a_stale_tv_claim_is_rejected(client):
    """Simulates a token that was valid at issue time but whose account has
    since had its token_version bumped by some other action -- forged by
    hand-editing the "tv" claim downward and re-signing with the app's own
    secret, to isolate exactly the comparison in get_current_user without
    depending on any specific action that bumps the real column."""
    login_resp = client.post("/api/auth/login", json={"username": "revoke_user", "password": "original-password123"})
    payload = jwt.decode(login_resp.json()["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    payload["tv"] = payload["tv"] - 1 if payload["tv"] else -1
    stale_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    resp = client.get("/api/auth/me", headers=_auth(stale_token))
    assert resp.status_code == 401
