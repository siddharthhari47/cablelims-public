"""
Regression test for the review's most serious correctness finding: a limit
value that skb_seed_data.py itself documents as inferred, secondary-sourced,
or absent from the printed standard (via a "{key}_flag" or row-level
"_provenance" caveat) was being returned as kind="VERIFIED", so it could
produce an automatic, confident PASS/FAIL -- exactly what
confidence_engine.py's own docstring says must never happen
("do not add a shortcut that returns PASS/FAIL from a PLACEHOLDER or MISSING
limit, no matter how tempting during a demo").

This test is intentionally data-driven -- it walks skb_seed_data.py's own
tables rather than hardcoding the handful of caveats that exist today, so it
keeps catching this class of bug as CTL's engineering data grows and new
caveats get added.
"""
import pytest

from app.services import skb_seed_data as skb
from app.services.standards_service import standards_service


def _caveated_insulation_cases():
    cases = []
    for insulation_type, row in skb.IS694_INSULATION_LIMITS.items():
        row_caveated = isinstance(row.get("_provenance"), str)
        for key, value in row.items():
            if key.startswith("_") or key.endswith("_flag") or value is None:
                continue
            key_caveated = isinstance(row.get(f"{key}_flag"), str)
            if row_caveated or key_caveated:
                cases.append((insulation_type, key))
    return cases


def _uncaveated_insulation_cases():
    cases = []
    for insulation_type, row in skb.IS694_INSULATION_LIMITS.items():
        if isinstance(row.get("_provenance"), str):
            continue
        for key, value in row.items():
            if key.startswith("_") or key.endswith("_flag") or value is None:
                continue
            if isinstance(row.get(f"{key}_flag"), str):
                continue
            cases.append((insulation_type, key))
    return cases


def _caveated_sheath_cases():
    cases = []
    for sheath_type, row in skb.IS694_SHEATH_LIMITS.items():
        row_caveated = isinstance(row.get("_provenance"), str)
        for key, value in row.items():
            if key.startswith("_") or key.endswith("_flag") or value is None:
                continue
            key_caveated = isinstance(row.get(f"{key}_flag"), str)
            if row_caveated or key_caveated:
                cases.append((sheath_type, key))
    return cases


def _uncaveated_sheath_cases():
    cases = []
    for sheath_type, row in skb.IS694_SHEATH_LIMITS.items():
        if isinstance(row.get("_provenance"), str):
            continue
        for key, value in row.items():
            if key.startswith("_") or key.endswith("_flag") or value is None:
                continue
            if isinstance(row.get(f"{key}_flag"), str):
                continue
            cases.append((sheath_type, key))
    return cases


@pytest.mark.parametrize("insulation_type,key", _caveated_insulation_cases())
def test_caveated_insulation_values_are_never_verified(insulation_type, key):
    result = standards_service.get_insulation_limit(insulation_type, key)
    assert result.kind != "VERIFIED", (
        f"Insulation Type {insulation_type}'s '{key}' carries a documented caveat in "
        "skb_seed_data.py but standards_service still returns kind=VERIFIED -- this is "
        "the exact bug that let an unverified limit produce an automatic PASS/FAIL."
    )
    assert result.kind == "PLACEHOLDER"
    assert result.note, "A caveated value must carry its caveat text forward as the LookupResult note"


@pytest.mark.parametrize("insulation_type,key", _uncaveated_insulation_cases())
def test_uncaveated_insulation_values_are_still_verified(insulation_type, key):
    # Regression guard: this fix must not turn every insulation limit into a
    # placeholder -- only the ones actually flagged.
    result = standards_service.get_insulation_limit(insulation_type, key)
    assert result.kind == "VERIFIED"


@pytest.mark.parametrize("sheath_type,key", _caveated_sheath_cases())
def test_caveated_sheath_values_are_never_verified(sheath_type, key):
    result = standards_service.get_sheath_limit(sheath_type, key)
    assert result.kind != "VERIFIED", (
        f"Sheath Type {sheath_type}'s '{key}' carries a documented caveat in "
        "skb_seed_data.py but standards_service still returns kind=VERIFIED."
    )
    assert result.kind == "PLACEHOLDER"
    assert result.note


@pytest.mark.parametrize("sheath_type,key", _uncaveated_sheath_cases())
def test_uncaveated_sheath_values_are_still_verified(sheath_type, key):
    result = standards_service.get_sheath_limit(sheath_type, key)
    assert result.kind == "VERIFIED"


def test_at_least_one_real_caveat_exists_so_this_test_isnt_vacuous():
    # Guards against this whole file silently testing nothing if
    # skb_seed_data.py's caveats are ever removed/renamed without updating
    # this test's discovery logic.
    assert len(_caveated_insulation_cases()) > 0
    assert len(_caveated_sheath_cases()) > 0


def test_placeholder_limit_never_produces_pass_or_fail_end_to_end():
    # The full pipeline: a caveated limit must route to UNDETERMINED via the
    # confidence engine, not just carry the right `kind` in isolation.
    from app.engines.calculation_engine import CalcResult
    from app.engines.confidence_engine import evaluate

    limit = standards_service.get_insulation_limit("A", "loss_of_mass_max_mg_per_cm2")
    assert limit.kind == "PLACEHOLDER"
    calc = CalcResult(calculated_value=0.3, calculated_unit="mg/cm2", limit=limit,
                       operator="<=", limit_value=limit.value)
    outcome = evaluate(calc)
    assert outcome.result == "UNDETERMINED"
    assert outcome.confidence_state == "REVIEW_REQUIRED"
    assert "NOT_PRINTED_IN_IS5831_SOURCE" in outcome.explanation
