from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_authorized_sample, get_current_user, require_roles
from app.db import get_db
from app.models.models import Sample, User
from app.schemas.common import OkResponse
from app.schemas.samples import (
    CertificateGenerateResponse,
    CreateSampleResponse,
    MarkingImageUploadResponse,
    OverrideResponse,
    ProfileSubmitResponse,
    ReviewResponse,
    SampleDetailOut,
    SampleListItem,
    SubmitReadingResponse,
)
from app.services import sample_service as svc

router = APIRouter(prefix="/api/samples", tags=["samples"])

# Sprint Priority 6 / Sprint Priority 10 (object-level authorization): the
# lock check and the "is this caller allowed to touch this sample at all"
# check now both live in api.deps.get_authorized_sample, applied per-route
# below, rather than each endpoint separately fetching the Sample and
# re-deciding.
#
# H2: every route here is a thin HTTP controller -- parse the request,
# resolve auth/ownership, hand off to app.services.sample_service, return
# whatever it hands back. All business logic (queries, mutations, audit
# entries, commits) lives in that module now.


@router.get("", response_model=List[SampleListItem])
def list_samples(db: Session = Depends(get_db), user: User = Depends(get_current_user), status_filter: Optional[str] = None):
    return svc.list_samples(db, user, status_filter)


@router.post("", response_model=CreateSampleResponse)
def create_sample(body: svc.CreateSampleRequest, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("SCIENTIST"))):
    return svc.create_sample(db, user, body)


@router.get("/{sample_id}", response_model=SampleDetailOut)
def get_sample(sample_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                sample: Sample = Depends(get_authorized_sample(allow_locked=True))):
    return svc.get_sample_detail(db, sample)


@router.post("/{sample_id}/profile", response_model=ProfileSubmitResponse)
def submit_profile(sample_id: str, body: svc.ProfileRequest, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("SCIENTIFIC_ASSISTANT", "SCIENTIST")),
                    sample: Sample = Depends(get_authorized_sample())):
    return svc.submit_profile(db, user, sample, body)


@router.post("/{sample_id}/marking-image", response_model=MarkingImageUploadResponse)
def upload_marking_image(sample_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(require_roles("SCIENTIFIC_ASSISTANT", "SCIENTIST")),
                          sample: Sample = Depends(get_authorized_sample())):
    return svc.upload_marking_image(db, user, sample, file)


@router.post("/{sample_id}/diagram-image", response_model=OkResponse)
def upload_diagram_image(sample_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(require_roles("SCIENTIFIC_ASSISTANT", "SCIENTIST")),
                          sample: Sample = Depends(get_authorized_sample())):
    return svc.upload_diagram_image(db, user, sample, file)


@router.get("/{sample_id}/diagram-image")
def download_diagram_image(sample_id: str, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user),
                            sample: Sample = Depends(get_authorized_sample(allow_locked=True))):
    path = svc.resolve_diagram_image_path(sample)
    # Every stored diagram is now a re-encoded JPEG (see
    # services/image_upload.py), so this can never actually serve anything
    # but image/jpeg -- these headers are extra defense-in-depth, not the
    # primary control. The frontend fetches this as a blob via the
    # authenticated client (see ProfileSummaryCard.tsx's
    # useAuthenticatedImage), which is unaffected by Content-Disposition.
    return FileResponse(path, media_type="image/jpeg",
                         headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment"})


@router.post("/{sample_id}/tests/{assigned_test_id}/toggle", response_model=OkResponse)
def toggle_test(sample_id: str, assigned_test_id: str, enabled: bool, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("SCIENTIST")),
                 sample: Sample = Depends(get_authorized_sample())):
    return svc.toggle_test(db, user, sample, assigned_test_id, enabled)


@router.post("/{sample_id}/tests/{assigned_test_id}/submit", response_model=SubmitReadingResponse)
def submit_reading(sample_id: str, assigned_test_id: str, body: svc.SubmitReadingRequest,
                    db: Session = Depends(get_db), user: User = Depends(require_roles("SCIENTIFIC_ASSISTANT", "SCIENTIST")),
                    sample: Sample = Depends(get_authorized_sample())):
    return svc.submit_reading(db, user, sample, assigned_test_id, body)


@router.post("/{sample_id}/tests/{assigned_test_id}/override", response_model=OverrideResponse)
def override_reading(sample_id: str, assigned_test_id: str, body: svc.OverrideRequest,
                      db: Session = Depends(get_db), user: User = Depends(require_roles("SCIENTIST")),
                      sample: Sample = Depends(get_authorized_sample())):
    return svc.override_reading(db, user, sample, assigned_test_id, body)


@router.post("/{sample_id}/tests/{assigned_test_id}/verify", response_model=OkResponse)
def verify_reading(sample_id: str, assigned_test_id: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("SCIENTIST")),
                    sample: Sample = Depends(get_authorized_sample())):
    return svc.verify_reading(db, user, sample, assigned_test_id)


@router.post("/{sample_id}/tests/{assigned_test_id}/repeat", response_model=OkResponse)
def request_repeat(sample_id: str, assigned_test_id: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("SCIENTIST")),
                    sample: Sample = Depends(get_authorized_sample())):
    return svc.request_repeat(db, user, sample, assigned_test_id)


@router.post("/{sample_id}/review", response_model=ReviewResponse)
def review_sample(sample_id: str, body: svc.ReviewRequest, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("SCIENTIST")),
                   sample: Sample = Depends(get_authorized_sample())):
    return svc.review_sample(db, user, sample, body)


@router.get("/{sample_id}/observation-sheet")
def download_observation_sheet(sample_id: str, db: Session = Depends(get_db),
                                user: User = Depends(require_roles("SCIENTIST", "SCIENTIFIC_ASSISTANT")),
                                sample: Sample = Depends(get_authorized_sample(allow_locked=True))):
    path = svc.build_observation_sheet(db, sample)
    safe_name = f"{sample_id}_ObservationSheet.docx"
    return FileResponse(
        path, filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/{sample_id}/certificate", response_model=CertificateGenerateResponse)
def generate_certificate(sample_id: str, db: Session = Depends(get_db),
                          user: User = Depends(require_roles("SCIENTIST")),
                          # allow_locked=True: APPROVED (the one status this endpoint
                          # requires) is itself one of LOCKED_STATUSES -- the generic
                          # lock check would otherwise reject the very state this
                          # action exists to act on. The status != "APPROVED" check
                          # inside sample_service.generate_certificate is the real,
                          # more specific gate.
                          sample: Sample = Depends(get_authorized_sample(allow_locked=True))):
    return svc.generate_certificate(db, user, sample)
