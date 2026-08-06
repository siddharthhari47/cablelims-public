"""
Business logic for the sample lifecycle (registration -> profiling ->
testing -> review -> certification). Extracted from app/api/samples.py
(H2) so that module stays a thin HTTP layer: routes parse the request,
resolve auth/ownership via deps.get_authorized_sample, delegate here, and
return whatever this layer hands back. Every function signature, query,
side effect, audit entry, commit point, and error message below is
unchanged from the pre-extraction version -- this is a pure move, not a
rewrite.
"""
import os
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.engines.aggregation import (
    overall_decision_from_summary,
    pick_accepted_run,
    summarize_sample,
    summarize_samples_bulk,
)
from app.engines.calculation_engine import run_calculation
from app.engines.confidence_engine import evaluate as confidence_evaluate
from app.engines.reading_schemas import get_reading_schema
from app.engines.result_utils import effective_result, get_accepted_run
from app.engines.rule_engine import MAX_NAMED_CORE_COLORS, assign_tests, expand_for_positions, suggested_core_colors
from app.models.models import (
    LOCKED_STATUSES,
    AssignedTest,
    AuditEvent,
    CableProfile,
    Certificate,
    Sample,
    Standard,
    TestRun,
    User,
    iso_utc,
)
from app.services.checksum import compute_file_sha256
from app.services.docx_report_filler import generate_filled_report_docx
from app.services.image_upload import save_uploaded_image
from app.services.observation_sheet_filler import generate_filled_observation_sheet
from app.services.ocr_service import extract_marking
from app.services.procedure_notes import get_procedure_note
from app.services.report_builder import clause_references
from app.services.sequence_service import next_sequence_value

# sample_service.py lives at app/services/sample_service.py, the same depth
# below backend/ as app/api/samples.py did when this constant was defined
# there (see the historical note this comment replaces) -- three dirname()
# calls from this file still lands on backend/, not app/.
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

VALID_CORE_COLORS = {"RED", "YELLOW", "BLUE", "BLACK"}
VALID_ARMOUR_TYPES = {"Steel Wire", "Steel Strip", "Steel Tape", "Aluminium Wire"}


def _audit(db, user, action, entity_type, entity_id, details=None):
    db.add(AuditEvent(actor_id=user.id, actor_name=user.full_name, action=action,
                       entity_type=entity_type, entity_id=entity_id, details=details or {}))


def _user_brief(u: Optional[User]):
    if not u:
        return None
    return {"id": u.id, "full_name": u.full_name, "username": u.username, "role": u.role}


def _profile_brief(p: Optional[CableProfile]):
    if not p:
        return None
    return {
        "conductor_material": p.conductor_material, "conductor_class": p.conductor_class,
        "insulation_type": p.insulation_type, "insulation_material": p.insulation_material,
        "sheath_type": p.sheath_type,
        "fire_category": p.fire_category, "construction": p.construction,
        "marking_image_path": bool(p.marking_image_path), "source": p.source, "confirmed": p.confirmed,
        "tested_core_colors": p.tested_core_colors,
        "has_outer_sheath": p.has_outer_sheath, "has_armour": p.has_armour, "has_inner_sheath": p.has_inner_sheath,
        "armour_type": p.armour_type, "armour_material": p.armour_material, "armour_strand_count": p.armour_strand_count,
        "hand_drawn_diagram_url": f"/api/samples/{p.sample_id}/diagram-image" if p.hand_drawn_diagram_path else None,
        "cable_shape": p.cable_shape, "overall_diameter_mm": p.overall_diameter_mm,
        "diameter_under_sheath_mm": p.diameter_under_sheath_mm,
        "flat_width_mm": p.flat_width_mm, "flat_height_mm": p.flat_height_mm,
    }


def _next_sample_number(db) -> str:
    # UTC, matching every other timestamp in the app (models.now()) -- local
    # time here meant a sample registered late on Dec 31 in a timezone ahead
    # of UTC (e.g. IST) could get next year's prefix relative to its own
    # created_at.
    year = datetime.now(timezone.utc).year
    value = next_sequence_value(
        db, "SAMPLE", year,
        bootstrap_fn=lambda: db.query(Sample).filter(Sample.sample_id.like(f"SMP-{year}-%")).count() + 1,
    )
    return f"SMP-{year}-{value:04d}"


class CreateSampleRequest(BaseModel):
    standard_id: str
    cores: int
    csa_mm2: float
    remarks: Optional[str] = None
    assigned_assistant_id: Optional[str] = None
    # Required only when cores > MAX_NAMED_CORE_COLORS (4) -- the Scientist's
    # answer to "how many cores are required for testing?" (Sprint Priority 9).
    # For cores <= 4, every core is tested and this is ignored if provided.
    cores_tested: Optional[int] = None


