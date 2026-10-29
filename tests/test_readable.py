"""
Whether an applicant tracking system can read a resume file
(search/readable.py). Files made here; no model, no network.

    python tests/test_readable.py
"""

from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.output import docx, pdf
from jobdork.search import readable
from jobdork.writing import resume_doc

INFO = {"name": "Jo Bloggs", "phone": "(312) 555-0199", "email": "jo@example.com",
        "location": "Chicago, IL"}
DOC = {"summary": "Accountant with eight years of experience.",
       "skills": ["Reconciliation", "Excel"],
       "experience": [{"title": f"Accountant {i}", "company": "Acme", "location": "Austin, TX",
                       "start": f"Mar {2010 + 2 * i}", "end": f"Feb {2012 + 2 * i}",
                       "bullets": ["Closed the books each month."]} for i in range(4)],
       "education": [{"credential": "B.S. in Accounting", "school": "UT", "location": "",
                      "start": "", "end": "May 2009"}],
       "certifications": [], "projects": []}


def _failed(report):
    return {c.id: c.status for c in report.checks if c.status != "pass"}


def _two_columns(same_length=False):
    ops, skills = [], ["Python", "SQL and data modelling", "Excel", "Team leadership", "AWS"]
    for i in range(30):
        y = 740 - i * 14
        ops.append(b"BT /F1 10 Tf 50 %d Td (Left column line %d about the work done) Tj ET" % (y, i))
        right = b"Right side skill %d" % i if same_length else skills[i % 5].encode()
        ops.append(b"BT /F1 10 Tf 360 %d Td (%s) Tj ET" % (y, right))
    return pdf._assemble([ops], "two")


def test_jobdorks_own_pdf_and_word_file_pass_every_check():
    md = resume_doc.to_markdown(INFO, DOC)
    for report in (readable.check_pdf(pdf.render(md)),
                   readable.check(readable.read_docx(docx.render(md)))):
        assert report.score == 100, _failed(report)


def test_dates_at_the_right_margin_are_not_a_second_column():
    # Titles and dates only, no bullets between: the dates make a band of their own.
    md = "# Jo Bloggs\n(312) 555-0199 | jo@example.com\n## EXPERIENCE\n" + "".join(
        f"### Job {i}\tMarch 20{10 + i} - May 20{11 + i}\nAcme, Austin, TX\n" for i in range(8)
    ) + "## EDUCATION\n### B.S.\t2009\nUT\n## SKILLS\nSQL\n"
    assert "columns" not in _failed(readable.check_pdf(pdf.render(md)))


def test_two_columns_are_found_even_when_the_sidebar_is_tidy():
    assert _failed(readable.check_pdf(_two_columns()))["columns"] == "fail"
    # A sidebar of skills of one length looks like a band of dates, but holds none.
    assert _failed(readable.check_pdf(_two_columns(same_length=True)))["columns"] == "fail"


def test_a_scan_and_spaced_letters_are_told_apart_from_text():
    empty = readable.check_pdf(pdf._assemble([[b"0.5 w 50 50 m 500 500 l S"]], "scan"))
    assert _failed(empty)["text_layer"] == "fail"
    spaced = " ".join("JOHN PAUL ACCOUNTANT EXPERIENCE EDUCATION") + "\n" * 2
    report = readable.check(readable.Document("text", spaced * 20 + "jo@example.com"))
    garbled = next(c for c in report.checks if c.id == "garbled")
    assert garbled.status == "fail" and "single letters" in garbled.detail


def test_headings_are_found_in_their_usual_forms_and_split_ones_said():
    found = readable.find_sections("PROFESSIONAL EXPERIENCES\nx\nEducation and\nTraining\n"
                                   "Technical Skills & Tools\n")
    assert found == ["experience", "education", "skills"]
    # "Experience in product work" is prose, not a heading.
    assert readable.find_sections("Experience in product work for ten years") == []
    split = readable.check(readable.Document(
        "text", "jo@example.com (312) 555-0199\nE xperience\nAcme 2020\nE ducation\nS kills\n"))
    heads = next(c for c in split.checks if c.id == "headings")
    assert heads.status == "fail" and "first letter apart" in heads.detail


def test_contact_details_and_phone_numbers():
    assert readable.has_phone("(312) 555-0199") and readable.has_phone("+63 926 733 1164")
    assert not readable.has_phone("2019 - 2022") and not readable.has_phone("03.2019 - 05.2021")
    report = readable.check(readable.Document("text", "Experience\nEducation\nSkills\n2020"))
    assert _failed(report)["contact"] == "fail"


def _word(body: str, header: str = "") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")
        if header:
            z.writestr("word/header1.xml", f"<w:hdr><w:p><w:r><w:t>{header}</w:t></w:r></w:p></w:hdr>")
        z.writestr("word/media/image1.png", b"png")
    return buffer.getvalue()


def test_word_files_with_tables_text_boxes_columns_and_a_header():
    para = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in
                   ("Experience", "Acme 2020", "Education", "Skills"))
    box = "<w:txbxContent>" + "<w:p><w:r><w:t>" + "x" * 80 + "</w:t></w:r></w:p></w:txbxContent>"
    doc = readable.read_docx(_word(para + "<w:tbl></w:tbl>" + box + '<w:cols w:num="2"/>',
                                   header="jo@example.com (312) 555-0199"))
    report = readable.check(doc)
    assert {"tables": "warn", "text_boxes": "fail", "columns": "fail",
            "header_footer": "fail", "images": "warn", "contact": "fail"}.items() \
        <= _failed(report).items()
    header = next(c for c in report.checks if c.id == "header_footer")
    assert "only in the page header" in header.detail


def test_a_file_that_cannot_be_read_says_so_and_the_score_is_the_weights():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "r.pdf"
        bad.write_bytes(b"not a pdf")
        report = readable.check_file(str(bad))
        assert report.error and report.checks == []
    checks = [readable.Check("a", "x", "high", "fail"), readable.Check("b", "x", "medium", "warn"),
              readable.Check("c", "x", "low", "pass")]
    assert readable.score(checks) == 100 - 30 - 6


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
