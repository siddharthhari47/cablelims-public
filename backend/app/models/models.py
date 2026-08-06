"""
SQLAlchemy models -- MVP subset of the full CableLIMS data model described in
CableLIMS_SDD_v2.md section 6. Scoped to the Cable product family / IS 694
only, per the one-day MVP brief. Field names and relationships are chosen so
this can grow into the full multi-product-family schema later without a
rewrite (e.g. Sample.product_family already exists even though only "CABLE"
is populated today).
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import ClassVar, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, relationship

from app.db import Base


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    """Serializes a datetime as ISO-8601 WITH an explicit UTC offset.

    Every datetime this app writes is UTC (see now() above), but SQLite has
    no native datetime type -- SQLAlchemy stores a naive string and hands
    back a naive `datetime` on read, silently dropping the tzinfo. A plain
    `dt.isoformat()` on that naive value produces a string with no offset
    (e.g. "2026-08-02T14:00:00"), which a browser's `new Date(...)` parses
    as LOCAL time -- in IST (UTC+5:30), every timestamp in the app would
    display 5h30m later than it actually happened. This attaches UTC to a
    naive value before formatting (an already-aware value passes through
    unchanged), so every API response carries an unambiguous offset. Use
    this everywhere a DB-sourced datetime is serialized -- never call
    .isoformat() on one directly."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class Role(str, enum.Enum):
    SCIENTIST = "SCIENTIST"
    SCIENTIFIC_ASSISTANT = "SCIENTIFIC_ASSISTANT"
    ADMINISTRATOR = "ADMINISTRATOR"


class SampleStatus(str, enum.Enum):
    REGISTERED = "REGISTERED"
    PROFILE_PENDING = "PROFILE_PENDING"
    PROFILE_VERIFIED = "PROFILE_VERIFIED"
    TESTING = "TESTING"
    REPEAT_REQUIRED = "REPEAT_REQUIRED"
    SCIENTIST_REVIEW = "SCIENTIST_REVIEW"
    APPROVED = "APPROVED"
    REPORT_GENERATED = "REPORT_GENERATED"
    ARCHIVED = "ARCHIVED"



# Once a sample reaches one of these statuses, its profile/readings are
# locked -- further edits require an explicit revision path (not built in
# this pass), not a silent overwrite of an approved/certified record. This
# is the single source of truth for that check: previously three separate
# hardcoded copies of this same tuple existed in api/samples.py,
# engines/aggregation.py, and api/dashboard.py, which is exactly the kind
# of duplication that drifts silently when a status is added or renamed.
LOCKED_STATUSES = (SampleStatus.APPROVED.value, SampleStatus.REPORT_GENERATED.value, SampleStatus.ARCHIVED.value)


