"""EPUB books, read by laying them out once as a PDF.

Everything Dogear does (highlights by position, answer lines found in the
pixels, search, export by page) works on fixed pages. An EPUB has none, so
the first time a book is opened its chapters are set in pages with Qt's own
text layout (QTextDocument) and written out as a PDF: the book's
"rendition". Dogear then reads the rendition like any other PDF, while the
marks belong to the EPUB (they are keyed by the EPUB's hash).

The rendition is made once and kept in the library folder
(.dogear/renditions/<sha256>.pdf), so it syncs with the marks: a second
computer shows the same pages and the marks land on the same words, even if
its fonts differ. It is never made again for the same book, because marks
are positions on its pages.

The publisher's stylesheets are not used: QTextDocument understands only a
little CSS, and books read better in one plain, consistent style. Inline
styles in the text are kept. There is no network access: only files inside
the EPUB are read.
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urldefrag
from xml.etree import ElementTree as ET

from .fsutil import atomic_write_text

log = logging.getLogger(__name__)

# The layout of renditions made by this version. Stored with each rendition
# for the record; an existing rendition is never remade (marks sit on it).
LAYOUT_VERSION = 1

# A 6 × 9 in page (a trade paperback), in points.
PAGE_W, PAGE_H = 432.0, 648.0
MARGIN = 54.0
BODY_PT = 11.0

STYLE = f"""
body {{ font-family: serif; font-size: {BODY_PT}pt; }}
p {{ margin-top: 0; margin-bottom: 0.5em; }}
h1 {{ font-size: 20pt; font-weight: bold; margin-top: 0.6em; margin-bottom: 0.8em; }}
h2 {{ font-size: 16pt; font-weight: bold; margin-top: 0.8em; margin-bottom: 0.6em; }}
h3 {{ font-size: 13.5pt; font-weight: bold; margin-top: 0.8em; margin-bottom: 0.5em; }}
h4, h5, h6 {{ font-size: {BODY_PT}pt; font-weight: bold; margin-top: 0.8em; margin-bottom: 0.4em; }}
blockquote {{ margin-left: 18pt; margin-right: 18pt; }}
pre, code {{ font-family: monospace; font-size: 9.5pt; }}
table {{ border-collapse: collapse; }}
td, th {{ padding: 2pt; }}
"""

_NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "x": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}
_IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/svg+xml", "image/webp", "image/bmp")


class EpubError(Exception):
    """The file isn't an EPUB Dogear can read."""


def is_epub(path: Path) -> bool:
    """An EPUB by its name, or by its contents (a zip whose `mimetype` says so)."""
    if path.suffix.lower() == ".epub":
        return True
    try:
        with zipfile.ZipFile(path) as z:
            return z.read("mimetype").strip() == b"application/epub+zip"
    except (OSError, KeyError, zipfile.BadZipFile):
        return False


@dataclass
class Book:
    title: str = ""
    author: str = ""
    identifier: str = ""
    # Spine items in reading order: (zip path, media type).
    spine: list[tuple[str, str]] = field(default_factory=list)
    # The book's table of contents: {"title", "level", "href"} with href a
    # zip path and maybe "#fragment".
    toc: list[dict] = field(default_factory=list)
    media: dict[str, str] = field(default_factory=dict)  # zip path -> media type


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _join(base_dir: str, href: str) -> str:
    """A zip path for `href` relative to a file in `base_dir`; keeps a #fragment."""
    href, frag = urldefrag(href)
    path = posixpath.normpath(posixpath.join(base_dir, unquote(href))) if href else ""
    path = path.lstrip("/")
    return f"{path}#{frag}" if frag else path


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


_LEADER = re.compile(r"\s*(?:\.\s*){3,}\S*$")


def _title(el: ET.Element | None) -> str:
    """A contents entry's title without dot leaders and a page number."""
    return _LEADER.sub("", _text(el)).strip()


