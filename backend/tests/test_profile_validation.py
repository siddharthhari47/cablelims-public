"""
Regression tests for B8 (Review #2 remediation): six ProfileRequest fields
-- conductor_material, conductor_class, insulation_type, sheath_type,
fire_category, cable_shape -- used to be bare `str`, so a typo or wrong
casing reached the Standards Knowledge Base lookups unnoticed. Literal[...]
closes all six at the API boundary (422 instead of silently reaching
standards_service).

conductor_material is the one genuinely dangerous case, not just a missing-
limit one: standards_service.get_conductor_resistance_limit does
`"copper_plain" if material == "Copper" else "aluminium"` -- before this
fix, "copper" (lowercase) would silently be treated as ALUMINIUM and graded
against the wrong IS 8130 resistance table instead of failing safe to
MISSING/UNDETERMINED.
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
    scientist = User(username="sci_pv", full_name="Profile Scientist", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-PV", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id="SMP-PV-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=3, cores_tested=3, csa_mm2=2.5, status="TESTING", registered_by_id=scientist.id)
    db.add(sample)
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-PV-0001"
        yield c
    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "sci_pv", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _valid_profile(**overrides):
    body = {
        "conductor_material": "Copper", "conductor_class": "2", "insulation_type": "A",
        "fire_category": "01", "sheath_type": "ST1", "cable_shape": "Round",
        "tested_core_colors": ["RED", "YELLOW", "BLUE"],
    }
    body.update(overrides)
    return body


def _submit(client, token, **overrides):
    return client.post(
        f"/api/samples/{client.sample_id}/profile",
        json=_valid_profile(**overrides),
        headers={"Authorization": f"Bearer {token}"},
    )


def test_valid_profile_still_succeeds(client):
    token = _token(client)
    resp = _submit(client, token)
    assert resp.status_code == 200, resp.text


def test_lowercase_copper_is_rejected_not_silently_treated_as_aluminium(client):
    # The dangerous case: before this fix, "copper" would silently resolve
    # to the ALUMINIUM resistance table instead of being rejected.
    token = _token(client)
    resp = _submit(client, token, conductor_material="copper")
    assert resp.status_code == 422


def test_unknown_conductor_material_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, conductor_material="Bronze")
    assert resp.status_code == 422


def test_unknown_insulation_type_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, insulation_type="PVC Type A")  # a real ambiguity from review #1
    assert resp.status_code == 422


def test_unknown_sheath_type_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, sheath_type="ST4")
    assert resp.status_code == 422


def test_unknown_fire_category_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, fire_category="03")
    assert resp.status_code == 422


def test_unknown_conductor_class_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, conductor_class="3")  # not an IS 8130 table
    assert resp.status_code == 422


def test_unknown_cable_shape_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, cable_shape="Oval")
    assert resp.status_code == 422


def test_null_sheath_type_and_conductor_class_still_accepted(client):
    # Both are genuinely Optional (a sheathless/unsheathed cable, or a
    # profile where the class isn't known yet) -- must not be forced into
    # one of the four allowed strings.
    token = _token(client)
    resp = _submit(client, token, sheath_type=None, conductor_class=None)
    assert resp.status_code == 200, resp.text
