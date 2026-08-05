"""
Regression tests for SEC-4: POST /api/auth/login accepted unlimited attempts
from unlimited sources -- no lockout, no backoff, no record of failed
attempts anywhere in the audit log (only successful LOGIN events were
written). Both an offline-quality brute force made online, and (every
attempt costs a full bcrypt verification) a trivial way to saturate the
single application process.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import AuditEvent, User
from app.services import login_throttle
from app.services.auth_service import hash_password


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
    db.add(User(username="throttle_user", full_name="Throttle User", role="SCIENTIST",
                password_hash=hash_password("correct-password"), is_active=True))
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.session_factory = TestSessionLocal
        yield c

    app.dependency_overrides.clear()
    login_throttle.reset_all()


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_five_failed_attempts_lock_out_the_sixth_even_with_the_right_password(client):
    for _ in range(5):
        resp = _login(client, "throttle_user", "wrong-password")
        assert resp.status_code == 401

    resp = _login(client, "throttle_user", "correct-password")
    assert resp.status_code == 429


def test_a_successful_login_resets_the_failure_counter(client):
    for _ in range(4):
        _login(client, "throttle_user", "wrong-password")

    resp = _login(client, "throttle_user", "correct-password")
    assert resp.status_code == 200  # 4 failures, not yet locked out

    # After a clean success, the streak resets -- 4 more failures shouldn't
    # be enough to lock out on their own.
    for _ in range(4):
        _login(client, "throttle_user", "wrong-password")
    resp = _login(client, "throttle_user", "correct-password")
    assert resp.status_code == 200


def test_lockout_is_scoped_per_username_not_global(client):
    db = client.session_factory()
    db.add(User(username="throttle_user_2", full_name="Throttle User 2", role="SCIENTIST",
                password_hash=hash_password("correct-password-2"), is_active=True))
    db.commit()
    db.close()

    for _ in range(5):
        _login(client, "throttle_user", "wrong-password")

    # throttle_user is now locked out...
    resp = _login(client, "throttle_user", "correct-password")
    assert resp.status_code == 429

    # ...but a different username, same source, is unaffected.
    resp = _login(client, "throttle_user_2", "correct-password-2")
    assert resp.status_code == 200


def test_nonexistent_username_is_throttled_identically_to_a_real_one(client):
    # If only real usernames were throttled, the presence/absence of a
    # lockout after N attempts would itself leak whether the username
    # exists -- a second enumeration oracle alongside the login error
    # message (which is already deliberately uniform).
    for _ in range(5):
        resp = _login(client, "no-such-user", "whatever")
        assert resp.status_code == 401

    resp = _login(client, "no-such-user", "whatever")
    assert resp.status_code == 429


def test_failed_attempts_are_recorded_in_the_audit_log(client):
    _login(client, "throttle_user", "wrong-password")

    db = client.session_factory()
    events = db.query(AuditEvent).filter(AuditEvent.action == "LOGIN_FAILED").all()
    db.close()
    assert len(events) == 1
    assert events[0].actor_name == "throttle_user"
    assert "ip" in events[0].details


def test_lockout_trigger_is_recorded_distinctly_in_the_audit_log(client):
    for _ in range(5):
        _login(client, "throttle_user", "wrong-password")

    db = client.session_factory()
    lockout_events = db.query(AuditEvent).filter(AuditEvent.action == "LOGIN_LOCKED_OUT").all()
    failed_events = db.query(AuditEvent).filter(AuditEvent.action == "LOGIN_FAILED").all()
    db.close()
    assert len(lockout_events) == 1  # only the 5th (threshold-crossing) attempt triggers this
    assert len(failed_events) == 5


def test_valid_login_still_succeeds_end_to_end(client):
    resp = _login(client, "throttle_user", "correct-password")
    assert resp.status_code == 200
    assert resp.json()["access_token"]
