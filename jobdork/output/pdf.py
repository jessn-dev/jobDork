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
(writing/resume_doc.py): Arial's equal at 10 points (Indeed: 10 to 12), the
name at 20, 0.5 inch margins, headings in dark blue over a thin rule. The
person preferred that look to the larger, plainer template's: more fits on
a page, and the sections stand apart (2026-11-12).

    # Name                        centred, bold
    **Headline**                  centred, bold, dark blue
    Phone | Email | Location      centred
    ## SECTION                    bold capitals, dark blue, a rule under it
    ### Job title<TAB>dates       bold, the dates at the right margin
    Company, City                 plain line
    - bullet
    anything else                 a paragraph
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from functools import lru_cache

PAGE_W, PAGE_H = 612.0, 792.0            # US Letter, in points
MARGIN = 36.0                             # 0.5 inch
BODY = 10.0                               # points (Indeed: 10 to 12)
NAME = 20.0
# Headings and the headline: a dark blue that prints as near-black in grey.
ACCENT = b"0.122 0.306 0.475"
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


class Face:
    """A font pair (regular, bold) as the layout measures it: each byte's
    width per 1000 units, and for an embedded font the files to embed."""

    def __init__(self, regular: list[float], bold: list[float], names=(b"Helvetica",
                 b"Helvetica-Bold"), files: tuple[str, str] | None = None):
        self.widths = {False: regular, True: bold}
        self.names, self.files = names, files


def _standard(table: list[int]) -> list[float]:
    return [table[b - 32] if 32 <= b <= 126 else _WIDE for b in range(256)]


HELVETICA = Face(_standard(_REGULAR), _standard(_BOLD))
# Source Sans 3 (Adobe, SIL Open Font License, jobdork/data/fonts): what a
# resume is set in. A person preferred a resume in Aptos, Microsoft's font,
# which cannot be shipped; Source Sans 3 is free and reads much the same
# (2026-11-12). Embedded, cut down to the glyphs a resume uses (output/ttf.py).
SANS_FILES = ("SourceSans3-Regular.ttf", "SourceSans3-Bold.ttf")
_SANS: Face | None = None


def sans() -> Face:
    """Source Sans 3 with its own widths; Helvetica if its files are missing."""
    global _SANS
    if _SANS is None:
        from . import ttf
        try:
            fonts = [ttf.load(name) for name in SANS_FILES]
        except (OSError, ttf.FontError):
            return HELVETICA
        widths = [[f.advance(bytes([b]).decode("cp1252", "replace")) if b >= 32 else 0.0
                   for b in range(256)] for f in fonts]
        _SANS = Face(widths[0], widths[1], (b"SourceSans3-Regular", b"SourceSans3-Bold"),
                     SANS_FILES)
    return _SANS


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


def text_width(data: bytes, size: float, bold: bool = False, face: Face = HELVETICA) -> float:
    table = face.widths[bold]
    return sum(table[b] for b in data) * size / 1000


