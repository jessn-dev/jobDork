"""
jobdork.search.scan
===================
Runs the sources, screens what came back, stores what passed.

Keyword sources and employer boards are read in one pool. Concurrency governs
how many DIFFERENT boards are read at once and not how hard any one of them is
hit — the pacing that matters is per host, and lives in fetch/http.py.

A scan filters what it fetched today and never looks back, so changing your
titles or your radius tomorrow does not revisit what is already stored. That
is what `rescreen` is for.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .. import fetch
from ..core import telemetry
from ..core.config import Config
from ..db import grouping
from ..db.store import Role, Store
from ..fetch.http import Fetcher
from ..writing import resume_doc
from . import directory, ownboard, screen
from . import resume as resume_mod

log = logging.getLogger("jobdork.search.scan")


@dataclass
class ScanReport:
    fetched: int = 0
    kept: int = 0
    stored: int = 0
    newly_seen: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    # Listed again by a source after you deleted them; not re-added.
    previously_deleted: int = 0
    per_source: list[fetch.SourceResult] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)
    # Sources left unread because Stop was pressed; what was read is kept.
    stopped: int = 0

    def lines(self) -> list[str]:
        out = self.source_lines()
        if self.stopped:
            out.append(f"stopped: {self.stopped} source{'' if self.stopped == 1 else 's'} "
                       "not read; what was found before is kept")
        out.append(
            f"fetched {self.fetched}, kept {self.kept}, "
            f"stored {self.stored} ({self.newly_seen} new)"
        )
        if self.dropped:
            # lambda: sort key, (reason, count) pairs by count, most first.
            top = sorted(self.dropped.items(), key=lambda kv: -kv[1])[:6]
            out.append("dropped: " + "; ".join(f"{n}x {why}" for why, n in top))
        if self.previously_deleted:
            out.append(f"{self.previously_deleted} you deleted earlier were "
                       "listed again and left out")
        if self.blocked_hosts:
            out.append(
                "blocked after repeated 429s (left alone, not retried): "
                + ", ".join(sorted(self.blocked_hosts))
            )
        return out

    def source_lines(self) -> list[str]:
        """One line per kind of source, however many boards of it were read.

        A full scan reads hundreds of employer boards, mostly of a few kinds;
        one line each made the run's summary a wall of text. A kind read
        once keeps its own line, which says more (why it skipped, say).
        Each board's own line still goes to progress as it finishes.
        """
        by_source: dict[str, list[fetch.SourceResult]] = {}
        for result in self.per_source:
            by_source.setdefault(result.source, []).append(result)
        out = []
        for source, results in by_source.items():
            if len(results) == 1:
                out.append(results[0].summary())
                continue
            ran = [r for r in results if not r.skipped]
            parts = [f"{source}: {sum(len(r.roles) for r in ran)} roles "
                     f"from {len(ran)} boards"]
            if len(ran) < len(results):
                parts.append(f"{len(results) - len(ran)} skipped")
            suspect = sum(r.suspect for r in ran)
            if suspect:
                parts.append(f"{suspect} SUSPECT (answered empty)")
            failed = sum(bool(r.errors) for r in ran)
            if failed:
                parts.append(f"{failed} with errors")
            out.append(", ".join(parts))
        return out

    def counts_by_source(self) -> dict[str, int]:
        """Job posts per kind of source, summed over its boards."""
        counts: dict[str, int] = {}
        for result in self.per_source:
            counts[result.source] = counts.get(result.source, 0) + len(result.roles)
        return counts


# A first scan's quick part: the keyword sources, your own boards, and this
# many of the smallest built-in boards (directory.quick), so the first job
# posts arrive within a few minutes. The rest follow as a scan of their own.
QUICK_BOARDS = 8
PARTS = ("all", "quick", "rest")


def _jobs_for(cfg: Config, part: str = "all") -> list[tuple[str, dict]]:
    """Every (source, kwargs) pair this config asks for, or one part of them.

    Keyword sources run once. Employer boards run once per company, because
    each needs its own token: yours from `sources.companies`, and the
    directory's (see search/directory.py).
    """
    jobs: list[tuple[str, dict]] = []
    keyword_sources = ("workable", "kalibrr", "himalayas", "arbeitsagentur",
                       "arbeitnow", "usajobs", "adzuna")

    if part != "rest":
        for name in cfg.active_sources():
            if name in keyword_sources:
                jobs.append((name, {}))

        # Dormant keyed sources still get a turn so they can say why they skipped.
        for name in cfg.dormant_sources():
            jobs.append((name, {}))

    # Your own boards, then the ones jobdork ships with (data/boards.csv)
    # for your countries and industries.
    own = {(c.platform.lower(), c.token.lower()) for c in cfg.sources.companies}
    sample = directory.quick(cfg, QUICK_BOARDS) if part != "all" else set()
    for company in directory.companies(cfg):
        if company.platform not in cfg.sources.keyless:
            continue
        key = (company.platform.lower(), company.token.lower())
        early = key in own or key in sample
        if part == "all" or (part == "quick") == early:
            jobs.append((company.platform,
                         {"token": company.token, "company": company.name}))

    return jobs


def _load_resume(cfg: Config, store: Store | None = None):
    """Optional. A resume that cannot be read warns and scoring goes on.

    The config loader already refused a path that does not exist, so anything
    reaching here is a format problem, and a format problem should not stop a
    scan that mostly does not need it.

    With `store`, the projects and education from the Resume page count as
    part of it: a skill shown only in a project is still a skill you have.
    """
    if not cfg.resume_path:
        return None
    try:
        cv = resume_mod.load(cfg.resume_path)
    except resume_mod.ResumeError as exc:
        log.warning("resume not used for scoring: %s", exc)
        return None
    notes = (resume_doc.record_notes(store.projects(), store.education())
             if store is not None else "")
    if notes:
        cv.text += "\n\n" + notes
        cv.skills = resume_mod.resume_skills(cv.text)
    return cv


class ScanBusy(RuntimeError):
    """Another scan of the same database is running, in this process or another."""


LOCK_FILE = "scan.lock"


@contextlib.contextmanager
def scan_lock(db_path: str) -> Iterator[None]:
    """Hold the scan lock for this database, or raise ScanBusy.

    The dashboard runs one job at a time, but a scheduled scan, or one typed
    in a terminal, is another process: two scans at once double every request
    to hosts that are paced on purpose, and the second earns the rate limit
    the first was avoiding. An operating-system lock, not a file that says
    "running": the system lets go of it when the process ends however it
    ends, so a crashed scan cannot leave the next one refused.
    """
    path = Path(db_path).resolve().parent / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")             # noqa: SIM115 - held for the scan
    try:
        try:
            if sys.platform == "win32":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ScanBusy("another scan is already running (from the dashboard, "
                           "a terminal or the schedule); this one did not start") from None
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                handle.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def run(cfg: Config, store: Store, limit: int = 0,
        progress=None, part: str = "all", stop=None) -> ScanReport:
    """Fetch, screen and store. `limit` caps roles kept, for a quick look.

    `part` is "all", or a first scan's "quick" part and the "rest" after it.
    `stop`, a threading.Event: once set, no more sources are started, the
    ones being read finish, and what was found is screened and stored.
    Raises ScanBusy when another scan of the same database is running.
    """
    with scan_lock(cfg.db_path):
        return _run(cfg, store, limit, progress, part, stop)


def _run(cfg: Config, store: Store, limit: int, progress, part: str,
         stop=None) -> ScanReport:
    report = ScanReport()
    fetcher = Fetcher(
        user_agent=cfg.fetch.user_agent,
        timeout=cfg.fetch.timeout,
        retries=cfg.fetch.retries,
    )
    home = screen.home_of(cfg)
    for text, at in home.cities:
        if not at.located:
            log.warning("city %r could not be placed (%s), so no distance is "
                        "measured from it", text, at.note)

    cv = _load_resume(cfg, store)
    jobs = _jobs_for(cfg, part)
    run_id = store.start_run()
    deleted = store.deleted_uids()
    keepers: list[Role] = []
    left_out: list[tuple[Role, str, str]] = []      # (role, rule, reason)

    telemetry.tick(total=len(jobs))
    sources_done = 0
    reads: list[tuple[str, str, str, bool]] = []     # employer boards, for ownboard

    with ThreadPoolExecutor(max_workers=cfg.fetch.concurrency) as pool:
        futures = {}
        for name, kwargs in jobs:
            adapter = fetch.get(name)
            if adapter is None:
                continue
            futures[pool.submit(adapter, fetcher, cfg, **kwargs)] = (name, kwargs)

        for future in as_completed(futures):
            if stop is not None and stop.is_set() and not report.stopped:
                # Stop: what has not started is cancelled; what is being read
                # finishes as the pool closes, and is not waited on here.
                report.stopped = sum(1 for f in futures if f.cancel())
                if progress:
                    progress(f"stopped: {report.stopped} sources left unread")
            if future.cancelled():
                continue                                   # left unread by Stop
            name, kwargs = futures[future]
            try:
                result = future.result()
            except Exception as exc:                       # one board, not the run
                log.exception("%s raised", name)
                result = fetch.SourceResult(source=name, errors=[str(exc)])
            report.per_source.append(result)
            if name in ownboard.OWN_BOARDS and kwargs.get("token") and not result.skipped:
                # Complete only when read to the end, with no error, and not
                # an empty answer that may be a throttle: then a job missing
                # from it is missing from the employer's board.
                reads.append((name, kwargs["token"], kwargs.get("company") or "",
                              result.complete and not result.errors and not result.suspect))
            if result.skipped.startswith("no key"):
                # A keyed source you chose, with no key to run on. Other skips
                # (a country it does not serve) are by design, not a warning.
                log.warning("%s: skipped (%s)", name, result.skipped)
            if result.errors:
                # Logged so the Activity page shows it as a warning, not as
                # one more progress line.
                log.warning("%s: %s", name, "; ".join(map(str, result.errors[:3])))
            sources_done += 1
            telemetry.tick(done=sources_done)
            if progress:
                progress(result.summary())

            for role in result.roles:
                report.fetched += 1
                if role.uid in deleted:
                    report.previously_deleted += 1
                    continue
                # A source that only ever sends a teaser (Adzuna's is 500
                # characters) must not replace an advert fetched by `enrich`
                # or pasted in by hand, nor be what the role is screened on.
                stored = store.stored_description(role.uid)
                if len(stored) > len(role.description or ""):
                    role.description = stored
                seen = store.first_seen(role.uid)
                verdict = screen.screen(role, cfg, home, cv, first_seen=seen)
                # Screening resolved the place, so the job's other copies can
                # now be found: one seen earlier means this is a repost, as old
                # as that first sighting (freshness.age).
                if verdict.keep:
                    earliest = grouping.earliest_seen(store.conn, role=role)
                    if earliest and (not seen or earliest < seen):
                        verdict = screen.screen(role, cfg, home, cv, first_seen=earliest)
                telemetry.tick(count="kept" if verdict.keep else "dropped")
                if verdict.keep:
                    keepers.append(role)
                else:
                    why = verdict.reasons[0] if verdict.reasons else "unknown"
                    report.dropped[why] = report.dropped.get(why, 0) + 1
                    left_out.append((role, verdict.rule, why))

    # lambda: sort key; a role with no score sorts as 0 rather than failing on
    # None.
    keepers.sort(key=lambda r: r.score or 0, reverse=True)
    if limit:
        keepers = keepers[:limit]

    report.kept = len(keepers)
    report.stored, report.newly_seen = store.upsert_many(keepers)
    # Shown on request in Job posts ("Dropped by your filters"); a post kept
    # this time is no longer a dropped one.
    store.forget_dropped(r.uid for r in keepers)
    store.save_dropped(left_out)
    store.record_board_reads(reads)
    report.blocked_hosts = sorted(fetcher.blocked_hosts)

    store.finish_run(run_id, {
        "fetched": report.fetched,
        "kept": report.kept,
        "stored": report.stored,
        "new": report.newly_seen,
        # Summed: many boards share one kind (greenhouse), and keeping the
        # last board's count made "returned 0" warnings out of busy kinds.
        "sources": report.counts_by_source(),
        # Did not run at all (no key, not your countries): not "returned 0".
        # Only when every board of that kind skipped: one Workday board
        # skipping says nothing about the other Workday boards.
        "skipped": sorted({r.source for r in report.per_source}
                          - {r.source for r in report.per_source if not r.skipped}),
        # Had an error on at least one board: a 0 from these is a failure,
        # where a 0 from the others is boards with nothing matching.
        "failed": sorted({r.source for r in report.per_source if r.errors}),
        # A first scan's two parts, which the Dashboard reads as one scan.
        "part": part,
        "stopped": report.stopped,
    })
    return report


def rescreen(cfg: Config, store: Store, remove: bool = False) -> tuple[int, int, int]:
    """Re-apply the current config to what is already stored.

    Returns (checked, no_longer_matching, removed).

    A role you have already acted on is never removed, whatever the filters
    now say. The status is a decision you made and it outranks a rule change.
    One removed is remembered as dropped, with the rule and the reason, as a
    scan's filters leave a post out: Job posts can show it and keep it, and
    a later scan that matches it again brings it back.
    """
    home = screen.home_of(cfg)
    cv = _load_resume(cfg, store)
    # Every copy, not just the one the list shows. Duplicates are collapsed
    # by score, so a hidden copy left on its old score can outrank the copy
    # that was re-screened and become the one displayed.
    rows = store.list_roles(include_settled=True, collapse_duplicates=False)
    checked = stale = removed = 0
    left_out: list[tuple[Role, str, str]] = []
    last_commit = time.monotonic()
    telemetry.tick(total=len(rows))

    for row in rows:
        checked += 1
        telemetry.tick(done=checked)
        role = Role(
            platform=row["platform"],
            company=row["company"] or "",
            title=row["title"] or "",
            url=row["url"] or "",
            location_raw=row["location_raw"] or "",
            description=row["description"] or "",
            posted_at=row["posted_at"] or "",
            work_mode=row["work_mode"] or "",
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"] or "",
            salary_period=row["salary_period"] or "",
            salary_stated=bool(row["salary_stated"]),
        )
        verdict = screen.screen(role, cfg, home, cv,
                                first_seen=grouping.earliest_seen(store.conn, uid=row["uid"]))
        # Commit as it goes. One write held open over hundreds of posts kept
        # every other writer out, telemetry included, until the very end; and
        # fifty posts at a time could still outlast the five seconds another
        # request waits for the lock, now that a change to the search starts
        # a re-screen by itself. So at least twice a second.
        if time.monotonic() - last_commit > 0.5:
            store.conn.commit()
            last_commit = time.monotonic()
        if verdict.keep:
            store.upsert(role, seen=False)
            continue

        stale += 1
        telemetry.tick(count="no longer matching")
        if remove and not store.has_acted(row["uid"]):
            left_out.append((role, verdict.rule,
                             verdict.reasons[0] if verdict.reasons else "unknown"))
            store.delete(row["uid"])
            removed += 1

    store.conn.commit()
    store.save_dropped(left_out)
    return checked, stale, removed
