"""
jobdork.output.docx
===================
A resume as a Word document (.docx), laid out as the PDF is: the template
of writing/resume_doc.py, after Indeed's free resume template (nothing of its
file is copied; the layout is rebuilt here).

Written here rather than with a library, as the PDF is: a .docx is a zip of
a few XML files, and a resume needs one column of paragraphs, bold runs, a
tab stop for the dates and one bullet list. A library for that is one more
package to lock and scan in the installers.

**What an applicant tracking system needs, it gets:** real paragraphs in
reading order, no tables, no text boxes, no headers or footers, the contact
lines in the body. Arial 11 point, the name at 18, 0.7 inch margins, US
Letter, the dates at the right margin. Unlike the PDF, any script is kept as
it is: Word draws it with the fonts the reader's computer has.

Input is the same small Markdown (see output/pdf.py).
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from xml.sax.saxutils import escape

# Twentieths of a point: US Letter, 0.7 inch margins (1008), the text width
# between them, where the dates' right-aligned tab stop goes.
PAGE_W, PAGE_H, MARGIN = 12240, 15840, 1008
TEXT_W = PAGE_W - 2 * MARGIN
BODY, NAME = 22, 36                       # half-points: 11 and 18

_BOLD_MARKS = re.compile(r"\*\*(.+?)\*\*")
# Characters XML 1.0 cannot carry at all; a resume never needs them.
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _text(value: str) -> str:
    return escape(_NOT_XML.sub("", value))


# On every run as well as in the defaults: a lesser reader (macOS Quick Look)
# ignores the defaults and shows Times.
_FONT = '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial"/>'


def _run(text: str, bold: bool = False, size: int = 0) -> str:
    size = size or BODY
    props = f'{_FONT}{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{_text(text)}</w:t></w:r>'


def _tab() -> str:
    return f"<w:r><w:rPr>{_FONT}<w:b/></w:rPr><w:tab/></w:r>"


def _para(runs: str, *, centre: bool = False, before: int = 0, after: int = 0,
          tab: bool = False, bullet: bool = False, keep: bool = False) -> str:
    props = []
    if bullet:
        props.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
    if keep:
        props.append("<w:keepNext/>")
    if tab:
        props.append(f'<w:tabs><w:tab w:val="right" w:pos="{TEXT_W}"/></w:tabs>')
    props.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="240" '
                 'w:lineRule="auto"/>')
    if centre:
        props.append('<w:jc w:val="center"/>')
    return f"<w:p><w:pPr>{''.join(props)}</w:pPr>{runs}</w:p>"


def _body(markdown: str) -> str:
    out: list[str] = []
    header = False
    for raw in markdown.splitlines():
        line = _BOLD_MARKS.sub(r"\1", raw.rstrip())
        if not line.strip():
            continue
        if line.startswith("# "):
            out.append(_para(_run(line[2:].strip(), bold=True, size=NAME), centre=True))
            header = True
            continue
        if header and not line.startswith("#"):
            out.append(_para(_run(line.strip()), centre=True))
            continue
        header = False
        if line.startswith("## "):
            out.append(_para(_run(line[3:].strip().upper(), bold=True),
                             before=180, after=80, keep=True))
        elif line.startswith("### "):
            left, _, right = line[4:].strip().partition("\t")
            runs = _run(left.strip(), bold=True)
            if right.strip():
                runs += _tab() + _run(right.strip(), bold=True)
            out.append(_para(runs, before=80, tab=True, keep=True))
        elif re.match(r"^\s*[-*] ", line):
            out.append(_para(_run(re.sub(r"^\s*[-*] ", "", line)), bullet=True))
        else:
            out.append(_para(_run(line.strip())))
    return "".join(out)


_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _document(markdown: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f"<w:document {_NS}><w:body>{_body(markdown)}"
            f'<w:sectPr><w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
            f'<w:pgMar w:top="{MARGIN}" w:right="{MARGIN}" w:bottom="{MARGIN}" '
            f'w:left="{MARGIN}" w:header="720" w:footer="720" w:gutter="0"/>'
            "</w:sectPr></w:body></w:document>")


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f"<w:styles {_NS}><w:docDefaults><w:rPrDefault><w:rPr>{_FONT}"
    f'<w:sz w:val="{BODY}"/><w:szCs w:val="{BODY}"/><w:lang w:val="en-US"/>'
    "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
    '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:qFormat/></w:style></w:styles>')

_NUMBERING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:numbering {_NS}><w:abstractNum w:abstractNumId="0">'
    '<w:multiLevelType w:val="hybridMultilevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
    '<w:lvlText w:val="●"/><w:lvlJc w:val="left"/>'
    '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>'
    '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/></w:rPr></w:lvl>'
    '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    "</w:numbering>")

_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.numbering+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-'
    'package.core-properties+xml"/>'
    "</Types>")

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/'
    'relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    "</Relationships>")

_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/numbering" Target="numbering.xml"/>'
    "</Relationships>")


def _core(title: str) -> str:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
            'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{_text(title)}</dc:title><dc:creator>jobdork</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            "</cp:coreProperties>")


def render(markdown: str, title: str = "Resume") -> bytes:
    """The resume template's Markdown as the bytes of a .docx file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", _document(markdown))
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/numbering.xml", _NUMBERING)
        z.writestr("docProps/core.xml", _core(title))
    return buffer.getvalue()
