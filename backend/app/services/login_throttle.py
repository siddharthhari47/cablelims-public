"""
In-process login throttling: 5 failed attempts against the same
(username, source IP) pair locks that pair out for 15 minutes.

Deliberately NOT slowapi/Redis-backed -- this app runs as a single uvicorn
process on one machine (see DEPLOYMENT.md; there is no multi-worker or
multi-instance deployment story here), so a plain in-memory counter guarded
by a lock is both sufficient and one fewer dependency to maintain. If this
ever becomes a genuinely multi-instance deployment, this module is the one
place that would need to move to a shared store.

Keyed on (username, ip) rather than username alone: locking out only by
username would let an attacker with many source IPs bypass the limit
entirely by rotating IPs (irrelevant at this app's actual scale, but free to
avoid); keyed on ip alone would let one attacker lock a legitimate user out
of their own account from the outside. Username is tracked as typed, not
resolved against an actual User row first -- so a nonexistent username is
throttled exactly the same as a real one, which avoids letting the presence
or absence of a lockout become a second username-enumeration side channel
alongside the login endpoint's already-uniform error message.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Tuple

from app.config import settings

# H14: sourced from Settings (env-overridable) instead of module-level
# constants. Re-exported under their old names since other modules
# (api/auth.py) and tests import these directly.
MAX_FAILURES = settings.login_max_failures
LOCKOUT_SECONDS = settings.login_lockout_seconds
# A failure streak older than this doesn't count toward the threshold --
# without it, 5 isolated mistyped passwords spread across a whole month
# would eventually lock someone out, which isn't the threat this defends
# against.
FAILURE_WINDOW_SECONDS = settings.login_failure_window_seconds


@dataclass
class _Entry:
    failures: int = 0
    first_failure_at: float = field(default_factory=time.monotonic)
    locked_until: float = 0.0


_entries: Dict[Tuple[str, str], _Entry] = {}
_lock = threading.Lock()


def _key(username: str, ip: str) -> Tuple[str, str]:
    return (username.strip().lower(), ip)


def is_locked_out(username: str, ip: str) -> Tuple[bool, float]:
    """Returns (locked, seconds_remaining)."""
    now = time.monotonic()
    with _lock:
        entry = _entries.get(_key(username, ip))
        if entry and entry.locked_until > now:
            return True, entry.locked_until - now
        return False, 0.0


def record_failure(username: str, ip: str) -> bool:
    """Records a failed attempt; returns True if this attempt is the one
    that triggered a NEW lockout (so the caller can audit/log it distinctly
    from an ordinary failed attempt)."""
    now = time.monotonic()
    key = _key(username, ip)
    with _lock:
        entry = _entries.setdefault(key, _Entry())
        if now - entry.first_failure_at > FAILURE_WINDOW_SECONDS:
            entry.failures = 0
            entry.first_failure_at = now
        entry.failures += 1
        newly_locked = False
        if entry.failures >= MAX_FAILURES and entry.locked_until <= now:
            entry.locked_until = now + LOCKOUT_SECONDS
            newly_locked = True
        return newly_locked


def record_success(username: str, ip: str) -> None:
    with _lock:
        _entries.pop(_key(username, ip), None)


def reset_all() -> None:
    """Test-only: this module's state is a process-wide global by design
    (see module docstring), so tests that exercise lockout behaviour must
    reset it first -- otherwise failures recorded by one test could leak
    into another test reusing the same username within the same pytest
    process."""
    with _lock:
        _entries.clear()
