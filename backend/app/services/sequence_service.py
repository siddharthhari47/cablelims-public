"""
Transactional allocation of human-readable sequence numbers (sample IDs,
certificate numbers), replacing the previous `COUNT(matching rows) + 1`
pattern used at both call sites. That pattern had two failure modes: a race
under concurrent requests (two callers read the same count before either
commits -> both construct the same number -> the second commit raises an
unhandled IntegrityError), and going backwards the moment any row was ever
deleted (nothing in this app deletes rows today, but direct sqlite3 access
-- which DEPLOYMENT.md's own troubleshooting section assumes an operator
might use -- does).

Correctness here relies on SQLite's single-writer model: this function's
first statement (the `INSERT ... ON CONFLICT DO NOTHING`, or the UPDATE on
an existing row) acquires the database's write lock, which is held until
the CALLER commits. As long as the caller allocates the number and persists
the row that uses it (Sample, Certificate) within the same session/
transaction -- never committing in between -- no other request can observe
or allocate the same number in the meantime.
"""
from typing import Callable, Optional

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.models import Sequence, uid


def next_sequence_value(db: Session, kind: str, year: int, bootstrap_fn: Optional[Callable[[], int]] = None) -> int:
    """Returns the next integer in the (kind, year) sequence and advances it.

    `bootstrap_fn`, if given, is called ONLY the first time this (kind, year)
    pair is ever allocated from, to seed the starting value -- e.g. from a
    COUNT(*) of already-existing rows, so a database that already has
    SMP-2026-0001..0042 from the old counting scheme continues at 0043
    instead of restarting at 0001 and colliding. Every call after the first
    for a given (kind, year) is a cheap indexed read + increment; the
    (possibly expensive) bootstrap query never runs again once the row
    exists.

    The increment itself is a single atomic `UPDATE ... SET next_value =
    next_value + 1 RETURNING next_value` -- deliberately NOT "read
    next_value into Python, add 1, write it back", which is a classic
    read-modify-write race regardless of SQLite serializing writers: two
    transactions can each read the same pre-increment value before either
    writes, and the second write silently clobbers the first's result with
    the same final number. Doing the arithmetic in the SQL expression means
    the database evaluates it against whatever is actually current at the
    moment it acquires the write lock, not a value cached in Python
    beforehand.
    """
    seq = db.query(Sequence).filter(Sequence.kind == kind, Sequence.year == year).first()
    if seq is None:
        start = bootstrap_fn() if bootstrap_fn else 1
        stmt = sqlite_insert(Sequence).values(
            id=uid(), kind=kind, year=year, next_value=start,
        ).on_conflict_do_nothing(index_elements=["kind", "year"])
        db.execute(stmt)
        db.flush()

    result = db.execute(
        update(Sequence)
        .where(Sequence.kind == kind, Sequence.year == year)
        .values(next_value=Sequence.next_value + 1)
        .returning(Sequence.next_value)
    )
    new_value = result.scalar_one()
    db.flush()
    return new_value - 1  # the number to hand out is the pre-increment value
