"""
Golden-value test suite for calculation_engine.py -- §12.1's highest-value
item. There was zero automated coverage of a calculation engine that
decides whether electrical cable is safe to sell; the review's own cited
example (a real production defect -- CSA=2.5mm2 Class 5 copper, 7.41 vs the
correct 7.98 ohm/km, because the app had only ever encoded IS 8130 Table 2
and applied it to every conductor class) was caught by a human noticing an
odd number, not by a test. This suite is what would have caught it before
it reached a user.

Expected values are computed independently in this file's own arithmetic
(or, for the direct-entry tests, are just the raw reading passed through) --
NOT by calling the calculator under test -- so a bug in a calculator's
implementation of its own documented formula actually disagrees with this
file. Every raw-input set is drawn from seed.py's DEMO_READINGS, which is
CTL's own curated, SKB-consistent worked-example data (independently
cross-checked here against the actual "Calculated Results" values this
project verified live against the real running app earlier in this
project's history -- both agree).

Limit comparisons (PASS/FAIL) are asserted using the REAL standards_service
lookup rather than a second hardcoded copy of every SKB number, deliberately
-- that avoids two independent sources of truth for the same engineering
constant silently drifting apart, while still giving full regression
coverage: if a limit lookup breaks, the PASS/FAIL assertion catches it.
"""

import pytest

from app.engines.calculation_engine import CALCULATORS, run_calculation
from app.engines.confidence_engine import evaluate as confidence_evaluate
from app.models.models import CableProfile
from app.services.standards_service import standards_service


def _profile(**kwargs) -> CableProfile:
    defaults = dict(conductor_material="Copper", conductor_class="2", insulation_type="A",
                     insulation_material="PVC", sheath_type="ST1")
    defaults.update(kwargs)
    return CableProfile(**defaults)


def _run(test_id, raw, profile, csa_mm2=2.5, core_position=None, cores=3):
    calc = run_calculation(test_id, raw, profile, csa_mm2, core_position=core_position, cores=cores)
    outcome = confidence_evaluate(calc)
    return calc, outcome


# -- Registry completeness ---------------------------------------------------

def test_every_catalog_test_id_except_the_known_gap_has_a_calculator():
    # TEST-0007 is a pre-existing, documented gap (also absent from
    # engines/reading_schemas.py -- see that file's comment): the map jumps
    # TEST-0006 -> TEST-0008. Fabricating a calculator for it without
    # confirming what it actually is against CTL's source documents would
    # violate this project's "never guess" principle, so it stays excluded
    # here rather than silently masked. If a *different* test_id goes
    # missing in the future, this test must fail.
    expected_ids = {f"TEST-{i:04d}" for i in range(1, 29)} - {"TEST-0007"}
    assert expected_ids <= set(CALCULATORS.keys())


# -- Conductor tests ----------------------------------------------------------

def test_conductor_resistance_class2_copper_2p5mm2():
    profile = _profile(conductor_class="2")
    calc, outcome = _run("TEST-0001", {
        "observed_resistance_mohm": 18.2, "specimen_length_m": 5.0, "room_temperature_c": 27.0,
    }, profile, csa_mm2=2.5, core_position="RED")
    assert calc.calculated_value == pytest.approx(3.541, abs=1e-3)
    limit = standards_service.get_conductor_resistance_limit("Copper", 2.5, "2")
    assert limit.kind == "VERIFIED"
    assert outcome.result == ("PASS" if calc.calculated_value <= limit.value else "FAIL")


def test_conductor_resistance_class5_uses_the_class5_table_not_class2():
    # The exact regression class the review cites by name: Class 5's limit
    # must NOT silently fall back to Class 2's table at the same CSA.
    limit_class2 = standards_service.get_conductor_resistance_limit("Copper", 2.5, "2")
    limit_class5 = standards_service.get_conductor_resistance_limit("Copper", 2.5, "5")
    assert limit_class2.kind == "VERIFIED" and limit_class5.kind == "VERIFIED"
    assert limit_class2.value != limit_class5.value, (
        "Class 2 and Class 5 must resolve to different IS 8130 table values at the same CSA"
    )


