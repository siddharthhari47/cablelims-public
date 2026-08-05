from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.engines.aggregation import summarize_samples_bulk
from app.models.models import LOCKED_STATUSES, AuditEvent, Certificate, Sample, User, iso_utc
from app.schemas.dashboard import DashboardResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Sample)
    if user.role == "SCIENTIFIC_ASSISTANT":
        q = q.filter(Sample.assigned_assistant_id == user.id)
    samples = q.all()

    pending = sum(1 for s in samples if s.status in ("REGISTERED", "PROFILE_PENDING"))
    in_progress = sum(1 for s in samples if s.status in ("PROFILE_VERIFIED", "TESTING", "REPEAT_REQUIRED"))
    scientist_review = sum(1 for s in samples if s.status == "SCIENTIST_REVIEW")
    completed = sum(1 for s in samples if s.status in LOCKED_STATUSES)
    # Only count repeat-needed tests on samples still actively in the lab --
    # an already-approved/archived sample's historical UNDETERMINED tests were
    # resolved via manual review and must not inflate an "active work" KPI.
    #
    # H5: one bulk aggregation pass for every active sample, instead of
    # summarize_sample() in a loop (itself a query per assigned test) --
    # was O(active samples x tests) queries on every dashboard load.
    active_samples = [s for s in samples if s.status not in LOCKED_STATUSES]
    summaries = summarize_samples_bulk(db, active_samples)
    repeat_tests = sum(len(summary.repeat_required) for summary in summaries.values())

    # Scoped the same way `samples` above already is -- an Assistant should
    # see the certificate count for their own work, not the whole lab's.
    cert_q = db.query(Certificate)
    if user.role == "SCIENTIFIC_ASSISTANT":
        cert_q = cert_q.join(Sample, Certificate.sample_id == Sample.sample_id).filter(
            Sample.assigned_assistant_id == user.id
        )
    certificates_issued = cert_q.count()

    recent = (
        db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(12).all()
    )
    recent_activity = [
        {"actor": a.actor_name, "action": a.action, "entity_type": a.entity_type,
         "entity_id": a.entity_id, "timestamp": iso_utc(a.timestamp)}
        for a in recent
    ]

    return {
        "total_samples": len(samples),
        "pending": pending,
        "in_progress": in_progress,
        "scientist_review": scientist_review,
        "completed": completed,
        "repeat_tests": repeat_tests,
        "certificates_issued": certificates_issued,
        "recent_activity": recent_activity,
    }
