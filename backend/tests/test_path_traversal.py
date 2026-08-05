"""
Regression test for SEC-1: unauthenticated arbitrary-file-read via the SPA
catch-all route in app.main.serve_frontend.

Before the fix, a request like GET /%2e%2e/%2e%2e/backend/data/.secret_key
escaped FRONTEND_DIST and returned the JWT signing key (or the database, or
any other file the process can read) to an unauthenticated caller. The
encoded form matters: Starlette percent-decodes the path *after* routing, so
"%2e%2e" reaches the handler as ".." even though a well-behaved HTTP client
would have already normalised a literal "../" away.

This must stay passing after any future change to serve_frontend.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import FRONTEND_DIST, app

client = TestClient(app)


def test_frontend_dist_actually_exists():
    # If this ever stops being true (e.g. a dev checkout with no `npm run
    # build` yet), the traversal route below isn't even registered and the
    # rest of this file would be silently testing nothing.
    assert os.path.isdir(FRONTEND_DIST), (
        "frontend/dist is missing -- run `npm run build` in cablelims/frontend "
        "before running this test, otherwise the SPA catch-all route (and the "
        "vulnerability it tests for) is never registered."
    )


TRAVERSAL_PAYLOADS = [
    "/%2e%2e/%2e%2e/backend/data/.secret_key",
    "/%2e%2e%2f%2e%2e%2fbackend%2fdata%2f.secret_key",
    "/assets/%2e%2e/%2e%2e/%2e%2e/backend/data/.secret_key",
    "/..%2f..%2fbackend/data/.secret_key",
]


@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
def test_encoded_traversal_cannot_escape_frontend_dist(payload):
    resp = client.get(payload, follow_redirects=False)
    # The fixed handler must never serve the escaped file. It either falls
    # back to index.html (200, containing the SPA shell) or the request
    # never reaches a real file (404) -- either is acceptable; what is NOT
    # acceptable is the secret key's actual content coming back.
    assert "-----BEGIN" not in resp.text
    secret_path = os.path.join(os.path.dirname(os.path.dirname(FRONTEND_DIST)), "backend", "data", ".secret_key")
    if os.path.exists(secret_path):
        with open(secret_path, "r", encoding="utf-8", errors="ignore") as f:
            secret_content = f.read().strip()
        assert secret_content not in resp.text, (
            f"Path traversal succeeded: payload {payload!r} returned the actual "
            "contents of backend/data/.secret_key"
        )


def test_traversal_falls_back_to_spa_shell():
    resp = client.get("/%2e%2e/%2e%2e/backend/data/.secret_key")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        # Should be index.html (the SPA shell), not an arbitrary file.
        assert "<div id=" in resp.text or "<html" in resp.text.lower()


def test_legitimate_spa_route_still_falls_back_to_index():
    # Regression check: the containment fix must not break normal client-side
    # routing (e.g. a bookmarked /dashboard deep link or a page refresh).
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()


def test_legitimate_static_asset_still_served():
    # manifest.json ships in every build; confirms real, in-bounds files
    # still resolve correctly after adding the containment check.
    resp = client.get("/manifest.json")
    assert resp.status_code == 200
