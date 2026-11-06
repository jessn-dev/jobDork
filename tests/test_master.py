"""A master resume or the one you send (search/master.py), and what changes
with it: the length check, the setting, the page's report. Made-up text
only; no file of anyone's."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from jobdork.core import config, setup  # noqa: E402
from jobdork.search import master, readable  # noqa: E402


def _career(jobs: int, words_each: int, extra: str = "") -> str:
    """A resume of `jobs` dated roles, about `words_each` words apiece."""
    lines = ["Jane Doe", "jane@example.com", "Experience"]
    for i in range(jobs):
        year = 2000 + i
        lines += [f"Engineer at Company {i}", f"January {year} - December {year}",
                  ("Built and ran systems for the team " * (words_each // 7)).strip()]
    return "\n".join(lines) + extra


def test_the_file_name_saying_master_decides_it():
    g = master.guess("short", 1, "Master Resume Jane Doe.pdf")
    assert g.kind == master.MASTER and g.why == ["its file name says master"]
    assert master.guess("short", 1, "MasterResumeJaneDoe.pdf").kind == master.MASTER
    assert master.guess("short", 1, "Jane_master_cv.docx").kind == master.MASTER
    assert master.guess("short", 1, "Jane Doe Mastercard analyst.pdf").kind == master.REGULAR


def test_a_long_archive_is_a_master_and_a_long_cv_people_send_is_not():
    archive = _career(10, 180)                       # about 1,900 words, ten roles
    assert master.guess(archive, 4).kind == master.MASTER
    # A five-page CV of 1,500 words, and a designed resume with little text on
    # its four pages, are sent as they are (2026-11-05, eight real resumes).
    assert master.guess(_career(9, 160), 5).kind == master.REGULAR
    assert master.guess(_career(12, 10), 4).kind == master.REGULAR
    assert master.guess(_career(4, 120), 2).kind == master.REGULAR


def test_archive_sections_count_toward_a_master():
    text = _career(6, 280, "\n\nVolunteer Work\nTaught coding\n\nAwards\nEngineer of the year\n")
    g = master.guess(text, 2)
    assert g.kind == master.MASTER and any("volunteer" in w for w in g.why)
    # Part-time work and skills sorted into hard and soft are kept in an archive too.
    text = _career(6, 280, "\n\nPart-Time Work\nBarista\n\nHard Skills\nSQL\n\nSoft Skills\nMentoring\n")
    g = master.guess(text, 2)
    assert g.kind == master.MASTER and any("part-time" in w for w in g.why)


def test_your_choice_wins_over_the_guess():
    archive = _career(10, 180)
    assert master.kind_of("regular", archive, 4) == master.REGULAR
    assert master.kind_of("master", "short", 1) == master.MASTER
    assert master.kind_of("", archive, 4) == master.MASTER


def test_a_master_resume_is_not_warned_for_its_length():
    doc = readable.Document("pdf", _career(10, 180), page_count=4)
    pages = {c.id: c for c in readable.check(doc).checks}["pages"]
    assert pages.status == "warn"
    as_master = {c.id: c for c in readable.check(doc, master=True).checks}["pages"]
    assert as_master.status == "pass" and "master resume" in as_master.detail
    assert readable.check(doc, master=True).score > readable.check(doc).score


def test_the_setting_is_master_regular_or_left_to_the_guess():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles: {include: [engineer]}\nlocations: {countries: [US]}\n")
        cfg = setup.write(str(path), {"resume_kind": "master"})
        assert cfg.resume_kind == "master" and "kind: master" in path.read_text()
        cfg = setup.write(str(path), {"resume_kind": ""})
        assert cfg.resume_kind == "" and "kind:" not in path.read_text()
        with pytest.raises(ValueError):
            setup.write(str(path), {"resume_kind": "archive"})
        path.write_text(path.read_text() + "resume: {kind: archive}\n")
        with pytest.raises(config.ConfigError):
            config.load(str(path))


def test_the_page_is_told_the_kind_why_and_how_much_the_ai_reads():
    from jobdork.ai.llm import MAX_RESUME
    from jobdork.web import api

    long = _career(10, 180) + "x" * MAX_RESUME
    k = api.resume_kind("", long, 4, "resume.pdf")
    assert k["kind"] == master.MASTER and k["guess"] == master.MASTER and k["why"]
    assert k["chars"] > k["ai_reads"] == MAX_RESUME
    assert api.resume_kind("regular", long, 4)["kind"] == master.REGULAR
