"""
jobdork.output.ttf
==================
A TrueType font read just far enough to set a resume in it: the advance
width of each character, and a copy of the font cut down to the glyphs a
resume can use, for embedding in the PDF (output/pdf.py).

Written here rather than taken from a library, as the PDF itself is: the
whole job is reading five tables and copying a few others. A font library
would be one more package to lock, scan and keep patched in the installers.

**Why cut it down.** Source Sans 3, the font a resume is set in, is 430 KB a
weight; embedded whole, a two-page resume would be close to a megabyte. The
PDF can only show the characters of Windows-1252 (pdf.to_winansi), so every
other glyph is emptied (its slot kept, so glyph numbers do not move) and the
tables only typesetting software reads (GSUB, GPOS and the like) are left
out. A subset embedded in a document is what the font's licence, the SIL Open
Font License, allows: the font file itself is shipped unchanged.
"""

from __future__ import annotations

import struct
from functools import lru_cache
from pathlib import Path

# What a PDF viewer needs of an embedded TrueType font, and what it may use.
# The rest (GSUB, GPOS, GDEF, BASE, DSIG, STAT...) is for typesetting.
KEEP = (b"OS/2", b"cmap", b"cvt ", b"fpgm", b"gasp", b"glyf", b"head", b"hhea",
        b"hmtx", b"loca", b"maxp", b"name", b"post", b"prep")


class FontError(Exception):
    """A font file jobdork cannot read."""


def _checksum(data: bytes) -> int:
    data += b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


