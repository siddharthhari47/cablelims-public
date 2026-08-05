"""
Regression tests for SEC-7: certificate and diagram-image downloads
required authentication but not authorization -- any authenticated user of
any role could download any certificate (certificate numbers are strictly
sequential, so every one ever issued is reachable just by counting) or any
sample's hand-drawn diagram (previously keyed by an opaque filename with no
ownership check at all).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import CableProfile, Certificate, Sample, Standard, User
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
    owner = User(username="asst_owner_dl", full_name="Owner Assistant", role="SCIENTIFIC_ASSISTANT",
                 password_hash=hash_password("password123"), is_active=True)
    other = User(username="asst_other_dl", full_name="Other Assistant", role="SCIENTIFIC_ASSISTANT",
                 password_hash=hash_password("password123"), is_active=True)
    scientist = User(username="sci_dl", full_name="Scientist DL", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([owner, other, scientist])
    db.flush()

    standard = Standard(standard_id="STD-DL", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-DL-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="ARCHIVED",
                     registered_by_id=scientist.id, assigned_assistant_id=owner.id)
    db.add(sample)
    db.flush()

    # A real, readable file on disk so FileResponse doesn't itself 404 for
    # an unrelated reason -- what's under test is the ownership check, not
    # file existence.
    diagram_path = tmp_path / "diagram.jpg"
    diagram_path.write_bytes(b"fake-jpeg-bytes")
    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                            confirmed=True, tested_core_colors=["RED"], hand_drawn_diagram_path=str(diagram_path))
    db.add(profile)

    cert_path = tmp_path / "certificate.docx"
    cert_path.write_bytes(b"fake-docx-bytes")
    cert = Certificate(certificate_no="CTL/CBL/2026/0001", sample_id=sample.sample_id,
                        generated_by_id=scientist.id, overall_decision="PASS", file_path=str(cert_path))
    db.add(cert)
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-DL-0001"
        yield c

    app.dependency_overrides.clear()


def _token(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# -- Certificate download ------------------------------------------------

def test_unassigned_assistant_cannot_download_another_samples_certificate(client):
    token = _token(client, "asst_other_dl")
    resp = client.get("/api/certificates/CTL%2FCBL%2F2026%2F0001/download", headers=_auth(token))
    assert resp.status_code == 404


def test_assigned_assistant_can_download_their_own_samples_certificate(client):
    token = _token(client, "asst_owner_dl")
    resp = client.get("/api/certificates/CTL%2FCBL%2F2026%2F0001/download", headers=_auth(token))
    assert resp.status_code == 200


def test_scientist_is_not_restricted_downloading_any_certificate(client):
    token = _token(client, "sci_dl")
    resp = client.get("/api/certificates/CTL%2FCBL%2F2026%2F0001/download", headers=_auth(token))
    assert resp.status_code == 200


def test_nonexistent_certificate_is_404_for_everyone(client):
    token = _token(client, "sci_dl")
    resp = client.get("/api/certificates/CTL%2FCBL%2F2026%2F9999/download", headers=_auth(token))
    assert resp.status_code == 404


# -- Diagram image download ------------------------------------------------

def test_unassigned_assistant_cannot_download_another_samples_diagram(client):
    token = _token(client, "asst_other_dl")
    resp = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers=_auth(token))
    assert resp.status_code == 404


def test_assigned_assistant_can_download_their_own_samples_diagram(client):
    token = _token(client, "asst_owner_dl")
    resp = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg-bytes"


def test_scientist_is_not_restricted_downloading_any_diagram(client):
    token = _token(client, "sci_dl")
    resp = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers=_auth(token))
    assert resp.status_code == 200


def test_diagram_download_works_on_an_archived_sample(client):
    # allow_locked=True -- viewing a historical diagram must still work
    # after the sample is locked/certified, same as the certificate itself.
    token = _token(client, "sci_dl")
    resp = client.get(f"/api/samples/{client.sample_id}/diagram-image", headers=_auth(token))
    assert resp.status_code == 200
