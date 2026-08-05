"""
Fills the ACTUAL Observation Sheet template (OBSERVATION SHEET FOR
694_2010_4 Core.docx) with a sample's own data -- same "edit the real
document's existing cells, never redesign" principle as
docx_report_filler.py, and shares its low-level cell-editing helpers.

Honest scope note (read before extending this file): this template is a
far more granular RAW data-recording form than Test Report_694.docx --
many of its rows are printed for individual specimen replicates (e.g. 4
separate breaking-load readings before a median, two separate T1/T2 hot-
deformation thickness readings per specimen, 8 timed smoke-density
readings) that CableLIMS does not currently capture at that granularity
(TestRun stores one accepted reading set per core/sheath position, not
each individual specimen that fed into it). Filling those cells would
mean guessing numbers we don't have -- not done here.

What IS filled, because the mapping to real captured data is direct and
verified against the template's actual merged-cell structure:
  - Header: type of cable, sample length, materials, construction
  - Conductor Resistance test block (observed resistance, sample length,
    room temperature, correction factor, calculated resistance)
  - Overall diameter, insulation thickness (avg/min), sheath thickness
    (avg/min)

Everything else in the template is left exactly as the blank form has
it -- there for the lab to fill by hand -- rather than populated with a
single aggregate value pretending to be the per-specimen breakdown the
form actually asks for.
"""
import os
import shutil
from typing import Optional

import docx
from sqlalchemy.orm import Session

from app.models.models import CableProfile, Sample
from app.services.docx_report_filler import (
    REPORT_DIR,
    _latest_run,
    _num,
    _set_cell_value,
)
from app.services.standards_service import standards_service

# Lives inside app/ (see docx_report_filler.py's TEMPLATE_PATH comment for
# why -- so package_for_handoff.ps1 includes it automatically).
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "report_templates", "OBSERVATION SHEET FOR 694_2010_4 Core.docx",
)

# Column groups within the Conductor-Resistance / Dimensions rows of
# Table 1, verified against the template's actual merged-cell boundaries
# (see cell-identity dump during development) -- consistently
# [3,4,5] / [6,7] / [8,9,10,11] / [12,13] across every value row in that
# block, matching the project's established Red/Yellow/Blue/Black order.
CORE_COL_FIRST_CELL = {"RED": 3, "YELLOW": 6, "BLUE": 8, "BLACK": 12}


def _append_after_label(cell, value: str):
    """For single-merged-cell form fields like '1. Type of cable' that
    have no separate blank cell -- adds the value as a new paragraph in
    the same cell rather than guessing at a colon/blank to overwrite."""
    if not value:
        return
    p = cell.add_paragraph()
    p.add_run(value)


def generate_filled_observation_sheet(db: Session, sample_id: str, output_name: str) -> str:
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Observation Sheet template not found at {TEMPLATE_PATH}")

    sample = db.query(Sample).filter(Sample.sample_id == sample_id).first()
    if not sample:
        raise ValueError(f"Sample {sample_id} not found")
    profile: Optional[CableProfile] = sample.profile

    out_path = os.path.join(REPORT_DIR, f"{output_name}_ObservationSheet.docx")
    shutil.copy(TEMPLATE_PATH, out_path)
    d = docx.Document(out_path)
    t = d.tables

    core_colors = (profile.tested_core_colors if profile else None) or []
    color_to_position = {c: c for c in core_colors}

    if profile:
        material = profile.conductor_material or "-"
        nomenclature = (
            f"PVC insulated, {'sheathed' if profile.has_outer_sheath else 'unsheathed'} "
            f"{sample.cores} core cable with {material} conductor, {profile.cable_shape or 'Round'}"
        )
        _append_after_label(t[0].rows[2].cells[0], nomenclature)
        _append_after_label(t[0].rows[3].cells[0], "As received (per registration)")
        _append_after_label(t[0].rows[10].cells[0], profile.construction or "-")

        # Materials block (rows 7-9): label | sub-label | BLANK value cell
        _set_cell_value(t[0].rows[7].cells[3], material)
        _set_cell_value(t[0].rows[8].cells[3], f"Type {profile.insulation_type} ({profile.insulation_material})" if profile.insulation_type else "-")
        _set_cell_value(t[0].rows[9].cells[3], f"Type {profile.sheath_type}" if profile.sheath_type else "Unsheathed")

    # -- Conductor Resistance (Table 1, rows 3-7) ----------------------------
    def cr_value(row_idx: int, field: str, decimals=None):
        for color, first_col in CORE_COL_FIRST_CELL.items():
            pos = color_to_position.get(color)
            if not pos:
                continue
            run = _latest_run(db, sample_id, "TEST-0001", pos)
            if not run:
                continue
            if field == "observed_mohm":
                val = run.raw_values.get("observed_resistance_mohm") if run.raw_values else None
            elif field == "length_m":
                val = run.raw_values.get("specimen_length_m") if run.raw_values else None
            elif field == "room_temp":
                val = run.raw_values.get("room_temperature_c") if run.raw_values else None
            elif field == "calculated":
                val = run.calculated_value
            elif field == "correction_factor":
                room_temp = run.raw_values.get("room_temperature_c") if run.raw_values else None
                val = standards_service.get_temperature_correction_factor(room_temp).value if room_temp is not None else None
            else:
                val = None
            _set_cell_value(t[1].rows[row_idx].cells[first_col], _num(val, decimals))

    cr_value(3, "observed_mohm", 3)
    cr_value(4, "length_m", 2)
    cr_value(5, "room_temp", 1)
    cr_value(6, "correction_factor", 4)  # kt = 250/(230+t) -- same pure function the calculation itself used
    cr_value(7, "calculated", 4)

    # -- Overall diameter (row 9, single merged value cell) ------------------
    if profile and profile.overall_diameter_mm is not None:
        _set_cell_value(t[1].rows[9].cells[0], f"Overall Diameter: {_num(profile.overall_diameter_mm, 2)} mm")

    # -- Insulation thickness avg/min (rows 14-15) ---------------------------
    def dim_value(row_idx: int, test_id: str, decimals=2):
        for color, first_col in CORE_COL_FIRST_CELL.items():
            pos = color_to_position.get(color)
            if not pos:
                continue
            run = _latest_run(db, sample_id, test_id, pos)
            if run and run.calculated_value is not None:
                _set_cell_value(t[1].rows[row_idx].cells[first_col], _num(run.calculated_value, decimals))

    dim_value(14, "TEST-0002")  # Average thickness -- our one reported value
    # Row 15 "Minimum thickness" -- same gap as the Certificate: our system
    # reports one already-min-checked thickness value, not separate
    # avg/min readings, so left blank rather than duplicated.

    # -- Sheath thickness avg/min (rows 18-19) -------------------------------
    sheath_run = _latest_run(db, sample_id, "TEST-0014", "SHEATH")
    if sheath_run and sheath_run.calculated_value is not None:
        _set_cell_value(t[1].rows[18].cells[2], _num(sheath_run.calculated_value, 2))

    d.save(out_path)
    return out_path
