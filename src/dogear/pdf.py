"""Text geometry from Qt PDF: selection, words, outline and links.

Page rendering is not done here: QML's PdfPageImage renders in C++ off the
UI thread. Everything in this module runs on the UI thread only. Running
Python on a render thread could deadlock: Qt's pdfium lock and Python's GIL
would be taken in opposite orders by the two threads.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QModelIndex, QPointF, QRectF, Qt
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument, QPdfLinkModel



def rect_list(r: QRectF) -> list[float]:
    return [round(r.x(), 2), round(r.y(), 2), round(r.width(), 2), round(r.height(), 2)]


def selection(doc: QPdfDocument, page: int, x1: float, y1: float, x2: float, y2: float) -> dict:
    """Text and line rectangles between two points on a page (PDF points)."""
    sel = doc.getSelection(page, QPointF(x1, y1), QPointF(x2, y2))
    if not sel.isValid():
        return {"text": "", "rects": []}
    rects = [rect_list(poly.boundingRect()) for poly in sel.bounds()]
    return {"text": sel.text(), "rects": [r for r in rects if r[2] > 0 and r[3] > 0]}


def page_text_at(doc: QPdfDocument, page: int, x: float, y: float) -> dict:
    """The word under a point, for double-click selection."""
    text = doc.getAllText(page)
    if not text.isValid():
        return {"text": "", "rects": []}
    # pdfium has no word API exposed through Qt: select a few points around
    # the click to find a character index, then grow to whitespace.
    sel = None
    for half in (3.0, 6.0):
        candidate = doc.getSelection(page, QPointF(x - half, y), QPointF(x + half, y))
        if candidate.isValid() and candidate.text().strip():
            sel = candidate
            break
    if sel is None:
        return {"text": "", "rects": []}
    full = text.text()
    lo = hi = min(len(full), max(0, (sel.startIndex() + sel.endIndex()) // 2))
    while lo > 0 and not full[lo - 1].isspace():
        lo -= 1
    while hi < len(full) and not full[hi].isspace():
        hi += 1
    # Leave surrounding punctuation out of the word.
    while lo < hi and not full[lo].isalnum():
        lo += 1
    while hi > lo and not full[hi - 1].isalnum():
        hi -= 1
    if hi <= lo:
        return {"text": "", "rects": []}
    word = doc.getSelectionAtIndex(page, lo, hi - lo)
    if not word.isValid():
        return {"text": "", "rects": []}
    rects = [rect_list(poly.boundingRect()) for poly in word.bounds()]
    return {"text": word.text(), "rects": [r for r in rects if r[2] > 0 and r[3] > 0]}


def outline(doc: QPdfDocument) -> list[dict]:
    """The PDF's table of contents, flattened depth-first."""
    model = QPdfBookmarkModel()
    model.setDocument(doc)
    out: list[dict] = []
    page_role = QPdfBookmarkModel.Role.Page.value
    loc_role = QPdfBookmarkModel.Role.Location.value

    def walk(parent: QModelIndex, level: int) -> None:
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            loc = idx.data(loc_role)
            out.append({
                "title": str(idx.data(Qt.ItemDataRole.DisplayRole) or "").strip() or "Untitled",
                "level": level,
                "page": int(idx.data(page_role) or 0),
                "y": float(loc.y()) if isinstance(loc, QPointF) else 0.0,
            })
            walk(idx, level + 1)

    walk(QModelIndex(), 0)
    return out


def links(doc: QPdfDocument, page: int) -> list[dict]:
    """Internal links on a page (jumps within the document)."""
    model = QPdfLinkModel()
    model.setDocument(doc)
    model.setPage(page)
    out = []
    rect_role = QPdfLinkModel.Role.Rectangle.value
    page_role = QPdfLinkModel.Role.Page.value
    loc_role = QPdfLinkModel.Role.Location.value
    url_role = QPdfLinkModel.Role.Url.value
    for row in range(model.rowCount(QModelIndex())):
        idx = model.index(row, 0)
        rect = idx.data(rect_role)
        target = idx.data(page_role)
        url = idx.data(url_role)
        if not isinstance(rect, QRectF):
            continue
        if url is not None and url.isValid() and not url.isEmpty():
            continue  # external links are not followed (no network access)
        if target is None or int(target) < 0:
            continue
        loc = idx.data(loc_role)
        out.append({
            "rect": rect_list(rect),
            "page": int(target),
            "y": float(loc.y()) if isinstance(loc, QPointF) else 0.0,
        })
    return out


_LINE = re.compile(r"[^\r\n]+")


def text_lines(doc: QPdfDocument, page: int) -> list[dict]:
    """The page's text lines in reading order: {"text", "rect"} in points."""
    text = doc.getAllText(page)
    if not text.isValid():
        return []
    out = []
    for m in _LINE.finditer(text.text()):
        if not m.group().strip():
            continue
        sel = doc.getSelectionAtIndex(page, m.start(), m.end() - m.start())
        if sel.isValid():
            out.append({"text": m.group().strip(), "rect": rect_list(sel.boundingRectangle())})
    return out
