import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models.models import Certificate, Sample, User

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


@router.get("/{certificate_no:path}/download")
def download_certificate(certificate_no: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cert = db.query(Certificate).filter(Certificate.certificate_no == certificate_no).first()
    if not cert or not cert.file_path or not os.path.exists(cert.file_path):
        raise HTTPException(404, "Certificate not found")
    # Certificate numbers are strictly sequential (CTL/CBL/2026/0001, 0002,
    # ...), so without this any authenticated user -- any role -- could
    # download every certificate the lab has ever issued just by counting.
    # Same ownership rule as every sample-scoped route: a Scientific
    # Assistant may only reach a certificate for a sample assigned to them;
    # SCIENTIST/ADMINISTRATOR are unrestricted, matching list_samples'
    # existing scoping. 404, not 403, so a blocked caller can't infer the
    # certificate exists at all.
    sample = db.query(Sample).filter(Sample.sample_id == cert.sample_id).first()
    if user.role == "SCIENTIFIC_ASSISTANT" and (not sample or sample.assigned_assistant_id != user.id):
        raise HTTPException(404, "Certificate not found")
    ext = os.path.splitext(cert.file_path)[1].lower()
    safe_name = certificate_no.replace("/", "_") + ext
    return FileResponse(cert.file_path, media_type=MEDIA_TYPES.get(ext, "application/octet-stream"), filename=safe_name)
