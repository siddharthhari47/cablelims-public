"""
The single place that resolves "which result actually counts" for a
TestRun. Everywhere else that used to read `run.result` directly for a
PASS/FAIL/UNDETERMINED decision (aggregation, the certificate/observation-
sheet fillers, the Calculation view) must go through this instead, so a
Scientist override can never be silently ignored in one place while being
honoured in another.

TestRun rows are immutable once submitted (see TestRun's docstring) -- an
override never rewrites `result`/`calculated_value`/etc; it adds a
separate, explicitly-flagged layer on top, and this function is what
resolves the two into one effective answer.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import AssignedTest, TestRun


def get_accepted_run(db: Session, assigned_test: AssignedTest) -> Optional[TestRun]:
    """The run that actually counts for this assigned test right now.

    Every "which reading matters" query used to independently re-derive
    "latest attempt" via `ORDER BY attempt_number DESC LIMIT 1` -- five
    separate places (this module's own callers: the API detail view, the
    certificate/observation-sheet filler, sample aggregation, and the
    override/verify endpoints). That meant a Scientist's override, which
    submit_reading records by pointing `assigned_test.accepted_attempt_id`
    at the overridden run, was silently invisible again the moment a later
    attempt was submitted and became the new MAX(attempt_number) -- nothing
    read the pointer that was supposed to protect it.

    `accepted_attempt_id` is now load-bearing: prefer it when set, and only
    fall back to the latest attempt when it isn't (e.g. no reading has ever
    been submitted for this test yet). submit_reading refuses to move this
    pointer past an overridden run without an explicit repeat request first
    (see its own docstring) -- that is the other half of this same
    invariant, on the write side.
    """
    if assigned_test.accepted_attempt_id:
        run = db.query(TestRun).filter(TestRun.id == assigned_test.accepted_attempt_id).first()
        if run:
            return run
    return (
        db.query(TestRun)
        .filter(TestRun.assigned_test_id == assigned_test.id)
        .order_by(TestRun.attempt_number.desc())
        .first()
    )


def effective_result(run) -> Optional[str]:
    if run is None:
        return None
    if run.overridden and run.override_result:
        return run.override_result
    return run.result


def effective_limit_display(run) -> Optional[str]:
    """For UI/report display -- the limit actually being judged against."""
    if run is None:
        return None
    if run.overridden and run.override_limit_value is not None:
        return f"{run.limit_operator or ''} {run.override_limit_value}".strip()
    if run.limit_value is not None:
        return f"{run.limit_operator or ''} {run.limit_value}".strip()
    return None
