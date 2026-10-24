#!/usr/bin/env python3
"""
badges.py
=========
The README's coverage and vulnerability badges, as small JSON files that
shields.io turns into pictures.

    python scripts/badges.py <coverage.json> <pip-audit.json> <out dir>

`coverage.json` is `coverage json`'s report on the test suite;
`pip-audit.json` is `pip-audit -f json` on requirements.lock, the exact
dependencies the image and the installers carry. The files are published
with the user guide on GitHub Pages (.github/workflows/guide.yml), on every
push to main and once a week, because new advisories appear without any
change here. No outside service and no account: shields.io reads the files
from the Pages site.

Writes <out dir>/coverage.json and <out dir>/vulnerabilities.json in
shields.io's endpoint format. Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def coverage_badge(report: dict) -> dict:
    percent = float(report["totals"]["percent_covered"])
    colour = ("brightgreen" if percent >= 80 else "green" if percent >= 70
              else "yellow" if percent >= 60 else "orange" if percent >= 50 else "red")
    return {"schemaVersion": 1, "label": "coverage", "message": f"{percent:.0f}%",
            "color": colour}


def vulnerability_badge(audit: dict) -> dict:
    found = sum(len(d.get("vulns") or []) for d in audit.get("dependencies") or [])
    return {"schemaVersion": 1, "label": "known vulnerabilities",
            "message": str(found) if found else "none",
            "color": "red" if found else "brightgreen"}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1])
        return 2
    coverage, audit, out = (Path(a) for a in argv)
    out.mkdir(parents=True, exist_ok=True)
    badges = {"coverage.json": coverage_badge(json.loads(coverage.read_text(encoding="utf-8"))),
              "vulnerabilities.json": vulnerability_badge(
                  json.loads(audit.read_text(encoding="utf-8")))}
    for name, badge in badges.items():
        (out / name).write_text(json.dumps(badge), encoding="utf-8")
        print(f"{name}: {badge['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
