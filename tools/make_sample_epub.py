#!/usr/bin/env python3
"""Write a small sample EPUB for tests: python3 tools/make_sample_epub.py out.epub [chapters] [--ncx] [--no-toc]

Each chapter has a heading, a "Topic" section and a few paragraphs, with
a cover image on the first. EPUB 3 with a nav document by default; --ncx
writes an EPUB 2 table of contents (toc.ncx) instead, --no-toc neither.
Only the standard library is used.
"""

from __future__ import annotations

import struct
import sys
import zipfile
import zlib
from pathlib import Path



def _png(w: int = 40, h: int = 30) -> bytes:
    """A small solid red PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + b"\xcc\x22\x22" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


WORDS = ("the quick brown fox jumps over the lazy dog while students read and remember their books "
         "with highlights notes and bookmarks on every page of the chapter").split()


def paragraph(ch: int, n: int) -> str:
    words = [WORDS[(ch * 7 + n * 3 + i) % len(WORDS)] for i in range(60)]
    return f"<p>Paragraph {n} of chapter {ch}: " + " ".join(words) + ".</p>"


def chapter(ch: int, paragraphs: int) -> str:
    body = [f'<h1 id="start">Chapter {ch}: Topic {ch}</h1>']
    if ch == 1:
        body.append('<div><img src="../images/cover.png" alt="cover"/></div>')
    body += [paragraph(ch, n) for n in range(1, paragraphs + 1)]
    body.append(f'<h2 id="more">More about topic {ch}</h2>')
    body += [paragraph(ch, n) for n in range(paragraphs + 1, 2 * paragraphs + 1)]
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title>'
        '<style>p { color: red; }</style></head>'
        f'<body>{"".join(body)}<p>See <a href="ch{ch}.xhtml#more">more</a>.</p></body></html>'
    )


def build(out: Path, chapters: int = 3, *, toc: str = "nav", paragraphs: int = 12, title: str = "Sample Book",
          identifier: str = "urn:uuid:12345678-dog-ear-sample") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = ['<item id="cover" href="images/cover.png" media-type="image/png"/>']
    spine = []
    for ch in range(1, chapters + 1):
        manifest.append(f'<item id="ch{ch}" href="text/ch{ch}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="ch{ch}"/>')
    if toc == "nav":
        manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    if toc == "ncx":
        manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    spine_attr = ' toc="ncx"' if toc == "ncx" else ""
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="uid">{identifier}</dc:identifier><dc:title>{title}</dc:title>'
        '<dc:creator>Dogear Tests</dc:creator><dc:language>en</dc:language></metadata>'
        f'<manifest>{"".join(manifest)}</manifest>'
        f'<spine{spine_attr}>{"".join(spine)}</spine></package>'
    )
    items = "".join(
        f'<li><a href="text/ch{ch}.xhtml">Chapter {ch}: Topic {ch}</a>'
        f'<ol><li><a href="text/ch{ch}.xhtml#more">More about topic {ch}</a></li></ol></li>'
        for ch in range(1, chapters + 1)
    )
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head>'
        f'<body><nav epub:type="toc"><h1>Contents</h1><ol>{items}</ol></nav></body></html>'
    )
    points = "".join(
        f'<navPoint id="p{ch}"><navLabel><text>Chapter {ch}: Topic {ch} ........ {ch * 3}</text></navLabel>'
        f'<content src="text/ch{ch}.xhtml"/>'
        f'<navPoint id="p{ch}m"><navLabel><text>More about topic {ch}</text></navLabel>'
        f'<content src="text/ch{ch}.xhtml#more"/></navPoint></navPoint>'
        for ch in range(1, chapters + 1)
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<navMap>{points}</navMap></ncx>'
    )
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")  # stored, first
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            compress_type=zipfile.ZIP_DEFLATED,
        )
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/images/cover.png", _png())
        for ch in range(1, chapters + 1):
            z.writestr(f"OEBPS/text/ch{ch}.xhtml", chapter(ch, paragraphs), compress_type=zipfile.ZIP_DEFLATED)
        if toc == "nav":
            z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        if toc == "ncx":
            z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        sys.exit(__doc__)
    kind = "ncx" if "--ncx" in flags else "none" if "--no-toc" in flags else "nav"
    build(Path(args[0]), int(args[1]) if len(args) > 1 else 3, toc=kind)