class TestResult(str, enum.Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    UNDETERMINED = "UNDETERMINED"
    MANUAL_REVIEW_APPROVED = "MANUAL_REVIEW_APPROVED"


class ConfidenceState(str, enum.Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    # True only for the accounts seed.py creates (scientist1/assistant1/
    # admin1/.../demo1234) on a demo/dev install. Drives whether the login
    # page's "Demo accounts" hint shows at all -- a real install created via
    # create_user.py never has one of these, so the hint must not claim
    # credentials that don't exist there (see LoginPage.tsx).
    is_demo = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    # H6: every access token embeds the token_version it was issued under
    # (see services.auth_service.create_access_token); api.deps.
    # get_current_user rejects a token whose "tv" claim doesn't match the
    # user's CURRENT token_version. Bumped on self-service password change
    # and administrator password reset, so changing a password immediately
    # invalidates every other still-live token for that account -- without
    # this, a stolen or previously-shared token would keep working for its
    # full 12-hour lifetime even after the password that (in the attacker's
    # mind) "protects" it has been changed.
    token_version = Column(Integer, nullable=False, default=1)


class Standard(Base):
    __tablename__ = "standards"
    id = Column(String, primary_key=True, default=uid)
    standard_id = Column(String, unique=True, nullable=False)  # e.g. STD-0001
    name = Column(String, nullable=False)                      # e.g. "IS 694"
    edition = Column(String)                                   # e.g. "2010"
    amendment = Column(String)                                 # e.g. "Amendment 3 (2015)"
    product_family = Column(String, default="CABLE")
    scope_summary = Column(Text)


class TestDefinition(Base):
    __tablename__ = "test_definitions"
    id = Column(String, primary_key=True, default=uid)
    test_id = Column(String, unique=True, nullable=False)  # e.g. TEST-0001
    name = Column(String, nullable=False)
    category = Column(String)             # Electrical / Dimensional / Mechanical / Fire
    unit = Column(String)
    input_schema = Column(JSON)           # list of {key,label,type,unit} raw fields the Scientific Assistant fills in
    sequence = Column(Integer, default=0)

    # Groups tests into the same lettered sections Test Report_694.docx uses
    # (IS 694:2010 Table 1, Sl. No. iii): a) Test on Conductor, b) Overall
    # dimensions & thickness, c) Physical test on Insulation/Sheath,
    # d) Test on Completed Cable. Drives the Calculation tab's section
    # headers so it renders as the same grouped tables the report uses,
    # not a flat list.
    report_section = Column(String, nullable=True)

    # scope drives how the Rule Engine expands this test into AssignedTest rows:
    #   ONCE                 -- a single whole-sample result (e.g. Flammability)
    #   PER_CORE              -- one result per tested core/color (e.g. Conductor Resistance)
    #   PER_CORE_AND_SHEATH   -- one result per tested core/color, PLUS a separate sheath result
    #                            (e.g. Tensile/Elongation, which IS 694 requires on both
    #                            insulation-per-core and the outer sheath)
    #   SHEATH_ONLY           -- a single whole-sample result, but specifically about the sheath
    #                            (e.g. Sheath Thickness -- distinct from per-core Insulation Thickness)
    scope = Column(String, default="ONCE")

    # For tests whose calculation depends on a prior test's accepted result on the SAME
    # core/sheath position (e.g. "Ageing" needs the base Tensile/Elongation test's median
    # as its "before" value) -- NULL for tests with no such dependency.
    depends_on_test_id = Column(String, ForeignKey("test_definitions.test_id"), nullable=True)


class TestAssignmentRule(Base):
    __tablename__ = "test_assignment_rules"
    id = Column(String, primary_key=True, default=uid)
    rule_id = Column(String, unique=True, nullable=False)
    standard_id = Column(String, ForeignKey("standards.standard_id"))
    test_id = Column(String, ForeignKey("test_definitions.test_id"))
    condition = Column(String, nullable=False)   # e.g. "always", "fire_category in (FR,FR-LSH)"
    mandatory = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    clause_reference = Column(String)


class Sample(Base):
    __tablename__ = "samples"
    id = Column(String, primary_key=True, default=uid)
    sample_id = Column(String, unique=True, nullable=False)  # e.g. SMP-2026-0014
    product_family = Column(String, default="CABLE")
    standard_id = Column(String, ForeignKey("standards.standard_id"))
    cores = Column(Integer)
    csa_mm2 = Column(Float)
    remarks = Column(Text)

    # Core-count/colour-testing logic (Sprint Priority 9): decided by the
    # Scientist at registration, before a profile exists, because "how many
    # cores will actually be tested" must be known before the Rule Engine
    # can expand PER_CORE tests. This is the COUNT only; which physical
    # core gets which colour is a separate, explicit choice made later
    # during profiling (see CableProfile.tested_core_colors below).
    cores_tested = Column(Integer, nullable=True)
    # Both indexed (H4): assigned_assistant_id is filtered on every
    # list_samples/dashboard call for a SCIENTIFIC_ASSISTANT (every sample
    # they can see, on every page load), and status is the optional
    # list_samples filter plus the natural "show me everything in TESTING"
    # query a LIMS gets asked constantly.
    status = Column(String, default=SampleStatus.REGISTERED.value, index=True)
    # H16: the Scientist's explanation when RETURNing a sample from review
    # (mandatory in that case -- see sample_service.review_sample) -- lets
    # the Assistant see WHY it bounced back instead of just a status change
    # with no context. Cleared on the next APPROVE, since a resolved review
    # cycle has nothing left to act on.
    last_review_comment = Column(Text, nullable=True)
    registered_by_id = Column(String, ForeignKey("users.id"))
    assigned_assistant_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    profile: Mapped[Optional["CableProfile"]] = relationship("CableProfile", back_populates="sample", uselist=False)
    assigned_tests: Mapped[List["AssignedTest"]] = relationship("AssignedTest", back_populates="sample")
    certificates: Mapped[List["Certificate"]] = relationship("Certificate", back_populates="sample")

    standard: Mapped[Optional["Standard"]] = relationship("Standard")
    registered_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[registered_by_id])
    assigned_assistant: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_assistant_id])


