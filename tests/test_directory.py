"""
The employer boards jobdork ships with: read from data/boards.csv, chosen by
your countries and industries, merged with your own boards, and maintained
by scripts/build_boards.py. Nothing here touches the network.

    python tests/test_directory.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config as config_mod
from jobdork.core.config import Company, Config, Directory, Locations, Sources
from jobdork.fetch.http import Response
from jobdork.search import directory, scan

ROOT = Path(__file__).resolve().parent.parent
BOARDS = [
    directory.Board("Acme Health", "workday", "acme/wd5/Ext", ("US", "PH"), "healthcare"),
    directory.Board("Beta Bank", "greenhouse", "betabank", ("US",), "banking"),
    directory.Board("Gamma", "lever", "gamma", ("GB",), "tech"),
    directory.Board("Delta", "icims", "delta", ("US",), "retail"),     # no reader
]


def _cfg(where=("US",), **directory_kw):
    return Config(locations=Locations(countries=list(where)),
                  sources=Sources(directory=Directory(**directory_kw)))


TITLES = "titles:\n  include: [nurse]\n"


def _build():
    spec = importlib.util.spec_from_file_location("build_boards", ROOT / "scripts" / "build_boards.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boards_follow_your_countries_and_readable_platforms():
    chosen = directory.select(_cfg(("US",)), BOARDS)
    assert [b.name for b in chosen] == ["Acme Health", "Beta Bank"]
    assert [b.name for b in directory.select(_cfg(("PH",)), BOARDS)] == ["Acme Health"]
    assert len(directory.select(_cfg(()), BOARDS)) == 3      # no countries: all readable


def test_directory_countries_and_industries_narrow_it():
    cfg = _cfg(("PH",), countries=["GB"], industries=["tech"])
    assert [b.name for b in directory.select(cfg, BOARDS)] == ["Gamma"]
    assert directory.select(_cfg(enabled=False), BOARDS) == []


def test_your_own_board_is_not_read_twice():
    cfg = _cfg(("US",))
    cfg.sources.companies = [Company("Beta", "greenhouse", "BetaBank")]
    names = [c.name for c in directory.companies(cfg, BOARDS)]
    assert names == ["Beta", "Acme Health"]


def test_config_reads_the_directory_setting():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(TITLES + "sources:\n  directory:\n    countries: [ph]\n    industries: [Banking]\n")
        d = config_mod.load(str(path)).sources.directory
        assert (d.enabled, d.countries, d.industries) == (True, ["PH"], ["banking"])
        path.write_text(TITLES + "sources:\n  directory: false\n")
        assert not config_mod.load(str(path)).sources.directory.enabled
        path.write_text(TITLES)
        assert config_mod.load(str(path)).sources.directory.enabled


def test_save_and_load_round_trip_sorted():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "boards.csv"
        directory.save(BOARDS, path)
        again = directory.load(path)
        assert [b.industry for b in again] == ["banking", "healthcare", "retail", "tech"]
        assert again[1].countries == ("US", "PH")
    assert directory.load("/nonexistent/boards.csv") == []


def test_scan_reads_directory_boards():
    cfg = _cfg(("US",))
    cfg.sources.keyless = ["greenhouse", "workday"]
    cfg.sources.companies = [Company("Own", "workday", "own/wd1/Ext")]
    original = directory.load
    directory.load = lambda path=None: BOARDS
    try:
        jobs = scan._jobs_for(cfg)
    finally:
        directory.load = original
    assert ("greenhouse", {"token": "betabank", "company": "Beta Bank"}) in jobs
    assert ("workday", {"token": "acme/wd5/Ext", "company": "Acme Health"}) in jobs
    assert ("workday", {"token": "own/wd1/Ext", "company": "Own"}) in jobs


def test_build_keeps_home_country_first_and_old_countries_when_none_found():
    build = _build()
    assert build.countries_for("US", ["PH", "IN", "US"]) == ("US", "IN", "PH")
    assert build.countries_for("", [], ("US", "PH")) == ("US", "PH")
    assert build.countries_for("", ["GB"], ("US", "PH")) == ("US", "GB")


def test_reverify_refreshes_keeps_a_recent_failure_and_drops_a_stale_one():
    build = _build()

    class _Boards:
        def get(self, url, **_):
            if "betabank" in url:
                return Response(url=url, status=200, json={"jobs": [
                    {"title": "Teller", "location": {"name": "Austin, TX"},
                     "absolute_url": "https://x/1", "updated_at": "2026-09-30"}]})
            return Response(url=url, status=404, error="HTTP 404")

        def post(self, url, **_):
            return Response(url=url, status=404, error="HTTP 404")

    boards = {
        ("greenhouse", "betabank"): directory.Board("Beta Bank", "greenhouse", "betabank",
                                                    ("US",), "banking", verified="2026-01-01"),
        ("greenhouse", "recent"): directory.Board("Recent", "greenhouse", "recent",
                                                  ("US",), "tech", verified="2026-09-25"),
        ("greenhouse", "stale"): directory.Board("Stale", "greenhouse", "stale",
                                                 ("US",), "tech", verified="2026-08-01"),
    }
    log = {k: [] for k in ("added", "refreshed", "failing", "removed", "review",
                           "not found", "errors")}
    build.reverify(boards, "2026-10-01", _Boards(), log)
    assert boards[("greenhouse", "betabank")].verified == "2026-10-01"
    assert ("greenhouse", "recent") in boards and ("greenhouse", "stale") not in boards
    assert len(log["failing"]) == 1 and len(log["removed"]) == 1


def test_a_rejected_board_is_removed_and_its_reason_kept_in_the_review_file():
    build = _build()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review.csv"
        path.write_text("platform,token,decision,reason\n"
                        "Workday,GoHealthUC/wd12/External,reject,a partner, not UPMC\n"
                        "workday,swa/wd1/external,accept,Southwest Airlines\n")
        review = build.load_review(path)
    assert review == {("workday", "gohealthuc/wd12/external"): "reject",
                      ("workday", "swa/wd1/external"): "accept"}
    boards = {("workday", "gohealthuc/wd12/external"): directory.Board(
        "UPMC", "workday", "gohealthuc/wd12/External", ("US",), "healthcare")}
    log = {"rejected": []}
    build.apply_rejects(boards, review, log)
    assert boards == {} and log["rejected"] == ["UPMC: workday `gohealthuc/wd12/External`"]


def test_an_employer_is_read_through_one_kind_of_board_not_two():
    """Mayo's site gives way to its Oracle board; FedEx's Workday boards keep
    its site out."""
    from jobdork.search import discover

    build = _build()
    found = {
        "Mayo Clinic": discover.Found("oracle", "x.fa.oraclecloud.com/Mayo", status="verified", jobs=9),
        "FedEx": discover.Found("site", "https://careers.fedex.com", status="verified", jobs=9),
    }
    original = discover.discover
    discover.discover = lambda url, fetcher: discover.Report(
        employer=url, found=[found[url]])
    try:
        boards = {
            ("site", "https://jobs.mayoclinic.org"): directory.Board(
                "Mayo Clinic", "site", "https://jobs.mayoclinic.org", ("US",), "healthcare"),
            ("workday", "fedex/wd1/x"): directory.Board(
                "FedEx", "workday", "fedex/wd1/x", ("US",), "logistics"),
        }
        log = {k: [] for k in ("added", "refreshed", "replaced", "review", "not found", "errors")}
        build.add([{"name": n, "url": n, "country": "US", "industry": "x"} for n in found],
                  boards, "2026-10-01", None, log)
    finally:
        discover.discover = original
    assert sorted(boards) == [("oracle", "x.fa.oraclecloud.com/mayo"), ("workday", "fedex/wd1/x")]
    assert len(log["replaced"]) == 1 and log["not found"] == []


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
