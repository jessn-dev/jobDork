"""
jobdork.db.store
================
The SQLite database every other module reads and writes.

A scanner that forgets shows you the same job every week. This is the part
that remembers: what was seen, when it was first seen, and what you decided
about it.

Two tables that could have been one, deliberately are not:

  role_state  where a role sits in your pipeline
  artifacts   documents produced for it

Keeping them apart is what makes "which roles have a CV but no application"
a query rather than a combinatorial explosion of status values.

The database is the single source of truth. The CLI and the dashboard both
read it, so the two cannot disagree.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config import SETTLED_STATUSES, STATUSES
from . import grouping
from .migrations import SCHEMA_VERSION, migrate

# Tracking parameters that change per click and would otherwise mint a new
# uid for a posting already stored.
#
# `gh_jid` is deliberately NOT here. Greenhouse's `absolute_url` is often the
# employer's own careers page with the job id in the query string —
# `https://stripe.com/jobs/search?gh_jid=7532733` — so stripping it collapses
# every job on that board to one uid and the scanner stores one role per
# employer. A parameter that identifies the posting is not tracking.
_JUNK_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "source", "referrer", "lever-source",
    "gclid", "fbclid", "src", "trk", "trackingid",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    uid              TEXT PRIMARY KEY,
    platform         TEXT NOT NULL,
    origin           TEXT NOT NULL DEFAULT 'scan',
    company          TEXT,
    title            TEXT,
    url              TEXT,
    location_raw     TEXT,
    city             TEXT,
    state            TEXT,
    country          TEXT,
    lat              REAL,
    lon              REAL,
    distance_mi      REAL,
    work_mode        TEXT,
    salary_min       REAL,
    salary_max       REAL,
    salary_currency  TEXT,
    salary_period    TEXT,
    salary_stated    INTEGER NOT NULL DEFAULT 0,
    description      TEXT,
    posted_at        TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    score            REAL,
    fit              REAL,
    score_parts      TEXT,
    llm_score        REAL,
    llm_judgement    TEXT,
    listing_state    TEXT,
    listing_note     TEXT,
    listing_checked_at TEXT,
    flags            TEXT,
    reasons          TEXT
);

CREATE TABLE IF NOT EXISTS role_state (
    uid         TEXT PRIMARY KEY REFERENCES roles(uid) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'new',
    note        TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL REFERENCES roles(uid) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    path        TEXT,
    rating      REAL,
    gates_json  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    counts_json  TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- What running and recent jobs did, from any process (telemetry.py).
-- New tables need no migration step: this script runs on every open.
CREATE TABLE IF NOT EXISTS activity (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job           TEXT NOT NULL,
    origin        TEXT NOT NULL,
    pid           INTEGER,
    started_at    TEXT NOT NULL,
    heartbeat_at  TEXT NOT NULL,
    finished_at   TEXT,
    state         TEXT NOT NULL DEFAULT 'running',
    done          INTEGER NOT NULL DEFAULT 0,
    total         INTEGER,
    counters      TEXT,
    hosts         TEXT,
    ai            TEXT,
    last_line     TEXT,
    summary       TEXT
);

CREATE TABLE IF NOT EXISTS activity_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id  INTEGER NOT NULL,
    at           TEXT NOT NULL,
    level        TEXT,
    text         TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_activity ON activity_events(activity_id);

-- Job posts you deleted. A scan skips these, or a deleted post still listed
-- by its source would come straight back as new.
CREATE TABLE IF NOT EXISTS deleted (
    uid         TEXT PRIMARY KEY,
    deleted_at  TEXT NOT NULL,
    reason      TEXT
);

-- One row per piece of text a model wrote: a verdict, a page read, a cover
-- letter, a resume review, a draft. What the hallucination score, its
-- coverage and the feedback trend are counted from (guard.py).
-- `checked` is 0 when the guard could not run; `feedback` is 1, -1 or NULL.
CREATE TABLE IF NOT EXISTS ai_outputs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    uid          TEXT,
    model        TEXT,
    created_at   TEXT NOT NULL,
    activity_id  INTEGER,
    text         TEXT,
    guard_json   TEXT,
    claims       INTEGER NOT NULL DEFAULT 0,
    unsupported  INTEGER NOT NULL DEFAULT 0,
    checked      INTEGER NOT NULL DEFAULT 0,
    feedback     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ai_outputs_created ON ai_outputs(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_outputs_uid     ON ai_outputs(uid);

-- One row per model call inside a recorded job, for latency percentiles.
-- Written by telemetry.py; no prompt or answer text.
CREATE TABLE IF NOT EXISTS llm_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT NOT NULL,
    activity_id  INTEGER,
    model        TEXT,
    purpose      TEXT,
    seconds      REAL NOT NULL,
    ok           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_at ON llm_calls(at);

-- Projects you describe yourself, STAR-style, on the Resume page. Source
-- material for a tailored resume beside the resume file: the writer may use
-- them, and the checks accept what they say (ai/writer.py).
CREATE TABLE IF NOT EXISTS projects (
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
);

CREATE INDEX IF NOT EXISTS idx_roles_first_seen ON roles(first_seen);
CREATE INDEX IF NOT EXISTS idx_roles_company    ON roles(company);
CREATE INDEX IF NOT EXISTS idx_roles_url        ON roles(url);
CREATE INDEX IF NOT EXISTS idx_state_status     ON role_state(status);
CREATE INDEX IF NOT EXISTS idx_artifacts_uid    ON artifacts(uid);
"""


