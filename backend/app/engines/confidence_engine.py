"""
Confidence Engine -- implements the deterministic function from
CableLIMS_SDD_v2.md section 6.4.

    ALL of (limit VERIFIED, calculated value present, exactly one limit
      resolved, outside the guard band)          -> VERIFIED -> PASS/FAIL
    limit VERIFIED but result is inside the guard band (borderline)
      or limit is PLACEHOLDER                    -> REVIEW_REQUIRED -> UNDETERMINED
    limit MISSING, or a required raw input is absent -> BLOCKED -> UNDETERMINED

No other path to PASS/FAIL exists. This is the one place "never guess" is
enforced in code -- do not add a shortcut that returns PASS/FAIL from a
PLACEHOLDER or MISSING limit, no matter how tempting during a demo.
"""
from dataclasses import dataclass
from typing import Optional

from app.engines.calculation_engine import CalcResult

GUARD_BAND_PCT = 3.0  # within 3% of the limit is treated as borderline, not a clean pass


@dataclass
class DecisionOutcome:
    confidence_state: str   # VERIFIED | REVIEW_REQUIRED | BLOCKED
    result: str              # PASS | FAIL | UNDETERMINED
    margin_pct: Optional[float]
    explanation: str
    limit_source_kind: str
    limit_source_ref: Optional[str]


def _compare(value: float, operator: str, limit_value: float) -> bool:
    if operator == ">=":
        return value >= limit_value
    if operator == "<=":
        return value <= limit_value
    if operator == "==":
        return value == limit_value
    return False


def _margin(value: float, operator: str, limit_value: float) -> Optional[float]:
    if limit_value in (None, 0):
        return None
    if operator == ">=":
        return round(((value - limit_value) / limit_value) * 100, 1)
    if operator == "<=":
        return round(((limit_value - value) / limit_value) * 100, 1)
    return None


def evaluate(calc: CalcResult) -> DecisionOutcome:
    limit = calc.limit

    if calc.calculated_value is None:
        return DecisionOutcome(
            "BLOCKED", "UNDETERMINED", None,
            "Raw reading(s) not yet submitted or incomplete.",
            limit.kind, limit.source,
        )

    if limit.kind == "MISSING":
        return DecisionOutcome(
            "BLOCKED", "UNDETERMINED", None,
            f"No acceptance criterion available: {limit.note or 'not yet authored in the Standards Knowledge Base.'}",
            limit.kind, limit.source,
        )

    if limit.kind == "PLACEHOLDER":
        return DecisionOutcome(
            "REVIEW_REQUIRED", "UNDETERMINED", None,
            f"Acceptance limit is a placeholder pending Standards Knowledge Base verification "
            f"({limit.note or limit.source}). A Scientist must confirm this result manually.",
            limit.kind, limit.source,
        )

    # limit.kind == VERIFIED from here on
    # calc.note carries genuinely useful computed detail (e.g. the
    # intermediate after-ageing absolute value, or a correction-factor
    # breakdown) that calculation_engine.py already worked out but that
    # otherwise has nowhere to go -- appended here so it survives into
    # TestRun.result_explanation instead of being silently discarded.
    note_suffix = f" [{calc.note}]" if calc.note else ""

    if calc.operator == "==":
        passed = calc.calculated_value == calc.limit_value
        return DecisionOutcome(
            "VERIFIED", "PASS" if passed else "FAIL", None,
            f"Qualitative test, verified against {limit.source}.{note_suffix}",
            limit.kind, limit.source,
        )

    if calc.criteria:
        return _evaluate_criteria(calc, note_suffix)

    passed = _compare(calc.calculated_value, calc.operator, calc.limit_value)
    margin = _margin(calc.calculated_value, calc.operator, calc.limit_value)

    if margin is not None and abs(margin) <= GUARD_BAND_PCT:
        return DecisionOutcome(
            "REVIEW_REQUIRED", "UNDETERMINED", margin,
            f"Result is within {GUARD_BAND_PCT}% of the acceptance limit ({limit.source}) -- "
            f"borderline result, requires Scientist judgement rather than an automatic decision.{note_suffix}",
            limit.kind, limit.source,
        )

    return DecisionOutcome(
        "VERIFIED", "PASS" if passed else "FAIL", margin,
        f"Verified against {limit.source}.{note_suffix}",
        limit.kind, limit.source,
    )


