"""
Regression tests for §7.2: re-profiling a sample only ever ADDED
AssignedTest rows for the newly-applicable test set -- a test that stopped
applying (e.g. correcting fire_category from FR-LSH back to 01) stayed
assigned, mandatory, and PENDING forever, permanently blocking the sample
from reaching SCIENTIST_REVIEW and forcing readings to be recorded for a
test the standard no longer requires for this construction.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import (
    Sample,
    Standard,
    TestAssignmentRule,
    TestDefinition,
    User,
)
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
    scientist = User(username="sci_rp", full_name="Scientist RP", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(scientist)
    db.flush()

    standard = Standard(standard_id="STD-RP", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    # Real test_ids with real registered calculators/reading schemas (see
    # engines/calculation_engine.CALCULATORS and engines/reading_schemas.py)
    # so submissions in these tests exercise the real validation/calculation
    # path rather than being rejected for an unregistered made-up test_id.
    # TEST-0019 (Heat Shock) applies to every profile; TEST-0008 (Oxygen
    # Index) and TEST-0010 (Temperature Index) only apply when fire_category
    # is FR-LSH -- mirrors seed.py's real rules exactly (condition=
    # "fire_category in (FR-LSH)").
    always_def = TestDefinition(test_id="TEST-0019", name="Heat Shock Test", unit="pass/fail", scope="ONCE")
    fire_def = TestDefinition(test_id="TEST-0008", name="Oxygen Index", unit="%", scope="ONCE")
    fire2_def = TestDefinition(test_id="TEST-0010", name="Temperature Index", unit="deg C", scope="ONCE")
    db.add_all([always_def, fire_def, fire2_def])
    db.flush()

    db.add_all([
        TestAssignmentRule(rule_id="R-ALWAYS", standard_id=standard.standard_id, test_id="TEST-0019",
                            condition="always", mandatory=True, priority=1),
        TestAssignmentRule(rule_id="R-FIRE", standard_id=standard.standard_id, test_id="TEST-0008",
                            condition="fire_category in (FR-LSH)", mandatory=True, priority=2),
        TestAssignmentRule(rule_id="R-FIRE2", standard_id=standard.standard_id, test_id="TEST-0010",
                            condition="fire_category in (FR-LSH)", mandatory=True, priority=3),
    ])
    db.flush()

    sample = Sample(sample_id="SMP-RP-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="PROFILE_PENDING",
                     registered_by_id=scientist.id, assigned_assistant_id=scientist.id)
    db.add(sample)
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-RP-0001"
        yield c

    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "sci_rp", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _profile(client, token, fire_category):
    return client.post(
        f"/api/samples/{client.sample_id}/profile",
        json={
            "conductor_material": "Copper", "insulation_type": "A", "fire_category": fire_category,
            "tested_core_colors": ["RED"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def _assigned_test_ids(client, token):
    detail = client.get(f"/api/samples/{client.sample_id}", headers={"Authorization": f"Bearer {token}"}).json()
    return {t["test_id"]: t for t in detail["tests"]}


def test_correcting_fire_category_retracts_tests_with_no_data(client):
    token = _token(client)

    resp = _profile(client, token, "FR-LSH")
    assert resp.status_code == 200
    assert resp.json()["assigned_tests"] == 3  # Heat Shock + Oxygen Index + Temperature Index

    tests = _assigned_test_ids(client, token)
    assert set(tests.keys()) == {"TEST-0019", "TEST-0008", "TEST-0010"}

    # Correct the profile: this is NOT actually a fire-rated cable.
    resp = _profile(client, token, "01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retracted_tests"] == 2
    assert body["retracted_with_existing_readings"] == []  # no data existed -> deleted, not disabled

    tests = _assigned_test_ids(client, token)
    assert set(tests.keys()) == {"TEST-0019"}  # the two fire-only tests are gone entirely


def test_a_test_with_existing_readings_is_disabled_not_deleted(client):
    token = _token(client)

    resp = _profile(client, token, "FR-LSH")
    assert resp.status_code == 200
    tests = _assigned_test_ids(client, token)
    fire_test_id = tests["TEST-0008"]["assigned_test_id"]  # Oxygen Index

    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{fire_test_id}/submit",
        json={"raw_values": {"oxygen_index_pct": 29.3}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    resp = _profile(client, token, "01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retracted_with_existing_readings"] == ["TEST-0008"]

    # Retracted via disable, not deletion -- the historical reading and the
    # row itself survive.
    tests_after = _assigned_test_ids(client, token)
    assert "TEST-0008" in tests_after
    assert tests_after["TEST-0008"]["enabled"] is False
    assert tests_after["TEST-0008"]["attempts"] == 1
    assert tests_after["TEST-0008"]["latest_result"]["calculated_value"] == 29.3


def test_sample_can_still_reach_scientist_review_after_retraction(client):
    # This is the actual production bug: before the fix, a retracted-but-
    # still-enabled mandatory PENDING test permanently blocked
    # summarize_sample's completion gate, so the sample could never leave
    # TESTING no matter how many of the currently-applicable tests were
    # completed.
    token = _token(client)
    _profile(client, token, "FR-LSH")
    _profile(client, token, "01")  # retract the two fire-only tests

    tests = _assigned_test_ids(client, token)
    assert set(tests.keys()) == {"TEST-0019"}
    heat_shock_id = tests["TEST-0019"]["assigned_test_id"]

    resp = client.post(
        f"/api/samples/{client.sample_id}/tests/{heat_shock_id}/submit",
        json={"raw_values": {"cracks_observed": False}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    detail = client.get(f"/api/samples/{client.sample_id}", headers={"Authorization": f"Bearer {token}"}).json()
    assert detail["status"] in ("SCIENTIST_REVIEW", "APPROVED"), (
        f"sample stuck at {detail['status']} -- a retracted test is still blocking completion"
    )
