"""
Golden certificate tests (H11): generate a certificate from a fully
deterministic, seeded fixture and compare its complete rendered text
against a known-good snapshot on disk (tests/golden/). Protects report
generation itself from regressions -- a change anywhere in
docx_report_filler.py (a reordered cell, a dropped marker, a formatting
change) that alters the certificate's actual output will fail this test,
even if every other test still passes.

This complements, rather than duplicates, existing coverage:
- test_calculation_golden_values.py protects the CALCULATION engine
  (is the number right for a given raw reading).
- test_certificate_transparency.py protects specific H9 marker strings
  in isolation.
- This file protects the FULL rendered certificate -- every cell, not
  just the ones a marker test happens to check.

Updating the golden file: if a deliberate, reviewed change to
docx_report_filler.py legitimately changes the certificate's output, run
this test, inspect the failure diff to confirm the NEW output is correct,
then overwrite tests/golden/full_certificate.txt with it. Never update the
golden file to make a test pass without first understanding why the
output changed.
"""
import uuid
from pathlib import Path

import docx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.models import AssignedTest, CableProfile, Sample, Standard, TestDefinition, TestRun, User
from app.services.docx_report_filler import generate_filled_report_docx

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_FILE = GOLDEN_DIR / "full_certificate.txt"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / f'{uuid.uuid4().hex}.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _def(db, test_id):
    db.add(TestDefinition(test_id=test_id, name=test_id, unit="unit"))
    db.flush()


def _submit(db, sample_id, test_id, core_position, *, calculated_value=None, calculated_unit=None,
            limit_value=None, limit_operator=">=", result="PASS", confidence_state="VERIFIED"):
    at = AssignedTest(sample_id=sample_id, test_id=test_id, mandatory=True, enabled=True,
                       status="COMPLETED", core_position=core_position)
    db.add(at)
    db.flush()
    run = TestRun(
        assigned_test_id=at.id, attempt_number=1, raw_values={},
        calculated_value=calculated_value, calculated_unit=calculated_unit,
        limit_value=limit_value, limit_operator=limit_operator, limit_unit=calculated_unit,
        limit_source_kind="VERIFIED", limit_source_ref="IS 694:2010",
        confidence_state=confidence_state, result=result,
    )
    db.add(run)
    db.flush()
    at.accepted_attempt_id = run.id
    return run