class ProfileRequest(BaseModel):
    # B8 (Review #2 remediation): these six fields used to be bare `str`,
    # so a typo or wrong casing could reach the SKB lookups below unnoticed.
    # Five (everything but conductor_material) fail safe on a bad value --
    # standards_service.get_insulation_limit/get_sheath_limit return
    # "MISSING" for an unrecognized key, and an unrecognized fire_category
    # just means no fire-performance tests get assigned -- so the previous
    # risk there was an avoidable UNDETERMINED, not a wrong answer.
    # conductor_material is the one genuinely dangerous case:
    # get_conductor_resistance_limit does `"copper_plain" if material ==
    # "Copper" else "aluminium"` -- any value that isn't exactly "Copper"
    # (a typo, different casing) silently resolves to the ALUMINIUM
    # resistance table instead of failing safe, which is a wrong answer,
    # not a missing one. Literal[...] closes all six at the API boundary,
    # with the exact key sets verified against skb_seed_data.py and
    # seed.py's rule conditions, not guessed.
    conductor_material: Literal["Copper", "Aluminium"]
    conductor_class: Optional[Literal["1", "2", "5", "6"]] = None
    insulation_type: Literal["A", "B", "C", "D"]
    insulation_material: Optional[str] = "PVC"
    sheath_type: Optional[Literal["ST1", "ST2", "ST3"]] = None
    fire_category: Literal["01", "02", "FR", "FR-LSH"]
    construction: Optional[str] = None
    # Explicit per-core colour assignment, one entry per tested core, in
    # physical-position order -- e.g. ["RED","BLUE","YELLOW"]. Required:
    # never auto-assigned by the server. The Scientist/Assistant may start
    # from the "suggested_core_colors" hint returned by GET /samples/{id},
    # but must actively confirm it (or pick different colours) here.
    tested_core_colors: List[str]
    has_outer_sheath: bool = True
    has_armour: bool = False
    has_inner_sheath: bool = False
    armour_type: Optional[str] = None
    armour_material: Optional[str] = None
    armour_strand_count: Optional[int] = None
    cable_shape: Optional[Literal["Round", "Flat"]] = "Round"
    # Round only (IS 694 cl.9 / Table 5-7) -- a single diameter isn't a
    # meaningful measurement for a flat cross-section.
    overall_diameter_mm: Optional[float] = None    # OD -- measured with calipers
    diameter_under_sheath_mm: Optional[float] = None  # ID -- over laid-up cores, before outer sheath
    # Flat only (IS 694 cl.22, Table 10 -- "Overall Dimensions, Max (W x H)").
    flat_width_mm: Optional[float] = None    # W
    flat_height_mm: Optional[float] = None   # H


class SubmitReadingRequest(BaseModel):
    raw_values: dict
    # Offline support (phase 3a): a client-generated UUID, one per logical
    # submission, echoed unchanged on every retry of that same submission --
    # lets a queued-while-offline reading be safely replayed after a lost
    # confirmation without creating a duplicate TestRun. Optional so the
    # desktop Scientist path and any older client (never queued, always
    # online) keep working exactly as before.
    client_request_id: Optional[str] = None


class OverrideRequest(BaseModel):
    result: str                              # PASS | FAIL -- the Scientist's final decision
    limit_value: Optional[float] = None      # the limit the Scientist believes is actually correct
    reason: str                              # mandatory -- why the system's own decision is being overridden


class ReviewRequest(BaseModel):
    action: str  # APPROVE | RETURN
    comment: Optional[str] = None


def list_samples(db: Session, user: User, status_filter: Optional[str],
                  limit: int = 200, offset: int = 0) -> dict:
    # B7 (Review #2 remediation): limit/offset pagination, matching
    # GET /api/admin/audit's existing convention (same clamping, same
    # {total, ...} response shape) -- this app's one pagination pattern,
    # not a second, differently-shaped one. Default limit (200) is
    # comfortably above any realistic single-lab sample count today, so
    # this is additive capacity rather than a behavior change for current
    # data volumes, while genuinely capping unbounded future growth.
    limit = min(max(limit, 1), 500)
    q = db.query(Sample)
    if user.role == "SCIENTIFIC_ASSISTANT":
        q = q.filter(Sample.assigned_assistant_id == user.id)
    if status_filter:
        q = q.filter(Sample.status == status_filter)
    total = q.count()
    samples = q.order_by(Sample.created_at.desc()).offset(offset).limit(limit).all()
    # H5: one bulk aggregation pass for every sample on this page, instead
    # of summarize_sample() once per sample (which itself used to query per
    # assigned test) -- was O(samples x tests) queries on every list load.
    summaries = summarize_samples_bulk(db, samples)
    out = []
    for s in samples:
        out.append({
            "sample_id": s.sample_id, "status": s.status, "standard": s.standard.name if s.standard else None,
            "cores": s.cores, "cores_tested": s.cores_tested, "csa_mm2": s.csa_mm2, "created_at": iso_utc(s.created_at),
            "registered_by": _user_brief(s.registered_by), "assigned_assistant": _user_brief(s.assigned_assistant),
            "profile": _profile_brief(s.profile),
            "last_review_comment": s.last_review_comment,
            "summary": vars(summaries[s.sample_id]),
        })
    return {"total": total, "samples": out}