class CableProfile(Base):
    """
    MVP profile shape for the Cable product family only (SDD section 2 calls
    for a per-family schema long-term; this table IS that schema's first,
    single-family instance).
    """
    __tablename__ = "cable_profiles"

    # Calc-time-only scratch fields, not persisted columns: engines.
    # calculation_engine.run_calculation() bolts the sample's CSA/core-count
    # onto the profile instance just before invoking a calculator, since
    # every calc_* function signature only receives `profile`. Declared
    # here (not wrapped in Column(), so classic declarative_base() leaves
    # them as ordinary, unmapped Python attributes -- SQLAlchemy never sees
    # them) purely so mypy understands the pattern instead of flagging
    # every read/write as an attribute that doesn't exist.
    # ClassVar, not Mapped[]: SQLAlchemy 2.0's declarative scanner requires
    # this exact annotation (its own suggestion, verified against the
    # actual ArgumentError it raises otherwise) for a class-level default
    # on a plain, non-ORM-mapped attribute once ANY sibling attribute on
    # this class uses Mapped[] -- profile._csa = x below still sets a
    # perfectly ordinary per-INSTANCE attribute at runtime, identical to
    # before this annotation existed; ClassVar only tells SQLAlchemy/mypy
    # "don't try to map this as a column."
    _csa: ClassVar[Optional[float]] = None
    _cores: ClassVar[Optional[int]] = None

    id = Column(String, primary_key=True, default=uid)
    sample_id = Column(String, ForeignKey("samples.sample_id"), unique=True)
    conductor_material = Column(String)   # Copper / Aluminium
    conductor_class = Column(String)      # 1 / 2 / 5 (IS 8130 classes)
    insulation_type = Column(String)      # PVC Type A / C / D (per IS 5831) -- drives engineering limits
    insulation_material = Column(String, default="PVC")  # PVC / XLPE / PE -- descriptive/diagram label only;
                                                           # only PVC is functionally graded under IS 694 scope today
    sheath_type = Column(String)          # ST1 / ST2 / ST3 / None
    fire_category = Column(String)        # 01 / 02 / FR / FR-LSH
    construction = Column(String)         # free text, e.g. "3 core, sheathed"

    # -- Construction / cross-section diagram fields ---------------------
    # Explicit, per-position colour assignment -- e.g. ["RED","BLUE","YELLOW"]
    # for a 3-core sample, index 0 = physical core position 1, etc. NEVER
    # silently auto-assigned: rule_engine.default_tested_core_colors() still
    # exists as a *suggested* starting point the UI offers, but the
    # Scientist/Assistant must explicitly accept or change it before the
    # profile can be confirmed -- see api/samples.py submit_profile.
    tested_core_colors = Column(JSON, nullable=True)

    has_outer_sheath = Column(Boolean, default=True)
    has_armour = Column(Boolean, default=False)
    has_inner_sheath = Column(Boolean, default=False)
    armour_type = Column(String, nullable=True)      # "Steel Wire" | "Steel Strip" | "Steel Tape" | "Aluminium Wire" | None
    armour_material = Column(String, nullable=True)  # e.g. "Galvanized Steel" (IS 3975 terminology)
    armour_strand_count = Column(Integer, nullable=True)

    # If the real construction doesn't fit the parametric ring model above,
    # a photographed/hand-drawn diagram replaces the generated one entirely.
    hand_drawn_diagram_path = Column(String, nullable=True)

    cable_shape = Column(String, default="Round")  # Round | Flat
    # Measured with calipers during profiling (IS 694 cl.9 / Table 5 col
    # "Max overall diameter"). Overall diameter over the finished cable, and
    # the diameter under the outer sheath (over the laid-up cores, before
    # the outer sheath is applied) -- previously a genuine gap: the Test
    # Report template has a dedicated "Overall diameter in mm" row that this
    # app always left blank because nothing captured it.
    #
    # Round cables only -- "diameter" isn't a meaningful measurement for a
    # flat cross-section.
    overall_diameter_mm = Column(Float, nullable=True)     # OD
    diameter_under_sheath_mm = Column(Float, nullable=True)  # ID

    # Flat cables only (IS 694 cl.22, Table 10 -- "Overall Dimensions, Max
    # (W x H)"). A flat cross-section has two independent dimensions, not
    # one "diameter" -- these are genuinely different fields from OD/ID
    # above, not a relabelling of them.
    flat_width_mm = Column(Float, nullable=True)   # W
    flat_height_mm = Column(Float, nullable=True)  # H

    marking_image_path = Column(String)
    source = Column(String, default="MANUAL")  # MANUAL | OCR_PENDING (OCR stubbed in MVP)
    confirmed = Column(Boolean, default=False)
    confirmed_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="profile")


