"""
Standards Knowledge Base -- SEED DATA.

*** THIS FILE IS THE ONLY PLACE ENGINEERING NUMBERS LIVE. ***

Per CableLIMS_SDD_v2.md section 4.3, engineering values must never be
hardcoded in application/engine code or pasted into the CableLIMS workbook.
This module stands in for a real Standards Knowledge Base -- every value
below is tagged VERIFIED or PLACEHOLDER so the rest of the application can
treat them honestly, and the whole file is designed to be replaced by an
Excel-Import-Engine-backed SQLite table (Sprint Priority 2) with zero
changes to any caller (see standards_service.py, the only module that reads
this file).

Sources, in order of authority:
  1. Direct PDF reads of the actual BIS standards (IS 694, IS 8130) --
     tagged VERIFIED with exact clause/table citations.
  2. CTL's own internal engineering-limits reference table (the "BIS" sheet
     of Calculations.xlsx, a real, completed IS 694 4-core test worksheet
     supplied by CTL) -- tagged VERIFIED_CTL, since this is CTL's own
     working reference used to certify real samples, cross-referenced
     against (1) wherever they overlap (they agree). Reproduced exactly;
     no value here was inferred or rounded by the assistant.
  3. Values CTL's own source left blank, or that could not be reconciled
     with confidence -- tagged MISSING or PENDING_VERIFICATION and never
     silently invented. See CableLIMS_SDD_v2.md's "never guess" principle.

A PLACEHOLDER/MISSING/PENDING_VERIFICATION value must never back an
automatic PASS/FAIL -- confidence_engine.py forces all of these to
REVIEW_REQUIRED/UNDETERMINED.
"""

