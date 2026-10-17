"""QObjects exposed to QML: the open document (Doc) and app-level state (App)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QModelIndex, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel

from . import config, pdf
from .export import export_markdown
from .store import HIGHLIGHT_COLORS, AnnotationStore, DocAnnotations, Rect, ViewState, clean_pdf_text

log = logging.getLogger(__name__)


def _to_path(path_or_url: str) -> Path:
    if path_or_url.startswith("file:"):
        return Path(QUrl(path_or_url).toLocalFile())
    return Path(path_or_url).expanduser()


class DocumentController(QObject):
    loadedChanged = Signal()
    annotationsChanged = Signal()
    searchChanged = Signal()
    message = Signal(str)  # transient notice for the toast
    opened = Signal()  # a document finished loading; the view restores its position

    def __init__(self, store: AnnotationStore, provider: pdf.PageImageProvider, app: AppController, parent=None):
        super().__init__(parent)
        self._store = store
        self._provider = provider
        self._app = app
        self._pdf = QPdfDocument(self)
        self._ann: DocAnnotations | None = None
        self._path = ""
        self._generation = 0
        self._revision = 0
        self._page_sizes: list[list[float]] = []
        self._outline: list[dict] = []
        self._links: dict[int, list[dict]] = {}
        self._error = ""

        self._search = QPdfSearchModel(self)
        self._search.setDocument(self._pdf)
        self._search_term = ""
        self._search_results: list[dict] = []
        self._search_timer = QTimer(self, singleShot=True, interval=120)
        self._search_timer.timeout.connect(self._collect_search)
        for sig in (self._search.rowsInserted, self._search.modelReset, self._search.rowsRemoved):
            sig.connect(lambda *_: self._search_timer.start())

        self._view_timer = QTimer(self, singleShot=True, interval=800)
        self._view_timer.timeout.connect(self._persist)

    # -- loading
    @Slot(str, result=bool)
    def open(self, path_or_url: str) -> bool:
        path = _to_path(path_or_url)
        if not path.is_file():
            self._fail(f"File not found: {path}")
            return False
        self.close()
        status = self._pdf.load(str(path))
        if status != QPdfDocument.Error.None_:
            self._pdf.close()
            reason = {
                QPdfDocument.Error.IncorrectPassword: "it is password protected",
                QPdfDocument.Error.UnsupportedSecurityScheme: "its security scheme is not supported",
                QPdfDocument.Error.InvalidFileFormat: "it is not a valid PDF",
            }.get(status, f"error {status.name}")
            self._fail(f"Could not open {path.name}: {reason}")
            return False
        title = (self._pdf.metaData(QPdfDocument.MetaDataField.Title) or "").strip()
        try:
            self._ann = self._store.open_document(path, title=title)
        except OSError as exc:
            self._pdf.close()
            self._fail(f"Could not read {path.name}: {exc}")
            return False
        self._path = str(path.resolve())
        self._provider.load(self._path)
        self._generation += 1
        self._page_sizes = []
        for i in range(self._pdf.pageCount()):
            s = self._pdf.pagePointSize(i)
            self._page_sizes.append([s.width() or 612.0, s.height() or 792.0])
        self._outline = pdf.outline(self._pdf)
        self._error = ""
        self._revision += 1
        self.loadedChanged.emit()
        self.annotationsChanged.emit()
        self._app.refreshRecents()
        if self._ann.carried_from:
            self.message.emit("This PDF changed since you last read it; your annotations were carried over.")
            self._ann.carried_from = ""
            self._save()
        self.opened.emit()
        return True

    def _fail(self, text: str) -> None:
        log.warning(text)
        self._error = text
        self.loadedChanged.emit()
        self.message.emit(text)

    @Slot()
    def close(self) -> None:
        if self._ann is None:
            return
        self._persist()
        self.setSearch("")
        self._provider.close()
        self._pdf.close()
        self._ann = None
        self._path = ""
        self._page_sizes = []
        self._outline = []
        self._links = {}
        self._revision += 1
        self.loadedChanged.emit()
        self.annotationsChanged.emit()

    @Slot()
    def flush(self) -> None:
        self._persist()

    def _save(self) -> None:
        if self._ann is None:
            return
        try:
            self._store.save(self._ann)
        except OSError as exc:
            log.error("Saving annotations failed: %s", exc)
            self.message.emit(f"Could not save annotations: {exc}")

    def _changed(self) -> None:
        self._save()
        self._revision += 1
        self.annotationsChanged.emit()

    def _persist(self) -> None:
        self._view_timer.stop()
        self._save()

    # -- document properties
    loaded = Property(bool, lambda self: self._ann is not None, notify=loadedChanged)
    path = Property(str, lambda self: self._path, notify=loadedChanged)
    fileName = Property(str, lambda self: Path(self._path).name if self._path else "", notify=loadedChanged)
    title = Property(
        str,
        lambda self: (self._ann.title or Path(self._path).stem) if self._ann else "",
        notify=loadedChanged,
    )
    error = Property(str, lambda self: self._error, notify=loadedChanged)
    pageCount = Property(int, lambda self: len(self._page_sizes), notify=loadedChanged)
    generation = Property(int, lambda self: self._generation, notify=loadedChanged)
    pageSizes = Property("QVariantList", lambda self: self._page_sizes, notify=loadedChanged)
    outline = Property("QVariantList", lambda self: self._outline, notify=loadedChanged)
    revision = Property(int, lambda self: self._revision, notify=annotationsChanged)
    colors = Property("QStringList", lambda self: list(HIGHLIGHT_COLORS), constant=True)

    @Property("QVariantList", notify=annotationsChanged)
    def highlights(self) -> list[dict]:
        if self._ann is None:
            return []
        return [h.to_dict() for h in self._ann.highlights]

    @Property("QVariantList", notify=annotationsChanged)
    def bookmarks(self) -> list[dict]:
        if self._ann is None:
            return []
        return [b.to_dict() for b in self._ann.bookmarks]

    @Property("QVariantList", notify=annotationsChanged)
    def notes(self) -> list[dict]:
        if self._ann is None:
            return []
        return [n.to_dict() for n in self._ann.notes]

    @Slot(int, result=str)
    def pageLabel(self, page: int) -> str:
        if self._ann is None or not 0 <= page < len(self._page_sizes):
            return ""
        return self._pdf.pageLabel(page) or str(page + 1)

    @Slot(int, result="QVariantList")
    def highlightsOnPage(self, page: int) -> list[dict]:
        if self._ann is None:
            return []
        return [h.to_dict() for h in self._ann.highlights_on_page(page)]

    @Slot(int, result="QVariantList")
    def bookmarksOnPage(self, page: int) -> list[dict]:
        if self._ann is None:
            return []
        return [b.to_dict() for b in self._ann.bookmarks if b.page == page]

    @Slot(int, result="QVariantList")
    def linksOnPage(self, page: int) -> list[dict]:
        if self._ann is None or not 0 <= page < len(self._page_sizes):
            return []
        if page not in self._links:
            self._links[page] = pdf.links(self._pdf, page)
        return self._links[page]

    # -- selection
    @Slot(int, float, float, float, float, result="QVariantMap")
    def select(self, page: int, x1: float, y1: float, x2: float, y2: float) -> dict:
        if self._ann is None or not 0 <= page < len(self._page_sizes):
            return {"text": "", "rects": []}
        return pdf.selection(self._pdf, page, x1, y1, x2, y2)

    @Slot(int, float, float, result="QVariantMap")
    def wordAt(self, page: int, x: float, y: float) -> dict:
        if self._ann is None or not 0 <= page < len(self._page_sizes):
            return {"text": "", "rects": []}
        return pdf.page_text_at(self._pdf, page, x, y)

    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(clean_pdf_text(text))

    # -- highlights
    @Slot(int, "QVariantList", str, str, result=str)
    def addHighlight(self, page: int, rects: list, text: str, color: str) -> str:
        if self._ann is None:
            return ""
        parsed = [r for r in (Rect.from_any(v) for v in rects) if r]
        if not parsed:
            return ""
        hl = self._ann.add_highlight(page, parsed, clean_pdf_text(text), color if color in HIGHLIGHT_COLORS else "yellow")
        self._app.setLastColor(hl.color)
        self._changed()
        return hl.id

    @Slot(str, result="QVariantMap")
    def highlight(self, hid: str) -> dict:
        hl = self._ann.highlight(hid) if self._ann else None
        return hl.to_dict() if hl else {}

    @Slot(str, str)
    def setHighlightColor(self, hid: str, color: str) -> None:
        if self._ann and self._ann.highlight(hid) and color in HIGHLIGHT_COLORS:
            self._ann.update_highlight(hid, color=color)
            self._app.setLastColor(color)
            self._changed()

    @Slot(str, str)
    def setHighlightNote(self, hid: str, note: str) -> None:
        hl = self._ann.highlight(hid) if self._ann else None
        if hl and hl.note != note:
            self._ann.update_highlight(hid, note=note)
            self._changed()

    @Slot(str)
    def removeHighlight(self, hid: str) -> None:
        if self._ann and self._ann.remove_highlight(hid):
            self._changed()

    # -- bookmarks
    @Slot(int, result=str)
    def suggestBookmarkName(self, page: int) -> str:
        """The outline entry covering this page, else 'Page N'."""
        best = None
        for entry in self._outline:
            if entry["page"] <= page:
                if best is None or entry["page"] >= best["page"]:
                    best = entry
        label = self.pageLabel(page)
        page_name = f"Page {label}" if label else f"Page {page + 1}"
        if best is not None:
            return best["title"] if best["page"] == page else f"{best['title']} · {page_name}"
        return page_name

    @Slot(int, float, str, result=str)
    def addBookmark(self, page: int, y: float, name: str) -> str:
        if self._ann is None:
            return ""
        bm = self._ann.add_bookmark(page, name or self.suggestBookmarkName(page), y)
        self._changed()
        return bm.id

    @Slot(str, str)
    def renameBookmark(self, bid: str, name: str) -> None:
        if self._ann is None:
            return
        try:
            self._ann.rename_bookmark(bid, name)
        except KeyError:
            return
        self._changed()

    @Slot(str)
    def removeBookmark(self, bid: str) -> None:
        if self._ann and self._ann.remove_bookmark(bid):
            self._changed()

    # -- document notes
    @Slot(str, result=str)
    def addNote(self, text: str) -> str:
        if self._ann is None:
            return ""
        note = self._ann.add_note(text)
        self._changed()
        return note.id

    @Slot(str, str)
    def updateNote(self, nid: str, text: str) -> None:
        if self._ann is None:
            return
        try:
            note = next(n for n in self._ann.notes if n.id == nid)
        except StopIteration:
            return
        if note.text != text:
            self._ann.update_note(nid, text)
            # No revision bump: the editor already shows the text, and
            # rebuilding the list would steal its focus mid-typing.
            self._save()

    @Slot(str)
    def removeNote(self, nid: str) -> None:
        if self._ann and self._ann.remove_note(nid):
            self._changed()

    # -- view state
    @Slot(result="QVariantMap")
    def view(self) -> dict:
        return self._ann.view.to_dict() if self._ann else ViewState().to_dict()

    @Slot(int, float, float, bool, float)
    def saveView(self, page: int, offset: float, zoom: float, fit_width: bool, x: float) -> None:
        if self._ann is None:
            return
        self._ann.view = ViewState.from_dict(
            {"page": page, "offset": offset, "zoom": zoom, "fit_width": fit_width, "x": x}
        )
        self._view_timer.start()

    # -- search
    @Slot(str)
    def setSearch(self, term: str) -> None:
        term = term.strip()
        if term == self._search_term:
            return
        self._search_term = term
        self._search_results = []
        self._search.setSearchString(term)
        self.searchChanged.emit()
        self._search_timer.start()

    def _collect_search(self) -> None:
        results = []
        if self._search_term:
            for i in range(self._search.rowCount(QModelIndex())):
                link = self._search.resultAtIndex(i)
                if link.page() < 0:
                    continue
                results.append({
                    "page": link.page(),
                    "rects": [pdf.rect_list(r) for r in link.rectangles()],
                    "context": (link.contextBefore() + link.contextAfter()).replace("⏎", " ").strip(),
                })
        results.sort(key=lambda r: (r["page"], r["rects"][0][1] if r["rects"] else 0, r["rects"][0][0] if r["rects"] else 0))
        if results != self._search_results:
            self._search_results = results
            self.searchChanged.emit()

    searchTerm = Property(str, lambda self: self._search_term, notify=searchChanged)
    searchResults = Property("QVariantList", lambda self: self._search_results, notify=searchChanged)

    # -- export
    @Slot(result=str)
    def exportMarkdown(self) -> str:
        if self._ann is None:
            return ""
        out_dir = self._app.settings.resolved_export_dir()
        try:
            target = export_markdown(self._ann, out_dir, source_path=self._path, page_label=self.pageLabel)
        except OSError as exc:
            self.message.emit(f"Export failed: {exc}")
            return ""
        self.message.emit(f"Exported to {target}")
        return str(target)


class AppController(QObject):
    recentsChanged = Signal()
    settingsChanged = Signal()

    def __init__(self, store: AnnotationStore, parent=None):
        super().__init__(parent)
        self._store = store
        self.settings = config.load_settings()
        self._last_color = "yellow"
        self._recents: list[dict] = []
        self.refreshRecents()

    @Slot()
    def refreshRecents(self) -> None:
        out = []
        for r in self._store.recents():
            opened = datetime.fromtimestamp(r.opened) if r.opened else None
            folder = str(Path(r.path).parent).replace(str(Path.home()), "~", 1)
            out.append({
                "path": r.path,
                "title": r.title,
                "fileName": Path(r.path).name,
                "folder": folder,
                "exists": r.exists(),
                "opened": opened.strftime("%b %-d, %H:%M") if opened else "",
            })
        self._recents = out
        self.recentsChanged.emit()

    @Slot(str)
    def forgetRecent(self, path: str) -> None:
        self._store.forget_recent(path)
        self.refreshRecents()

    recents = Property("QVariantList", lambda self: self._recents, notify=recentsChanged)

    @Property(str, notify=settingsChanged)
    def exportDir(self) -> str:
        return str(self.settings.resolved_export_dir())

    @Property(bool, notify=settingsChanged)
    def exportDirIsDefault(self) -> bool:
        return not self.settings.export_dir.strip()

    @Slot(str)
    def setExportDir(self, value: str) -> None:
        value = str(_to_path(value)) if value.strip() else ""
        self.settings.export_dir = value
        try:
            config.save_settings(self.settings)
        except OSError as exc:
            log.error("Saving settings failed: %s", exc)
        self.settingsChanged.emit()

    dataDir = Property(str, lambda self: str(self._store.root), constant=True)

    lastColorChanged = Signal()
    lastColor = Property(str, lambda self: self._last_color, notify=lastColorChanged)

    @Slot(str)
    def setLastColor(self, color: str) -> None:
        if color in HIGHLIGHT_COLORS and color != self._last_color:
            self._last_color = color
            self.lastColorChanged.emit()