class AssignedTest(Base):
    __tablename__ = "assigned_tests"
    id = Column(String, primary_key=True, default=uid)
    # Indexed (H4): every summarize_sample() call (fired once per sample on
    # every list_samples/dashboard load) and every get_sample_detail() call
    # filters AssignedTest by sample_id -- the single hottest FK lookup in
    # the app.
    sample_id = Column(String, ForeignKey("samples.sample_id"), index=True)
    test_id = Column(String, ForeignKey("test_definitions.test_id"))
    mandatory = Column(Boolean, default=True)
    enabled = Column(Boolean, default=True)   # scientist can disable an optional test
    status = Column(String, default="PENDING")  # PENDING | IN_PROGRESS | COMPLETED | REPEAT_REQUIRED
    accepted_attempt_id = Column(String, ForeignKey("test_runs.id"), nullable=True)

    # NULL for whole-sample (ONCE-scope) tests. Otherwise "RED"|"YELLOW"|"BLUE"|"BLACK"|
    # "SHEATH" -- a PER_CORE_AND_SHEATH-scope TestDefinition produces one AssignedTest per
    # tested core color AND a separate one with core_position="SHEATH".
    core_position = Column(String, nullable=True)

    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="assigned_tests")
    test_definition: Mapped[Optional["TestDefinition"]] = relationship("TestDefinition")
    attempts: Mapped[List["TestRun"]] = relationship(
        "TestRun", back_populates="assigned_test", foreign_keys="TestRun.assigned_test_id"
    )


class TestRun(Base):
    """One attempt at one assigned test. Immutable once submitted (a repeat
    creates a new row, never edits an old one -- SDD section 6.5, item 12)."""
    __tablename__ = "test_runs"
    id = Column(String, primary_key=True, default=uid)
    assigned_test_id = Column(String, ForeignKey("assigned_tests.id"))
    attempt_number = Column(Integer, default=1)
    raw_values = Column(JSON)             # dict of field -> value, shape defined by TestDefinition.input_schema
    submitted_by_id = Column(String, ForeignKey("users.id"))
    submitted_at = Column(DateTime, default=now)

    # Offline support (phase 3a): a client-generated UUID, one per logical
    # submission -- lets services.sample_service.submit_reading detect and
    # safely short-circuit a replayed offline-queued submission instead of
    # creating a duplicate attempt. Nullable -- only ever set by a client
    # that's actually queueing (the desktop Scientist path never sends one).
    # SQLite's own unique-index semantics treat every NULL as distinct from
    # every other NULL, so this doesn't collide across the many rows that
    # never set it.
    client_request_id = Column(String, nullable=True)

    calculated_value = Column(Float, nullable=True)
    calculated_unit = Column(String, nullable=True)
    limit_value = Column(Float, nullable=True)
    limit_operator = Column(String, nullable=True)   # >=, <=, ==
    limit_unit = Column(String, nullable=True)
    margin_pct = Column(Float, nullable=True)

    limit_source_kind = Column(String, nullable=True)   # VERIFIED | PLACEHOLDER | MISSING
    limit_source_ref = Column(String, nullable=True)    # e.g. "IS 8130:2013 Table 2"

    confidence_state = Column(String, default=ConfidenceState.NOT_EVALUATED.value)
    result = Column(String, default=TestResult.PENDING.value)
    result_explanation = Column(Text)

    # -- Scientist override -----------------------------------------------
    # Layered on top, never mutating the fields above (this row is immutable
    # once submitted -- see class docstring). A Scientist who has grounds to
    # believe the Standards Knowledge Base's limit is wrong for this specific
    # test (e.g. the wrong conductor class was used) records the limit they
    # believe is correct and the final PASS/FAIL, with a mandatory reason --
    # never a silent "just mark it PASS". See app.engines.result_utils.
    overridden = Column(Boolean, default=False)
    override_result = Column(String, nullable=True)       # PASS | FAIL
    override_limit_value = Column(Float, nullable=True)    # the limit the Scientist is using instead
    override_reason = Column(Text, nullable=True)
    overridden_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime, nullable=True)

    # -- Scientist verification --------------------------------------------
    # A lighter-weight QA step, distinct from override: confirms the
    # Scientist has looked at this raw reading (most often Assistant-
    # submitted) and endorses it, without changing any decision. Shown as a
    # "Verify" action in the Observation stage.
    verified = Column(Boolean, default=False)
    verified_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    assigned_test: Mapped[Optional["AssignedTest"]] = relationship(
        "AssignedTest", back_populates="attempts", foreign_keys=[assigned_test_id]
    )
    submitted_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[submitted_by_id])
    overridden_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[overridden_by_id])
    verified_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[verified_by_id])

    # H4: covers engines.result_utils.get_accepted_run's fallback query --
    # "the latest attempt for this assigned test" (WHERE assigned_test_id =
    # ? ORDER BY attempt_number DESC LIMIT 1) -- exercised once per
    # AssignedTest on every sample-summary/detail view, same hot path as
    # AssignedTest.sample_id above.
    __table_args__ = (
        Index("ix_test_runs_assigned_test_id_attempt_number", "assigned_test_id", "attempt_number"),
        # Offline support (phase 3a): enforces the dedupe guarantee at the DB
        # level too, not just in the service-layer lookup -- see
        # sample_service.submit_reading's IntegrityError handling for why.
        Index("uq_test_runs_assigned_test_client_request_id", "assigned_test_id", "client_request_id", unique=True),
    )


