"""
When no built-in employer board is read, the Sources page, `jobdork
sources` and the scan's log say why, with what to change. No network.

    python tests/test_sources_why_none.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.search import directory
from jobdork.web import api

B = directory.Board


def _boards():
    return [B(name="Acme Health", platform="greenhouse", token="acme", industry="healthcare",
              countries=("US",)),
            B(name="Bank Co", platform="greenhouse", token="bank", industry="finance",
              countries=("US",)),
            B(name="Nordic", platform="lever", token="nordic", industry="healthcare",
              countries=("SE",))]


def _cfg(**directory_settings) -> Config:
    cfg = Config(titles_include=["x"])
    for k, v in directory_settings.items():
        setattr(cfg.sources.directory, k, v)
    return cfg


def test_nothing_said_when_a_board_is_read():
    cfg = _cfg(countries=["US"])
    assert directory.none_read_why(cfg, _boards()) == ""


def test_off_says_how_to_turn_them_on():
    why = directory.none_read_why(_cfg(enabled=False), _boards())
    assert "they are off" in why and "Read the built-in boards" in why


def test_each_reason_counted_with_what_to_change():
    cfg = _cfg(countries=["PH"])
    why = directory.none_read_why(cfg, _boards())
    assert why.startswith("No built-in employer board is read. Of the 3, ")
    assert "3 hire outside your countries (Philippines)" in why and "add a country" in why

    cfg = _cfg(countries=["US"], industries=["education"], skip=["Nordic"])
    why = directory.none_read_why(cfg, _boards())
    assert "2 are not in your industries" in why and "1 you switched off" in why


def test_the_sources_page_gets_the_sentence():
    was = directory.load
    # lambda: the three boards above instead of the shipped list.
    directory.load = lambda: _boards()
    try:
        assert "outside your countries" in api.directory_boards(_cfg(countries=["PH"]))["none_why"]
        assert api.directory_boards(_cfg(countries=["US"]))["none_why"] == ""
    finally:
        directory.load = was


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
