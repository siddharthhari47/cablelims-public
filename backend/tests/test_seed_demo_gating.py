"""
Regression test for SEC-3: seed.py must never create demo accounts
(scientist1/assistant1/admin1, password demo1234) unless
CABLELIMS_ALLOW_DEMO_USERS=1 is explicitly set in the environment, even when
called without --config-only. This is what stops a habit-driven
`python -m app.seed` on a real server from putting a known-password
Administrator account in front of real samples.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.seed as seed_module
from app.db import Base
from app.models.models import User


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
