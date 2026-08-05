"""Response models for api/samples.py -- see schemas/common.py's module docstring."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.schemas.common import OkResponse, SampleSummary, UserBrief


class ProfileOut(BaseModel):
    conductor_material: Optional[str] = None
    conductor_class: Optional[str] = None
    insulation_type: Optional[str] = None
    insulation_material: Optional[str] = None
    sheath_type: Optional[str] = None
    fire_category: Optional[str] = None
    construction: Optional[str] = None
    marking_image_path: bool
    source: Optional[str] = None
    confirmed: bool
    tested_core_colors: Optional[List[str]] = None
    has_outer_sheath: bool
    has_armour: bool
    has_inner_sheath: bool
    armour_type: Optional[str] = None
    armour_material: Optional[str] = None
    armour_strand_count: Optional[int] = None
    hand_drawn_diagram_url: Optional[str] = None
    cable_shape: Optional[str] = None
    overall_diameter_mm: Optional[float] = None
    diameter_under_sheath_mm: Optional[float] = None


class StandardBrief(BaseModel):
    standard_id: str
    name: str
    edition: Optional[str] = None
    amendment: Optional[str] = None


class CertificateBrief(BaseModel):
    certificate_no: str
    overall_decision: Optional[str] = None
    generated_at: str
    # H10: nullable -- certificates generated before this column existed
    # never had a checksum recorded (see the model column's own docstring
    # for why that's never backfilled after the fact).
    file_checksum_sha256: Optional[str] = None


class SampleListItem(BaseModel):
    sample_id: str
    status: str
    standard: Optional[str] = None
    cores: Optional[int] = None
    cores_tested: Optional[int] = None
    csa_mm2: Optional[float] = None
    created_at: str
    registered_by: Optional[UserBrief] = None
    assigned_assistant: Optional[UserBrief] = None
    profile: Optional[ProfileOut] = None
    # H16: the Scientist's explanation from the most recent RETURN, if any
    # review cycle is still unresolved (cleared on the next APPROVE).
    last_review_comment: Optional[str] = None
    summary: SampleSummary


class SampleListResponse(BaseModel):
    # B7 (Review #2 remediation): pagination, matching the limit/offset +
    # {total, ...} shape GET /api/admin/audit already established -- one
    # pagination convention in this app, not two.
    total: int
    samples: List[SampleListItem]


class CreateSampleResponse(BaseModel):
    sample_id: str
    status: str
    cores_tested: int


class LatestResultOut(BaseModel):
    attempt_number: int
    raw_values: Optional[Dict[str, Any]] = None
    calculated_value: Optional[float] = None
    calculated_unit: Optional[str] = None
    limit_value: Optional[float] = None
    limit_operator: Optional[str] = None
    margin_pct: Optional[float] = None
    confidence_state: Optional[str] = None
    result: Optional[str] = None
    effective_result: Optional[str] = None
    explanation: Optional[str] = None
    limit_source_kind: Optional[str] = None
    limit_source_ref: Optional[str] = None
    submitted_by: Optional[UserBrief] = None
    submitted_at: str
    performed_by_role: Optional[str] = None
    overridden: bool
    override_result: Optional[str] = None
    override_limit_value: Optional[float] = None
    override_reason: Optional[str] = None
    overridden_by: Optional[UserBrief] = None
    overridden_at: Optional[str] = None
    verified: bool
    verified_by: Optional[UserBrief] = None
    verified_at: Optional[str] = None


class TestDetailOut(BaseModel):
    assigned_test_id: str
    test_id: str
    name: str
    category: Optional[str] = None
    unit: Optional[str] = None
    # Nullable at the DB layer (TestDefinition.input_schema has no
    # server_default) -- a TestDefinition row created without one set
    # genuinely returns None here, not []. Matching that exactly rather
    # than coercing to [] preserves the pre-existing behavior.
    input_schema: Optional[List[Dict[str, Any]]] = None
    report_section: Optional[str] = None
    clause_reference: Optional[str] = None
    procedure_summary: Optional[str] = None
    procedure_measurement: Optional[str] = None
    procedure_formula: Optional[str] = None
    core_position: Optional[str] = None
    mandatory: bool
    enabled: bool
    status: str
    attempts: int
    latest_result: Optional[LatestResultOut] = None


class SampleDetailOut(BaseModel):
    sample_id: str
    status: str
    product_family: Optional[str] = None
    standard: Optional[StandardBrief] = None
    cores: Optional[int] = None
    cores_tested: Optional[int] = None
    csa_mm2: Optional[float] = None
    remarks: Optional[str] = None
    # H16: same field/lifecycle as SampleListItem.last_review_comment above.
    last_review_comment: Optional[str] = None
    locked: bool
    suggested_core_colors: Optional[List[str]] = None
    registered_by: Optional[UserBrief] = None
    assigned_assistant: Optional[UserBrief] = None
    created_at: str
    profile: Optional[ProfileOut] = None
    tests: List[TestDetailOut]
    summary: SampleSummary
    certificate: Optional[CertificateBrief] = None


class ProfileSubmitResponse(BaseModel):
    ok: bool = True
    assigned_tests: int
    retracted_tests: int
    retracted_with_existing_readings: List[str]


class MarkingImageUploadResponse(BaseModel):
    ok: bool = True
    ocr_available: bool
    note: Optional[str] = None


class SubmitReadingResponse(BaseModel):
    result: str
    confidence_state: str
    calculated_value: Optional[float] = None
    explanation: str
    margin_pct: Optional[float] = None


class OverrideResponse(BaseModel):
    ok: bool = True
    result: str


class ReviewResponse(BaseModel):
    ok: bool = True
    status: str


class CertificateGenerateResponse(BaseModel):
    certificate_no: str
    overall_decision: str
    download_url: str
    file_checksum_sha256: str


__all__ = [
    "CertificateBrief",
    "CertificateGenerateResponse",
    "CreateSampleResponse",
    "LatestResultOut",
    "MarkingImageUploadResponse",
    "OkResponse",
    "OverrideResponse",
    "ProfileOut",
    "ProfileSubmitResponse",
    "ReviewResponse",
    "SampleDetailOut",
    "SampleListItem",
    "StandardBrief",
    "SubmitReadingResponse",
    "TestDetailOut",
]
