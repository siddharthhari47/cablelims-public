"""
Regression tests for offline support phase 3a: submit_reading was not
idempotent -- every successful call unconditionally created a new TestRun
and could flip the whole Sample.status to SCIENTIST_REVIEW. An offline
client that queues a submission and later replays it (e.g. the sync
succeeded but the confirmation was lost) would otherwise silently create a
duplicate attempt and could re-trigger that status flip a second time.

Fix: an optional client-generated `client_request_id` on the request, echoed
onto the created TestRun, with a unique (assigned_test_id, client_request_id)
index -- a replay with the same id short-circuits to the already-recorded
result instead of creating anything new.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import AssignedTest, CableProfile, Sample, Standard, TestDefinition, TestRun, User
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
    assistant = User(username="asst_idem", full_name="Assistant Idem", role="SCIENTIFIC_ASSISTANT",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(assistant)
    db.flush()

    standard = Standard(standard_id="STD-IDEM", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    # A single mandatory test on this sample -- submitting it is the LAST
    # outstanding test, so a normal (non-replayed) submission flips
    # sample.status to SCIENTIST_REVIEW. This is deliberate: it's what makes
    # test_replaying_does_not_re_flip_sample_status_a_second_time meaningful.
    sample = Sample(sample_id="SMP-IDEM-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=assistant.id, assigned_assistant_id=assistant.id)
    db.add(sample)
    db.flush()

    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                            confirmed=True, tested_core_colors=["RED"])
    db.add(profile)
    db.flush()

    # Heat Shock Test: a qualitative pass/fail test (cracks_observed), kept
    # deliberately decoupled from any specific numeric calculator.
    db.add(TestDefinition(test_id="TEST-0019", name="Heat Shock Test", unit="pass"))
    db.flush()
    at = AssignedTest(sample_id=sample.sample_id, test_id="TEST-0019", mandatory=True,
                       enabled=True, status="PENDING", core_position=None)
    db.add(at)
    db.commit()
    at_id = at.id
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-IDEM-0001"
        c.assigned_test_id = at_id
        c.session_factory = TestSessionLocal
        yield c

    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "asst_idem", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _submit(client, token, client_request_id=None, cracked=False):
    body = {"raw_values": {"cracks_observed": cracked}}
    if client_request_id is not None:
        body["client_request_id"] = client_request_id
    return client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def _run_count(client):
    db = client.session_factory()
    try:
        return db.query(TestRun).filter(TestRun.assigned_test_id == client.assigned_test_id).count()
    finally:
        db.close()


def _get_sample_status(client):
    db = client.session_factory()
    try:
        return db.query(Sample).filter(Sample.sample_id == client.sample_id).first().status
    finally:
        db.close()


def _set_sample_status(client, status):
    db = client.session_factory()
    try:
        sample = db.query(Sample).filter(Sample.sample_id == client.sample_id).first()
        sample.status = status
        db.commit()
    finally:
        db.close()


def test_replaying_identical_submission_does_not_create_a_second_test_run(client):
    token = _token(client)
    key = str(uuid.uuid4())

    first = _submit(client, token, client_request_id=key, cracked=False)
    assert first.status_code == 200
    assert _run_count(client) == 1

    second = _submit(client, token, client_request_id=key, cracked=False)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert _run_count(client) == 1


def test_replaying_does_not_re_flip_sample_status_a_second_time(client):
    token = _token(client)
    key = str(uuid.uuid4())

    # This is the only assigned test -- submitting it flips the sample to
    # SCIENTIST_REVIEW.
    resp = _submit(client, token, client_request_id=key, cracked=False)
    assert resp.status_code == 200
    assert _get_sample_status(client) == "SCIENTIST_REVIEW"

    # Simulate the Scientist having since acted on it (or simply prove the
    # replay path never touches sample.status at all, regardless of why it
    # might differ from what it was at original-submission time).
    _set_sample_status(client, "TESTING")

    replay = _submit(client, token, client_request_id=key, cracked=False)
    assert replay.status_code == 200
    assert replay.json() == resp.json()
    # The replay must not re-flip status -- it never reaches that logic at all.
    assert _get_sample_status(client) == "TESTING"


def test_two_different_client_request_ids_still_create_two_attempts(client):
    token = _token(client)

    first = _submit(client, token, client_request_id=str(uuid.uuid4()), cracked=False)
    assert first.status_code == 200
    assert _run_count(client) == 1

    # A genuinely distinct submission (different id) is a real second
    # attempt, not a replay -- must not be suppressed by the dedupe check.
    second = _submit(client, token, client_request_id=str(uuid.uuid4()), cracked=True)
    assert second.status_code == 200
    assert _run_count(client) == 2


def test_missing_client_request_id_still_works_unchanged(client):
    # Backward-compat: the desktop Scientist path (and any older client)
    # never sends this field at all -- must behave exactly as before H16/P3a.
    token = _token(client)
    resp = _submit(client, token, client_request_id=None, cracked=False)
    assert resp.status_code == 200
    assert resp.json()["result"] == "PASS"
    assert _run_count(client) == 1
