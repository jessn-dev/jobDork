#!/usr/bin/env python3
"""
build_boards.py
===============
Builds and maintains `jobdork/data/boards.csv`, the employer boards jobdork
ships with.

    python scripts/build_boards.py --add                 # discover candidates
    python scripts/build_boards.py --reverify            # re-check the list
    python scripts/build_boards.py --add --name Walmart  # one candidate

`--add` runs `discover` on each employer in `scripts/candidates.csv` (name,
industry, country, url) and writes in every board it verified with jobs.
Nothing is typed in by hand: a token is read off the employer's own site or
it is not added. A board that came with a "check it is theirs" note (found
deep in the site under another name, like Marriott's link to Marriott
Vacations Worldwide) is left out and listed for a person to look at.

`--reverify` asks every board in the file again. One that answers with jobs
gets today's date, its job count and the countries it lists jobs in. One
that does not is kept until it has failed for STALE_DAYS, so one bad night
on their side does not drop an employer, then removed.

A person's decisions are in `scripts/boards_review.csv` (platform, token,
decision, reason): `accept` adds a board the note held back, `reject` keeps
a board out for good and removes it if it is in. Every decision has its
reason written down, so the list never holds an edit nobody can explain.

Both write `out/boards_report.md`: what was added, refreshed, failing and
removed. The weekly GitHub Action uses it as the pull request's text.

This makes real requests, paced per host as every jobdork request is. Run it
on purpose, not in CI's tests.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.fetch.http import Fetcher  # noqa: E402
from jobdork.search import directory, discover  # noqa: E402

CANDIDATES = ROOT / "scripts" / "candidates.csv"
REVIEW = ROOT / "scripts" / "boards_review.csv"
REPORT = ROOT / "out" / "boards_report.md"
USER_AGENT = "jobdork (+https://github.com/jessn-dev/jobDork)"
# A board that has not answered with jobs for this long is removed.
STALE_DAYS = 21
WORKERS = 8


def countries_for(home: str, found: list[str], old: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Home country first, then every other country the board lists jobs in.

    The home country stays even when one read shows no jobs there: a US
    employer whose open jobs today are all remote still hires in the US.
    With nothing found, what was recorded before stands.
    """
    home = (home or (old[0] if old else "")).upper()
    if not found:
        return old or ((home,) if home else ())
    rest = sorted({c.upper() for c in found} - {home})
    return ((home,) if home else ()) + tuple(rest)


