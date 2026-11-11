"""
Employers to skip (asked 2026-11-11): posts from a named employer are
dropped wherever they come from, compared without case or "Inc"/"LLC", and
a change to the list re-screens. No network.

    python tests/test_skip_employers.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config as config_mod
from jobdork.core import setup
from jobdork.core.config import Config
from jobdork.db.store import Role
from jobdork.search import screen
from jobdork.web import serve


def _cfg(**kw) -> Config:
    cfg = Config(titles_include=["Nurse"])
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _role(company: str) -> Role:
    return Role(platform="greenhouse", title="Registered Nurse", company=company,
                url="https://x.test/1", location_raw="Remote", work_mode="remote")


def test_a_skipped_employer_is_dropped_however_it_is_written():
    cfg = _cfg(skip_employers=["Acme Staffing", "Initech"])
    for company in ("Acme Staffing", "ACME STAFFING, Inc.", "Acme Staffing LLC", "initech corp."):
        verdict = screen.screen(_role(company), cfg)
        assert not verdict.keep and verdict.rule == "employer", company
        assert "an employer you skip" in verdict.reasons[0]
    assert screen.skipped_employer("Acme Staffing Health", cfg) == ""
    assert screen.skipped_employer("", cfg) == ""
    assert screen.screen(_role("Lakeview Hospital"), cfg).rule != "employer"


def test_the_list_is_saved_tidy_and_loaded_back():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles:\n  include: [Nurse]\n", encoding="utf-8")
        setup.write(str(path), {"skip_employers": ["  Acme   Staffing ", "Initech", "", "acme staffing"]})
        cfg = config_mod.load(str(path))
        assert sorted(n.casefold() for n in cfg.skip_employers) == ["acme staffing", "initech"]


def test_a_change_to_the_list_re_screens_and_is_named():
    old, fresh = _cfg(), _cfg(skip_employers=["Initech"])
    assert serve._screen_key(old) != serve._screen_key(fresh)
    assert "Employers to skip: added Initech" in serve.change_words(old, fresh)


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
