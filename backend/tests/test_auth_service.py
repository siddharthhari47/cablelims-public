"""
Regression tests for H13: migrated from python-jose to PyJWT, and from
passlib to bcrypt directly. These test auth_service.py's functions in
isolation (no HTTP/DB needed) to lock in the exact contract the rest of
the app depends on -- a bcrypt hash that round-trips, and a JWT that
round-trips its claims and rejects tampering/expiry.
"""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.services import auth_service


def test_hash_password_produces_a_standard_bcrypt_hash():
    h = auth_service.hash_password("correct horse battery staple")
    # $2b$ (or $2a$/$2y$) is bcrypt's own format marker -- confirms this
    # is a real, portable bcrypt hash, not something passlib-specific that
    # only passlib itself could read back.
    assert h.startswith("$2")


def test_verify_password_round_trips():
    h = auth_service.hash_password("correct horse battery staple")
    assert auth_service.verify_password("correct horse battery staple", h) is True
    assert auth_service.verify_password("wrong password", h) is False


def test_verify_password_accepts_a_standard_bcrypt_hash_from_any_producer():
    # Bcrypt hashes are self-describing and fully portable regardless of
    # which library produced them ($2b$12$... is bcrypt's own format, not
    # anything passlib-specific) -- this is a hash produced independently
    # via the bcrypt library directly (as passlib's bcrypt handler itself
    # always did internally), confirming every existing user's stored
    # password_hash keeps working after switching to calling bcrypt
    # directly, with no re-hash/migration step needed for existing
    # accounts.
    independently_produced_hash = "$2b$12$rCEV7/ij9TNHcl9JlM6v.O2heCa7y4bxCuL8VuvuPLwH1.bCJ7lbK"
    assert auth_service.verify_password("demo1234", independently_produced_hash) is True
    assert auth_service.verify_password("wrong", independently_produced_hash) is False


def test_create_and_decode_access_token_round_trips_claims():
    token = auth_service.create_access_token("user-1", "sci1", "SCIENTIST", "Dr. Test", token_version=3)
    payload = auth_service.decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["username"] == "sci1"
    assert payload["role"] == "SCIENTIST"
    assert payload["full_name"] == "Dr. Test"
    assert payload["tv"] == 3
    assert "exp" in payload


def test_decode_access_token_rejects_garbage():
    assert auth_service.decode_access_token("not-a-real-token") is None


def test_decode_access_token_rejects_a_token_signed_with_a_different_key():
    forged = pyjwt.encode({"sub": "attacker", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                           "a-completely-different-secret-key-not-the-real-one", algorithm=auth_service.ALGORITHM)
    assert auth_service.decode_access_token(forged) is None


def test_decode_access_token_rejects_an_expired_token():
    expired = pyjwt.encode(
        {"sub": "user-1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        auth_service.SECRET_KEY, algorithm=auth_service.ALGORITHM,
    )
    assert auth_service.decode_access_token(expired) is None