def create_sample(db: Session, user: User, body: CreateSampleRequest) -> dict:
    standard = db.query(Standard).filter(Standard.standard_id == body.standard_id).first()
    if not standard:
        raise HTTPException(404, "Standard not found")
    if body.cores < 1:
        raise HTTPException(400, "Number of cores must be at least 1")

    # Core-count -> testing-count logic (Sprint Priority 9): <=4 cores, test
    # every core automatically; >4 cores, the Scientist must say how many.
    if body.cores <= MAX_NAMED_CORE_COLORS:
        cores_tested = body.cores
    else:
        if not body.cores_tested:
            raise HTTPException(
                400,
                f"This cable has {body.cores} cores, more than the {MAX_NAMED_CORE_COLORS} that can be "
                "auto-assigned a colour. Specify cores_tested: how many cores are required for testing?",
            )
        if not (1 <= body.cores_tested <= MAX_NAMED_CORE_COLORS):
            raise HTTPException(400, f"cores_tested must be between 1 and {MAX_NAMED_CORE_COLORS}")
        cores_tested = body.cores_tested

    sample_id = _next_sample_number(db)
    # (ignore comment below on csa_mm2: the SQLAlchemy mypy plugin can't
    # fully resolve a plain Column(Float) to a concrete numeric type --
    # see engines/aggregation.py's matching note -- genuinely correct at
    # runtime.)
    sample = Sample(
        sample_id=sample_id, product_family=standard.product_family, standard_id=standard.standard_id,
        cores=body.cores, cores_tested=cores_tested, csa_mm2=body.csa_mm2, remarks=body.remarks,  # type: ignore[arg-type]
        status="PROFILE_PENDING", registered_by_id=user.id, assigned_assistant_id=body.assigned_assistant_id,
    )
    db.add(sample)
    _audit(db, user, "SAMPLE_REGISTERED", "sample", sample_id,
           {"standard": standard.name, "cores": body.cores, "cores_tested": cores_tested})
    db.commit()
    return {"sample_id": sample_id, "status": sample.status, "cores_tested": cores_tested}


def get_sample_detail(db: Session, sample: Sample) -> dict:
    # B7 (Review #2 remediation): this used to loop every AssignedTest
    # issuing get_accepted_run() (1-2 queries), a separate .count() for
    # attempts, and a lazy test_definition load each -- measured at 241
    # queries for a 76-test sample. Fixed the same way H5 fixed the
    # list/dashboard endpoints: one query for every assigned test (with its
    # test_definition eager-loaded), one query for every run those tests
    # have (with the three user relationships each run's response needs
    # eager-loaded too), then the same per-test resolution
    # (aggregation.pick_accepted_run) run entirely in memory.
    sample_id = sample.sample_id
    summary = summarize_sample(db, sample_id, sample.status)
    clause_refs = clause_references(db, sample.standard_id) if sample.standard_id else {}

    assigned = (
        db.query(AssignedTest)
        .options(joinedload(AssignedTest.test_definition))
        .filter(AssignedTest.sample_id == sample_id)
        .all()
    )
    runs_by_assigned_test: dict = {}
    assigned_ids = [at.id for at in assigned]
    if assigned_ids:
        for run in (
            db.query(TestRun)
            .filter(TestRun.assigned_test_id.in_(assigned_ids))
            .options(
                joinedload(TestRun.submitted_by),
                joinedload(TestRun.overridden_by),
                joinedload(TestRun.verified_by),
            )
            .all()
        ):
            runs_by_assigned_test.setdefault(run.assigned_test_id, []).append(run)

    tests = []
    for at in assigned:
        candidate_runs = runs_by_assigned_test.get(at.id, [])
        latest = pick_accepted_run(at, candidate_runs)
        procedure = get_procedure_note(at.test_id)
        tests.append({
            "assigned_test_id": at.id, "test_id": at.test_id,
            "name": at.test_definition.name if at.test_definition else at.test_id,
            "category": at.test_definition.category if at.test_definition else None,
            "unit": at.test_definition.unit if at.test_definition else None,
            "input_schema": at.test_definition.input_schema if at.test_definition else [],
            "report_section": at.test_definition.report_section if at.test_definition else None,
            "clause_reference": clause_refs.get(at.test_id),
            "procedure_summary": procedure["summary"] if procedure else None,
            "procedure_measurement": procedure["measurement"] if procedure else None,
            "procedure_formula": procedure["formula"] if procedure else None,
            "core_position": at.core_position,
            "_sequence": at.test_definition.sequence if at.test_definition else 999,
            "mandatory": at.mandatory, "enabled": at.enabled, "status": at.status,
            "attempts": len(candidate_runs),
            "latest_result": None if not latest else {
                "attempt_number": latest.attempt_number, "raw_values": latest.raw_values,
                "calculated_value": latest.calculated_value, "calculated_unit": latest.calculated_unit,
                "limit_value": latest.limit_value, "limit_operator": latest.limit_operator,
                "margin_pct": latest.margin_pct, "confidence_state": latest.confidence_state,
                "result": latest.result, "effective_result": effective_result(latest),
                "explanation": latest.result_explanation,
                "limit_source_kind": latest.limit_source_kind, "limit_source_ref": latest.limit_source_ref,
                "submitted_by": _user_brief(latest.submitted_by), "submitted_at": iso_utc(latest.submitted_at),
                "performed_by_role": latest.submitted_by.role if latest.submitted_by else None,
                "overridden": latest.overridden, "override_result": latest.override_result,
                "override_limit_value": latest.override_limit_value, "override_reason": latest.override_reason,
                "overridden_by": _user_brief(latest.overridden_by) if latest.overridden else None,
                "overridden_at": iso_utc(latest.overridden_at),
                "verified": latest.verified,
                "verified_by": _user_brief(latest.verified_by) if latest.verified else None,
                "verified_at": iso_utc(latest.verified_at),
            },
        })
    core_order = {"RED": 0, "YELLOW": 1, "BLUE": 2, "BLACK": 3, "SHEATH": 4, None: -1}
    tests.sort(key=lambda t: (t["_sequence"], core_order.get(t["core_position"], 9)))
    for t in tests:
        del t["_sequence"]

    cert = db.query(Certificate).filter(Certificate.sample_id == sample_id).order_by(Certificate.generated_at.desc()).first()

    return {
        "sample_id": sample.sample_id, "status": sample.status, "product_family": sample.product_family,
        "standard": {"standard_id": sample.standard.standard_id, "name": sample.standard.name,
                     "edition": sample.standard.edition, "amendment": sample.standard.amendment} if sample.standard else None,
        "cores": sample.cores, "cores_tested": sample.cores_tested, "csa_mm2": sample.csa_mm2, "remarks": sample.remarks,
        "last_review_comment": sample.last_review_comment,
        "locked": sample.status in LOCKED_STATUSES,
        # A UI pre-fill suggestion only -- never applied automatically. The
        # Scientist/Assistant must explicitly confirm or change this during
        # profiling (see ProfileRequest.tested_core_colors below).
        "suggested_core_colors": suggested_core_colors(sample.cores_tested) if sample.cores_tested else None,
        "registered_by": _user_brief(sample.registered_by), "assigned_assistant": _user_brief(sample.assigned_assistant),
        "created_at": iso_utc(sample.created_at),
        "profile": _profile_brief(sample.profile),
        "tests": tests,
        "summary": vars(summary),
        "certificate": None if not cert else {
            "certificate_no": cert.certificate_no, "overall_decision": cert.overall_decision,
            "generated_at": iso_utc(cert.generated_at), "file_checksum_sha256": cert.file_checksum_sha256,
        },
    }


