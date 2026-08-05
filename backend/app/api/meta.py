from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models.models import Standard, User
from app.schemas.meta import AssistantOut, StandardOut

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/standards", response_model=List[StandardOut])
def list_standards(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(Standard).all()
    return [{"standard_id": s.standard_id, "name": s.name, "edition": s.edition,
             "amendment": s.amendment, "scope_summary": s.scope_summary} for s in rows]


@router.get("/assistants", response_model=List[AssistantOut])
def list_assistants(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(User).filter(User.role == "SCIENTIFIC_ASSISTANT").all()
    return [{"id": u.id, "full_name": u.full_name, "username": u.username} for u in rows]
