"""
Administrator console API: account management (create/edit/deactivate,
role assignment) and audit-log viewing. Everything here is ADMINISTRATOR-
only -- create_user.py remains the break-glass path for the very first
account on a fresh install (before any Administrator exists to use this).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db import get_db
from app.models.models import AuditEvent, User, iso_utc
from app.schemas.admin import AuditListResponse, UserOut
from app.services.auth_service import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_ROLES = ("SCIENTIST", "SCIENTIFIC_ASSISTANT", "ADMINISTRATOR")


def _audit(db, user, action, entity_type, entity_id, details=None):
    db.add(AuditEvent(actor_id=user.id, actor_name=user.full_name, action=action,
                       entity_type=entity_type, entity_id=entity_id, details=details or {}))


def _user_out(u: User):
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
        "is_active": u.is_active, "is_demo": u.is_demo, "created_at": iso_utc(u.created_at),
    }


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_roles("ADMINISTRATOR"))):
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [_user_out(u) for u in users]


class CreateUserRequest(BaseModel):
    username: str
    full_name: str
    role: str
    password: str


@router.post("/users", response_model=UserOut)
def create_user(body: CreateUserRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("ADMINISTRATOR"))):
    username = body.username.strip()
    if not username:
        raise HTTPException(400, "Username is required")
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"role must be one of {VALID_ROLES}")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, f"Username '{username}' already exists")

    new_user = User(
        username=username, full_name=body.full_name.strip() or username, role=body.role,
        password_hash=hash_password(body.password), is_active=True, is_demo=False,
    )
    db.add(new_user)
    db.flush()
    _audit(db, user, "USER_CREATED", "user", new_user.id, {"username": username, "role": body.role})
    db.commit()
    return _user_out(new_user)


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # if provided, resets the password


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UpdateUserRequest, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("ADMINISTRATOR"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id and body.is_active is False:
        raise HTTPException(400, "You cannot deactivate your own account")

    changes: Dict[str, Any] = {}
    if body.full_name is not None and body.full_name.strip():
        target.full_name = body.full_name.strip()
        changes["full_name"] = target.full_name
    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(400, f"role must be one of {VALID_ROLES}")
        target.role = body.role
        changes["role"] = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        target.password_hash = hash_password(body.password)
        # H6: invalidates every token this account currently holds -- an
        # Administrator resetting someone's password is exactly the case
        # session revocation exists for (e.g. a suspected compromised
        # account), so the old password's tokens must stop working
        # immediately, not linger until their natural 12-hour expiry.
        target.token_version += 1
        changes["password_reset"] = True

    _audit(db, user, "USER_UPDATED", "user", target.id, changes)
    db.commit()
    return _user_out(target)


@router.get("/audit", response_model=AuditListResponse)
def list_audit(limit: int = 100, offset: int = 0, entity_type: Optional[str] = None,
               db: Session = Depends(get_db), user: User = Depends(require_roles("ADMINISTRATOR"))):
    limit = min(max(limit, 1), 500)
    q = db.query(AuditEvent)
    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type)
    total = q.count()
    rows = q.order_by(AuditEvent.timestamp.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "events": [
            {
                "id": e.id, "actor_name": e.actor_name, "action": e.action,
                "entity_type": e.entity_type, "entity_id": e.entity_id,
                "details": e.details, "timestamp": iso_utc(e.timestamp),
            }
            for e in rows
        ],
    }
