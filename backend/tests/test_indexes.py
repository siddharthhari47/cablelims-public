"""
Regression tests for H4: the hot-path indexes added on top of the Alembic
baseline (see alembic/versions/00e595886516_add_hot_path_indexes.py and the
index=True annotations they were generated from in app/models/models.py).

These check the indexes actually exist on a freshly migrated database --
not query performance itself (meaningless to assert on a database this
small; see H4's Phase 8 report for the EXPLAIN QUERY PLAN before/after
evidence that was actually used to verify effectiveness).
"""
from sqlalchemy import create_engine, inspect

from app.db_migrate import run_migrations


def _index_names(inspector, table):
    return {ix["name"] for ix in inspector.get_indexes(table)}


def test_hot_path_indexes_exist_after_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'indexed.db'}")
    run_migrations(engine)
    inspector = inspect(engine)

    assert "ix_assigned_tests_sample_id" in _index_names(inspector, "assigned_tests")
    assert "ix_samples_assigned_assistant_id" in _index_names(inspector, "samples")
    assert "ix_samples_status" in _index_names(inspector, "samples")
    assert "ix_certificates_sample_id" in _index_names(inspector, "certificates")
    assert "ix_audit_events_timestamp" in _index_names(inspector, "audit_events")

    test_run_indexes = inspector.get_indexes("test_runs")
    composite = next((ix for ix in test_run_indexes if ix["name"] == "ix_test_runs_assigned_test_id_attempt_number"), None)
    assert composite is not None
    assert composite["column_names"] == ["assigned_test_id", "attempt_number"]

    # Offline support (phase 3a): enforces submit_reading's idempotency
    # guarantee at the DB level, not just in the service-layer lookup --
    # see test_reading_idempotency.py for the behavioral tests.
    dedupe = next((ix for ix in test_run_indexes if ix["name"] == "uq_test_runs_assigned_test_client_request_id"), None)
    assert dedupe is not None
    assert dedupe["column_names"] == ["assigned_test_id", "client_request_id"]
    assert dedupe["unique"]  # SQLite's reflection reports this as 1, not True