def load_review(path: Path = REVIEW) -> dict[tuple[str, str], str]:
    """(platform, token) -> "accept" or "reject", from the reviewed file."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {(r["platform"].strip().lower(), r["token"].strip().lower()):
                r["decision"].strip().lower() for r in csv.DictReader(fh)
                if r.get("platform") and r.get("token")}


def apply_rejects(boards: dict, review: dict, log: dict[str, list[str]]) -> None:
    for key, decision in review.items():
        if decision == "reject" and key in boards:
            board = boards.pop(key)
            log["rejected"].append(f"{board.name}: {board.platform} `{board.token}`")


def add(candidates: list[dict], boards: dict, today: str, fetcher: Fetcher,
        log: dict[str, list[str]], review: dict | None = None) -> None:
    review = review or {}
    def one(row: dict):
        try:
            return row, discover.discover(row["url"], fetcher)
        except Exception as exc:                   # one employer, not the run
            return row, exc

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row, report in pool.map(one, candidates):
            name = row["name"]
            if isinstance(report, Exception):
                log["errors"].append(f"{name}: {type(report).__name__}: {report}")
                continue
            kept = [f for f in report.found if f.addable]
            # A real board makes the employer's site board redundant: Mayo
            # Clinic's site was read until its Oracle board could be.
            if any(f.platform != "site" for f in kept):
                for key in [k for k, b in boards.items()
                            if b.platform == "site" and b.name == name]:
                    log["replaced"].append(f"{name}: site `{boards.pop(key).token}`, "
                                           "now read through its own board")
            # The reverse holds too: an employer already read through their
            # own board gains nothing from their site (FedEx's careers page
            # stopped linking its Workday boards; the boards still answer).
            has_board = any(b.name == name and b.platform != "site" for b in boards.values())
            kept = [f for f in kept if not (f.platform == "site" and has_board)]
            for item in kept:
                verdict = review.get((item.platform.lower(), item.token.lower()))
                if verdict == "reject":
                    continue
                if "sister company" in item.note and verdict != "accept":
                    log["review"].append(f"{name}: {item.platform} `{item.token}` — {item.note}")
                    continue
                key = (item.platform.lower(), item.token.lower())
                old = boards.get(key)
                boards[key] = directory.Board(
                    name=old.name if old else name, platform=item.platform,
                    token=item.token,
                    countries=countries_for(row.get("country", ""), item.countries,
                                            old.countries if old else ()),
                    industry=old.industry if old else (row.get("industry") or "").lower(),
                    site=item.source_url, verified=today, jobs=item.jobs)
                log["refreshed" if old else "added"].append(
                    f"{name}: {item.platform} `{item.token}`, {item.jobs} jobs")
            if not kept and not has_board:
                # Why: a system with no reader, blocked, or nothing named at all.
                why = sorted({u.platform for u in report.unsupported}) or \
                    (["blocked"] if report.blocked else []) or \
                    ([f"front end {report.front_end}"] if report.front_end else []) or \
                    [f"{h} token not on page" for h in report.hinted] or ["nothing named"]
                log["not found"].append(f"{name} ({row['url']}): {', '.join(why)}")


def reverify(boards: dict, today: str, fetcher: Fetcher,
             log: dict[str, list[str]]) -> None:
    def one(board: directory.Board):
        item = discover.Found(platform=board.platform, token=board.token,
                              board_url=discover._board_url(board.platform, board.token))
        try:
            return board, discover._verify(fetcher, item)
        except Exception as exc:
            item.status, item.note = "unread", f"{type(exc).__name__}: {exc}"
            return board, item

    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=STALE_DAYS)).isoformat()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for board, item in pool.map(one, list(boards.values())):
            label = f"{board.name}: {board.platform} `{board.token}`"
            if item.status == "verified":
                board.verified, board.jobs = today, item.jobs
                board.countries = countries_for("", item.countries, board.countries)
                log["refreshed"].append(f"{label}, {item.jobs} jobs")
            elif (board.verified or "0000") < cutoff:
                del boards[board.key]
                log["removed"].append(f"{label}: {item.status} since {board.verified or 'never'}"
                                      f" ({item.note or 'no jobs'})")
            else:
                log["failing"].append(f"{label}: {item.status}, last verified "
                                      f"{board.verified} ({item.note or 'no jobs'})")


def report_text(boards: dict, log: dict[str, list[str]], mode: str) -> str:
    rows = list(boards.values())
    by_country = Counter(c for b in rows for c in b.countries[:1])
    by_industry = Counter(b.industry for b in rows)
    out = [f"## Employer boards: {mode}", "",
           f"{len(rows)} boards in `jobdork/data/boards.csv`.", "",
           "Home countries: " + ", ".join(f"{c} {n}" for c, n in by_country.most_common()),
           "", "Industries: " + ", ".join(f"{i} {n}" for i, n in by_industry.most_common()),
           ""]
    titles = {"added": "Added", "removed": f"Removed (no jobs for {STALE_DAYS} days)",
              "rejected": "Removed: rejected in scripts/boards_review.csv",
              "replaced": "Site boards replaced by the employer's own board",
              "failing": "Failing, kept for now", "review": "Left out: check by hand",
              "not found": "No readable board found", "errors": "Errors"}
    for key, title in titles.items():
        if log.get(key):
            out += [f"### {title} ({len(log[key])})", ""]
            out += [f"- {line}" for line in sorted(log[key])] + [""]
    if log.get("refreshed"):
        out += [f"{len(log['refreshed'])} boards answered with jobs and were refreshed.", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--add", action="store_true", help="discover the candidates")
    ap.add_argument("--reverify", action="store_true", help="re-check every board")
    ap.add_argument("--candidates", default=str(CANDIDATES))
    ap.add_argument("--name", action="append",
                    help="only this candidate (with --add); repeat for more")
    ap.add_argument("--file", default=str(directory.BOARDS_FILE))
    args = ap.parse_args()
    if not (args.add or args.reverify):
        ap.error("say --add, --reverify, or both")

    today = dt.date.today().isoformat()
    fetcher = Fetcher(user_agent=USER_AGENT, timeout=20, retries=1)
    boards = {b.key: b for b in directory.load(args.file)}
    log: dict[str, list[str]] = {k: [] for k in
                                 ("added", "refreshed", "failing", "removed",
                                  "rejected", "replaced", "review", "not found",
                                  "errors")}

    if args.reverify:
        reverify(boards, today, fetcher, log)
    review = load_review()
    if args.add:
        with open(args.candidates, encoding="utf-8", newline="") as fh:
            candidates = [r for r in csv.DictReader(fh)
                          if not args.name or r["name"].lower() in
                          {n.lower() for n in args.name}]
        add(candidates, boards, today, fetcher, log, review)
    apply_rejects(boards, review, log)

    directory.save(list(boards.values()), args.file)
    mode = " + ".join(m for m, on in (("re-verified", args.reverify),
                                      ("candidates added", args.add)) if on)
    text = report_text(boards, log, mode)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