def test_conductor_resistance_unknown_class_is_missing_not_defaulted():
    profile = _profile(conductor_class="99")
    calc, outcome = _run("TEST-0001", {
        "observed_resistance_mohm": 18.2, "specimen_length_m": 5.0, "room_temperature_c": 27.0,
    }, profile)
    assert calc.limit.kind == "MISSING"
    assert outcome.result == "UNDETERMINED"


def test_annealing_elongation():
    profile = _profile()
    calc, outcome = _run("TEST-0011", {
        "wire_diameter_mm": 0.3, "specimen_gauge_length_mm": 250.0, "length_after_break_mm": 297.5,
    }, profile)
    assert calc.calculated_value == pytest.approx(19.0, abs=0.01)


def test_aluminium_tensile():
    profile = _profile(conductor_material="Aluminium")
    calc, outcome = _run("TEST-0012", {
        "aluminium_grade": "Grade H4", "after_stranding": False,
        "wire_diameter_mm": 2.0, "breaking_load_n": 100.0,
    }, profile)
    assert calc.calculated_value == pytest.approx(31.83, abs=0.01)


def test_aluminium_wrapping_no_break_passes():
    profile = _profile(conductor_material="Aluminium")
    calc, outcome = _run("TEST-0013", {"wire_diameter_mm": 2.0, "wire_broke": False}, profile)
    assert outcome.result == "PASS"


def test_aluminium_wrapping_broke_fails():
    profile = _profile(conductor_material="Aluminium")
    calc, outcome = _run("TEST-0013", {"wire_diameter_mm": 2.0, "wire_broke": True}, profile)
    assert outcome.result == "FAIL"


# -- Dimensional tests ---------------------------------------------------------

def test_insulation_thickness_mean_and_pass():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0002", {"readings_mm": [0.82, 0.81, 0.85, 0.80, 0.83]}, profile, csa_mm2=2.5)
    assert calc.calculated_value == pytest.approx(0.822, abs=1e-3)
    nominal = standards_service.get_insulation_thickness_nominal(2.5)
    assert nominal.kind == "VERIFIED"
    # mean 0.822 is only (0.822-0.8)/0.8 = 2.75% above nominal 0.8 -- inside
    # the 3% guard band, so this is correctly borderline/UNDETERMINED, not a
    # clean PASS. (Confirmed independently: 2.75% < GUARD_BAND_PCT=3.0%.)
    assert outcome.result == "UNDETERMINED"
    assert outcome.confidence_state == "REVIEW_REQUIRED"


def test_insulation_thickness_one_low_reading_fails_the_individual_floor():
    # cl.8.3's individual-reading floor (nominal - (0.1+0.1*nominal)) is a
    # SEPARATE criterion from the mean -- a single reading below it must
    # not be masked by an otherwise-healthy mean (H8). Before H8 this was
    # reported as a FAIL against the MEAN's own limit (nominal, 0.8mm),
    # producing a misleadingly large ~-29% margin; it must now be reported
    # against the floor it actually violated, and named explicitly.
    profile = _profile(insulation_type="A")
    nominal = standards_service.get_insulation_thickness_nominal(2.5)
    assert nominal.kind == "VERIFIED"
    floor = round(nominal.value - (0.1 + 0.1 * nominal.value), 3)
    low_reading = round(floor - 0.05, 3)
    assert low_reading > 0
    calc, outcome = _run("TEST-0002", {"readings_mm": [0.95, 0.95, 0.95, 0.95, low_reading]}, profile, csa_mm2=2.5)
    assert outcome.result == "FAIL"
    expected_margin = round(((low_reading - floor) / floor) * 100, 1)
    assert outcome.margin_pct == pytest.approx(expected_margin, abs=0.05)
    assert outcome.explanation.startswith("lowest individual reading does not meet")