def read_book(z: zipfile.ZipFile) -> Book:
    """The package of an open EPUB: metadata, spine and table of contents."""
    try:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//c:rootfile", _NS)
        opf_path = rootfile.get("full-path") if rootfile is not None else None
        if not opf_path:
            raise EpubError("it has no package file")
        opf = ET.fromstring(z.read(opf_path))
    except KeyError as exc:
        raise EpubError(f"{exc.args[0]} is missing") from exc
    except ET.ParseError as exc:
        raise EpubError(f"its package file is damaged ({exc})") from exc
    base = posixpath.dirname(opf_path)
    book = Book()
    meta = opf.find("opf:metadata", _NS)
    if meta is not None:
        book.title = _text(meta.find("dc:title", _NS))
        book.author = _text(meta.find("dc:creator", _NS))
        uid = opf.get("unique-identifier")
        ids = meta.findall("dc:identifier", _NS)
        chosen = next((i for i in ids if uid and i.get("id") == uid), ids[0] if ids else None)
        book.identifier = _text(chosen)
    manifest: dict[str, tuple[str, str, str]] = {}  # id -> (path, media type, properties)
    for item in opf.iterfind("opf:manifest/opf:item", _NS):
        href = item.get("href")
        if not href:
            continue
        path = _join(base, href)
        media = item.get("media-type", "")
        manifest[item.get("id", "")] = (path, media, item.get("properties", ""))
        book.media[path] = media
    spine = opf.find("opf:spine", _NS)
    if spine is not None:
        for ref in spine.iterfind("opf:itemref", _NS):
            entry = manifest.get(ref.get("idref", ""))
            if entry and entry[1] in ("application/xhtml+xml", "text/html", "application/x-dtbook+xml", ""):
                book.spine.append((entry[0], entry[1]))
    if not book.spine:
        raise EpubError("it has no chapters")
    nav = next((p for p, _, props in manifest.values() if "nav" in props.split()), None)
    if nav:
        book.toc = _nav_toc(z, nav)
    if not book.toc and spine is not None:
        ncx = manifest.get(spine.get("toc", ""))
        ncx_path = ncx[0] if ncx else next((p for p, m, _ in manifest.values() if m == "application/x-dtbncx+xml"), None)
        if ncx_path:
            book.toc = _ncx_toc(z, ncx_path)
    return book


def _nav_toc(z: zipfile.ZipFile, path: str) -> list[dict]:
    try:
        root = ET.fromstring(z.read(path))
    except (KeyError, ET.ParseError):
        return []
    navs = [n for n in root.iter() if _local(n.tag) == "nav"]
    toc_nav = next((n for n in navs if n.get(f"{{{_NS['epub']}}}type", "").split().count("toc")), navs[0] if navs else None)
    if toc_nav is None:
        return []
    base = posixpath.dirname(path)
    out: list[dict] = []

    def walk(ol: ET.Element, level: int) -> None:
        for li in ol:
            if _local(li.tag) != "li":
                continue
            link = next((c for c in li if _local(c.tag) in ("a", "span")), None)
            href = link.get("href") if link is not None else None
            title = _title(link)
            if href and title:
                out.append({"title": title, "level": level, "href": _join(base, href)})
            for child in li:
                if _local(child.tag) == "ol":
                    walk(child, level + 1 if href and title else level)

    for child in toc_nav:
        if _local(child.tag) == "ol":
            walk(child, 0)
    return out


def _ncx_toc(z: zipfile.ZipFile, path: str) -> list[dict]:
    try:
        root = ET.fromstring(z.read(path))
    except (KeyError, ET.ParseError):
        return []
    base = posixpath.dirname(path)
    out: list[dict] = []

    def walk(parent: ET.Element, level: int) -> None:
        for point in parent.findall("ncx:navPoint", _NS):
            title = _title(point.find("ncx:navLabel/ncx:text", _NS))
            content = point.find("ncx:content", _NS)
            src = content.get("src") if content is not None else None
            if title and src:
                out.append({"title": title, "level": level, "href": _join(base, src)})
            walk(point, level + 1)

    nav_map = root.find("ncx:navMap", _NS)
    if nav_map is not None:
        walk(nav_map, 0)
    return out


# -- turning chapters into HTML that QTextDocument understands

