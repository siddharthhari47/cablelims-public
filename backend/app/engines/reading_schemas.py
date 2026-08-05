"""
Typed, bounded validation for TestRun.raw_values -- one Pydantic model per
test_id, registered in READING_SCHEMAS below.

Previously `SubmitReadingRequest.raw_values` was a bare `dict`: any JSON
object was accepted and handed straight to the calculator. Concretely, that
meant:
  - A typo'd field name (e.g. "specimen_length_mm" instead of "..._m") was
    silently read as missing by `_num()`, producing a MISSING-limit
    UNDETERMINED that looks exactly like a genuine Standards Knowledge Base
    gap -- a misdiagnosis, not an error.
  - Physically impossible values were accepted outright: a negative length,
    a room temperature that sends get_temperature_correction_factor's
    `250/(230+t)` toward a division by zero, a percentage above 100.
  - A qualitative field like `cracks_observed` did a bare Python truthy
    check (`0.0 if cracked else 1.0`) -- the JSON string "false" is truthy
    in Python, so it would flip a passing specimen to FAIL with no error at
    all. Pydantic's bool coercion correctly parses "true"/"false" strings
    (and rejects anything else), so this class of bug is closed structurally
    by validating through these models rather than trusting `raw.get()`.
  - A malformed list value (e.g. a non-numeric reading) reached
    `[float(v) for v in readings]` with no try/except -> unhandled
    ValueError -> HTTP 500 with a stack trace, not a clean error to the
    caller.

Every model below is deliberately shaped to match the corresponding
TestDefinition.input_schema in seed.py exactly (same keys, same
"count"-bounded list lengths) -- these are not independently invented
bounds, they're the frontend's own declared input contract, now actually
enforced server-side instead of existing only as a UI hint. Bounds beyond
"matches input_schema" (e.g. room_temperature_c's range) are documented
inline with the specific hazard they close.

`submit_reading` validates against this registry before calling
run_calculation; the validated model's `.model_dump()` -- still a plain
dict -- is what actually reaches the calculators, so none of the 27
functions in calculation_engine.py needed to change.
"""
from typing import List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictReading(BaseModel):
    """Base for every per-test reading model: unknown keys are rejected
    outright (extra="forbid") rather than silently ignored, so a mistyped
    field name is a loud 422 at submission time instead of a MISSING-limit
    UNDETERMINED discovered downstream that looks like a Standards
    Knowledge Base gap."""
    model_config = ConfigDict(extra="forbid")


# -- Shared shapes (byte-identical across multiple tests) -------------------

class QualitativeCrackReading(_StrictReading):
    """TEST-0019 Heat Shock, TEST-0026 Cold Bend, TEST-0027 Cold Impact --
    all three ask the same yes/no question."""
    cracks_observed: bool


class BreakdownReading(_StrictReading):
    """TEST-0005 HV Room Temp, TEST-0025 HV Water Immersion."""
    breakdown_observed: bool


class FiveThicknessReadings(_StrictReading):
    """TEST-0002 Insulation Thickness, TEST-0014 Sheath Thickness -- both
    declare "count": 5 in their input_schema."""
    readings_mm: List[float] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _positive_readings(self):
        if any(v <= 0 for v in self.readings_mm):
            raise ValueError("Every thickness reading must be a positive number of mm")
        return self


# -- Conductor tests ----------------------------------------------------------

class ConductorResistanceReading(_StrictReading):
    observed_resistance_mohm: float = Field(gt=0)
    specimen_length_m: float = Field(gt=0)
    # Bounded well clear of -230 degC, where
    # get_temperature_correction_factor's kt = 250/(230+t) divides by zero.
    # This is a generous real-world lab-ambient range, not a guess at CTL's
    # exact spec -- wide enough to never reject a genuine reading, narrow
    # enough to catch a clearly wrong entry (a typo'd extra digit, a unit
    # mixup with Fahrenheit, etc).
    room_temperature_c: float = Field(ge=-40, le=80)


class AnnealingElongationReading(_StrictReading):
    wire_diameter_mm: float = Field(gt=0)
    specimen_gauge_length_mm: float = Field(gt=0)
    length_after_break_mm: float = Field(gt=0)


