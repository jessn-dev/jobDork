"""
Tests for schema migrations.

The point of these is the case that cannot be tested by using the tool: a
database created by an OLDER version of the code, opened by a newer one. Every
one of these builds that situation deliberately rather than waiting for it.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.db import migrations
from jobdork.db.store import Role, Store

# The v1 schema, as it shipped, before any migration existed.
V1_SCHEMA = """
CREATE TABLE roles (
    uid TEXT PRIMARY KEY, platform TEXT NOT NULL, company TEXT, title TEXT,
    url TEXT, location_raw TEXT, description TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, score REAL,
    flags TEXT, reasons TEXT, salary_stated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE role_state (
    uid TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'new',
    note TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, kind TEXT NOT NULL,
    path TEXT, rating REAL, gates_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
    finished_at TEXT, counts_json TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


OLD_UID = "a" * 12


def _v1_database(path: Path) -> None:
    """A database as an older jobdork would have left it, with data in it."""
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', '1')")
    # SQLite reads 'a'*12 as arithmetic, not string repetition, so the uid is
    # bound as a parameter rather than written into the SQL.
    conn.execute(
        "INSERT INTO roles(uid, platform, company, title, url, description,"
        " first_seen, last_seen, score, flags, reasons, salary_stated)"
        " VALUES(?, 'workable', 'Acme', 'Engineer', 'https://x.test/1',"
        " 'advert', '2026-01-01T00:00:00', '2026-01-01T00:00:00', 50,"
        " '[]', '[]', 0)", (OLD_UID,))
    conn.execute(
        "INSERT INTO role_state(uid, status, note, updated_at)"
        " VALUES(?, 'applied', 'kept me', '2026-01-01T00:00:00')", (OLD_UID,))
    conn.execute(
        "INSERT INTO artifacts(uid, kind, path, created_at)"
        " VALUES(?, 'cv', '/tmp/CV.md', '2026-01-01T00:00:00')", (OLD_UID,))
    conn.commit()
    conn.close()


def test_an_old_database_is_upgraded_without_losing_anything():
    """The case that only appears after somebody has been using the tool."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.db"
        _v1_database(path)

        with Store(path) as store:
            assert store.applied_migrations == [2, 3, 4, 5, 6], store.applied_migrations
            assert migrations.current_version(store.conn) == 6
            assert {"fit", "score_parts", "llm_score", "listing_state"} \
                <= migrations._columns(store.conn, "roles")

            row = store.get(OLD_UID)
            assert row["company"] == "Acme"
            assert row["status"] == "applied"
            assert row["note"] == "kept me", "a decision you made must survive"
            assert len(store.artifacts(OLD_UID)) == 1


def test_migrating_twice_does_nothing_the_second_time():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.db"
        _v1_database(path)
        with Store(path) as store:
            assert store.applied_migrations == [2, 3, 4, 5, 6]
        with Store(path) as store:
            assert store.applied_migrations == [], "already at the version"


def test_a_fresh_database_starts_current_and_migrates_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        with Store(Path(tmp) / "new.db") as store:
            assert store.applied_migrations == []
            assert migrations.current_version(store.conn) == migrations.SCHEMA_VERSION


def test_a_database_from_the_future_is_refused_not_opened():
    """Opening it would mean writing rows a newer schema does not expect."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "future.db"
        with Store(path):
            pass
        conn = sqlite3.connect(path)
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        try:
            Store(path)
        except migrations.MigrationError as exc:
            assert "999" in str(exc) and "newer" in str(exc)
        else:
            raise AssertionError("a future database must not be opened")


def test_a_failed_step_rolls_back_and_leaves_the_version_alone():
    """Half-applied is the worst outcome; the version must not move."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.db"
        _v1_database(path)
        conn = sqlite3.connect(path)

        def explode(_conn):
            raise sqlite3.OperationalError("simulated failure")

        original = dict(migrations.STEPS)
        migrations.STEPS[2] = explode
        try:
            try:
                migrations.migrate(conn)
            except migrations.MigrationError as exc:
                assert "rolled back" in str(exc)
            else:
                raise AssertionError("a failing step must raise")
            assert migrations.current_version(conn) == 1
        finally:
            migrations.STEPS.clear()
            migrations.STEPS.update(original)
            conn.close()


def test_steps_are_numbered_in_order_with_no_gaps():
    """An out-of-order or missing step would skip a schema change."""
    versions = sorted(migrations.STEPS)
    assert versions == list(range(2, migrations.SCHEMA_VERSION + 1)), versions


def test_adding_a_column_twice_is_harmless():
    """A pre-migration database may already carry a column a step adds."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "db.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE roles (uid TEXT)")
        migrations._add_column(conn, "roles", "origin", "TEXT")
        migrations._add_column(conn, "roles", "origin", "TEXT")
        assert "origin" in migrations._columns(conn, "roles")
        conn.close()


def test_the_store_still_works_after_a_migration():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.db"
        _v1_database(path)
        with Store(path) as store:
            store.upsert(Role(platform="ashby", company="New Co",
                              title="Engineer", url="https://y.test/2",
                              location_raw="Chicago, Illinois"))
            store.conn.commit()
            assert len(store.list_roles(include_settled=True)) == 2


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
