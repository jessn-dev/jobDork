"""
jobdork.migrations
==================
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

log = logging.getLogger("jobdork.migrations")

# The version a fresh database is created at, and the version this code
# understands. Bumped by adding a step below.
SCHEMA_VERSION = 2


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


# Numbered, ordered, append-only. The key is the version a step produces.
STEPS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _v1_to_v2,
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
