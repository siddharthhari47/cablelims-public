"""
Regression test for SEC-3: seed.py must never create demo accounts
(scientist1/assistant1/admin1, password demo1234) unless
CABLELIMS_ALLOW_DEMO_USERS=1 is explicitly set in the environment, even when
called without --config-only. This is what stops a habit-driven
`python -m app.seed` on a real server from putting a known-password
Administrator account in front of real samples.

Also (B6, Review #2 remediation): GET /api/auth/demo-hint must not be a free
reconnaissance oracle -- an anonymous caller against a real install (which
never sets CABLELIMS_ALLOW_DEMO_USERS) must get a flat "no" without the
endpoint even querying whether demo accounts exist, regardless of whatever
is actually in that install's database.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.seed as seed_module
from app.db import Base, get_db
from app.main import app
from app.models.models import User
from app.services.auth_service import hash_password


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A throwaway SQLite file per test, so this never touches the real dev
    database at backend/data/cablelims.db."""
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module, "SessionLocal", TestSessionLocal)
    yield TestSessionLocal
    engine.dispose()


def _demo_user_count(session_factory) -> int:
    db = session_factory()
    try:
        return db.query(User).filter(User.is_demo == True).count()
    finally:
        db.close()


def test_bare_seed_without_env_var_creates_no_demo_users(isolated_db, monkeypatch):
    monkeypatch.delenv("CABLELIMS_ALLOW_DEMO_USERS", raising=False)
    seed_module.run(config_only=False)
    assert _demo_user_count(isolated_db) == 0


def test_config_only_creates_no_demo_users_even_with_env_var_set(isolated_db, monkeypatch):
    # --config-only is the stronger signal ("this is a real install") and
    # must win even if the environment happens to have the variable set.
    monkeypatch.setenv("CABLELIMS_ALLOW_DEMO_USERS", "1")
    seed_module.run(config_only=True)
    assert _demo_user_count(isolated_db) == 0


def test_demo_users_only_created_with_explicit_opt_in(isolated_db, monkeypatch):
    monkeypatch.setenv("CABLELIMS_ALLOW_DEMO_USERS", "1")
    seed_module.run(config_only=False)
    assert _demo_user_count(isolated_db) == 5  # scientist1/2, assistant1/2, admin1


def test_env_var_must_be_exactly_1(isolated_db, monkeypatch):
    # Guards against "truthy string" bugs (SEC-6/§5.4's own lesson applied
    # here) -- CABLELIMS_ALLOW_DEMO_USERS=true or =yes must NOT count.
    monkeypatch.setenv("CABLELIMS_ALLOW_DEMO_USERS", "true")
    seed_module.run(config_only=False)
    assert _demo_user_count(isolated_db) == 0


@pytest.fixture
def client_with_a_demo_user(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    db.add(User(username="scientist1", full_name="Demo Scientist", role="SCIENTIST",
                password_hash=hash_password("demo1234"), is_active=True, is_demo=True))
    db.commit()
    db.close()

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_demo_hint_says_no_without_the_env_var_even_if_demo_users_exist(client_with_a_demo_user, monkeypatch):
    # B6: the oracle is closed by never even looking at the database when
    # the environment doesn't say this is a demo/dev install -- a real
    # production server's answer must not depend on what's actually in its
    # database, which an anonymous caller has no business learning either way.
    monkeypatch.delenv("CABLELIMS_ALLOW_DEMO_USERS", raising=False)
    resp = client_with_a_demo_user.get("/api/auth/demo-hint")
    assert resp.status_code == 200  # still callable with no Authorization header -- pre-login use
    assert resp.json()["show_demo_hint"] is False


def test_demo_hint_says_yes_with_the_env_var_set_and_demo_users_present(client_with_a_demo_user, monkeypatch):
    # The legitimate dev/demo case (LoginPage.tsx's own reason for calling
    # this pre-login) must keep working exactly as before.
    monkeypatch.setenv("CABLELIMS_ALLOW_DEMO_USERS", "1")
    resp = client_with_a_demo_user.get("/api/auth/demo-hint")
    assert resp.status_code == 200
    assert resp.json()["show_demo_hint"] is True
