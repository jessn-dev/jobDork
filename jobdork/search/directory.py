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
    # lambda: sort key, industry then name, so the file's order is stable.
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
    Boards named in `sources.directory.skip` are left out.
    """
    directory = cfg.sources.directory
    if not directory.enabled:
        return []
    boards = load() if boards is None else boards
    countries = {c.upper() for c in (directory.countries or cfg.locations.countries)}
    industries = {i.lower() for i in directory.industries}
    readable = set(cfg.sources.keyless)
    skip = {n.casefold() for n in directory.skip}
    return [b for b in boards
            if b.platform in readable
            and (not countries or countries.intersection(b.countries))
            and (not industries or b.industry in industries)
            and b.name.casefold() not in skip]


def why_not(cfg: Config, board: Board) -> str:
    """Why `select` leaves this board out, in the Sources page's words; ''
    when it is read."""
    d = cfg.sources.directory
    if not d.enabled:
        return "built-in boards are off"
    if board.name.casefold() in {n.casefold() for n in d.skip}:
        return "switched off"
    countries = {c.upper() for c in (d.countries or cfg.locations.countries)}
    if countries and not countries.intersection(board.countries):
        return "hires outside your countries"
    if d.industries and board.industry not in {i.lower() for i in d.industries}:
        return "not one of your industries"
    if board.platform not in set(cfg.sources.keyless):
        return f"{board.platform} is not among your sources"
    return ""


# A board with fewer jobs than this is read last in a first scan's quick part:
# small is fast, but a board with one job (Alorica, 2026-10-23) shows nothing.
QUICK_MIN_JOBS = 10


def quick(cfg: Config, count: int,
          boards: list[Board] | None = None) -> set[tuple[str, str]]:
    """Keys of `count` boards for a first, quick scan: taken in turn from each
    industry, so a search across every industry samples all of them rather
    than the alphabet's first, and the smallest boards first in each. A board
    is read a page at a time, paced per host, so one with 2,000 jobs took over
    three minutes alone; the big ones are left to the background scan.
    Boards with almost no jobs come after, and unknown counts last."""
    by_industry: dict[str, list[Board]] = {}
    # lambda: sort key, fewest jobs first from QUICK_MIN_JOBS up, then the
    # boards with fewer, then those whose count is unknown (0).
    smallest = sorted(select(cfg, boards), key=lambda b: (
        0 if b.jobs >= QUICK_MIN_JOBS else 1 if b.jobs else 2, b.jobs))
    for board in smallest:
        by_industry.setdefault(board.industry, []).append(board)
    queues = list(by_industry.values())
    picked: list[tuple[str, str]] = []
    while queues and len(picked) < count:
        for q in list(queues):
            if len(picked) >= count:
                break
            picked.append(q.pop(0).key)
            if not q:
                queues.remove(q)
    return set(picked)


def companies(cfg: Config, boards: list[Board] | None = None) -> list[Company]:
    """Your own `sources.companies`, then directory boards not already in it."""
    own = list(cfg.sources.companies)
    have = {(c.platform.lower(), c.token.lower()) for c in own}
    extra = [Company(name=b.name, platform=b.platform, token=b.token)
             for b in select(cfg, boards) if b.key not in have]
    return own + extra