# ---------------------------------------------------------------------------
# VERIFIED: IS 8130:2013 Tables 1/2/3/4 -- max conductor resistance at 20 degC,
# by conductor CLASS, nominal CSA, and material. Each class has its own table
# (they are NOT interchangeable -- a Class 5/6 flexible conductor has a
# materially higher max resistance than Class 1/2 at the same CSA, since more,
# thinner strands with more air gap between them means slightly less
# conductive cross-section for the same nominal CSA rating).
#
# Re-verified directly against 8130.pdf page images (not text extraction --
# this table's layout defeats naive text linearization) on 2026-07-30, after
# a reported CSA=2.5mm2 Class 5 case (7.41 vs the correct 7.98 ohm/km)
# revealed the app had only ever encoded Table 2 (Class 2) and applied it to
# every conductor class regardless of what was actually selected.
#
# Table 1 (Class 1, solid) -- clauses 6.1.1, 7.3.1
# Table 2 (Class 2, stranded) -- clauses 6.2.3, 6.3.3, 7.3.1
# Table 3 (Class 5, flexible) -- clauses 6.4.3, 7.3.1 (copper only -- flexible
#   cords/cables are not made with aluminium conductors)
# Table 4 (Class 6, flexible, finer strands than Class 5) -- clauses 6.4.3,
#   7.3.1 (copper only; resistance values are identical to Class 5 at every
#   CSA -- class only changes strand count/diameter, not conductive area)
#
# Units: ohm/km. "plain" = uncoated wire (the common case; used by this app).
# ---------------------------------------------------------------------------
IS8130_RESISTANCE_OHM_PER_KM = {
    "1": {  # Table 1: Solid Conductors
        0.5: {"copper_plain": 36.0, "aluminium": None},
        0.75: {"copper_plain": 24.5, "aluminium": None},
        1: {"copper_plain": 18.1, "aluminium": None},
        1.5: {"copper_plain": 12.1, "aluminium": None},
        2.5: {"copper_plain": 7.41, "aluminium": None},
        4: {"copper_plain": 4.61, "aluminium": None},
        6: {"copper_plain": 3.08, "aluminium": None},
        10: {"copper_plain": 1.83, "aluminium": 3.08},
        16: {"copper_plain": 1.15, "aluminium": 1.91},
        25: {"copper_plain": 0.727, "aluminium": 1.20},
        35: {"copper_plain": 0.524, "aluminium": 0.868},
        50: {"copper_plain": 0.387, "aluminium": 0.641},
        70: {"copper_plain": 0.268, "aluminium": 0.443},
        95: {"copper_plain": 0.193, "aluminium": 0.320},
        120: {"copper_plain": 0.153, "aluminium": 0.253},
    },
    "2": {  # Table 2: Stranded Conductors
        1: {"copper_plain": 18.1, "aluminium": None},
        1.5: {"copper_plain": 12.1, "aluminium": 18.1},
        2.5: {"copper_plain": 7.41, "aluminium": 12.1},
        4: {"copper_plain": 4.61, "aluminium": 7.41},
        6: {"copper_plain": 3.08, "aluminium": 4.61},
        10: {"copper_plain": 1.83, "aluminium": 3.08},
        16: {"copper_plain": 1.15, "aluminium": 1.91},
        25: {"copper_plain": 0.727, "aluminium": 1.20},
        35: {"copper_plain": 0.524, "aluminium": 0.868},
        50: {"copper_plain": 0.387, "aluminium": 0.641},
        70: {"copper_plain": 0.268, "aluminium": 0.443},
        95: {"copper_plain": 0.193, "aluminium": 0.320},
        120: {"copper_plain": 0.153, "aluminium": 0.253},
    },
    "5": {  # Table 3: Flexible Copper Conductors (Class 5) -- copper only
        0.5: {"copper_plain": 39.0, "aluminium": None},
        0.75: {"copper_plain": 26.0, "aluminium": None},
        1: {"copper_plain": 19.5, "aluminium": None},
        1.5: {"copper_plain": 13.3, "aluminium": None},
        2.5: {"copper_plain": 7.98, "aluminium": None},
        4: {"copper_plain": 4.95, "aluminium": None},
        6: {"copper_plain": 3.30, "aluminium": None},
        10: {"copper_plain": 1.91, "aluminium": None},
        16: {"copper_plain": 1.21, "aluminium": None},
        25: {"copper_plain": 0.780, "aluminium": None},
        35: {"copper_plain": 0.554, "aluminium": None},
        50: {"copper_plain": 0.386, "aluminium": None},
        70: {"copper_plain": 0.272, "aluminium": None},
        95: {"copper_plain": 0.206, "aluminium": None},
        120: {"copper_plain": 0.161, "aluminium": None},
    },
    "6": {  # Table 4: Flexible Copper Conductors (Class 6) -- copper only
        0.5: {"copper_plain": 39.0, "aluminium": None},
        0.75: {"copper_plain": 26.0, "aluminium": None},
        1: {"copper_plain": 19.5, "aluminium": None},
        1.5: {"copper_plain": 13.3, "aluminium": None},
        2.5: {"copper_plain": 7.98, "aluminium": None},
        4: {"copper_plain": 4.95, "aluminium": None},
        6: {"copper_plain": 3.30, "aluminium": None},
        10: {"copper_plain": 1.91, "aluminium": None},
        16: {"copper_plain": 1.21, "aluminium": None},
        25: {"copper_plain": 0.780, "aluminium": None},
        35: {"copper_plain": 0.554, "aluminium": None},
        50: {"copper_plain": 0.386, "aluminium": None},
        70: {"copper_plain": 0.272, "aluminium": None},
        95: {"copper_plain": 0.206, "aluminium": None},
        120: {"copper_plain": 0.161, "aluminium": None},
    },
}
IS8130_TABLE2_SOURCE = "IS 8130:2013, Table 2 (clauses 6.2.3, 6.3.3, 7.3.1)"
IS8130_RESISTANCE_SOURCE_BY_CLASS = {
    "1": "IS 8130:2013, Table 1 (clauses 6.1.1, 7.3.1)",
    "2": "IS 8130:2013, Table 2 (clauses 6.2.3, 6.3.3, 7.3.1)",
    "5": "IS 8130:2013, Table 3 (clauses 6.4.3, 7.3.1)",
    "6": "IS 8130:2013, Table 4 (clauses 6.4.3, 7.3.1)",
}

# ---------------------------------------------------------------------------
# VERIFIED: IS 8130:2013, Table 6 -- temperature correction factor kt to
# correct measured resistance at t degC to 20 degC. Formula confirmed in
# clause text: kt = 250 / (230 + t).
#
# NOTE: CTL's own worked example (Calculations.xlsx, per-core sheets) uses a
# DIFFERENT, simpler correction: k = 1 / (1 + 0.004*(RoomTemp-20)). Both are
# standard resistance-temperature-correction forms (0.004/degC is the
# nominal copper temperature coefficient); the app implements the IS
# 8130-cited kt formula as the VERIFIED path since it's the one the actual
# standard's clause text specifies, and exposes CTL's alternate as a
# secondary reference in calculation_engine.py's docstring rather than a
# second source of truth. If CTL's lab practice is to use their own
# worksheet formula specifically, flag this to reconcile explicitly.
# ---------------------------------------------------------------------------
def is8130_table6_kt(temp_c: float) -> float:
    return 250.0 / (230.0 + temp_c)

