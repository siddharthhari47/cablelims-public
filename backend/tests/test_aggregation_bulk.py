"""
Regression tests for H5: summarize_samples_bulk() must produce identical
summaries to calling summarize_sample() once per sample -- while using a
constant number of queries rather than one round trip per sample (and,
within each, one more per assigned test). Before this change, list_samples
and the dashboard each called summarize_sample() in a loop, which itself
called get_accepted_run() once per assigned test -- O(samples x tests)
queries on every single page load.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.engines.aggregation import summarize_sample, summarize_samples_bulk
from app.models.models import AssignedTest, Sample, Standard, TestDefinition, TestRun, User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_sample(db, sample_id, standard_id, scientist_id):
    sample = Sample(sample_id=sample_id, product_family="CABLE", standard_id=standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING", registered_by_id=scientist_id)
    db.add(sample)
    db.flush()
    return sample


def _assign(db, sample_id, test_id):
    at = AssignedTest(sample_id=sample_id, test_id=test_id, mandatory=True, enabled=True, status="PENDING")
    db.add(at)
    db.flush()
    return at


def _run(db, at, attempt_number, result, margin_pct=None):
    run = TestRun(assigned_test_id=at.id, attempt_number=attempt_number, raw_values={},
                   result=result, margin_pct=margin_pct)
    db.add(run)
    db.flush()
    at.accepted_attempt_id = run.id
    return run


def _seed_common(db, suffix):
    scientist = User(username=f"sci_{suffix}", password_hash="x", full_name="S", role="SCIENTIST")
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id=f"STD-{suffix}", name="IS 694")
    db.add(standard)
    db.flush()
    for test_id in ("TEST-PASS", "TEST-FAIL", "TEST-UNDETERMINED", "TEST-PENDING"):
        db.add(TestDefinition(test_id=f"{test_id}-{suffix}", name=test_id, unit="unit"))
    db.flush()
    return scientist, standard


def _build_sample_with_every_branch(db, sample_id, standard_id, scientist_id, suffix):
    s = _make_sample(db, sample_id, standard_id, scientist_id)
    _run(db, _assign(db, sample_id, f"TEST-PASS-{suffix}"), 1, "PASS")
    _run(db, _assign(db, sample_id, f"TEST-FAIL-{suffix}"), 1, "FAIL")
    _run(db, _assign(db, sample_id, f"TEST-UNDETERMINED-{suffix}"), 1, "UNDETERMINED", margin_pct=5.0)
    _assign(db, sample_id, f"TEST-PENDING-{suffix}")  # assigned, never submitted
    return s


def test_bulk_aggregation_matches_per_sample_aggregation_for_every_branch(db):
    scientist, standard = _seed_common(db, "A")
    samples = [
        _build_sample_with_every_branch(db, f"SMP-BULK-{i}", standard.standard_id, scientist.id, "A")
        for i in range(3)
    ]
    db.commit()

    per_sample = {s.sample_id: summarize_sample(db, s.sample_id, s.status) for s in samples}
    bulk = summarize_samples_bulk(db, samples)

    assert set(per_sample.keys()) == set(bulk.keys())
    for sample_id in per_sample:
        assert per_sample[sample_id] == bulk[sample_id]
        # sanity: every branch was actually exercised, not all-zero summaries
        assert per_sample[sample_id].completed_tests == 3
        assert per_sample[sample_id].passed == 1
        assert per_sample[sample_id].failed == 1
        assert per_sample[sample_id].undetermined == 1
        assert per_sample[sample_id].applicable_tests == 4  # includes the still-pending one


def test_bulk_aggregation_query_count_does_not_scale_with_sample_count(db):
    scientist, standard = _seed_common(db, "B")

    def build(n, offset):
        return [
            _build_sample_with_every_branch(db, f"SMP-COUNT-{offset + i}", standard.standard_id, scientist.id, "B")
            for i in range(n)
        ]

    small = build(2, 0)
    extra = build(8, 2)  # 8 more samples, same shape
    db.commit()
    # Re-fetch fresh from the DB rather than reusing the just-committed ORM
    # objects: SQLAlchemy's default expire_on_commit=True invalidates every
    # attribute on commit, so accessing e.g. s.sample_id on the *original*
    # objects below would itself trigger a refresh query per object -- an
    # artifact of this test's own setup, not something list_samples/
    # dashboard hit (they always pass freshly queried, never-expired Sample
    # objects straight from the same request's own db.query(Sample)...all()).
    small = db.query(Sample).filter(Sample.sample_id.in_([s.sample_id for s in small])).all()
    extra = db.query(Sample).filter(Sample.sample_id.in_([s.sample_id for s in extra])).all()

    def count_select_queries(fn):
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

    small_queries = count_select_queries(lambda: summarize_samples_bulk(db, small))
    large_queries = count_select_queries(lambda: summarize_samples_bulk(db, small + extra))

    # Bulk aggregation issues the same fixed number of queries regardless of
    # how many samples are in the batch. If this ever regressed back to
    # O(samples), large_queries would scale up with the extra 8 samples
    # instead of staying flat.
    assert small_queries == large_queries
    assert small_queries <= 3  # 1 for AssignedTest, 1 for TestRun -- constant, not per-sample