def submit_profile(db: Session, user: User, sample: Sample, body: ProfileRequest) -> dict:
    sample_id = sample.sample_id
    if not sample.cores_tested:
        raise HTTPException(400, "Sample is missing a cores_tested value -- this should have been set at "
                                  "registration; contact the Scientist who registered this sample.")

    # Core-to-colour assignment must be explicit, one colour per tested
    # core, and (for named colours) drawn from the standard sequence --
    # never inferred or defaulted here.
    if len(body.tested_core_colors) != sample.cores_tested:
        raise HTTPException(400, f"tested_core_colors must have exactly {sample.cores_tested} entries "
                                  f"(one per tested core); got {len(body.tested_core_colors)}.")
    if sample.cores_tested <= MAX_NAMED_CORE_COLORS:
        bad = [c for c in body.tested_core_colors if c not in VALID_CORE_COLORS]
        if bad:
            raise HTTPException(400, f"Invalid core colour(s) {bad}; must be one of {sorted(VALID_CORE_COLORS)}.")
        if len(set(body.tested_core_colors)) != len(body.tested_core_colors):
            raise HTTPException(400, "Each core must be assigned a distinct colour.")
    if body.has_armour and body.armour_type and body.armour_type not in VALID_ARMOUR_TYPES:
        raise HTTPException(400, f"Invalid armour_type; must be one of {sorted(VALID_ARMOUR_TYPES)}.")

    profile = db.query(CableProfile).filter(CableProfile.sample_id == sample_id).first()
    if not profile:
        profile = CableProfile(sample_id=sample_id)
        db.add(profile)

    profile.conductor_material = body.conductor_material
    profile.conductor_class = body.conductor_class
    profile.insulation_type = body.insulation_type
    profile.insulation_material = body.insulation_material
    profile.sheath_type = body.sheath_type
    profile.fire_category = body.fire_category
    profile.construction = body.construction
    profile.source = "MANUAL"
    profile.confirmed = True
    profile.confirmed_by_id = user.id
    profile.tested_core_colors = body.tested_core_colors
    profile.has_outer_sheath = body.has_outer_sheath
    profile.has_armour = body.has_armour
    profile.has_inner_sheath = body.has_inner_sheath
    profile.armour_type = body.armour_type if body.has_armour else None
    profile.armour_material = body.armour_material if body.has_armour else None
    profile.armour_strand_count = body.armour_strand_count if body.has_armour else None
    profile.cable_shape = body.cable_shape or "Round"
    # (ignore comments below: same plain-Column(Float) mypy-plugin gap as
    # csa_mm2 above.)
    profile.overall_diameter_mm = body.overall_diameter_mm  # type: ignore[assignment]
    profile.diameter_under_sheath_mm = body.diameter_under_sheath_mm  # type: ignore[assignment]
    profile.flat_width_mm = body.flat_width_mm  # type: ignore[assignment]
    profile.flat_height_mm = body.flat_height_mm  # type: ignore[assignment]
    db.flush()

    # Rule Engine: which tests apply, then expand into one AssignedTest row
    # per tested core/sheath position per that test's scope (Sprint Priority 1).
    existing_ats = db.query(AssignedTest).filter(AssignedTest.sample_id == sample_id).all()
    existing = {(at.test_id, at.core_position): at for at in existing_ats}
    outcomes = assign_tests(db, sample.standard_id, profile)
    expanded = expand_for_positions(db, outcomes, profile)
    new_applicable = {(o.test_id, o.core_position) for o in expanded}

    added = 0
    for o in expanded:
        if (o.test_id, o.core_position) in existing:
            continue
        db.add(AssignedTest(sample_id=sample_id, test_id=o.test_id, mandatory=o.mandatory,
                             enabled=True, status="PENDING", core_position=o.core_position))
        added += 1

    # Re-profiling (e.g. correcting fire_category from FR-LSH back to 01, or
    # changing which core got which colour) previously only ever ADDED
    # AssignedTest rows -- a test that no longer applies stayed assigned,
    # mandatory, and PENDING forever, permanently blocking the sample from
    # reaching SCIENTIST_REVIEW and forcing readings to be recorded (or
    # faked) for a test the standard no longer actually requires for this
    # construction. Diff against the newly-applicable set and retract
    # anything that fell out of it: delete outright if nothing was ever
    # recorded against it (nothing to lose), or disable-but-preserve if a
    # reading already exists (never silently discard measured data -- the
    # TestRun rows and the audit trail stay exactly as they were).
    retracted_no_data = []
    retracted_with_data = []
    for (test_id, core_position), at in existing.items():
        if (test_id, core_position) in new_applicable:
            continue
        has_data = db.query(TestRun).filter(TestRun.assigned_test_id == at.id).first() is not None
        label = f"{test_id}" + (f" ({core_position})" if core_position else "")
        if has_data:
            at.enabled = False
            retracted_with_data.append(label)
        else:
            db.delete(at)
            retracted_no_data.append(label)

    sample.status = "TESTING"
    _audit(db, user, "PROFILE_CONFIRMED", "sample", sample_id,
           {"fire_category": body.fire_category, "tested_core_colors": profile.tested_core_colors,
            "retracted_no_data": retracted_no_data, "retracted_with_data": retracted_with_data})
    db.commit()
    return {
        "ok": True, "assigned_tests": added,
        "retracted_tests": len(retracted_no_data) + len(retracted_with_data),
        "retracted_with_existing_readings": retracted_with_data,
    }


