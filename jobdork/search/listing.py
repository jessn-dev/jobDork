"""
jobdork.search.listing
======================
Is the job still there? Checks each stored role's posting and records what
it found as `listing_state`: open, closed, listed, unlisted or unknown.

Evidence first, a model last. What decides, in order:

  **The platform's own API**, where a page cannot say. Ashby postings are a
  single-page app that renders the same shell whether the job exists or not,
  so the board's posting API is asked for its current list instead.

  **The posting page**, read like enrich reads it:
    404 or 410                          closed (Workable answers 410)
    redirected to `?error=true`         closed (Greenhouse's closed-job redirect)
    schema.org `validThrough` in past   closed (USAJOBS states its closing date)
    the page says it plainly            closed ("no longer accepting applications")
    the page still carries JobPosting   open

  **A model**, only for a page that loaded and said none of the above, and
  only when `llm.read_pages` is on. Its "closed" counts only when it quotes
  words that are really on the page; an answer it cannot back with a quote
  is recorded as unknown.

**Adzuna cannot be checked this way**: its pages refuse scripts (see
enrich.py), and neither this nor a model gets past that. What can be said is
whether the role was still in Adzuna's results the last time Adzuna was
scanned — "listed" or "unlisted". Unlisted is a strong hint, not proof:
Adzuna returns a capped, ranked page of results, and a role can fall off it
while still open.

A role found closed on hard evidence, and still `new`, `viewed` or
`interested`, is moved to `closed` with the evidence as its note — once
every copy of the job is closed (grouping.py); one live copy keeps it open. A role you
applied to, or are interviewing for, keeps its status: the posting coming
down does not end an application.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..core import telemetry
from ..core.textutil import to_text
from ..db import grouping
from .enrich import _LD_BLOCK, _walk

log = logging.getLogger("jobdork.search.listing")

# Only statuses that mean "not acted on yet" are closed automatically.
AUTO_CLOSE = ("new", "viewed", "interested")

# Worded tightly on purpose. USAJOBS prints "this posting will no longer be
# available once the announcement has closed" on every OPEN job, and a loose
# "no longer available" would close all of them.
CLOSED_TEXT = re.compile(
    r"\b(?:"
    r"no longer accepting (?:applications|applicants|candidates)"
    r"|(?:this|the) (?:job|position|posting|role|vacancy|opening|requisition|listing)"
    r"(?: you(?:'re| are) looking for)? "
    r"(?:is no longer (?:available|open|active|accepting)"
    r"|has (?:been )?(?:closed|filled|expired|removed|taken down)"
    r"|(?:was|is) (?:closed|filled|expired|removed))"
    r"|(?:job|position|posting|vacancy) (?:has )?expired"
    r"|applications? (?:are|is|have) (?:now )?closed"
    r"|position (?:has been )?filled"
    r"|job (?:posting )?not found"
    r")\b",
    re.IGNORECASE,
)

# Evidence stronger than this is not needed to re-check; weaker is re-read.
RECHECK_HOURS = 12

# A scan older than this cannot vouch for what it listed still being up.
# Ads on the aggregators mostly expire within about a month, and opening a
# dead one gives "page not found".
STALE_DAYS = 15

# Only these say anything current about the posting itself; everything else
# is subject to the age of the scan that found it.
DIRECT = ("open", "closed", "unlisted")


@dataclass
class Finding:
    state: str          # open | closed | listed | unlisted | stale | unknown
    note: str
    hard: bool = False  # evidence enough to close a role you have not acted on


@dataclass
class CheckReport:
    checked: int = 0
    states: dict[str, int] = field(default_factory=dict)
    closed_now: list[str] = field(default_factory=list)
    skipped_fresh: int = 0

    def lines(self) -> list[str]:
        out = [f"checked {self.checked}"
               + (f", {self.skipped_fresh} checked recently and skipped"
                  if self.skipped_fresh else "")]
        if self.states:
            out.append(", ".join(f"{n} {s}" for s, n in sorted(self.states.items())))
        if self.closed_now:
            out.append(f"marked closed: {len(self.closed_now)}")
        return out


def _visible(html: str) -> str:
    return to_text(html or "")[:60_000]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _postings(html: str) -> list[dict]:
    found: list[dict] = []
    for block in _LD_BLOCK.findall(html or ""):
        try:
            found.extend(_walk(json.loads(block)))
        except (json.JSONDecodeError, TypeError):
            continue
    return found


def read_page(html: str, final_url: str, today: str) -> Finding | None:
    """What a page that loaded says about itself, or None if nothing clear."""
    if "error=true" in (final_url or ""):
        return Finding("closed", "redirected to the board's index, which is how "
                       "Greenhouse answers for a closed job", hard=True)

    postings = _postings(html)
    for posting in postings:
        until = str(posting.get("validThrough") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", until) and until < today:
            return Finding("closed", f"the advert says applications closed {until}",
                           hard=True)

    text = _visible(html)
    said = CLOSED_TEXT.search(text)
    if said:
        start = max(0, said.start() - 40)
        quote = re.sub(r"\s+", " ", text[start:said.end() + 40]).strip()
        return Finding("closed", f'the page says "…{quote}…"', hard=True)

    if postings:
        return Finding("open", "the page still carries the job advert")
    return None


class Checker:
    """Checks roles one at a time, remembering board lists it has fetched."""

    def __init__(self, fetcher, settings=None, read_pages: bool = False,
                 store=None):
        self.fetcher = fetcher
        self.store = store              # where page reads are recorded, if given
        self.settings = settings
        self.read_pages = read_pages
        self._boards: dict[str, set[str] | None] = {}
        self.today = time.strftime("%Y-%m-%d")

    def check(self, row, scans: dict[str, str] | None = None) -> Finding:
        """What is known about one posting, aged by the scan that found it."""
        scans = scans or {}
        platform = row["platform"] or ""
        found = self._evidence(row, scans.get(platform, ""))
        if found.state in DIRECT:
            return found
        # Nothing current was learned — a page that could not be read or said
        # nothing, or a source (Adzuna) that can only be taken on its word.
        # That word is only as fresh as the scan it came from.
        scanned = scans.get(platform) or (row["first_seen"] or "")
        days = _days_since(scanned)
        if days is not None and days > STALE_DAYS:
            return Finding("stale", f"{platform or 'its source'} was last "
                           f"scanned {scanned[:10]}, {days:.0f} days ago. That is over "
                           f"{STALE_DAYS} days, so this posting may be gone. "
                           f"{found.note[0].upper() + found.note[1:]}. Run a scan "
                           "to refresh, or open the posting to check")
        return found

    def _evidence(self, row, scanned: str) -> Finding:
        url = row["url"] or ""
        platform = row["platform"] or ""
        if not url:
            return Finding("unknown", "no posting URL stored")
        if platform == "adzuna":
            return self._adzuna(row, scanned)
        if platform == "ashby":
            found = self._ashby(url)
            if found:
                return found
        return self._page(row)

    def _adzuna(self, row, adzuna_run: str) -> Finding:
        seen = (row["last_seen"] or "")[:10]
        if not adzuna_run:
            return Finding("unknown", "Adzuna pages refuse scripts, and no "
                           "completed scan has read Adzuna to compare with")
        if (row["last_seen"] or "") < adzuna_run:
            return Finding("unlisted", f"not in Adzuna's results since {seen}. "
                           "Adzuna pages refuse scripts, so this cannot be "
                           "confirmed. Open the posting to check")
        return Finding("listed", "it was in Adzuna's latest results; its pages "
                       "refuse scripts, so the posting itself was not read")

    def _ashby(self, url: str) -> Finding | None:
        parts = [p for p in urlsplit(url).path.split("/") if p]
        if len(parts) < 2:
            return None
        board, job_id = parts[0], parts[1]
        if board not in self._boards:
            resp = self.fetcher.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{board}")
            jobs = (resp.json or {}).get("jobs") if resp.ok and isinstance(
                resp.json, dict) else None
            self._boards[board] = None if jobs is None else {
                str(j.get("id")) for j in jobs if j.get("isListed") is not False
            } | {str(j.get("jobUrl") or "").rstrip("/").rsplit("/", 1)[-1]
                 for j in jobs}
        ids = self._boards[board]
        if ids is None:
            return None                     # board unreadable: try the page
        if job_id in ids:
            return Finding("open", f"still listed on {board}'s Ashby board")
        return Finding("closed", f"no longer on {board}'s Ashby board",
                       hard=True)

    def _page(self, row) -> Finding:
        resp = self.fetcher.get(row["url"], expect_json=False)
        if resp.status in (404, 410):
            return Finding("closed", f"the posting answers HTTP {resp.status}",
                           hard=True)
        if not resp.ok or not resp.body:
            return Finding("unknown",
                           f"could not read the posting: {resp.error or resp.status}")

        found = read_page(resp.body, resp.final_url, self.today)
        if found:
            return found

        if self.read_pages and self.settings is not None \
                and not self.settings.problem():
            return self._ask(row["title"] or "", resp.body, row["uid"])
        return Finding("unknown", "the page loads but does not say whether "
                       "the job is open")

    def _ask(self, title: str, html: str, uid: str = "") -> Finding:
        from ..ai.llm import LLMError, classify_listing

        text = _visible(html)
        try:
            answer = classify_listing(self.settings, title, text)
        except LLMError as exc:
            return Finding("unknown", f"page unclear, and the model could not "
                           f"read it: {exc}")
        quote = answer["evidence"]
        # A claim it cannot quote from the page is not evidence.
        backed = bool(quote) and _norm(quote) in _norm(text)
        self._record(uid, answer, backed)
        if answer["state"] == "closed" and backed:
            return Finding("closed", f'{self.settings.label} read the page: '
                           f'"{quote}"', hard=True)
        if answer["state"] == "open" and backed:
            return Finding("open", f'{self.settings.label} read the page: "{quote}"')
        return Finding("unknown", "page unclear; the model's answer could not "
                       "be matched to the page's text")


    def _record(self, uid: str, answer: dict, backed: bool) -> None:
        """One page read in `ai_outputs`, guarded by the quote rule.

        The quote match is the check: an "open" or "closed" is one claim,
        supported when its quote is on the page. "unknown" claims nothing.
        """
        if self.store is None:
            return
        claims = 0 if answer["state"] == "unknown" else 1
        bad = claims and not backed
        claim = f'the job is {answer["state"]}'
        self.store.add_ai_output(
            "page_read", f'{answer["state"]}: "{answer["evidence"]}"', uid=uid,
            model=self.settings.label,
            guard={"checked": True, "claims": claims, "unsupported": int(bad),
                   "rate": (1.0 if bad else 0.0) if claims else None,
                   "flagged": [{"claim": claim, "verdict": "unsupported"}] if bad else [],
                   "method": "quote match"})


def _days_since(stamp: str) -> float | None:
    try:
        then = time.mktime(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None
    return (time.time() - then) / 86400


def last_scans(store) -> dict[str, str]:
    """Per source, the start of the latest finished scan it returned roles in.

    A source that answered nothing in a scan (Adzuna did, once) has not
    vouched for anything by being part of it.
    """
    latest: dict[str, str] = {}
    for row in store.conn.execute(
            "SELECT started_at, counts_json FROM runs WHERE finished_at IS NOT "
            "NULL ORDER BY id DESC LIMIT 100"):
        try:
            sources = json.loads(row["counts_json"] or "{}").get("sources") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        for source, count in sources.items():
            if count and source not in latest:
                latest[source] = row["started_at"]
    return latest


def run(cfg, store, fetcher, limit: int = 0, uid: str = "", force: bool = False,
        progress=None, platform: str = "") -> CheckReport:
    """Check stored roles, newest decisions first. `uid` checks just one."""
    from ..ai.llm import Settings

    report = CheckReport()
    settings = Settings.from_config(cfg)
    checker = Checker(fetcher, settings, read_pages=cfg.llm.read_pages,
                      store=store)
    scans = last_scans(store)

    if uid:
        row = store.get(uid)
        rows = [row] if row is not None else []
    else:
        rows = store.list_roles(collapse_duplicates=False)
    if platform:
        rows = [r for r in rows if r["platform"] == platform]
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - RECHECK_HOURS * 3600))
    telemetry.tick(total=min(len(rows), limit) if limit else len(rows))

    for position, row in enumerate(rows, 1):
        if limit and report.checked >= limit:
            break
        if not uid and not force and (row["listing_checked_at"] or "") > cutoff \
                and row["listing_state"] in ("closed", "open"):
            report.skipped_fresh += 1
            telemetry.tick(done=position, count="checked recently")
            continue

        found = checker.check(row, scans)
        report.checked += 1
        report.states[found.state] = report.states.get(found.state, 0) + 1
        store.set_listing(row["uid"], found.state, found.note)
        telemetry.tick(done=position, count=found.state)

        status = row["status"] or "new"
        # A job is closed when every copy of it is. The copies are checked in
        # whatever order the list gives, so the last copy found closed is the
        # one that closes the job; until then a live copy keeps it open.
        if found.state == "closed" and found.hard and status in AUTO_CLOSE:
            members = grouping.uids(store.conn, row["uid"])
            if grouping.all_closed(store.conn, members):
                others = len(members) - 1
                store.set_status(row["uid"], "closed", f"check: {found.note}"
                                 + (f" (and all {others} other copies)" if others else ""))
                report.closed_now.append(row["uid"])
        # Listed and stale come in hundreds and say the same thing; the
        # summary counts them. Print what names a particular posting.
        if progress and found.state not in ("listed", "stale"):
            progress(f"  {found.state:<8} {row['uid']}  "
                     f"{(row['title'] or '')[:40]}: {found.note[:90]}")
    return report