IS8130_TABLE6_SOURCE = "IS 8130:2013, Table 6 (clause 7.3), formula kt = 250/(230+t)"

# ---------------------------------------------------------------------------
# VERIFIED: IS 8130-derived conductor class rules (workbook 18_CONDUCTOR_RULES
# migration, see prior SDD work).
# ---------------------------------------------------------------------------
IS8130_ALLOWED_CONDUCTOR_CLASSES = [
    {"csa_values": [1, 1.5, 2.5], "material": "Copper", "classes": [2, 5]},
    {"csa_values": [1.5, 2.5, 4, 6, 10], "material": "Aluminium", "classes": [1, 2]},
    {"csa_values": "gt10", "material": "Aluminium", "classes": [2]},
]
CONDUCTOR_RULES_SOURCE = "IS 8130 (Amendment 3 rules, via workbook 18_CONDUCTOR_RULES)"

# ---------------------------------------------------------------------------
# VERIFIED: IS 8130:2013 -- Annealing test (copper, before stranding)
# elongation-by-wire-diameter bands (clause 7.1.2.1), and aluminium
# tensile-strength-by-grade bands (clause 4.1, 3.1). Read directly from
# 8130.pdf during the original architecture review.
# "After stranding" annealing elongation limit is explicitly "Under
# consideration" in IS 8130 itself -- confirmed independently in CTL's own
# BIS reference sheet, which uses the identical phrase. This is a genuine,
# standard-acknowledged gap, not an extraction failure -- always MISSING.
# ---------------------------------------------------------------------------
IS8130_ANNEALING_ELONGATION_MIN_PCT_BY_WIRE_DIA = [
    # (over_mm, up_to_and_incl_mm, elongation_min_pct)
    (None, 0.21, 9.0),
    (0.21, 0.41, 13.5),
    (0.41, 1.36, 18.0),
    (1.36, None, 22.5),
]
IS8130_ANNEALING_SOURCE = "IS 8130:2013, clause 7.1.2.1 (method: IS 10810 Part 1)"

IS8130_ALUMINIUM_TENSILE_GRADE_BANDS_MPA = {
    # before stranding, N/mm^2 (clause 4.1 / 3.1)
    "before_stranding": [
        (None, 100, "Grade 0"),
        (100, 150, "Grade H2"),
        (150, None, "Grade H4"),
    ],
    # after stranding: not less than 95% of the before-stranding minimum (clause 7.2.1(b))
    "after_stranding_pct_of_before": 95.0,
}
IS8130_ALUMINIUM_TENSILE_SOURCE = "IS 8130:2013, clause 7.2.1 / 4.1 (method: IS 10810 Part 2)"
IS8130_WRAPPING_SOURCE = "IS 8130:2013, clause 6.2.2 (method: IS 10810 Part 3) -- qualitative: wire shall not break"

# ---------------------------------------------------------------------------
# VERIFIED: IS 694:2010 (as amended by Amendment 3, 2015), Table 5 --
# nominal insulation thickness by CSA. Units: mm.
# ---------------------------------------------------------------------------
IS694_TABLE5_INSULATION_THICKNESS_MM = {
    1: 0.6, 1.5: 0.7, 2.5: 0.8, 4: 0.8, 6: 0.8,
    10: 1.0, 16: 1.0, 25: 1.2, 35: 1.2, 50: 1.4, 70: 1.4, 95: 1.6, 120: 1.6,
}
IS694_TABLE5_SOURCE = "IS 694:2010, Table 5 (as substituted by Amendment No. 3, July 2015) -- 'PVC Insulated " \
                       "Circular Sheathed Cables for Fixed Wiring (Circular)', clauses 18.1.2/18.1.4/18.1.6"

# Insulation thickness tolerance rule, IS 694 clause 5.3 (per Amendment 3 text,
# verified directly from the PDF, page-image read):
#   mean of readings must be >= nominal (ti)
#   smallest single reading must be >= ti - (0.1 + 0.1*ti)
IS694_CLAUSE_8_3_SOURCE = "IS 694:2010, clause 5.3 (insulation tolerance -- 0.1 + 0.1*ti)"

