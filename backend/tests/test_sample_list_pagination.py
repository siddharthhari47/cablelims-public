"""
Regression tests for B7 (Review #2 remediation): GET /api/samples now
supports limit/offset pagination, matching GET /api/admin/audit's existing
{total, ...}-shaped convention, rather than always returning every sample
unbounded.
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
    scientist = User(username="sci_page", full_name="Page Scientist", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-PAGE", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()
    for i in range(15):
        db.add(Sample(sample_id=f"SMP-PAGE-{i:04d}", product_family="CABLE", standard_id=standard.standard_id,
                       cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING", registered_by_id=scientist.id))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "sci_page", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_response_is_wrapped_with_total_and_defaults_to_a_generous_limit(client):
    token = _token(client)
    resp = client.get("/api/samples", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 15
    assert len(body["samples"]) == 15  # default limit (200) comfortably covers this


def test_limit_and_offset_slice_correctly(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    first_page = client.get("/api/samples?limit=5&offset=0", headers=headers).json()
    second_page = client.get("/api/samples?limit=5&offset=5", headers=headers).json()

    assert first_page["total"] == 15
    assert second_page["total"] == 15
    assert len(first_page["samples"]) == 5
    assert len(second_page["samples"]) == 5
    first_ids = {s["sample_id"] for s in first_page["samples"]}
    second_ids = {s["sample_id"] for s in second_page["samples"]}
    assert first_ids.isdisjoint(second_ids)  # no overlap between pages


def test_limit_is_clamped_to_500(client):
    token = _token(client)
    resp = client.get("/api/samples?limit=10000", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # 15 real samples exist -- this just proves an oversized limit doesn't
    # error or otherwise misbehave, matching the audit endpoint's own clamp.
    assert resp.json()["total"] == 15


def test_limit_is_clamped_to_at_least_1(client):
    token = _token(client)
    resp = client.get("/api/samples?limit=0", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()["samples"]) == 1
