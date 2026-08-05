"""
Fills the ACTUAL Test Report_694.docx template with a sample's own data --
per explicit instruction: do not redesign the report, do not write new
prose, only replace the value cells with this sample's calculated numbers,
leaving every label, clause reference, heading and static requirement
sentence in the template exactly as it is.

Approach: copy the template file, then edit specific existing paragraphs
by (table_index, row_index, col_index) coordinates that were hand-mapped
against the actual document (see report_templates/Test Report_694.docx).
Each edit only rewrites the text of the run(s) already holding a value in
that cell -- it never adds/removes rows, columns, or paragraphs, so the
template's structure and formatting are untouched.

Where this sample simply doesn't have the data point the template's
example sample happened to have (e.g. overall diameter, or an elevated-
temperature 70C insulation-resistance reading -- neither is a test in our
current catalog), the cell is blanked rather than left showing the
template's original (now-wrong, belongs-to-a-different-sample) numbers.
Never guessing a replacement value for a gap.
"""
import os
import re
import shutil
from typing import Optional

import docx
from sqlalchemy.orm import Session

from app.engines.result_utils import effective_result, get_accepted_run
from app.models.models import AssignedTest, CableProfile, Sample, TestRun

# Lives inside app/ (not up in the repo root) so
# it's included automatically by package_for_handoff.ps1, which copies
# backend/app/ wholesale -- a template path outside that folder would
# silently go missing from every handoff/update package.
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "report_templates", "Test Report_694.docx",
)

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "certificates")
REPORT_DIR = os.path.abspath(REPORT_DIR)
os.makedirs(REPORT_DIR, exist_ok=True)

CORE_LETTER = {"RED": "R", "YELLOW": "Y", "BLUE": "B", "BLACK": "Bk"}


def _format_sci(v) -> Optional[str]:
    """1e13 -> '1 x 10^13', matching the template's own convention for the
    very large/small resistivity limits (its own text just renders as
    "1 X 1012" once superscript formatting is lost in extraction -- this
    keeps the same information legible in plain text)."""
    if v is None:
        return None
    exp = 0
    val = float(v)
    if val != 0:
        import math
        exp = math.floor(math.log10(abs(val)))
    mantissa = val / (10 ** exp)
    if abs(mantissa - round(mantissa)) < 1e-9:
        mantissa_str = str(round(mantissa))
    else:
        mantissa_str = f"{mantissa:.2f}"
    return f"{mantissa_str} x 10^{exp}"


def _num(v, decimals=None) -> str:
    if v is None:
        return "-"
    if decimals is not None:
        try:
            return f"{float(v):.{decimals}f}"
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def _set_cell_paragraph_text(cell, para_index: int, text: str):
    """Rewrites only the run text of an existing paragraph in a cell --
    keeps every other paragraph, run, and the cell's own formatting
    (font, size, borders, column widths) exactly as the template has it."""
    paras = cell.paragraphs
    if para_index >= len(paras):
        return
    p = paras[para_index]
    if not p.runs:
        # No run to carry formatting from -- borrow the cell's last
        # non-empty paragraph's run formatting if one exists anywhere in
        # the cell, otherwise just add a plain run (rare: only affects
        # cells that were fully blank in the template already).
        p.add_run(text)
        return
    p.runs[0].text = text
    for r in p.runs[1:]:
        r.text = ""


def _set_cell_value(cell, text: str):
    """Value cells in this template don't follow one consistent paragraph
    position -- some hold their value in the LAST paragraph (leading blank
    paragraphs used for vertical spacing), others in the FIRST (trailing
    blank paragraph after). Finds whichever paragraph actually holds text
    today and replaces just that one; every other paragraph in the cell is
    explicitly cleared too, so no fragment of the old example's value can
    survive in an unexpected slot."""
    paras = cell.paragraphs
    if not paras:
        return
    value_idx = max(range(len(paras)), key=lambda i: len(paras[i].text)) if any(p.text for p in paras) else len(paras) - 1
    for i, p in enumerate(paras):
        if i == value_idx:
            _set_cell_paragraph_text(cell, i, text)
        else:
            for r in p.runs:
                r.text = ""


