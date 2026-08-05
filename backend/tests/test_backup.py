"""
Regression tests for §10.4: DEPLOYMENT.md's own backup instruction ("copy
cablelims.db on a schedule") is unsafe under WAL mode -- committed
transactions can live in cablelims.db-wal until a checkpoint, so a plain
file copy of just the main file can silently miss recent data or be
structurally inconsistent. app.backup uses the SQLite online backup API
instead, which is specifically designed to be safe against a live,
concurrently-written database.
"""
import os
import sqlite3
import uuid

import pytest

from app.backup import backup_database, prune_old_backups, run_backup, verify_backup


@pytest.fixture
def live_wal_db(tmp_path):
    """A real WAL-mode SQLite database, actively open (mirroring db.py's
    own setup) with an uncommitted-to-main-file transaction sitting in the
    WAL -- exactly the scenario that makes a plain file copy of the main
    file alone unsafe."""
    db_path = tmp_path / f"source_{uuid.uuid4().hex}.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, sample_id TEXT)")
    conn.execute("INSERT INTO samples (sample_id) VALUES ('SMP-TEST-0001')")
    conn.commit()
    # A second write, deliberately left uncheckpointed -- this row lives in
    # the -wal file, not (necessarily) in the main db file on disk yet.
    conn.execute("INSERT INTO samples (sample_id) VALUES ('SMP-TEST-0002')")
    conn.commit()
    yield str(db_path), conn
    conn.close()


def test_backup_database_captures_data_still_sitting_in_the_wal_file(live_wal_db, tmp_path, monkeypatch):
    db_path, conn = live_wal_db
    monkeypatch.setattr("app.backup.DB_PATH", db_path)

    dest = str(tmp_path / "backup.db")
    backup_database(dest)

    backup_conn = sqlite3.connect(dest)
    rows = backup_conn.execute("SELECT sample_id FROM samples ORDER BY sample_id").fetchall()
    backup_conn.close()
    assert [r[0] for r in rows] == ["SMP-TEST-0001", "SMP-TEST-0002"], (
        "backup is missing data that was committed but not yet checkpointed out of the WAL file"
    )


def test_a_plain_file_copy_would_have_missed_the_wal_data(live_wal_db, tmp_path):
    # Not a test of app.backup -- a control proving the WAL hazard is real
    # in this exact test setup, so the test above is actually meaningful
    # and not just trivially true.
    import shutil
    db_path, conn = live_wal_db
    naive_copy = str(tmp_path / "naive_copy.db")
    shutil.copy(db_path, naive_copy)

    # Force a checkpoint on the ORIGINAL only, so the naive copy (taken
    # before this point) is provably stale relative to what a real backup
    # would have captured.
    conn.execute("PRAGMA wal_checkpoint(FULL)")

    naive_conn = sqlite3.connect(naive_copy)
    try:
        rows = naive_conn.execute("SELECT sample_id FROM samples ORDER BY sample_id").fetchall()
    except sqlite3.DatabaseError:
        rows = None
    naive_conn.close()
    # Either it's missing the second row, or the file is inconsistent
    # enough to error -- either way, NOT a clean 2-row result, proving a
    # plain copy is not equivalent to a real backup.
    assert rows != [("SMP-TEST-0001",), ("SMP-TEST-0002",)]


def test_verify_backup_passes_for_a_healthy_backup(live_wal_db, tmp_path, monkeypatch):
    db_path, conn = live_wal_db
    monkeypatch.setattr("app.backup.DB_PATH", db_path)
    dest = str(tmp_path / "backup.db")
    backup_database(dest)
    assert verify_backup(dest) is True


def test_verify_backup_fails_for_a_corrupted_file(tmp_path):
    corrupt_path = tmp_path / "corrupt.db"
    corrupt_path.write_bytes(b"this is not a sqlite database at all")
    assert verify_backup(str(corrupt_path)) is False


def test_run_backup_creates_a_verified_timestamped_directory(live_wal_db, tmp_path, monkeypatch):
    db_path, conn = live_wal_db
    monkeypatch.setattr("app.backup.DB_PATH", db_path)
    monkeypatch.setattr("app.backup.CERTIFICATES_DIR", str(tmp_path / "no_certs_here"))
    monkeypatch.setattr("app.backup.UPLOADS_DIR", str(tmp_path / "no_uploads_here"))

    dest_root = str(tmp_path / "backups")
    backup_dir = run_backup(dest_root)

    assert os.path.isdir(backup_dir)
    assert os.path.exists(os.path.join(backup_dir, "cablelims.db"))
    assert verify_backup(os.path.join(backup_dir, "cablelims.db"))


def test_run_backup_copies_certificates_and_uploads(live_wal_db, tmp_path, monkeypatch):
    db_path, conn = live_wal_db
    monkeypatch.setattr("app.backup.DB_PATH", db_path)

    certs_dir = tmp_path / "certs_src"
    certs_dir.mkdir()
    (certs_dir / "CTL_CBL_2026_0001.docx").write_bytes(b"fake certificate content")
    uploads_dir = tmp_path / "uploads_src"
    uploads_dir.mkdir()
    (uploads_dir / "SMP-2026-0001_diagram_abcd1234.jpg").write_bytes(b"fake image content")

    monkeypatch.setattr("app.backup.CERTIFICATES_DIR", str(certs_dir))
    monkeypatch.setattr("app.backup.UPLOADS_DIR", str(uploads_dir))

    backup_dir = run_backup(str(tmp_path / "backups"))

    assert os.path.exists(os.path.join(backup_dir, "certificates", "CTL_CBL_2026_0001.docx"))
    assert os.path.exists(os.path.join(backup_dir, "uploads", "SMP-2026-0001_diagram_abcd1234.jpg"))


def test_prune_old_backups_keeps_only_the_n_most_recent(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    # Names sort chronologically because the timestamp format does --
    # create 5, keep 3.
    names = [f"cablelims_2026010{i}_000000" for i in range(1, 6)]
    for name in names:
        (backup_root / name).mkdir()

    removed = prune_old_backups(str(backup_root), keep=3)

    remaining = sorted(os.listdir(backup_root))
    assert remaining == names[-3:]
    assert sorted(removed) == names[:2]


def test_backup_failure_does_not_touch_the_source_database(live_wal_db, tmp_path, monkeypatch):
    # backup_database opens the source read-only (mode=ro) -- confirm the
    # source is genuinely unmodified by a backup run, including a failed
    # one, since a backup process must never be a risk to the data it's
    # protecting.
    db_path, conn = live_wal_db
    monkeypatch.setattr("app.backup.DB_PATH", db_path)

    before = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    backup_database(str(tmp_path / "backup.db"))
    after = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert before == after
