import os
import shutil
import time

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import admin, auth, certificates, dashboard, meta, samples
from app.config import settings
from app.db import DATA_DIR, engine, get_db
from app.db_migrate import run_migrations
from app.logging_config import configure_logging, get_logger, new_request_id, set_request_id
from app.services.docx_report_filler import TEMPLATE_PATH as CERTIFICATE_TEMPLATE_PATH
from app.services.observation_sheet_filler import TEMPLATE_PATH as OBSERVATION_SHEET_TEMPLATE_PATH

configure_logging()
logger = get_logger("main")

app = FastAPI(title="CableLIMS", version="0.1.0-mvp")

app.add_middleware(
    CORSMiddleware,
    # H19: sourced from Settings (env-overridable, see config.py's own
    # comment on this field for the full reasoning) -- defaults to the local
    # Vite dev origin only, not a wildcard. The documented deployment (this
    # backend serving the built frontend on its own origin, see
    # FRONTEND_DIST below) never actually needs a cross-origin allowance;
    # this exists for direct browser-tool access to the API and for anyone
    # running a genuinely split-origin deployment (who must set this
    # explicitly). allow_credentials stays False regardless -- auth is a
    # Bearer token in the Authorization header, never a cookie, so there's
    # no ambient credential for a cross-origin page to ride even if its
    # origin were allowed.
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    # A client-supplied X-Request-ID is honoured (lets a future reverse
    # proxy or the frontend correlate its own logs), otherwise one is
    # generated -- either way, every log line emitted while handling this
    # request carries it (see logging_config._RequestIdFilter), and it's
    # echoed back so a Scientist reporting "it broke" can hand over an ID
    # that's actually traceable in backend/logs/cablelims.log.
    request_id = request.headers.get("x-request-id") or new_request_id()
    set_request_id(request_id)
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    level = logger.warning if response.status_code >= 400 else logger.info
    level(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Previously: an unhandled exception anywhere (a malformed float(), a
    # math domain error, a sequence IntegrityError, a missing template file)
    # produced a generic 500 with a stack trace printed to a console window
    # the operator is told to minimise -- and under Task Scheduler ("run
    # whether user is logged on or not"), no console exists at all, so it
    # went nowhere. Now it's always logged with a full traceback and this
    # request's correlation ID, and the caller gets a clean, safe response
    # instead of whatever text repr the raw exception happened to produce.
    logger.error(f"Unhandled exception on {request.method} {request.url.path}", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please try again "
                                                             "or contact support with this request's timestamp."})


logger.info(run_migrations(engine))

app.include_router(auth.router)
app.include_router(samples.router)
app.include_router(certificates.router)
app.include_router(dashboard.router)
app.include_router(meta.router)
app.include_router(admin.router)


# Below this, disk space is considered "low" -- not exhausted, but close
# enough to warrant a warning before it actually stops the app from writing
# new samples/certificates. SQLite's own failure mode on a genuinely full
# disk is not always clean, so this is meant to give an operator a chance
# to notice before that happens, not just report the exhaustion after.
# H14: sourced from Settings (env-overridable).
LOW_DISK_SPACE_BYTES = settings.low_disk_space_bytes


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    # Previously this returned {"status": "ok"} unconditionally, regardless
    # of whether the database was reachable, the report templates existed,
    # or the disk had any space left -- a completely broken application
    # would still report healthy. Every check below is something that has
    # a real, named failure mode elsewhere in this codebase (a missing
    # template raises FileNotFoundError mid-certificate-generation; a full
    # disk fails SQLite writes unpredictably) -- this surfaces those before
    # a Scientist hits them mid-workflow, not after.
    checks = {}
    healthy = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"unreachable: {e}"
        healthy = False

    for name, path in [
        ("certificate_template", CERTIFICATE_TEMPLATE_PATH),
        ("observation_sheet_template", OBSERVATION_SHEET_TEMPLATE_PATH),
    ]:
        if os.path.exists(path):
            checks[name] = "ok"
        else:
            checks[name] = f"missing: {path}"
            healthy = False

    try:
        free_bytes = shutil.disk_usage(DATA_DIR).free
        checks["disk_space"] = f"ok ({free_bytes // (1024 * 1024)} MB free)"
        if free_bytes < LOW_DISK_SPACE_BYTES:
            checks["disk_space"] = f"low ({free_bytes // (1024 * 1024)} MB free)"
            healthy = False
    except OSError as e:
        checks["disk_space"] = f"unknown: {e}"
        healthy = False

    body = {"status": "ok" if healthy else "degraded", "service": "CableLIMS MVP", "checks": checks}
    if not healthy:
        logger.warning(f"Health check reporting degraded: {checks}")
    return JSONResponse(status_code=200 if healthy else 503, content=body)


# --- Serve the built frontend (production/server deployment) ---------------
# In local development, run `npm run dev` in frontend/ separately (Vite's
# dev server + proxy, per README) -- this block is inert then, since
# frontend/dist won't exist yet. For a server install, run `npm run build`
# once and this backend serves the compiled static site on the SAME port as
# the API: one process to keep running, and Node.js is only needed at build
# time, not on the server itself. See DEPLOYMENT.md.
FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend", "dist")
)

if os.path.isdir(FRONTEND_DIST):
    _FRONTEND_DIST_REAL = os.path.realpath(FRONTEND_DIST)

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        # full_path is attacker-controlled. os.path.join alone does not
        # stop ".." segments (and Starlette percent-decodes the path
        # *after* routing, so "%2e%2e" arrives here as ".." too) -- without
        # this containment check, a request could escape FRONTEND_DIST and
        # read any file the process can (e.g. backend/data/cablelims.db or
        # backend/data/.secret_key). realpath() resolves both ".." and
        # symlinks before the comparison, so both variants are closed.
        candidate = os.path.realpath(os.path.join(FRONTEND_DIST, full_path))
        is_contained = (
            candidate == _FRONTEND_DIST_REAL
            or candidate.startswith(_FRONTEND_DIST_REAL + os.sep)
        )
        if full_path and is_contained and os.path.isfile(candidate):
            return FileResponse(candidate)
        # Any other path (a client-side route like /dashboard, or a direct
        # deep link like /assistant/samples/SMP-2026-0001) falls back to
        # index.html so React Router can take over -- this is what makes a
        # phone bookmark or a page refresh work correctly.
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