def _latest_run(db: Session, sample_id: str, test_id: str, position: Optional[str]) -> Optional[TestRun]:
    at = (
        db.query(AssignedTest)
        .filter(AssignedTest.sample_id == sample_id, AssignedTest.test_id == test_id,
                AssignedTest.core_position == position)
        .first()
    )
    if not at:
        return None
    # Despite the name (kept for the many call sites already using it), this
    # resolves the ACCEPTED attempt, not blindly the most recent one -- see
    # result_utils.get_accepted_run. A certificate must reflect a Scientist's
    # override, not silently revert to whatever was submitted most recently.
    return get_accepted_run(db, at)


def _extract_after_value(note: Optional[str]) -> Optional[str]:
    """Ageing tests only persist the before/after VARIATION percentage as
    calculated_value; the intermediate absolute after-ageing value (which
    the template shows on its own row, separate from the variation row)
    is still computed by the same formula and present in the run's note
    text -- extracted here rather than re-derived or guessed."""
    if not note:
        return None
    m = re.search(r"after=([\-\d.]+)", note)
    return m.group(1) if m else None


def _override_marker(run: Optional[TestRun]) -> str:
    """H9: a certificate must visibly flag a Scientist's overridden result
    -- silently showing the corrected number/verdict with no indication it
    differs from what the system itself computed would misrepresent the
    record's provenance. Never changes which value/verdict is shown, only
    appends a plain-text flag alongside it."""
    return " [OVERRIDDEN]" if run and run.overridden else ""


def _undetermined_marker(run: Optional[TestRun]) -> str:
    """H9: an UNDETERMINED numeric result must not look identical to a
    clean PASS/FAIL value on the printed certificate -- the guard-band/
    placeholder/missing-limit ambiguity that produced it must stay
    visible. Skipped when the run was overridden: an override means a
    Scientist has already resolved the ambiguity, so _override_marker
    alone is the correct (and non-redundant) flag."""
    if run and not run.overridden and effective_result(run) == "UNDETERMINED":
        return " [UNDETERMINED]"
    return ""


def _placeholder_suffix(run: Optional[TestRun]) -> str:
    """H9: a limit sourced from an unverified Standards Knowledge Base
    placeholder (limit_source_kind == "PLACEHOLDER") must not display
    identically to a verified one -- the certificate is the one place a
    Scientist reviewing it later has no other way to know the limit itself
    was never confirmed against the actual standard text."""
    return " [PLACEHOLDER LIMIT]" if run and run.limit_source_kind == "PLACEHOLDER" else ""


def _qualitative_text(run: Optional[TestRun], pass_text: str, fail_text: str) -> str:
    result = effective_result(run)
    if not run or result is None:
        return "-"
    if result == "PASS":
        return pass_text + _override_marker(run)
    if result == "FAIL":
        return fail_text + _override_marker(run)
    return "Result pending Scientist review"


