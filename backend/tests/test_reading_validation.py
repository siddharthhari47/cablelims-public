"""
Regression tests for §5.4: `SubmitReadingRequest.raw_values` was a bare
`dict` -- any JSON object was accepted and handed straight to the
calculator. Each test here reproduces one of the specific failure modes the
review named and proves it's now a clean, immediate rejection instead of a
silent misdiagnosis, a wrong result, or an unhandled 500.
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
    assistant = User(username="asst_rv", full_name="Assistant RV", role="SCIENTIFIC_ASSISTANT",
                      password_hash=hash_password("password123"), is_active=True)
    db.add(assistant)
    db.flush()

    standard = Standard(standard_id="STD-RV", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-RV-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=assistant.id, assigned_assistant_id=assistant.id)
    db.add(sample)
    db.flush()

    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", conductor_class="2",
                            insulation_type="A", confirmed=True, tested_core_colors=["RED"])
    db.add(profile)
    db.flush()

    test_ids = {
        "TEST-0001": "Conductor Resistance",
        "TEST-0002": "Insulation Thickness",
        "TEST-0004": "Elongation at Break",
        "TEST-0009": "Halogen Acid Gas",
        "TEST-0012": "Tensile Test (Aluminium Conductor)",
        "TEST-0018": "Shrinkage Test",
        "TEST-0019": "Heat Shock Test",
    }
    assigned = {}
    for test_id, name in test_ids.items():
        db.add(TestDefinition(test_id=test_id, name=name, unit="x"))
        db.flush()
        at = AssignedTest(sample_id=sample.sample_id, test_id=test_id, mandatory=True,
                           enabled=True, status="PENDING", core_position=None)
        db.add(at)
        db.flush()
        assigned[test_id] = at.id
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-RV-0001"
        c.assigned = assigned
        yield c

    app.dependency_overrides.clear()


def _token(client):
    resp = client.post("/api/auth/login", json={"username": "asst_rv", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _submit(client, token, test_id, raw_values):
    return client.post(
        f"/api/samples/{client.sample_id}/tests/{client.assigned[test_id]}/submit",
        json={"raw_values": raw_values},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_typo_in_field_name_is_rejected_loudly_not_silently_missing(client):
    # Before: "specimen_length_mm" (extra "m") would be silently ignored by
    # raw.get("specimen_length_m"), producing a MISSING-limit UNDETERMINED
    # that looks exactly like a genuine Standards Knowledge Base gap.
    token = _token(client)
    resp = _submit(client, token, "TEST-0001", {
        "observed_resistance_mohm": 18.2,
        "specimen_length_mm": 5.0,  # typo: should be specimen_length_m
        "room_temperature_c": 27,
    })
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    fields_mentioned = {tuple(e["loc"]) for e in errors}
    assert ("specimen_length_m",) in fields_mentioned  # reported missing
    assert any("specimen_length_mm" in str(e) for e in errors)  # reported as unexpected


def test_negative_length_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0001", {
        "observed_resistance_mohm": 18.2,
        "specimen_length_m": -5.0,
        "room_temperature_c": 27,
    })
    assert resp.status_code == 422


def test_absurd_room_temperature_is_rejected_before_it_can_divide_by_zero(client):
    # get_temperature_correction_factor computes 250/(230+t) -- t=-230 is a
    # ZeroDivisionError with no guard in the calculator itself.
    token = _token(client)
    resp = _submit(client, token, "TEST-0001", {
        "observed_resistance_mohm": 18.2,
        "specimen_length_m": 5.0,
        "room_temperature_c": -230,
    })
    assert resp.status_code == 422


def test_string_false_on_a_qualitative_field_is_correctly_interpreted_not_truthy(client):
    # The exact bug: raw Python `bool("false")` is True. A specimen that
    # genuinely did NOT crack, reported as the string "false" (e.g. a phone
    # form library that stringifies), must still PASS, not silently FAIL.
    token = _token(client)
    resp = _submit(client, token, "TEST-0019", {"cracks_observed": "false"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "PASS"


def test_garbage_string_on_a_qualitative_field_is_rejected_not_silently_coerced(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0019", {"cracks_observed": "banana"})
    assert resp.status_code == 422


def test_malformed_list_value_is_a_clean_422_not_an_unhandled_500(client):
    # Before: [float(v) for v in readings] with no try/except -> unhandled
    # ValueError -> HTTP 500 with a stack trace.
    token = _token(client)
    resp = _submit(client, token, "TEST-0002", {"readings_mm": [0.82, 0.81, "abc", 0.80, 0.83]})
    assert resp.status_code == 422
    assert resp.status_code != 500


def test_wrong_list_length_is_rejected(client):
    # input_schema declares "count": 5 for this test.
    token = _token(client)
    resp = _submit(client, token, "TEST-0002", {"readings_mm": [0.82, 0.81, 0.85]})
    assert resp.status_code == 422


def test_elongation_final_shorter_than_initial_is_rejected(client):
    # A specimen physically stretches before breaking -- final <= initial is
    # not a real elongation-at-break reading (most likely a swapped pair of
    # fields), not something that should silently compute a negative %.
    token = _token(client)
    resp = _submit(client, token, "TEST-0004", {"initial_length_mm": 68, "final_length_mm": 25})
    assert resp.status_code == 422


def test_valid_elongation_reading_still_succeeds(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0004", {"initial_length_mm": 25, "final_length_mm": 68})
    assert resp.status_code == 200


def test_shrinkage_specimen_growing_is_rejected(client):
    # B11 (Review #2 remediation): length_after_mm > length_before_mm is a
    # swapped-field error (a specimen doesn't grow under this test), not a
    # real reading -- would otherwise sail through a "<=" limit as a
    # comfortable, wrong PASS via a negative shrinkage percentage.
    token = _token(client)
    resp = _submit(client, token, "TEST-0018", {"length_before_mm": 50, "length_after_mm": 52})
    assert resp.status_code == 422


def test_valid_shrinkage_reading_still_succeeds(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0018", {"length_before_mm": 50, "length_after_mm": 48})
    assert resp.status_code == 200


def test_halogen_acid_gas_a_exceeding_b_is_rejected(client):
    # B11 (Review #2 remediation): calc_halogen_acid_gas computes HCl%
    # proportional to (B - A) -- titration_a_ml > titration_b_ml yields a
    # negative HCl%, an impossible physical result.
    token = _token(client)
    resp = _submit(client, token, "TEST-0009", {
        "sample_weight_g": 1.0, "titration_b_ml": 10.0, "titration_a_ml": 12.0, "titration_factor": 1.0,
    })
    assert resp.status_code == 422


def test_valid_halogen_acid_gas_reading_still_succeeds(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0009", {
        "sample_weight_g": 1.0, "titration_b_ml": 12.0, "titration_a_ml": 10.0, "titration_factor": 1.0,
    })
    assert resp.status_code == 200


def test_unlisted_aluminium_grade_is_rejected(client):
    token = _token(client)
    resp = _submit(client, token, "TEST-0012", {
        "aluminium_grade": "Grade Z",  # not one of the 3 real grades
        "after_stranding": False,
        "wire_diameter_mm": 2.0,
        "breaking_load_n": 100,
    })
    assert resp.status_code == 422


def test_valid_reading_still_succeeds_end_to_end(client):
    # Regression guard: a completely normal, in-bounds submission must still
    # work exactly as before.
    token = _token(client)
    resp = _submit(client, token, "TEST-0001", {
        "observed_resistance_mohm": 18.2,
        "specimen_length_m": 5.0,
        "room_temperature_c": 27,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["calculated_value"] is not None
