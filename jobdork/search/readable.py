"""
jobdork.search.readable
=======================
Whether an applicant tracking system can read a resume file: the file read
back the way a tracking system's text extractor reads it, then checked.

The checks follow Resume Matcher's parse check (github.com/srbhr/resume-matcher,
Apache-2.0, apps/backend/app/services/ats_parse), rewritten for jobdork: its
rules, thresholds and penalties, read with pypdf (which jobdork already
uses to read a resume) rather than pdfminer, and Word files read as the zip
of XML they are. No model is involved; the same file gives the same answer.

What is checked:

- **extraction**: there is a text layer (not a scan), the letters come out
  as letters, no page is a picture with little text on it;
- **layout**: one column (two columns are read across, line by line, and
  mixed), no tables or text boxes in a Word file, nothing important only in
  the page header or footer, few pictures, a sensible number of pages;
- **content**: an email and a phone number, near the top; the headings a
  tracking system files a resume by (experience, education, skills); dates.

Each check passes, warns or fails, with a severity. The score is 100 less 30
for a failed high-severity check, 12 for a medium and 4 for a low; a warning
costs half (Resume Matcher's weights).

Used on the resume uploaded on the Resume page (`check_file`) and on every
tailored resume jobdork writes (`check_pdf`, on its own PDF: a self-test of
output/pdf.py).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_PAGES = 10                 # read at most this many pages of one file
MIN_TEXT = 50                  # characters, for a text layer at all
SPARSE_PAGE = 200              # characters on a page with a picture: a scan
COLUMN_MIN_COVERAGE = 0.05     # of the page height, each side of a gutter
COLUMN_MIN_BOXES = 3
RIGHT_BAND_MAX_WIDTH = 0.3     # dates at the right margin are not a column
RIGHT_BAND_EDGE = 6.0          # points: boxes ending this near one right edge
RIGHT_BAND_FLUSH = 0.8
COMFORTABLE_PAGES = 2
WORD_GAP = 2.0                 # font sizes: closer than this, two pieces are one line
PENALTY = {"high": 30, "medium": 12, "low": 4}

_EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{5,}\d")
_DATE_PART = re.compile(r"(?:19|20)\d{2}|0?[1-9]|1[0-2]")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT = re.compile(r"\b(?:present|current|now)\b", re.IGNORECASE)
_GARBLED = re.compile("\\(cid:\\d+\\)|�|[-]")
_MONTH_YEAR = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
                         r"[a-z]*\.?\s+(?:19|20)\d\d\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b(?:0?[1-9]|1[0-2])[/.](?:19|20)\d\d\b")

# The headings a tracking system files a resume by, and the words for them,
# in English and the languages jobdork's users write resumes in most.
HEADINGS = {
    "experience": ("experience", "work experience", "professional experience",
                   "relevant experience", "employment", "employment history",
                   "work history", "career history", "professional background",
                   "experiencia", "experiencia laboral", "experiencia profesional",
                   "expérience", "expérience professionnelle", "berufserfahrung",
                   "experiência", "experiência profissional", "esperienza"),
    "education": ("education", "educational background", "academic background",
                  "education and training", "qualifications", "academic qualifications",
                  "educación", "formación", "formación académica", "formation",
                  "ausbildung", "bildung", "educação", "formação", "istruzione"),
    "skills": ("skills", "key skills", "technical skills", "core competencies",
               "competencies", "areas of expertise", "expertise", "core skills",
               "skills and abilities", "habilidades", "competencias", "compétences",
               "kenntnisse", "fähigkeiten", "competências", "competenze"),
}
REQUIRED = tuple(HEADINGS)
# What may follow a heading word: punctuation ("Skills & Awards"), a joining
# word ("Education and Training", or "Education and" wrapped onto a line of
# its own), or a plural ("Professional Experiences").
_JOINER = re.compile(r"[^\w\s]|(?:and|y|e|et|und)(?:\s|$)|s$")
# "S ummary", "E xperience": a large first letter, or letter spacing.
_SPLIT_FIRST = re.compile(r"^([a-z]) (?=[a-z]{2})")

# What each check says, for a person rather than a parser.
TITLES = {
    "text_layer": "Text a computer can read",
    "garbled": "Letters come out as letters",
    "scanned_pages": "No page is a picture",
    "columns": "One column",
    "tables": "No tables",
    "text_boxes": "No text boxes",
    "header_footer": "Nothing only in the page header or footer",
    "images": "Few pictures",
    "pages": "Length",
    "contact": "Email and phone near the top",
    "headings": "Standard section headings",
    "dates": "Dates, in one format",
}


@dataclass
class Check:
    id: str
    category: str                  # extraction, layout, content
    severity: str                  # high, medium, low
    status: str                    # pass, warn, fail
    detail: str = ""               # what was found, in words
    advice: str = ""               # what to do, when not passed

    @property
    def title(self) -> str:
        return TITLES.get(self.id, self.id)


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass
class Page:
    width: float
    height: float
    boxes: list[Box] = field(default_factory=list)
    images: int = 0

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.boxes)


@dataclass
class Document:
    kind: str                      # pdf, docx, text
    text: str
    pages: list[Page] = field(default_factory=list)
    page_count: int | None = None
    truncated: bool = False
    images: int = 0
    tables: int = 0
    columns: int = 1
    textbox_text: str = ""
    margin_text: str = ""          # a Word file's headers and footers


@dataclass
class Report:
    score: int
    checks: list[Check]
    kind: str = ""
    error: str = ""                # why the file could not be checked at all

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warned(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    def to_dict(self) -> dict:
        return {"score": self.score, "kind": self.kind, "error": self.error,
                "checks": [{**asdict(c), "title": c.title} for c in self.checks]}


# ── reading the file the way a tracking system does ──────────────────────────

def _visible(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def read_pdf(data: bytes) -> Document:
    """Text, and where each line of it sits, from a PDF's bytes."""
    import logging

    from pypdf import PdfReader

    # A damaged file is reported by the checks, not by pypdf in the log.
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    pages = []
    for page in list(reader.pages)[:MAX_PAGES]:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        pieces: list[tuple[float, float, float, str]] = []

        def seen(text, cm, tm, font, size, pieces=pieces):
            if not text.strip():
                return
            # Where the text matrix puts it, through the current transform.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = abs(tm[0] * cm[0]) or abs(tm[3] * cm[3]) or 1.0
            size = (size or 10) * scale
            for n, line in enumerate(t for t in text.split("\n") if t.strip()):
                pieces.append((x, y - n * size * 1.2, size, _width(line, font, size), line))

        text = page.extract_text(visitor_text=seen) or ""
        found = Page(width, height, _lines(pieces), images=_page_images(page))
        if not found.boxes and text.strip():
            found.boxes = [Box(0, 0, width, height, text)]
        pages.append(found)
    return Document("pdf", "\n".join(p.text for p in pages), pages=pages,
                    page_count=total, truncated=total > MAX_PAGES,
                    images=sum(p.images for p in pages))


