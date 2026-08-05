from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import LOCKED_STATUSES, Sample, User
from app.services.auth_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if not user.is_active:
        # Deactivated mid-session -- the existing token must stop working
        # immediately, not just block a future login.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account has been deactivated")
    # H6: a token minted before the user's most recent password change (or
    # any other future action that bumps token_version) carries a stale
    # "tv" claim -- reject it here so a stolen/previously-shared token stops
    # working the moment the password is changed, not just at its natural
    # 12-hour expiry. payload.get("tv") (rather than payload["tv"]) also
    # means a token issued before this feature existed -- which has no "tv"
    # claim at all -- correctly fails this comparison too, forcing exactly
    # one re-login after upgrading to this version.
    if payload.get("tv") != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been invalidated -- please log in again")
    return user


def require_roles(*roles):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user
    return _dep


def get_authorized_sample(*, allow_locked: bool = False):
    """Dependency factory for every {sample_id}-scoped route.

    Loads the Sample and enforces the two checks that were previously
    either missing entirely or copy-pasted inconsistently across
    api/samples.py:

    1. Object-level authorization -- a SCIENTIFIC_ASSISTANT may only reach a
       sample assigned to them. Sample IDs are sequential and guessable
       (SMP-2026-0001, -0002, ...), so without this any assistant could read
       or -- far worse -- submit readings against any sample in the lab,
       attributed to them, feeding the calculation/confidence engines and
       potentially reaching an issued certificate. SCIENTIST and
       ADMINISTRATOR are unrestricted here, matching list_samples' existing
       scoping (which only ever filtered SCIENTIFIC_ASSISTANT).

       A missing/unauthorized sample both return 404, never 403 -- a 403
       would confirm to an assistant that a sample they can't see exists.

    2. Lock enforcement -- once a sample is APPROVED/REPORT_GENERATED/
       ARCHIVED, mutating endpoints must reject the request rather than
       silently reopening a certified record. Pass allow_locked=True for
       read-only or already-self-checking endpoints (e.g. certificate
       generation, which has its own more specific status check).
    """
    def _dep(sample_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Sample:
        sample = db.query(Sample).filter(Sample.sample_id == sample_id).first()
        if not sample:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample not found")
        if user.role == "SCIENTIFIC_ASSISTANT" and sample.assigned_assistant_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample not found")
        if not allow_locked and sample.status in LOCKED_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Sample is {sample.status} and locked -- this action is no longer available "
                "(post-approval changes require a Scientist-approved revision).",
            )
        return sample
    return _dep