class AluminiumTensileReading(_StrictReading):
    # Matches input_schema's exact "options" list -- an unlisted grade is
    # now a loud validation error instead of silently reaching
    # get_aluminium_tensile_grade_limit() and returning MISSING.
    aluminium_grade: Literal["Grade 0", "Grade H2", "Grade H4"]
    after_stranding: bool = False
    wire_diameter_mm: float = Field(gt=0)
    breaking_load_n: float = Field(gt=0)


class AluminiumWrappingReading(_StrictReading):
    # wire_diameter_mm is part of input_schema (and the frontend sends it)
    # even though calc_aluminium_wrapping doesn't currently read it -- kept
    # here so a real submission isn't rejected for a field the UI legitimately
    # collects.
    wire_diameter_mm: float = Field(gt=0)
    wire_broke: bool


# -- Dimensional tests --------------------------------------------------------

InsulationThicknessReading = FiveThicknessReadings
SheathThicknessReading = FiveThicknessReadings


# -- Physical tests on insulation / sheath ------------------------------------

class TensileStrengthReading(_StrictReading):
    breaking_load_n: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)


class ElongationReading(_StrictReading):
    initial_length_mm: float = Field(gt=0)
    final_length_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def _final_exceeds_initial(self):
        # A specimen physically stretches before breaking -- final length at
        # or below the initial gauge length is not a real elongation-at-break
        # reading (most likely a data-entry swap of the two fields).
        if self.final_length_mm <= self.initial_length_mm:
            raise ValueError("final_length_mm must be greater than initial_length_mm (the specimen stretches before breaking)")
        return self


class AgeingTensileVariationReading(_StrictReading):
    before_tensile_mpa: float = Field(gt=0)
    breaking_load_n: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)


class AgeingElongationVariationReading(_StrictReading):
    before_elongation_pct: float = Field(gt=0)
    initial_length_mm: float = Field(gt=0)
    final_length_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def _final_exceeds_initial(self):
        if self.final_length_mm <= self.initial_length_mm:
            raise ValueError("final_length_mm must be greater than initial_length_mm (the specimen stretches before breaking)")
        return self


class LossOfMassReading(_StrictReading):
    initial_weight_mg: float = Field(gt=0)
    final_weight_mg: float = Field(gt=0)
    surface_area_cm2: float = Field(gt=0)
    # No initial > final ordering constraint: a specimen can genuinely gain a
    # small amount of mass (moisture pickup), so this isn't "impossible
    # data" the way a swapped elongation reading is -- see calculation_engine
    # calc_loss_of_mass's own note on the resulting negative-loss/PASS
    # interaction, which is a confidence-engine/decision-rule question, not
    # an input-validation one, and is intentionally NOT addressed here.


class ShrinkageReading(_StrictReading):
    length_before_mm: float = Field(gt=0)
    length_after_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def _length_does_not_grow(self):
        # B11 (Review #2 remediation): unlike LossOfMassReading's genuine
        # moisture-pickup case above, a specimen *growing* under the 150 C /
        # 15 min shrinkage protocol is not a real physical reading -- it's a
        # swapped-field data-entry error, exactly like ElongationReading's
        # own guard above. Without this, length_after_mm > length_before_mm
        # yields a negative shrinkage percentage, which sails through a
        # "<=" limit as a comfortable, wrong PASS.
        if self.length_after_mm > self.length_before_mm:
            raise ValueError("length_after_mm cannot exceed length_before_mm (a specimen does not grow under this test)")
        return self


HeatShockReading = QualitativeCrackReading


