"""
Regression tests for H9: the generated certificate (Test Report_694.docx
fill) must visibly flag overridden results, placeholder-derived limits,
and UNDETERMINED decisions -- previously a bare number looked identical
whether it was a clean system-verified PASS/FAIL, a Scientist's manual
correction, or a result still awaiting review, and a limit looked
identical whether it came from a verified Standards Knowledge Base entry
or an unconfirmed placeholder.

docx_report_filler.py had zero prior automated coverage at all -- these
tests generate a real certificate against a minimal fixture and read the
actual .docx cell text back out, rather than only unit-testing the marker
helper functions in isolation.
"""
import uuid

import docx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.models import AssignedTest, CableProfile, Sample, Standard, TestDefinition, TestRun, User
from app.services.docx_report_filler import generate_filled_report_docx


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / f'{uuid.uuid4().hex}.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_sample(db):
    scientist = User(username="cert_sci", password_hash="x", full_name="Cert Scientist", role="SCIENTIST")
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-CERT", name="IS 694", product_family="CABLE")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id="SMP-CERT-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="APPROVED", registered_by_id=scientist.id)
    db.add(sample)
    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", conductor_class="2",
                            insulation_type="A", sheath_type="ST1", fire_category="01",
                            confirmed=True, tested_core_colors=["RED"], has_outer_sheath=True)
    db.add(profile)
    db.flush()
    return sample


def _assign_and_submit(db, sample_id, test_id, core_position, *, calculated_value, limit_value,
                        limit_operator=">=", overridden=False, limit_source_kind="VERIFIED",
                        confidence_state="VERIFIED", result="PASS"):
    db.add(TestDefinition(test_id=test_id, name=test_id, unit="unit"))
    db.flush()
    at = AssignedTest(sample_id=sample_id, test_id=test_id, mandatory=True, enabled=True,
                       status="COMPLETED", core_position=core_position)
    db.add(at)
    db.flush()
    run = TestRun(
        assigned_test_id=at.id, attempt_number=1, raw_values={},
        calculated_value=calculated_value, calculated_unit="unit",
        limit_value=limit_value, limit_operator=limit_operator, limit_unit="unit",
        limit_source_kind=limit_source_kind, limit_source_ref="IS 694:2010",
        confidence_state=confidence_state, result=result,
        overridden=overridden, override_result="PASS" if overridden else None,
        override_reason="Scientist correction" if overridden else None,
    )
    db.add(run)
    db.flush()
    at.accepted_attempt_id = run.id
    return run


def _full_text(doc) -> str:
    return "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)


def test_overridden_result_is_flagged_on_the_certificate(db, tmp_path):
    sample = _seed_sample(db)
    _assign_and_submit(db, sample.sample_id, "TEST-0001", "RED", calculated_value=3.5, limit_value=5.0,
                        overridden=True)
    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"cert_{uuid.uuid4().hex}")
    text = _full_text(docx.Document(path))
    assert "[OVERRIDDEN]" in text


def test_placeholder_limit_is_flagged_on_the_certificate(db, tmp_path):
    sample = _seed_sample(db)
    _assign_and_submit(db, sample.sample_id, "TEST-0001", "RED", calculated_value=3.5, limit_value=5.0,
                        limit_source_kind="PLACEHOLDER", confidence_state="REVIEW_REQUIRED")
    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"cert_{uuid.uuid4().hex}")
    text = _full_text(docx.Document(path))
    assert "[PLACEHOLDER LIMIT]" in text


def test_undetermined_result_is_flagged_on_the_certificate(db, tmp_path):
    sample = _seed_sample(db)
    _assign_and_submit(db, sample.sample_id, "TEST-0001", "RED", calculated_value=4.95, limit_value=5.0,
                        confidence_state="REVIEW_REQUIRED", result="UNDETERMINED")
    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"cert_{uuid.uuid4().hex}")
    text = _full_text(docx.Document(path))
    assert "[UNDETERMINED]" in text


def test_a_clean_verified_pass_carries_no_markers_at_all(db, tmp_path):
    # The negative case: an ordinary, unremarkable result must NOT be
    # decorated with any flag -- markers exist to highlight the exception,
    # not clutter every cell.
    sample = _seed_sample(db)
    _assign_and_submit(db, sample.sample_id, "TEST-0001", "RED", calculated_value=3.5, limit_value=5.0)
    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"cert_{uuid.uuid4().hex}")
    text = _full_text(docx.Document(path))
    assert "[OVERRIDDEN]" not in text
    assert "[PLACEHOLDER LIMIT]" not in text
    assert "[UNDETERMINED]" not in text


def test_overridden_qualitative_result_is_flagged_too(db, tmp_path):
    # Qualitative (pass/fail-text, not numeric) tests go through a
    # different code path (_qualitative_text) -- must be covered
    # independently, not assumed to inherit the numeric path's behaviour.
    sample = _seed_sample(db)
    _assign_and_submit(db, sample.sample_id, "TEST-0025", None, calculated_value=1.0, limit_value=1.0,
                        limit_operator="==", overridden=True, result="PASS")
    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"cert_{uuid.uuid4().hex}")
    text = _full_text(docx.Document(path))
    assert "[OVERRIDDEN]" in text
