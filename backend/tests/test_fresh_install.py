"""
B2 (Review #2 remediation): a clean-room reproduction of the documented
first-time install (first_time_setup.bat / DEPLOYMENT.md), end to end,
against a genuinely empty database -- the one path every single user takes,
and the one path nothing else in this suite covers (every other test either
seeds config directly against an already-isolated engine, or drives the API
against a database some fixture already built). This is what would have
caught B1's regression before it shipped (see the review, section 7.1).

Sequence, matching first_time_setup.bat exactly:
  1. `python -m app.seed --config-only`
  2. `python -m app.create_user` (its interactive prompts can't be driven
     here; after B1 both steps converge on the same run_migrations() call,
     so a second direct call is a faithful equivalent, not a placeholder)
  3. `start_cablelims.bat` -> `uvicorn app.main:app` -- reproduced by
     reloading app.main so its own module-level startup code (including its
     own run_migrations() call) actually executes against this database.
"""
import importlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db as db_module
import app.seed as seed_module
from app.db_migrate import run_migrations


def test_fresh_install_documented_order_boots_and_reports_healthy(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh_install.db"
    tmp_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    tmp_session_local = sessionmaker(autocommit=False, autoflush=False, bind=tmp_engine)

    # get_db() (app/db.py) reads these two names as module globals at call
    # time, not at def time -- patching them here is enough to redirect
    # every DB access anywhere in the app, without needing to reload every
    # module that happens to hold its own `from app.db import ... engine`
    # binding. monkeypatch reverts both automatically at teardown.
    monkeypatch.setattr(db_module, "engine", tmp_engine)
    monkeypatch.setattr(db_module, "SessionLocal", tmp_session_local)

    # app.seed captured its own `engine`/`SessionLocal` names at whatever
    # point it was first imported (by test_seed_demo_gating.py, in this
    # suite) -- reload it now so it re-reads the patched db_module.
    importlib.reload(seed_module)

    # Step 1: python -m app.seed --config-only
    seed_module.run(config_only=True)

    # Step 2: python -m app.create_user's schema-creation half (see the
    # module docstring above for why this stands in for the interactive
    # script itself).
    run_migrations(tmp_engine)

    # Step 3: start_cablelims.bat. Reloading app.main forces its own
    # top-level code -- including its own run_migrations(engine) call at
    # startup -- to actually execute against this database, which is the
    # thing under test: does the documented order produce an app that boots?
    import app.main as main_module
    importlib.reload(main_module)  # must not raise

    with TestClient(main_module.app) as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