def _width(text: str, font, size: float) -> float:
    """How wide a piece of text is drawn: pypdf says where text starts, not
    where it ends. From the font's own width table when it has one; the
    standard fonts (Helvetica, which jobdork's PDF uses) have none, and get
    Helvetica's; otherwise half the font size a letter."""
    try:
        widths = font.get("/Widths") if font else None
        if widths:
            first = int(font.get("/FirstChar", 0))
            table = [float(w) for w in widths]
            avg = sum(table) / max(1, len([w for w in table if w])) or 500
            return sum(table[ord(c) - first] if 0 <= ord(c) - first < len(table)
                       and table[ord(c) - first] else avg for c in text) / 1000 * size
        if font and "Helvetica" in str(font.get("/BaseFont", "")):
            from ..output import pdf
            return pdf.text_width(pdf.to_winansi(text), size,
                                  bold="Bold" in str(font.get("/BaseFont")))
    except Exception:                     # an odd font dictionary: estimate
        pass
    return len(text) * size * 0.5


def _lines(pieces) -> list[Box]:
    """Pieces of text on one baseline, close together, as one box."""
    boxes: list[Box] = []
    # lambda: top to bottom, then left to right.
    for x, y, size, width, text in sorted(pieces, key=lambda p: (-round(p[1]), p[0])):
        end = x + width
        last = boxes[-1] if boxes else None
        if last and abs(last.y0 - y) < size * 0.4 and 0 <= x - last.x1 < size * WORD_GAP:
            last.x1, last.text = max(last.x1, end), f"{last.text} {text.strip()}"
        else:
            boxes.append(Box(x, y, end, y + size, text.strip()))
    return boxes


