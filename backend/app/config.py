"""
Centralized runtime configuration (H14).

Every operationally-tunable value in this app lives here, sourced from
environment variables (prefixed CABLELIMS_) or a `backend/.env` file --
see .env.example for the full list with defaults and descriptions. An
operator overrides one by setting it in the environment before running
start_cablelims.bat, or by copying .env.example to .env and editing it;
neither requires touching source code.

Deliberately NOT centralized here: engineering/scientific constants that
encode a domain or measurement decision rather than a deployment
preference -- e.g. confidence_engine.GUARD_BAND_PCT (what counts as
"confident enough" for an automatic PASS/FAIL is a QA/scientific policy
decision, calibrated deliberately, not something that should silently
change because an environment variable was set) and
rule_engine.MAX_NAMED_CORE_COLORS (a physical fact about how many core
colours IS 694 assigns names to, not a preference). Also not here: the
JWT signing secret itself (see auth_service._load_or_create_secret_key) --
its env var name (CABLELIMS_SECRET_KEY) is documented below for
discoverability, but its value is deliberately never routed through this
module, so it can never accidentally end up in a settings dump/log.
"""
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CABLELIMS_", env_file=".env", extra="ignore")

    # -- Authentication / sessions --------------------------------------------
    access_token_expire_hours: int = Field(
        12, description="How long an access token stays valid before requiring a fresh login.",
    )

    # -- Login throttling (services/login_throttle.py) ------------------------
    login_max_failures: int = Field(
        5, description="Failed login attempts (same username+source IP) before that pair is locked out.",
    )
    login_lockout_seconds: int = Field(
        15 * 60, description="How long a triggered lockout lasts, in seconds.",
    )
    login_failure_window_seconds: int = Field(
        15 * 60,
        description="A failure older than this doesn't count toward the lockout threshold -- "
                    "resets an in-progress failure streak.",
    )

    # -- Uploads (services/image_upload.py) ------------------------------------
    max_upload_bytes: int = Field(
        10 * 1024 * 1024, description="Maximum accepted size for an uploaded marking/diagram photo, in bytes.",
    )
    upload_jpeg_quality: int = Field(
        85, description="JPEG re-encode quality (1-95) every uploaded image is normalized to.",
    )

    # -- Logging (logging_config.py) -------------------------------------------
    log_max_bytes: int = Field(
        5 * 1024 * 1024, description="Rotate backend/logs/cablelims.log once it reaches this size, in bytes.",
    )
    log_backup_count: int = Field(
        5, description="How many rotated log files to keep before the oldest is deleted.",
    )

    # -- Backups (backup.py) ---------------------------------------------------
    backup_default_keep: int = Field(
        30, description="How many timestamped backups run_backup() keeps before pruning the oldest.",
    )

    # -- Health check (main.py) ------------------------------------------------
    low_disk_space_bytes: int = Field(
        500 * 1024 * 1024,
        description="/api/health reports 'degraded' once free disk space on the data volume drops below this, in bytes.",
    )

    # -- Database (db.py) -------------------------------------------------------
    db_busy_timeout_ms: int = Field(
        5000,
        description="SQLite busy_timeout -- how long a writer waits for a lock held by another "
                    "connection before failing outright, in milliseconds.",
    )

    # -- CORS (main.py) -----------------------------------------------------------
    # H19: the wildcard default was reconsidered, not just left permissive
    # "because Bearer tokens make CSRF moot" (true, but beside the point --
    # CORS also controls whether an arbitrary third-party page can read the
    # API's JSON response cross-origin, which a wildcard allows regardless
    # of the auth model). Tracing this app's actual browser traffic: the
    # documented production deployment serves the built frontend from the
    # SAME origin as the API (main.py's own FRONTEND_DIST block), and the
    # documented local-dev setup (README.md) has Vite proxy /api itself
    # (vite.config.ts) -- so in both supported paths, the browser's request
    # is same-origin and these CORS headers are never even consulted. The
    # one genuine use is a browser-based TOOL hitting the dev backend
    # directly (e.g. a standalone test page, or /docs's "Try it out" from a
    # different port) -- which only ever needs the Vite dev origin, not the
    # whole internet. A deployment that genuinely splits frontend and
    # backend across two origins (not the documented setup) must set this
    # explicitly to that frontend's real origin(s) -- see .env.example.
    # NoDecode: pydantic-settings' default env parsing for a List[str] field
    # expects JSON (e.g. '["a","b"]') -- unusable for a non-technical
    # operator editing .env by hand (see logging_config.py's docstring on
    # who actually reads this app's operational surfaces). NoDecode skips
    # that JSON pre-parse so the before-validator below sees the raw
    # env-var string and can split it on commas instead.
    cors_allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Origins allowed to call the API cross-origin (comma-separated in the env "
                    "var). Defaults to the local Vite dev server only -- the documented "
                    "deployment (frontend served by this same backend) never needs a cross-origin "
                    "allowance at all, since the browser's requests are same-origin. Set this "
                    "explicitly if you're running a non-standard split-origin deployment.",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated_origins(cls, value: object) -> object:
        # A value that's already a list (the Python default_factory, or a
        # future non-env source) passes through untouched.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
