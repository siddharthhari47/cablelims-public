"""
Regression tests for H19: CORSMiddleware previously allowed allow_origins=["*"]
unconditionally -- any third-party page could read this API's JSON responses
cross-origin (Bearer-token auth makes CSRF moot, but says nothing about
response readability, which is what CORS actually governs). The default is
now a short, explicit allowlist (the local Vite dev origin only) instead of
a wildcard -- see app/config.py's own comment on cors_allowed_origins for
why the documented deployment never needs a broader one.

These tests exercise the actual CORSMiddleware behavior via TestClient, not
just the Settings value -- starlette's CORSMiddleware doesn't reject a
disallowed origin with an error status; it simply omits
Access-Control-Allow-Origin from the response, which is what makes the
browser (not the server) block the calling page from reading it.
"""
from fastapi.testclient import TestClient

from app.main import app


def _preflight(client, origin):
    return client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_allowed_origin_gets_the_cors_header():
    with TestClient(app) as client:
        resp = _preflight(client, "http://localhost:5173")
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_disallowed_origin_gets_no_cors_header():
    with TestClient(app) as client:
        resp = _preflight(client, "http://evil.example.com")
    assert "access-control-allow-origin" not in resp.headers


def test_wildcard_is_not_the_default_allowlist():
    # The regression this whole file guards against: allow_origins=["*"]
    # would make the disallowed-origin test above fail (a wildcard answers
    # every Origin), so this asserts the configured value directly too.
    from app.config import settings
    assert "*" not in settings.cors_allowed_origins