def generate_filled_report_docx(db: Session, sample_id: str, output_name: str) -> str:
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Report template not found at {TEMPLATE_PATH}")

    sample = db.query(Sample).filter(Sample.sample_id == sample_id).first()
    if not sample:
        raise ValueError(f"Sample {sample_id} not found")
    profile: Optional[CableProfile] = sample.profile

    out_path = os.path.join(REPORT_DIR, f"{output_name}.docx")
    shutil.copy(TEMPLATE_PATH, out_path)
    d = docx.Document(out_path)

    core_colors = (profile.tested_core_colors if profile else None) or []
    # Which physical core, if any, is currently assigned to each of the
    # template's fixed Red/Yellow/Blue/Black columns.
    color_to_position = {c: c for c in core_colors}  # our positions ARE the colour names (RED/YELLOW/...)

    def core_value(test_id: str, color_key: str, decimals=None) -> str:
        pos = color_to_position.get(color_key)
        if not pos:
            return "-"
        run = _latest_run(db, sample_id, test_id, pos)
        return _num(run.calculated_value if run else None, decimals) + _override_marker(run) + _undetermined_marker(run)

    def sheath_value(test_id: str, decimals=None) -> str:
        run = _latest_run(db, sample_id, test_id, "SHEATH")
        return _num(run.calculated_value if run else None, decimals) + _override_marker(run) + _undetermined_marker(run)

    def whole_value(test_id: str, decimals=None) -> str:
        run = _latest_run(db, sample_id, test_id, None)
        return _num(run.calculated_value if run else None, decimals) + _override_marker(run) + _undetermined_marker(run)

    t = d.tables

    # -- General Requirements (Table 0) --------------------------------------
    if profile:
        _set_cell_value(t[0].rows[1].cells[1], profile.conductor_material or "-")
        _set_cell_value(t[0].rows[1].cells[2], profile.conductor_material or "-")
        _set_cell_paragraph_text(t[0].rows[2].cells[1], 0, f"PVC Type {profile.insulation_type}" if profile.insulation_type else "-")
        _set_cell_paragraph_text(t[0].rows[2].cells[2], 0, f"Type {profile.insulation_type}" if profile.insulation_type else "-")
        _set_cell_value(t[0].rows[3].cells[1], f"PVC Type {profile.sheath_type}" if profile.sheath_type else "Unsheathed")
        _set_cell_value(t[0].rows[3].cells[2], f"Type {profile.sheath_type}" if profile.sheath_type else "Unsheathed")

        # -- Construction (Table 0 rows 5-6, Table 1 rows 1-3) -----------------
        _set_cell_value(t[0].rows[5].cells[1], f"Class {profile.conductor_class} Conductor" if profile.conductor_class else "-")
        _set_cell_value(t[0].rows[5].cells[2], f"Class {profile.conductor_class} Conductor" if profile.conductor_class else "-")
        _set_cell_value(t[0].rows[6].cells[1], f"{sample.csa_mm2} sq.mm. (Nominal)")
        _set_cell_value(t[0].rows[6].cells[2], f"{sample.csa_mm2} sq.mm (Calculated)")

        _set_cell_value(t[1].rows[2].cells[4], ", ".join(core_colors) if core_colors else "-")
        _set_cell_value(t[1].rows[2].cells[5], ", ".join(core_colors) if core_colors else "-")

    # -- a. Test on Conductor (Table 1) --------------------------------------
    run_r1 = _latest_run(db, sample_id, "TEST-0001", "RED") or _latest_run(db, sample_id, "TEST-0001", core_colors[0] if core_colors else None)
    limit_r1 = f"{run_r1.limit_operator} {run_r1.limit_value} (Max){_placeholder_suffix(run_r1)}" if run_r1 and run_r1.limit_value is not None else "-"
    _set_cell_value(t[1].rows[6].cells[2], limit_r1)
    _set_cell_value(t[1].rows[6].cells[3], core_value("TEST-0001", "RED", 3))
    _set_cell_value(t[1].rows[6].cells[4], core_value("TEST-0001", "YELLOW", 3))
    _set_cell_value(t[1].rows[6].cells[5], core_value("TEST-0001", "BLUE", 3))
    _set_cell_value(t[1].rows[6].cells[6], core_value("TEST-0001", "BLACK", 3))

    # -- b. Overall dimensions & thickness (Table 1) -------------------------
    ins_run = _latest_run(db, sample_id, "TEST-0002", "RED") or _latest_run(db, sample_id, "TEST-0002", core_colors[0] if core_colors else None)
    ins_limit = f"{ins_run.limit_value} (Nominal){_placeholder_suffix(ins_run)}" if ins_run and ins_run.limit_value is not None else "-"
    _set_cell_value(t[1].rows[8].cells[2], ins_limit)
    _set_cell_value(t[1].rows[8].cells[3], core_value("TEST-0002", "RED", 2))
    _set_cell_value(t[1].rows[8].cells[4], core_value("TEST-0002", "YELLOW", 2))
    _set_cell_value(t[1].rows[8].cells[5], core_value("TEST-0002", "BLUE", 2))
    _set_cell_value(t[1].rows[8].cells[6], core_value("TEST-0002", "BLACK", 2))
    # Template's row 9 is a separate MIN-thickness line -- our system reports
    # one thickness result per core (already min-checked internally), so a
    # second independent reading doesn't exist to show here. All 5 cells
    # (limit + Red/Yellow/Blue/Black) held the old example's own numbers
    # and must be cleared, not just the ones a first pass happened to check.
    for c in [2, 3, 4, 5, 6]:
        _set_cell_value(t[1].rows[9].cells[c], "-")
    # Overall diameter: now captured during profiling (OD, measured with
    # calipers) -- shown when present. The Max Overall Diameter LIMIT from
    # IS 694 Table 5 hasn't been extracted into the SKB yet (only that
    # table's insulation/sheath-thickness columns were), so the limit cell
    # stays "-" rather than guessed -- a real, separate, disclosed gap.
    _set_cell_value(t[1].rows[10].cells[2], "-")
    _set_cell_value(t[1].rows[10].cells[4], _num(profile.overall_diameter_mm, 2) if profile and profile.overall_diameter_mm is not None else "-")

    sheath_th_run = _latest_run(db, sample_id, "TEST-0014", "SHEATH")
    sheath_limit = f"{sheath_th_run.limit_value} (Nominal){_placeholder_suffix(sheath_th_run)}" if sheath_th_run and sheath_th_run.limit_value is not None else "-"
    _set_cell_value(t[1].rows[11].cells[2], sheath_limit)
    _set_cell_value(t[1].rows[11].cells[4], sheath_value("TEST-0014", 2))
    # Template's row 12 (minimum sheath thickness) -- same "no separate
    # min reading" gap as row 9 above.
    _set_cell_value(t[1].rows[12].cells[2], "-")
    _set_cell_value(t[1].rows[12].cells[4], "-")

    # -- c. Physical Test on Insulation (and Sheath) (Table 2) ---------------
    def fill_physical_row(row_idx, test_id, decimals, limit_suffix):
        run = _latest_run(db, sample_id, test_id, "RED") or (_latest_run(db, sample_id, test_id, core_colors[0]) if core_colors else None)
        limit = f"{run.limit_value} {limit_suffix}{_placeholder_suffix(run)}" if run and run.limit_value is not None else "-"
        _set_cell_value(t[2].rows[row_idx].cells[1], limit)
        _set_cell_value(t[2].rows[row_idx].cells[2], core_value(test_id, "RED", decimals))
        _set_cell_value(t[2].rows[row_idx].cells[3], core_value(test_id, "YELLOW", decimals))
        _set_cell_value(t[2].rows[row_idx].cells[4], core_value(test_id, "BLUE", decimals))
        _set_cell_value(t[2].rows[row_idx].cells[5], core_value(test_id, "BLACK", decimals))
        _set_cell_value(t[2].rows[row_idx].cells[6], sheath_value(test_id, decimals))

    fill_physical_row(4, "TEST-0003", 2, "(Min)")
    fill_physical_row(5, "TEST-0004", 0, "(Min)")
    fill_physical_row(6, "TEST-0017", 2, "(Max)")

    # Ageing: absolute after-ageing values on rows 8/9 (extracted from the
    # note -- see _extract_after_value), variation % on rows 10/11.
    def fill_ageing_after(row_idx, test_id, base_test_id, decimals):
        for i, color in enumerate(["RED", "YELLOW", "BLUE", "BLACK"]):
            pos = color_to_position.get(color)
            run = _latest_run(db, sample_id, test_id, pos) if pos else None
            val = _extract_after_value(run.result_explanation if run else None) if run else None
            _set_cell_value(t[2].rows[row_idx].cells[2 + i], val or "-")
        sheath_run = _latest_run(db, sample_id, test_id, "SHEATH")
        sheath_val = _extract_after_value(sheath_run.result_explanation if sheath_run else None) if sheath_run else None
        _set_cell_value(t[2].rows[row_idx].cells[6], sheath_val or "-")
        # Same base (not-after-ageing) minimum applies -- the ageing test
        # only adds a separate limit on the % swing, checked on the rows below.
        base_limit_run = _latest_run(db, sample_id, base_test_id, "RED") or (_latest_run(db, sample_id, base_test_id, core_colors[0]) if core_colors else None)
        _set_cell_value(
            t[2].rows[row_idx].cells[1],
            _num(base_limit_run.limit_value, decimals) + " (Min)" + _placeholder_suffix(base_limit_run)
            if base_limit_run and base_limit_run.limit_value is not None else "-",
        )

    fill_ageing_after(8, "TEST-0015", "TEST-0003", 2)
    fill_ageing_after(9, "TEST-0016", "TEST-0004", 0)
    fill_physical_row(10, "TEST-0015", 2, "(Max)")
    fill_physical_row(11, "TEST-0016", 2, "(Max)")
    fill_physical_row(12, "TEST-0018", 2, "(Max)")

    # Heat shock -- qualitative. NOTE: in the template, cells 2-5 (Red/
    # Yellow/Blue/Black) on this row are ONE merged cell (confirmed via
    # cell._tc identity), not four independent ones -- writing different
    # per-core text there would silently overwrite itself. One combined
    # statement is written instead, matching the template's own layout;
    # the Specified-column cell (index 1) is left untouched.
    hs_pass = "Satisfactory as no signs of scales or cracks observed"
    hs_fail = "Cracks or scales observed"
    hs_runs = [
        _latest_run(db, sample_id, "TEST-0019", color_to_position[color])
        for color in ["RED", "YELLOW", "BLUE", "BLACK"] if color in color_to_position
    ]
    if any(r and effective_result(r) == "FAIL" for r in hs_runs):
        hs_combined = hs_fail
    elif hs_runs and all(r and effective_result(r) == "PASS" for r in hs_runs):
        hs_combined = hs_pass
    elif any(r for r in hs_runs):
        hs_combined = "Result pending Scientist review"
    else:
        hs_combined = "-"
    # H9: this cell combines 4 independent runs (RED/YELLOW/BLUE/BLACK)
    # into one merged-cell statement -- if any one of them was overridden,
    # that must still be visible even though the statement itself can't
    # say which specific core it was (the per-core detail already exists
    # in the API's "View Details" tab, this is just the certificate flag).
    if any(r and r.overridden for r in hs_runs):
        hs_combined += " [INCLUDES AN OVERRIDDEN RESULT]"
    _set_cell_value(t[2].rows[13].cells[2], hs_combined)
    hs_sheath_run = _latest_run(db, sample_id, "TEST-0019", "SHEATH")
    _set_cell_value(t[2].rows[13].cells[6], _qualitative_text(hs_sheath_run, hs_pass, hs_fail))

    fill_physical_row(15, "TEST-0020", 0, "(Max)")

    # Thermal stability -- the template's limit cell has TWO lines (separate
    # insulation vs sheath minutes), not one, so it needs its own paragraph-
    # level writes rather than the generic single-value helper above.
    ins_ts_run = _latest_run(db, sample_id, "TEST-0021", "RED") or (_latest_run(db, sample_id, "TEST-0021", core_colors[0]) if core_colors else None)
    sheath_ts_run = _latest_run(db, sample_id, "TEST-0021", "SHEATH")
    _set_cell_paragraph_text(
        t[2].rows[16].cells[1], 0,
        f"For insulation {_num(ins_ts_run.limit_value, 0)}(Min){_placeholder_suffix(ins_ts_run)}"
        if ins_ts_run and ins_ts_run.limit_value is not None else "For insulation -",
    )
    _set_cell_paragraph_text(
        t[2].rows[16].cells[1], 1,
        f"For sheath {_num(sheath_ts_run.limit_value, 0)}(Min){_placeholder_suffix(sheath_ts_run)}"
        if sheath_ts_run and sheath_ts_run.limit_value is not None else "For sheath -",
    )
    _set_cell_value(t[2].rows[16].cells[2], core_value("TEST-0021", "RED", 0))
    _set_cell_value(t[2].rows[16].cells[3], core_value("TEST-0021", "YELLOW", 0))
    _set_cell_value(t[2].rows[16].cells[4], core_value("TEST-0021", "BLUE", 0))
    _set_cell_value(t[2].rows[16].cells[5], core_value("TEST-0021", "BLACK", 0))
    _set_cell_value(t[2].rows[16].cells[6], sheath_value("TEST-0021", 0))

    # -- viii. Flammability / fire performance (Table 3) -- FR/FR-LSH only ---
    fire_tested = bool(profile and profile.fire_category in ("FR", "FR-LSH"))
    if fire_tested:
        burn_run = whole_value("TEST-0023", 0)
        unaff_run = whole_value("TEST-0024", 0)
        _set_cell_value(t[3].rows[1].cells[2], burn_run)
        _set_cell_value(t[3].rows[2].cells[2], unaff_run)
        _set_cell_value(t[3].rows[3].cells[2], whole_value("TEST-0008", 1))
        _set_cell_value(t[3].rows[4].cells[2], whole_value("TEST-0009", 1))
        _set_cell_value(t[3].rows[5].cells[2], whole_value("TEST-0010", 0))
        _set_cell_value(t[3].rows[6].cells[2], whole_value("TEST-0022", 0))
    else:
        for r in [1, 2, 3, 4, 5, 6]:
            _set_cell_value(t[3].rows[r].cells[2], "N/A (fire category " + (profile.fire_category if profile else "-") + ")")

    # -- d. Test on Completed Cable (Table 3 + Table 4) ----------------------
    hv_wi_run = _latest_run(db, sample_id, "TEST-0025", None)
    hv_wi_text = _qualitative_text(hv_wi_run, "The cable withstood the test satisfactorily", "Breakdown/flashover observed")
    _set_cell_value(t[3].rows[10].cells[2], hv_wi_text)
    _set_cell_value(t[3].rows[11].cells[2], hv_wi_text)
    _set_cell_value(t[3].rows[13].cells[2], hv_wi_text)

    # Insulation resistance (volume resistivity + IR constant) -- room temp only;
    # our catalog doesn't include an elevated-temperature (70C) variant.
    for i, color in enumerate(["RED", "YELLOW", "BLUE", "BLACK"]):
        pos = color_to_position.get(color)
        vr_run = _latest_run(db, sample_id, "TEST-0006", pos) if pos else None
        vr_text = (
            _format_sci(vr_run.calculated_value) + _override_marker(vr_run) + _undetermined_marker(vr_run)
            if vr_run and vr_run.calculated_value is not None else "-"
        )
        _set_cell_value(t[4].rows[3].cells[2 + i], vr_text)
        _set_cell_value(t[4].rows[4].cells[2 + i], "-")  # 70C -- not captured
        _set_cell_value(t[4].rows[6].cells[2 + i], core_value("TEST-0028", color, 5))
        _set_cell_value(t[4].rows[7].cells[2 + i], "-")  # 70C -- not captured

    vr_limit_run = _latest_run(db, sample_id, "TEST-0006", "RED") or (_latest_run(db, sample_id, "TEST-0006", core_colors[0]) if core_colors else None)
    vr_sci = _format_sci(vr_limit_run.limit_value) if vr_limit_run and vr_limit_run.limit_value else None
    _set_cell_value(t[4].rows[3].cells[1], f"{vr_sci} (Min){_placeholder_suffix(vr_limit_run)}" if vr_sci else "-")
    irc_limit_run = _latest_run(db, sample_id, "TEST-0028", "RED") or (_latest_run(db, sample_id, "TEST-0028", core_colors[0]) if core_colors else None)
    _set_cell_value(
        t[4].rows[6].cells[1],
        f"{irc_limit_run.limit_value} (Min){_placeholder_suffix(irc_limit_run)}"
        if irc_limit_run and irc_limit_run.limit_value is not None else "-",
    )

    hv_room_run = _latest_run(db, sample_id, "TEST-0005", None)
    hv_room_text = _qualitative_text(hv_room_run, "The cable withstood the test satisfactorily", "Breakdown/flashover observed")
    for c in range(2, 6):
        _set_cell_value(t[4].rows[9].cells[c], hv_room_text)

    # -- Description of the sample (header paragraphs) -----------------------
    if profile:
        cores = sample.cores or 0
        sheathed = "sheathed" if profile.has_outer_sheath else "unsheathed"
        material = profile.conductor_material or "-"
        fire_cat_text = profile.fire_category or "-"
        conductor_class_text = f"Class {profile.conductor_class}" if profile.conductor_class else "-"
        nomenclature = (
            f"PVC insulated, {sheathed} {cores} core cable with flexible {material} conductor "
            f"for general purpose, {conductor_class_text} cat {fire_cat_text}."
        )
        _replace_paragraph_after_label(d.paragraphs[4], "Nomenclature", nomenclature)
        # The template's Nomenclature runs on to a second free paragraph
        # (no separate label) -- clear it since our one-sentence version
        # above doesn't need a continuation line.
        _clear_paragraph(d.paragraphs[5])
        _replace_paragraph_after_label(d.paragraphs[6], "Size", f"{cores} Core X {sample.csa_mm2} mm2")
        # Quantity and Markings aren't captured anywhere in CableLIMS today
        # (no "number of coils" field; marking-photo OCR is not implemented)
        # -- left as an explicit gap rather than invented.
        _replace_paragraph_after_label(d.paragraphs[7], "Quantity", "Not recorded")
        _replace_paragraph_after_label(d.paragraphs[8], "Markings", "Not recorded (marking photo on file, not yet transcribed)")
        _clear_paragraph(d.paragraphs[9])

    d.save(out_path)
    return out_path


def _clear_paragraph(p):
    for r in p.runs:
        r.text = ""


def _replace_paragraph_after_label(p, label: str, value: str):
    """The template's description lines are 'Label<tab>: value...' spread
    across many runs. Keeps every run up to and including the ':' run
    (preserving the label text and tab formatting exactly), replaces the
    first following run with the new value, and blanks any further runs
    that held the old value's remaining words."""
    colon_idx = None
    for i, r in enumerate(p.runs):
        if ":" in r.text:
            colon_idx = i
            break
    if colon_idx is None:
        return
    remaining = p.runs[colon_idx + 1:]
    if not remaining:
        p.add_run(" " + value)
        return
    remaining[0].text = " " + value
    for r in remaining[1:]:
        r.text = ""
