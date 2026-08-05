"""
Regression tests for H3 (replace ad-hoc startup schema-sync with Alembic).

Three things are under test:
1. A brand-new (empty) database ends up with exactly the schema
   Base.metadata describes, via the baseline migration -- not create_all().
2. A pre-Alembic database (the old create_all()+sync_schema() startup pair,
   which every install before this change has) gets stamped at the
   baseline revision rather than replayed, and isn't touched further.
3. Running migrations at startup must not disable the app's own "cablelims"
   logger. This was a real bug found while implementing H3: Alembic's
   env.py calls logging.config.fileConfig() to load alembic.ini's logging
   section, whose default disable_existing_loggers=True silently disabled
   every logger not explicitly named there -- including "cablelims",
   configured moments earlier in app.main.py -- so nothing reached
   backend/logs/cablelims.log after startup ran migrations. Fixed by
   passing disable_existing_loggers=False in alembic/env.py.
"""
import logging

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import app.models.models  # noqa: F401 -- registers every table on Base.metadata
from alembic import command
from app.db import Base
from app.db_migrate import BASELINE_REVISION, _alembic_config, run_migrations


def test_run_migrations_builds_the_full_schema_on_an_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_path}")

    run_migrations(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = set(Base.metadata.tables.keys()) | {"alembic_version"}
    assert tables == expected


def test_run_migrations_stamps_rather_than_replays_a_pre_alembic_database(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # Simulates a database created before H3 existed: schema exactly as the
    # baseline revision defines it (NOT current Base.metadata -- that drifts
    # every time a later migration, like H4's indexes, adds something new,
    # which would make this "legacy" fixture describe a database that never
    # actually existed), and -- critically -- no alembic_version table,
    # since the old create_all()+sync_schema() startup pair never wrote one.
    command.upgrade(_alembic_config(engine), BASELINE_REVISION)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE alembic_version")
    inspector = inspect(engine)
    assert "alembic_version" not in inspector.get_table_names()

    run_migrations(engine)  # must not raise "table/index already exists"

    inspector = inspect(engine)
    with engine.connect() as conn:
        stamped = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()

    script_dir = ScriptDirectory.from_config(_alembic_config(engine))
    current_head = script_dir.get_current_head()
    # Stamped and then upgraded straight to head -- not stuck at the
    # baseline -- so any migration added after H3 (e.g. H4's indexes) still
    # reaches a database that predates Alembic, same as a brand-new one.
    assert stamped == current_head
    assert current_head != BASELINE_REVISION  # sanity: a later migration does exist to prove this
    assert set(Base.metadata.tables.keys()) <= set(inspector.get_table_names())


def test_run_migrations_does_not_disable_the_app_logger(tmp_path):
    db_path = tmp_path / "logging_check.db"
    engine = create_engine(f"sqlite:///{db_path}")

    app_logger = logging.getLogger("cablelims")
    was_disabled_before = app_logger.disabled
    app_logger.disabled = False
    try:
        run_migrations(engine)
        assert app_logger.disabled is False, (
            "run_migrations() disabled the 'cablelims' logger -- alembic/env.py's "
            "fileConfig() call must pass disable_existing_loggers=False."
        )
    finally:
        app_logger.disabled = was_disabled_before