def upload_marking_image(db: Session, user: User, sample: Sample, file: UploadFile) -> dict:
    sample_id = sample.sample_id
    saved = save_uploaded_image(file, UPLOAD_DIR, sample_id)
    dest_path = saved.path

    profile = db.query(CableProfile).filter(CableProfile.sample_id == sample_id).first()
    if not profile:
        profile = CableProfile(sample_id=sample_id, source="OCR_PENDING")
        db.add(profile)
    profile.marking_image_path = dest_path
    ocr = extract_marking(dest_path)
    _audit(db, user, "MARKING_IMAGE_UPLOADED", "sample", sample_id, {"ocr_available": ocr.available})
    db.commit()
    return {"ok": True, "ocr_available": ocr.available, "note": ocr.note}


def upload_diagram_image(db: Session, user: User, sample: Sample, file: UploadFile) -> dict:
    """Fallback for constructions the parametric SVG diagram can't represent
    (e.g. unusual layer counts/geometries) -- a hand-drawn or photographed
    diagram replaces the generated one entirely on the certificate/profile
    view. Never auto-generated; always an explicit upload."""
    sample_id = sample.sample_id
    saved = save_uploaded_image(file, UPLOAD_DIR, f"{sample_id}_diagram")
    dest_path = saved.path

    profile = db.query(CableProfile).filter(CableProfile.sample_id == sample_id).first()
    if not profile:
        profile = CableProfile(sample_id=sample_id)
        db.add(profile)
    profile.hand_drawn_diagram_path = dest_path
    _audit(db, user, "DIAGRAM_IMAGE_UPLOADED", "sample", sample_id, {})
    db.commit()
    return {"ok": True}