class TrueType:
    """One TrueType font file: its metrics, and a subset of it to embed."""

    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        if self.data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            raise FontError(f"{path.name} is not a TrueType font")
        count = struct.unpack(">H", self.data[4:6])[0]
        self.tables: dict[bytes, tuple[int, int]] = {}
        for n in range(count):
            tag, _sum, offset, length = struct.unpack(
                ">4sIII", self.data[12 + 16 * n:28 + 16 * n])
            self.tables[tag] = (offset, length)
        head = self._table(b"head")
        self.units = struct.unpack(">H", head[18:20])[0]
        self.long_loca = struct.unpack(">h", head[50:52])[0] == 1
        self.ascent, self.descent = struct.unpack(">hh", self._table(b"hhea")[4:8])
        self.bbox = struct.unpack(">hhhh", head[36:44])
        os2 = self._table(b"OS/2") if b"OS/2" in self.tables else b""
        self.cap_height = (struct.unpack(">h", os2[88:90])[0] if len(os2) >= 90
                           else self.ascent)
        self.glyphs = struct.unpack(">H", self._table(b"maxp")[4:6])[0]
        self._metrics = self._read_hmtx()
        self.cmap = self._read_cmap()

    def _table(self, tag: bytes) -> bytes:
        if tag not in self.tables:
            raise FontError(f"{self.path.name} has no {tag.decode()} table")
        offset, length = self.tables[tag]
        return self.data[offset:offset + length]

    def _read_hmtx(self) -> list[int]:
        count = struct.unpack(">H", self._table(b"hhea")[34:36])[0]
        hmtx = self._table(b"hmtx")
        widths = [struct.unpack(">H", hmtx[4 * n:4 * n + 2])[0] for n in range(count)]
        # Glyphs past the last full metric share its width.
        return widths + [widths[-1]] * (self.glyphs - count)

    def _read_cmap(self) -> dict[int, int]:
        """Unicode to glyph, from the Windows Unicode (3, 1) format 4 subtable."""
        cmap = self._table(b"cmap")
        count = struct.unpack(">H", cmap[2:4])[0]
        for n in range(count):
            platform, encoding, offset = struct.unpack(">HHI", cmap[4 + 8 * n:12 + 8 * n])
            if (platform, encoding) == (3, 1) and \
                    struct.unpack(">H", cmap[offset:offset + 2])[0] == 4:
                return self._format4(cmap, offset)
        raise FontError(f"{self.path.name} has no Unicode character map")

    @staticmethod
    def _format4(cmap: bytes, at: int) -> dict[int, int]:
        segments = struct.unpack(">H", cmap[at + 6:at + 8])[0] // 2
        ends_at = at + 14
        starts_at = ends_at + 2 * segments + 2
        deltas_at = starts_at + 2 * segments
        ranges_at = deltas_at + 2 * segments

        def word(pos: int) -> int:
            return struct.unpack(">H", cmap[pos:pos + 2])[0]

        out = {}
        for s in range(segments):
            end, start = word(ends_at + 2 * s), word(starts_at + 2 * s)
            delta, rng = word(deltas_at + 2 * s), word(ranges_at + 2 * s)
            for code in range(start, min(end, 0xFFFE) + 1):
                if rng:
                    pos = ranges_at + 2 * s + rng + 2 * (code - start)
                    glyph = word(pos)
                    glyph = (glyph + delta) & 0xFFFF if glyph else 0
                else:
                    glyph = (code + delta) & 0xFFFF
                if glyph:
                    out[code] = glyph
        return out

    def advance(self, char: str) -> float:
        """A character's width in thousandths of the font size, as PDF counts."""
        glyph = self.cmap.get(ord(char), 0)
        return self._metrics[glyph] * 1000 / self.units

    def _offsets(self) -> list[int]:
        loca = self._table(b"loca")
        if self.long_loca:
            return list(struct.unpack(f">{self.glyphs + 1}I", loca[:4 * (self.glyphs + 1)]))
        return [2 * x for x in struct.unpack(f">{self.glyphs + 1}H",
                                             loca[:2 * (self.glyphs + 1)])]

    def subset(self, chars: str) -> bytes:
        """The font with every glyph but those of `chars` (and .notdef, and
        the parts a composite glyph is built from) emptied, and only KEEP's
        tables: a file to embed in a PDF."""
        glyf, offsets = self._table(b"glyf"), self._offsets()
        wanted = {0} | {self.cmap[ord(c)] for c in chars if ord(c) in self.cmap}
        todo = list(wanted)
        while todo:                               # composites name their parts
            g = todo.pop()
            body = glyf[offsets[g]:offsets[g + 1]]
            if len(body) < 10 or struct.unpack(">h", body[:2])[0] >= 0:
                continue
            pos = 10
            while True:
                flags, part = struct.unpack(">HH", body[pos:pos + 4])
                if part not in wanted:
                    wanted.add(part)
                    todo.append(part)
                pos += 4 + (4 if flags & 0x0001 else 2)
                pos += 8 if flags & 0x0080 else 4 if flags & 0x0040 else 2 if flags & 0x0008 else 0
                if not flags & 0x0020:
                    break
        new_glyf, new_loca = bytearray(), []
        for g in range(self.glyphs):
            new_loca.append(len(new_glyf))
            if g in wanted:
                new_glyf += glyf[offsets[g]:offsets[g + 1]]
                new_glyf += b"\0" * (-len(new_glyf) % 4)
        new_loca.append(len(new_glyf))
        head = bytearray(self._table(b"head"))
        head[8:12] = b"\0\0\0\0"                  # checkSumAdjustment, set below
        head[50:52] = struct.pack(">h", 1)        # long offsets in loca
        tables = {tag: self._table(tag) for tag in KEEP if tag in self.tables}
        tables[b"glyf"] = bytes(new_glyf)
        tables[b"loca"] = struct.pack(f">{len(new_loca)}I", *new_loca)
        tables[b"head"] = bytes(head)
        # Version 3: no glyph names, which a PDF never needs.
        tables[b"post"] = struct.pack(">I", 0x00030000) + self._table(b"post")[4:32]
        return _assemble(tables)


def _assemble(tables: dict[bytes, bytes]) -> bytes:
    """A font file from its tables, with their checksums and the font's."""
    tags = sorted(tables)
    count = len(tags)
    power = 1 << (count.bit_length() - 1)
    out = bytearray(struct.pack(">IHHHH", 0x00010000, count, power * 16,
                                power.bit_length() - 1, count * 16 - power * 16))
    offset = 12 + 16 * count
    body = bytearray()
    for tag in tags:
        data = tables[tag]
        out += struct.pack(">4sIII", tag, _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    font = bytearray(out + body)
    head_at = struct.unpack(">I", font[12 + 16 * tags.index(b"head") + 8:][:4])[0]
    font[head_at + 8:head_at + 12] = struct.pack(">I", (0xB1B0AFBA - _checksum(bytes(font)))
                                                 & 0xFFFFFFFF)
    return bytes(font)


FONTS = Path(__file__).resolve().parent.parent / "data" / "fonts"


@lru_cache(maxsize=4)
def load(name: str) -> TrueType:
    """A font shipped in jobdork/data/fonts, read once."""
    return TrueType(FONTS / name)
