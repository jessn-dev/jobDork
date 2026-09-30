"""
jobdork.db.migrations
=====================
Schema versioning for the SQLite database.

`CREATE TABLE IF NOT EXISTS` gets a database created, and then quietly stops
being enough. It cannot add a column, rename one, backfill a value or change
an index — and because it fails silently rather than loudly, a database created
by an older version keeps opening cleanly and then behaves wrongly when
something reads a column that was never added.

So every schema change from here is a numbered step. The version lives in
`meta.schema_version`, each step runs once, in order, inside a transaction, and
a database at the current version does nothing at all.

Rules for adding one:

  **Append, never edit.** A step that has run somewhere cannot be changed;
  editing it means two databases claiming the same version with different
  shapes. Add a new step instead.

  **Forwards only.** There is no down-migration. This is one person's job
  search on one machine, the database is regenerable by re-scanning, and a
  down-migration that has never been run is a down-migration that does not
  work.

  **Additive where possible.** SQLite can add a column but not drop one before
  3.35, and a step that rebuilds a table to remove a column risks the data.
  Leaving an unused column costs nothing.

A database newer than the code is refused rather than opened, because the
alternative is the code writing rows the newer schema does not expect.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

log = logging.getLogger("jobdork.db.migrations")

# The version a fresh database is created at, and the version this code
# understands. Bumped by adding a step below.
SCHEMA_VERSION = 8


class MigrationError(Exception):
    """The database cannot be brought to the version this code expects."""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str,
                spec: str) -> None:
    """Add a column unless it is already there.

    Idempotent on purpose: a database that has been through the pre-migration
    world may already carry a column that a later step adds, and a step that
    cannot survive that is a step that cannot be shipped.
    """
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
        log.info("added %s.%s", table, column)


# ── the steps ─────────────────────────────────────────────────────────────────


# Every column the current `roles` table is expected to carry, with the type
# to add it as. `CREATE TABLE IF NOT EXISTS` builds this shape for a NEW
# database and does nothing at all for an existing one, so a database created
# before a column was introduced keeps opening cleanly and then fails on the
# first write that mentions it. Reconciling closes that gap for good.
EXPECTED_ROLE_COLUMNS: dict[str, str] = {
    "origin": "TEXT NOT NULL DEFAULT 'scan'",
    "city": "TEXT",
    "state": "TEXT",
    "country": "TEXT",
    "lat": "REAL",
    "lon": "REAL",
    "distance_mi": "REAL",
    "work_mode": "TEXT",
    "salary_min": "REAL",
    "salary_max": "REAL",
    "salary_currency": "TEXT",
    "salary_period": "TEXT",
    "salary_stated": "INTEGER NOT NULL DEFAULT 0",
    "posted_at": "TEXT",
    "enriched_at": "TEXT",
    "score": "REAL",
    "flags": "TEXT",
    "reasons": "TEXT",
}


def _v1_to_v2(conn: sqlite3.Connection) -> None:
    """Reconcile the roles table, and index what is now queried.

    Adds any expected column the database is missing — including `origin`,
    which distinguishes a role from a scan from one added by hand with
    `jobdork add`, and `enriched_at`, which lets `enrich` skip roles it has
    already tried rather than re-fetching them every run.
    """
    for column, spec in EXPECTED_ROLE_COLUMNS.items():
        _add_column(conn, "roles", column, spec)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_roles_platform ON roles(platform)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind)")


def _v2_to_v3(conn: sqlite3.Connection) -> None:
    """Store the resume-fit part of the score on its own.

    A score of 100 said nothing about whether the 100 came from the advert
    matching your resume or from the title, distance and salary. NULL until
    the role is next screened, which is what `rescreen` is for.
    """
    _add_column(conn, "roles", "fit", "REAL")


def _v3_to_v4(conn: sqlite3.Connection) -> None:
    """Store how each score was reached, so the dashboard can say why.

    JSON, one entry per rule with its points and a sentence. NULL until the
    role is next screened.
    """
    _add_column(conn, "roles", "score_parts", "TEXT")


def _v4_to_v5(conn: sqlite3.Connection) -> None:
    """A model's verdict on each role, and whether its posting is still up.

    Neither is written by a scan's upsert, so a rescan keeps them.
    """
    for column, spec in (("llm_score", "REAL"), ("llm_judgement", "TEXT"),
                         ("listing_state", "TEXT"), ("listing_note", "TEXT"),
                         ("listing_checked_at", "TEXT")):
        _add_column(conn, "roles", column, spec)


def _v5_to_v6(conn: sqlite3.Connection) -> None:
    """Give every copy of a job the same status, now that decisions are grouped.

    Before grouping, a status lived on whichever copy was shown, so copies of
    one job disagree. Per group the latest real decision wins, for every
    copy, and its note fills notes that are empty.

    One kind of status is not a decision: `closed` set by the listing check
    (its note starts "check:") on a copy whose job is still up elsewhere. A
    job is closed only when every copy is, so those are undone — the group
    takes its other copies' status instead, or `new`.
    """
    from . import grouping

    rows = conn.execute(
        # Safe: key_sql() is a fixed SQL fragment.
        f"SELECT r.uid, {grouping.key_sql('r')} AS gkey, r.listing_state, "  # nosec B608
        "COALESCE(s.status, 'new') AS status, COALESCE(s.note, '') AS note, "
        "COALESCE(s.updated_at, '') AS updated_at "
        "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid").fetchall()
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row[1], []).append(row)

    for members in groups.values():
        if len(members) < 2:
            continue
        every_copy_closed = all(m[2] == "closed" for m in members)
        decisions = [
            m for m in members if m[3] != "new"
            and not (m[3] == "closed" and m[4].startswith("check:")
                     and not every_copy_closed)
        ]
        chosen = max(decisions, key=lambda m: m[5]) if decisions else None
        status = chosen[3] if chosen else "new"
        note = chosen[4] if chosen else ""
        for m in members:
            keep_note = m[4] if m[4] and not (
                m[4].startswith("check:") and status != "closed") else note
            conn.execute(
                "INSERT INTO role_state(uid, status, note, updated_at) "
                "VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')) ON CONFLICT(uid) DO UPDATE SET "
                "status = excluded.status, note = excluded.note",
                (m[0], status, keep_note))



def _v6_to_v7(conn: sqlite3.Connection) -> None:
    """Spell it "resume", without the accents, in what jobdork wrote itself.

    The score's part name ("résumé fit") is a key the page looks up, so rows
    scored before the change would lose their fit tip. Run names, run logs
    and the text of AI outputs are changed too, so the dashboard does not
    mix both spellings. Adverts and your notes are not: those are someone
    else's words. `score_parts` is JSON written with ASCII escapes, so there
    the accent is the six characters \\u00e9.
    """
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    plain = [("activity", "job"), ("activity", "last_line"), ("activity", "summary"),
             ("activity_events", "text"), ("ai_outputs", "text")]
    for table, column in plain:
        if table in tables and column in _columns(conn, table):
            conn.execute(
                # Safe: table and column come from the hard-coded list above.
                f"UPDATE {table} SET {column} = REPLACE(REPLACE({column}, "  # nosec B608
                f"'résumé', 'resume'), 'Résumé', 'Resume') "
                f"WHERE {column} LIKE '%sum%'")
    if "roles" in tables and "score_parts" in _columns(conn, "roles"):
        conn.execute(
            "UPDATE roles SET score_parts = REPLACE(REPLACE(score_parts, "
            "'r\\u00e9sum\\u00e9', 'resume'), 'R\\u00e9sum\\u00e9', 'Resume') "
            "WHERE score_parts LIKE '%sum%'")


def _v7_to_v8(conn: sqlite3.Connection) -> None:
    """Projects described STAR-style on the Resume page, for tailored resumes."""
    # execute, not executescript: that commits, and a step is one transaction.
    conn.execute('''CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    tools       TEXT NOT NULL DEFAULT '',
    link        TEXT NOT NULL DEFAULT '',
    situation   TEXT NOT NULL DEFAULT '',
    task        TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL DEFAULT '',
    result      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)''')


# Numbered, ordered, append-only. The key is the version a step produces.
STEPS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _v1_to_v2,
    3: _v2_to_v3,
    4: _v3_to_v4,
    5: _v4_to_v5,
    6: _v5_to_v6,
    7: _v6_to_v7,
    8: _v7_to_v8,
}


# ── running them ──────────────────────────────────────────────────────────────


def current_version(conn: sqlite3.Connection) -> int:
    """The version recorded in the database, or 1 for a pre-versioning one."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        return 0                              # no meta table: a fresh database
    if not row:
        return 1
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 1


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Bring the database up to SCHEMA_VERSION. Returns the steps applied."""
    version = current_version(conn)

    if version > SCHEMA_VERSION:
        raise MigrationError(
            f"the database is at schema version {version} and this jobdork "
            f"understands {SCHEMA_VERSION}. It was written by a newer version; "
            "upgrade jobdork rather than letting an older one write to it."
        )

    applied: list[int] = []
    for target in sorted(STEPS):
        if target <= version:
            continue
        step = STEPS[target]
        log.info("migrating schema %d -> %d", version, target)
        try:
            # One transaction per step: a step that fails leaves the database
            # at the version before it, not half way through it.
            with conn:
                step(conn)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(target),))
        except sqlite3.Error as exc:
            raise MigrationError(
                f"schema migration to version {target} failed and was rolled "
                f"back; the database is still at {version}: {exc}") from exc
        applied.append(target)
        version = target

    return applied