def _build_deterministic_certificate(db) -> str:
    """Builds one fully deterministic, seeded sample -- 3 cores, a
    representative cross-section of test types (conductor, dimensional,
    physical, qualitative, insulation resistance) -- and returns the
    generated certificate's complete extracted text."""
    scientist = User(username="golden_sci", password_hash="x", full_name="Golden Scientist", role="SCIENTIST")
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-GOLDEN", name="IS 694", product_family="CABLE")
    db.add(standard)
    db.flush()

    sample = Sample(sample_id="SMP-GOLDEN-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=3, cores_tested=3, csa_mm2=2.5, status="APPROVED", registered_by_id=scientist.id)
    db.add(sample)
    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", conductor_class="2",
                            insulation_type="A", sheath_type="ST1", fire_category="01",
                            confirmed=True, tested_core_colors=["RED", "YELLOW", "BLUE"], has_outer_sheath=True)
    db.add(profile)
    db.flush()

    for test_id in ("TEST-0001", "TEST-0002", "TEST-0003", "TEST-0006", "TEST-0014", "TEST-0019",
                     "TEST-0025", "TEST-0005", "TEST-0028"):
        _def(db, test_id)

    # a. Conductor resistance -- <=, Max
    _submit(db, sample.sample_id, "TEST-0001", "RED", calculated_value=3.500, calculated_unit="ohm/km",
            limit_value=5.000, limit_operator="<=")
    _submit(db, sample.sample_id, "TEST-0001", "YELLOW", calculated_value=3.520, calculated_unit="ohm/km",
            limit_value=5.000, limit_operator="<=")
    _submit(db, sample.sample_id, "TEST-0001", "BLUE", calculated_value=3.510, calculated_unit="ohm/km",
            limit_value=5.000, limit_operator="<=")

    # b. Insulation + sheath thickness -- >=, Nominal
    _submit(db, sample.sample_id, "TEST-0002", "RED", calculated_value=0.850, calculated_unit="mm",
            limit_value=0.800)
    _submit(db, sample.sample_id, "TEST-0002", "YELLOW", calculated_value=0.860, calculated_unit="mm",
            limit_value=0.800)
    _submit(db, sample.sample_id, "TEST-0002", "BLUE", calculated_value=0.840, calculated_unit="mm",
            limit_value=0.800)
    _submit(db, sample.sample_id, "TEST-0014", "SHEATH", calculated_value=1.300, calculated_unit="mm",
            limit_value=1.200)

    # c. Tensile strength (physical, insulation + sheath) -- >=, Min
    _submit(db, sample.sample_id, "TEST-0003", "RED", calculated_value=13.00, calculated_unit="N/mm2",
            limit_value=12.50)
    _submit(db, sample.sample_id, "TEST-0003", "YELLOW", calculated_value=13.10, calculated_unit="N/mm2",
            limit_value=12.50)
    _submit(db, sample.sample_id, "TEST-0003", "BLUE", calculated_value=12.90, calculated_unit="N/mm2",
            limit_value=12.50)
    _submit(db, sample.sample_id, "TEST-0003", "SHEATH", calculated_value=11.50, calculated_unit="N/mm2",
            limit_value=12.50)

    # Heat shock -- qualitative, all clean pass
    for pos in ("RED", "YELLOW", "BLUE", "SHEATH"):
        _submit(db, sample.sample_id, "TEST-0019", pos, calculated_value=0.0, limit_value=1.0, limit_operator="==")

    # d. High voltage tests -- qualitative, whole-sample
    _submit(db, sample.sample_id, "TEST-0025", None, calculated_value=0.0, limit_value=1.0, limit_operator="==")
    _submit(db, sample.sample_id, "TEST-0005", None, calculated_value=0.0, limit_value=1.0, limit_operator="==")

    # Insulation resistance -- volume resistivity (>=, Min) + IR constant (>=, Min)
    _submit(db, sample.sample_id, "TEST-0006", "RED", calculated_value=1e13, calculated_unit="ohm-cm",
            limit_value=1e12)
    _submit(db, sample.sample_id, "TEST-0006", "YELLOW", calculated_value=1e13, calculated_unit="ohm-cm",
            limit_value=1e12)
    _submit(db, sample.sample_id, "TEST-0006", "BLUE", calculated_value=1e13, calculated_unit="ohm-cm",
            limit_value=1e12)
    _submit(db, sample.sample_id, "TEST-0028", "RED", calculated_value=0.01000, calculated_unit="M-ohm.km",
            limit_value=0.00400)
    _submit(db, sample.sample_id, "TEST-0028", "YELLOW", calculated_value=0.01000, calculated_unit="M-ohm.km",
            limit_value=0.00400)
    _submit(db, sample.sample_id, "TEST-0028", "BLUE", calculated_value=0.01000, calculated_unit="M-ohm.km",
            limit_value=0.00400)

    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"golden_{uuid.uuid4().hex}")
    doc = docx.Document(path)
    return "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)


def test_certificate_matches_the_known_good_golden_output(db):
    actual = _build_deterministic_certificate(db)

    if not GOLDEN_FILE.exists():
        pytest.fail(
            f"No golden file yet at {GOLDEN_FILE}. Run this fixture once, review the output for "
            f"correctness by hand, then save it there before this test can run."
        )

    expected = GOLDEN_FILE.read_text(encoding="utf-8")
    assert actual == expected, (
        "Certificate output no longer matches the known-good golden file. If this change to "
        "docx_report_filler.py is deliberate and you've confirmed the NEW output is correct, "
        f"update {GOLDEN_FILE} to match -- never do this without reviewing the diff first."
    )


