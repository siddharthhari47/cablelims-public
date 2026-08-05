"""
Seed script: demo users + IS 694 configuration (test catalog, assignment
rules) + a couple of historical samples so the dashboard isn't empty on
first login. Run once via `python -m app.seed`. Idempotent (safe to re-run).

Sprint Priority 1: the test catalog below is the full set extracted from
CTL's own observation sheet ("OBSERVATION SHEET FOR 694_2010_4 Core.docx"),
Test Report template, and worked Calculations.xlsx example -- not the
smaller MVP subset. See CableLIMS_SDD_v2.md and the sprint summary for the
source-to-catalog mapping.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.db import Base, SessionLocal, engine
from app.engines.aggregation import overall_decision_from_summary, summarize_sample
from app.engines.calculation_engine import run_calculation
from app.engines.confidence_engine import evaluate as confidence_evaluate
from app.engines.rule_engine import assign_tests, expand_for_positions, suggested_core_colors
from app.models.models import (
    AssignedTest,
    AuditEvent,
    CableProfile,
    Certificate,
    Sample,
    Standard,
    TestAssignmentRule,
    TestDefinition,
    TestRun,
    User,
)
from app.services.auth_service import hash_password
from app.services.checksum import compute_file_sha256
from app.services.docx_report_filler import generate_filled_report_docx


def _get_or_create(db, model, defaults=None, **kwargs):
    inst = db.query(model).filter_by(**kwargs).first()
    if inst:
        return inst, False
    params = dict(kwargs)
    params.update(defaults or {})
    inst = model(**params)
    db.add(inst)
    db.flush()
    return inst, True


def seed_users(db):
    users = [
        dict(username="scientist1", full_name="Dr. Ananya Rao", role="SCIENTIST"),
        dict(username="scientist2", full_name="Dr. Vikram Nair", role="SCIENTIST"),
        dict(username="assistant1", full_name="Ravi Kumar", role="SCIENTIFIC_ASSISTANT"),
        dict(username="assistant2", full_name="Priya Sharma", role="SCIENTIFIC_ASSISTANT"),
        dict(username="admin1", full_name="System Administrator", role="ADMINISTRATOR"),
    ]
    created = {}
    for u in users:
        inst, _ = _get_or_create(
            db, User, username=u["username"],
            defaults=dict(full_name=u["full_name"], role=u["role"], password_hash=hash_password("demo1234"),
                           is_demo=True),
        )
        created[u["username"]] = inst
    db.commit()
    return created


def seed_standard(db):
    std, _ = _get_or_create(
        db, Standard, standard_id="STD-0001",
        defaults=dict(
            name="IS 694", edition="2010", amendment="Amendment 3 (2015), reaffirmed 2020 up to Amdt 4",
            product_family="CABLE",
            scope_summary="PVC insulated unsheathed and sheathed cables/cords, rigid and flexible "
                          "conductor, up to and including 1100 V (as amended).",
        ),
    )
    db.commit()
    return std


# =============================================================================
# TEST CATALOG -- full set from CTL's observation sheet / Test Report /
# Calculations.xlsx. `scope` drives AssignedTest expansion (rule_engine.py):
#   ONCE | SHEATH_ONLY | PER_CORE | PER_CORE_AND_SHEATH
#
# `report_section` groups tests exactly the way Test Report_694.docx does,
# under IS 694:2010 Table 1, Sl. No. iii's own lettered headings:
#   CONDUCTOR        -- a) Test on Conductor
#   DIMENSIONAL      -- b) Overall dimensions & thickness of insulation/sheath
#   PHYSICAL         -- c) Physical test on Insulation (and, via the same
#                        test on the SHEATH core_position, its "d) Physical
#                        test on Sheath" analog -- the docx renders both as
#                        an extra "Outer Sheath" column on the same rows)
#   COMPLETED_CABLE  -- d) Test on Completed Cable (HV, insulation resistance)
# =============================================================================
TEST_DEFS = [
    # -- Conductor tests --------------------------------------------------
    dict(test_id="TEST-0001", name="Conductor Resistance", category="Electrical", unit="ohm/km", sequence=1,
         scope="PER_CORE", report_section="CONDUCTOR",
         input_schema=[
             {"key": "observed_resistance_mohm", "label": "Observed Resistance", "type": "number", "unit": "mOhm"},
             {"key": "specimen_length_m", "label": "Specimen Length", "type": "number", "unit": "m"},
             {"key": "room_temperature_c", "label": "Room Temperature", "type": "number", "unit": "deg C"},
         ]),
    dict(test_id="TEST-0011", name="Annealing Test (Copper Conductor)", category="Mechanical", unit="%", sequence=2,
         scope="ONCE", report_section="CONDUCTOR",
         input_schema=[
             {"key": "wire_diameter_mm", "label": "Wire Diameter", "type": "number", "unit": "mm"},
             {"key": "specimen_gauge_length_mm", "label": "Specimen (Gauge) Length", "type": "number", "unit": "mm", "default": 250},
             {"key": "length_after_break_mm", "label": "Length After Break", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0012", name="Tensile Test (Aluminium Conductor)", category="Mechanical", unit="N/mm2", sequence=3,
         scope="ONCE", report_section="CONDUCTOR",
         input_schema=[
             {"key": "aluminium_grade", "label": "Aluminium Grade", "type": "select",
              "options": ["Grade 0", "Grade H2", "Grade H4"]},
             {"key": "after_stranding", "label": "Measured After Stranding?", "type": "boolean"},
             {"key": "wire_diameter_mm", "label": "Diameter of the Wire", "type": "number", "unit": "mm"},
             {"key": "breaking_load_n", "label": "Breaking Load", "type": "number", "unit": "N"},
         ]),
    dict(test_id="TEST-0013", name="Wrapping Test (Aluminium Conductor)", category="Mechanical", unit="pass/fail", sequence=4,
         scope="ONCE", report_section="CONDUCTOR",
         input_schema=[
             {"key": "wire_diameter_mm", "label": "Diameter of the Wire", "type": "number", "unit": "mm"},
             {"key": "wire_broke", "label": "Wire Broke?", "type": "boolean"},
         ]),

    # -- Dimensional tests --------------------------------------------------
    dict(test_id="TEST-0002", name="Insulation Thickness", category="Dimensional", unit="mm", sequence=5,
         scope="PER_CORE", report_section="DIMENSIONAL",
         input_schema=[
             {"key": "readings_mm", "label": "Thickness Readings", "type": "number_array", "unit": "mm", "count": 5},
         ]),
    dict(test_id="TEST-0014", name="Sheath Thickness", category="Dimensional", unit="mm", sequence=6,
         scope="SHEATH_ONLY", report_section="DIMENSIONAL",
         input_schema=[
             {"key": "readings_mm", "label": "Thickness Readings", "type": "number_array", "unit": "mm", "count": 5},
         ]),

    # -- Physical tests on insulation / sheath (PER_CORE_AND_SHEATH) --------
    dict(test_id="TEST-0003", name="Tensile Strength", category="Mechanical", unit="N/mm2", sequence=7,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "breaking_load_n", "label": "Breaking Load", "type": "number", "unit": "N"},
             {"key": "width_mm", "label": "Specimen Width", "type": "number", "unit": "mm"},
             {"key": "thickness_mm", "label": "Specimen Thickness", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0004", name="Elongation at Break", category="Mechanical", unit="%", sequence=8,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "initial_length_mm", "label": "Initial Gauge Length", "type": "number", "unit": "mm"},
             {"key": "final_length_mm", "label": "Length at Break", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0015", name="Ageing -- Tensile Strength Variation", category="Mechanical", unit="%", sequence=9,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "before_tensile_mpa", "label": "Tensile Strength Before Ageing (autofill)", "type": "number", "unit": "N/mm2"},
             {"key": "breaking_load_n", "label": "Breaking Load (after ageing)", "type": "number", "unit": "N"},
             {"key": "width_mm", "label": "Specimen Width", "type": "number", "unit": "mm"},
             {"key": "thickness_mm", "label": "Specimen Thickness", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0016", name="Ageing -- Elongation Variation", category="Mechanical", unit="%", sequence=10,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "before_elongation_pct", "label": "Elongation Before Ageing (autofill)", "type": "number", "unit": "%"},
             {"key": "initial_length_mm", "label": "Initial Gauge Length (after ageing)", "type": "number", "unit": "mm"},
             {"key": "final_length_mm", "label": "Length at Break (after ageing)", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0017", name="Loss of Mass Test", category="Mechanical", unit="mg/cm2", sequence=11,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "initial_weight_mg", "label": "Initial Weight", "type": "number", "unit": "mg"},
             {"key": "final_weight_mg", "label": "Final Weight", "type": "number", "unit": "mg"},
             {"key": "surface_area_cm2", "label": "Surface Area", "type": "number", "unit": "cm2"},
         ]),
    dict(test_id="TEST-0018", name="Shrinkage Test", category="Mechanical", unit="%", sequence=12,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "length_before_mm", "label": "Length Before Shrinkage", "type": "number", "unit": "mm"},
             {"key": "length_after_mm", "label": "Length After Shrinkage", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0019", name="Heat Shock Test", category="Mechanical", unit="pass/fail", sequence=13,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "cracks_observed", "label": "Cracks or Scales Observed?", "type": "boolean"},
         ]),
    dict(test_id="TEST-0020", name="Hot Deformation Test", category="Mechanical", unit="%", sequence=14,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "t1_indentation_mm", "label": "Thickness at Indentation Point (2 specimens)", "type": "number_array", "unit": "mm", "count": 2},
             {"key": "t2_reference_mm", "label": "Thickness ~10mm from Indentation (2 per specimen)", "type": "number_array", "unit": "mm", "count": 4},
         ]),
    dict(test_id="TEST-0021", name="Thermal Stability Test", category="Fire", unit="min", sequence=15,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "thermal_stability_minutes", "label": "Thermal Stability Time", "type": "number", "unit": "min"},
         ]),

    # -- Fire performance (PER_CORE_AND_SHEATH, FR/FR-LSH only) -------------
    dict(test_id="TEST-0008", name="Oxygen Index", category="Fire", unit="%", sequence=16,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[{"key": "oxygen_index_pct", "label": "Oxygen Index", "type": "number", "unit": "%"}]),
    dict(test_id="TEST-0009", name="Halogen Acid Gas Evolution", category="Fire", unit="%", sequence=17,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "sample_weight_g", "label": "Sample Weight", "type": "number", "unit": "g"},
             {"key": "titration_b_ml", "label": "Titration Volume B", "type": "number", "unit": "ml"},
             {"key": "titration_a_ml", "label": "Titration Volume A (blank)", "type": "number", "unit": "ml"},
             {"key": "titration_factor", "label": "Titration Factor (F)", "type": "number", "unit": ""},
         ]),
    dict(test_id="TEST-0010", name="Temperature Index", category="Fire", unit="deg C", sequence=18,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[{"key": "temperature_index_c", "label": "Temperature Index (at 21% O2)", "type": "number", "unit": "deg C"}]),
    dict(test_id="TEST-0022", name="Smoke Density Test", category="Fire", unit="%", sequence=19,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[
             {"key": "readings_pct", "label": "Light Absorption Readings (t=0 to 240s, 15s steps)", "type": "number_array", "unit": "%", "count": 17},
         ]),
    dict(test_id="TEST-0023", name="Flammability -- Burn Duration", category="Fire", unit="s", sequence=20,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[{"key": "burn_duration_after_removal_s", "label": "Burning Period After Flame Removal", "type": "number", "unit": "s"}]),
    dict(test_id="TEST-0024", name="Flammability -- Unaffected Length", category="Fire", unit="mm", sequence=21,
         scope="PER_CORE_AND_SHEATH", report_section="PHYSICAL",
         input_schema=[{"key": "unaffected_length_mm", "label": "Unaffected Length from Top Clamp", "type": "number", "unit": "mm"}]),

    # -- Whole-cable electrical tests -----------------------------------------
    dict(test_id="TEST-0005", name="High Voltage Test (Room Temperature)", category="Electrical", unit="withstand", sequence=22,
         scope="ONCE", report_section="COMPLETED_CABLE",
         input_schema=[{"key": "breakdown_observed", "label": "Breakdown Observed?", "type": "boolean"}]),
    dict(test_id="TEST-0025", name="High Voltage Test (Water Immersion)", category="Electrical", unit="withstand", sequence=23,
         scope="ONCE", report_section="COMPLETED_CABLE",
         input_schema=[{"key": "breakdown_observed", "label": "Breakdown Observed?", "type": "boolean"}]),
    dict(test_id="TEST-0006", name="Insulation Resistance -- Volume Resistivity", category="Electrical", unit="ohm-cm", sequence=24,
         scope="PER_CORE", report_section="COMPLETED_CABLE",
         input_schema=[
             {"key": "specimen_length_m", "label": "Specimen Length", "type": "number", "unit": "m"},
             {"key": "insulation_resistance_megaohm", "label": "Insulation Resistance", "type": "number", "unit": "M-ohm"},
             {"key": "overall_diameter_mm", "label": "Overall Diameter", "type": "number", "unit": "mm"},
             {"key": "conductor_diameter_mm", "label": "Conductor Diameter", "type": "number", "unit": "mm"},
         ]),
    dict(test_id="TEST-0028", name="Insulation Resistance Constant", category="Electrical", unit="M-ohm.km", sequence=25,
         scope="PER_CORE", report_section="COMPLETED_CABLE",
         input_schema=[
             {"key": "specimen_length_m", "label": "Specimen Length", "type": "number", "unit": "m"},
             {"key": "insulation_resistance_megaohm", "label": "Insulation Resistance", "type": "number", "unit": "M-ohm"},
             {"key": "overall_diameter_mm", "label": "Overall Diameter", "type": "number", "unit": "mm"},
             {"key": "conductor_diameter_mm", "label": "Conductor Diameter", "type": "number", "unit": "mm"},
         ]),

    # -- Category 02 (outdoor) only -------------------------------------------
    dict(test_id="TEST-0026", name="Cold Bend Test", category="Mechanical", unit="pass/fail", sequence=26,
         scope="ONCE", report_section="PHYSICAL",
         input_schema=[{"key": "cracks_observed", "label": "Cracks or Scales Observed?", "type": "boolean"}]),
    dict(test_id="TEST-0027", name="Cold Impact Test", category="Mechanical", unit="pass/fail", sequence=27,
         scope="ONCE", report_section="PHYSICAL",
         input_schema=[{"key": "cracks_observed", "label": "Cracks or Scales Observed?", "type": "boolean"}]),
]

RULES = [
    dict(rule_id="RULE-0001", test_id="TEST-0001", condition="always", mandatory=True, priority=1, clause_reference="IS 8130:2013 cl.7.3 / Table 1-5; IS 10810 Pt.5"),
    dict(rule_id="RULE-0011", test_id="TEST-0011", condition="conductor_material == Copper", mandatory=True, priority=2, clause_reference="IS 8130:2013 cl.7.1.2.1; IS 10810 Pt.1"),
    dict(rule_id="RULE-0012", test_id="TEST-0012", condition="conductor_material == Aluminium", mandatory=True, priority=3, clause_reference="IS 8130:2013 cl.7.2.1; IS 10810 Pt.2"),
    dict(rule_id="RULE-0013", test_id="TEST-0013", condition="conductor_material == Aluminium", mandatory=True, priority=4, clause_reference="IS 8130:2013 cl.6.2.2; IS 10810 Pt.3"),
    dict(rule_id="RULE-0002", test_id="TEST-0002", condition="always", mandatory=True, priority=5, clause_reference="IS 694:2010 cl.8.3, Table 5; IS 10810 Pt.6"),
    dict(rule_id="RULE-0014", test_id="TEST-0014", condition="always", mandatory=True, priority=6, clause_reference="IS 694:2010 cl.8.3; IS 10810 Pt.6"),
    dict(rule_id="RULE-0003", test_id="TEST-0003", condition="always", mandatory=True, priority=7, clause_reference="IS 5831:1984 Table 1/2; IS 10810 Pt.7"),
    dict(rule_id="RULE-0004", test_id="TEST-0004", condition="always", mandatory=True, priority=8, clause_reference="IS 5831:1984 Table 1/2; IS 10810 Pt.7"),
    dict(rule_id="RULE-0015", test_id="TEST-0015", condition="always", mandatory=True, priority=9, clause_reference="IS 10810 Pt.11"),
    dict(rule_id="RULE-0016", test_id="TEST-0016", condition="always", mandatory=True, priority=10, clause_reference="IS 10810 Pt.11"),
    dict(rule_id="RULE-0017", test_id="TEST-0017", condition="always", mandatory=True, priority=11, clause_reference="IS 10810 Pt.10"),
    dict(rule_id="RULE-0018", test_id="TEST-0018", condition="always", mandatory=True, priority=12, clause_reference="IS 10810 Pt.12"),
    dict(rule_id="RULE-0019", test_id="TEST-0019", condition="always", mandatory=True, priority=13, clause_reference="IS 10810 Pt.14"),
    dict(rule_id="RULE-0020", test_id="TEST-0020", condition="always", mandatory=True, priority=14, clause_reference="IS 10810 Pt.15"),
    dict(rule_id="RULE-0021", test_id="TEST-0021", condition="always", mandatory=True, priority=15, clause_reference="IS 10810 Pt.60"),
    dict(rule_id="RULE-0008", test_id="TEST-0008", condition="fire_category in (FR,FR-LSH)", mandatory=True, priority=16, clause_reference="IS 694:2010 cl.10.5; IS 10810 Pt.58"),
    dict(rule_id="RULE-0009", test_id="TEST-0009", condition="fire_category in (FR-LSH)", mandatory=True, priority=17, clause_reference="IS 694:2010 cl.10.6; IS 10810 Pt.59"),
    dict(rule_id="RULE-0010", test_id="TEST-0010", condition="fire_category in (FR-LSH)", mandatory=True, priority=18, clause_reference="IS 694:2010 cl.10.7; IS 10810 Pt.64"),
    dict(rule_id="RULE-0022", test_id="TEST-0022", condition="fire_category in (FR-LSH)", mandatory=True, priority=19, clause_reference="IS 13360 Pt.6/Sec.9"),
    dict(rule_id="RULE-0023", test_id="TEST-0023", condition="fire_category in (FR,FR-LSH)", mandatory=True, priority=20, clause_reference="IS 694:2010 cl.10.4; IS 10810 Pt.53"),
    dict(rule_id="RULE-0024", test_id="TEST-0024", condition="fire_category in (FR,FR-LSH)", mandatory=True, priority=21, clause_reference="IS 694:2010 cl.10.4; IS 10810 Pt.53"),
    dict(rule_id="RULE-0005", test_id="TEST-0005", condition="always", mandatory=True, priority=22, clause_reference="IS 694:2010 cl.10.2; IS 10810 Pt.45"),
    dict(rule_id="RULE-0025", test_id="TEST-0025", condition="always", mandatory=True, priority=23, clause_reference="IS 694:2010 cl.10.1; IS 10810 Pt.45"),
    dict(rule_id="RULE-0006", test_id="TEST-0006", condition="always", mandatory=True, priority=24, clause_reference="IS 10810 Pt.43"),
    dict(rule_id="RULE-0028", test_id="TEST-0028", condition="always", mandatory=True, priority=25, clause_reference="IS 10810 Pt.43"),
    dict(rule_id="RULE-0026", test_id="TEST-0026", condition="fire_category == 02", mandatory=True, priority=26, clause_reference="IS 694:2010 Table 1 sl.iii.c.8; IS 10810 Pt.20"),
    dict(rule_id="RULE-0027", test_id="TEST-0027", condition="fire_category == 02", mandatory=False, priority=27, clause_reference="IS 694:2010 Table 1 sl.iii.c.9; IS 10810 Pt.21 (Optional)"),
]


def seed_test_catalog(db, standard):
    for td in TEST_DEFS:
        _get_or_create(db, TestDefinition, test_id=td["test_id"], defaults={k: v for k, v in td.items() if k != "test_id"})
    db.commit()
    # keep scope/input_schema in sync on re-seed even if the row already existed
    for td in TEST_DEFS:
        row = db.query(TestDefinition).filter_by(test_id=td["test_id"]).first()
        for k, v in td.items():
            if k != "test_id":
                setattr(row, k, v)
    db.commit()
    for r in RULES:
        _get_or_create(
            db, TestAssignmentRule, rule_id=r["rule_id"],
            defaults=dict(standard_id=standard.standard_id, test_id=r["test_id"], condition=r["condition"],
                          mandatory=r["mandatory"], priority=r["priority"], clause_reference=r["clause_reference"]),
        )
    db.commit()


def _make_sample(db, sample_id, standard, scientist, assistant, cores, csa, fire_category,
                  conductor_material, insulation_type, sheath_type, construction, days_ago=0):
    sample, created = _get_or_create(
        db, Sample, sample_id=sample_id,
        defaults=dict(
            product_family="CABLE", standard_id=standard.standard_id, cores=cores, csa_mm2=csa,
            cores_tested=cores, remarks="Routine acceptance testing.", status="REGISTERED",
            registered_by_id=scientist.id, assigned_assistant_id=assistant.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        ),
    )
    if not created:
        # Idempotent re-run: this demo sample already exists with its
        # profile/readings fully populated from a previous seed run --
        # nothing left to do. (Returning the bare Sample here used to crash
        # the caller's `sample, profile, assigned_tests = result` unpack;
        # None makes the caller's existing `if result:` guard skip it
        # cleanly instead.)
        return None
    profile = CableProfile(
        sample_id=sample.sample_id, conductor_material=conductor_material, conductor_class="2",
        insulation_type=insulation_type, insulation_material="PVC", sheath_type=sheath_type,
        fire_category=fire_category, construction=construction, source="MANUAL", confirmed=True,
        confirmed_by_id=assistant.id,
        # Demo data stands in for what a Scientist/Assistant would explicitly
        # confirm during profiling -- suggested_core_colors() here plays the
        # role of "accepting the suggested default" rather than a silent
        # server-side auto-assignment (that path no longer exists).
        tested_core_colors=suggested_core_colors(cores),
        has_outer_sheath=bool(sheath_type), has_armour=False, has_inner_sheath=False,
        # Demo dimensional readings -- illustrative, like the rest of this
        # seed script's DEMO_READINGS, not sourced from a real inspection.
        # (ignore comment below: the SQLAlchemy mypy plugin can't fully
        # resolve a plain Column(Float) to a concrete numeric type -- see
        # engines/aggregation.py's matching note -- genuinely correct at
        # runtime.)
        cable_shape="Round", overall_diameter_mm=9.4 if csa <= 4 else 14.6,  # type: ignore[arg-type]
    )
    db.add(profile)
    sample.status = "PROFILE_VERIFIED"
    db.flush()

    outcomes = assign_tests(db, standard.standard_id, profile)
    expanded = expand_for_positions(db, outcomes, profile)
    assigned_tests = []
    for o in expanded:
        at = AssignedTest(sample_id=sample.sample_id, test_id=o.test_id, mandatory=o.mandatory,
                           enabled=True, status="PENDING", core_position=o.core_position)
        db.add(at)
        assigned_tests.append(at)
    sample.status = "TESTING"
    db.flush()
    return sample, profile, assigned_tests


# Demo raw readings -- applied uniformly across whichever core/sheath
# positions a test expands to (same value entered per position for a clean,
# reproducible demo, not meant to represent realistic per-core variance).
DEMO_READINGS: Dict[str, Dict[str, Any]] = {
    "TEST-0001": {"observed_resistance_mohm": 18.2, "specimen_length_m": 5.0, "room_temperature_c": 27},
    "TEST-0002": {"readings_mm": [0.82, 0.81, 0.85, 0.80, 0.83]},
    "TEST-0003": {"breaking_load_n": 210, "width_mm": 10, "thickness_mm": 1.6},
    "TEST-0004": {"initial_length_mm": 25, "final_length_mm": 68},
    "TEST-0005": {"breakdown_observed": False},
    "TEST-0006": {"specimen_length_m": 5.0, "insulation_resistance_megaohm": 3200, "overall_diameter_mm": 14.5, "conductor_diameter_mm": 10.2},
    "TEST-0008": {"oxygen_index_pct": 29.3},
    "TEST-0009": {"sample_weight_g": 1.0, "titration_b_ml": 12.5, "titration_a_ml": 0.5, "titration_factor": 1.0},
    "TEST-0010": {"temperature_index_c": 262},
    "TEST-0011": {"wire_diameter_mm": 0.3, "specimen_gauge_length_mm": 250, "length_after_break_mm": 297.5},
    "TEST-0014": {"readings_mm": [1.32, 1.29, 1.35, 1.28, 1.31]},  # tuned for CSA=2.5mm2, 3-core nominal 1.3mm
    "TEST-0015": {"before_tensile_mpa": 13.12, "breaking_load_n": 195, "width_mm": 10, "thickness_mm": 1.6},
    "TEST-0016": {"before_elongation_pct": 172.0, "initial_length_mm": 25, "final_length_mm": 62},
    "TEST-0017": {"initial_weight_mg": 850, "final_weight_mg": 848.5, "surface_area_cm2": 5.0},
    "TEST-0018": {"length_before_mm": 200, "length_after_mm": 194},
    "TEST-0019": {"cracks_observed": False},
    "TEST-0020": {"t1_indentation_mm": [0.85, 0.83], "t2_reference_mm": [1.0, 0.98, 1.02, 0.99]},
    "TEST-0021": {"thermal_stability_minutes": 95},
    "TEST-0022": {"readings_pct": [0, 5, 12, 18, 24, 29, 33, 37, 40, 43, 45, 47, 49, 50, 51, 52, 53]},
    "TEST-0023": {"burn_duration_after_removal_s": 12},
    "TEST-0024": {"unaffected_length_mm": 85},
    "TEST-0025": {"breakdown_observed": False},
    "TEST-0028": {"specimen_length_m": 5.0, "insulation_resistance_megaohm": 3200, "overall_diameter_mm": 14.5, "conductor_diameter_mm": 10.2},
}


def _submit_and_decide(db, assigned_test, profile, csa, assistant, cores=None):
    raw = DEMO_READINGS.get(assigned_test.test_id)
    if raw is None:
        return
    calc = run_calculation(assigned_test.test_id, raw, profile, csa, core_position=assigned_test.core_position, cores=cores)
    outcome = confidence_evaluate(calc)
    # (ignore comments below on calculated_value/limit_value/margin_pct:
    # same plain-Column(Float) mypy-plugin gap as overall_diameter_mm above.)
    run = TestRun(
        assigned_test_id=assigned_test.id, attempt_number=1, raw_values=raw,
        submitted_by_id=assistant.id,
        calculated_value=calc.calculated_value, calculated_unit=calc.calculated_unit,  # type: ignore[arg-type]
        limit_value=calc.limit_value, limit_operator=calc.operator,  # type: ignore[arg-type]
        limit_unit=calc.calculated_unit, margin_pct=outcome.margin_pct,  # type: ignore[arg-type]
        limit_source_kind=outcome.limit_source_kind, limit_source_ref=outcome.limit_source_ref,
        confidence_state=outcome.confidence_state, result=outcome.result,
        result_explanation=outcome.explanation,
    )
    db.add(run)
    db.flush()
    assigned_test.accepted_attempt_id = run.id
    assigned_test.status = "COMPLETED" if outcome.result in ("PASS", "FAIL") else "REPEAT_REQUIRED"


def seed_demo_samples(db, users, standard):
    scientist = users["scientist1"]
    assistant = users["assistant1"]

    # Historical sample #1: fully approved + certificate already issued.
    # Insulation Type A (general purpose PVC) -- matches the DEMO_READINGS
    # tensile/elongation values, which were originally tuned against Type A's
    # 12.5 N/mm2 / 150% minimums.
    # NOTE: CSA is 2.5 mm^2 to match DEMO_READINGS' conductor-resistance reading.
    result = _make_sample(
        db, "SMP-2026-0009", standard, scientist, assistant, cores=3, csa=2.5,
        fire_category="01", conductor_material="Copper", insulation_type="A", sheath_type="ST1",
        construction="3 core, sheathed, fixed wiring", days_ago=6,
    )
    if result:
        sample, profile, assigned_tests = result
        for at in assigned_tests:
            _submit_and_decide(db, at, profile, sample.csa_mm2, assistant, cores=sample.cores)
        db.flush()
        sample.status = "APPROVED"

        summary = summarize_sample(db, sample.sample_id)
        overall = overall_decision_from_summary(summary)

        cert_no = "CTL/CBL/2026/0009"
        cert = Certificate(
            certificate_no=cert_no, sample_id=sample.sample_id, generated_by_id=scientist.id,
            overall_decision=overall, file_path="",
        )
        db.add(cert)
        db.flush()

        try:
            path = generate_filled_report_docx(db, sample.sample_id, cert_no.replace("/", "_"))
            cert.file_path = path
            cert.file_checksum_sha256 = compute_file_sha256(path)
        except Exception as e:  # pragma: no cover -- demo seed should not hard-fail
            print("Certificate pre-generation skipped:", e)
        sample.status = "ARCHIVED"
        db.commit()

    # Historical sample #2: still mid-testing, sitting in the assistant's queue
    result2 = _make_sample(
        db, "SMP-2026-0011", standard, scientist, assistant, cores=1, csa=2.5,
        fire_category="02", conductor_material="Copper", insulation_type="A", sheath_type=None,
        construction="Single core, unsheathed", days_ago=2,
    )
    if result2:
        sample2, profile2, assigned_tests2 = result2
        # only submit a handful of tests, leave the rest pending -- shows "in progress"
        for at in assigned_tests2[:3]:
            _submit_and_decide(db, at, profile2, sample2.csa_mm2, assistant, cores=sample2.cores)
        db.commit()


def run(config_only: bool = False):
    """config_only=True seeds ONLY the standard/test-catalog/rule configuration
    -- no demo1234 accounts, no example samples. This is what a real handoff
    to an external site should run (see first_time_setup.bat); the demo
    accounts/samples are for our own internal development and demonstrations
    only, never for a real install.

    Demo accounts/samples additionally require CABLELIMS_ALLOW_DEMO_USERS=1
    in the environment, on top of config_only being False, before they'll be
    created -- two independent things have to go wrong (someone runs the bare
    `python -m app.seed` on a real server AND that server happens to have
    this variable set) rather than one habit-driven copy-paste command being
    enough to put demo1234/ADMINISTRATOR on a production box. Set it in your
    own local shell/`.env` for day-to-day development; a fresh server clone
    that has never heard of this variable stays safe by default."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        standard = seed_standard(db)
        seed_test_catalog(db, standard)
        note = "Configuration seeded (standards/tests/rules only -- no demo accounts or samples)."
        allow_demo = os.environ.get("CABLELIMS_ALLOW_DEMO_USERS") == "1"
        if not config_only and allow_demo:
            users = seed_users(db)
            seed_demo_samples(db, users, standard)
            note = "Configuration + demo accounts + demo samples seeded."
        elif not config_only and not allow_demo:
            note = ("Configuration seeded (standards/tests/rules only). Demo accounts/samples were "
                     "requested but skipped -- set CABLELIMS_ALLOW_DEMO_USERS=1 to allow them "
                     "(never do this on a real install).")
        db.add(AuditEvent(actor_name="system", action="SEED", entity_type="system", entity_id="-",
                           details={"note": note}))
        db.commit()
        print(note)
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    run(config_only="--config-only" in sys.argv)