# ---------------------------------------------------------------------------
# VERIFIED (second-pass, page-image read of the actual PDF, including the
# Amendment No. 3 substitution page): Table 5's sheath-thickness (ts) columns
# are keyed by BOTH CSA and core count (Single/Two/Three/Four Core), not by
# CSA alone -- a materially different shape than first assumed. The prior
# single data point (CSA=70, sourced from a CTL worked example) has been
# DROPPED and replaced by this verified table, because the worked example's
# own number (1.88mm minimum) turned out to be computed with the wrong
# tolerance coefficient (see IS694_CLAUSE_ts_TOLERANCE_SOURCE below) --
# using the standard's own text is more reliable than re-deriving from a
# secondary worked example that itself contained an error.
# "-" (present in the source table at 70/95/120 mm^2, Two Core) means that
# combination is not tabulated in this construction, not a data gap.
# ---------------------------------------------------------------------------
IS694_SHEATH_THICKNESS_NOMINAL_MM = {
    # csa_mm2: {core_count: ts_nominal_mm}
    1: {1: 1.1, 2: 1.2, 3: 1.2, 4: 1.2},
    1.5: {1: 1.1, 2: 1.2, 3: 1.2, 4: 1.3},
    2.5: {1: 1.1, 2: 1.3, 3: 1.3, 4: 1.3},
    4: {1: 1.2, 2: 1.3, 3: 1.3, 4: 1.4},
    6: {1: 1.2, 2: 1.4, 3: 1.4, 4: 1.4},
    10: {1: 1.2, 2: 1.5, 3: 1.5, 4: 1.6},
    16: {1: 1.3, 2: 1.5, 3: 1.6, 4: 1.6},
    25: {1: 1.3, 2: 1.6, 3: 1.7, 4: 1.8},
    35: {1: 1.4, 2: 1.7, 3: 1.8, 4: 1.9},
    50: {1: 1.4, 2: 1.9, 3: 1.9, 4: 2.0},
    70: {1: 1.5, 3: 2.0, 4: 2.2},          # Two Core not tabulated at this CSA
    95: {1: 1.5, 3: 2.2, 4: 2.3},          # Two Core not tabulated at this CSA
    120: {1: 1.6, 3: 2.3, 4: 2.4},         # Two Core not tabulated at this CSA
}
IS694_SHEATH_THICKNESS_SOURCE = IS694_TABLE5_SOURCE

# Sheath thickness tolerance rule -- clause 18.1.4 (governing Table 5;
# identical wording independently repeated at clauses 8.3, 19.1.5, 20.1.4,
# 22.1.4 for the other sheathed-cable tables), verified from a direct
# page-image read of the PDF:
#   mean of readings must be >= nominal (ts)
#   smallest single reading must be >= ts - (0.1 + 0.15*ts)
# NOTE: this coefficient (0.15) is DIFFERENT from insulation's (0.1) --
# confirmed by five independent occurrences of the same clause wording
# across the standard, not just one. Do not reuse the insulation formula
# for sheath calculations.
IS694_CLAUSE_ts_TOLERANCE_SOURCE = "IS 694:2010, clause 18.1.4 (sheath tolerance -- 0.1 + 0.15*ts; " \
                                    "also cl. 8.3, 19.1.5, 20.1.4, 22.1.4)"