def test_insulation_thickness_mean_fails_but_individual_floor_passes():
    # The complementary case (H8): every individual reading clears its own
    # floor, but the mean itself falls short of nominal -- must be reported
    # as a MEAN failure, not attributed to the individual readings, which
    # are all perfectly fine on their own terms.
    profile = _profile(insulation_type="A")
    nominal = standards_service.get_insulation_thickness_nominal(2.5)
    assert nominal.kind == "VERIFIED"
    floor = round(nominal.value - (0.1 + 0.1 * nominal.value), 3)
    low_mean_reading = round(nominal.value - 0.1, 3)  # comfortably below nominal, still above the floor
    assert low_mean_reading > floor
    calc, outcome = _run("TEST-0002", {"readings_mm": [low_mean_reading] * 5}, profile, csa_mm2=2.5)
    assert outcome.result == "FAIL"
    assert outcome.explanation.startswith("mean of all readings does not meet")


def test_insulation_thickness_reports_both_criteria_explicitly():
    # H8: both acceptance criteria must be visible on the CalcResult
    # itself, not collapsed into a single overloaded value/limit pair.
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0002", {"readings_mm": [0.82, 0.81, 0.85, 0.80, 0.83]}, profile, csa_mm2=2.5)
    assert calc.criteria is not None and len(calc.criteria) == 2
    assert {c.name for c in calc.criteria} == {"mean of all readings", "lowest individual reading"}


def test_sheath_thickness_mean():
    profile = _profile(sheath_type="ST1")
    calc, outcome = _run("TEST-0014", {"readings_mm": [1.32, 1.29, 1.35, 1.28, 1.31]},
                          profile, csa_mm2=2.5, core_position="SHEATH")
    assert calc.calculated_value == pytest.approx(1.31, abs=1e-3)


def test_sheath_thickness_one_low_reading_fails_the_individual_floor():
    # Same two-criteria structure as insulation thickness, but sheath's
    # tolerance coefficient is 0.15, not 0.1 (cl.18.1.4) -- confirming this
    # test exercises the sheath-specific floor, not a copy-pasted
    # insulation one.
    profile = _profile(sheath_type="ST1")
    nominal = standards_service.get_sheath_thickness_nominal(2.5, 3)
    assert nominal.kind == "VERIFIED"
    floor = round(nominal.value - (0.1 + 0.15 * nominal.value), 3)
    low_reading = round(floor - 0.05, 3)
    assert low_reading > 0
    calc, outcome = _run(
        "TEST-0014", {"readings_mm": [nominal.value + 0.2] * 4 + [low_reading]},
        profile, csa_mm2=2.5, core_position="SHEATH",
    )
    assert outcome.result == "FAIL"
    assert outcome.explanation.startswith("lowest individual reading does not meet")


# -- Physical tests -------------------------------------------------------------

def test_tensile_strength():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0003", {"breaking_load_n": 210.0, "width_mm": 10.0, "thickness_mm": 1.6},
                          profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(13.12, abs=0.01)
    assert outcome.result == "PASS"  # Type A min 12.5 N/mm2


def test_tensile_strength_below_limit_fails():
    profile = _profile(insulation_type="A")
    limit = standards_service.get_insulation_limit("A", "tensile_strength_min_mpa")
    assert limit.kind == "VERIFIED"
    # Force a clearly-below-limit result -- well outside the 3% guard band.
    low_load = (limit.value * 0.5) * (10.0 * 1.6)
    calc, outcome = _run("TEST-0003", {"breaking_load_n": low_load, "width_mm": 10.0, "thickness_mm": 1.6},
                          profile, core_position="RED")
    assert outcome.result == "FAIL"


def test_elongation():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0004", {"initial_length_mm": 25.0, "final_length_mm": 68.0},
                          profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(172.0, abs=0.1)
    assert outcome.result == "PASS"  # Type A min 150%


def test_ageing_tensile_variation():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0015", {
        "before_tensile_mpa": 13.12, "breaking_load_n": 195.0, "width_mm": 10.0, "thickness_mm": 1.6,
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(7.09, abs=0.01)
    assert outcome.result == "PASS"  # Type A max variation 20%


def test_ageing_elongation_variation():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0016", {
        "before_elongation_pct": 172.0, "initial_length_mm": 25.0, "final_length_mm": 62.0,
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(13.95, abs=0.01)
    assert outcome.result == "PASS"


