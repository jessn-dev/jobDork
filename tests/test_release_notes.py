"""
A release page's "What changed" (scripts/release_notes.py): the changelog
entries written since the release before, in full, within GitHub's limit.

    python tests/test_release_notes.py

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEAD = "# Changelog\n\nIntro.\n\n---\n\n"
TAIL = "\n## Still outstanding\n\n- a bug\n"


def _script():
    spec = importlib.util.spec_from_file_location(
        "release_notes", ROOT / "scripts" / "release_notes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _log(*titles: str, body: str = "- did it\n") -> str:
    return HEAD + "".join(f"## Added — 2026-10-01 — {t}\n\n{body}\n---\n\n"
                          for t in titles) + TAIL


def test_only_the_entries_above_where_the_last_release_stopped():
    rn = _script()
    old = _log("Three", "Two")
    new = _log("Five", "Four", "Three", "Two")
    found = rn.since(new, old)
    assert [e.splitlines()[0] for e in found] == ["## Added — 2026-10-01 — Five",
                                                  "## Added — 2026-10-01 — Four"]
    assert all("Still outstanding" not in e for e in rn.entries(new))
    assert len(rn.since(new, "")) == 4          # the first release: everything


def test_a_long_release_gives_what_fits_and_links_the_rest():
    rn = _script()
    rn.BUDGET = 300
    # lambda: git as the release tag would answer: six long entries, no earlier release.
    rn._git = lambda *a: _log(*[f"Entry {i}" for i in range(6)], body="- " + "x" * 120 + "\n") \
        if a[1].startswith("v2") else ""
    text = rn.notes("v2.0.0", "")
    assert text.startswith("## What changed")
    assert "### Added — 2026-10-01 — Entry 0" in text and "x" * 120 in text
    assert "### And " in text and "#added--2026-10-01--entry-5)" in text


def test_the_link_is_the_one_github_makes_for_the_heading():
    rn = _script()
    assert (rn.anchor("## Changed — 2026-09-30 — version 0.14.3; `v0.14.2` was never released")
            == "changed--2026-09-30--version-0143-v0142-was-never-released")


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)