# ---------------------------------------------------------------------------
# VERIFIED: qualitative/fixed test parameters read directly from 694_2010's
# clause text, cross-confirmed against CTL's own observation sheet wording.
# ---------------------------------------------------------------------------
IS694_QUALITATIVE_LIMITS = {
    "HIGH_VOLTAGE_ROOM_TEMP": {
        "ac_kv_rms": 3.0, "dc_kv": 7.2, "duration_min": 5,
        "source": "IS 694:2010, clause 10.2 (method: IS 10810 Part 45)",
    },
    "HIGH_VOLTAGE_WATER_IMMERSION_AC": {
        "soak_temp_c": 60, "soak_duration_h": 24,
        "initial_kv": 3.0, "raised_kv": 6.0, "raise_within_s": 10, "hold_min": 5,
        "source": "IS 694:2010, clause 10.1(i) (method: IS 10810 Part 45)",
    },
    "HIGH_VOLTAGE_WATER_IMMERSION_DC": {
        "dc_kv": 1.2, "duration_h": 240, "soak_temp_c": 60,
        "source": "IS 694:2010, clause 10.1(ii) (method: IS 10810 Part 45)",
    },
    "OXYGEN_INDEX": {
        "min_pct": 29.0, "test_temp_c": 27,
        "source": "IS 694:2010, clause 10.5 (method: IS 10810 Part 58)",
    },
    "HALOGEN_ACID_GAS": {
        "max_pct_by_weight": 20.0,
        "source": "IS 694:2010, clause 10.6 (method: IS 10810 Part 59)",
    },
    "TEMPERATURE_INDEX": {
        "min_c": 250.0,
        "source": "IS 694:2010, clause 10.7 (method: IS 10810 Part 64)",
    },
    "SMOKE_DENSITY": {
        "max_pct_light_absorption": 60.0,
        "source": "IS 13360 (Part 6/Sec 9):2001, cited at IS 694:2010 clause 10.8",
    },
    "FLAMMABILITY": {
        "max_burn_after_removal_s": 60.0, "min_unaffected_length_mm": 50.0,
        "source": "IS 694:2010, clause 10.4 (method: IS 10810 Part 53)",
    },
    "COLD_BEND": {
        "conditioning_temp_c": -15.0, "conditioning_duration_h": 2, "specimens": 2,
        "applies_to_diameter_mm_max": 12.5,
        "pass_criterion": "No cracks or scales shall be visible.",
        "source": "IS 694:2010, Table 1 Sl. iii.c.8 (method: IS 10810 Part 20); category 02 only",
    },
    "COLD_IMPACT": {
        "conditioning_temp_c": -5.0, "conditioning_duration_h": 2, "specimens": 2,
        "applies_to_diameter_mm_min": 12.5,
        "pass_criterion": "No cracks or scales shall be visible.",
        "source": "IS 694:2010, Table 1 Sl. iii.c.9 (method: IS 10810 Part 21); category 02 only, Optional",
    },
}

# ---------------------------------------------------------------------------
# VERIFIED (primary source): IS 5831:1984 (First Revision, reaffirmed 2021),
# Table 1 (insulation, clause 4.1) and Table 2 (sheath, clause 4.1). Read
# directly from the PDF via 288dpi page-image rendering with digit-level
# zoom verification on ambiguous cells -- see this project's standards
# review notes for the full per-cell citation. This REPLACES the previous
# secondary-source values (CTL's Calculations.xlsx "BIS" sheet), which are
# now demoted to a cross-check rather than the primary source.
#
# IMPORTANT: IS 5831:1984 defines Insulation Types A, B, C and Sheath Types
# ST1, ST2 ONLY. There is no Type D or ST3 anywhere in this edition -- CTL's
# own worksheet uses "Type D" and "ST3" designations that do not trace to
# this specific PDF. Those entries are kept below (real samples are actively
# certified against them) but explicitly marked CTL-sourced, not
# IS-5831-1984-sourced, since silently blending the two would misrepresent
# which numbers are independently standard-verified.
#
# Two cells are genuinely defective in the source printing itself (not an
# extraction failure -- confirmed by direct visual inspection at high zoom):
#   - Table 1, Type A volume resistivity at 27 degC: printed in a non-
#     superscript font unlike its neighbours; likely 1e13 by internal
#     consistency with the IR-constant row, but not fully certain.
#   - Table 1, Type A "Loss of mass, Max": the numeric cell is entirely
#     absent from the printed table (a typesetting gap, not a scan defect).
#     CTL's own worksheet independently uses 2 mg/cm2 for this; kept as a
#     secondary-sourced value, explicitly flagged, not claimed as
#     IS-5831-verified.
# ---------------------------------------------------------------------------
IS5831_TABLE1_SOURCE = "IS 5831:1984, Table 1 (clause 4.1) -- PVC insulation compound properties"
IS5831_TABLE2_SOURCE = "IS 5831:1984, Table 2 (clause 4.1) -- PVC sheath compound properties"

