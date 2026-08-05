"""Auth: password hashing + JWT issuance/verification. Simple by design for
a one-day MVP -- role-based authorization is enforced in the API layer via
`require_role`, which is the part that must not be skipped.

H13: uses PyJWT (not python-jose, which has known CVEs and is effectively
unmaintained) and bcrypt directly (not passlib, whose bcrypt backend has a
well-known compatibility break against bcrypt>=4.1 -- it was already
running in a degraded, warning-emitting fallback mode against this app's
own pinned bcrypt version before this change, with no actual behavioral
difference from calling bcrypt directly for any real password)."""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.config import settings


def _load_or_create_secret_key() -> str:
    """Never hardcode the JWT signing secret. Prefer an environment variable
    (set CABLELIMS_SECRET_KEY for a real deployment); otherwise generate a
    random key once and persist it locally so it survives a server restart
    without every existing login session being invalidated, but without ever
    being a predictable, shared, or source-controlled string."""
    env_key = os.environ.get("CABLELIMS_SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", ".secret_key"
    )
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if os.path.isfile(key_path):
        with open(key_path, "r") as f:
            existing = f.read().strip()
            if existing:
                return existing
    generated = secrets.token_hex(32)
    with open(key_path, "w") as f:
        f.write(generated)
    return generated


SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, username: str, role: str, full_name: str, token_version: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "full_name": full_name,
        # H6: checked against User.token_version on every request (see
        # api.deps.get_current_user) -- bumping the column instantly
        # invalidates every token issued before that bump, regardless of
        # its exp. See User.token_version's own docstring for why.
        "tv": token_version,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