_BODY = re.compile(r"<body\b[^>]*>(.*)</body\s*>", re.S | re.I)
_DROP = re.compile(r"<(script|style|head|title|svg:title)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_ATTR_ID = re.compile(r"""(\s)(id|name)\s*=\s*(["'])(.*?)\3""", re.S | re.I)
_ATTR_HREF = re.compile(r"""\shref\s*=\s*(["']).*?\1""", re.S | re.I)
_IMG = re.compile(r"<(img|image|svg:image)\b([^>]*?)/?>", re.S | re.I)
_SRC = re.compile(r"""(?:\s(?:src|xlink:href|href))\s*=\s*(["'])(.*?)\1""", re.S | re.I)
_SVG = re.compile(r"<svg\b[^>]*>(.*?)</svg\s*>", re.S | re.I)
# A chapter's anchors: dg<chapter>, and dg<chapter>-<id> for its ids.
_ANCHOR = "dg{}"


def _anchor(chapter: int, frag: str = "") -> str:
    base = _ANCHOR.format(chapter)
    return f"{base}-{re.sub(r'[^A-Za-z0-9_.-]', '_', frag)}" if frag else base


def chapter_html(raw: str, chapter: int, chapter_path: str, image_key) -> str:
    """The body of one chapter, ready to join with the others: ids made
    unique to the chapter, links unlinked (they can't be followed in the
    rendition) and images pointed at `image_key(zip path)`."""
    m = _BODY.search(raw)
    body = m.group(1) if m else raw
    body = _COMMENT.sub("", body)
    body = _DROP.sub("", body)
    base = posixpath.dirname(chapter_path)

    # An <svg> wrapping a single <image> (common for covers) becomes the image.
    def svg(mm: re.Match) -> str:
        inner = _IMG.search(mm.group(1))
        return f"<div>{inner.group(0)}</div>" if inner else ""

    body = _SVG.sub(svg, body)

    def img(mm: re.Match) -> str:
        src = _SRC.search(mm.group(2))
        if not src:
            return ""
        key = image_key(_join(base, unescape(src.group(2))).split("#", 1)[0])
        if not key:
            return ""
        alt = re.search(r"""\salt\s*=\s*(["'])(.*?)\1""", mm.group(2), re.S)
        alt_attr = f' alt="{alt.group(2)}"' if alt else ""
        return f'<img src="{key}"{alt_attr} />'

    body = _IMG.sub(img, body)
    body = _ATTR_HREF.sub("", body)
    body = _ATTR_ID.sub(lambda mm: f'{mm.group(1)}{mm.group(2)}="{_anchor(chapter, unescape(mm.group(4)))}"', body)
    return body


# -- the rendition


def rendition_paths(folder: Path, sha256: str) -> tuple[Path, Path]:
    return folder / f"{sha256}.pdf", folder / f"{sha256}.json"


def load_contents(meta: Path) -> list[dict] | None:
    """The table of contents saved with a rendition; None if unreadable."""
    try:
        raw = json.loads(meta.read_text(encoding="utf-8"))
        return [
            {"title": str(e["title"]), "level": int(e["level"]), "page": int(e["page"]), "y": float(e["y"])}
            for e in raw["contents"]
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def render(epub: Path, pdf_out: Path, meta_out: Path) -> dict:
    """Lay the EPUB out as a PDF at `pdf_out` and save its table of
    contents (with pages) and metadata to `meta_out`. Returns the metadata.
    Needs a QGuiApplication (fonts); runs on the UI thread."""
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF, QUrl
    from PySide6.QtGui import (
        QAbstractTextDocumentLayout,
        QImage,
        QPageLayout,
        QPageSize,
        QPainter,
        QPdfWriter,
        QTextDocument,
    )

    try:
        z = zipfile.ZipFile(epub)
    except (OSError, zipfile.BadZipFile) as exc:
        raise EpubError(f"it is not a valid EPUB ({exc})") from exc
    with z:
        names = set(z.namelist())
        if "META-INF/encryption.xml" in names:
            enc = z.read("META-INF/encryption.xml")
            # Font obfuscation is harmless; encrypted chapters are DRM.
            if b"http://www.idpf.org/2008/embedding" not in enc and b"http://ns.adobe.com/pdf/enc#RC" not in enc:
                raise EpubError("it is protected with DRM")
        book = read_book(z)

        doc = QTextDocument()
        writer = QPdfWriter(str(pdf_out))
        writer.setResolution(72)  # one unit is one point
        writer.setPageLayout(
            QPageLayout(QPageSize(QSizeF(PAGE_W, PAGE_H), QPageSize.Unit.Point, "Dogear", QPageSize.SizeMatchPolicy.ExactMatch),
                        QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
        )
        writer.setTitle(book.title or epub.stem)
        writer.setCreator("Dogear")
        doc.documentLayout().setPaintDevice(writer)
        doc.setDocumentMargin(MARGIN)
        doc.setPageSize(QSizeF(PAGE_W, PAGE_H))
        doc.setDefaultStyleSheet(STYLE)
        font = doc.defaultFont()
        font.setFamily("serif")
        font.setPointSizeF(BODY_PT)
        doc.setDefaultFont(font)

        content_w = PAGE_W - 2 * MARGIN
        max_h = (PAGE_H - 2 * MARGIN) * 0.9
        images: dict[str, str] = {}

        def image_key(path: str) -> str:
            if path in images:
                return images[path]
            key = ""
            if path in names and (book.media.get(path, "").startswith("image/") or path.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp"))):
                image = QImage()
                if image.loadFromData(z.read(path)) and not image.isNull():
                    # Fit the page; never enlarge (a small ornament stays small).
                    # Images are sized for screens at 96 dpi: 1 px = 0.75 pt.
                    w, h = image.width() * 0.75, image.height() * 0.75
                    scale = min(1.0, content_w / w, max_h / h)
                    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
                    image = image.scaled(round(tw * 2), round(th * 2), mode=_smooth()) if scale < 1 else image
                    key = f"dg-img-{len(images)}"
                    doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(key), image)
                    key = f'{key}" width="{tw}" height="{th}'
            images[path] = key
            return key

        parts = []
        for i, (path, _media) in enumerate(book.spine):
            try:
                raw = z.read(path).decode("utf-8", errors="replace")
            except KeyError:
                log.warning("%s: chapter %s is missing", epub.name, path)
                continue
            brk = "page-break-before: always; " if parts else ""
            parts.append(f'<p style="{brk}margin: 0;"><a name="{_anchor(i)}"></a></p>')
            parts.append(chapter_html(raw, i, path, image_key))
        doc.setHtml("<html><body>" + "\n".join(parts) + "</body></html>")

        layout = doc.documentLayout()
        pages = max(1, doc.pageCount())
        anchors = _anchor_positions(doc)
        contents = []
        chapter_of = {p: i for i, (p, _m) in enumerate(book.spine)}
        for entry in book.toc:
            path, _, frag = entry["href"].partition("#")
            if path not in chapter_of:
                continue
            ch = chapter_of[path]
            y = anchors.get(_anchor(ch, frag)) if frag else None
            if y is None:
                y = anchors.get(_anchor(ch))
            if y is None:
                continue
            page = min(pages - 1, int(y // PAGE_H))
            contents.append({"title": entry["title"], "level": entry["level"], "page": page,
                             "y": round(max(0.0, y - page * PAGE_H - 4), 2)})

        painter = QPainter()
        if not painter.begin(writer):
            raise OSError(f"{pdf_out} could not be written")
        try:
            for page in range(pages):
                if page:
                    writer.newPage()
                painter.save()
                painter.translate(0, -page * PAGE_H)
                ctx = QAbstractTextDocumentLayout.PaintContext()
                clip = QRectF(0, page * PAGE_H, PAGE_W, PAGE_H)
                ctx.clip = clip
                painter.setClipRect(clip)
                layout.draw(painter, ctx)
                painter.restore()
        finally:
            painter.end()

    meta = {
        "layout": LAYOUT_VERSION,
        "title": book.title,
        "author": book.author,
        "identifier": book.identifier,
        "pages": pages,
        "contents": contents,
    }
    atomic_write_text(meta_out, json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    return meta


def _smooth():
    from PySide6.QtCore import Qt

    return Qt.TransformationMode.SmoothTransformation


def _anchor_positions(doc) -> dict[str, float]:
    """The y (in document coordinates) of every named anchor."""
    out: dict[str, float] = {}
    layout = doc.documentLayout()
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                names = frag.charFormat().anchorNames()
                if names:
                    top = layout.blockBoundingRect(block).top()
                    line = block.layout().lineForTextPosition(frag.position() - block.position())
                    y = top + (line.y() if line.isValid() else 0.0)
                    for n in names:
                        out.setdefault(n, y)
            it += 1
        block = block.next()
    return out


def rendition(epub: Path, sha256: str, folders: list[Path]) -> tuple[Path, dict]:
    """The PDF rendition of an EPUB and its metadata, made if needed.

    `folders` are where renditions are kept, best first (the library folder,
    then this computer's data folder). An existing rendition in any of them
    is used as it is; a new one goes in the first that can be written."""
    for folder in folders:
        pdf, meta_path = rendition_paths(folder, sha256)
        if pdf.is_file() and pdf.stat().st_size > 0:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            return pdf, meta if isinstance(meta, dict) else {}
    last: Exception | None = None
    for folder in folders:
        pdf, meta_path = rendition_paths(folder, sha256)
        tmp = pdf.with_name(f".{pdf.name}.tmp")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            meta = render(epub, tmp, meta_path)
            tmp.replace(pdf)
            return pdf, meta
        except EpubError:
            _discard(tmp, meta_path)
            raise
        except OSError as exc:
            _discard(tmp)
            last = exc
            log.warning("Could not keep the rendition of %s in %s: %s", epub.name, folder, exc)
    raise EpubError(f"its pages could not be saved ({last})")


def _discard(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
