"""
Sample-level aggregation for the "System Decision" panel and dashboards.
Pure read-side aggregation -- computes a summary from AssignedTest/TestRun
rows already decided by the Confidence Engine; makes no decisions itself.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.engines.result_utils import effective_result
from app.models.models import LOCKED_STATUSES, AssignedTest, Sample, TestRun


@dataclass
class SampleDecisionSummary:
    applicable_tests: int
    completed_tests: int
    passed: int
    failed: int
    undetermined: int
    repeat_required: List[str] = field(default_factory=list)
    overall_confidence_pct: Optional[float] = None
    overall_status: str = "IN_PROGRESS"


def pick_accepted_run(assigned_test: AssignedTest, candidate_runs: List[TestRun]) -> Optional[TestRun]:
    """Same resolution rule as engines.result_utils.get_accepted_run (prefer
    accepted_attempt_id when set, otherwise the highest attempt_number), but
    operating on an already-fetched list of this assigned test's runs
    instead of issuing its own query.

    Deliberately NOT reusing get_accepted_run itself: that function's whole
    point is to avoid fetching every attempt when accepted_attempt_id is
    already known (a single targeted WHERE id = ? lookup covers the common
    case) -- exactly right for resolving one test's result, but the wrong
    shape for bulk aggregation below, which needs every sample's every
    test's runs pre-fetched in one query rather than issued per-test. The
    two implementations are intentionally duplicated in miniature rather
    than forcing get_accepted_run's per-call query pattern to change for a
    problem (N+1 across samples) it isn't the one causing -- see H5's
    Phase 8 report.

    B7 (Review #2 remediation): public (no leading underscore) because
    sample_service.get_sample_detail now reuses it too, for the same
    N+1 reason -- one shared "which run counts" rule, used everywhere a
    caller already has runs pre-fetched instead of resolving per-test."""
    if assigned_test.accepted_attempt_id:
        for run in candidate_runs:
            if run.id == assigned_test.accepted_attempt_id:
                return run
    if not candidate_runs:
        return None
    return max(candidate_runs, key=lambda r: r.attempt_number)


def _summarize(
    assigned: List[AssignedTest], runs_by_assigned_test: Dict[str, List[TestRun]], sample_status: Optional[str]
) -> SampleDecisionSummary:
    applicable = len(assigned)
    completed = 0
    passed = 0
    failed = 0
    undetermined = 0
    repeat_required = []
    confidences = []

    for at in assigned:
        latest = pick_accepted_run(at, runs_by_assigned_test.get(at.id, []))
        result = effective_result(latest)
        if not latest or result == "PENDING":
            continue
        completed += 1
        if result == "PASS":
            passed += 1
            confidences.append(100.0)
        elif result == "FAIL":
            failed += 1
            confidences.append(100.0)
        else:  # UNDETERMINED
            undetermined += 1
            label = at.test_definition.name if at.test_definition else at.test_id
            if at.core_position:
                label = f"{label} ({at.core_position.title()})"
            repeat_required.append(label)
            # confidence proxy: closer margin -> lower score; unknown margin -> 70
            # H12: the SQLAlchemy mypy plugin can't fully resolve a plain
            # Column(Float) (vs. the newer mapped_column() style) to a
            # concrete `float | None` -- it's genuinely that type at
            # runtime (proven by the golden-value/aggregation test suites),
            # just imprecisely typed by the plugin. Not worth migrating the
            # whole ORM layer to mapped_column() just to resolve this.
            margin = latest.margin_pct
            if margin is not None:
                confidences.append(max(50.0, 100 - abs(margin) * 3))  # type: ignore[operator]
            else:
                confidences.append(70.0)

    overall_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None

    if sample_status in LOCKED_STATUSES:
        # The sample has already moved past scientist review (and possibly has
        # a certificate). The panel must reflect that real lifecycle state,
        # not re-derive a "needs review" status from raw test counts -- an
        # already-certified sample must never look like it's still pending.
        status = sample_status
    elif applicable == 0:
        status = "AWAITING_TEST_ASSIGNMENT"
    elif completed < applicable:
        status = "TESTING_IN_PROGRESS"
    elif failed > 0 or undetermined > 0:
        status = "UNDER_SCIENTIST_REVIEW"
    else:
        status = "READY_FOR_APPROVAL"

    return SampleDecisionSummary(
        applicable_tests=applicable,
        completed_tests=completed,
        passed=passed,
        failed=failed,
        undetermined=undetermined,
        repeat_required=repeat_required,
        overall_confidence_pct=overall_confidence,
        overall_status=status,
    )


def _fetch_runs_by_assigned_test(db: Session, assigned_test_ids: List[str]) -> Dict[str, List[TestRun]]:
    if not assigned_test_ids:
        return {}
    runs_by_assigned_test: Dict[str, List[TestRun]] = {}
    for run in db.query(TestRun).filter(TestRun.assigned_test_id.in_(assigned_test_ids)).all():
        runs_by_assigned_test.setdefault(run.assigned_test_id, []).append(run)
    return runs_by_assigned_test


def summarize_sample(db: Session, sample_id: str, sample_status: Optional[str] = None) -> SampleDecisionSummary:
    assigned = (
        db.query(AssignedTest)
        # joinedload: _summarize's UNDETERMINED branch reads
        # at.test_definition.name for the repeat_required label -- without
        # this, that's a lazy-loaded query per UNDETERMINED test, a second,
        # smaller N+1 alongside the one summarize_samples_bulk below exists
        # to fix (found by this change's own test_bulk_aggregation_query_
        # count_does_not_scale_with_sample_count test).
        .options(joinedload(AssignedTest.test_definition))
        .filter(AssignedTest.sample_id == sample_id, AssignedTest.enabled == True)  # noqa: E712
        .all()
    )
    runs_by_assigned_test = _fetch_runs_by_assigned_test(db, [at.id for at in assigned])
    return _summarize(assigned, runs_by_assigned_test, sample_status)


def summarize_samples_bulk(db: Session, samples: List[Sample]) -> Dict[str, SampleDecisionSummary]:
    """Same result as calling summarize_sample() once per sample, in a
    constant number of queries instead of one round-trip per sample (H5):
    list_samples and the dashboard each used to call summarize_sample() in
    a loop, and summarize_sample() itself used to call get_accepted_run()
    once per assigned test -- for a lab with dozens of samples and ~20
    tests each, that's hundreds of queries on every single page load.
    Here: one query for every assigned test across every requested sample,
    one query for every run those tests have, then the exact same
    per-sample math as summarize_sample() runs entirely in memory."""
    sample_ids = [s.sample_id for s in samples]
    if not sample_ids:
        return {}

    assigned = (
        db.query(AssignedTest)
        .options(joinedload(AssignedTest.test_definition))
        .filter(AssignedTest.sample_id.in_(sample_ids), AssignedTest.enabled == True)  # noqa: E712
        .all()
    )
    runs_by_assigned_test = _fetch_runs_by_assigned_test(db, [at.id for at in assigned])

    assigned_by_sample: Dict[str, List[AssignedTest]] = {}
    for at in assigned:
        assigned_by_sample.setdefault(at.sample_id, []).append(at)

    return {
        s.sample_id: _summarize(assigned_by_sample.get(s.sample_id, []), runs_by_assigned_test, s.status)
        for s in samples
    }


def overall_decision_from_summary(summary: SampleDecisionSummary) -> str:
    """Single source of truth for 'what does this sample's certificate say
    overall' -- used by both the live certificate-generation endpoint and the
    demo seed script, so a pre-seeded historical sample can never claim a
    cleaner result than its own test outcomes actually support."""
    if summary.failed > 0:
        return "FAIL"
    if summary.undetermined == 0:
        return "PASS"
    return "MANUAL_REVIEW_APPROVED"