IS694_INSULATION_LIMITS = {
    "A": {
        "tensile_strength_min_mpa": 12.5,
        "elongation_min_pct": 150.0,
        "tensile_strength_after_ageing_min_mpa": 12.5,
        "elongation_after_ageing_min_pct": 150.0,
        "tensile_strength_variation_max_pct": 20.0,
        "elongation_variation_max_pct": 20.0,
        "loss_of_mass_max_mg_per_cm2": 2.0,
        "loss_of_mass_max_mg_per_cm2_flag": "NOT_PRINTED_IN_IS5831_SOURCE -- value from CTL's own worksheet, "
                                             "not independently standard-verified; the source table's cell is "
                                             "physically absent (typesetting gap), not merely hard to read",
        "shrinkage_max_pct": 4.0,
        "hot_deformation_indentation_max_pct": 50.0,   # CONFIRMED: "Depth of indentation, Max" -- see calc_hot_deformation
        "thermal_stability_min_minutes": 80.0,
        "ageing_temp_c": 80.0,
        "ageing_duration_days": 7,
        "ir_constant_room_temp_min_mohm_km": 36.7,
        "ir_constant_max_temp_min_mohm_km": 0.037,
        "ir_max_temp_c": 70.0,
        "volume_resistivity_room_temp_min_ohm_cm": 1e13,
        "volume_resistivity_room_temp_min_ohm_cm_flag": "Source cell typeset non-superscript, exponent inferred "
                                                          "from internal consistency with IR constant row -- see module docstring",
        "volume_resistivity_max_temp_min_ohm_cm": 1e10,
    },
    "B": {
        # Present for completeness (a real IS 5831 type) though not currently
        # offered in the Cable Profile UI -- CTL's own reference data (and
        # therefore this app's product-family scope so far) does not use
        # Type B for the IS 694 samples reviewed. Add to the UI if a real
        # sample needs it.
        "tensile_strength_min_mpa": 12.5,
        "elongation_min_pct": 135.0,
        "tensile_strength_after_ageing_min_mpa": 12.5,
        "elongation_after_ageing_min_pct": 125.0,
        "tensile_strength_variation_max_pct": 25.0,
        "elongation_variation_max_pct": 25.0,
        "loss_of_mass_max_mg_per_cm2": None,  # test does not apply to Type B (IS 5831 Table 1 row v.a)
        "shrinkage_max_pct": 4.0,
        "hot_deformation_indentation_max_pct": 50.0,
        "thermal_stability_min_minutes": 100.0,
        "ageing_temp_c": 100.0,
        "ageing_duration_days": 7,
        "ir_constant_room_temp_min_mohm_km": 367.0,
        "ir_constant_max_temp_min_mohm_km": 0.37,
        "ir_max_temp_c": 70.0,
        "volume_resistivity_room_temp_min_ohm_cm": 1e14,
        "volume_resistivity_max_temp_min_ohm_cm": 1e11,
    },
    "C": {
        "tensile_strength_min_mpa": 12.5,
        "elongation_min_pct": 125.0,
        "tensile_strength_after_ageing_min_mpa": 12.5,
        "elongation_after_ageing_min_pct": 125.0,
        "tensile_strength_variation_max_pct": 25.0,
        "elongation_variation_max_pct": 35.0,
        "loss_of_mass_max_mg_per_cm2": None,  # test does not apply to Type C (IS 5831 Table 1 row v.a: "-")
        "shrinkage_max_pct": 4.0,
        "hot_deformation_indentation_max_pct": 50.0,
        "thermal_stability_min_minutes": 100.0,
        "ageing_temp_c": 135.0,   # CONFIRMED by direct digit-level zoom read of the source -- not a typo
        "ageing_duration_days": 7,
        "ir_constant_room_temp_min_mohm_km": 36.7,
        "ir_constant_max_temp_min_mohm_km": 0.037,
        "ir_max_temp_c": 85.0,
        "volume_resistivity_room_temp_min_ohm_cm": 1e13,
        "volume_resistivity_max_temp_min_ohm_cm": 1e10,
    },
    "D": {
        # NOT present in IS 5831:1984 -- this is CTL's own operational
        # classification (used for flexible-cord insulation on real
        # samples), sourced from Calculations.xlsx's "BIS" sheet, not from
        # the standard PDF itself. Kept because CTL actively certifies
        # against it; not claimed as independently standard-verified.
        "tensile_strength_min_mpa": 10.0,
        "elongation_min_pct": 150.0,
        "tensile_strength_after_ageing_min_mpa": 10.0,
        "elongation_after_ageing_min_pct": 150.0,
        "tensile_strength_variation_max_pct": 20.0,
        "elongation_variation_max_pct": 20.0,
        "loss_of_mass_max_mg_per_cm2": 2.0,
        "shrinkage_max_pct": 6.0,
        "hot_deformation_indentation_max_pct": 65.0,
        "thermal_stability_min_minutes": 80.0,
        "ageing_temp_c": 70.0,
        "ir_constant_room_temp_min_mohm_km": 3.67,
        "ir_constant_max_temp_min_mohm_km": 0.004,
        "ir_max_temp_c": 70.0,
        "volume_resistivity_room_temp_min_ohm_cm": 1e12,
        "volume_resistivity_max_temp_min_ohm_cm": 1e10,
        "_provenance": "CTL_WORKSHEET_ONLY -- not in IS 5831:1984",
    },
}
IS694_INSULATION_LIMITS_SOURCE = IS5831_TABLE1_SOURCE

