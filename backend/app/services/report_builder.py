"""
Builds the exact data shape the certificate PDF needs to reproduce
Test Report_694.docx's own layout: a General Requirements / Construction
summary (IS 694:2010 Table 1 Sl.i/ii, boilerplate clause requirements --
not a numeric threshold, so safe to state descriptively) followed by the
Type Tests, grouped into the same a/b/c/d sections and Specified-vs-per-
position-Observed columns the Calculation tab already uses on screen
(TestDefinition.report_section). Kept as one shared builder so the on-
screen view and the PDF can never structurally drift apart.
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.models import AssignedTest, CableProfile, Sample, TestAssignmentRule, TestRun


def clause_references(db: Session, standard_id: str) -> Dict[str, str]:
    rows = db.query(TestAssignmentRule).filter(TestAssignmentRule.standard_id == standard_id).all()
    out: Dict[str, str] = {}
    for r in rows:
        if r.test_id not in out and r.clause_reference:
            out[r.test_id] = r.clause_reference
    return out

SECTION_LABELS = {
    "CONDUCTOR": "a. Test on Conductor",
    "DIMENSIONAL": "b. Overall Dimensions & Thickness of Insulation and Sheath",
    "PHYSICAL": "c. Physical Test on Insulation (and Sheath)",
    "COMPLETED_CABLE": "d. Test on Completed Cable",
}
SECTION_ORDER = ["CONDUCTOR", "DIMENSIONAL", "PHYSICAL", "COMPLETED_CABLE"]
POSITION_ORDER = ["RED", "YELLOW", "BLUE", "BLACK", "SHEATH"]
POSITION_LABELS = {"RED": "Red", "YELLOW": "Yellow", "BLUE": "Blue", "BLACK": "Black", "SHEATH": "Outer Sheath"}


def _conductor_spec_text(material: Optional[str]) -> str:
    if material == "Copper":
        return "High conductivity copper, plain or tinned (IS 8130)"
    if material == "Aluminium":
        return "Aluminium, Grade 0/H2/H4 (IS 8130)"
    return material or "-"


def _insulation_spec_text(itype: Optional[str]) -> str:
    if not itype:
        return "-"
    return (f"PVC Type {itype}, applied by extrusion; shall fit closely to the conductor and be "
            f"removable without damage to the conductor or the insulation (IS 694 cl.5.1/5.2)")


def _sheath_spec_text(stype: Optional[str]) -> str:
    if not stype:
        return "Unsheathed"
    return (f"PVC Type {stype}, applied by extrusion; the sheath may fill the space between cores "
            f"but shall not adhere to them (IS 694 cl.8.1/19.1.4)")


def build_general_and_construction(profile: Optional[CableProfile], sample: Sample) -> List[dict]:
    """Two small Specified/Observed tables matching the docx's "General
    Requirements" (Section 1) and "Construction" (Section 2) tables. The
    "Specified" column here is the standard's own boilerplate requirement
    text (same for every cable of a given type -- not a numeric limit), so
    it's safe to state without engineering-data risk; "Observed" is what
    was actually entered for this sample's profile."""
    if not profile:
        return []

    core_colors = profile.tested_core_colors or []
    outer_parts = []
    if profile.has_armour:
        armour_bits = [profile.armour_type or "Armour"]
        if profile.armour_material:
            armour_bits.append(f"({profile.armour_material})")
        if profile.armour_strand_count:
            armour_bits.append(f"{profile.armour_strand_count} strands")
        outer_parts.append(" ".join(armour_bits))
    if profile.has_inner_sheath:
        outer_parts.append("inner sheath")
    if profile.has_outer_sheath:
        outer_parts.append(f"outer sheath, PVC Type {profile.sheath_type}" if profile.sheath_type else "outer sheath")
    outer_construction_observed = "; ".join(outer_parts) if outer_parts else "Unsheathed, unarmoured"

    general = {
        "label": "3. General Requirements (IS 694:2010, Section 1)",
        "rows": [
            {"label": "a. Conductor (Cl. 4.1)", "specified": _conductor_spec_text(profile.conductor_material),
             "observed": profile.conductor_material or "-"},
            {"label": "b. Insulation (Cl. 5.1/5.2)", "specified": _insulation_spec_text(profile.insulation_type),
             "observed": f"Type {profile.insulation_type}" + (f" ({profile.insulation_material})" if profile.insulation_material else "") if profile.insulation_type else "-"},
            {"label": "c. Sheath (Cl. 8.1)", "specified": _sheath_spec_text(profile.sheath_type),
             "observed": f"Type {profile.sheath_type}" if profile.sheath_type else "Unsheathed"},
        ],
    }
    construction = {
        "label": "4. Construction (IS 694:2010, Section 2, Cl.17)",
        "rows": [
            {"label": "a. Conductor Class (Cl.17.1.1)", "specified": f"Class {profile.conductor_class} (IS 8130)" if profile.conductor_class else "-",
             "observed": f"Class {profile.conductor_class}" if profile.conductor_class else "-"},
            {"label": "b. Area of Conductor (Cl.17.1.1.1)", "specified": f"{sample.csa_mm2} sq.mm (Nominal)",
             "observed": f"{sample.csa_mm2} sq.mm (Calculated)"},
            {"label": "c. Core Identification (Cl. 12)", "specified": "As per IS 694 Table 2 standard colour sequence",
             "observed": ", ".join(core_colors) if core_colors else "-"},
            {"label": "d. Outer Sheath / Armour (Cl. 19.1.4)", "specified": _sheath_spec_text(profile.sheath_type),
             "observed": outer_construction_observed},
        ],
    }
    return [general, construction]