def wrap(data: bytes, size: float, width: float, bold: bool = False,
         face: Face = HELVETICA) -> list[bytes]:
    """Greedy word wrap; a word longer than the line is split where it must be."""
    lines, line = [], b""
    for word in data.split():
        trial = line + b" " + word if line else word
        if text_width(trial, size, bold, face) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        while text_width(word, size, bold, face) > width:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, bold, face) > width:
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

    def __init__(self, face: Face = HELVETICA) -> None:
        self.pages: list[list[bytes]] = [[]]
        self.y = PAGE_H - MARGIN
        self.face = face

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
             centre: bool = False, accent: bool = False) -> None:
        lead = size * 1.25
        self._room(lead)
        self.y -= lead
        if centre:
            x = (PAGE_W - text_width(data, size, bold, self.face)) / 2
        font = b"/F2" if bold else b"/F1"
        colour = ACCENT + b" rg " if accent else b""
        self.pages[-1].append(
            b"BT %s%s %.1f Tf %.2f %.2f Td (%s) Tj ET%s"
            % (colour, font, size, x, self.y + size * 0.25, _escape(data),
               b" 0 g" if accent else b""))

    def rule(self) -> None:
        """A thin line across the text width, just under the line written last."""
        y = self.y - 2
        self.pages[-1].append(b"%s RG 0.6 w %.2f %.2f m %.2f %.2f l S 0 G"
                              % (ACCENT, MARGIN, y, PAGE_W - MARGIN, y))

    def dated(self, heading: str, size: float) -> None:
        """A bold heading with its dates (after a tab) at the right margin;
        the dates go on a line of their own when the heading fills it."""
        left, _, right = heading.partition("\t")
        left_b, right_b = to_winansi(left.strip()), to_winansi(right.strip())
        room = WIDTH - (text_width(right_b, size, True, self.face) + 12 if right_b else 0)
        lines = wrap(left_b, size, room, bold=True, face=self.face) or [b""]
        for n, line in enumerate(lines):
            self.text(line, size, bold=True)
            if n == 0 and right_b:
                self.pages[-1].append(
                    b"BT /F2 %.1f Tf %.2f %.2f Td (%s) Tj ET"
                    % (size, PAGE_W - MARGIN - text_width(right_b, size, True, self.face),
                       self.y + size * 0.25, _escape(right_b)))

    def _bullet(self, size: float, indent: float) -> None:
        self._room(size * 1.25)
        self.pages[-1].append(b"BT /F1 %.1f Tf %.2f %.2f Td (\x95) Tj ET"
                              % (size, MARGIN + indent - 9, self.y - size))

    def paragraph(self, data: bytes, size: float, bold: bool = False,
                  indent: float = 0.0, bullet: bool = False) -> None:
        lines = wrap(data, size, WIDTH - indent, bold, self.face)
        for n, line in enumerate(lines):
            if bullet and n == 0:
                self._bullet(size, indent)
            self.text(line, size, bold, x=MARGIN + indent)

    def rich(self, runs: list[tuple[bytes, bool]], size: float, indent: float = 0.0,
             bullet: bool = False) -> None:
        """A paragraph with bold words in it ("**Cloud:** Azure, GCP"):
        wrapped word by word, each measured in its own weight, and written
        line by line as one text object that switches font where it must,
        so a tracking system reads it in order."""
        # (word, bold, a space before it): "**Developer**, Acme" has none
        # between "Developer" and its comma.
        words: list[tuple[bytes, bool, bool]] = []
        gap = False
        for text, bold in runs:
            for n, w in enumerate(text.split()):
                words.append((w, bold, n > 0 or gap or text[:1].isspace()))
            gap = text[-1:].isspace()
        lines: list[list[tuple[bytes, bool, bool]]] = [[]]
        used, room = 0.0, WIDTH - indent
        for word, bold, spaced in words:
            space = text_width(b" ", size, bold, self.face) if lines[-1] and spaced else 0.0
            width = text_width(word, size, bold, self.face)
            if lines[-1] and used + space + width > room:
                lines.append([])
                used, space = 0.0, 0.0
            lines[-1].append((word, bold, spaced))
            used += space + width
        for n, line in enumerate(lines):
            if bullet and n == 0:
                self._bullet(size, indent)
            lead = size * 1.25
            self._room(lead)
            self.y -= lead
            ops, last = [], None
            for k, (word, bold, spaced) in enumerate(line):
                if bold != last:
                    ops.append(b"%s %.1f Tf" % (b"/F2" if bold else b"/F1", size))
                    last = bold
                ops.append(b"(%s) Tj" % _escape((b" " if k and spaced else b"") + word))
            self.pages[-1].append(b"BT %.2f %.2f Td %s ET"
                                  % (MARGIN + indent, self.y + size * 0.25, b" ".join(ops)))


_BOLD_MARKS = re.compile(r"\*\*(.+?)\*\*")


