"""
Consolidated security regression suite (review §12.1 Tier 2) covering the
two structural guarantees `deps.get_authorized_sample()` is supposed to
provide across EVERY sample-scoped route, tested systematically here rather
than relying on "it uses the same shared dependency other routes already
proved works":

  1. A locked (APPROVED/REPORT_GENERATED/ARCHIVED) sample rejects every
     mutating route that doesn't explicitly opt out with allow_locked=True.
  2. A SCIENTIFIC_ASSISTANT can only reach a sample assigned to them, on
     every route reachable by that role.

Path traversal (SEC-1) has its own dedicated suite in
test_path_traversal.py; upload content-type/size/re-encoding validation
(SEC-6) has its own in test_image_upload_hardening.py. Every other named
C-item (override survival, reprofile retraction, reading validation,
download ownership, login throttling, calculation golden values) already
shipped its own focused regression test alongside its fix -- this file's
job is specifically the two guarantees above, systematically, in one place.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import (
    AssignedTest,
    CableProfile,
    Sample,
    Standard,
    TestDefinition,
    User,
)
from app.services.auth_service import hash_password


def _fake_jpeg_bytes() -> bytes:
    # A real, minimal, decodable JPEG -- since C17, the upload endpoints
    # re-encode and reject anything that isn't a genuine image, so a
    # placeholder byte string like b"data" would (correctly) be rejected as
    # invalid regardless of the authorization/lock check this file is
    # actually testing.
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def rig(tmp_path):
    """A fully-wired sample with one PENDING mandatory test (TEST-0019 Heat
    Shock -- a real, schema-registered, calculator-backed test) and one
    optional test (for the toggle route), plus an owner assistant, an
    unrelated assistant, and a scientist."""
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
    owner = User(username="owner_sec", full_name="Owner", role="SCIENTIFIC_ASSISTANT",
                 password_hash=hash_password("password123"), is_active=True)
    other = User(username="other_sec", full_name="Other", role="SCIENTIFIC_ASSISTANT",
                 password_hash=hash_password("password123"), is_active=True)
    scientist = User(username="sci_sec", full_name="Scientist", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([owner, other, scientist])
    db.flush()

    standard = Standard(standard_id="STD-SEC", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-SEC-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=scientist.id, assigned_assistant_id=owner.id)
    db.add(sample)
    db.flush()

    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                            confirmed=True, tested_core_colors=["RED"])
    db.add(profile)

    db.add(TestDefinition(test_id="TEST-0019", name="Heat Shock Test", unit="pass/fail", scope="ONCE"))
    db.flush()
    mandatory_test = AssignedTest(sample_id=sample.sample_id, test_id="TEST-0019", mandatory=True,
                                   enabled=True, status="PENDING", core_position=None)
    optional_test = AssignedTest(sample_id=sample.sample_id, test_id="TEST-0019", mandatory=False,
                                  enabled=True, status="PENDING", core_position="RED")
    db.add_all([mandatory_test, optional_test])
    db.commit()
    mandatory_id, optional_id = mandatory_test.id, optional_test.id
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-SEC-0001"
        c.mandatory_test_id = mandatory_id
        c.optional_test_id = optional_id
        c.session_factory = TestSessionLocal
        yield c

    app.dependency_overrides.clear()


def _token(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _lock_sample(client):
    db = client.session_factory()
    sample = db.query(Sample).filter(Sample.sample_id == client.sample_id).first()
    sample.status = "ARCHIVED"
    db.commit()
    db.close()


def _profile_body():
    return {
        "conductor_material": "Copper", "insulation_type": "A", "fire_category": "01",
        "tested_core_colors": ["RED"],
    }


# -- 1. Locked sample rejects every mutating route --------------------------

def test_locked_sample_rejects_profile_resubmission(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/profile", json=_profile_body(), headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_marking_image_upload(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/marking-image",
                     files={"file": ("m.jpg", io.BytesIO(_fake_jpeg_bytes()), "image/jpeg")}, headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_diagram_image_upload(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/diagram-image",
                     files={"file": ("d.jpg", io.BytesIO(_fake_jpeg_bytes()), "image/jpeg")}, headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_toggle(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.optional_test_id}/toggle?enabled=false",
                     headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_reading_submission(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/submit",
                     json={"raw_values": {"cracks_observed": False}}, headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_override(rig):
    token = _token(rig, "sci_sec")
    rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/submit",
              json={"raw_values": {"cracks_observed": True}}, headers=_auth(token))
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/override",
                     json={"result": "PASS", "reason": "Reviewed and cosmetic only, not a real crack"},
                     headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_verify(rig):
    token = _token(rig, "sci_sec")
    rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/submit",
              json={"raw_values": {"cracks_observed": False}}, headers=_auth(token))
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/verify", headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_repeat_request(rig):
    # The specific historical bug: request_repeat previously had NO lock
    # check at all and would reopen an already-certified sample.
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/tests/{rig.mandatory_test_id}/repeat", headers=_auth(token))
    assert resp.status_code == 400


def test_locked_sample_rejects_review(rig):
    token = _token(rig, "sci_sec")
    _lock_sample(rig)
    resp = rig.post(f"/api/samples/{rig.sample_id}/review", json={"action": "APPROVE"}, headers=_auth(token))
    assert resp.status_code == 400


# -- 2. Unassigned assistant is blocked on every assistant-reachable route --

def test_unassigned_assistant_cannot_submit_a_profile(rig):
    token = _token(rig, "other_sec")
    resp = rig.post(f"/api/samples/{rig.sample_id}/profile", json=_profile_body(), headers=_auth(token))
    assert resp.status_code == 404


def test_unassigned_assistant_cannot_upload_a_marking_image(rig):
    token = _token(rig, "other_sec")
    resp = rig.post(f"/api/samples/{rig.sample_id}/marking-image",
                     files={"file": ("m.jpg", io.BytesIO(_fake_jpeg_bytes()), "image/jpeg")}, headers=_auth(token))
    assert resp.status_code == 404


def test_unassigned_assistant_cannot_upload_a_diagram_image(rig):
    token = _token(rig, "other_sec")
    resp = rig.post(f"/api/samples/{rig.sample_id}/diagram-image",
                     files={"file": ("d.jpg", io.BytesIO(_fake_jpeg_bytes()), "image/jpeg")}, headers=_auth(token))
    assert resp.status_code == 404


def test_unassigned_assistant_cannot_download_the_observation_sheet(rig):
    # Confirm the profile first (SCIENTIST does it, out of band) so the
    # 400 "profile not confirmed" precondition doesn't mask the 404 under
    # test.
    sci_token = _token(rig, "sci_sec")
    rig.post(f"/api/samples/{rig.sample_id}/profile", json=_profile_body(), headers=_auth(sci_token))

    other_token = _token(rig, "other_sec")
    resp = rig.get(f"/api/samples/{rig.sample_id}/observation-sheet", headers=_auth(other_token))
    assert resp.status_code == 404


def test_assigned_assistant_is_not_blocked_by_any_of_the_above(rig):
    # Regression guard: the owner assistant must still be able to do all of
    # this normally.
    token = _token(rig, "owner_sec")
    resp = rig.post(f"/api/samples/{rig.sample_id}/profile", json=_profile_body(), headers=_auth(token))
    assert resp.status_code == 200
    resp = rig.post(f"/api/samples/{rig.sample_id}/marking-image",
                     files={"file": ("m.jpg", io.BytesIO(_fake_jpeg_bytes()), "image/jpeg")}, headers=_auth(token))
    assert resp.status_code == 200
