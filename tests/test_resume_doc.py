"""
The tailored resume's template, file name and PDF, and the resume viewer's
Word conversion. No model involved.

    python tests/test_resume_doc.py
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.output import pdf
from jobdork.search import resume
from jobdork.writing import resume_doc

HEAD = """JESSE NGOLAB
Chicago, IL | (312) 555-0199 | jesse@example.com | https://www.linkedin.com/in/jesse
PROFESSIONAL SUMMARY
Engineer. Worked 2019-2023 on 1,200 services.
"""


def test_dates_take_the_template_form_without_inventing_a_month():
    cases = {"Mar 2022": "March 2022", "03/2022": "March 2022",
             "2022-03": "March 2022", "Sept 2019": "September 2019",
             "current": "Present", "2021": "2021", "13/2020": "13/2020"}
    for given, expected in cases.items():
        assert resume_doc.format_date(given) == expected, given
    assert resume_doc.date_range("Jan 2020", "present") == "January 2020 - Present"
    assert resume_doc.date_range("", "2021") == "2021"


def test_the_contact_line_comes_from_the_resume():
    info = resume_doc.contact(HEAD)
    assert info == {"name": "Jesse Ngolab", "location": "Chicago, IL",
                    "phone": "(312) 555-0199", "email": "jesse@example.com",
                    "profile": "linkedin.com/in/jesse"}
    # "2019-2023" and "1,200" are not phone numbers.
    assert resume_doc.contact("Jo Bloggs\nWorked 2019-2023 on 1,200 things")["phone"] == ""


def test_the_file_name_is_first_last_title_resume():
    assert (resume_doc.filename("Jesse Ngolab", "Senior Software Engineer II, "
                                "Payments Platform (Remote)")
            == "Jesse_Ngolab_Senior_Software_Engineer_II_Payments_Platform_Resume.pdf")
    assert (resume_doc.filename("María José García", "Data Analyst")
            == "Maria_Garcia_Data_Analyst_Resume.pdf")
    assert resume_doc.filename("", "../../etc/passwd") == "etc_passwd_Resume.pdf"


def test_the_template_is_laid_out_in_order():
    doc = {"summary": "S.", "skills": ["SQL", "Python"],
           "experience": [{"title": "Analyst", "company": "Acme", "location": "Austin, TX",
                           "start": "Mar 2022", "end": "current", "bullets": ["Did it."]}],
           "education": [{"credential": "B.S.", "school": "UT", "location": "",
                          "start": "", "end": "2017"}],
           "certifications": [], "projects": []}
    md = resume_doc.to_markdown(resume_doc.contact(HEAD), doc)
    assert md.splitlines()[:2] == [
        "# Jesse Ngolab",
        "Chicago, IL | (312) 555-0199 | jesse@example.com | linkedin.com/in/jesse"]
    order = [md.index(h) for h in ("## PROFESSIONAL SUMMARY", "## SKILLS",
                                   "## PROFESSIONAL EXPERIENCE", "## EDUCATION")]
    assert order == sorted(order)
    assert "Acme | Austin, TX | March 2022 - Present" in md
    assert "## CERTIFICATIONS" not in md, "an empty section is left out"
    assert resume_doc.name_of(md) == "Jesse Ngolab"


def test_the_pdf_is_real_text_in_reading_order():
    md = ("# Jesse Ngolab\nChicago, IL | jesse@example.com\n## SKILLS\nSQL, Python\n"
          "## PROFESSIONAL EXPERIENCE\n### Analyst (Łódź)\nAcme | March 2022 - Present\n"
          + "\n".join(f"- Bullet {i} with (brackets) and a back\\slash" for i in range(80)))
    data = pdf.render(md, "Jesse Ngolab, Analyst")
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.pdf"
        path.write_bytes(data)
        reader = PdfReader(str(path))
        assert len(reader.pages) >= 2, "80 bullets run onto a second page"
        text = reader.pages[0].extract_text()
    assert text.index("Jesse Ngolab") < text.index("SKILLS") < text.index("Acme")
    assert "Analyst (Lódz)" in text and "(brackets)" in text and "back\\slash" in text


def test_a_heading_is_never_left_alone_at_the_foot_of_a_page():
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    filler = "\n".join(f"- line {i}" for i in range(49))
    md = f"# Jo Bloggs\n## PROFESSIONAL EXPERIENCE\n{filler}\n### Last Job\nAcme | 2020\n- Did it.\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.pdf"
        path.write_bytes(pdf.render(md))
        pages = [p.extract_text() for p in PdfReader(str(path)).pages]
    heading_page = next(i for i, t in enumerate(pages) if "Last Job" in t)
    assert "Acme" in pages[heading_page], "the job's details follow its title"
    assert not pages[heading_page].rstrip().endswith("Last Job")


def test_a_long_word_is_split_rather_than_run_off_the_page():
    lines = pdf.wrap(b"x" * 400, 10, pdf.WIDTH)
    assert len(lines) > 1
    assert all(pdf.text_width(line, 10) <= pdf.WIDTH for line in lines)


def test_a_word_file_is_shown_with_its_headings_bullets_and_bold():
    xml = ('<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Jesse Ngolab</w:t></w:r></w:p>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Experience</w:t></w:r></w:p>'
           '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Engineer</w:t></w:r>'
           '<w:r><w:tab/><w:t xml:space="preserve">Acme &amp; Co</w:t></w:r></w:p>'
           '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr>'
           '<w:r><w:t>Built things</w:t></w:r></w:p></w:body></w:document>')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        md = resume.docx_markdown(str(path))
    assert md == "# Jesse Ngolab\n## Experience\n**Engineer** Acme & Co\n- Built things\n"


def _doc(stage, industry):
    return {"stage": stage, "industry": industry, "summary": "S.", "skills": ["SQL"],
            "experience": [{"title": "Analyst", "company": "Acme", "location": "",
                            "start": "2020", "end": "2021", "bullets": ["Did it."]}],
            "education": [{"credential": "B.S.", "school": "UT", "location": "",
                           "start": "", "end": "2019"}],
            "certifications": [],
            "projects": [{"name": f"P{i}", "bullets": ["Made it."]} for i in range(5)]}


def _headings(md):
    return [line[3:] for line in md.splitlines() if line.startswith("## ")]


def test_projects_are_placed_and_named_by_career_stage_and_industry():
    info = {"name": "Jo Bloggs"}
    assert _headings(resume_doc.to_markdown(info, _doc("student", "tech"))) == [
        "PROFESSIONAL SUMMARY", "SKILLS", "EDUCATION", "TECHNICAL PROJECTS",
        "PROFESSIONAL EXPERIENCE"]
    assert _headings(resume_doc.to_markdown(info, _doc("career_changer", "creative"))) == [
        "PROFESSIONAL SUMMARY", "SKILLS", "PORTFOLIO HIGHLIGHTS",
        "PROFESSIONAL EXPERIENCE", "EDUCATION"]
    assert _headings(resume_doc.to_markdown(info, _doc("freelancer", "tech"))) == [
        "PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
        "SELECTED CLIENT PROJECTS", "EDUCATION"]
    assert "CONSULTING HIGHLIGHTS" in _headings(
        resume_doc.to_markdown(info, _doc("freelancer", "business")))
    assert "KEY INITIATIVES" in _headings(
        resume_doc.to_markdown(info, _doc("student", "business")))
    assert _headings(resume_doc.to_markdown(info, _doc("experienced", "tech"))) == [
        "PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION"]
    # A stage the model made up is treated as experienced: nothing added.
    assert "PROJECTS" not in resume_doc.to_markdown(info, _doc("guru", "tech"))


def test_a_student_shows_at_most_three_projects():
    md = resume_doc.to_markdown({"name": "Jo"}, _doc("student", "other"))
    assert [ln for ln in md.splitlines() if ln.startswith("### P")] == [
        "### P0", "### P1", "### P2"]


def test_tutorial_projects_are_recognised():
    names = ["To-Do List", "Tic Tac Toe in C", "Weather App", "Calculator",
             "Netflix clone", "Inventory forecasting for a bakery", "Payments ledger"]
    assert resume_doc.tutorial_projects(names) == names[:5]


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