class HotDeformationReading(_StrictReading):
    # input_schema declares "count": 2 and "count": 4 respectively, matching
    # the documented protocol (2 specimens for T1, 2 readings each for T2).
    t1_indentation_mm: List[float] = Field(min_length=2, max_length=2)
    t2_reference_mm: List[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _positive_readings(self):
        if any(v <= 0 for v in self.t1_indentation_mm) or any(v <= 0 for v in self.t2_reference_mm):
            raise ValueError("Every thickness reading must be a positive number of mm")
        return self


class ThermalStabilityReading(_StrictReading):
    thermal_stability_minutes: float = Field(gt=0)


class OxygenIndexReading(_StrictReading):
    oxygen_index_pct: float = Field(ge=0, le=100)


class HalogenAcidGasReading(_StrictReading):
    sample_weight_g: float = Field(gt=0)
    titration_b_ml: float = Field(ge=0)
    titration_a_ml: float = Field(ge=0)
    titration_factor: float = Field(gt=0)

    @model_validator(mode="after")
    def _a_does_not_exceed_b(self):
        # B11 (Review #2 remediation): calc_halogen_acid_gas computes
        # HCl% proportional to (B - A) -- titration_a_ml > titration_b_ml
        # yields a negative HCl%, an impossible physical result (a
        # swapped-field data-entry error), which would otherwise sail
        # through a "<=" limit as a comfortable, wrong PASS.
        if self.titration_a_ml > self.titration_b_ml:
            raise ValueError("titration_a_ml cannot exceed titration_b_ml (this would yield a negative HCl%)")
        return self


class TemperatureIndexReading(_StrictReading):
    temperature_index_c: float = Field(ge=0, le=500)


class SmokeDensityReading(_StrictReading):
    # input_schema: "count": 17 (t=0 through t=240s at 15s intervals).
    readings_pct: List[float] = Field(min_length=17, max_length=17)

    @model_validator(mode="after")
    def _bounded_readings(self):
        if any(v < 0 or v > 100 for v in self.readings_pct):
            raise ValueError("Every light-absorption reading must be between 0 and 100 (%)")
        return self


class FlammabilityBurnDurationReading(_StrictReading):
    burn_duration_after_removal_s: float = Field(ge=0)


class FlammabilityUnaffectedLengthReading(_StrictReading):
    unaffected_length_mm: float = Field(ge=0)


# -- Whole-cable electrical tests ---------------------------------------------

class InsulationResistanceReading(_StrictReading):
    specimen_length_m: float = Field(gt=0)
    insulation_resistance_megaohm: float = Field(gt=0)
    overall_diameter_mm: float = Field(gt=0)
    conductor_diameter_mm: float = Field(gt=0)


InsulationResistanceConstantReading = InsulationResistanceReading

HvRoomTempReading = BreakdownReading
HvWaterImmersionReading = BreakdownReading
ColdBendReading = QualitativeCrackReading
ColdImpactReading = QualitativeCrackReading


READING_SCHEMAS: dict = {
    "TEST-0001": ConductorResistanceReading,
    "TEST-0002": InsulationThicknessReading,
    "TEST-0003": TensileStrengthReading,
    "TEST-0004": ElongationReading,
    "TEST-0005": HvRoomTempReading,
    "TEST-0006": InsulationResistanceReading,
    # TEST-0007 is intentionally absent -- it's also missing from
    # calculation_engine.CALCULATORS (a pre-existing gap, see that module's
    # docstring/the codebase's own known-issues) and, per this project's
    # "never guess" principle, no calculator or schema is fabricated for it
    # here without confirming what it actually is against CTL's source
    # documents.
    "TEST-0008": OxygenIndexReading,
    "TEST-0009": HalogenAcidGasReading,
    "TEST-0010": TemperatureIndexReading,
    "TEST-0011": AnnealingElongationReading,
    "TEST-0012": AluminiumTensileReading,
    "TEST-0013": AluminiumWrappingReading,
    "TEST-0014": SheathThicknessReading,
    "TEST-0015": AgeingTensileVariationReading,
    "TEST-0016": AgeingElongationVariationReading,
    "TEST-0017": LossOfMassReading,
    "TEST-0018": ShrinkageReading,
    "TEST-0019": HeatShockReading,
    "TEST-0020": HotDeformationReading,
    "TEST-0021": ThermalStabilityReading,
    "TEST-0022": SmokeDensityReading,
    "TEST-0023": FlammabilityBurnDurationReading,
    "TEST-0024": FlammabilityUnaffectedLengthReading,
    "TEST-0025": HvWaterImmersionReading,
    "TEST-0026": ColdBendReading,
    "TEST-0027": ColdImpactReading,
    "TEST-0028": InsulationResistanceConstantReading,
}


def get_reading_schema(test_id: str) -> Optional[Type[BaseModel]]:
    return READING_SCHEMAS.get(test_id)