def _runs(text: str) -> list[tuple[bytes, bool]]:
    """"**Cloud:** Azure" as (text, bold) pieces."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    return [(to_winansi(p), n % 2 == 1) for n, p in enumerate(parts) if p]


def render(markdown: str, title: str = "Resume", font: str = "sans") -> bytes:
    """The resume template's Markdown as PDF bytes, in Source Sans 3 (embedded)
    or, for `font="serif"`, Times. A serif line is measured with Helvetica's
    widths: Times is narrower, so it wraps a little early and never runs past
    the margin."""
    face = HELVETICA if font == "serif" else sans()
    pages = _Pages(face)
    header = False
    for raw in markdown.splitlines():
        line = _BOLD_MARKS.sub(r"\1", raw.rstrip())
        if not line.strip():
            continue
        if line.startswith("# "):
            pages.text(to_winansi(line[2:].strip()), NAME, bold=True, centre=True)
            header = True
            continue
        if header and not line.startswith("#"):
            # The headline (bold in the Markdown), then the contact line, centred.
            headline = raw.strip().startswith("**") and raw.strip().endswith("**")
            for part in wrap(to_winansi(line.strip()), BODY, WIDTH, bold=headline, face=face):
                pages.text(part, BODY + (0.5 if headline else 0), bold=headline,
                           centre=True, accent=headline)
            continue
        header = False
        if line.startswith("## "):
            pages.gap(8)
            pages.keep(3 * BODY * 1.25 + 8)
            pages.text(to_winansi(line[3:].strip().upper()), BODY + 0.5, bold=True,
                       accent=True)
            pages.rule()
            pages.gap(5)
        elif line.startswith("### "):
            pages.gap(4)
            pages.keep(3 * BODY * 1.25)
            pages.dated(line[4:].strip(), BODY)
        elif re.match(r"^\s*[-*] ", line):
            text = re.sub(r"^\s*[-*] ", "", raw.rstrip())
            if "**" in text:
                pages.rich(_runs(text), BODY, indent=18, bullet=True)
            else:
                pages.paragraph(to_winansi(text), BODY, indent=18, bullet=True)
        elif "**" in raw:
            pages.rich(_runs(raw.strip()), BODY)
        else:
            pages.paragraph(to_winansi(line.strip()), BODY)
    return _assemble(pages.pages, title, font, face)


def page_count(data: bytes) -> int:
    """How many pages a PDF this module wrote has."""
    found = re.search(rb"/Type /Pages /Kids \[[^\]]*\] /Count (\d+)", data)
    return int(found.group(1)) if found else 0


# Every character the PDF can show (to_winansi): the glyphs a subset keeps.
WINANSI = "".join(bytes([b]).decode("cp1252", "ignore") for b in range(32, 256))


@lru_cache(maxsize=4)
def _font_file(name: str) -> tuple[bytes, int]:
    """The subset of a shipped font, compressed, and its length before."""
    from . import ttf
    raw = ttf.load(name).subset(WINANSI)
    return zlib.compress(raw, 9), len(raw)


def _embedded_font(add, name: str, base: bytes, tag: bytes, widths: list[float]) -> int:
    """A TrueType font embedded as a subset: its file, descriptor and widths.
    The name carries a six-letter tag, as the PDF standard asks of a subset."""
    from . import ttf
    font = ttf.load(name)
    data, length = _font_file(name)
    scale = 1000 / font.units
    stream = add(b"<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n%s\nendstream"
                 % (len(data), length, data))
    x0, y0, x1, y1 = (round(v * scale) for v in font.bbox)
    descriptor = add(
        b"<< /Type /FontDescriptor /FontName /%s+%s /Flags 32 /FontBBox [%d %d %d %d] "
        b"/ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d /StemV 80 /FontFile2 %d 0 R >>"
        % (tag, base, x0, y0, x1, y1, round(font.ascent * scale),
           round(font.descent * scale), round(font.cap_height * scale), stream))
    return add(b"<< /Type /Font /Subtype /TrueType /BaseFont /%s+%s /FirstChar 32 "
               b"/LastChar 255 /Widths [%s] /Encoding /WinAnsiEncoding "
               b"/FontDescriptor %d 0 R >>"
               % (tag, base, b" ".join(b"%d" % round(w) for w in widths[32:]), descriptor))


def _assemble(pages: list[list[bytes]], title: str, font: str = "sans",
              face: Face = HELVETICA) -> bytes:
    """The PDF file: catalogue, pages, two fonts, compressed content."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")                         # filled in once the pages exist
    pages_id = add(b"")
    if face.files:
        regular = _embedded_font(add, face.files[0], face.names[0], b"JDKSAA",
                                 face.widths[False])
        bold = _embedded_font(add, face.files[1], face.names[1], b"JDKSAB",
                              face.widths[True])
    else:
        name, heavy = (b"Times-Roman", b"Times-Bold") if font == "serif" else face.names
        regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                      b"/Encoding /WinAnsiEncoding >>" % name)
        bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                   b"/Encoding /WinAnsiEncoding >>" % heavy)
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
