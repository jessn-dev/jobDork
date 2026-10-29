"""
A tailored resume's length, after Indeed's guidance, and its Word file. No
model involved.

    python tests/test_resume_length.py
"""

from __future__ import annotations

import html
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.output import docx, pdf
from jobdork.writing import length, resume_doc


def _job(title, start, end, bullets=8):
    return {"title": title, "company": "Acme", "location": "Austin, TX",
            "start": start, "end": end,
            "bullets": [f"Led work item {i} for the team, with a result." for i in range(bullets)]}


def _render(doc):
    return pdf.render(resume_doc.to_markdown({"name": "Jo Bloggs"}, doc))


def test_the_page_budget_follows_the_years_and_the_kind_of_work():
    assert length.budget(4)[0] == 1
    assert length.budget(10)[0] == 1
    assert length.budget(12)[0] == 2
    assert length.budget(26)[0] == 3
    # Academic and medical work keeps a longer record at any length.
    assert length.budget(3, title="Assistant Professor of Biology")[0] == 3
    assert length.budget(3, title="Staff Physician")[0] == 3
    assert length.budget(3, title="Accounts Payable Clerk")[0] == 1


def test_jobs_older_than_fifteen_years_are_left_out_unless_they_are_all_there_is():
    jobs = [_job("New", "2020", "Present"), _job("Mid", "2012", "2019"),
            _job("Old", "2001", "2008")]
    kept, old = length.recent(jobs, this_year=2026)
    assert [j["title"] for j in kept] == ["New", "Mid"] and [j["title"] for j in old] == ["Old"]
    # Someone returning to work keeps their newest job.
    kept, old = length.recent([_job("Old", "1998", "2005")], this_year=2026)
    assert [j["title"] for j in kept] == ["Old"] and not old
    # A job with no end year is current.
    assert length.recent([_job("Undated", "", "")], this_year=2026)[0]


def test_bullets_are_capped_by_how_recent_the_job_is():
    jobs = [_job(f"J{i}", "2020", "Present", bullets=9) for i in range(6)]
    gone = length.cap_bullets(jobs)
    assert [len(j["bullets"]) for j in jobs] == [7, 6, 5, 4, 3, 3]
    assert gone == 9 * 6 - (7 + 6 + 5 + 4 + 3 + 3)


def test_a_long_resume_is_cut_to_its_pages_and_says_what_went():
    doc = {"summary": "S.", "skills": [f"Skill {i}" for i in range(20)],
           "experience": [_job(f"J{i}", f"{2024 - 2 * i}", f"{2025 - 2 * i}") for i in range(7)],
           "education": [], "certifications": [], "awards": ["Employee of the year"],
           "projects": []}
    assert pdf.page_count(_render(doc)) > 1
    fitted = length.fit(doc, _render, years=6, this_year=2026)
    assert fitted.budget == 1 and fitted.pages == 1
    assert pdf.page_count(_render(doc)) == 1
    assert any(x.startswith("for space: a bullet of J6") for x in fitted.left_out)
    # The newest job is cut last: it keeps more than the oldest.
    bullets = [len(j["bullets"]) for j in doc["experience"]]
    assert bullets[0] >= bullets[-1] >= length.MIN_BULLETS


def test_a_resume_that_fits_is_left_alone():
    doc = {"summary": "S.", "skills": ["SQL"], "experience": [_job("J", "2022", "Present", 4)],
           "education": [], "certifications": [], "projects": []}
    fitted = length.fit(doc, _render, years=3, this_year=2026)
    assert fitted.pages == 1 and not fitted.left_out and len(doc["experience"][0]["bullets"]) == 4


def test_the_dates_sit_at_the_right_margin_in_the_pdf():
    md = "# Jo Bloggs\n## EXPERIENCE\n### Analyst\tMarch 2022 - Present\nAcme, Austin, TX\n"
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    reader = PdfReader(io.BytesIO(pdf.render(md)))
    places = {}
    # lambda: record where each piece of text starts on the page.
    reader.pages[0].extract_text(visitor_text=lambda t, cm, tm, f, s: places.setdefault(
        t.strip(), tm[4]) if t.strip() else None)
    width = pdf.text_width(b"March 2022 - Present", pdf.BODY, bold=True)
    assert abs(places["March 2022 - Present"] + width - (pdf.PAGE_W - pdf.MARGIN)) < 1
    assert abs(places["Analyst"] - pdf.MARGIN) < 1


def test_the_word_file_is_the_template_in_real_paragraphs():
    md = resume_doc.to_markdown(
        {"name": "Jo Bloggs", "phone": "(312) 555-0199", "email": "jo@example.com",
         "location": "Chicago, IL", "profile": "linkedin.com/in/jo"},
        {"summary": "Analyst & <lead>.", "skills": ["SQL", "Python"],
         "experience": [_job("Analyst", "Mar 2022", "current", 2)],
         "education": [{"credential": "B.S.", "school": "UT", "location": "", "start": "",
                        "end": "2017"}],
         "certifications": ["CPA, AICPA - 2019"], "awards": ["Volunteer, Food Bank"],
         "projects": []})
    data = docx.render(md, "Jo Bloggs, Analyst")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        names = set(z.namelist())
        body = z.read("word/document.xml").decode("utf-8")
        styles = z.read("word/styles.xml").decode("utf-8")
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml",
            "word/numbering.xml"} <= names
    import xml.dom.minidom
    xml.dom.minidom.parseString(body)                 # well-formed, escapes and all
    assert "<w:tbl" not in body and "<w:txbx" not in body and "header" not in "".join(names)
    assert 'w:ascii="Arial"' in styles and 'w:val="22"' in styles
    assert 'w:top="1008"' in body and 'w:w="12240"' in body
    text = [html.unescape(t) for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", body)]
    assert text[:3] == ["Jo Bloggs", "(312) 555-0199 | jo@example.com | Chicago, IL",
                        "linkedin.com/in/jo"]
    order = [text.index(h) for h in ("PROFESSIONAL SUMMARY", "EXPERIENCE", "SKILLS",
                                     "EDUCATION", "CERTIFICATIONS", "AWARDS & VOLUNTEER WORK")]
    assert order == sorted(order)
    assert "Analyst &amp; &lt;lead&gt;." in body
    # The dates follow a right tab stop at the text's edge.
    assert f'<w:tab w:val="right" w:pos="{docx.TEXT_W}"/>' in body
    assert "March 2022 - Present" in text and "Acme, Austin, TX" in text
    assert body.count('<w:numId w:val="1"/>') == 2 + 1 + 1   # bullets, cert, award


def test_the_word_file_keeps_any_script():
    with zipfile.ZipFile(io.BytesIO(docx.render("# Łukasz Żółw\n## SKILLS\n日本語 | SQL\n"))) as z:
        body = z.read("word/document.xml").decode("utf-8")
    assert "Łukasz Żółw" in body and "日本語 | SQL" in body


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
