"""
jobdork.store
=============
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

from .config import SETTLED_STATUSES, STATUSES
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
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── Store ──────────────────────────────────────────────────────────────────────


class Store:
    """Thin wrapper over sqlite3. Open it with a `with` block."""

    def __init__(self, path: str | Path = "data/jobdork.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
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

    def upsert(self, role: Role) -> bool:
        """Store a role. Returns True if this is the first time it was seen.

        An existing row keeps its `first_seen`: that is the date the tool
        learned about the job, and a later scan does not make it newer.
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
                score, flags, reasons
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                last_seen       = excluded.last_seen,
                score           = excluded.score,
                flags           = excluded.flags,
                reasons         = excluded.reasons
            """,
            (
                uid, role.platform, role.origin, role.company, role.title,
                canonical_url(role.url), role.location_raw, role.city, role.state,
                role.country, role.lat, role.lon, role.distance_mi, role.work_mode,
                role.salary_min, role.salary_max, role.salary_currency,
                role.salary_period, int(role.salary_stated), role.description,
                role.posted_at, first_seen, now, role.score,
                json.dumps(role.flags), json.dumps(role.reasons),
            ),
        )
        if is_new:
            self.conn.execute(
                "INSERT INTO role_state(uid, status, updated_at) VALUES(?, 'new', ?) "
                "ON CONFLICT(uid) DO NOTHING",
                (uid, now),
            )
        return is_new

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
        sql = [
            "SELECT r.*, COALESCE(s.status, 'new') AS status, s.note, s.updated_at,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'cv') AS has_cv,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'cover_letter') AS has_letter,",
            "  (SELECT COUNT(*) FROM artifacts a WHERE a.uid = r.uid AND a.kind = 'screen') AS has_screen",
            "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid",
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
            # Ordering matters more than it looks. Ranking by score alone kept
            # the WORSE copy: the same Vectra role arrived from an aggregator
            # truncated to 500 characters and from the employer's own board at
            # 4,701, and the truncated one scored higher — it had a tidier
            # location string, and it could not lose points on advert content
            # it did not contain. So the fuller advert wins first, and score
            # only breaks ties between copies that say as much as each other.
            #
            # Bucketed rather than compared exactly, because two adverts of
            # 4,700 and 4,900 characters are the same advert and the score
            # should decide between them.
            where.append("""r.uid IN (
                SELECT uid FROM (
                    SELECT uid, ROW_NUMBER() OVER (
                        PARTITION BY lower(trim(COALESCE(company, ''))),
                                     lower(trim(COALESCE(title, '')))
                        ORDER BY LENGTH(COALESCE(description, '')) / 1000 DESC,
                                 score DESC, first_seen ASC, uid ASC
                    ) AS rn
                    FROM roles
                ) WHERE rn = 1
            )""")

        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY r.score DESC NULLS LAST, r.first_seen DESC")
        if limit:
            sql.append("LIMIT ?")
            params.append(limit)

        return self.conn.execute("\n".join(sql), params).fetchall()

    def delete(self, uid: str) -> None:
        self.conn.execute("DELETE FROM roles WHERE uid = ?", (uid,))
        self.conn.commit()

    # ── state ──────────────────────────────────────────────────────────────────

    def set_status(self, uid: str, status: str, note: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(
                f"{status!r} is not a status. Accepted: {', '.join(STATUSES)}"
            )
        self.conn.execute(
            "INSERT INTO role_state(uid, status, note, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(uid) DO UPDATE SET "
            "  status = excluded.status, "
            "  note = COALESCE(NULLIF(excluded.note, ''), role_state.note), "
            "  updated_at = excluded.updated_at",
            (uid, status, note, _now()),
        )
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
