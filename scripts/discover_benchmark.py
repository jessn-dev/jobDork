#!/usr/bin/env python3
"""
discover_benchmark.py
=====================
Runs `discover` against real employers and reports how often it finds a
board jobdork can read, and why not when it does not.

    python scripts/discover_benchmark.py                  # every employer
    python scripts/discover_benchmark.py --only US        # one country
    python scripts/discover_benchmark.py --name Walmart   # one employer

The employers are `scripts/employers.csv`: US employers across industries
first (jobdork's default audience is US job seekers in every industry, not
only tech), a smaller international set after. It is the measure for every
change to discovery and for which platform readers to build next: a fix
that does not move these numbers did not fix what users meet.

Writes `out/discover_benchmark.json` with every result, and prints:

  - each employer's outcome: found (and the board), a platform jobdork has
    no reader for, a career-site front end, blocked, or nothing at all;
  - the hit rate overall, for the US, and by industry;
  - every platform seen, readable or not, by how many employers use it.

This makes real requests to real careers sites, a few per employer, paced
per host as every jobdork request is. Run it on purpose, not in CI.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.fetch.http import Fetcher  # noqa: E402
from jobdork.search import discover  # noqa: E402

EMPLOYERS = ROOT / "scripts" / "employers.csv"
REPORT = ROOT / "out" / "discover_benchmark.json"
USER_AGENT = "jobdork (+https://github.com/jessn-dev/jobDork)"


def outcome(report: discover.Report) -> str:
    """One word for what happened, the first that applies."""
    if report.error:
        return "job site" if "job site" in report.error else "error"
    if any(f.status == "verified" for f in report.found):
        return "found"
    if report.found:
        return "board unverified"
    if report.unsupported:
        return "no reader"
    if report.hinted:
        return "token not on page"
    if report.front_end:
        return "front end"
    if report.blocked:
        return "blocked"
    return "nothing"


def run_one(row: dict, fetcher: Fetcher) -> dict:
    started = time.monotonic()
    try:
        report = discover.discover(row["url"], fetcher)
    except Exception as exc:                       # one employer, not the run
        return {**row, "outcome": "error", "detail": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.monotonic() - started, 1)}
    return {
        **row,
        "outcome": outcome(report),
        "boards": [{"platform": f.platform, "token": f.token, "status": f.status,
                    "jobs": f.jobs, "note": f.note} for f in report.found],
        "no_reader": sorted({f.platform for f in report.unsupported}),
        "hinted": report.hinted,
        "front_end": report.front_end,
        "blocked": report.blocked,
        "unreachable": report.unreachable,
        # A page robots.txt closed is a page not read: a drop in finds with
        # these filled in is the robots reading, not the site.
        "robots_skipped": report.robots_skipped,
        "pages_read": report.pages_read,
        "detail": report.error,
        "seconds": round(time.monotonic() - started, 1),
    }


def summary(results: list[dict]) -> list[str]:
    def rate(rows):
        hit = sum(r["outcome"] == "found" for r in rows)
        return f"{hit}/{len(rows)} ({100 * hit // max(len(rows), 1)}%)"

    out = ["", f"found a readable board: {rate(results)} overall"]
    us = [r for r in results if r["country"] == "US"]
    if us and len(us) != len(results):
        out.append(f"  US: {rate(us)}   international: "
                   f"{rate([r for r in results if r['country'] != 'US'])}")
    out += ["", "by industry:"]
    for industry in sorted({r["industry"] for r in results}):
        rows = [r for r in results if r["industry"] == industry]
        out.append(f"  {industry:24} {rate(rows)}")
    out += ["", "outcomes:"]
    for name, n in Counter(r["outcome"] for r in results).most_common():
        out.append(f"  {name:24} {n}")
    platforms = Counter()
    for r in results:
        for b in r.get("boards") or []:
            platforms[(b["platform"], "readable")] += 1
        for p in r.get("no_reader") or []:
            platforms[(p, "no reader")] += 1
        if r.get("front_end"):
            platforms[(r["front_end"], "front end")] += 1
    out += ["", "platforms seen (employers using each):"]
    for (name, kind), n in platforms.most_common():
        out.append(f"  {name:24} {n:3}  {kind}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--only", help="one country, e.g. US")
    parser.add_argument("--name", help="one employer, by name")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    with EMPLOYERS.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if args.only:
        rows = [r for r in rows if r["country"].upper() == args.only.upper()]
    if args.name:
        rows = [r for r in rows if r["name"].lower() == args.name.lower()]
    if not rows:
        print("no employers match")
        return 1

    fetcher = Fetcher(user_agent=USER_AGENT, timeout=20, retries=1)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda r: run_one(r, fetcher), rows))

    for r in results:
        board = ", ".join(f"{b['platform']} {b['token']} [{b['status']}]"
                          for b in r.get("boards") or [])
        extra = board or ", ".join(r.get("no_reader") or []) or r.get("front_end") \
            or ", ".join(r.get("blocked") or []) or r.get("detail") or ""
        print(f"{r['outcome']:17} {r['name'][:26]:26} {r['industry'][:14]:14} "
              f"{r['country']}  {extra[:70]}")
    for line in summary(results):
        print(line)

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
