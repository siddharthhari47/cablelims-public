"""
Regression test for B7 (Review #2 remediation): get_sample_detail() looped
every AssignedTest issuing get_accepted_run() (1-2 queries), a separate
.count() for attempts, and a lazy test_definition load each -- measured by
the review at 241 queries for a 76-test sample (the Scientist's most-used
screen). Fixed the same way H5 fixed list_samples/the dashboard: bulk-fetch
everything up front, resolve per-test in memory. Same query-counting
approach as test_aggregation_bulk.py's own H5 regression test.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.models import AssignedTest, Sample, Standard, TestDefinition, TestRun, User
from app.services.sample_service import get_sample_detail


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _build_sample_with_n_tests(db, sample_id, n, suffix):
    scientist = User(username=f"sci_{suffix}", password_hash="x", full_name="S", role="SCIENTIST")
    assistant = User(username=f"asst_{suffix}", password_hash="x", full_name="A", role="SCIENTIFIC_ASSISTANT")
    db.add_all([scientist, assistant])
    db.flush()
    standard = Standard(standard_id=f"STD-{suffix}", name="IS 694")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id=sample_id, product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING", registered_by_id=scientist.id,
                     assigned_assistant_id=assistant.id)
    db.add(sample)
    db.flush()
    for i in range(n):
        test_id = f"TEST-{suffix}-{i}"
        db.add(TestDefinition(test_id=test_id, name=test_id, unit="unit", sequence=i))
        db.flush()
        at = AssignedTest(sample_id=sample_id, test_id=test_id, mandatory=True, enabled=True, status="COMPLETED")
        db.add(at)
        db.flush()
        run = TestRun(assigned_test_id=at.id, attempt_number=1, raw_values={}, result="PASS",
                       submitted_by_id=assistant.id)
        db.add(run)
        db.flush()
        at.accepted_attempt_id = run.id
    db.commit()
    return db.query(Sample).filter(Sample.sample_id == sample_id).first()


def _count_select_queries(db, fn):
    count = 0

    def _listener(conn, cursor, statement, *a, **kw):
        nonlocal count
        if statement.strip().upper().startswith("SELECT"):
            count += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return count


def test_sample_detail_query_count_does_not_scale_with_test_count():
    db_small = _db()
    small_sample = _build_sample_with_n_tests(db_small, "SMP-DETAIL-SMALL", 3, "SMALL")
    small_queries = _count_select_queries(db_small, lambda: get_sample_detail(db_small, small_sample))

    db_large = _db()
    large_sample = _build_sample_with_n_tests(db_large, "SMP-DETAIL-LARGE", 76, "LARGE")
    large_queries = _count_select_queries(db_large, lambda: get_sample_detail(db_large, large_sample))

    # The whole point: a fixed number of queries regardless of test count.
    # If this ever regresses back to the per-test loop, large_queries would
    # scale up by roughly 3x the extra 73 tests instead of staying flat.
    assert small_queries == large_queries
    assert large_queries <= 10  # measured well under this after the fix; 241 before it
