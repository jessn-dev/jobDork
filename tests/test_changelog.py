"""scripts/changelog.py: entries wait in docs/changes/, one file each, and a
release moves them into the changelog. Temporary folders only, except the
check that every entry waiting in the repository is well formed (so CI
refuses a malformed one)."""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "changelog", Path(__file__).resolve().parent.parent / "scripts" / "changelog.py")
changelog = importlib.util.module_from_spec(_SPEC)
sys.modules["changelog"] = changelog          # its dataclass looks itself up there
_SPEC.loader.exec_module(changelog)

LOG = """# Changelog

Intro.

---

## Fixed — 2026-11-01 — An older fix

Its text.

---

## Still outstanding

- something
"""


def _entry(folder: Path, name: str, heading: str, body: str = "What changed.") -> Path:
    path = folder / name
    path.write_text(f"{heading}\n\n{body}\n", encoding="utf-8")
    return path


def _never_added(path):
    return 0


def test_every_entry_waiting_in_the_repository_is_well_formed():
    for path in changelog.files():
        assert changelog.problems(path) == [], path.name


@pytest.mark.parametrize("heading, body, wrong", [
    ("## Added: a thing", "Text.", "first line"),
    ("## Improved — 2026-11-05 — A thing", "Text.", "is not one of"),
    ("## Added — 2026-13-40 — A thing", "Text.", "is not a date"),
    ("## Added — 2026-11-05 — A thing", "Text.\n\n## Fixed — 2026-11-05 — Another\n\nMore.",
     "more than one entry"),
    ("## Added — 2026-11-05 — A thing", "Text.\n\n---", "leave out the `---`"),
])
def test_a_malformed_entry_is_named_with_what_is_wrong(heading, body, wrong):
    with tempfile.TemporaryDirectory() as tmp:
        path = _entry(Path(tmp), "thing.md", heading, body)
        found = changelog.problems(path)
        assert any(wrong in p for p in found), found


def test_a_heading_with_no_text_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bare.md"
        path.write_text("## Added — 2026-11-05 — A thing\n", encoding="utf-8")
        assert any("no text" in p for p in changelog.problems(path))


def test_collect_puts_entries_above_the_newest_newest_first_and_deletes_them():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "CHANGELOG.md"
        log.write_text(LOG, encoding="utf-8")
        waiting = tmp / "changes"
        waiting.mkdir()
        (waiting / "README.md").write_text("How this folder works.", encoding="utf-8")
        _entry(waiting, "a-old.md", "## Fixed — 2026-11-03 — Third")
        _entry(waiting, "b-new.md", "## Added — 2026-11-05 — First")
        _entry(waiting, "c-mid.md", "## Changed — 2026-11-04 — Second")

        moved = changelog.collect(log, waiting, _never_added)

        assert sorted(p.name for p in moved) == ["a-old.md", "b-new.md", "c-mid.md"]
        assert [p.name for p in waiting.iterdir()] == ["README.md"]
        text = log.read_text(encoding="utf-8")
        heads = [line for line in text.splitlines() if line.startswith("## ")]
        assert heads == ["## Added — 2026-11-05 — First", "## Changed — 2026-11-04 — Second",
                         "## Fixed — 2026-11-03 — Third", "## Fixed — 2026-11-01 — An older fix",
                         "## Still outstanding"]
        assert text.startswith("# Changelog\n\nIntro.\n\n---\n\n## Added")
        assert "First\n\nWhat changed.\n\n---\n\n## Changed" in text


def test_on_the_same_date_the_entry_added_later_comes_first():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "CHANGELOG.md"
        log.write_text(LOG, encoding="utf-8")
        waiting = tmp / "changes"
        waiting.mkdir()
        _entry(waiting, "z-early.md", "## Added — 2026-11-05 — Merged first")
        _entry(waiting, "a-late.md", "## Added — 2026-11-05 — Merged later")
        when = {"z-early.md": 100, "a-late.md": 200}
        # lambda: a stand-in for git's "when was this file added", by name
        changelog.collect(log, waiting, lambda p: when[p.name])
        text = log.read_text(encoding="utf-8")
        assert text.index("Merged later") < text.index("Merged first")


def test_a_malformed_entry_stops_collect_and_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "CHANGELOG.md"
        log.write_text(LOG, encoding="utf-8")
        waiting = tmp / "changes"
        waiting.mkdir()
        good = _entry(waiting, "good.md", "## Added — 2026-11-05 — Fine")
        _entry(waiting, "bad.md", "## Better — 2026-11-05 — Not a kind")
        with pytest.raises(ValueError, match=r"bad\.md"):
            changelog.collect(log, waiting, _never_added)
        assert log.read_text(encoding="utf-8") == LOG and good.exists()


def test_nothing_waiting_leaves_the_changelog_alone():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log = tmp / "CHANGELOG.md"
        log.write_text(LOG, encoding="utf-8")
        assert changelog.collect(log, tmp / "changes", _never_added) == []
        assert log.read_text(encoding="utf-8") == LOG
