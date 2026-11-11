"""
Cover letter rules, the fuller interview prep and the resume's font (asked
2026-11-09, from the prompt pack). No live model.

    python tests/test_letter_prep_font.py
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import llm, writer
from jobdork.core import config, setup
from jobdork.core.config import Config
from jobdork.output import docx, pdf
from jobdork.writing import gates

RESUME = "# Jane Doe\nICU nurse. Seven years on a 30-bed unit. RN licence. Epic, ACLS.\n"
ADVERT = "Charge nurse for a 30-bed ICU. Required: RN licence, ACLS, leadership. " * 6


def test_a_letter_is_held_to_its_length_and_to_no_stock_phrases():
    short = "I am passionate about nursing and a team player. " * 3
    fit = ("I ran a 30-bed unit for seven years, and your advert asks for that. " * 18).strip()
    by_name = {g.name: g for g in gates.run_all(short, "cover_letter", resume_text=RESUME)}
    assert not by_name["length"].passed and "aim for 250 to 300" in by_name["length"].detail
    assert not by_name["stock phrases"].passed
    assert set(by_name["stock phrases"].items) == {"passionate", "team player"}
    ok = {g.name: g for g in gates.run_all(fit, "cover_letter", resume_text=RESUME)}
    assert ok["length"].passed and ok["stock phrases"].passed
    assert "stock phrases" in {g.name for g in gates.run_all("x " * 80, "recruiter_message")}
    assert "250 to 300 words" in writer.LETTER_SYSTEM and "never" in writer.LETTER_SYSTEM


def test_interview_prep_groups_fifteen_questions_and_builds_three_stories():
    def q(text, kind, priority="normal"):
        return {"question": text, "tests": "x", "points": ["Seven years on a 30-bed unit"],
                "kind": kind, "priority": priority}
    answer = {
        "fit": ["Seven years on a 30-bed unit"],
        "questions": [q("Tell me about a mistake you made", "behavioral", "high"),
                      q("What is your greatest weakness?", "behavioral"),
                      q("How do you staff a night shift?", "role"),
                      q("What would you do if two patients crashed?", "situational"),
                      {"question": "Old shape", "tests": "x", "points": []}],
        "follow_ups": [], "gaps": [], "talking_points": [],
        "stories": [{"question": "A mistake", "situation": "A med error was caught.",
                     "task": "I led the review.", "action": "I changed the check.",
                     "result": "No repeat."}]}
    original = llm.complete_json
    # lambda: the model's answer, with no model.
    writer.complete_json = lambda *a, **k: answer
    try:
        row = {"title": "Charge Nurse", "company": "Acme", "location_raw": "", "description": ADVERT,
               "uid": "abc"}
        draft = writer.interview_prep(llm.Settings(provider="ollama", model="m"), row, RESUME,
                                      check=False)
    finally:
        writer.complete_json = original
    text = draft.text
    assert text.index("## Behavioral") < text.index("## About the work itself") \
        < text.index("## What would you do")
    assert "Tell me about a mistake you made (high priority)" in text
    assert "### Old shape" in text, "an answer without a kind is a question about the work"
    assert "## Answers to build (STAR)" in text and "- Action: I changed the check." in text
    hard = next(g for g in draft.gates if g.name == "a failure or weakness")
    assert hard.passed and len(hard.items) == 2


def test_the_resume_font_is_chosen_or_follows_the_industries():
    cfg = Config(titles_include=["x"])
    assert config.resume_font(cfg) == "sans"
    cfg.sources.directory.industries = ["Legal services", "Banking"]
    assert config.resume_font(cfg) == "serif"
    cfg.sources.directory.industries = ["Legal services", "Healthcare"]
    assert config.resume_font(cfg) == "sans", "serif only when every field chosen suits it"
    cfg.resume_font = "serif"
    cfg.sources.directory.industries = []
    assert config.resume_font(cfg) == "serif"


def test_word_and_pdf_are_set_in_the_face_chosen():
    md = "# Jane Doe\n\n## Experience\n\n- Ran a 30-bed unit\n"
    serif = docx.render(md, "Resume", font="serif")
    with zipfile.ZipFile(io.BytesIO(serif)) as z:
        styles = z.read("word/styles.xml").decode()
        body = z.read("word/document.xml").decode()
    assert '"Georgia"' in styles and '"Georgia"' in body and '"Arial"' not in body
    with zipfile.ZipFile(io.BytesIO(docx.render(md, "Resume"))) as z:
        assert '"Arial"' in z.read("word/styles.xml").decode()
    assert b"/BaseFont /Times-Roman" in pdf.render(md, font="serif")
    assert b"/BaseFont /Helvetica " in pdf.render(md)


def test_the_font_is_saved_and_read_back():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles: {include: [nurse]}\nlocations: {countries: [US]}\n"
                        f"db: {Path(tmp) / 't.db'}\n", encoding="utf-8")
        assert setup.write(str(path), {"resume_font": "serif"}).resume_font == "serif"
        assert setup.write(str(path), {"resume_font": ""}).resume_font == ""
        try:
            setup.write(str(path), {"resume_font": "comic"})
        except ValueError as exc:
            assert "sans, serif" in str(exc)
        else:
            raise AssertionError("a font jobdork does not offer was saved")


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
