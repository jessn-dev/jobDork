"""
jobdork.output.pdf
==================
A resume as a PDF: single column, real text, the standard fonts.

Written here rather than taken from a library on purpose. A resume needs
headings, paragraphs and bullets in one column, and the PDF standard fonts
(Helvetica, which the AI-friendly template accepts as Arial's equal) need no
font files. A library for that would bring an image stack and a font toolkit
into the container, each something to lock, scan and keep patched.

**What an applicant tracking system needs, it gets:** selectable text in
reading order, top to bottom, no tables, no text boxes, no images, the contact
line in the body rather than a page header.

**What it cannot do:** the standard fonts cover Western European text
(Windows-1252). Anything else is spelled with the nearest letters ("Łódź"
becomes "Lodz"), and a character with no near letter becomes "?". A resume
in another script needs a different tool.

Input is the small Markdown the resume template is written in
(writing/resume_doc.py):

    # Name
    contact line
    ## SECTION
    ### Job title                 bold line
    Company | City | dates        plain line
    - bullet
    anything else                 a paragraph
"""

from __future__ import annotations

import re
import unicodedata
import zlib

PAGE_W, PAGE_H = 612.0, 792.0            # US Letter, in points
MARGIN = 54.0                             # three quarters of an inch
WIDTH = PAGE_W - 2 * MARGIN

# Advance widths from the Helvetica AFM files, per 1000 units, for 32..126.
_REGULAR = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]
_WIDE = 600          # anything outside 32..126: a little wide, so lines never overrun


def to_winansi(text: str) -> bytes:
    """Text in the standard fonts' encoding, with the nearest letters for the rest."""
    out = []
    for ch in text:
        try:
            out.append(ch.encode("cp1252"))
            continue
        except UnicodeEncodeError:
            pass
        plain = unicodedata.normalize("NFKD", ch)
        plain = "".join(c for c in plain if not unicodedata.combining(c))
        plain = plain.replace("Ł", "L").replace("ł", "l")
        out.append(plain.encode("cp1252", errors="replace") if plain else b"?")
    return b"".join(out)


def text_width(data: bytes, size: float, bold: bool = False) -> float:
    table = _BOLD if bold else _REGULAR
    return sum(table[b - 32] if 32 <= b <= 126 else _WIDE for b in data) * size / 1000


def wrap(data: bytes, size: float, width: float, bold: bool = False) -> list[bytes]:
    """Greedy word wrap; a word longer than the line is split where it must be."""
    lines, line = [], b""
    for word in data.split():
        trial = line + b" " + word if line else word
        if text_width(trial, size, bold) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        while text_width(word, size, bold) > width:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, bold) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        line = word
    if line:
        lines.append(line)
    return lines or [b""]


def _escape(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Pages:
    """Lays lines out down the page, starting a new one when it is full."""

    def __init__(self) -> None:
        self.pages: list[list[bytes]] = [[]]
        self.y = PAGE_H - MARGIN

    def _room(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def keep(self, height: float) -> None:
        """Start a new page now unless `height` fits: a heading goes with what follows it."""
        self._room(height)

    def gap(self, points: float) -> None:
        self.y -= points

    def text(self, data: bytes, size: float, bold: bool = False, x: float = MARGIN,
             centre: bool = False) -> None:
        lead = size * 1.25
        self._room(lead)
        self.y -= lead
        if centre:
            x = (PAGE_W - text_width(data, size, bold)) / 2
        font = b"/F2" if bold else b"/F1"
        self.pages[-1].append(
            b"BT %s %.1f Tf %.2f %.2f Td (%s) Tj ET" % (font, size, x, self.y + size * 0.25,
                                                         _escape(data)))

    def rule(self) -> None:
        self.y -= 3
        self.pages[-1].append(b"0.5 w %.2f %.2f m %.2f %.2f l S"
                              % (MARGIN, self.y, PAGE_W - MARGIN, self.y))
        self.y -= 4

    def paragraph(self, data: bytes, size: float, bold: bool = False,
                  indent: float = 0.0, bullet: bool = False) -> None:
        lines = wrap(data, size, WIDTH - indent, bold)
        for n, line in enumerate(lines):
            if bullet and n == 0:
                self._room(size * 1.25)
                self.pages[-1].append(b"BT /F1 %.1f Tf %.2f %.2f Td (\x95) Tj ET"
                                      % (size, MARGIN + indent - 9, self.y - size))
            self.text(line, size, bold, x=MARGIN + indent)


_BOLD_MARKS = re.compile(r"\*\*(.+?)\*\*")


def render(markdown: str, title: str = "Resume") -> bytes:
    """The resume template's Markdown as PDF bytes."""
    pages = _Pages()
    contact_next = False
    for raw in markdown.splitlines():
        line = _BOLD_MARKS.sub(r"\1", raw.rstrip())
        if not line.strip():
            continue
        if line.startswith("# "):
            pages.text(to_winansi(line[2:].strip()), 18, bold=True, centre=True)
            contact_next = True
            continue
        if contact_next and not line.startswith("#"):
            for part in wrap(to_winansi(line.strip()), 10, WIDTH):
                pages.text(part, 10, centre=True)
            contact_next = False
            continue
        contact_next = False
        if line.startswith("## "):
            pages.gap(8)
            pages.keep(11 * 1.25 + 7 + 10.5 * 1.25 + 2 * 10 * 1.25)
            pages.text(to_winansi(line[3:].strip().upper()), 11, bold=True)
            pages.rule()
        elif line.startswith("### "):
            pages.gap(3)
            pages.keep(10.5 * 1.25 + 2 * 10 * 1.25)
            pages.paragraph(to_winansi(line[4:].strip()), 10.5, bold=True)
        elif re.match(r"^\s*[-*] ", line):
            pages.paragraph(to_winansi(re.sub(r"^\s*[-*] ", "", line)), 10,
                            indent=14, bullet=True)
        else:
            pages.paragraph(to_winansi(line.strip()), 10)
    return _assemble(pages.pages, title)


def _assemble(pages: list[list[bytes]], title: str) -> bytes:
    """The PDF file: catalogue, pages, two standard fonts, compressed content."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")                         # filled in once the pages exist
    pages_id = add(b"")
    regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                  b"/Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
               b"/Encoding /WinAnsiEncoding >>")
    kids = []
    for ops in pages:
        stream = zlib.compress(b"\n".join(ops))
        content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream"
                      % (len(stream), stream))
        kids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, PAGE_W, PAGE_H, regular, bold, content)))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    objects[pages_id - 1] = (b"<< /Type /Pages /Kids [%s] /Count %d >>"
                             % (b" ".join(b"%d 0 R" % k for k in kids), len(kids)))
    info = add(b"<< /Title (%s) /Producer (jobdork) >>" % _escape(to_winansi(title)))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog, info, xref))
    return bytes(out)