MARKERS_GOLDEN_FILE = GOLDEN_DIR / "certificate_with_markers.txt"


def _build_certificate_with_markers(db) -> str:
    """A second deterministic scenario (H9 + H11 combined): one overridden
    result, one placeholder-derived limit, one UNDETERMINED result -- the
    golden-diff path most likely to regress silently if a future change to
    docx_report_filler.py touches the marker logic without anyone noticing
    the exact appended text changed."""
    scientist = User(username="golden_marker_sci", password_hash="x", full_name="Golden Marker Scientist",
                      role="SCIENTIST")
    db.add(scientist)
    db.flush()
    standard = Standard(standard_id="STD-GOLDEN-MARKERS", name="IS 694", product_family="CABLE")
    db.add(standard)
    db.flush()
    sample = Sample(sample_id="SMP-GOLDEN-MARKERS-0001", product_family="CABLE", standard_id=standard.standard_id,
                     cores=1, cores_tested=1, csa_mm2=2.5, status="APPROVED", registered_by_id=scientist.id)
    db.add(sample)
    profile = CableProfile(sample_id=sample.sample_id, conductor_material="Copper", conductor_class="2",
                            insulation_type="A", sheath_type="ST1", fire_category="01",
                            confirmed=True, tested_core_colors=["RED"], has_outer_sheath=True)
    db.add(profile)
    db.flush()

    for test_id in ("TEST-0001", "TEST-0002", "TEST-0003"):
        _def(db, test_id)

    # Overridden
    at1 = AssignedTest(sample_id=sample.sample_id, test_id="TEST-0001", mandatory=True, enabled=True,
                        status="COMPLETED", core_position="RED")
    db.add(at1)
    db.flush()
    run1 = TestRun(assigned_test_id=at1.id, attempt_number=1, raw_values={},
                    calculated_value=3.500, calculated_unit="ohm/km", limit_value=5.000, limit_operator="<=",
                    limit_source_kind="VERIFIED", limit_source_ref="IS 694:2010",
                    confidence_state="VERIFIED", result="PASS",
                    overridden=True, override_result="PASS", override_reason="Scientist correction")
    db.add(run1)
    db.flush()
    at1.accepted_attempt_id = run1.id

    # Placeholder-derived limit
    placeholder_run = _submit(db, sample.sample_id, "TEST-0002", "RED", calculated_value=0.850,
                               calculated_unit="mm", limit_value=0.800, confidence_state="REVIEW_REQUIRED")
    placeholder_run.limit_source_kind = "PLACEHOLDER"
    db.flush()

    # UNDETERMINED
    _submit(db, sample.sample_id, "TEST-0003", "RED", calculated_value=12.60, calculated_unit="N/mm2",
            limit_value=12.50, result="UNDETERMINED", confidence_state="REVIEW_REQUIRED")

    db.commit()

    path = generate_filled_report_docx(db, sample.sample_id, f"golden_markers_{uuid.uuid4().hex}")
    doc = docx.Document(path)
    return "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)


def test_certificate_with_markers_matches_the_known_good_golden_output(db):
    actual = _build_certificate_with_markers(db)

    if not MARKERS_GOLDEN_FILE.exists():
        pytest.fail(
            f"No golden file yet at {MARKERS_GOLDEN_FILE}. Run this fixture once, review the output "
            f"for correctness by hand, then save it there before this test can run."
        )

    expected = MARKERS_GOLDEN_FILE.read_text(encoding="utf-8")
    assert actual == expected, (
        "Certificate output (override/placeholder/undetermined scenario) no longer matches the "
        f"known-good golden file. Update {MARKERS_GOLDEN_FILE} only after confirming the new "
        "output is correct."
    )