def test_loss_of_mass():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0017", {
        "initial_weight_mg": 850.0, "final_weight_mg": 848.5, "surface_area_cm2": 5.0,
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(0.3, abs=0.001)
    # Type A's loss_of_mass_max_mg_per_cm2 carries a documented caveat
    # (skb_seed_data.py: "NOT_PRINTED_IN_IS5831_SOURCE") -- correctly
    # PLACEHOLDER/UNDETERMINED since the C5 fix, not VERIFIED/PASS, even
    # though 0.3 is comfortably under the 2.0 limit. Asserting this here
    # too (not just in test_skb_caveats.py) proves the caveat actually
    # reaches this specific calculator's real output, end to end.
    assert calc.limit.kind == "PLACEHOLDER"
    assert outcome.result == "UNDETERMINED"


def test_shrinkage():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0018", {"length_before_mm": 200.0, "length_after_mm": 194.0},
                          profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(3.0, abs=0.01)
    assert outcome.result == "PASS"  # Type A max 4%


def test_heat_shock_no_crack_passes():
    profile = _profile()
    calc, outcome = _run("TEST-0019", {"cracks_observed": False}, profile, core_position="RED")
    assert outcome.result == "PASS"


def test_heat_shock_crack_fails():
    profile = _profile()
    calc, outcome = _run("TEST-0019", {"cracks_observed": True}, profile, core_position="RED")
    assert outcome.result == "FAIL"


def test_hot_deformation():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0020", {
        "t1_indentation_mm": [0.85, 0.83], "t2_reference_mm": [1.0, 0.98, 1.02, 0.99],
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(15.79, abs=0.01)
    assert outcome.result == "PASS"  # Type A max 50%


def test_thermal_stability():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0021", {"thermal_stability_minutes": 95.0}, profile, core_position="RED")
    assert calc.calculated_value == 95.0
    assert outcome.result == "PASS"  # Type A min 80 min


def test_oxygen_index():
    profile = _profile()
    calc, outcome = _run("TEST-0008", {"oxygen_index_pct": 29.3}, profile)
    assert calc.calculated_value == 29.3


def test_halogen_acid_gas():
    profile = _profile()
    calc, outcome = _run("TEST-0009", {
        "sample_weight_g": 1.0, "titration_b_ml": 12.5, "titration_a_ml": 0.5, "titration_factor": 1.0,
    }, profile)
    assert calc.calculated_value == pytest.approx(219.0, abs=0.1)


def test_temperature_index():
    profile = _profile()
    calc, outcome = _run("TEST-0010", {"temperature_index_c": 262.0}, profile)
    assert calc.calculated_value == 262.0


def test_smoke_density():
    profile = _profile()
    readings = [0, 5, 12, 18, 24, 29, 33, 37, 40, 43, 45, 47, 49, 50, 51, 52, 53]
    calc, outcome = _run("TEST-0022", {"readings_pct": readings}, profile)
    assert calc.calculated_value == pytest.approx(34.59, abs=0.01)


def test_flammability_burn_duration():
    profile = _profile()
    calc, outcome = _run("TEST-0023", {"burn_duration_after_removal_s": 12.0}, profile)
    assert calc.calculated_value == 12.0


def test_flammability_unaffected_length():
    profile = _profile()
    calc, outcome = _run("TEST-0024", {"unaffected_length_mm": 85.0}, profile)
    assert calc.calculated_value == 85.0


# -- Whole-cable electrical tests -----------------------------------------------

def test_hv_room_temp_no_breakdown_passes():
    profile = _profile()
    calc, outcome = _run("TEST-0005", {"breakdown_observed": False}, profile)
    assert outcome.result == "PASS"


def test_hv_room_temp_breakdown_fails():
    profile = _profile()
    calc, outcome = _run("TEST-0005", {"breakdown_observed": True}, profile)
    assert outcome.result == "FAIL"


def test_hv_water_immersion_no_breakdown_passes():
    profile = _profile()
    calc, outcome = _run("TEST-0025", {"breakdown_observed": False}, profile)
    assert outcome.result == "PASS"


def test_cold_bend_no_crack_passes():
    profile = _profile()
    calc, outcome = _run("TEST-0026", {"cracks_observed": False}, profile)
    assert outcome.result == "PASS"


