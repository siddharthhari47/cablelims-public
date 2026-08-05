# CableLIMS — Software Design Document v2

`README.md` references this document five times; it didn't exist in the package the Review #2
audit had access to (H22 / B12, Review #2 remediation). This describes the system as it's
actually built today — not a design proposal, a description of what's already implemented and
tested.

---

## 1. System overview

CableLIMS is a single-lab LIMS appliance for cable conformity testing under IS 694 (National Test
House). One FastAPI backend (`backend/app`), one SQLite database (WAL mode), serving a built
React/Vite frontend from its own origin. No separate database server, no message queue, no
multi-process deployment — the whole application is one process an operator starts by
double-clicking a batch file (see `DEPLOYMENT.md`).

Two client experiences share the same backend and API:
- **Scientist desktop console** — register samples, review Assistant-submitted readings, approve,
  generate the Test Report.
- **Scientific Assistant mobile PWA** — installable, works fully offline for the dominant
  in-lab workflow (profile capture, test readings) once a sample has been opened online at least
  once. See §5.

**Core engineering principle, unchanged since the project's first line of code: never guess.**
Every numeric limit traces to a specific standard/clause. A value the Standards Knowledge Base
doesn't actually verify is never silently treated as if it were — it's marked `PLACEHOLDER` or
`MISSING` and routed to `UNDETERMINED`, never an automatic PASS/FAIL. This shows up throughout the
design below, most concretely in §4 (the SKB) and §3 (the confidence engine).

## 2. Data model

Eleven SQLAlchemy models (`backend/app/models/models.py`), Alembic-migrated (`backend/alembic/`,
see `MIGRATIONS.md`):

| Model | Purpose |
|---|---|
| `User` | Login accounts. `role` is SCIENTIST / SCIENTIFIC_ASSISTANT / ADMINISTRATOR. `token_version` supports session revocation (H6) — bumped on password change, invalidates every other live token for that account. |
| `Standard` | A testing standard (currently one row: IS 694:2010). |
| `TestDefinition` | One row per test in the catalog (~27), with `input_schema` (the exact fields the UI collects and `reading_schemas.py` validates against) and `report_section` (which heading of `Test Report_694.docx` it belongs under). |
| `TestAssignmentRule` | Drives `rule_engine.assign_tests()` — which tests apply to a given profile (core count, fire category, etc.). |
| `Sample` | One physical cable sample under test. `status` drives the workflow state machine (PENDING → TESTING → SCIENTIST_REVIEW → APPROVED → REPORT_GENERATED → ARCHIVED); `LOCKED_STATUSES` gates every mutating route once a sample is past APPROVED. |
| `CableProfile` | Construction details (conductor material/class, insulation type, sheath type, fire category, core colors, armour, dimensions) — the input the rule engine assigns tests from. One profile per sample; re-profiling retracts stale test assignments (C10) rather than leaving orphaned rows. |
| `AssignedTest` | One row per (sample, test) the rule engine decided applies. Tracks `status`, `mandatory`/`enabled` (a Scientist can disable an optional test), and `accepted_attempt_id` — the load-bearing pointer to which `TestRun` actually counts (see C6/C9 below). |
| `TestRun` | One attempt at one assigned test. **Immutable once submitted** — a repeat creates a new row, never edits an old one. Carries the calculated value, the resolved limit (with its `limit_source_kind`: VERIFIED/PLACEHOLDER/MISSING), the PASS/FAIL/UNDETERMINED result, and separate override/verify layers that sit on top without ever mutating the original submission. |
| `Certificate` | A generated Test Report, with a SHA-256 checksum of the file (H10) so tampering after generation is detectable. |
| `AuditEvent` | Every login, submission, override, review action, admin action — actor, action, entity, timestamp, IP. |
| `Sequence` | Backs transactional sample/certificate numbering (C8) — an atomic `UPDATE ... RETURNING`, not read-modify-write, so two concurrent registrations can never collide. |

**Immutability discipline:** `TestRun` rows are never edited after submission. An override
(`overridden`, `override_result`, `override_reason`, `overridden_by_id`) or a verification
(`verified`, `verified_by_id`) is a separate, explicitly-flagged layer recorded on the *same* row
without touching the original `result`/`calculated_value` — `engines/result_utils.py`'s
`effective_result()` is the one place that resolves the two into a final answer, so every caller
sees an override the same way.

## 3. The rule / calculation / confidence engine trio (`backend/app/engines/`)

Three independent, pure-function-style modules, each testable without a database:

- **`rule_engine.py`** — given a `CableProfile`, decides which `TestDefinition`s apply
  (`assign_tests`), expands per-core tests into one `AssignedTest` per tested core position
  (`expand_for_positions`), and suggests (never auto-applies) core colors.
- **`calculation_engine.py`** — 27 pure calculator functions (`calc_conductor_resistance`,
  `calc_elongation`, `calc_halogen_acid_gas`, etc.), one per test, each taking raw validated
  readings and returning a `CalcResult` (value, unit, resolved limit, operator). Golden-value
  tested (`tests/test_calculation_golden_values.py`) against BIS-verified expected outputs, not
  just against the code's own logic.
- **`confidence_engine.py`** — turns a `CalcResult` into a final PASS/FAIL/UNDETERMINED plus a
  `confidence_state`. The one rule that matters most: **a PLACEHOLDER or MISSING limit can never
  produce an automatic PASS/FAIL** — it always routes to UNDETERMINED / REVIEW_REQUIRED, with the
  caveat text carried into `TestRun.result_explanation` so a Scientist sees *why* before
  confirming it (see §4).
- **`aggregation.py`** — the "System Decision" summary (applicable/completed/passed/failed
  counts, overall confidence) shown on both the sample-detail view and, in bulk, the
  list/dashboard screens. `summarize_samples_bulk()` computes this for every sample on a page in
  a constant number of queries (H5) rather than one round-trip per sample; `pick_accepted_run()`
  (promoted to public in B7) is the shared "which attempt counts" resolution rule, reused by
  `services/sample_service.get_sample_detail` for the same reason.
- **`reading_schemas.py`** — one Pydantic model per test_id, registered in `READING_SCHEMAS`,
  validating every submitted reading against the exact shape `TestDefinition.input_schema`
  declares before it ever reaches a calculator (C9). Ordering constraints (e.g. a specimen can't
  shrink to a *larger* size, B11) are guarded here when a bad value would otherwise be a silent,
  wrong-direction PASS — and explicitly *not* guarded (with a comment explaining why) where the
  physically odd case is actually real, e.g. `LossOfMassReading`'s genuine moisture-pickup case.

## 4. The Standards Knowledge Base (`services/standards_service.py` + `skb_seed_data.py`)

The SKB is the single place standard-derived numeric limits live — every lookup returns a
`LookupResult` with a `kind`: `VERIFIED` (a real, citable clause value), `PLACEHOLDER` (a value
that exists but isn't independently standard-verified — inferred, secondary-sourced, or an
CTL-operational classification not in the printed standard), or `MISSING` (no criterion at all).
Nothing outside this module needs to change if the placeholder data here is later replaced by a
real, licensed SKB integration — every caller already goes through this contract.

**The caveat convention:** a `PLACEHOLDER` is marked in `skb_seed_data.py` either per-value (a
sibling key named `"{key}_flag"`) or per-row (`"_provenance"`, e.g. Insulation Type D and Sheath
Type ST3, which are CTL's own operational classifications entirely absent from IS 5831:1984, not
merely one uncertain cell within an otherwise-verified type). `standards_service._caveat_for()` is
the one place that resolves either form into the caveat text carried forward as the
`LookupResult.note`. `tests/test_skb_caveats.py` enforces this as a contract, not just a
convention — a data-driven, parametrized test walking every caveated entry in `skb_seed_data.py`
and asserting the corresponding lookup is never `VERIFIED`.

## 5. Offline support (Scientific Assistant PWA)

Five phases, all shipped:

1. **Installable app shell** — `vite-plugin-pwa`, real icon set, service worker precaching the
   built frontend.
2. **Read-side cache** — IndexedDB (`frontend/src/offline/db.ts`) mirrors the sample list and
   sample detail on every successful fetch; a network failure (distinguished from a real HTTP
   error — a 401 must still trigger logout, never be treated as "offline") falls back to the
   cached copy with a visible "showing cached data from..." banner.
3. **Write-side outbox** (`outbox.ts`, `syncEngine.ts`, `queueOrSend.ts`) — a mutating request
   that fails on a genuine network error is queued in IndexedDB instead of rejecting outright, and
   replayed once connectivity returns. Backed server-side by `TestRun.client_request_id`
   idempotency (a unique `(assigned_test_id, client_request_id)` index) so a replayed submission
   after a lost confirmation can never create a duplicate attempt.
4. **Sync status UI + image compression** — a pending-item badge, and canvas-based photo
   resize/re-encode before a marking/diagram image ever reaches the outbox (smaller queued
   payloads, EXIF stripped as a side effect).
5. **Opt-in auth persistence** — the default (`sessionStorage`-only, "a new tab forces login") is
   unchanged; a separate, explicit "Stay signed in on this device" toggle persists a session
   *only* when the app is genuinely running as an installed, standalone-mode PWA, so a cold
   relaunch with no network available can still restore the session.

**Documented scope boundary:** a brand-new sample's profile can be queued offline, but its test
list doesn't exist until the profile actually syncs (the rule engine that generates `AssignedTest`
rows runs server-side only) — first-time profile capture and first-time test entry can't both
happen in one fully offline session. The dominant real use case (an already-profiled sample,
losing connectivity mid-way through its 18–52 test readings) works fully offline.