def _evaluate_criteria(calc: CalcResult, note_suffix: str) -> DecisionOutcome:
    """H8: a test with more than one independent acceptance criterion (e.g.
    insulation/sheath thickness: mean AND individual-reading floor) is
    evaluated criterion-by-criterion here, instead of collapsing everything
    into the single (calculated_value, limit_value) pair the rest of this
    module uses -- see calculation_engine.Criterion's docstring for exactly
    what that collapsing used to get wrong (the reported margin was
    sometimes measured against the wrong criterion's own limit)."""
    limit = calc.limit
    rows = [
        (c, _compare(c.calculated_value, c.operator, c.limit_value), _margin(c.calculated_value, c.operator, c.limit_value))
        for c in calc.criteria
    ]
    detail = "; ".join(
        f"{c.name} {c.calculated_value}{c.operator}{c.limit_value} ({'meets' if passed else 'FAILS'} its limit)"
        for c, passed, _ in rows
    )

    failing = [(c, margin) for c, passed, margin in rows if not passed]
    if failing:
        # The failing criterion with the largest relative miss is the
        # dominant reason this test failed; its own margin (against its OWN
        # limit, not some other criterion's) is what's reported -- every
        # criterion's individual pass/fail still appears in `detail` so
        # nothing is hidden behind whichever one happens to be "worst".
        worst_criterion, worst_margin = min(failing, key=lambda cm: cm[1] if cm[1] is not None else 0)
        # Same guard-band philosophy as the single-criterion path below: a
        # near-miss FAIL is exactly as borderline as a near-miss PASS, and
        # gets the same "ask a Scientist" treatment rather than an automatic
        # clean FAIL -- the single-value path already applied the guard
        # band unconditionally (regardless of pass/fail direction); this
        # must not become stricter than that just because it now has to
        # pick which criterion's margin to check.
        if worst_margin is not None and abs(worst_margin) <= GUARD_BAND_PCT:
            return DecisionOutcome(
                "REVIEW_REQUIRED", "UNDETERMINED", worst_margin,
                f"{worst_criterion.name} is within {GUARD_BAND_PCT}% of its acceptance limit ({limit.source}) -- "
                f"borderline result, requires Scientist judgement rather than an automatic decision ({detail}).{note_suffix}",
                limit.kind, limit.source,
            )
        return DecisionOutcome(
            "VERIFIED", "FAIL", worst_margin,
            f"{worst_criterion.name} does not meet its acceptance criterion, verified against "
            f"{limit.source} ({detail}).{note_suffix}",
            limit.kind, limit.source,
        )

    # Every criterion passes. The guard band must key off whichever
    # criterion sits CLOSEST to its own limit -- not whichever single value
    # calc_* happened to surface as "the" calculated_value, which could
    # silently hide a borderline individual-reading floor behind a
    # comfortably-passing mean (exactly the scenario this refactor exists
    # to stop hiding).
    tightest_criterion, tightest_margin = min(
        ((c, margin) for c, _, margin in rows),
        key=lambda cm: cm[1] if cm[1] is not None else float("inf"),
    )
    if tightest_margin is not None and abs(tightest_margin) <= GUARD_BAND_PCT:
        return DecisionOutcome(
            "REVIEW_REQUIRED", "UNDETERMINED", tightest_margin,
            f"{tightest_criterion.name} is within {GUARD_BAND_PCT}% of its acceptance limit ({limit.source}) -- "
            f"borderline result, requires Scientist judgement rather than an automatic decision ({detail}).{note_suffix}",
            limit.kind, limit.source,
        )

    return DecisionOutcome(
        "VERIFIED", "PASS", tightest_margin,
        f"All criteria verified against {limit.source} ({detail}).{note_suffix}",
        limit.kind, limit.source,
    )
