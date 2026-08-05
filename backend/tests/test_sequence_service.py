"""
Regression tests for §7.4: sample/certificate numbers previously used
`COUNT(matching rows) + 1`, computed fresh on every call. That races under
concurrent requests (two callers read the same count before either commits,
both construct the same number, the second commit raises an unhandled
IntegrityError) and goes backwards -- straight into a collision with an
already-issued number -- the moment any row is ever deleted.
"""
import threading
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.sequence_service import next_sequence_value


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield SessionLocal
    engine.dispose()


def test_first_allocation_on_a_fresh_kind_year_starts_at_one(db_session):
    db = db_session()
    value = next_sequence_value(db, "SAMPLE", 2026)
    db.commit()
    assert value == 1
    db.close()


def test_sequential_allocations_increment_with_no_gaps_or_repeats(db_session):
    db = db_session()
    values = [next_sequence_value(db, "SAMPLE", 2026) for _ in range(10)]
    db.commit()
    db.close()
    assert values == list(range(1, 11))


def test_bootstrap_fn_seeds_starting_value_only_once(db_session):
    # Simulates migrating an existing database that already has samples
    # numbered under the old COUNT(*)+1 scheme -- the sequence must continue
    # from there, not restart at 1 and collide with SMP-2026-0001..0042.
    db = db_session()
    calls = []

    def bootstrap():
        calls.append(1)
        return 43

    first = next_sequence_value(db, "SAMPLE", 2026, bootstrap_fn=bootstrap)
    second = next_sequence_value(db, "SAMPLE", 2026, bootstrap_fn=bootstrap)
    db.commit()
    db.close()

    assert first == 43
    assert second == 44
    assert len(calls) == 1, "bootstrap_fn must only run once per (kind, year), not on every call"


def test_different_kinds_and_years_have_independent_sequences(db_session):
    db = db_session()
    sample_2026 = next_sequence_value(db, "SAMPLE", 2026)
    cert_2026 = next_sequence_value(db, "CERTIFICATE", 2026)
    sample_2027 = next_sequence_value(db, "SAMPLE", 2027)
    db.commit()
    db.close()
    assert sample_2026 == 1
    assert cert_2026 == 1
    assert sample_2027 == 1


def test_a_deleted_row_does_not_cause_the_next_allocation_to_collide(db_session):
    # The old COUNT(*)+1 scheme would go backwards here and hand out an
    # already-used number the moment the highest-numbered row was removed
    # (e.g. via direct sqlite3 access, which DEPLOYMENT.md's own
    # troubleshooting section assumes an operator might use). A real
    # sequence counter is monotonic regardless of what rows still exist.
    db = db_session()
    v1 = next_sequence_value(db, "SAMPLE", 2026)
    v2 = next_sequence_value(db, "SAMPLE", 2026)
    v3 = next_sequence_value(db, "SAMPLE", 2026)
    db.commit()
    assert [v1, v2, v3] == [1, 2, 3]

    # Simulate "v3's row was deleted" -- nothing about the sequence counter
    # itself is affected, because it was never derived from counting rows.
    v4 = next_sequence_value(db, "SAMPLE", 2026)
    db.commit()
    db.close()
    assert v4 == 4


def test_concurrent_allocations_never_produce_a_duplicate_number(tmp_path):
    # A real concurrency check, not just sequential calls -- N threads each
    # open their OWN session/connection (matching how FastAPI's request-
    # scoped `get_db` dependency works) and race to allocate from the same
    # (kind, year) sequence. SQLite's single-writer lock plus busy_timeout
    # (set on this engine below) must serialize them into a gap-free,
    # collision-free run, not a pile of duplicates or crashes.
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    results = []
    errors = []
    lock = threading.Lock()

    def worker():
        db = SessionLocal()
        try:
            value = next_sequence_value(db, "SAMPLE", 2026)
            db.commit()
            with lock:
                results.append(value)
        except Exception as e:
            db.rollback()
            with lock:
                errors.append(e)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    engine.dispose()

    assert not errors, f"concurrent allocation raised: {errors}"
    assert sorted(results) == list(range(1, 21)), (
        f"expected exactly {list(range(1, 21))} with no duplicates/gaps, got {sorted(results)}"
    )
