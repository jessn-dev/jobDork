"""
jobdork.search.enrich
=====================
Fetches the full advert for roles that arrived with only a summary.

Dealbreakers read the advert body. So does work-mode detection, and so does
resume fit scoring. A role stored with 200 characters of teaser has not been
screened so much as waved through, and the flags on it are guesses.

The reader is schema.org `JobPosting` JSON-LD, which posting pages publish for
Google's benefit and which is therefore both stable and intended for machines.
Measured against live pages: 7,341 characters from an Ashby posting, 2,033
from a Lever one, where the search index carried a fraction of that.

**Adzuna cannot be enriched, and this refuses to try.** Its links answer 403
from bot protection, and getting past that is breaking a control rather than
declining a request — a line this tool does not cross. Adzuna's 500-character
cap is permanent, which is worth knowing before you write a dealbreaker that
depends on advert text and wonder why it never fires.

A role whose advert changes is re-screened afterwards, because a dealbreaker
that could not match 200 characters may well match 7,000, and leaving the old
verdict in place would be worse than never having fetched.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from ..core.textutil import to_text
from ..db import grouping
from ..db.store import Role, Store

log = logging.getLogger("jobdork.search.enrich")

# Below this, an advert is a teaser rather than a description.
THIN = 400

# Platforms whose adverts already arrive whole. Fetching them again would cost
# a request per role to learn nothing.
ALREADY_FULL = ("workable", "greenhouse", "ashby", "lever", "usajobs")

# Platforms that cannot be read, and why. Named rather than silently skipped.
UNREACHABLE = {
    "adzuna": "links answer 403 from bot protection, which is not worked around",
}

_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class EnrichReport:
    considered: int = 0
    fetched: int = 0
    improved: int = 0
    unchanged: int = 0
    failed: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    gained: int = 0                      # characters of advert recovered
    dated: int = 0                       # posts given their posting date from the page
    rescreened_out: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"considered {self.considered}, fetched {self.fetched}, "
            f"improved {self.improved}"
        ]
        if self.improved:
            out.append(
                f"recovered {self.gained:,} characters of advert "
                f"({self.gained // max(self.improved, 1):,} average)"
            )
        if self.unchanged or self.failed:
            out.append(f"no better {self.unchanged}, could not read {self.failed}")
        if self.dated:
            out.append(f"posting date read from the page for {self.dated}")
        for platform, count in sorted(self.skipped.items()):
            why = UNREACHABLE.get(platform, "advert already complete")
            out.append(f"skipped {count} {platform}: {why}")
        if self.rescreened_out:
            out.append(
                f"{len(self.rescreened_out)} no longer pass on the fuller text: "
                + ", ".join(self.rescreened_out[:5])
            )
        return out


def _walk(node) -> list[dict]:
    """JSON-LD nests: a list, a @graph, or a bare object."""
    found: list[dict] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk(item))
    elif isinstance(node, dict):
        if node.get("@type") == "JobPosting":
            found.append(node)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                found.extend(_walk(node[key]))
    return found


def extract_description(html: str) -> str:
    """The longest JobPosting description on the page, as plain text.

    Longest rather than first: a page may carry a short summary block and a
    full one, and the summary is the thing already stored.
    """
    best = ""
    for block in _LD_BLOCK.findall(html or ""):
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for posting in _walk(data):
            description = posting.get("description")
            if isinstance(description, str) and len(description) > len(best):
                best = description
    return to_text(best)


def extract_posted(html: str) -> str:
    """The posting date the page states, YYYY-MM-DD, or "".

    schema.org `datePosted` first, which is the employer's own record; else a
    "Posted 3 weeks ago" in the page text (freshness.relative_posted, which
    only reads a date after the word "posted"). For posts whose board gave no
    date, so their age does not rest on when jobdork happened to see them.
    """
    from . import freshness

    for block in _LD_BLOCK.findall(html or ""):
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for posting in _walk(data):
            when = freshness.parse_date(str(posting.get("datePosted") or ""))
            if when:
                return when.isoformat()
    when = freshness.relative_posted(to_text(html or "")[:20_000])
    return when.isoformat() if when else ""


def _smartrecruiters(fetcher, row) -> tuple[str, bool]:
    """SmartRecruiters keeps the advert on the detail record, not the page.

    Its public posting page carries no schema.org data, so the generic reader
    finds nothing there. The detail endpoint splits the advert across
    `jobAd.sections`, and all of them are joined — a dealbreaker about
    qualifications lives in a different section from one about the role.
    """
    import re as _re

    match = _re.search(
        r"jobs\.smartrecruiters\.com/([^/]+)/(\d+)", row["url"] or "")
    if not match:
        return "", False
    company, posting = match.groups()
    resp = fetcher.get(
        f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting}")
    if not resp.ok or not isinstance(resp.json, dict):
        return "", False

    sections = ((resp.json.get("jobAd") or {}).get("sections") or {})
    ordered = ("jobDescription", "qualifications", "additionalInformation",
               "companyDescription")
    parts = [(sections.get(name) or {}).get("text") or "" for name in ordered]
    return to_text("\n\n".join(p for p in parts if p)), True


# Platforms whose advert is not on the page the role links to.
PLATFORM_READERS = {"smartrecruiters": _smartrecruiters}


def enrich(cfg, store: Store, fetcher, limit: int = 0, platform: str = "",
           thin: int = THIN, dry_run: bool = False,
           progress=None) -> EnrichReport:
    """Fetch fuller adverts for thin roles and re-screen what changes."""
    from . import geo, screen
    from .scan import _load_resume

    report = EnrichReport()
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    cv = _load_resume(cfg)

    sql = [
        "SELECT r.*, COALESCE(s.status, 'new') AS status",
        "FROM roles r LEFT JOIN role_state s ON s.uid = r.uid",
        "WHERE LENGTH(COALESCE(r.description, '')) < ?",
    ]
    params: list = [thin]
    if platform:
        sql.append("AND r.platform = ?")
        params.append(platform)
    sql.append("ORDER BY r.score DESC NULLS LAST")
    if limit:
        sql.append("LIMIT ?")
        params.append(limit)

    rows = store.conn.execute("\n".join(sql), params).fetchall()
    from ..core import telemetry
    telemetry.tick(total=len(rows))

    for row in rows:
        report.considered += 1
        telemetry.tick(done=report.considered)
        source = row["platform"] or ""

        if source in UNREACHABLE or source in ALREADY_FULL:
            report.skipped[source] = report.skipped.get(source, 0) + 1
            continue
        if not row["url"]:
            report.failed += 1
            continue

        reader = PLATFORM_READERS.get(source)
        if reader:
            description, ok = reader(fetcher, row)
            report.fetched += 1
            if not ok:
                report.failed += 1
                if progress:
                    progress(f"  {row['uid']} could not read its detail record")
                continue
        else:
            resp = fetcher.get(row["url"], expect_json=False)
            report.fetched += 1
            if not resp.ok or not resp.body:
                report.failed += 1
                if progress:
                    progress(f"  {row['uid']} could not read: "
                             f"{resp.error or resp.status}")
                continue
            description = extract_description(resp.body)
            if not row["posted_at"] and not dry_run:
                posted = extract_posted(resp.body)
                if posted:
                    # Kept whether or not the advert improved: the date alone
                    # is worth having.
                    store.conn.execute("UPDATE roles SET posted_at = ? WHERE uid = ?",
                                       (posted, row["uid"]))
                    row = store.get(row["uid"]) or row
                    report.dated += 1
        before = len(row["description"] or "")
        if len(description) <= before:
            report.unchanged += 1
            continue

        report.improved += 1
        telemetry.tick(count="improved")
        report.gained += len(description) - before
        if progress:
            progress(f"  {row['uid']} {before} -> {len(description)} chars  "
                     f"{(row['title'] or '')[:44]}")
        if dry_run:
            continue

        role = Role(
            platform=row["platform"], company=row["company"] or "",
            title=row["title"] or "", url=row["url"] or "",
            location_raw=row["location_raw"] or "", description=description,
            posted_at=row["posted_at"] or "", work_mode=row["work_mode"] or "",
            salary_min=row["salary_min"], salary_max=row["salary_max"],
            salary_currency=row["salary_currency"] or "",
            salary_period=row["salary_period"] or "",
            salary_stated=bool(row["salary_stated"]),
        )

        # Re-screened on the fuller text. A dealbreaker that could not match a
        # 200-character teaser may match 7,000 characters, and keeping the old
        # verdict would be worse than never having fetched.
        verdict = screen.screen(role, cfg, anchor, cv,
                                first_seen=grouping.earliest_seen(store.conn, uid=row["uid"]))
        store.upsert(role, seen=False)
        store.conn.commit()                  # each fetch is slow; do not hold a write
        if not verdict.keep:
            report.rescreened_out.append(row["uid"])
            store.set_status(row["uid"], "skipped",
                             f"enrich: {verdict.reasons[0]}")

    store.conn.commit()
    return report
