#!/usr/bin/env python3
"""
coverage_benchmark.py
=====================
What a fresh install finds for someone outside the US: one real default
scan per test city, counted by source.

    python scripts/coverage_benchmark.py                      # Asia
    python scripts/coverage_benchmark.py --only SG --only PH  # some cities
    python scripts/coverage_benchmark.py --title "nurse"      # other titles

"Default" means what `config.example.yaml` runs with no keys: every keyless
source and the built-in employer boards, for the city's country, within
50 km, any work arrangement. Keyed sources (Adzuna, USAJOBS) are left out
on purpose, because a fresh install has none; where Adzuna has an index for
the country, the report says so.

It is the measure for adding sources outside North America: a source that
does not move these numbers did not help the people it was added for.

Writes `out/coverage_<region>.json` and prints, per city: jobs kept, by
source; distinct employers; how many are remote; and the titles that found
nothing. Real requests, paced as every scan's are; minutes per city. Run it
on purpose, not in CI.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.core import config as config_mod  # noqa: E402
from jobdork.db.store import Store  # noqa: E402
from jobdork.search import scan  # noqa: E402

REGIONS = {
    "asia": [
        ("Manila", "PH", "Manila, Philippines"),
        ("Singapore", "SG", "Singapore, Singapore"),
        ("Kuala Lumpur", "MY", "Kuala Lumpur, Malaysia"),
        ("Jakarta", "ID", "Jakarta, Indonesia"),
        ("Bangkok", "TH", "Bangkok, Thailand"),
        ("Ho Chi Minh City", "VN", "Ho Chi Minh City, Vietnam"),
        ("Bengaluru", "IN", "Bengaluru, India"),
        ("Tokyo", "JP", "Tokyo, Japan"),
        ("Seoul", "KR", "Seoul, South Korea"),
        ("Hong Kong", "HK", "Hong Kong, Hong Kong"),
        ("Taipei", "TW", "Taipei, Taiwan"),
    ],
}
# Across industries, and short: each title is a search on every source.
TITLES = ["software engineer", "accountant", "nurse", "customer service"]
# Adzuna's national indexes (docs/CONFIG.md): a keyed install would add these.
ADZUNA = {"gb", "us", "ca", "ie", "in", "de", "fr", "nl", "at", "be", "ch", "es",
          "it", "pl", "br", "mx", "za"}


def default_config(country: str, anchor: str, titles: list[str], db: str):
    cfg = config_mod.load(str(ROOT / "config.example.yaml"))
    # A fresh install has no keys, whatever this machine's .env holds.
    cfg.sources.usajobs_key = cfg.sources.usajobs_email = ""
    cfg.sources.adzuna_app_id = cfg.sources.adzuna_app_key = ""
    return config_mod.apply_overrides(
        cfg, titles=titles, countries=[country], anchor=anchor, radius=50,
        units="km", db=db)


def kept(db: str) -> list[dict]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT platform, company, title, work_mode, country FROM roles")]


def run_city(label: str, country: str, anchor: str, titles: list[str]) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "coverage.db")
        cfg = default_config(country, anchor, titles, db)
        with Store(db) as store:
            report = scan.run(cfg, store)
        rows = kept(db)
    lower = {t: [r for r in rows if t.split()[0] in (r["title"] or "").lower()] for t in titles}
    return {
        "city": label, "country": country,
        "kept": len(rows),
        "by_source": dict(Counter(r["platform"] for r in rows).most_common()),
        "employers": len({(r["company"] or "").lower() for r in rows}),
        "remote": sum(1 for r in rows if r["work_mode"] == "remote"),
        "titles_with_none": [t for t, hits in lower.items() if not hits],
        "fetched": report.fetched,
        "requests": sum(s.requests_made for s in report.per_source),
        "skipped": [s.summary() for s in report.per_source if s.skipped][:12],
        "adzuna_index": country.lower() in ADZUNA,
        "seconds": round(time.monotonic() - started),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--region", default="asia", choices=sorted(REGIONS))
    ap.add_argument("--only", action="append", help="a country code; repeat for more")
    ap.add_argument("--title", action="append", help="replace the titles; repeat")
    args = ap.parse_args()
    titles = args.title or TITLES
    cities = [c for c in REGIONS[args.region]
              if not args.only or c[1] in {o.upper() for o in args.only}]

    results = []
    for label, country, anchor in cities:
        print(f"... {label}", file=sys.stderr, flush=True)
        try:
            results.append(run_city(label, country, anchor, titles))
        except Exception as exc:                  # one city, not the run
            results.append({"city": label, "country": country,
                            "error": f"{type(exc).__name__}: {exc}"})

    out = ROOT / "out" / f"coverage_{args.region}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"titles": titles, "results": results}, indent=2),
                   encoding="utf-8")

    print(f"\ntitles: {', '.join(titles)}   (keyless default install, 50 km)\n")
    print(f"{'city':18} {'kept':>5} {'empl':>5} {'remote':>6}  by source   [no hits for]")
    for r in results:
        if "error" in r:
            print(f"{r['city']:18} error: {r['error']}")
            continue
        sources = ", ".join(f"{k} {v}" for k, v in r["by_source"].items()) or "nothing"
        adz = "" if not r["adzuna_index"] else "  (+Adzuna with a key)"
        none = f"  [{', '.join(r['titles_with_none'])}]" if r["titles_with_none"] else ""
        print(f"{r['city']:18} {r['kept']:>5} {r['employers']:>5} {r['remote']:>6}  "
              f"{sources}{adz}{none}")
    print(f"\nwritten: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
