"""
Rule Engine -- test assignment.

Reads TestAssignmentRule rows from the database (config, authored per
CableLIMS_SDD_v2.md as workbook-equivalent data) and evaluates a small, safe
condition grammar against a sample's CableProfile. No engineering logic or
test-applicability decision is hardcoded here -- only the grammar/evaluator
is code; the actual rules are data.

Grammar supported (deliberately minimal; CableLIMS_SDD_v2.md section
4.12-equivalent full grammar is a later hardening item):
    "always"
    "<field> in (v1,v2,v3)"
    "<field> == value"

Sprint Priority 1 addition: `expand_for_positions` -- a test's applicability
(this module's original job) is a separate concern from how many
AssignedTest rows it produces (a test scoped PER_CORE_AND_SHEATH needs one
row per tested core color plus one for the sheath). That expansion is
driven by TestDefinition.scope and the profile's core-color selection, not
by another rule -- it is structural, not a business rule, so it stays out
of the condition grammar above.
"""
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import CableProfile, TestAssignmentRule, TestDefinition

# IS 694 Table 2 core-identification colour sequence, as used in CTL's own
# Calculations.xlsx per-core sheet naming (R/Y/B/BLK) and confirmed by the
# Test Report's observed core-identification row for a 4-core sample.
CORE_COLOR_SEQUENCE = ["RED", "YELLOW", "BLUE", "BLACK"]

# A sample can only be tested per-named-color up to this many cores with the
# current colour/limit modelling. Above this, the Scientist selects how many
# REPRESENTATIVE cores to test (Sprint Priority 9 requirement) rather than
# every physical core -- matching CTL's own practice of using a different,
# correctly-sized observation-sheet template per core count rather than
# testing arbitrarily many cores on one form.
MAX_NAMED_CORE_COLORS = 4


def suggested_core_colors(cores: int) -> Optional[List[str]]:
    """Returns a SUGGESTED colour sequence for the UI to pre-fill as a
    starting point only -- e.g. ["RED","YELLOW","BLUE"] for a 3-core
    sample. This is never applied automatically: the Scientist/Assistant
    must explicitly confirm (or change) the core-to-colour assignment
    during profiling before a profile can be submitted. See
    api/samples.py submit_profile, which requires tested_core_colors to
    be supplied in the request body and rejects the request if it is
    missing. >4 cores: return None -- there is no standard colour beyond
    BLACK, so the UI must not suggest one; the Scientist enters the
    tested core count/labels manually."""
    if cores is None:
        return None
    if cores <= MAX_NAMED_CORE_COLORS:
        return CORE_COLOR_SEQUENCE[:cores]
    return None


@dataclass
class RuleEvalOutcome:
    test_id: str
    mandatory: bool
    matched_rule_id: str
    clause_reference: str


@dataclass
class ExpandedTestOutcome:
    test_id: str
    mandatory: bool
    matched_rule_id: str
    clause_reference: str
    core_position: Optional[str]   # None | "RED"|"YELLOW"|"BLUE"|"BLACK"|"SHEATH"


def _profile_field(profile: CableProfile, field: str):
    return getattr(profile, field, None)


def _evaluate_condition(condition: str, profile: CableProfile) -> bool:
    condition = condition.strip()
    if condition.lower() == "always":
        return True
    if " in (" in condition:
        field, rest = condition.split(" in (", 1)
        field = field.strip()
        values = [v.strip() for v in rest.rstrip(")").split(",")]
        return str(_profile_field(profile, field)) in values
    if "==" in condition:
        field, value = condition.split("==", 1)
        return str(_profile_field(profile, field.strip())) == value.strip()
    return False


def assign_tests(db: Session, standard_id: str, profile: CableProfile) -> List[RuleEvalOutcome]:
    rules = (
        db.query(TestAssignmentRule)
        .filter(TestAssignmentRule.standard_id == standard_id)
        .order_by(TestAssignmentRule.priority.asc())
        .all()
    )
    outcomes: List[RuleEvalOutcome] = []
    seen_tests = set()
    for rule in rules:
        if rule.test_id in seen_tests:
            continue
        if _evaluate_condition(rule.condition, profile):
            outcomes.append(
                RuleEvalOutcome(
                    test_id=rule.test_id,
                    mandatory=rule.mandatory,
                    matched_rule_id=rule.rule_id,
                    clause_reference=rule.clause_reference or "",
                )
            )
            seen_tests.add(rule.test_id)
    return outcomes


def expand_for_positions(db: Session, outcomes: List[RuleEvalOutcome], profile: CableProfile) -> List[ExpandedTestOutcome]:
    """Turn 'this test applies' into 'these are the AssignedTest rows it
    produces', using each TestDefinition's scope and the profile's tested
    core colors. Requires profile.tested_core_colors to be set for any
    PER_CORE / PER_CORE_AND_SHEATH test to expand -- if it's not set (e.g. a
    >4-core sample where the Scientist hasn't chosen a count yet), those
    tests are silently skipped here (not assigned) rather than guessed;
    the caller is responsible for having required profile completion
    (including core selection) before calling this."""
    test_ids = [o.test_id for o in outcomes]
    defs = {
        td.test_id: td
        for td in db.query(TestDefinition).filter(TestDefinition.test_id.in_(test_ids)).all()
    }
    expanded: List[ExpandedTestOutcome] = []
    colors = profile.tested_core_colors or []

    for o in outcomes:
        td = defs.get(o.test_id)
        scope = td.scope if td else "ONCE"

        if scope == "ONCE":
            expanded.append(ExpandedTestOutcome(o.test_id, o.mandatory, o.matched_rule_id, o.clause_reference, None))

        elif scope == "SHEATH_ONLY":
            if profile.sheath_type:
                expanded.append(ExpandedTestOutcome(o.test_id, o.mandatory, o.matched_rule_id, o.clause_reference, "SHEATH"))

        elif scope == "PER_CORE":
            for color in colors:
                expanded.append(ExpandedTestOutcome(o.test_id, o.mandatory, o.matched_rule_id, o.clause_reference, color))

        elif scope == "PER_CORE_AND_SHEATH":
            for color in colors:
                expanded.append(ExpandedTestOutcome(o.test_id, o.mandatory, o.matched_rule_id, o.clause_reference, color))
            if profile.sheath_type:
                expanded.append(ExpandedTestOutcome(o.test_id, o.mandatory, o.matched_rule_id, o.clause_reference, "SHEATH"))

    return expanded
