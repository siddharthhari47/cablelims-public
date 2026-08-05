"""
WAL-safe backup for CableLIMS's data.

DEPLOYMENT.md previously said "everything that matters is one file --
cablelims.db -- copy it on a schedule." That is unsafe: db.py runs SQLite in
WAL mode, which means recently-committed transactions live in a separate
cablelims.db-wal file until a checkpoint folds them back into the main
file. A plain file copy of cablelims.db while the server is running yields
a backup missing everything since the last checkpoint, and can be
structurally inconsistent if the copy lands mid-checkpoint.

This uses sqlite3.Connection.backup() -- the SQLite online backup API,
specifically designed to be safe against a live, concurrently-written
database (WAL or not) -- and also copies certificates/ and uploads/, which
the old instruction omitted entirely despite being part of the technical
record.

Run manually (backup_now.bat) or wire into Windows Task Scheduler for a
nightly run, the same way start_cablelims.bat itself is scheduled -- see
DEPLOYMENT.md.

Usage:
    venv\\Scripts\\python -m app.backup [destination_dir]

Defaults to backend\\backups\\ if no destination is given. That default is
convenient but does NOT satisfy "off-site" -- it is still one disk failure
away from losing both the original and the backup. Point this at a network
drive or external disk (`python -m app.backup D:\\CableLIMS-Backups`) for a
backup that actually survives this machine dying.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.db import DB_PATH

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTIFICATES_DIR = os.path.join(BACKEND_DIR, "certificates")
UPLOADS_DIR = os.path.join(BACKEND_DIR, "uploads")
DEFAULT_BACKUP_ROOT = os.path.join(BACKEND_DIR, "backups")

# Kept simple deliberately: N most-recent backups, not the reviewer's
# suggested "30 dailies + 12 monthlies" grandfather-father-son scheme --
# that's calendar-aware retention logic with its own edge cases, for a
# single-lab appliance whose actual backup cadence (how often the operator
# actually runs this, or how the scheduled task is configured) isn't fixed
# by this script at all. A flat count is easy to reason about and covers
# the actual need: don't grow the backups folder forever.
# H14: sourced from Settings (env-overridable). Re-exported under its old
# name since this module's own callers/tests import it directly.
DEFAULT_KEEP = settings.backup_default_keep


def backup_database(dest_path: str) -> None:
    """Online, WAL-safe copy -- safe to run while the server is live."""
    source = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()


def verify_backup(path: str) -> bool:
    """Opens the backup and runs PRAGMA integrity_check -- a backup nobody
    has ever confirmed is readable is not a backup, it's a hope. Returns
    False (never raises) for anything that isn't a readable, structurally
    sound SQLite database -- including a file that isn't a SQLite database
    at all, which sqlite3 itself reports as a DatabaseError rather than a
    normal integrity_check failure."""
    try:
        conn = sqlite3.connect(path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def prune_old_backups(backup_root: str, keep: int = DEFAULT_KEEP) -> list:
    if not os.path.isdir(backup_root):
        return []
    entries = sorted(
        (e for e in os.listdir(backup_root) if os.path.isdir(os.path.join(backup_root, e)) and e.startswith("cablelims_")),
        reverse=True,
    )
    removed = []
    for stale in entries[keep:]:
        path = os.path.join(backup_root, stale)
        shutil.rmtree(path, ignore_errors=True)
        removed.append(stale)
    return removed


def run_backup(destination_root: Optional[str] = None, keep: int = DEFAULT_KEEP) -> str:
    destination_root = destination_root or DEFAULT_BACKUP_ROOT
    os.makedirs(destination_root, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(destination_root, f"cablelims_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)

    print(f"Backing up database ({DB_PATH}) ...")
    db_backup_path = os.path.join(backup_dir, "cablelims.db")
    backup_database(db_backup_path)

    print("Verifying backup integrity ...")
    if not verify_backup(db_backup_path):
        raise RuntimeError(
            f"Backup verification FAILED for {db_backup_path} -- this backup is not trustworthy. "
            "The source database was not modified; investigate before relying on this backup."
        )
    print("  OK -- PRAGMA integrity_check passed.")

    if os.path.isdir(CERTIFICATES_DIR):
        print(f"Copying certificates ({CERTIFICATES_DIR}) ...")
        shutil.copytree(CERTIFICATES_DIR, os.path.join(backup_dir, "certificates"), dirs_exist_ok=True)
    if os.path.isdir(UPLOADS_DIR):
        print(f"Copying uploads ({UPLOADS_DIR}) ...")
        shutil.copytree(UPLOADS_DIR, os.path.join(backup_dir, "uploads"), dirs_exist_ok=True)

    removed = prune_old_backups(destination_root, keep=keep)
    if removed:
        print(f"Pruned {len(removed)} backup(s) older than the {keep} most recent: {', '.join(removed)}")

    print(f"\nBackup complete: {backup_dir}")
    return backup_dir


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        run_backup(dest)
    except Exception as e:
        print(f"\nBACKUP FAILED: {e}")
        sys.exit(1)
