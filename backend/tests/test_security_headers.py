"""
Regression test for B10 (Review #2 remediation): no global security-headers
middleware existed -- only the diagram-download endpoint set
X-Content-Type-Options itself (C7). main.security_headers_middleware now
sets X-Content-Type-Options, X-Frame-Options, and Referrer-Policy on every
response. Same pattern as test_cors.py -- exercises the actual middleware
via TestClient, not just reads the source.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_every_response_carries_the_security_headers():
    with TestClient(app) as client:
        # /api/health needs no auth and always returns something -- any
        # route would do, since this middleware runs on every request.
        resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_headers_are_present_even_on_an_error_response():
    with TestClient(app) as client:
        resp = client.get("/api/samples/does-not-exist")  # 401, no auth header sent
    assert resp.status_code == 401
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