def _page_images(page) -> int:
    try:
        xobjects = page["/Resources"].get("/XObject") or {}
        return sum(1 for o in xobjects.values() if o.get_object().get("/Subtype") == "/Image")
    except Exception:                     # a page without resources, or an odd one
        return 0


def read_docx(data: bytes) -> Document:
    """A Word file's body text, and what a tracking system trips on in it."""
    from xml.sax.saxutils import unescape

    from . import resume as resume_mod

    def text_of(xml: str) -> str:
        xml = re.sub(r"</w:p>", "\n", xml)
        return unescape(re.sub(r"<[^>]+>", "", xml))

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        # Each part refused past the size no resume reaches (resume.MAX_DOCX_XML).
        body = resume_mod.document_xml(z)
        margins = "".join(resume_mod.document_xml(z, n) for n in names
                          if re.fullmatch(r"word/(header|footer)\d*\.xml", n))
    boxes = "".join(re.findall(r"<w:txbxContent>.*?</w:txbxContent>", body, re.S))
    # Text boxes are left out of the body text, as a tracking system leaves them.
    main = re.sub(r"<w:txbxContent>.*?</w:txbxContent>", "", body, flags=re.S)
    cols = [int(n) for n in re.findall(r'<w:cols [^>]*w:num="(\d+)"', body)]
    return Document("docx", text_of(main).strip(),
                    images=sum(1 for n in names if n.startswith("word/media/")),
                    tables=len(re.findall(r"<w:tbl>", main)),
                    columns=max(cols, default=1), textbox_text=text_of(boxes),
                    margin_text=text_of(margins))


# ── the checks ────────────────────────────────────────────────────────────────

def _text_layer(doc: Document) -> Check:
    chars = _visible(doc.text)
    ok = chars >= MIN_TEXT
    return Check("text_layer", "extraction", "high", "pass" if ok else "fail",
                 f"{chars} characters of text read",
                 "" if ok else "This looks like a scan or a picture of a resume. Export it "
                 "again from Word or Google Docs as a PDF, or upload the .docx.")


def spaced_letters(text: str) -> float:
    """The share of words that are one letter: "J O H N" reads as four words.
    English has a few ("a", "I"); letter-spaced text has many."""
    words = re.findall(r"[^\W\d_]+", text)
    return sum(1 for w in words if len(w) == 1) / max(1, len(words))


def _garbled(doc: Document) -> Check:
    count = len(_GARBLED.findall(doc.text))
    ratio = count / max(1, _visible(doc.text))
    spaced = spaced_letters(doc.text)
    status = ("fail" if ratio > 0.05 or spaced > 0.3 else
              "warn" if ratio > 0.005 or spaced > 0.12 else "pass")
    if spaced > 0.12:
        return Check("garbled", "extraction", "high", status,
                     f"{round(spaced * 100)}% of the words read as single letters "
                     "(\"J O H N\" for \"JOHN\")",
                     "The letters are spaced apart, or placed one by one, so they are "
                     "read as separate words. Remove the letter spacing, or export from "
                     "Word or Google Docs rather than a design tool.")
    return Check("garbled", "extraction", "high", status,
                 f"{count} character(s) came out as symbols" if count else "",
                 "" if status == "pass" else "A font in this file does not say which letters "
                 "its shapes are. Export it again with a standard font (Arial, Calibri, "
                 "Times New Roman).")