# ── Role ───────────────────────────────────────────────────────────────────────


@dataclass
class Role:
    """One posting, normalised. Adapters return these; nothing else."""

    platform: str
    company: str = ""
    title: str = ""
    url: str = ""
    location_raw: str = ""
    description: str = ""
    posted_at: str = ""
    origin: str = "scan"

    # Filled in by geo.py
    city: str = ""
    state: str = ""
    country: str = ""
    lat: float | None = None
    lon: float | None = None
    distance_mi: float | None = None

    # Filled in by screen.py
    work_mode: str = ""            # remote | hybrid | office | "" when unstated
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""        # year | month | day | hour
    salary_stated: bool = False
    score: float | None = None
    # The resume-fit part of `score`, 0-25. None when there was no resume or
    # no advert to compare it with, which is not the same as a fit of 0.
    fit: float | None = None
    # How `score` was reached: [{part, points, max, why, ...}], one per rule.
    score_parts: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return make_uid(self.platform, self.url)


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same posting keeps the same uid.

    Without this a role arriving from a Google click and the same role arriving
    from a scan are two rows, and the scanner forgets it already showed you one.
    """
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    query = [
        (k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _JUNK_PARAMS
    ]
    return urllib.parse.urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/") or "/",
        urllib.parse.urlencode(query),
        "",                                  # fragments never identify a posting
    ))


def make_uid(platform: str, url: str) -> str:
    """Stable id for a posting. Short enough to type on the command line."""
    basis = f"{platform.lower()}|{canonical_url(url)}"
    # An id, not a security measure: collisions are merely unlikely, not guarded.
    return hashlib.sha1(basis.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── Store ──────────────────────────────────────────────────────────────────────


class Store:
    """Thin wrapper over sqlite3. Open it with a `with` block."""

    def __init__(self, path: str | Path = "data/jobdork.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        try:
            self._open()
        except BaseException:
            # A refused database (newer than this code, a failed migration)
            # must not leave its connection open: it leaked, and on Windows
            # would keep the file locked.
            self.conn.close()
            raise

    def _open(self) -> None:
        # WAL: a reader (the dashboard, a run's telemetry) never blocks this
        # connection's commit, and a commit never blocks a reader. Kept in the
        # file once set; -wal and -shm files appear beside it.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        # A fresh database is created at the current version; an existing one
        # is stepped up to it. `CREATE TABLE IF NOT EXISTS` above builds the
        # shape a NEW database starts with and can do nothing for an old one,
        # which is what migrations are for.
        fresh = self._is_fresh()
        self._set_meta_default(
            "schema_version", str(SCHEMA_VERSION if fresh else 1))
        self.conn.commit()
        self.applied_migrations = migrate(self.conn)

    def _is_fresh(self) -> bool:
        """True when nothing has been stored yet, so no migration is owed."""
        if self.conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'").fetchone():
            return False
        return self.conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    # ── meta ───────────────────────────────────────────────────────────────────

    def _set_meta_default(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ── roles ──────────────────────────────────────────────────────────────────

    def upsert(self, role: Role, seen: bool = True) -> bool:
        """Store a role. Returns True if this is the first time it was seen.

        An existing row keeps its `first_seen`: that is the date the tool
        learned about the job, and a later scan does not make it newer.

        `seen` is False when the role is only being re-scored or re-read —
        rescreen, enrich, a pasted advert. `last_seen` means "a source listed
        it", and the listing check reads it that way: bumping it on every
        rescreen made month-old Adzuna ads look listed today.
        """
        uid = role.uid
        now = _now()
        existing = self.conn.execute(
            "SELECT first_seen FROM roles WHERE uid = ?", (uid,)
        ).fetchone()
        first_seen = existing["first_seen"] if existing else now
        is_new = existing is None

        self.conn.execute(
            """
            INSERT INTO roles (
                uid, platform, origin, company, title, url, location_raw,
                city, state, country, lat, lon, distance_mi, work_mode,
                salary_min, salary_max, salary_currency, salary_period,
                salary_stated, description, posted_at, first_seen, last_seen,
                score, fit, score_parts, flags, reasons
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(uid) DO UPDATE SET
                company         = excluded.company,
                title           = excluded.title,
                location_raw    = excluded.location_raw,
                city            = excluded.city,
                state           = excluded.state,
                country         = excluded.country,
                lat             = excluded.lat,
                lon             = excluded.lon,
                distance_mi     = excluded.distance_mi,
                work_mode       = excluded.work_mode,
                salary_min      = excluded.salary_min,
                salary_max      = excluded.salary_max,
                salary_currency = excluded.salary_currency,
                salary_period   = excluded.salary_period,
                salary_stated   = excluded.salary_stated,
                -- A later fetch that could not read the advert must not blank
                -- one an earlier fetch managed to read.
                description     = COALESCE(NULLIF(excluded.description, ''), roles.description),
                posted_at       = COALESCE(NULLIF(excluded.posted_at, ''), roles.posted_at),
                last_seen       = CASE WHEN ? THEN excluded.last_seen
                                       ELSE roles.last_seen END,
                score           = excluded.score,
                fit             = excluded.fit,
                score_parts     = excluded.score_parts,
                flags           = excluded.flags,
                reasons         = excluded.reasons
            """,
            (
                uid, role.platform, role.origin, role.company, role.title,
                canonical_url(role.url), role.location_raw, role.city, role.state,
                role.country, role.lat, role.lon, role.distance_mi, role.work_mode,
                role.salary_min, role.salary_max, role.salary_currency,
                role.salary_period, int(role.salary_stated), role.description,
                role.posted_at, first_seen, now, role.score, role.fit,
                json.dumps(role.score_parts) if role.score_parts else None,
                json.dumps(role.flags), json.dumps(role.reasons),
                int(seen),
            ),
        )
        if is_new:
            self.conn.execute(
                "INSERT INTO role_state(uid, status, updated_at) VALUES(?, 'new', ?) "
                "ON CONFLICT(uid) DO NOTHING",
                (uid, now),
            )
        return is_new

    def first_seen(self, uid: str) -> str:
        """When a stored post was first seen, or "" for one never stored."""
        row = self.conn.execute(
            "SELECT first_seen FROM roles WHERE uid = ?", (uid,)).fetchone()
        return (row["first_seen"] or "") if row else ""

    def stored_description(self, uid: str) -> str:
        row = self.conn.execute(
            "SELECT description FROM roles WHERE uid = ?", (uid,)).fetchone()
        return (row["description"] or "") if row else ""

    def upsert_many(self, roles: Iterable[Role]) -> tuple[int, int]:
        """Returns (stored, newly_seen)."""
        stored = new = 0
        for role in roles:
            if self.upsert(role):
                new += 1
            stored += 1
        self.conn.commit()
        return stored, new

    def get(self, uid: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT r.*, s.status, s.note, s.updated_at "
            "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid "
            "WHERE r.uid = ?",
            (uid,),
        ).fetchone()

    def resolve(self, ref: str) -> list[sqlite3.Row]:
        """Find roles by uid, posting URL, or company name.

        A name that matches more than one role returns all of them so the
        caller can stop and ask. Recording a status against the wrong role is
        worse than not recording it.
        """
        ref = (ref or "").strip()
        if not ref:
            return []

        row = self.get(ref)
        if row:
            return [row]

        if "://" in ref:
            rows = self.conn.execute(
                "SELECT r.*, s.status, s.note, s.updated_at "
                "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid "
                "WHERE r.url = ?",
                (canonical_url(ref),),
            ).fetchall()
            if rows:
                return rows

        return self.conn.execute(
            "SELECT r.*, s.status, s.note, s.updated_at "
            "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid "
            "WHERE r.company LIKE ? OR r.title LIKE ? "
            "ORDER BY r.first_seen DESC",
            (f"%{ref}%", f"%{ref}%"),
        ).fetchall()

    def list_roles(
        self,
        status: str = "",
        new_only: bool = False,
        include_settled: bool = False,
        limit: int = 0,
        collapse_duplicates: bool = True,
    ) -> list[sqlite3.Row]:
        """Roles worth looking at, best score first.

        The four settled statuses are hidden unless asked for: a role you have
        already turned down should not come back every week.

        `collapse_duplicates` hides repeats of the same job. Aggregators
        republish one vacancy under several URLs — one Chicago run had the
        same Resource Innovations posting seven times — and each URL is a
        genuinely different uid, so this cannot be fixed at store time without
        throwing away a posting that might be the only copy. It is collapsed
        on the way out instead: same employer, same title, best score wins.
        """
        group_key = grouping.key_sql()
        sql = [
            "SELECT r.*, COALESCE(s.status, 'new') AS status, s.note, s.updated_at,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'cv') AS has_cv,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'cover_letter') AS has_letter,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'screen') AS has_screen,",
            "  g.copies",
            "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid",
            # Every copy's place in its group: how many copies, and which one
            # is shown. See grouping.py.
            f"JOIN (SELECT uid, COUNT(*) OVER (PARTITION BY {group_key}) AS copies,",
            f"        ROW_NUMBER() OVER (PARTITION BY {group_key}",
            f"                           ORDER BY {grouping.representative_order()}) AS rn",
            "      FROM roles) g ON g.uid = r.uid",
        ]
        where: list[str] = []
        params: list[Any] = []

        if status:
            where.append("COALESCE(s.status, 'new') = ?")
            params.append(status)
        elif not include_settled:
            placeholders = ",".join("?" for _ in SETTLED_STATUSES)
            where.append(f"COALESCE(s.status, 'new') NOT IN ({placeholders})")
            params.extend(SETTLED_STATUSES)

        if new_only:
            # "New" means first seen during the most recent completed scan,
            # not first seen on the most recent calendar date. The date rule
            # looks equivalent and is not: scan twice in one day and the
            # second digest resends everything the first one already sent,
            # and a day with no scan at all reports yesterday's roles as new.
            #
            # Falls back to the date rule when no run has been recorded, so a
            # database imported or built by hand still answers sensibly.
            where.append("""
                r.first_seen >= COALESCE(
                    (SELECT started_at FROM runs
                     WHERE finished_at IS NOT NULL
                     ORDER BY id DESC LIMIT 1),
                    (SELECT MAX(date(first_seen)) FROM roles)
                )""")

        if collapse_duplicates:
            # One copy per group. Ranking by score alone once kept the WORSE
            # copy — a 500-character teaser out-scored the employer's own
            # 4,701-character advert — so the order is in grouping.py.
            where.append("g.rn = 1")

        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY r.score DESC NULLS LAST, r.first_seen DESC")
        if limit:
            sql.append("LIMIT ?")
            params.append(limit)

        return self.conn.execute("\n".join(sql), params).fetchall()

    def copies(self, uid: str) -> list[sqlite3.Row]:
        """The other copies of this job, for "also posted at"."""
        others = [u for u in grouping.uids(self.conn, uid) if u != uid]
        if not others:
            return []
        marks = ",".join("?" for _ in others)
        return self.conn.execute(
            # Safe: only ? placeholders are interpolated.
            "SELECT uid, platform, url, listing_state, listing_note, last_seen, "  # nosec B608
            f"LENGTH(COALESCE(description, '')) AS advert_chars FROM roles "
            f"WHERE uid IN ({marks}) ORDER BY platform", others).fetchall()

    def delete(self, uid: str) -> None:
        self.conn.execute("DELETE FROM roles WHERE uid = ?", (uid,))
        self.conn.commit()

    # ── cleanup ────────────────────────────────────────────────────────────────

    def cleanup_candidates(self, older_than_days: int = 0,
                           statuses: Iterable[str] = ()) -> list[sqlite3.Row]:
        """Job posts a cleanup would delete, newest first.

        By age: first seen more than N days ago and not being pursued
        (PURSUING_STATUSES), whatever else their status. By status: every
        post whose status is one of `statuses`. Exactly one of the two.
        """
        from ..core.config import PURSUING_STATUSES

        base = ("SELECT r.uid, r.title, r.company, r.first_seen, "
                "COALESCE(s.status, 'new') AS status FROM roles r "
                "LEFT JOIN role_state s ON s.uid = r.uid WHERE ")
        if older_than_days:
            cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(
                time.time() - older_than_days * 86400))
            marks = ",".join("?" for _ in PURSUING_STATUSES)
            return self.conn.execute(
                base + f"r.first_seen < ? AND COALESCE(s.status, 'new') "
                f"NOT IN ({marks}) ORDER BY r.first_seen DESC",
                (cutoff, *PURSUING_STATUSES)).fetchall()
        wanted = [s for s in statuses if s in SETTLED_STATUSES]
        if not wanted:
            return []
        marks = ",".join("?" for _ in wanted)
        return self.conn.execute(
            base + f"COALESCE(s.status, 'new') IN ({marks}) "
            "ORDER BY r.first_seen DESC", wanted).fetchall()

    def delete_many(self, uids: Iterable[str], reason: str) -> int:
        """Delete job posts and remember them, so a scan does not re-add them.

        Their status, notes, AI verdicts and document records go with them
        (foreign keys cascade). Draft files on disk are not touched.
        """
        uids = list(uids)
        now = _now()
        with self.conn:
            self.conn.executemany(
                "INSERT INTO deleted(uid, deleted_at, reason) VALUES(?,?,?) "
                "ON CONFLICT(uid) DO UPDATE SET deleted_at = excluded.deleted_at, "
                "reason = excluded.reason", [(u, now, reason) for u in uids])
            self.conn.executemany("DELETE FROM roles WHERE uid = ?",
                                  [(u,) for u in uids])
        return len(uids)

    def scanned_count(self) -> int:
        """Job posts a fresh scan would delete: every one a scan found."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM roles WHERE origin = 'scan'").fetchone()[0]

    def clear_scanned(self) -> int:
        """Delete every job post a scan found, for a scan from scratch.

        Their statuses, notes, AI verdicts and document records go with them
        (foreign keys cascade). Unlike `delete_many`, nothing is remembered:
        the next scan is meant to find them again. Posts you deleted before
        stay deleted, and posts added by hand (`jobdork add`) are kept.
        """
        with self.conn:
            cur = self.conn.execute("DELETE FROM roles WHERE origin = 'scan'")
        return cur.rowcount

    def deleted_uids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT uid FROM deleted")}

    # ── state ──────────────────────────────────────────────────────────────────

    def set_status(self, uid: str, status: str, note: str = "") -> None:
        """Record a decision — for every copy of the job, not just this one.

        A decision about a job is about the job. Set on one copy only, it was
        lost the moment another copy became the one shown (see grouping.py).
        """
        if status not in STATUSES:
            raise ValueError(
                f"{status!r} is not a status. Accepted: {', '.join(STATUSES)}"
            )
        now = _now()
        self.conn.executemany(
            "INSERT INTO role_state(uid, status, note, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(uid) DO UPDATE SET "
            "  status = excluded.status, "
            "  note = COALESCE(NULLIF(excluded.note, ''), role_state.note), "
            "  updated_at = excluded.updated_at",
            [(member, status, note, now)
             for member in grouping.uids(self.conn, uid)],
        )
        self.conn.commit()

    def set_judgement(self, uid: str, judgement: dict) -> None:
        """A model's verdict on a role. Kept apart from the rule score."""
        self.conn.execute(
            "UPDATE roles SET llm_score = ?, llm_judgement = ? WHERE uid = ?",
            (judgement["score"], json.dumps(judgement), uid))
        self.conn.commit()

    def set_listing(self, uid: str, state: str, note: str) -> None:
        """Whether the posting is still up: open | closed | unlisted | unknown."""
        self.conn.execute(
            "UPDATE roles SET listing_state = ?, listing_note = ?, "
            "listing_checked_at = ? WHERE uid = ?",
            (state, note, _now(), uid))
        self.conn.commit()

    def has_acted(self, uid: str) -> bool:
        """True once you have made any decision about a role.

        A status is a decision you made, and it outranks a later change to
        your filters: `rescreen --remove` leaves these alone.
        """
        row = self.conn.execute(
            "SELECT status FROM role_state WHERE uid = ?", (uid,)
        ).fetchone()
        return bool(row and row["status"] != "new")

    def status_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT COALESCE(status, 'new') AS status, COUNT(*) AS n "
            "FROM role_state GROUP BY status"
        ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    # ── artifacts ──────────────────────────────────────────────────────────────

    def add_artifact(
        self,
        uid: str,
        kind: str,
        path: str = "",
        rating: float | None = None,
        gates: dict | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO artifacts(uid, kind, path, rating, gates_json, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (uid, kind, path, rating, json.dumps(gates or {}), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def artifacts(self, uid: str, kind: str = "") -> list[sqlite3.Row]:
        if kind:
            return self.conn.execute(
                "SELECT * FROM artifacts WHERE uid = ? AND kind = ? ORDER BY created_at DESC",
                (uid, kind),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM artifacts WHERE uid = ? ORDER BY created_at DESC", (uid,)
        ).fetchall()

    # ── AI outputs ─────────────────────────────────────────────────────────────

    def add_ai_output(self, kind: str, text: str, uid: str = "",
                      model: str = "", guard: dict | None = None,
                      activity_id: int | None = None) -> int:
        """Record text a model wrote, with the guard's report on it.

        `guard` is `GuardReport.to_dict()`; None means no check was tried,
        which counts the same as a failed one: not covered.
        """
        guard = guard or {}
        if activity_id is None:
            from ..core import telemetry
            activity_id = telemetry.current_id()
        cur = self.conn.execute(
            "INSERT INTO ai_outputs(kind, uid, model, created_at, activity_id, "
            "text, guard_json, claims, unsupported, checked) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (kind, uid or None, model, _now(), activity_id, text,
             json.dumps(guard) if guard else None,
             int(guard.get("claims") or 0), int(guard.get("unsupported") or 0),
             1 if guard.get("checked") else 0))
        self.conn.commit()
        return int(cur.lastrowid)

    # ── projects (Resume page, STAR fields) ─────────────────────────────────────

    PROJECT_FIELDS = ("name", "tools", "link", "situation", "task", "action", "result")

    def projects(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC, id DESC").fetchall()

    def save_project(self, fields: dict, project_id: int | None = None) -> int:
        """Add a project, or replace one by id. Returns its id; 0 if no such id."""
        values = [str(fields.get(f) or "").strip() for f in self.PROJECT_FIELDS]
        if not values[0]:
            raise ValueError("a project needs a name")
        now = _now()
        if project_id:
            cur = self.conn.execute(
                "UPDATE projects SET name = ?, tools = ?, link = ?, situation = ?, "
                "task = ?, action = ?, result = ?, updated_at = ? WHERE id = ?",
                (*values, now, int(project_id)))
            self.conn.commit()
            return int(project_id) if cur.rowcount else 0
        cur = self.conn.execute(
            "INSERT INTO projects(name, tools, link, situation, task, action, result, "
            "created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", (*values, now, now))
        self.conn.commit()
        return int(cur.lastrowid)

    def delete_project(self, project_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM projects WHERE id = ?", (int(project_id),))
        self.conn.commit()
        return cur.rowcount > 0

    def ai_output(self, output_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM ai_outputs WHERE id = ?", (output_id,)).fetchone()

    def set_feedback(self, output_id: int, value: int | None) -> bool:
        """Thumbs up (1), down (-1) or cleared (None). False if no such output."""
        if value not in (1, -1, None):
            raise ValueError(f"feedback is 1, -1 or None, not {value!r}")
        cur = self.conn.execute(
            "UPDATE ai_outputs SET feedback = ? WHERE id = ?", (value, output_id))
        self.conn.commit()
        return cur.rowcount > 0

    # ── runs ───────────────────────────────────────────────────────────────────

    def start_run(self) -> int:
        cur = self.conn.execute("INSERT INTO runs(started_at) VALUES(?)", (_now(),))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, counts: dict) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, counts_json = ? WHERE id = ?",
            (_now(), json.dumps(counts), run_id),
        )
        self.conn.commit()

    def last_run(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM runs WHERE finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
