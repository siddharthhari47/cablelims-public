"""
Calculation Engine.

Executes the derived-value calculation for a submitted TestRun's raw
readings, and resolves the applicable acceptance limit via the Standards
Service (never a literal in this file). Returns a CalcResult that the
Confidence Engine turns into VERIFIED/REVIEW_REQUIRED/BLOCKED and
PASS/FAIL/UNDETERMINED -- this module does not decide pass/fail itself,
it only computes numbers and fetches the limit to compare against.

Test IDs handled here are the Cable / IS 694 family, expanded per CTL's
real observation sheet, Test Report, and Calculations.xlsx worked example
(Sprint Priority 1). Every formula is either the literal formula from
Calculations.xlsx (cited in each function's docstring) or the plain
arithmetic stated directly in the observation sheet -- nothing here is
invented. Where a formula's exact meaning is ambiguous even after reading
the source documents, the function returns a PENDING_VERIFICATION result
rather than guessing (see calc_hot_deformation).

Functions receive `core_position` (None | "RED"|"YELLOW"|"BLUE"|"BLACK"|
"SHEATH") so PER_CORE_AND_SHEATH-scope tests know whether to look up
Insulation-Type or Sheath-Type limits for the same test_id.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.models import CableProfile
from app.services.standards_service import LookupResult, standards_service


@dataclass
class Criterion:
    """One independent acceptance criterion within a single test -- e.g.
    IS 694 cl.8.3 imposes TWO separate pass/fail conditions on an
    insulation-thickness reading set (mean >= nominal, AND every individual
    reading >= a separate floor), not one. Before H8, calc_insulation_
    thickness/calc_sheath_thickness collapsed both into a single reported
    (calculated_value, limit_value) pair, picking whichever one "lost" as
    the value to report -- which meant a failure of the individual-reading
    floor was reported as if it had failed the MEAN criterion instead (the
    wrong number, checked against the wrong limit), and its margin-from-
    limit was computed against the wrong reference value entirely. See
    confidence_engine._evaluate_criteria, the consumer of this list."""
    name: str
    calculated_value: float
    operator: str                # ">=" | "<=" | "=="
    limit_value: float


@dataclass
class CalcResult:
    calculated_value: Optional[float]
    calculated_unit: Optional[str]
    limit: LookupResult
    operator: Optional[str]     # ">=" | "<=" | "=="
    limit_value: Optional[float]
    note: Optional[str] = None
    # Populated only by calculators with more than one independent
    # acceptance criterion (currently: calc_insulation_thickness,
    # calc_sheath_thickness). When set, confidence_engine.evaluate()
    # decides PASS/FAIL/margin from these instead of the single
    # calculated_value/operator/limit_value triple above, which remains
    # populated purely for backward-compatible display (e.g. the
    # Calculation tab's single "measured value" column) -- see Criterion's
    # own docstring for why the single-value path was scientifically wrong
    # for a multi-criterion test.
    criteria: Optional[List[Criterion]] = field(default=None)


def _num(raw: Dict[str, Any], key: str) -> Optional[float]:
    v = raw.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _csa_bucket(profile) -> float:
    return getattr(profile, "_csa", None)


def _is_sheath(core_position: Optional[str]) -> bool:
    return core_position == "SHEATH"


def _material_limit(profile: CableProfile, core_position: Optional[str], key: str) -> LookupResult:
    """Route to the Insulation-Type (A/C/D) or Sheath-Type (ST1/ST2/ST3) limit
    table depending on which position this particular AssignedTest instance
    is for -- this is the mechanism that lets one TestDefinition (e.g.
    "Tensile Strength") serve both the per-core insulation tests and the
    separate outer-sheath test."""
    if _is_sheath(core_position):
        return standards_service.get_sheath_limit(profile.sheath_type, key)
    return standards_service.get_insulation_limit(profile.insulation_type, key)


# =============================================================================
# Conductor tests
# =============================================================================

def calc_conductor_resistance(raw, profile, core_position=None) -> CalcResult:
    """IS 8130:2013 clause 7.3 / Calculations.xlsx per-core sheets.
    corrected R(ohm/km) = (ObservedResistance(mOhm)/1000 * kt) / Length(m) * 1000
    -- Calculations.xlsx computes the /1000 (to Ohm/km) implicitly via unit
    setup; reproduced explicitly here to keep units unambiguous."""
    measured_mohm = _num(raw, "observed_resistance_mohm")
    length_m = _num(raw, "specimen_length_m")
    temp_c = _num(raw, "room_temperature_c")
    if measured_mohm is None or length_m is None or temp_c is None or length_m == 0:
        return CalcResult(None, "ohm/km", standards_service.missing("missing raw inputs"), None, None)
    kt = standards_service.get_temperature_correction_factor(temp_c)
    r_ohm = measured_mohm / 1000.0
    corrected_ohm_per_km = round((r_ohm * kt.value / length_m) * 1000.0, 4)
    limit = standards_service.get_conductor_resistance_limit(profile.conductor_material, _csa_bucket(profile), profile.conductor_class)
    return CalcResult(corrected_ohm_per_km, "ohm/km", limit, "<=", limit.value if limit.kind == "VERIFIED" else None,
                       note=f"corrected = (observed {measured_mohm}mOhm / length {length_m}m) x kt({temp_c}degC={kt.value})")


def calc_annealing_elongation(raw, profile, core_position=None) -> CalcResult:
    """IS 8130:2013 clause 7.1.2.1 (copper conductor, before stranding). Elongation
    Min% is banded by wire diameter (skb_seed_data.IS8130_ANNEALING_ELONGATION_MIN_PCT_BY_WIRE_DIA)."""
    wire_dia = _num(raw, "wire_diameter_mm")
    gauge_length = _num(raw, "specimen_gauge_length_mm")
    length_after_break = _num(raw, "length_after_break_mm")
    if wire_dia is None or gauge_length is None or length_after_break is None:
        return CalcResult(None, "%", standards_service.missing("missing raw inputs"), None, None)
    elongation_mm = length_after_break - gauge_length
    pct = round((elongation_mm / gauge_length) * 100, 2) if gauge_length else None
    limit = standards_service.get_annealing_elongation_min(wire_dia)
    return CalcResult(pct, "%", limit, ">=", limit.value if limit.kind == "VERIFIED" else None,
                       note=f"elongation = length_after_break - gauge_length = {elongation_mm}mm over {gauge_length}mm")


def calc_aluminium_tensile(raw, profile, core_position=None) -> CalcResult:
    """IS 8130:2013 clause 7.2.1 (aluminium conductor). Grade-banded limit,
    reduced to 95% after stranding per clause 7.2.1(b)."""
    load_n = _num(raw, "breaking_load_n")
    dia_mm = _num(raw, "wire_diameter_mm")
    grade = raw.get("aluminium_grade")  # "Grade 0" | "Grade H2" | "Grade H4"
    after_stranding = bool(raw.get("after_stranding", False))
    if load_n is None or dia_mm is None or not grade:
        return CalcResult(None, "N/mm2", standards_service.missing("missing raw inputs"), None, None)
    import math
    area_mm2 = math.pi * (dia_mm / 2.0) ** 2
    tensile = round(load_n / area_mm2, 2) if area_mm2 else None
    limit = standards_service.get_aluminium_tensile_grade_limit(grade, after_stranding)
    limit_val = limit.value["min"] if limit.kind == "VERIFIED" and isinstance(limit.value, dict) else None
    return CalcResult(tensile, "N/mm2", limit, ">=", limit_val,
                       note=f"area = pi*(d/2)^2 = {round(area_mm2,3)}mm2 from wire dia {dia_mm}mm")


def calc_aluminium_wrapping(raw, profile, core_position=None) -> CalcResult:
    """IS 8130:2013 clause 6.2.2 -- qualitative, wire shall not break."""
    broke = raw.get("wire_broke", None)
    if broke is None:
        return CalcResult(None, None, standards_service.missing("no reading"), "==", None)
    value = 0.0 if broke else 1.0
    limit = standards_service.get_wrapping_test_criterion()
    return CalcResult(value, "pass", limit, "==", 1.0)


# =============================================================================
# Dimensional tests
# =============================================================================

def calc_insulation_thickness(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 clause 8.3 / Table 5. Per-core.

    Two INDEPENDENT acceptance criteria, not one (H8):
      1. mean of all readings >= nominal thickness
      2. every individual reading >= nominal - (0.1 + 0.1*nominal) (a
         separate, lower floor -- a single thin spot can fail this even
         when the mean looks healthy)
    Both are reported as their own Criterion so confidence_engine can
    evaluate, and explain, each on its own terms -- see Criterion's
    docstring for what this replaced."""
    readings = raw.get("readings_mm")
    if not readings or not isinstance(readings, list):
        return CalcResult(None, "mm", standards_service.missing("no readings submitted"), None, None)
    values = [float(v) for v in readings]
    mean_val = round(sum(values) / len(values), 3)
    min_val = min(values)
    nominal = standards_service.get_insulation_thickness_nominal(_csa_bucket(profile))
    if nominal.kind != "VERIFIED":
        return CalcResult(mean_val, "mm", nominal, ">=", None, note="no nominal thickness on file")
    min_allowed = round(nominal.value - (0.1 + 0.1 * nominal.value), 3)
    note = f"mean={mean_val}mm (nominal {nominal.value}mm), min single reading={min_val}mm (floor {min_allowed}mm)"
    criteria = [
        Criterion("mean of all readings", mean_val, ">=", nominal.value),
        Criterion("lowest individual reading", min_val, ">=", min_allowed),
    ]
    # calculated_value/limit_value below stay the mean/nominal pair for any
    # display that only understands the single-value view (e.g. the
    # Calculation tab's "measured" column) -- the PASS/FAIL/margin decision
    # itself comes from `criteria`, not this pair (see confidence_engine).
    return CalcResult(mean_val, "mm", nominal, ">=", nominal.value, note=note, criteria=criteria)


