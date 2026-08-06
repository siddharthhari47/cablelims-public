"""
Regression tests for flat-cable dimension capture (added after Review #2
remediation): IS 694:2010 cl.22, Table 10 reports a flat cable's overall
dimensions as Width x Height, not a single diameter -- overall_diameter_mm/
diameter_under_sheath_mm (Round-only) can't represent a flat cross-section.
CableProfile.flat_width_mm/flat_height_mm are separate fields, not a
relabelling of the Round-only ones, and both pairs round-trip independently
through submit_profile -> get_sample_detail.
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
    scientist = User(username="sci_flat", full_name="Flat Scientist", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-FLAT", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id="SMP-FLAT-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=3, cores_tested=3, csa_mm2=2.5, status="TESTING", registered_by_id=scientist.id)
    db.add(sample)
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-FLAT-0001"
        yield c
    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "sci_flat", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _base_profile(**overrides):
    body = {
        "conductor_material": "Copper", "conductor_class": "2", "insulation_type": "A",
        "fire_category": "01", "sheath_type": "ST1",
        "tested_core_colors": ["RED", "YELLOW", "BLUE"],
    }
    body.update(overrides)
    return body


def test_flat_width_and_height_round_trip(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        f"/api/samples/{client.sample_id}/profile",
        json=_base_profile(cable_shape="Flat", flat_width_mm=13.0, flat_height_mm=6.2),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/api/samples/{client.sample_id}", headers=headers).json()
    profile = detail["profile"]
    assert profile["cable_shape"] == "Flat"
    assert profile["flat_width_mm"] == 13.0
    assert profile["flat_height_mm"] == 6.2
    # Round-only fields must not be silently populated for a Flat profile.
    assert profile["overall_diameter_mm"] is None
    assert profile["diameter_under_sheath_mm"] is None


def test_round_od_id_round_trip_and_flat_fields_stay_null(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        f"/api/samples/{client.sample_id}/profile",
        json=_base_profile(cable_shape="Round", overall_diameter_mm=11.5, diameter_under_sheath_mm=9.0),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/api/samples/{client.sample_id}", headers=headers).json()
    profile = detail["profile"]
    assert profile["cable_shape"] == "Round"
    assert profile["overall_diameter_mm"] == 11.5
    assert profile["diameter_under_sheath_mm"] == 9.0
    assert profile["flat_width_mm"] is None
    assert profile["flat_height_mm"] is None
