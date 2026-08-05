"""
Regression tests for §7.7: `models.now()` correctly returns a timezone-aware
UTC datetime, but the columns are plain `Column(DateTime)` and SQLite has no
native datetime type -- SQLAlchemy stores a naive string and hands back a
naive `datetime` on read, silently dropping the tzinfo. A bare
`dt.isoformat()` on that naive value produced a string with no offset (e.g.
"2026-08-02T14:00:00"), which a browser's `new Date(...)` parses as LOCAL
time -- in IST (UTC+5:30), every timestamp displayed 5h30m later than it
actually happened.

These tests hit real endpoints end-to-end (not just the iso_utc() helper in
isolation) and assert every timestamp string in the response ends in an
explicit UTC offset, per the review's own suggested check.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.models import CableProfile, Sample, Standard, User, iso_utc
from app.services.auth_service import hash_password


def _has_utc_offset(s: str) -> bool:
    return s.endswith("Z") or s.endswith("+00:00")


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
    admin = User(username="admin_tz", full_name="Admin TZ", role="ADMINISTRATOR",
                 password_hash=hash_password("password123"), is_active=True)
    scientist = User(username="sci_tz", full_name="Scientist TZ", role="SCIENTIST",
                      password_hash=hash_password("password123"), is_active=True)
    db.add_all([admin, scientist])
    db.flush()

    standard = Standard(standard_id="STD-TZ", name="IS 694", edition="2010", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-TZ-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="TESTING",
                     registered_by_id=scientist.id, assigned_assistant_id=scientist.id)
    db.add(sample)
    db.flush()
    db.add(CableProfile(sample_id=sample.sample_id, conductor_material="Copper", insulation_type="A",
                         confirmed=True, tested_core_colors=["RED"]))
    db.commit()
    db.close()

    with TestClient(app) as c:
        c.sample_id = "SMP-TZ-0001"
        yield c

    app.dependency_overrides.clear()


def _token(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_iso_utc_attaches_offset_to_a_naive_datetime():
    # Simulates exactly what SQLite hands back: a naive datetime that was
    # actually written as UTC but lost its tzinfo on the round trip.
    naive = datetime(2026, 8, 2, 14, 0, 0)
    result = iso_utc(naive)
    assert _has_utc_offset(result)
    assert result == "2026-08-02T14:00:00+00:00"


def test_iso_utc_passes_through_an_already_aware_datetime_unchanged():
    aware = datetime(2026, 8, 2, 14, 0, 0, tzinfo=timezone.utc)
    assert iso_utc(aware) == aware.isoformat()


def test_iso_utc_handles_none():
    assert iso_utc(None) is None


def test_sample_list_timestamps_carry_a_utc_offset(client):
    token = _token(client, "sci_tz")
    resp = client.get("/api/samples", headers=_auth(token))
    assert resp.status_code == 200
    samples = resp.json()
    assert len(samples) >= 1
    for s in samples:
        assert _has_utc_offset(s["created_at"]), f"created_at missing UTC offset: {s['created_at']!r}"


def test_sample_detail_timestamps_carry_a_utc_offset(client):
    token = _token(client, "sci_tz")
    resp = client.get(f"/api/samples/{client.sample_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert _has_utc_offset(resp.json()["created_at"])


def test_admin_user_list_timestamps_carry_a_utc_offset(client):
    token = _token(client, "admin_tz")
    resp = client.get("/api/admin/users", headers=_auth(token))
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 1
    for u in users:
        assert _has_utc_offset(u["created_at"]), f"created_at missing UTC offset: {u['created_at']!r}"


def test_admin_audit_log_timestamps_carry_a_utc_offset(client):
    token = _token(client, "admin_tz")
    resp = client.get("/api/admin/audit", headers=_auth(token))
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) >= 1
    for e in events:
        assert _has_utc_offset(e["timestamp"]), f"timestamp missing UTC offset: {e['timestamp']!r}"


def test_dashboard_recent_activity_timestamps_carry_a_utc_offset(client):
    token = _token(client, "sci_tz")
    resp = client.get("/api/dashboard", headers=_auth(token))
    assert resp.status_code == 200
    activity = resp.json()["recent_activity"]
    assert len(activity) >= 1
    for a in activity:
        assert _has_utc_offset(a["timestamp"]), f"timestamp missing UTC offset: {a['timestamp']!r}"