def test_cold_impact_no_crack_passes():
    profile = _profile()
    calc, outcome = _run("TEST-0027", {"cracks_observed": False}, profile)
    assert outcome.result == "PASS"


def test_insulation_resistance_volume_resistivity():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0006", {
        "specimen_length_m": 5.0, "insulation_resistance_megaohm": 3200.0,
        "overall_diameter_mm": 14.5, "conductor_diameter_mm": 10.2,
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(28579343692806.42, rel=1e-6)
    # Type A's volume_resistivity_room_temp_min_ohm_cm carries a documented
    # caveat too (skb_seed_data.py: exponent inferred from a non-superscript
    # source cell) -- correctly PLACEHOLDER/UNDETERMINED since the C5 fix.
    assert calc.limit.kind == "PLACEHOLDER"
    assert outcome.result == "UNDETERMINED"


def test_insulation_resistance_constant():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0028", {
        "specimen_length_m": 5.0, "insulation_resistance_megaohm": 3200.0,
        "overall_diameter_mm": 14.5, "conductor_diameter_mm": 10.2,
    }, profile, core_position="RED")
    assert calc.calculated_value == pytest.approx(104.73409, abs=1e-3)
    assert outcome.result == "PASS"  # Type A min 36.7 M-ohm.km


def test_insulation_resistance_overall_diameter_must_exceed_conductor():
    profile = _profile(insulation_type="A")
    calc, outcome = _run("TEST-0006", {
        "specimen_length_m": 5.0, "insulation_resistance_megaohm": 3200.0,
        "overall_diameter_mm": 8.0, "conductor_diameter_mm": 10.2,  # inverted -- physically impossible
    }, profile, core_position="RED")
    assert calc.calculated_value is None
    assert outcome.result == "UNDETERMINED"


# -- Confidence-engine invariants (kind-space coverage) --------------------------
# The review's own named property: no PLACEHOLDER or MISSING limit can ever
# yield PASS or FAIL, regardless of which calculator (or synthetic input)
# produced it. confidence_engine.evaluate() checks limit.kind before doing
# any comparison at all, so this is exercised directly rather than via
# Hypothesis-generated calculators -- the branch structure itself is the
# thing under test, not calculator-specific arithmetic.

from app.engines.calculation_engine import CalcResult
from app.services.standards_service import LookupResult


@pytest.mark.parametrize("kind", ["MISSING", "PLACEHOLDER"])
def test_unverified_limit_never_produces_pass_or_fail(kind):
    limit = LookupResult(kind, 10.0 if kind == "PLACEHOLDER" else None, "unit", "some source",
                          note="synthetic test case")
    calc = CalcResult(calculated_value=999.0, calculated_unit="unit", limit=limit,
                       operator=">=", limit_value=10.0 if kind == "PLACEHOLDER" else None)
    outcome = confidence_evaluate(calc)
    assert outcome.result == "UNDETERMINED"
    assert outcome.confidence_state in ("BLOCKED", "REVIEW_REQUIRED")


def test_verified_limit_within_guard_band_is_undetermined_not_a_clean_pass():
    limit = LookupResult("VERIFIED", 10.0, "unit", "some source")
    calc = CalcResult(calculated_value=10.2, calculated_unit="unit", limit=limit,  # 2% above a >= 10 limit
                       operator=">=", limit_value=10.0)
    outcome = confidence_evaluate(calc)
    assert outcome.result == "UNDETERMINED"
    assert outcome.confidence_state == "REVIEW_REQUIRED"


def test_verified_limit_clearly_outside_guard_band_decides_pass_or_fail():
    limit = LookupResult("VERIFIED", 10.0, "unit", "some source")
    calc_pass = CalcResult(calculated_value=20.0, calculated_unit="unit", limit=limit, operator=">=", limit_value=10.0)
    calc_fail = CalcResult(calculated_value=5.0, calculated_unit="unit", limit=limit, operator=">=", limit_value=10.0)
    assert confidence_evaluate(calc_pass).result == "PASS"
    assert confidence_evaluate(calc_fail).result == "FAIL"