## 6. API surface (`backend/app/api/`)

Thin HTTP controllers (H2) — every route parses the request, resolves auth/ownership via
`api/deps.py`, delegates to the corresponding `services/*.py` function, and returns whatever it
hands back. No business logic lives in the route handlers themselves.

| Router | Prefix | Covers |
|---|---|---|
| `auth.py` | `/api/auth` | Login (rate-limited, C12), self-service password change, session info, the demo-hint endpoint (gated on `CABLELIMS_ALLOW_DEMO_USERS`, B6). |
| `samples.py` | `/api/samples` | The sample lifecycle end to end — list (paginated, B7), create, profile, readings, review, override, verify, certificate generation, image uploads. 15 routes, all sample-scoped ones behind `deps.get_authorized_sample()`. |
| `certificates.py` | `/api/certificates` | Certificate/observation-sheet download, ownership-checked (C11). |
| `dashboard.py` | `/api/dashboard` | The Scientist's summary counts. |
| `admin.py` | `/api/admin` | User management, audit log (paginated) — Administrator-only. |
| `meta.py` | `/api/meta` | Standards catalog, procedure/calculation reference notes. |

**Authorization** (`api/deps.py`): `get_authorized_sample()` is the single dependency every
sample-scoped route uses — resolves the `Sample`, enforces that a SCIENTIFIC_ASSISTANT can only
reach a sample assigned to them (a missing/unauthorized sample both return 404, never 403, so an
assistant can't distinguish "doesn't exist" from "not yours"), and enforces the lock check
(`allow_locked=True` opts a read-only or already-self-checking route out).

**Security posture:** Bearer-token auth (JWT, `token_version`-checked per request, never a
cookie), CORS restricted to an explicit allowlist (H19), global security headers on every response
(`nosniff`/`X-Frame-Options: DENY`/`Referrer-Policy`, B10), structured logging with per-request
correlation IDs, and — as of B4 — TLS termination via a Caddy reverse proxy in front of the app
(see `DEPLOYMENT.md` step 7), with the app itself bound to loopback only.
