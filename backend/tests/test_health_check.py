"""
Regression tests for §10.2: GET /api/health returned {"status": "ok"}
unconditionally -- it never touched the database, never checked the report
templates existed, never checked disk space. A completely broken
application (dead database connection, a template deleted by an antivirus
quarantine, a full disk) would still report healthy, and nothing would ever
notice or alert on it.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_check_is_ok_under_normal_conditions(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["certificate_template"] == "ok"
    assert body["checks"]["observation_sheet_template"] == "ok"
    assert body["checks"]["disk_space"].startswith("ok")


def test_health_check_reports_503_and_missing_when_a_template_is_absent(client):
    with patch("app.main.CERTIFICATE_TEMPLATE_PATH", "C:\\does\\not\\exist.docx"):
        resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["certificate_template"].startswith("missing")
    # Everything else must still be individually reported, not masked by
    # the one failure -- a real operator needs to see the whole picture.
    assert body["checks"]["database"] == "ok"


def test_health_check_reports_503_when_the_database_is_unreachable(client):
    class _BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("simulated database connection failure")

    def _broken_get_db():
        yield _BrokenSession()

    from app.db import get_db
    app.dependency_overrides[get_db] = _broken_get_db
    try:
        resp = client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert "unreachable" in body["checks"]["database"]


def test_health_check_reports_503_when_disk_space_is_low(client):
    class _FakeUsage:
        free = 100 * 1024 * 1024  # 100 MB -- below the 500 MB threshold

    with patch("app.main.shutil.disk_usage", return_value=_FakeUsage()):
        resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["disk_space"].startswith("low")


def test_health_check_does_not_require_authentication(client):
    # A monitoring tool polling this endpoint shouldn't need a login --
    # confirmed by NOT sending an Authorization header at all.
    resp = client.get("/api/health")
    assert resp.status_code in (200, 503)  # never 401/403