def calc_sheath_thickness(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 clause 18.1.4 (Table 5). Sheath tolerance uses coefficient
    0.15, NOT insulation's 0.1 -- confirmed by direct standard text, repeated
    identically at 5 separate clauses (see skb_seed_data.py). Whole-sample
    (SHEATH_ONLY scope), keyed by CSA AND core count.

    Same two-independent-criteria structure as calc_insulation_thickness
    (H8) -- see that function's docstring and Criterion's docstring."""
    readings = raw.get("readings_mm")
    if not readings or not isinstance(readings, list):
        return CalcResult(None, "mm", standards_service.missing("no readings submitted"), None, None)
    values = [float(v) for v in readings]
    mean_val = round(sum(values) / len(values), 3)
    min_val = min(values)
    cores = getattr(profile, "_cores", None) or 1
    nominal = standards_service.get_sheath_thickness_nominal(_csa_bucket(profile), cores)
    if nominal.kind != "VERIFIED":
        return CalcResult(mean_val, "mm", nominal, ">=", None, note="no nominal sheath thickness on file")
    ts = nominal.value
    min_allowed = round(ts - (0.1 + 0.15 * ts), 3)
    note = (f"mean={mean_val}mm (nominal {ts}mm), min={min_val}mm (floor {min_allowed}mm, "
            f"per IS 694 cl.18.1.4: ts - (0.1+0.15*ts))")
    criteria = [
        Criterion("mean of all readings", mean_val, ">=", ts),
        Criterion("lowest individual reading", min_val, ">=", min_allowed),
    ]
    return CalcResult(mean_val, "mm", nominal, ">=", ts, note=note, criteria=criteria)


# =============================================================================
# Physical tests on insulation / sheath (PER_CORE_AND_SHEATH -- core_position
# selects Insulation-Type vs Sheath-Type limits via _material_limit above)
# =============================================================================

def calc_tensile_strength(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 7. Area = width x thickness (dumbbell specimen -- the
    tube-specimen alternate area formula pi*(D-t)*t from the observation
    sheet is not yet wired up; dumbbell is CTL's standard specimen shape)."""
    force_n = _num(raw, "breaking_load_n")
    width_mm = _num(raw, "width_mm")
    thickness_mm = _num(raw, "thickness_mm")
    key = "tensile_strength_min_mpa"
    limit = _material_limit(profile, core_position, key)
    if not all(v is not None for v in [force_n, width_mm, thickness_mm]):
        return CalcResult(None, "N/mm2", limit, ">=", None)
    area = width_mm * thickness_mm
    mpa = round(force_n / area, 2) if area else None
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(mpa, "N/mm2", limit, ">=", limit_val, note=f"area = width x thickness = {area}mm2")


def calc_elongation(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 7 (companion measurement to Tensile Strength, same
    specimen/pull). Elongation% = ((length at break - initial gauge length)
    / initial gauge length) x 100."""
    initial_mm = _num(raw, "initial_length_mm")
    final_mm = _num(raw, "final_length_mm")
    limit = _material_limit(profile, core_position, "elongation_min_pct")
    if initial_mm is None or final_mm is None or not initial_mm:
        return CalcResult(None, "%", limit, ">=", None)
    pct = round(((final_mm - initial_mm) / initial_mm) * 100, 1)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(pct, "%", limit, ">=", limit_val)


def calc_ageing_tensile_variation(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 11 -- ageing 80/100/135/70 degC per Insulation Type,
    7 days (168h). variation% = ((before-after)/before)*100. `before_tensile_mpa`
    is expected to be pre-filled from the sibling Tensile Strength test's
    accepted result (Sprint Priority 7 smart autofill) but is still an
    explicit raw input here so this function stays pure/DB-free."""
    before = _num(raw, "before_tensile_mpa")
    load_n = _num(raw, "breaking_load_n")
    width_mm = _num(raw, "width_mm")
    thickness_mm = _num(raw, "thickness_mm")
    limit = _material_limit(profile, core_position, "tensile_strength_variation_max_pct")
    after_min_limit = _material_limit(profile, core_position, "tensile_strength_after_ageing_min_mpa")
    if not all(v is not None for v in [before, load_n, width_mm, thickness_mm]) or not before:
        return CalcResult(None, "%", limit, "<=", None)
    area = width_mm * thickness_mm
    after = round(load_n / area, 2) if area else None
    variation_pct = round(abs((before - after) / before) * 100, 2) if after is not None else None
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    note = f"after={after} N/mm2 (min required {after_min_limit.value if after_min_limit.kind=='VERIFIED' else '?'}), before={before}"
    return CalcResult(variation_pct, "%", limit, "<=", limit_val, note=note)


def calc_ageing_elongation_variation(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 11 -- elongation variation% after ageing."""
    before = _num(raw, "before_elongation_pct")
    initial_mm = _num(raw, "initial_length_mm")
    final_mm = _num(raw, "final_length_mm")
    limit = _material_limit(profile, core_position, "elongation_variation_max_pct")
    if not all(v is not None for v in [before, initial_mm, final_mm]) or not initial_mm or not before:
        return CalcResult(None, "%", limit, "<=", None)
    after = round(((final_mm - initial_mm) / initial_mm) * 100, 1)
    variation_pct = round(abs((before - after) / before) * 100, 2)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(variation_pct, "%", limit, "<=", limit_val, note=f"after={after}%, before={before}%")


def calc_loss_of_mass(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 10. LossOfMass(mg/cm2) = (InitialWeight-FinalWeight)/SurfaceArea.
    NOTE: Calculations.xlsx's own formula includes an extra x1000 factor that
    does not dimensionally reconcile with mg and cm2 inputs (would yield
    g/cm2-scale numbers against a 2 mg/cm2-scale limit) -- implemented here
    without that factor, which is dimensionally consistent with the stated
    units and the stated limit's order of magnitude. Flagged for CTL to
    double check against a physical sample if the result looks off."""
    initial_mg = _num(raw, "initial_weight_mg")
    final_mg = _num(raw, "final_weight_mg")
    area_cm2 = _num(raw, "surface_area_cm2")
    key = "loss_of_mass_max_mg_per_cm2"
    limit = _material_limit(profile, core_position, key)
    if not all(v is not None for v in [initial_mg, final_mg, area_cm2]) or not area_cm2:
        return CalcResult(None, "mg/cm2", limit, "<=", None)
    loss = round((initial_mg - final_mg) / area_cm2, 3)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(loss, "mg/cm2", limit, "<=", limit_val)


def calc_shrinkage(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 12, 150 degC / 15 min. %Shrinkage = ((L1-L2)/L1)*100."""
    l1 = _num(raw, "length_before_mm")
    l2 = _num(raw, "length_after_mm")
    limit = _material_limit(profile, core_position, "shrinkage_max_pct")
    if l1 is None or l2 is None or not l1:
        return CalcResult(None, "%", limit, "<=", None)
    pct = round(((l1 - l2) / l1) * 100, 2)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(pct, "%", limit, "<=", limit_val)


def calc_heat_shock(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 14, 150 degC / 1h -- qualitative, no cracks/scales."""
    cracked = raw.get("cracks_observed", None)
    if cracked is None:
        return CalcResult(None, None, standards_service.missing("no reading"), "==", None)
    value = 0.0 if cracked else 1.0
    return CalcResult(value, "pass", LookupResult("VERIFIED", 1.0, None, "IS 694:2010 Table 1 sl.iii.c.5/d.5"), "==", 1.0)


def calc_hot_deformation(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 15 (method); limit per IS 5831:1984 Table 1/2, row
    'Depth of indentation, Max' (confirmed by direct reading of the primary
    standard -- see skb_seed_data.py HOT_DEFORMATION_FORMULA_STATUS).
    Raw readings per the observation sheet: T1 = thickness at the
    indentation point (2 specimens), T2 = thickness ~10mm from the
    indentation, i.e. the undeformed reference (4 readings, 2 per specimen).
    depth_of_indentation% = 100 - (T1_avg / T2_avg * 100) -- the complement
    of the observation sheet's own 'percentage thickness retained' formula,
    reframed to match how the standard itself states the limit (a maximum
    on indentation depth, not a minimum on thickness retained)."""
    t1_readings = raw.get("t1_indentation_mm")   # list, 2 readings (one per specimen)
    t2_readings = raw.get("t2_reference_mm")     # list, 4 readings (two per specimen)
    key = "hot_deformation_indentation_max_pct"
    limit = _material_limit(profile, core_position, key)
    if not t1_readings or not t2_readings:
        return CalcResult(None, "%", limit, "<=", None)
    t1_avg = sum(float(v) for v in t1_readings) / len(t1_readings)
    t2_avg = sum(float(v) for v in t2_readings) / len(t2_readings)
    if not t2_avg:
        return CalcResult(None, "%", limit, "<=", None)
    pct_retained = (t1_avg / t2_avg) * 100
    depth_of_indentation = round(100 - pct_retained, 2)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(depth_of_indentation, "%", limit, "<=", limit_val,
                       note=f"depth of indentation = 100 - (T1 avg {round(t1_avg,3)}mm / T2 avg {round(t2_avg,3)}mm x 100), "
                            f"per IS 5831:1984 'Depth of indentation, Max'")


def calc_thermal_stability(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 60, 200 +/-0.5 degC. Raw minutes-to-failure value;
    CTL's own worksheet stores this without an auto pass/fail formula, but
    the limit table (BIS sheet) does give a clear Min-minutes threshold per
    Insulation/Sheath type, so this can be graded confidently."""
    minutes = _num(raw, "thermal_stability_minutes")
    limit = _material_limit(profile, core_position, "thermal_stability_min_minutes")
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(minutes, "min", limit, ">=", limit_val)


def calc_oxygen_index(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 cl.10.5 / IS 10810 Part 58. Direct entry of the measured
    oxygen index (the minimum % concentration of oxygen in an oxygen/nitrogen
    mixture that will just support candle-like combustion of the specimen) --
    read directly off the oxygen index apparatus, not derived from other
    readings."""
    value = _num(raw, "oxygen_index_pct")
    limit = standards_service.get_qualitative_limit("OXYGEN_INDEX")
    limit_val = limit.value["min_pct"] if limit.kind == "VERIFIED" else None
    return CalcResult(value, "%", limit, ">=", limit_val)


def calc_halogen_acid_gas(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 59. HCl% = (36.5*(B-A)*F*(500/100)*100)/1000, where
    A/B are titration volumes (ml), F is the titration factor, per
    Calculations.xlsx's exact formula chain."""
    weight_g = _num(raw, "sample_weight_g")
    b_ml = _num(raw, "titration_b_ml")
    a_ml = _num(raw, "titration_a_ml")
    factor = _num(raw, "titration_factor")
    limit = standards_service.get_qualitative_limit("HALOGEN_ACID_GAS")
    if not all(v is not None for v in [weight_g, b_ml, a_ml, factor]):
        return CalcResult(None, "%", limit, "<=", None)
    intermediate = 36.5 * (b_ml - a_ml) * factor * (500.0 / 100.0)
    hcl_pct = round((intermediate * 100.0) / 1000.0, 3)
    limit_val = limit.value["max_pct_by_weight"] if limit.kind == "VERIFIED" else None
    return CalcResult(hcl_pct, "%", limit, "<=", limit_val, note=f"sample weight {weight_g}g, B-A={b_ml-a_ml}ml, factor={factor}")


def calc_temperature_index(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 64. CTL's own worksheet hard-types this final value
    rather than deriving it from the 3 (temperature, O2%) pairs via any
    visible formula (likely an external regression/interpolation) -- so,
    matching CTL's own practice, this is direct entry of the final
    temperature index, not a computed value."""
    value = _num(raw, "temperature_index_c")
    limit = standards_service.get_qualitative_limit("TEMPERATURE_INDEX")
    limit_val = limit.value["min_c"] if limit.kind == "VERIFIED" else None
    return CalcResult(value, "deg C", limit, ">=", limit_val)


def calc_smoke_density(raw, profile, core_position=None) -> CalcResult:
    """IS 13360 Part 6/Sec 9. SmokeDensityRating% = average of the 17 readings
    (t=0 through t=240s at 15s intervals)."""
    readings = raw.get("readings_pct")  # list of up to 17 values
    if not readings or not isinstance(readings, list):
        return CalcResult(None, "%", standards_service.missing("no readings submitted"), None, None)
    values = [float(v) for v in readings if v is not None]
    if not values:
        return CalcResult(None, "%", standards_service.missing("no readings submitted"), None, None)
    rating = round(sum(values) / len(values), 2)
    limit = standards_service.get_qualitative_limit("SMOKE_DENSITY")
    limit_val = limit.value["max_pct_light_absorption"] if limit.kind == "VERIFIED" else None
    return CalcResult(rating, "%", limit, "<=", limit_val, note=f"rating = average of {len(values)} readings")


def calc_flammability_burn_duration(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.c.10 / IS 10810 Part 53. The specimen is
    flame-tested per the standard's clamped-specimen method; this is the
    directly-timed period (seconds) the specimen continues burning after
    the test flame is withdrawn -- a stopwatch reading, not a derived value."""
    value = _num(raw, "burn_duration_after_removal_s")
    limit = standards_service.get_qualitative_limit("FLAMMABILITY")
    limit_val = limit.value["max_burn_after_removal_s"] if limit.kind == "VERIFIED" else None
    return CalcResult(value, "s", limit, "<=", limit_val)


def calc_flammability_unaffected_length(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.c.10 / IS 10810 Part 53, same test as Burn
    Duration above. After burning, the length of specimen left unaffected
    (undamaged) measured from the lower edge of the top clamp -- a direct
    ruler measurement on the post-test specimen."""
    value = _num(raw, "unaffected_length_mm")
    limit = standards_service.get_qualitative_limit("FLAMMABILITY")
    limit_val = limit.value["min_unaffected_length_mm"] if limit.kind == "VERIFIED" else None
    return CalcResult(value, "mm", limit, ">=", limit_val)


# =============================================================================
# Whole-cable electrical tests
# =============================================================================

def calc_insulation_resistance_room_temp(raw, profile, core_position=None) -> CalcResult:
    """IS 10810 Part 43. VolumeResistivity(ohm-cm) = 2*pi*L(m)*IR(Mohm)*10^8 /
    ln(D_insulation/d_conductor); IRconstant(Mohm.km) = L(m)*IR(Mohm) /
    (1000*log10(D/d)). Graded against Volume Resistivity (the more complete
    of the two limit sets for Type D; A/C max-temp values are MISSING)."""
    import math
    length_m = _num(raw, "specimen_length_m")
    ir_megaohm = _num(raw, "insulation_resistance_megaohm")
    d_outer_mm = _num(raw, "overall_diameter_mm")
    d_conductor_mm = _num(raw, "conductor_diameter_mm")
    limit = standards_service.get_insulation_limit(profile.insulation_type, "volume_resistivity_room_temp_min_ohm_cm")
    if not all(v is not None for v in [length_m, ir_megaohm, d_outer_mm, d_conductor_mm]) or d_conductor_mm <= 0:
        return CalcResult(None, "ohm-cm", limit, ">=", None)
    ratio = d_outer_mm / d_conductor_mm
    if ratio <= 1:
        return CalcResult(None, "ohm-cm", limit, ">=", None, note="overall diameter must exceed conductor diameter")
    vr = (2 * math.pi * length_m * ir_megaohm * 1e8) / math.log(ratio)
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(round(vr, 2), "ohm-cm", limit, ">=", limit_val)


def calc_insulation_resistance_constant(raw, profile, core_position=None) -> CalcResult:
    """IR constant K(Mohm.km) = L(m)*IR(Mohm) / (1000*log10(D/d))."""
    import math
    length_m = _num(raw, "specimen_length_m")
    ir_megaohm = _num(raw, "insulation_resistance_megaohm")
    d_outer_mm = _num(raw, "overall_diameter_mm")
    d_conductor_mm = _num(raw, "conductor_diameter_mm")
    limit = standards_service.get_insulation_limit(profile.insulation_type, "ir_constant_room_temp_min_mohm_km")
    if not all(v is not None for v in [length_m, ir_megaohm, d_outer_mm, d_conductor_mm]) or d_conductor_mm <= 0:
        return CalcResult(None, "M-ohm.km", limit, ">=", None)
    ratio = d_outer_mm / d_conductor_mm
    if ratio <= 1:
        return CalcResult(None, "M-ohm.km", limit, ">=", None, note="overall diameter must exceed conductor diameter")
    k = (length_m * ir_megaohm) / (1000.0 * math.log10(ratio))
    limit_val = limit.value if limit.kind == "VERIFIED" else None
    return CalcResult(round(k, 5), "M-ohm.km", limit, ">=", limit_val)


def calc_hv_room_temp(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.e.3 / cl.10.2 / IS 10810 Part 45. The
    complete cable, immersed in water at room temperature for 1 hour, has
    3kV(rms) 50Hz applied for 5 minutes -- qualitative pass/fail on whether
    breakdown or flashover was observed during that period, not a computed
    value."""
    breakdown = raw.get("breakdown_observed", None)
    limit = standards_service.get_qualitative_limit("HIGH_VOLTAGE_ROOM_TEMP")
    if breakdown is None:
        return CalcResult(None, None, limit, "==", None)
    value = 0.0 if breakdown else 1.0
    return CalcResult(value, "withstand", limit, "==", 1.0)


def calc_hv_water_immersion(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.e.1 / cl.10.1 / IS 10810 Part 45. Two-stage
    test on the water-immersed cable (60+-3 degC, 24h soak): (1) an ac test
    at 3kV(rms) raised to 6kV(rms) 50Hz within 10s and held 5 minutes, then
    (2) a dc test at 1.2kV held for 240 hours in the same bath. Qualitative
    pass/fail on breakdown/flashover, not a computed value."""
    breakdown = raw.get("breakdown_observed", None)
    limit = standards_service.get_qualitative_limit("HIGH_VOLTAGE_WATER_IMMERSION_AC")
    if breakdown is None:
        return CalcResult(None, None, limit, "==", None)
    value = 0.0 if breakdown else 1.0
    return CalcResult(value, "withstand", limit, "==", 1.0)


def calc_cold_bend(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.c.8/d.8 (Category 02/outdoor cables only).
    Specimen conditioned at low temperature then bent round a mandrel of
    specified diameter -- qualitative pass/fail on whether cracks or
    scales were observed, not a computed value."""
    cracked = raw.get("cracks_observed", None)
    limit = standards_service.get_qualitative_limit("COLD_BEND")
    if cracked is None:
        return CalcResult(None, None, limit, "==", None)
    value = 0.0 if cracked else 1.0
    return CalcResult(value, "pass", limit, "==", 1.0)


def calc_cold_impact(raw, profile, core_position=None) -> CalcResult:
    """IS 694:2010 Table 1 sl.iii.c.9/d.9 (Category 02/outdoor cables only).
    Specimen conditioned at low temperature then struck with a specified
    impact -- qualitative pass/fail on whether cracks or scales were
    observed, not a computed value."""
    cracked = raw.get("cracks_observed", None)
    limit = standards_service.get_qualitative_limit("COLD_IMPACT")
    if cracked is None:
        return CalcResult(None, None, limit, "==", None)
    value = 0.0 if cracked else 1.0
    return CalcResult(value, "pass", limit, "==", 1.0)


CALCULATORS = {
    "TEST-0001": calc_conductor_resistance,
    "TEST-0002": calc_insulation_thickness,
    "TEST-0003": calc_tensile_strength,
    "TEST-0004": calc_elongation,
    "TEST-0005": calc_hv_room_temp,
    "TEST-0006": calc_insulation_resistance_room_temp,
    "TEST-0008": calc_oxygen_index,
    "TEST-0009": calc_halogen_acid_gas,
    "TEST-0010": calc_temperature_index,
    "TEST-0011": calc_annealing_elongation,
    "TEST-0012": calc_aluminium_tensile,
    "TEST-0013": calc_aluminium_wrapping,
    "TEST-0014": calc_sheath_thickness,
    "TEST-0015": calc_ageing_tensile_variation,
    "TEST-0016": calc_ageing_elongation_variation,
    "TEST-0017": calc_loss_of_mass,
    "TEST-0018": calc_shrinkage,
    "TEST-0019": calc_heat_shock,
    "TEST-0020": calc_hot_deformation,
    "TEST-0021": calc_thermal_stability,
    "TEST-0022": calc_smoke_density,
    "TEST-0023": calc_flammability_burn_duration,
    "TEST-0024": calc_flammability_unaffected_length,
    "TEST-0025": calc_hv_water_immersion,
    "TEST-0026": calc_cold_bend,
    "TEST-0027": calc_cold_impact,
    "TEST-0028": calc_insulation_resistance_constant,
}


def run_calculation(test_id: str, raw_values: Dict[str, Any], profile: CableProfile, csa_mm2: float,
                     core_position: Optional[str] = None, cores: Optional[int] = None) -> CalcResult:
    fn = CALCULATORS.get(test_id)
    if not fn:
        return CalcResult(None, None, standards_service.missing(f"no calculator registered for {test_id}"), None, None)
    # (ignore comments below: models.CableProfile._csa/_cores are declared
    # ClassVar specifically so SQLAlchemy's declarative scanner doesn't try
    # to map them as columns -- see that declaration's own comment -- but
    # mypy then, correctly per bare ClassVar semantics, objects to
    # assigning one through an instance here. This genuinely IS a
    # per-instance runtime assignment (each CableProfile gets its own
    # _csa/_cores for the duration of one calculation), exactly what this
    # line has always done; the two type checkers' rules conflict, not the
    # code.)
    profile._csa = csa_mm2  # type: ignore[misc]
    profile._cores = cores  # type: ignore[misc]
    return fn(raw_values, profile, core_position)