IS694_SHEATH_LIMITS = {
    "ST1": {
        "tensile_strength_min_mpa": 12.5,
        "elongation_min_pct": 150.0,
        "tensile_strength_after_ageing_min_mpa": 12.5,
        "elongation_after_ageing_min_pct": 150.0,
        "tensile_strength_variation_max_pct": 20.0,
        "elongation_variation_max_pct": 20.0,
        "loss_of_mass_max_mg_per_cm2": 2.0,
        "shrinkage_max_pct": 4.0,
        "hot_deformation_indentation_max_pct": 50.0,   # CONFIRMED
        "thermal_stability_min_minutes": 40.0,
        "ageing_temp_c": 80.0,
        "ageing_duration_days": 7,
    },
    "ST2": {
        "tensile_strength_min_mpa": 12.5,
        "elongation_min_pct": 150.0,
        "tensile_strength_after_ageing_min_mpa": 12.5,
        "elongation_after_ageing_min_pct": 150.0,
        "tensile_strength_variation_max_pct": 25.0,
        "elongation_variation_max_pct": 25.0,
        "loss_of_mass_max_mg_per_cm2": 2.0,
        "shrinkage_max_pct": 4.0,
        "hot_deformation_indentation_max_pct": 50.0,   # CONFIRMED
        "thermal_stability_min_minutes": 80.0,
        "ageing_temp_c": 100.0,
        "ageing_temp_c_flag": "Source cell for ST2 hot-deformation test temperature (a DIFFERENT clause) reads "
                               "'30' as literally printed, inconsistent with ST2's own 90 degC service rating -- "
                               "likely a print defect for 90. Does not affect ageing_temp_c above (that cell was "
                               "clean); flagged here for visibility since it's the same Type.",
        "ageing_duration_days": 7,
    },
    "ST3": {
        # NOT present in IS 5831:1984 -- Table 2 defines only ST1 and ST2.
        # CTL-sourced operational classification, same caveat as Insulation
        # Type D above.
        "tensile_strength_min_mpa": 10.0,
        "elongation_min_pct": 150.0,
        "tensile_strength_after_ageing_min_mpa": 10.0,
        "elongation_after_ageing_min_pct": 150.0,
        "tensile_strength_variation_max_pct": 20.0,
        "elongation_variation_max_pct": 20.0,
        "loss_of_mass_max_mg_per_cm2": 2.0,
        "shrinkage_max_pct": 6.0,
        "hot_deformation_indentation_max_pct": None,  # not available from either source for ST3
        "thermal_stability_min_minutes": 40.0,
        "ageing_temp_c": 80.0,
        "_provenance": "CTL_WORKSHEET_ONLY -- not in IS 5831:1984",
    },
}
IS694_SHEATH_LIMITS_SOURCE = IS5831_TABLE2_SOURCE

# ---------------------------------------------------------------------------
# RESOLVED (was PENDING_VERIFICATION): Hot Deformation's pass/fail sense.
# IS 5831:1984 itself (Table 1 row vi.c, Table 2 row iv.c) labels the graded
# quantity "Depth of indentation, Max" for every type -- i.e. the measured
# compression, limited by a maximum, NOT a "percentage thickness retained"
# limited by a minimum. The observation sheet's own raw-reading formula
# (T1 = indentation-point thickness, T2 = undeformed reference thickness)
# is still used to capture readings, but the graded value is now computed
# as depth_of_indentation% = 100 - (T1/T2*100), matching this standard's
# framing -- see calculation_engine.calc_hot_deformation.
# ---------------------------------------------------------------------------
HOT_DEFORMATION_FORMULA_STATUS = "RESOLVED -- IS 5831:1984 Table 1/Table 2, 'Depth of indentation, Max' (all types = 50%)"
