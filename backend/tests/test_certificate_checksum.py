"""
Regression tests for H10: every generated certificate gets a SHA-256
checksum of its own file, computed at generation time and stored on
Certificate.file_checksum_sha256.
"""
import hashlib
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.models import CableProfile, Certificate, Sample, Standard, User
from app.services import sample_service as svc
from app.services.checksum import compute_file_sha256


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / f'{uuid.uuid4().hex}.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_approved_sample(db):
    scientist = User(username="checksum_sci", password_hash="x", full_name="Checksum Scientist", role="SCIENTIST")
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-CHECKSUM", name="IS 694", product_family="CABLE")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id="SMP-CHECKSUM-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="APPROVED", registered_by_id=scientist.id)
    db.add(sample)
    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", conductor_class="2",
                            insulation_type="A", sheath_type="ST1", fire_category="01",
                            confirmed=True, tested_core_colors=["RED"], has_outer_sheath=True)
    db.add(profile)
    db.commit()
    return sample, scientist


def test_compute_file_sha256_matches_hashlib_directly(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_bytes(b"CableLIMS checksum test content")
    expected = hashlib.sha256(b"CableLIMS checksum test content").hexdigest()
    assert compute_file_sha256(str(p)) == expected


def test_generate_certificate_stores_a_checksum_matching_the_actual_file(db):
    sample, scientist = _seed_approved_sample(db)

    result = svc.generate_certificate(db, scientist, sample)

    assert "file_checksum_sha256" in result
    assert len(result["file_checksum_sha256"]) == 64  # SHA-256 hex digest length
    int(result["file_checksum_sha256"], 16)  # must be valid hex

    cert = db.query(Certificate).filter(Certificate.certificate_no == result["certificate_no"]).first()
    assert cert is not None
    assert cert.file_checksum_sha256 == result["file_checksum_sha256"]

    # The stored checksum must match the ACTUAL file on disk right now --
    # not just be present, but genuinely correct.
    assert compute_file_sha256(cert.file_path) == cert.file_checksum_sha256


def test_certificate_appears_in_sample_detail_with_its_checksum(db):
    sample, scientist = _seed_approved_sample(db)
    result = svc.generate_certificate(db, scientist, sample)

    db.refresh(sample)
    detail = svc.get_sample_detail(db, sample)
    assert detail["certificate"] is not None
    assert detail["certificate"]["file_checksum_sha256"] == result["file_checksum_sha256"]


def test_a_pre_h10_certificate_with_no_checksum_is_null_not_fabricated(db):
    # A certificate row that predates this column (or whose generation
    # failed before the checksum step) must report a null checksum -- never
    # a guessed/backfilled one that would misrepresent its own provenance.
    sample, scientist = _seed_approved_sample(db)
    legacy_cert = Certificate(certificate_no="CTL/CBL/LEGACY/0001", sample_id=sample.sample_id,
                               generated_by_id=scientist.id, overall_decision="PASS",
                               file_path="/nonexistent/legacy.docx", file_checksum_sha256=None)
    db.add(legacy_cert)
    db.commit()

    detail = svc.get_sample_detail(db, sample)
    assert detail["certificate"]["file_checksum_sha256"] is None
