import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models.models import AuditEvent, User
from app.schemas.auth import DemoHintResponse, LoginResponse, MeResponse
from app.services.auth_service import create_access_token, hash_password, verify_password
from app.services.login_throttle import LOCKOUT_SECONDS, is_locked_out, record_failure, record_success

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/demo-hint", response_model=DemoHintResponse)
def demo_hint(db: Session = Depends(get_db)):
    """Public (no auth) -- tells the login page whether the seeded demo
    accounts actually exist on this install, so it never shows credentials
    that would just fail on a real production setup (see User.is_demo).

    B6 (Review #2 remediation): this must stay callable pre-login (it's
    what the login page itself uses to decide whether to render the hint,
    before any token exists -- see LoginPage.tsx) -- Depends(get_current_user)
    would make it always 401 and silently break the hint on every real
    demo/dev use, not just close the reconnaissance angle. The actual
    finding was that an anonymous caller against a real production install
    could poll this to check whether well-known demo credentials exist
    there. seed.py already gates demo-account *creation* on
    CABLELIMS_ALLOW_DEMO_USERS=1 being set in the environment -- a real
    install never sets it, so gating the *hint* on the same variable closes
    the oracle there without ever touching the database (nothing to learn
    from probing it) while leaving local dev/demo use, which already has
    the variable set, completely unaffected.
    """
    if os.environ.get("CABLELIMS_ALLOW_DEMO_USERS") != "1":
        return {"show_demo_hint": False}
    has_demo = db.query(User).filter(User.is_demo == True).first() is not None  # noqa: E712
    return {"show_demo_hint": has_demo}


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    locked, seconds_remaining = is_locked_out(body.username, ip)
    if locked:
        # Reject before touching the database or bcrypt at all -- a locked-
        # out caller gets no additional information (not even the cost of a
        # password-verify timing difference) and no additional database
        # load, which is also what stops this becoming its own trivial
        # denial-of-service vector against the single application process.
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed login attempts. Try again in about {int(seconds_remaining // 60) + 1} minute(s).",
        )

    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        newly_locked = record_failure(body.username, ip)
        # Logged with the username AS TYPED (actor_id is None -- there may
        # be no real user behind it) and the source IP, so a burst of
        # failed attempts is actually visible somewhere -- previously only
        # successful LOGIN events were audited at all.
        db.add(AuditEvent(actor_id=None, actor_name=body.username, action="LOGIN_FAILED",
                           entity_type="user", entity_id=body.username, details={"ip": ip}))
        if newly_locked:
            db.add(AuditEvent(actor_id=None, actor_name=body.username, action="LOGIN_LOCKED_OUT",
                               entity_type="user", entity_id=body.username,
                               details={"ip": ip, "lockout_seconds": LOCKOUT_SECONDS}))
        db.commit()
        # Pre-existing behaviour, unchanged here: a deactivated account gets
        # a distinct message rather than the uniform "Invalid username or
        # password" used for a wrong password or a nonexistent user. That is
        # a (minor, pre-existing) account-status oracle, not something this
        # rate-limiting change introduces or is scoped to fix.
        if user and user.is_active is False:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account has been deactivated")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    record_success(body.username, ip)
    token = create_access_token(user.id, user.username, user.role, user.full_name, user.token_version)
    db.add(AuditEvent(actor_id=user.id, actor_name=user.full_name, action="LOGIN",
                       entity_type="user", entity_id=user.id, details={"ip": ip}))
    db.commit()
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role},
    }


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=LoginResponse)
def change_password(body: ChangePasswordRequest, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Self-service password change (H6) -- any authenticated user, any
    role. Bumps token_version, which immediately invalidates every OTHER
    token this account currently has live (a shared device, an old
    session on another phone) -- but this request's own caller must not be
    logged out by their own action, so a freshly minted token (matching
    the new token_version) is returned in the same response the frontend
    already knows how to handle from /login, and authStore.login() re-uses
    it to replace the now-stale one it's holding."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be at least 8 characters")

    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.add(AuditEvent(actor_id=user.id, actor_name=user.full_name, action="PASSWORD_CHANGED",
                       entity_type="user", entity_id=user.id, details={}))
    db.commit()

    token = create_access_token(user.id, user.username, user.role, user.full_name, user.token_version)
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role},
    }
