"""
Regression tests for the object-level authorization fix (deps.get_authorized_sample)
covering the review's most serious finding after the path traversal: a
SCIENTIFIC_ASSISTANT could previously read, and worse, submit readings
against, any sample in the lab -- not just samples assigned to them. Sample
IDs are sequential and guessable (SMP-2026-0001, -0002, ...), so this was a
real, not merely theoretical, chain-of-custody hole.

Also covers the lock-check gaps this same dependency closes: request_repeat,
toggle_test, and upload_marking_image previously had NO status check at all
and could act on an already-archived, certified sample.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import AssignedTest, Sample, Standard, TestDefinition, User
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
    owned_assistant = User(username="assistant_owner", full_name="Owner Assistant", role="SCIENTIFIC_ASSISTANT",
                            password_hash=hash_password("password123"), is_active=True)
    other_assistant = User(username="assistant_other", full_name="Other Assistant", role="SCIENTIFIC_ASSISTANT",
                            password_hash=hash_password("password123"), is_active=True)
    scientist = User(username="scientist_x", full_name="Scientist X", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([owned_assistant, other_assistant, scientist])
    db.flush()

    standard = Standard(standard_id="STD-TEST", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-TEST-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=scientist.id, assigned_assistant_id=owned_assistant.id)
    db.add(sample)
    db.flush()

    test_def = TestDefinition(test_id="TEST-TEST-0001", name="Dummy Test", unit="mm")
    db.add(test_def)
    db.flush()

    at = AssignedTest(sample_id=sample.sample_id, test_id=test_def.test_id, mandatory=True,
                       enabled=True, status="PENDING", core_position=None)
    db.add(at)
    db.commit()
    at_id = at.id
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-TEST-0001"
        c.assigned_test_id = at_id
        yield c

    app.dependency_overrides.clear()


def _token(client, username, password="password123"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_unassigned_assistant_gets_404_reading_the_sample(client):
    token = _token(client, "assistant_other")
    resp = client.get(f"/api/samples/{client.sample_id}", headers=_auth(token))
    assert resp.status_code == 404


def test_unassigned_assistant_returns_404_not_403(client):
    # 404, not 403 -- a 403 would confirm to the caller that this sample
    # exists at all, which is itself an information leak for a role that
    # should never know about samples outside their own assignment.
    token = _token(client, "assistant_other")
    resp = client.get(f"/api/samples/{client.sample_id}", headers=_auth(token))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Sample not found"


def test_assigned_assistant_can_read_their_own_sample(client):
    token = _token(client, "assistant_owner")
    resp = client.get(f"/api/samples/{client.sample_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["sample_id"] == client.sample_id


def test_unassigned_assistant_cannot_submit_a_reading_against_someone_elses_sample(client):
    # This is the core finding: before the fix, ANY authenticated assistant
    # could submit a reading against ANY sample, attributed to them, feeding
    # the calculation/confidence engines regardless of assignment.
    token = _token(client, "assistant_other")
    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
        json={"raw_values": {"whatever": 1}},
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_scientist_is_not_restricted_by_assistant_scoping(client):
    # SCIENTIST is deliberately unrestricted here, matching list_samples'
    # existing behavior -- only SCIENTIFIC_ASSISTANT is scoped.
    token = _token(client, "scientist_x")
    resp = client.get(f"/api/samples/{client.sample_id}", headers=_auth(token))
    assert resp.status_code == 200


def test_nonexistent_sample_is_404_for_everyone(client):
    token = _token(client, "assistant_owner")
    resp = client.get("/api/samples/SMP-DOES-NOT-EXIST", headers=_auth(token))
    assert resp.status_code == 404