def _scanned_pages(doc: Document) -> Check | None:
    if doc.kind != "pdf" or not doc.pages:
        return None
    sparse = [n + 1 for n, p in enumerate(doc.pages)
              if p.images and _visible(p.text) < SPARSE_PAGE]
    status = "pass" if not sparse else "fail" if len(sparse) == len(doc.pages) else "warn"
    return Check("scanned_pages", "extraction", "medium", status,
                 f"page {', '.join(map(str, sparse))} is mostly a picture" if sparse else "",
                 "" if status == "pass" else "Text inside a picture is not read. Type it "
                 "as text instead.")


def _union(spans: list[tuple[float, float]]) -> float:
    total, end = 0.0, float("-inf")
    for lo, hi in sorted(spans):
        if hi > end:
            total += hi - max(lo, end)
            end = hi
    return total


def _free_bands(blocked: list[tuple[float, float]], height: float):
    bands, cursor = [], 0.0
    for lo, hi in sorted(blocked):
        if lo > cursor:
            bands.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < height:
        bands.append((cursor, height))
    return bands


def _right_band(boxes: list[Box], width: float) -> bool:
    """Narrow boxes ending at one right edge, holding dates: the dates beside
    job titles. Dates, too, unlike Resume Matcher's rule: a sidebar of skills
    of much the same length is narrow and flush as well."""
    edge = max(b.x1 for b in boxes)
    flush = sum(1 for b in boxes if edge - b.x1 <= RIGHT_BAND_EDGE)
    dated = sum(1 for b in boxes if _YEAR.search(b.text) or _PRESENT.search(b.text))
    return (flush >= RIGHT_BAND_FLUSH * len(boxes) and dated >= RIGHT_BAND_FLUSH * len(boxes)
            and max(b.x1 - b.x0 for b in boxes) < RIGHT_BAND_MAX_WIDTH * width)


def has_columns(page: Page) -> bool:
    """A gutter with text on both sides over a real stretch of the page.

    Full-width lines cross the gutter of a one-column page; the dates at the
    right margin, beside job titles, line up in a band of their own and are
    not a column.
    """
    if page.height <= 0 or len(page.boxes) < 4:
        return False
    for step in range(25, 76, 2):
        gutter = page.width * step / 100
        crossing = [(b.y0, b.y1) for b in page.boxes if b.x0 < gutter < b.x1]
        for lo, hi in _free_bands(crossing, page.height):
            left = [(max(b.y0, lo), min(b.y1, hi)) for b in page.boxes
                    if b.x1 <= gutter and b.y1 > lo and b.y0 < hi]
            right_boxes = [b for b in page.boxes
                           if b.x0 >= gutter and b.y1 > lo and b.y0 < hi]
            if min(len(left), len(right_boxes)) < COLUMN_MIN_BOXES:
                continue
            if _right_band(right_boxes, page.width):
                continue
            right = [(max(b.y0, lo), min(b.y1, hi)) for b in right_boxes]
            if min(_union(left), _union(right)) / page.height >= COLUMN_MIN_COVERAGE:
                return True
    return False


def _columns(doc: Document) -> Check | None:
    if doc.kind == "text":
        return None
    pages = ([1] if doc.columns > 1 else []) if doc.kind == "docx" else \
        [n + 1 for n, p in enumerate(doc.pages) if has_columns(p)]
    return Check("columns", "layout", "medium", "fail" if pages else "pass",
                 f"two columns on page {', '.join(map(str, pages))}" if pages else "",
                 "" if not pages else "Many tracking systems read across both columns, "
                 "line by line, and mix them. Use a one-column layout; a tailored resume "
                 "from jobdork is one.")