def resolve_diagram_image_path(sample: Sample) -> str:
    # Sample-scoped (previously GET /diagram-image/{filename}, keyed only by
    # an opaque filename with no ownership check at all -- any authenticated
    # user, any role, could fetch any sample's diagram just by knowing or
    # guessing its filename). Going through get_authorized_sample() means a
    # Scientific Assistant can only reach a diagram for a sample assigned to
    # them, same as every other sample-scoped route. Resolving the file via
    # the Sample -> CableProfile relationship (rather than trusting a
    # client-supplied filename at all) also fixes the secondary "this route
    # lives under /api/samples/ but isn't actually sample-scoped" REST smell
    # -- there's no longer a filename in the URL to parse or match against.
    if not sample.profile or not sample.profile.hand_drawn_diagram_path:
        raise HTTPException(404, "Diagram image not found")
    path = sample.profile.hand_drawn_diagram_path
    if not os.path.exists(path):
        raise HTTPException(404, "Diagram image not found")
    return path


def toggle_test(db: Session, user: User, sample: Sample, assigned_test_id: str, enabled: bool) -> dict:
    at = db.query(AssignedTest).filter(AssignedTest.id == assigned_test_id, AssignedTest.sample_id == sample.sample_id).first()
    if not at:
        raise HTTPException(404, "Assigned test not found")
    if at.mandatory:
        raise HTTPException(400, "Cannot disable a mandatory test")
    at.enabled = enabled
    _audit(db, user, "TEST_TOGGLED", "assigned_test", assigned_test_id, {"enabled": enabled})
    db.commit()
    return {"ok": True}


