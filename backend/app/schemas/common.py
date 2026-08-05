"""
Response models shared across more than one router. §5.3: previously every
endpoint hand-built a dict, `list_samples` embedded `vars(a_dataclass)`
directly (works today, silently changes shape the moment anyone adds a
non-field attribute), and because no endpoint declared `response_model=`,
the generated OpenAPI schema documented no response bodies at all -- /docs
told a consumer what to send and nothing about what comes back.

These models are deliberately shaped to match the dicts the handlers
already returned, field-for-field -- this is a documentation and
leak-prevention change, not a response-shape change. Nested `Optional[...]`
fields mirror exactly which sub-objects could already be `None` (e.g. a
sample with no certificate yet, a run with no override).
"""
from typing import List, Optional

from pydantic import BaseModel


class UserBrief(BaseModel):
    id: str
    full_name: str
    username: str
    role: str


class SampleSummary(BaseModel):
    """Mirrors engines.aggregation.SampleDecisionSummary field-for-field --
    kept as a distinct model (not reusing the dataclass via
    model_config=ConfigDict(from_attributes=True)) so a change to the
    dataclass's internals doesn't silently change the wire contract; the
    two are meant to be kept in sync deliberately, not automatically."""
    applicable_tests: int
    completed_tests: int
    passed: int
    failed: int
    undetermined: int
    repeat_required: List[str] = []
    overall_confidence_pct: Optional[float] = None
    overall_status: str


class OkResponse(BaseModel):
    ok: bool = True