def _tables(doc: Document) -> Check | None:
    if doc.kind != "docx":
        return None
    return Check("tables", "layout", "medium", "warn" if doc.tables else "pass",
                 f"{doc.tables} table(s)" if doc.tables else "",
                 "" if not doc.tables else "Some tracking systems skip or scramble tables. "
                 "Lay those parts out as plain lines.")


def _text_boxes(doc: Document) -> Check | None:
    if doc.kind != "docx":
        return None
    chars = _visible(doc.textbox_text)
    status = "fail" if chars >= MIN_TEXT else "warn" if chars else "pass"
    return Check("text_boxes", "layout", "medium", status,
                 f"{chars} characters in text boxes" if chars else "",
                 "" if status == "pass" else "Text in a text box is often not read at all. "
                 "Move it into the page itself.")


def _repeated_margins(pages: list[Page]) -> list[str]:
    seen = Counter()
    for p in pages:
        seen.update({b.text.strip().lower() for b in p.boxes
                     if b.y0 > p.height * 0.92 or b.y1 < p.height * 0.08} - {""})
    return sorted(t for t, n in seen.items() if n >= 2)


def _header_footer(doc: Document) -> Check | None:
    if doc.kind == "docx":
        only_there = bool(_EMAIL.search(doc.margin_text) and not _EMAIL.search(doc.text))
        status = "fail" if only_there else "warn" if doc.margin_text.strip() else "pass"
        return Check("header_footer", "layout", "medium", status,
                     "your email is only in the page header" if only_there
                     else "text in the page header or footer" if status == "warn" else "",
                     "" if status == "pass" else "Many tracking systems skip headers and "
                     "footers. Put your name and contact details at the top of the page itself.")
    if doc.kind != "pdf" or len(doc.pages) < 2:
        return None
    repeated = _repeated_margins(doc.pages)
    return Check("header_footer", "layout", "medium", "warn" if repeated else "pass",
                 f"{len(repeated)} line(s) repeated at the top or bottom of every page"
                 if repeated else "",
                 "" if not repeated else "A line on every page (a name, a page number) "
                 "can be read into the middle of your experience. Leave it out.")


def _images(doc: Document) -> Check | None:
    if doc.kind == "text":
        return None
    return Check("images", "layout", "low", "warn" if doc.images else "pass",
                 f"{doc.images} picture(s)" if doc.images else "",
                 "" if not doc.images else "Pictures (a photo, icons, logos, skill bars) are "
                 "not read. Anything they say should also be written as text.")


def _pages(doc: Document) -> Check | None:
    if doc.page_count is None:
        return None
    long = doc.page_count > COMFORTABLE_PAGES
    return Check("pages", "layout", "low", "warn" if long or doc.truncated else "pass",
                 f"{doc.page_count} page{'s' * (doc.page_count != 1)}",
                 "" if not long else "Over two pages is long except past 25 years of "
                 "experience or for academic and medical work. A tailored resume from "
                 "jobdork keeps to the length Indeed advises.")


def has_phone(text: str) -> bool:
    """Seven digits or more that are not all parts of a date."""
    for m in _PHONE.finditer(text):
        groups = re.findall(r"\d+", m.group())
        if sum(len(g) for g in groups) >= 7 and not all(_DATE_PART.fullmatch(g) for g in groups):
            return True
    return False


def _contact(doc: Document) -> Check:
    email = _EMAIL.search(doc.text)
    phone = has_phone(doc.text)
    where = email.start() / max(1, len(doc.text)) if email else None
    status = ("fail" if not email else
              "warn" if not phone or (where is not None and where > 0.25) else "pass")
    missing = [w for w, ok in (("an email address", bool(email)), ("a phone number", phone))
               if not ok]
    return Check("contact", "content", "high", status,
                 ("no " + " or ".join(m.split(" ", 1)[1] for m in missing) + " found")
                 if missing else ("the email is far down the page" if status == "warn" else ""),
                 "" if status == "pass" else "Put your email and phone number as text at "
                 "the top, under your name (not only in a header, a picture or an icon).")


