"""Qt PDF plumbing: page rendering for QML and the document's text geometry.

Rendering goes through a QQuickImageProvider with its own QPdfDocument so it
can run on QML's image-loading thread without touching the document the UI
thread uses for selection, search and links. Qt serialises pdfium access
internally; the lock here only guards loading/closing against a render in
flight.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QModelIndex, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument, QPdfLinkModel
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider

log = logging.getLogger(__name__)

PROVIDER_ID = "dogear"
MAX_RENDER_EDGE = 8192


class PageImageProvider(QQuickImageProvider):
    """Serves image://dogear/<generation>/<page>; the requested source size
    picks the render resolution."""

    def __init__(self):
        super().__init__(
            QQmlImageProviderBase.ImageType.Image,
            QQmlImageProviderBase.Flag.ForceAsynchronousImageLoading,
        )
        self._lock = threading.Lock()
        self._doc = QPdfDocument()

    def load(self, path: str) -> None:
        with self._lock:
            self._doc.close()
            self._doc.load(path)

    def close(self) -> None:
        with self._lock:
            self._doc.close()

    def requestImage(self, image_id: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802 (Qt API)
        try:
            page = int(image_id.split("/")[1])
        except (IndexError, ValueError):
            return QImage()
        with self._lock:
            if not (0 <= page < self._doc.pageCount()):
                return QImage()
            pts = self._doc.pagePointSize(page)
            if pts.width() <= 0 or pts.height() <= 0:
                return QImage()
            width = requested.width() if requested.width() > 0 else round(pts.width() * 2)
            width = max(16, min(MAX_RENDER_EDGE, width))
            height = max(16, min(MAX_RENDER_EDGE, round(width * pts.height() / pts.width())))
            rendered = self._doc.render(page, QSize(width, height))
        # Pages without a painted background come back transparent; readers
        # expect paper.
        image = QImage(rendered.size(), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.drawImage(0, 0, rendered)
        painter.end()
        return image


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
    # pdfium has no word API exposed through Qt; approximate by growing a
    # tiny selection sideways until it crosses whitespace.
    sel = doc.getSelection(page, QPointF(x - 0.5, y), QPointF(x + 0.5, y))
    if not sel.isValid() or not sel.text().strip():
        return {"text": "", "rects": []}
    start, end = sel.startIndex(), sel.endIndex()
    full = text.text()
    # Map back into the page text by index.
    lo, hi = start, end
    while lo > 0 and not full[lo - 1].isspace():
        lo -= 1
    while hi < len(full) and not full[hi].isspace():
        hi += 1
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
