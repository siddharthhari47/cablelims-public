"""
Regression tests for H16: a Scientist's RETURN comment was captured by
ReviewRequest.comment but only ever reached an Administrator-only audit log
entry -- there was no durable field on Sample, no API exposure, and no
frontend surface, so the Scientific Assistant a sample was returned to had
no way to learn why (just a status flip indistinguishable from ordinary
in-progress testing).

Covers: RETURN now requires a non-empty comment (mirrors override_reading's
existing mandatory `reason`), the comment persists to Sample.last_review_comment
and is exposed via both the sample-detail and sample-list endpoints, and a
later APPROVE clears it once the review cycle is resolved.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import Sample, Standard, User
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
    scientist = User(username="sci_rc", full_name="Scientist Review", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    assistant = User(username="asst_rc", full_name="Assistant Review", role="SCIENTIFIC_ASSISTANT",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([scientist, assistant])
    db.flush()

    standard = Standard(standard_id="STD-RC", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-RC-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="SCIENTIST_REVIEW",
                     registered_by_id=scientist.id, assigned_assistant_id=assistant.id)
    db.add(sample)
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-RC-0001"
        c.session_factory = TestSessionLocal
        yield c

    app.dependency_overrides.clear()


def _token(client, username, password="password123"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _set_status(client, status):
    """Test-only: directly puts the sample back into SCIENTIST_REVIEW,
    simulating the Assistant having resubmitted all readings -- the actual
    submit_reading auto-transition is exercised by other tests; this one is
    about review_sample's own comment handling, not that transition."""
    db = client.session_factory()
    sample = db.query(Sample).filter(Sample.sample_id == client.sample_id).first()
    sample.status = status
    db.commit()
    db.close()


def test_return_without_a_comment_is_rejected(client):
    token = _token(client, "sci_rc")
    resp = client.post(f"/api/samples/{client.sample_id}/review", json={"action": "RETURN"}, headers=_auth(token))
    assert resp.status_code == 400
    assert "comment" in resp.json()["detail"].lower()


def test_return_with_only_whitespace_is_rejected(client):
    token = _token(client, "sci_rc")
    resp = client.post(
        f"/api/samples/{client.sample_id}/review",
        json={"action": "RETURN", "comment": "   "},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_return_comment_persists_and_is_visible_to_the_assistant(client):
    sci_token = _token(client, "sci_rc")
    asst_token = _token(client, "asst_rc")

    resp = client.post(
        f"/api/samples/{client.sample_id}/review",
        json={"action": "RETURN", "comment": "  Insulation thickness reading looks like a typo -- please re-measure.  "},
        headers=_auth(sci_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "TESTING"

    # Leading/trailing whitespace stripped, same as override_reading's `reason`.
    expected = "Insulation thickness reading looks like a typo -- please re-measure."

    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(asst_token)).json()
    assert detail["status"] == "TESTING"
    assert detail["last_review_comment"] == expected

    listing = client.get("/api/samples", headers=_auth(asst_token)).json()
    row = next(s for s in listing if s["sample_id"] == client.sample_id)
    assert row["last_review_comment"] == expected


def test_approve_clears_the_prior_return_comment(client):
    sci_token = _token(client, "sci_rc")

    client.post(
        f"/api/samples/{client.sample_id}/review",
        json={"action": "RETURN", "comment": "Please redo the conductor resistance reading."},
        headers=_auth(sci_token),
    )
    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(sci_token)).json()
    assert detail["last_review_comment"]

    # Simulates the Assistant having addressed it and resubmitted all readings.
    _set_status(client, "SCIENTIST_REVIEW")

    resp = client.post(f"/api/samples/{client.sample_id}/review", json={"action": "APPROVE"}, headers=_auth(sci_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    detail = client.get(f"/api/samples/{client.sample_id}", headers=_auth(sci_token)).json()
    assert detail["last_review_comment"] is None