def _heading_lines(text: str, mend: bool = False) -> list[str]:
    lines = [ln.strip(" :•|*#-\t").lower() for ln in text.splitlines()
             if 0 < len(ln.split()) <= 6 and len(ln.strip()) <= 60]
    return [_SPLIT_FIRST.sub(r"\1", ln) for ln in lines] if mend else lines


def find_sections(text: str, mend: bool = False) -> list[str]:
    """The kinds of heading found; `mend` joins a split first letter first."""
    lines = _heading_lines(text, mend)
    found = []
    for kind, names in HEADINGS.items():
        for line in lines:
            if any(line.startswith(n) and (not line[len(n):].strip() or line[len(n):].strip()
                                           in names or _JOINER.match(line[len(n):].lstrip()))
                   for n in names):
                found.append(kind)
                break
    return found


def _headings(doc: Document) -> Check:
    found = find_sections(doc.text)
    missing = [k for k in REQUIRED if k not in found]
    split = [k for k in missing if k in find_sections(doc.text, mend=True)]
    status = ("pass" if not missing else
              "fail" if "experience" in missing or len(missing) > 1 else "warn")
    if split:
        return Check("headings", "content", "medium", status,
                     f"the {', '.join(split)} heading{'s' * (len(split) > 1)} read with the "
                     "first letter apart (\"E xperience\")",
                     "A large first letter or letter spacing splits the heading, and it is "
                     "not recognised. Write headings in plain letters.")
    return Check("headings", "content", "medium", status,
                 f"no {', '.join(missing)} heading found" if missing else "",
                 "" if status == "pass" else "Tracking systems file a resume by its "
                 "headings. Use the usual ones on a line of their own: Experience, "
                 "Education, Skills.")


def _dates(doc: Document) -> Check:
    years = len(_YEAR.findall(doc.text))
    written = len(_MONTH_YEAR.findall(doc.text)), len(_NUMERIC_DATE.findall(doc.text))
    mixed = all(written)
    status = "warn" if not years or mixed else "pass"
    return Check("dates", "content", "low", status,
                 "no years found" if not years else
                 "dates written two ways (\"March 2022\" and \"03/2022\")" if mixed else "",
                 "" if status == "pass" else "Give each job its dates, written one way "
                 "throughout, such as \"March 2022 - Present\".")


CHECKS = (_text_layer, _garbled, _scanned_pages, _columns, _tables, _text_boxes,
          _header_footer, _images, _pages, _contact, _headings, _dates)


def score(checks: list[Check]) -> int:
    total = 100.0
    for c in checks:
        if c.status != "pass":
            total -= PENALTY[c.severity] / (1 if c.status == "fail" else 2)
    return max(0, min(100, round(total)))


def check(doc: Document) -> Report:
    checks = [c for fn in CHECKS if (c := fn(doc)) is not None]
    return Report(score(checks), checks, kind=doc.kind)


def check_pdf(data: bytes) -> Report:
    return check(read_pdf(data))


def check_file(path: str) -> Report:
    """A resume file on disk, checked; a report with `error` when it cannot be."""
    p = Path(path).expanduser()
    suffix = p.suffix.lower()
    try:
        data = p.read_bytes()
        if suffix == ".pdf":
            doc = read_pdf(data)
        elif suffix == ".docx":
            doc = read_docx(data)
        else:
            # Markdown and text have no layout to trip on: only the content checks.
            doc = Document("text", data.decode("utf-8", "replace"))
    except ImportError:
        return Report(0, [], kind=suffix.lstrip("."),
                      error="reading a PDF needs pypdf: pip install pypdf")
    except Exception as exc:              # a damaged file: pypdf and zipfile raise many kinds
        return Report(0, [], kind=suffix.lstrip("."),
                      error=f"could not read it: {type(exc).__name__}")
    return check(doc)
