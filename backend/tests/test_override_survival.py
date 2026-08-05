"""
Regression test for §7.3/§A3: a Scientist's override on a test result was
silently destroyed the moment a new attempt was submitted, because nothing
ever read `AssignedTest.accepted_attempt_id` (written in two places, read in
none) -- every consumer independently re-derived "the current reading" via
MAX(attempt_number), which a fresh submission always wins.

Sequence this test proves is now handled correctly:
  1. Assistant submits attempt 1 -> some system result.
  2. Scientist overrides it to PASS, with a documented reason.
  3. A further submission against the SAME test is now blocked (400) rather
     than silently superseding the override.
  4. A Scientist explicitly requesting a repeat clears the block.
  5. The new attempt after a repeat correctly becomes the accepted one.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
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
    scientist = User(username="sci_ov", full_name="Scientist Override", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    assistant = User(username="asst_ov", full_name="Assistant Override", role="SCIENTIFIC_ASSISTANT",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([scientist, assistant])
    db.flush()

    standard = Standard(standard_id="STD-OV", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-OV-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=scientist.id, assigned_assistant_id=assistant.id)
    db.add(sample)
    db.flush()

    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                            confirmed=True, tested_core_colors=["RED"])
    db.add(profile)
    db.flush()

    # A qualitative test (Heat Shock: cracks_observed) keeps this test
    # decoupled from any single numeric formula -- what matters here is the
    # override/accepted-attempt plumbing, not a specific calculator.
    test_def = TestDefinition(test_id="TEST-0019", name="Heat Shock", unit="pass")
    db.add(test_def)
    db.flush()

    at = AssignedTest(sample_id=sample.sample_id, test_id=test_def.test_id, mandatory=True,
                       enabled=True, status="PENDING", core_position=None)
    db.add(at)
    db.commit()
    at_id = at.id
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-OV-0001"
        c.assigned_test_id = at_id
        yield c

    app.dependency_overrides.clear()


def _token(client, username, password="password123"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _submit(client, token, cracked=False):
    return client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/submit",
        json={"raw_values": {"cracks_observed": cracked}},
        headers=_auth(token),
    )


def test_override_survives_until_a_repeat_is_explicitly_requested(client):
    sci_token = _token(client, "sci_ov")
    asst_token = _token(client, "asst_ov")

    # 1. Assistant submits attempt 1 -- cracked, so the system says FAIL.
    resp = _submit(client, asst_token, cracked=True)
    assert resp.status_code == 200
    assert resp.json()["result"] == "FAIL"

    # 2. Scientist overrides to PASS with a documented reason (e.g. the
    # cracking was cosmetic/unrelated per their own judgement).
    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/override",
        json={"result": "PASS", "reason": "Crack was cosmetic, confirmed under magnification -- does not fail cl.8.5"},
        headers=_auth(sci_token),
    )
    assert resp.status_code == 200

    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(sci_token)).json()
    test_row = next(t for t in detail["tests"] if t["assigned_test_id"] == client.assigned_test_id)
    assert test_row["latest_result"]["effective_result"] == "PASS"
    assert test_row["latest_result"]["overridden"] is True

    # 3. A plain resubmission must NOT be allowed to silently erase that
    # override -- this is the exact bug: before the fix, this would have
    # succeeded, created attempt 2, and the override would vanish from every
    # view without any warning.
    resp = _submit(client, asst_token, cracked=True)
    assert resp.status_code == 400
    assert "overridden" in resp.json()["detail"].lower()

    # The override must still be intact after the blocked attempt.
    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(sci_token)).json()
    test_row = next(t for t in detail["tests"] if t["assigned_test_id"] == client.assigned_test_id)
    assert test_row["latest_result"]["effective_result"] == "PASS"
    assert test_row["latest_result"]["overridden"] is True

    # 4. A Scientist explicitly requesting a repeat is the deliberate signal
    # that supersedes the override.
    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/repeat",
        headers=_auth(sci_token),
    )
    assert resp.status_code == 200

    # 5. Now a new submission is allowed and correctly becomes the accepted,
    # un-overridden result.
    resp = _submit(client, asst_token, cracked=False)
    assert resp.status_code == 200
    assert resp.json()["result"] == "PASS"

    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(sci_token)).json()
    test_row = next(t for t in detail["tests"] if t["assigned_test_id"] == client.assigned_test_id)
    assert test_row["latest_result"]["overridden"] is False
    assert test_row["latest_result"]["attempt_number"] == 2


def test_resubmission_is_allowed_when_prior_attempt_was_only_verified_not_overridden(client):
    # Verify is a lighter-weight QA confirmation, not a decision override --
    # it must not block a legitimate resubmission the way an override does.
    sci_token = _token(client, "sci_ov")
    asst_token = _token(client, "asst_ov")

    resp = _submit(client, asst_token, cracked=False)
    assert resp.status_code == 200

    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned_test_id}/verify",
        headers=_auth(sci_token),
    )
    assert resp.status_code == 200

    resp = _submit(client, asst_token, cracked=False)
    assert resp.status_code == 200