def build_type_test_sections(db: Session, sample_id: str, clause_refs: Dict[str, str], only_enabled: bool = True) -> List[dict]:
    """The 'Test Report_694.docx' section a-d layout: grouped by
    TestDefinition.report_section, each row pivoted into Specified vs one
    column per tested core colour / Outer Sheath -- the exact same grouping
    the on-screen Calculation tab uses (CalculationMatrix.tsx), so the PDF
    and the live view can't structurally diverge."""
    q = db.query(AssignedTest).filter(AssignedTest.sample_id == sample_id)
    if only_enabled:
        q = q.filter(AssignedTest.enabled == True)  # noqa: E712
    assigned = q.all()

    by_section: Dict[str, List[AssignedTest]] = {}
    for at in assigned:
        td = at.test_definition
        sec = (td.report_section if td else None) or "OTHER"
        by_section.setdefault(sec, []).append(at)

    sections_out = []
    for sec_key in SECTION_ORDER:
        ats = by_section.get(sec_key)
        if not ats:
            continue
        by_test: Dict[str, List[AssignedTest]] = {}
        for at in ats:
            by_test.setdefault(at.test_id, []).append(at)
        test_ids = sorted(
            by_test.keys(),
            key=lambda tid: (by_test[tid][0].test_definition.sequence if by_test[tid][0].test_definition else 999),
        )
        positions_present = [p for p in POSITION_ORDER if any(a.core_position == p for a in ats)]
        has_whole = any(a.core_position is None for a in ats)

        rows = []
        for tid in test_ids:
            group = by_test[tid]
            td = group[0].test_definition
            name = td.name if td else tid
            unit = td.unit if td else ""
            values: Dict[str, dict] = {}
            specified_text = "-"
            for at in group:
                latest = (
                    db.query(TestRun).filter(TestRun.assigned_test_id == at.id)
                    .order_by(TestRun.attempt_number.desc()).first()
                )
                key = at.core_position or "WHOLE"
                if latest:
                    val = f"{latest.calculated_value} {latest.calculated_unit or ''}".strip() if latest.calculated_value is not None else "-"
                    values[key] = {"value": val, "result": latest.result}
                    if latest.limit_value is not None:
                        specified_text = f"{latest.limit_operator} {latest.limit_value} {unit}".strip()
                    elif latest.limit_source_kind == "PLACEHOLDER":
                        specified_text = "Pending verification"
                    elif latest.limit_source_kind == "MISSING":
                        specified_text = "No criterion authored"
                else:
                    values[key] = {"value": "-", "result": "PENDING"}
            rows.append({
                "name": name, "clause": clause_refs.get(tid, ""),
                "specified": specified_text, "values": values,
            })
        sections_out.append({
            "key": sec_key, "label": SECTION_LABELS[sec_key],
            "has_whole": has_whole, "positions": positions_present, "rows": rows,
        })
    return sections_out