class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(String, primary_key=True, default=uid)
    certificate_no = Column(String, unique=True, nullable=False)
    # Indexed (H4): get_sample_detail looks up "does this sample have a
    # certificate yet" by sample_id on every sample detail page load.
    sample_id = Column(String, ForeignKey("samples.sample_id"), index=True)
    generated_by_id = Column(String, ForeignKey("users.id"))
    generated_at = Column(DateTime, default=now)
    overall_decision = Column(String)
    file_path = Column(String)
    # H10: SHA-256 of file_path's contents at the moment it was generated
    # (see services/checksum.py) -- lets anyone with a copy of the .docx
    # confirm it's byte-for-byte what the system actually produced, not a
    # tampered or corrupted copy. Nullable rather than backfilled for
    # certificates issued before this column existed: computing a
    # checksum for a file whose exact bytes at generation time were never
    # recorded would be fabricating provenance, not recovering it -- a
    # NULL here honestly means "generated before integrity checksums
    # existed," never a guessed value.
    file_checksum_sha256 = Column(String, nullable=True)

    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="certificates")
    generated_by: Mapped[Optional["User"]] = relationship("User")


class AuditEvent(Base):
    """Lightweight audit trail for the MVP -- append-only at the application
    layer. Hash-chaining + DB-permission enforcement is a Phase 7 hardening
    item per the Roadmap, deliberately not built for a one-day demo."""
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True, default=uid)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    actor_name = Column(String)
    action = Column(String, nullable=False)
    entity_type = Column(String)
    entity_id = Column(String)
    details = Column(JSON)
    # Indexed (H4): both the dashboard's recent-activity panel and the
    # Administrator console's audit view run ORDER BY timestamp DESC LIMIT
    # on this table on every load -- it's the one table in this schema that
    # grows unboundedly (append-only, one row per action, for the lab's
    # entire operational lifetime), so an unindexed full-table sort here is
    # exactly the kind of thing that's invisible on a demo DB and slow
    # after a year of real use.
    timestamp = Column(DateTime, default=now, index=True)


class Sequence(Base):
    """Backs transactional number allocation for human-readable IDs (sample
    numbers, certificate numbers) -- see services/sequence_service.py. Was
    previously `COUNT(matching rows) + 1`, computed fresh on every
    registration/certificate, which raced under concurrent requests (two
    callers reading the same count before either commits -> duplicate
    number -> unhandled IntegrityError) and would go backwards the moment
    any row was ever deleted."""
    __tablename__ = "sequences"
    id = Column(String, primary_key=True, default=uid)
    kind = Column(String, nullable=False)         # "SAMPLE" | "CERTIFICATE"
    year = Column(Integer, nullable=False)
    next_value = Column(Integer, nullable=False, default=1)

    __table_args__ = (UniqueConstraint("kind", "year", name="uq_sequence_kind_year"),)