def submit_reading(db: Session, user: User, sample: Sample, assigned_test_id: str, body: SubmitReadingRequest) -> dict:
    sample_id = sample.sample_id
    at = db.query(AssignedTest).filter(AssignedTest.id == assigned_test_id, AssignedTest.sample_id == sample_id).first()
    if not at:
        raise HTTPException(404, "Assigned test not found")

    # Offline support (phase 3a): this MUST run before every other check
    # below (profile-exists, override-lock, validation) -- a replay of a
    # submission that already landed must succeed identically regardless of
    # what's happened to the sample since (the profile could since have
    # changed, the accepted attempt could since have been overridden). Moving
    # this after those checks would reintroduce exactly the bug it exists to
    # prevent: a retried-but-already-successful offline submission getting
    # rejected by a check that has nothing to do with whether THIS submission
    # already succeeded.
    if body.client_request_id:
        existing_run = db.query(TestRun).filter(
            TestRun.assigned_test_id == at.id,
            TestRun.client_request_id == body.client_request_id,
        ).first()
        if existing_run:
            return {
                "result": existing_run.result, "confidence_state": existing_run.confidence_state,
                "calculated_value": existing_run.calculated_value, "explanation": existing_run.result_explanation,
                "margin_pct": existing_run.margin_pct,
            }

    profile = db.query(CableProfile).filter(CableProfile.sample_id == sample_id).first()
    if not profile:
        raise HTTPException(400, "Profile not captured yet")

    # Every reading is validated against this test's own typed schema before
    # any calculator sees it -- a bare dict used to be accepted verbatim, so
    # a typo'd field name silently produced a MISSING-limit UNDETERMINED
    # (misdiagnosed as a Standards Knowledge Base gap), a physically
    # impossible value (negative length, a room temperature that divides by
    # zero in the correction-factor formula) was accepted outright, and a
    # qualitative field like cracks_observed did a bare Python truthy check
    # where the JSON string "false" is truthy. See engines/reading_schemas.py.
    schema = get_reading_schema(at.test_id)
    if not schema:
        raise HTTPException(400, f"No validated input schema is configured for {at.test_id} -- "
                                  "readings cannot be accepted for this test until one is added "
                                  "(see engines/reading_schemas.py).")
    try:
        validated = schema.model_validate(body.raw_values)
    except ValidationError as e:
        # Pydantic's raw .errors() dicts can carry a `ctx.error` key holding
        # the actual exception instance (from @model_validator's `raise
        # ValueError(...)`), which isn't JSON-serializable -- keep only the
        # plain-data fields FastAPI's own validation errors use, in the same
        # {loc, msg, type} shape the frontend already knows how to render.
        detail = [{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in e.errors()]
        raise HTTPException(422, detail=detail) from e
    raw_values = validated.model_dump()

    # A Scientist's override on the currently-accepted attempt must never be
    # silently superseded by a plain resubmission -- that override is a
    # documented professional judgement, not something a later reading
    # should be able to erase by accident. Force a deliberate action first
    # (request_repeat, which clears accepted_attempt_id) rather than letting
    # this new attempt quietly become accepted in the override's place.
    if at.accepted_attempt_id:
        accepted_run = db.query(TestRun).filter(TestRun.id == at.accepted_attempt_id).first()
        if accepted_run and accepted_run.overridden:
            overridden_by = accepted_run.overridden_by.full_name if accepted_run.overridden_by else "a Scientist"
            raise HTTPException(
                400,
                f"This test's accepted reading was overridden by {overridden_by}, with the reason: "
                f"\"{accepted_run.override_reason}\". Submitting a new reading now would silently replace "
                "that decision. If a new reading is genuinely needed, a Scientist must request a repeat first.",
            )

    # Sprint Priority 4: either role may perform/record a test -- "Performed
    # By" is derived from submitted_by.role at read time, not a separate
    # field, so this endpoint already supports both without change here.
    attempt_number = db.query(TestRun).filter(TestRun.assigned_test_id == at.id).count() + 1
    calc = run_calculation(at.test_id, raw_values, profile, sample.csa_mm2, core_position=at.core_position, cores=sample.cores)  # type: ignore[arg-type]
    outcome = confidence_evaluate(calc)

    # (ignore comments below: same plain-Column(Float) mypy-plugin gap as
    # csa_mm2 above.)
    run = TestRun(
        assigned_test_id=at.id, attempt_number=attempt_number, raw_values=raw_values,
        submitted_by_id=user.id, client_request_id=body.client_request_id,
        calculated_value=calc.calculated_value, calculated_unit=calc.calculated_unit,  # type: ignore[arg-type]
        limit_value=calc.limit_value, limit_operator=calc.operator, limit_unit=calc.calculated_unit,  # type: ignore[arg-type]
        margin_pct=outcome.margin_pct, limit_source_kind=outcome.limit_source_kind,  # type: ignore[arg-type]
        limit_source_ref=outcome.limit_source_ref, confidence_state=outcome.confidence_state,
        result=outcome.result, result_explanation=outcome.explanation,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        # Defensive only -- not expected to fire in the normal single-writer
        # request flow, but two near-simultaneous replays of the exact same
        # queued offline submission (e.g. two tabs syncing at once) would
        # race right up to this unique-index check. Whichever loses the race
        # gets the winner's already-committed result instead of a raw 500.
        db.rollback()
        existing_run = db.query(TestRun).filter(
            TestRun.assigned_test_id == at.id,
            TestRun.client_request_id == body.client_request_id,
        ).first()
        if existing_run:
            return {
                "result": existing_run.result, "confidence_state": existing_run.confidence_state,
                "calculated_value": existing_run.calculated_value, "explanation": existing_run.result_explanation,
                "margin_pct": existing_run.margin_pct,
            }
        raise
    at.accepted_attempt_id = run.id
    at.status = "COMPLETED" if outcome.result in ("PASS", "FAIL") else "REPEAT_REQUIRED"

    all_assigned = db.query(AssignedTest).filter(AssignedTest.sample_id == sample_id, AssignedTest.enabled == True).all()  # noqa: E712
    if all(a.status in ("COMPLETED", "REPEAT_REQUIRED") for a in all_assigned):
        sample.status = "SCIENTIST_REVIEW"

    _audit(db, user, "READING_SUBMITTED", "test_run", run.id, {"test_id": at.test_id, "result": outcome.result})
    db.commit()
    return {
        "result": outcome.result, "confidence_state": outcome.confidence_state,
        "calculated_value": calc.calculated_value, "explanation": outcome.explanation,
        "margin_pct": outcome.margin_pct,
    }


def override_reading(db: Session, user: User, sample: Sample, assigned_test_id: str, body: OverrideRequest) -> dict:
    """A Scientist's documented correction on top of the system's computed
    result -- e.g. the Standards Knowledge Base had the wrong table/class for
    this test. Never rewrites the original TestRun (immutable once
    submitted, see its docstring) -- layers the override alongside it, with
    a mandatory reason, so the original system result stays visible for
    audit/traceability rather than being silently replaced."""
    sample_id = sample.sample_id
    if body.result not in ("PASS", "FAIL"):
        raise HTTPException(400, "result must be PASS or FAIL")
    if not body.reason or not body.reason.strip():
        raise HTTPException(400, "A reason is required to override a test result")

    at = db.query(AssignedTest).filter(AssignedTest.id == assigned_test_id, AssignedTest.sample_id == sample_id).first()
    if not at:
        raise HTTPException(404, "Assigned test not found")

    run = get_accepted_run(db, at)
    if not run:
        raise HTTPException(400, "No reading has been submitted for this test yet")
    at.accepted_attempt_id = run.id  # self-heal if this row predates the column being wired up

    run.overridden = True
    run.override_result = body.result
    run.override_limit_value = body.limit_value  # type: ignore[assignment]  # plain-Column(Float) mypy-plugin gap, see csa_mm2 above
    run.override_reason = body.reason.strip()
    run.overridden_by_id = user.id
    run.overridden_at = datetime.now(timezone.utc)

    at.status = "COMPLETED"
    all_assigned = db.query(AssignedTest).filter(AssignedTest.sample_id == sample_id, AssignedTest.enabled == True).all()  # noqa: E712
    if all(a.status in ("COMPLETED", "REPEAT_REQUIRED") for a in all_assigned):
        sample.status = "SCIENTIST_REVIEW"

    _audit(db, user, "RESULT_OVERRIDDEN", "test_run", run.id,
           {"test_id": at.test_id, "system_result": run.result, "override_result": body.result,
            "override_limit_value": body.limit_value, "reason": body.reason.strip()})
    db.commit()
    return {"ok": True, "result": body.result}


def verify_reading(db: Session, user: User, sample: Sample, assigned_test_id: str) -> dict:
    """Lightweight QA confirmation -- a Scientist reviewed this raw reading
    (most often Assistant-submitted) and endorses it. Doesn't change any
    decision (see /override for that) -- just records who looked at it."""
    at = db.query(AssignedTest).filter(AssignedTest.id == assigned_test_id, AssignedTest.sample_id == sample.sample_id).first()
    if not at:
        raise HTTPException(404, "Assigned test not found")

    run = get_accepted_run(db, at)
    if not run:
        raise HTTPException(400, "No reading has been submitted for this test yet")
    at.accepted_attempt_id = run.id  # self-heal if this row predates the column being wired up

    run.verified = True
    run.verified_by_id = user.id
    run.verified_at = datetime.now(timezone.utc)
    _audit(db, user, "READING_VERIFIED", "test_run", run.id, {"test_id": at.test_id})
    db.commit()
    return {"ok": True}


def request_repeat(db: Session, user: User, sample: Sample, assigned_test_id: str) -> dict:
    at = db.query(AssignedTest).filter(AssignedTest.id == assigned_test_id, AssignedTest.sample_id == sample.sample_id).first()
    if not at:
        raise HTTPException(404, "Assigned test not found")
    at.status = "PENDING"
    # Explicitly release the accepted attempt (even if it was overridden) --
    # this Scientist-initiated action is exactly the deliberate signal
    # submit_reading's own override guard requires before a new attempt can
    # become accepted in its place. The old run itself is untouched and
    # stays in the audit trail with its override intact.
    at.accepted_attempt_id = None
    sample.status = "TESTING"
    _audit(db, user, "REPEAT_REQUESTED", "assigned_test", assigned_test_id, {})
    db.commit()
    return {"ok": True}


def review_sample(db: Session, user: User, sample: Sample, body: ReviewRequest) -> dict:
    if sample.status != "SCIENTIST_REVIEW":
        raise HTTPException(400, f"Sample is not awaiting review (current status: {sample.status})")
    if body.action == "APPROVE":
        sample.status = "APPROVED"
        # H16: a resolved review cycle has nothing left for the Assistant to
        # act on -- clear any comment from a prior RETURN so it doesn't
        # linger as stale feedback on an already-approved sample.
        sample.last_review_comment = None
    else:
        # H16: mandatory (same pattern as override_reading's `reason` above)
        # -- a RETURN with no explanation leaves the Assistant with a status
        # change and no idea what to fix.
        if not body.comment or not body.comment.strip():
            raise HTTPException(400, "A comment is required when returning a sample -- "
                                      "the Assistant needs to know what to correct.")
        sample.status = "TESTING"
        sample.last_review_comment = body.comment.strip()
    _audit(db, user, f"REVIEW_{body.action}", "sample", sample.sample_id, {"comment": body.comment})
    db.commit()
    return {"ok": True, "status": sample.status}


def build_observation_sheet(db: Session, sample: Sample) -> str:
    """Unlike the Certificate, this isn't a versioned/certified artifact --
    no certificate_no, no locked-in decision -- so it's generated fresh
    from current data on every download rather than persisted, and can be
    pulled any time a profile is confirmed (not gated behind approval) --
    including on an already-locked/archived sample, hence allow_locked=True
    on the route."""
    if not sample.profile or not sample.profile.confirmed:
        raise HTTPException(400, "Profile must be confirmed before generating the Observation Sheet")
    return generate_filled_observation_sheet(db, sample.sample_id, sample.sample_id.replace("/", "_"))


def generate_certificate(db: Session, user: User, sample: Sample) -> dict:
    sample_id = sample.sample_id
    if sample.status != "APPROVED":
        raise HTTPException(400, "Sample must be approved before generating a certificate")

    summary = summarize_sample(db, sample_id)
    overall = overall_decision_from_summary(summary)

    year = datetime.now(timezone.utc).year
    value = next_sequence_value(
        db, "CERTIFICATE", year,
        bootstrap_fn=lambda: db.query(Certificate).filter(Certificate.certificate_no.like(f"CTL/CBL/{year}/%")).count() + 1,
    )
    cert_no = f"CTL/CBL/{year}/{value:04d}"

    # Fills the CTL Test Report_694.docx template itself with this sample's
    # values -- per explicit instruction, the report is that exact document
    # with values inserted, not a redesigned layout.
    path = generate_filled_report_docx(db, sample_id, cert_no.replace("/", "_"))
    # H10: recorded at the moment of generation, while these bytes are known
    # to be exactly what the system produced -- see Certificate.
    # file_checksum_sha256's own docstring for why this is never backfilled
    # after the fact.
    checksum = compute_file_sha256(path)

    cert = Certificate(certificate_no=cert_no, sample_id=sample_id, generated_by_id=user.id,
                        overall_decision=overall, file_path=path, file_checksum_sha256=checksum)
    db.add(cert)
    sample.status = "ARCHIVED"
    _audit(db, user, "CERTIFICATE_GENERATED", "sample", sample_id,
           {"certificate_no": cert_no, "file_checksum_sha256": checksum})
    db.commit()
    return {"certificate_no": cert_no, "overall_decision": overall,
            "download_url": f"/api/certificates/{cert_no}/download", "file_checksum_sha256": checksum}
