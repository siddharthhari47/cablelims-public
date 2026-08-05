"""
Structured-ish logging + a per-request correlation ID.

Previously the entire application had exactly one deliberate output
statement (db_migrate's schema-update print()) and no logging at all: no
levels, no destination other than a console window the operator is
explicitly instructed to minimise, and -- run under Task Scheduler with
"run whether user is logged on or not" (see DEPLOYMENT.md), which has no
console at all -- that one print() went nowhere either. When something
broke, there was no way to answer "what happened, and when."

Plain-text lines rather than JSON, deliberately: this app's actual operator
is a non-technical person who might open this file in Notepad when told
"something went wrong, check the log" (see SELF_HOST_GUIDE.md's whole
tone) -- a JSON-lines file is more machine-parseable but considerably less
useful to that specific reader. The format below is still consistently
structured (timestamp | level | request id | logger | message) and
trivially greppable, which covers the actual need here without requiring a
JSON-aware tool to read it.
"""
import contextvars
import logging
import logging.handlers
import os
import uuid

from app.config import settings

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    os.makedirs(LOGS_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | req=%(request_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    request_id_filter = _RequestIdFilter()

    # 5 MB x 5 backups (H14: Settings-configurable) is comfortably more
    # than a single lab's traffic would fill in normal operation, without
    # growing unboundedly on a machine nobody is actively monitoring disk
    # space on.
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOGS_DIR, "cablelims.log"),
        maxBytes=settings.log_max_bytes, backupCount=settings.log_backup_count, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(request_id_filter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.addFilter(request_id_filter)

    root = logging.getLogger("cablelims")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"cablelims.{name}")
