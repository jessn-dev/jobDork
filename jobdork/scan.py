"""
jobdork.scan
============
Runs the sources, screens what came back, stores what passed.

Keyword sources and employer boards are read in one pool. Concurrency governs
how many DIFFERENT boards are read at once and not how hard any one of them is
hit — the pacing that matters is per host, and lives in fetch/http.py.

A scan filters what it fetched today and never looks back, so changing your
titles or your radius tomorrow does not revisit what is already stored. That
is what `rescreen` is for.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import fetch, geo, resume as resume_mod, screen
from .config import Config
from .fetch.http import Fetcher
from .store import Role, Store

log = logging.getLogger("jobdork.scan")


@dataclass
class ScanReport:
    fetched: int = 0
    kept: int = 0
    stored: int = 0
    newly_seen: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    per_source: list[fetch.SourceResult] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [result.summary() for result in self.per_source]
        out.append(
            f"fetched {self.fetched}, kept {self.kept}, "
            f"stored {self.stored} ({self.newly_seen} new)"
        )
        if self.dropped:
            top = sorted(self.dropped.items(), key=lambda kv: -kv[1])[:6]
            out.append("dropped: " + "; ".join(f"{n}x {why}" for why, n in top))
        if self.blocked_hosts:
            out.append(
                "blocked after repeated 429s (left alone, not retried): "
                + ", ".join(sorted(self.blocked_hosts))
            )
        return out


def _jobs_for(cfg: Config) -> list[tuple[str, dict]]:
    """Every (source, kwargs) pair this config asks for.

    Keyword sources run once. Employer boards run once per company, because
    each needs its own token.
    """
    jobs: list[tuple[str, dict]] = []
    keyword_sources = ("workable", "usajobs", "adzuna")

    for name in cfg.active_sources():
        if name in keyword_sources:
            jobs.append((name, {}))

    # Dormant keyed sources still get a turn so they can say why they skipped.
    for name in cfg.dormant_sources():
        jobs.append((name, {}))

    for company in cfg.sources.companies:
        if company.platform in cfg.sources.keyless:
            jobs.append((company.platform,
                         {"token": company.token, "company": company.name}))

    return jobs


def _load_resume(cfg: Config):
    """Optional. A resume that cannot be read warns and scoring goes on.

    The config loader already refused a path that does not exist, so anything
    reaching here is a format problem, and a format problem should not stop a
    scan that mostly does not need it.
    """
    if not cfg.resume_path:
        return None
    try:
        return resume_mod.load(cfg.resume_path)
    except resume_mod.ResumeError as exc:
        log.warning("resume not used for scoring: %s", exc)
        return None


def run(cfg: Config, store: Store, limit: int = 0,
        progress=None) -> ScanReport:
    """Fetch, screen and store. `limit` caps roles kept, for a quick look."""
    report = ScanReport()
    fetcher = Fetcher(
        user_agent=cfg.fetch.user_agent,
        timeout=cfg.fetch.timeout,
        retries=cfg.fetch.retries,
    )
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    if cfg.locations.anchor and not anchor.located:
        log.warning(
            "anchor %r could not be placed (%s) — distance filtering is off",
            cfg.locations.anchor, anchor.note,
        )

    cv = _load_resume(cfg)
    jobs = _jobs_for(cfg)
    run_id = store.start_run()
    keepers: list[Role] = []

    with ThreadPoolExecutor(max_workers=cfg.fetch.concurrency) as pool:
        futures = {}
        for name, kwargs in jobs:
            adapter = fetch.get(name)
            if adapter is None:
                continue
            futures[pool.submit(adapter, fetcher, cfg, **kwargs)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as exc:                       # one board, not the run
                log.exception("%s raised", name)
                result = fetch.SourceResult(source=name, errors=[str(exc)])
            report.per_source.append(result)
            if progress:
                progress(result.summary())

            for role in result.roles:
                report.fetched += 1
                verdict = screen.screen(role, cfg, anchor, cv)
                if verdict.keep:
                    keepers.append(role)
                else:
                    why = verdict.reasons[0] if verdict.reasons else "unknown"
                    report.dropped[why] = report.dropped.get(why, 0) + 1

    keepers.sort(key=lambda r: r.score or 0, reverse=True)
    if limit:
        keepers = keepers[:limit]

    report.kept = len(keepers)
    report.stored, report.newly_seen = store.upsert_many(keepers)
    report.blocked_hosts = sorted(fetcher.blocked_hosts)

    store.finish_run(run_id, {
        "fetched": report.fetched,
        "kept": report.kept,
        "stored": report.stored,
        "new": report.newly_seen,
        "sources": {r.source: len(r.roles) for r in report.per_source},
    })
    return report


def rescreen(cfg: Config, store: Store, remove: bool = False) -> tuple[int, int, int]:
    """Re-apply the current config to what is already stored.

    Returns (checked, no_longer_matching, removed).

    A role you have already acted on is never removed, whatever the filters
    now say. The status is a decision you made and it outranks a rule change.
    """
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    cv = _load_resume(cfg)
    rows = store.list_roles(include_settled=True)
    checked = stale = removed = 0

    for row in rows:
        checked += 1
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
        verdict = screen.screen(role, cfg, anchor, cv)
        if verdict.keep:
            store.upsert(role)
            continue

        stale += 1
        if remove and not store.has_acted(row["uid"]):
            store.delete(row["uid"])
            removed += 1

    store.conn.commit()
    return checked, stale, removed
