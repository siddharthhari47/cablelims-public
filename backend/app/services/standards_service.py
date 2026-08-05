"""
Standards Service -- query interface over the Standards Knowledge Base.

This is the ONLY module the rest of the application is allowed to ask for an
engineering number. Every function returns a `LookupResult`, which always
carries provenance and a `kind` (VERIFIED / PLACEHOLDER / MISSING) -- callers
(the calculation and confidence engines) must key their behaviour off `kind`,
never assume a returned number is trustworthy just because it exists.

Today this reads from `skb_seed_data.py` (a Python module). Later this
becomes a real Standards Knowledge Base service (its own versioned database,
populated by the Sprint Priority 2 Excel Import Engine) -- when that
happens, only this file's internals change; every caller (engines/
calculation_engine.py, engines/confidence_engine.py) keeps working
unmodified because the function signatures and LookupResult shape do not
change.
"""
from dataclasses import dataclass
from typing import Any, Optional

from app.services import skb_seed_data as skb


@dataclass
class LookupResult:
    kind: str          # "VERIFIED" | "PLACEHOLDER" | "MISSING"
    value: Optional[Any]
    unit: Optional[str]
    source: Optional[str]
    note: Optional[str] = None


class StandardsService:
    """Swap this class's internals for a real SKB-backed implementation later.
    Every method signature here is the contract the rest of the app depends on."""

    # -- conductor resistance -------------------------------------------------
    def get_conductor_resistance_limit(self, material: str, csa_mm2: float, conductor_class: Optional[str] = None) -> LookupResult:
        """conductor_class selects which IS 8130 table applies (1/2/5/6 --
        see skb_seed_data.py's IS8130_RESISTANCE_OHM_PER_KM). A Class 5
        conductor is NOT interchangeable with Class 2 at the same CSA --
        the max resistance genuinely differs between tables. Missing/unknown
        class is MISSING, never silently defaulted to another class's table."""
        if not conductor_class or str(conductor_class) not in skb.IS8130_RESISTANCE_OHM_PER_KM:
            return LookupResult("MISSING", None, "ohm/km", None,
                                 note=f"No IS 8130 resistance table for conductor class '{conductor_class}' "
                                      "-- the profile's conductor class must be one of "
                                      f"{sorted(skb.IS8130_RESISTANCE_OHM_PER_KM.keys())}.")
        class_key = str(conductor_class)
        table = skb.IS8130_RESISTANCE_OHM_PER_KM[class_key]
        row = table.get(csa_mm2)
        if not row:
            return LookupResult("MISSING", None, "ohm/km", None,
                                 note=f"No IS 8130 Table entry for Class {class_key} at CSA={csa_mm2} mm2")
        key = "copper_plain" if material == "Copper" else "aluminium"
        value = row.get(key)
        if value is None:
            return LookupResult("MISSING", None, "ohm/km", None,
                                 note=f"No {material} entry for Class {class_key} at CSA={csa_mm2} mm2 in IS 8130")
        return LookupResult("VERIFIED", value, "ohm/km", skb.IS8130_RESISTANCE_SOURCE_BY_CLASS[class_key])

    def get_temperature_correction_factor(self, temp_c: float) -> LookupResult:
        kt = skb.is8130_table6_kt(temp_c)
        return LookupResult("VERIFIED", round(kt, 4), "factor", skb.IS8130_TABLE6_SOURCE)

    def get_allowed_conductor_classes(self, material: str, csa_mm2: float) -> LookupResult:
        for rule in skb.IS8130_ALLOWED_CONDUCTOR_CLASSES:
            if rule["material"] != material:
                continue
            if rule["csa_values"] == "gt10":
                if csa_mm2 > 10:
                    return LookupResult("VERIFIED", rule["classes"], "class", skb.CONDUCTOR_RULES_SOURCE)
            elif csa_mm2 in rule["csa_values"]:
                return LookupResult("VERIFIED", rule["classes"], "class", skb.CONDUCTOR_RULES_SOURCE)
        return LookupResult("MISSING", None, "class", None,
                             note=f"No conductor class rule for {material} at {csa_mm2} mm2")

    # -- conductor material tests (annealing / aluminium tensile / wrapping) --
    def get_annealing_elongation_min(self, wire_diameter_mm: float) -> LookupResult:
        for lo, hi, min_pct in skb.IS8130_ANNEALING_ELONGATION_MIN_PCT_BY_WIRE_DIA:
            if (lo is None or wire_diameter_mm > lo) and (hi is None or wire_diameter_mm <= hi):
                return LookupResult("VERIFIED", min_pct, "%", skb.IS8130_ANNEALING_SOURCE)
        return LookupResult("MISSING", None, "%", None, note="Wire diameter out of banded range")

    def get_annealing_after_stranding_limit(self) -> LookupResult:
        return LookupResult("MISSING", None, "%", None,
                             note="IS 8130:2013 clause 7.1.2.2 explicitly states this limit is "
                                  "'Under consideration' -- there is no numeric limit to compare "
                                  "against, by the standard's own admission, not a data gap on our side.")

    def get_aluminium_tensile_grade_limit(self, grade: str, after_stranding: bool) -> LookupResult:
        # H12: skb_seed_data.py deliberately carries no type annotations on
        # its module-level constants (see that file's own docstring -- it's
        # explicitly "the only place engineering numbers live" and is kept
        # as plain, easy-to-diff-and-verify Python literals, not a typed
        # schema) -- mypy infers these dict/list values as `object`. This
        # is a real value at runtime (proven by the golden-value test
        # suite), just untyped; ignored here rather than adding type
        # annotations to that especially sensitive source-of-truth file.
        bands = skb.IS8130_ALUMINIUM_TENSILE_GRADE_BANDS_MPA["before_stranding"]
        band = next((b for b in bands if b[2] == grade), None)  # type: ignore[attr-defined]
        if not band:
            return LookupResult("MISSING", None, "N/mm2", None, note=f"Unknown aluminium grade {grade}")
        lo, hi, _ = band
        pct = skb.IS8130_ALUMINIUM_TENSILE_GRADE_BANDS_MPA["after_stranding_pct_of_before"]
        value = {"min": lo, "max": hi}
        if after_stranding and lo is not None:
            value["min"] = round(lo * pct / 100.0, 2)
        return LookupResult("VERIFIED", value, "N/mm2", skb.IS8130_ALUMINIUM_TENSILE_SOURCE)

    def get_wrapping_test_criterion(self) -> LookupResult:
        return LookupResult("VERIFIED", "no_break", None, skb.IS8130_WRAPPING_SOURCE)

    # -- insulation / sheath dimensions --------------------------------------
    def get_insulation_thickness_nominal(self, csa_mm2: float) -> LookupResult:
        val = skb.IS694_TABLE5_INSULATION_THICKNESS_MM.get(csa_mm2)
        if val is None:
            return LookupResult("MISSING", None, "mm", None,
                                 note=f"No IS 694 Table 5 entry for CSA={csa_mm2} mm2")
        return LookupResult("VERIFIED", val, "mm", skb.IS694_TABLE5_SOURCE)

    def get_sheath_thickness_nominal(self, csa_mm2: float, cores: int) -> LookupResult:
        by_csa = skb.IS694_SHEATH_THICKNESS_NOMINAL_MM.get(csa_mm2)
        if by_csa is None:
            return LookupResult("MISSING", None, "mm", None,
                                 note=f"No verified sheath-thickness nominal for CSA={csa_mm2} mm2 -- "
                                      "outside IS 694 Table 5's tabulated CSA range.")
        # Table 5 only tabulates up to 4 cores by name; >4-core constructions
        # use a different IS 694 table (6/7/9) not yet in this seed.
        capped_cores = min(cores, 4) if cores else None
        value = by_csa.get(capped_cores)
        if value is None:
            return LookupResult("MISSING", None, "mm", None,
                                 note=f"IS 694 Table 5 does not tabulate {cores}-core at CSA={csa_mm2} mm2 "
                                      "(this combination is absent from the source table, not an extraction gap).")
        return LookupResult("VERIFIED", value, "mm", skb.IS694_SHEATH_THICKNESS_SOURCE)

    # -- qualitative / fixed-parameter tests ------------------------------------
    def get_qualitative_limit(self, key: str) -> LookupResult:
        row = skb.IS694_QUALITATIVE_LIMITS.get(key)
        if not row:
            return LookupResult("MISSING", None, None, None, note=f"No qualitative limit for {key}")
        source = row.get("source")
        return LookupResult("VERIFIED", row, None, source)  # type: ignore[arg-type]  # see get_aluminium_tensile_grade_limit's note above

    # -- insulation-type-keyed limits (Type A/C/D) -----------------------------
    def get_insulation_limit(self, insulation_type: str, key: str) -> LookupResult:
        row = skb.IS694_INSULATION_LIMITS.get(insulation_type)
        if not row:
            return LookupResult("MISSING", None, None, None, note=f"Unknown insulation type '{insulation_type}'")
        value = row.get(key)  # type: ignore[attr-defined]  # see get_aluminium_tensile_grade_limit's note above
        if value is None:
            return LookupResult("MISSING", None, None, None,
                                 note=f"No verified '{key}' limit for Insulation Type {insulation_type} "
                                      "-- blank/not captured in CTL's own reference table.")
        caveat = self._caveat_for(row, key)  # type: ignore[arg-type]
        if caveat:
            # A value skb_seed_data.py itself documents as inferred, secondary-
            # sourced, or absent from the printed standard must never be graded
            # as an automatic PASS/FAIL -- PLACEHOLDER routes it to the
            # confidence engine's REVIEW_REQUIRED/UNDETERMINED path instead,
            # with this caveat text carried into TestRun.result_explanation
            # (see confidence_engine.evaluate's PLACEHOLDER branch) so a
            # Scientist actually sees *why* before confirming it. Previously
            # this returned VERIFIED unconditionally and the caveat, though
            # captured here, was discarded before reaching anyone.
            return LookupResult("PLACEHOLDER", value, None, skb.IS694_INSULATION_LIMITS_SOURCE, note=caveat)
        return LookupResult("VERIFIED", value, None, skb.IS694_INSULATION_LIMITS_SOURCE)

    # -- sheath-type-keyed limits (ST1/ST2/ST3) --------------------------------
    def get_sheath_limit(self, sheath_type: str, key: str) -> LookupResult:
        row = skb.IS694_SHEATH_LIMITS.get(sheath_type)
        if not row:
            return LookupResult("MISSING", None, None, None, note=f"Unknown sheath type '{sheath_type}'")
        value = row.get(key)  # type: ignore[attr-defined]  # see get_aluminium_tensile_grade_limit's note above
        if value is None:
            return LookupResult("MISSING", None, None, None,
                                 note=f"No verified '{key}' limit for Sheath Type {sheath_type} "
                                      "-- blank/not captured in CTL's own reference table.")
        caveat = self._caveat_for(row, key)  # type: ignore[arg-type]
        if caveat:
            return LookupResult("PLACEHOLDER", value, None, skb.IS694_SHEATH_LIMITS_SOURCE, note=caveat)
        return LookupResult("VERIFIED", value, None, skb.IS694_SHEATH_LIMITS_SOURCE)

    @staticmethod
    def _caveat_for(row: dict, key: str) -> Optional[str]:
        """A caveat can apply at two granularities in skb_seed_data.py's
        convention: a specific key ("{key}_flag", e.g. one ambiguously-
        typeset cell) or the whole row ("_provenance", e.g. Insulation Type D
        and Sheath Type ST3, which are CTL's own operational classifications
        entirely absent from IS 5831:1984, not merely one uncertain cell
        within an otherwise-verified type). Either one means this specific
        value is not something the standard itself verifies."""
        key_flag = row.get(f"{key}_flag")
        if isinstance(key_flag, str):
            return key_flag
        row_provenance = row.get("_provenance")
        if isinstance(row_provenance, str):
            return row_provenance
        return None

    # -- generic "no criterion authored yet" case -------------------------------
    def missing(self, note: str) -> LookupResult:
        return LookupResult("MISSING", None, None, None, note=note)

    def pending_verification(self, note: str, value: Optional[Any] = None, unit: Optional[str] = None) -> LookupResult:
        """For values whose formula/relationship is known to be ambiguous and
        explicitly deferred to CTL confirmation (see skb_seed_data.py's
        HOT_DEFORMATION_FORMULA_STATUS) -- distinct from MISSING (no data at
        all) so the UI can explain *why* differently."""
        return LookupResult("PLACEHOLDER", value, unit, "PENDING_VERIFICATION_FROM_CTL", note=note)


standards_service = StandardsService()
