"""
Regression tests for §10.1/§7.6: there was no global exception handler, so
any unhandled exception (float() on a bad value, a math domain error, a
sequence IntegrityError, a missing template file) produced a generic 500
with a raw stack trace to the client, and nowhere logged it -- the entire
application had exactly one deliberate output statement.

Note: C9's typed reading validation already closed off the specific
calculator-level crash vectors the review named (a malformed float in a
readings list, an out-of-domain temperature) before they can ever reach
`run_calculation`, so this file proves the handler itself works correctly
by deliberately forcing an unhandled exception via a mock, rather than by
finding a still-live crash to reproduce -- the point under test is "does an
unexpected exception get logged and turned into a clean response", not
"can we still find a way to crash a calculator."
"""
import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.logging_config import LOGS_DIR
from app.main import app
from app.models.models import AssignedTest, CableProfile, Sample, Standard, TestDefinition, User
from app.services.auth_service import hash_password


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestSessionLocal()
    scientist = User(username="sci_log", full_name="Scientist Log", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(scientist)
    db.flush()

    standard = Standard(standard_id="STD-LOG", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-LOG-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=scientist.id, assigned_assistant_id=scientist.id)
    db.add(sample)
    db.flush()

    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                            confirmed=True, tested_core_colors=["RED"])
    db.add(profile)
    db.add(TestDefinition(test_id="TEST-0019", name="Heat Shock Test", unit="pass/fail", scope="ONCE"))
    db.flush()
    at = AssignedTest(sample_id=sample.sample_id, test_id="TEST-0019", mandatory=True,
                       enabled=True, status="PENDING", core_position=None)
    db.add(at)
    db.commit()
    at_id = at.id
    db.close()

    with TestClient(app, raise_server_exceptions=False) as c:
        c.sample_id = "SMP-LOG-0001"
        c.assigned_test_id = at_id
        yield c

    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "sci_log", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_an_unhandled_exception_returns_a_clean_500_not_a_raw_traceback(client):
    token = _token(client)
    with patch("app.services.sample_service.run_calculation", side_effect=RuntimeError("boom -- simulated unexpected failure")):
        resp = client.post(
            f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
            json={"raw_values": {"cracks_observed": False}},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 500
    body = resp.json()
    assert "boom" not in str(body)  # no raw exception text/stack trace leaked to the client
    assert "detail" in body


def test_the_request_id_header_is_present_on_every_response(client):
    resp = client.get("/api/health")
    assert "x-request-id" in {k.lower() for k in resp.headers.keys()}


def test_a_client_supplied_request_id_is_honoured(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "test-fixed-id-123"})
    assert resp.headers.get("x-request-id") == "test-fixed-id-123"


def test_unhandled_exception_is_actually_written_to_the_log_file(client):
    log_path = os.path.join(LOGS_DIR, "cablelims.log")
    size_before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

    token = _token(client)
    marker = f"marker-{uuid.uuid4().hex}"
    with patch("app.services.sample_service.run_calculation", side_effect=RuntimeError(marker)):
        client.post(
            f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
            json={"raw_values": {"cracks_observed": False}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        f.seek(size_before)
        new_content = f.read()
    assert marker in new_content
    assert "ERROR" in new_content


def test_normal_requests_still_succeed(client):
    token = _token(client)
    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
        json={"raw_values": {"cracks_observed": False}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
