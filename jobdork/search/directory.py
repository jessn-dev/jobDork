"""
jobdork.search.directory
========================
Employer boards jobdork ships with, so a fresh install reads named employers
without anyone running `discover` first.

Every row in `data/boards.csv` was found by `discover` on the employer's own
site and verified with jobs, by `scripts/build_boards.py`, never typed in by
hand: a board token is not a company name (`ghr` is Bank of America), and a
guessed one that resolves is somebody else's board. A weekly GitHub Action
re-verifies the list and proposes the changes as a pull request.

Columns:

    name        the employer
    platform    greenhouse | ashby | lever | smartrecruiters | breezy | workday
    token       the board id discover read off their site
    countries   where they hire, ISO codes joined by "|" (US, US|PH)
    industry    one word or two: retail, healthcare, banking…
    site        the page discover read the token from
    verified    the date the board last answered with jobs (YYYY-MM-DD)
    jobs        how many it listed then

Which rows a scan reads is `sources.directory` in the config: the countries
default to `locations.countries`, and industries to all of them.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..core.config import Company, Config

BOARDS_FILE = Path(__file__).resolve().parent.parent / "data" / "boards.csv"
FIELDS = ("name", "platform", "token", "countries", "industry", "site",
          "verified", "jobs")


@dataclass
class Board:
    name: str
    platform: str
    token: str
    countries: tuple[str, ...]
    industry: str
    site: str = ""
    verified: str = ""
    jobs: int = 0

    def row(self) -> dict[str, str]:
        return {"name": self.name, "platform": self.platform, "token": self.token,
                "countries": "|".join(self.countries), "industry": self.industry,
                "site": self.site, "verified": self.verified, "jobs": str(self.jobs)}

    @property
    def key(self) -> tuple[str, str]:
        return (self.platform.lower(), self.token.lower())


def load(path: Path | str = BOARDS_FILE) -> list[Board]:
    """Every board in the file. A missing file is an empty directory."""
    path = Path(path)
    if not path.is_file():
        return []
    boards = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("name") and row.get("platform") and row.get("token")):
                continue
            try:
                jobs = int(row.get("jobs") or 0)
            except ValueError:
                jobs = 0
            boards.append(Board(
                name=row["name"].strip(), platform=row["platform"].strip().lower(),
                token=row["token"].strip(),
                countries=tuple(c.strip().upper() for c in
                                (row.get("countries") or "").split("|") if c.strip()),
                industry=(row.get("industry") or "").strip().lower(),
                site=(row.get("site") or "").strip(),
                verified=(row.get("verified") or "").strip(), jobs=jobs))
    return boards


def save(boards: list[Board], path: Path | str = BOARDS_FILE) -> None:
    """Written sorted by industry then name, so a weekly diff reads as changes."""
    path = Path(path)
    ordered = sorted(boards, key=lambda b: (b.industry, b.name.lower(), b.key))
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for board in ordered:
            writer.writerow(board.row())


def select(cfg: Config, boards: list[Board] | None = None) -> list[Board]:
    """The directory boards this config reads.

    Countries: `sources.directory.countries`, else `locations.countries`;
    empty in both means every country. A board with no countries recorded is
    left out of a country filter rather than assumed to hire everywhere.
    """
    directory = cfg.sources.directory
    if not directory.enabled:
        return []
    boards = load() if boards is None else boards
    countries = {c.upper() for c in (directory.countries or cfg.locations.countries)}
    industries = {i.lower() for i in directory.industries}
    readable = set(cfg.sources.keyless)
    return [b for b in boards
            if b.platform in readable
            and (not countries or countries.intersection(b.countries))
            and (not industries or b.industry in industries)]


def companies(cfg: Config, boards: list[Board] | None = None) -> list[Company]:
    """Your own `sources.companies`, then directory boards not already in it."""
    own = list(cfg.sources.companies)
    have = {(c.platform.lower(), c.token.lower()) for c in own}
    extra = [Company(name=b.name, platform=b.platform, token=b.token)
             for b in select(cfg, boards) if b.key not in have]
    return own + extra
