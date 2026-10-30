"""QObjects exposed to QML: the open document (Doc) and app-level state (App)."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QFileSystemWatcher, QModelIndex, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QGuiApplication, QTextBlockFormat, QTextCursor
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtQuick import QQuickTextDocument

from . import config, contents, library, pdf, rules
from .export import export_markdown
from .store import HIGHLIGHT_COLORS, AnnotationStore, Answer, DocAnnotations, Rect, ViewState, clean_pdf_text

log = logging.getLogger(__name__)


def _shown(path: Path) -> str:
    """A path as Settings shows it: ~/… inside your home folder. Settings
    expands ~ again when it saves."""
    home = Path.home()
    try:
        return "~/" + path.relative_to(home).as_posix() if path != home else "~"
    except ValueError:
        return str(path)


def _to_path(path_or_url: str) -> Path:
    if path_or_url.startswith("file:"):
        return Path(QUrl(path_or_url).toLocalFile())
    return Path(path_or_url).expanduser()


class DocumentController(QObject):
    loadedChanged = Signal()
    outlineChanged = Signal()
    annotationsChanged = Signal()
    searchChanged = Signal()
    message = Signal(str)  # transient notice for the toast
    opened = Signal()  # a document finished loading; the view restores its position
    # A marked-up copy of this document exists elsewhere (another download
    # or edition): {sha256, title, fileName, highlights, notes, answers, ...}.
    copyFound = Signal("QVariantMap")

    def __init__(self, store: AnnotationStore, app: AppController, parent=None):
        super().__init__(parent)
        self._store = store
        self._app = app
        self._pdf = QPdfDocument(self)
        self._ann: DocAnnotations | None = None
        # The document's file as this computer last read or wrote it; what
        # changed on disk since came from another computer.
        self._base: dict | None = None
        self._path = ""
        self._revision = 0
        self._page_sizes: list[list[float]] = []
        self._outline: list[dict] = []
        # A PDF without an outline gets one made from its headings, a few
        # pages at a time so reading isn't held up (pdfium is UI-thread only).
        self._outline_made = False
        self._outline_next = -1  # the next page to read; -1 when not building
        self._outline_step = QTimer(self, interval=0)
        self._outline_step.timeout.connect(self._build_outline)
        self._links: dict[int, list[dict]] = {}
        self._rules: dict[int, list[dict]] = {}
        self._lines: dict[int, list[dict]] = {}
        self._char_lefts: dict[tuple[int, int], list[float]] = {}
        self._error = ""

        self._search = QPdfSearchModel(self)
        self._search.setDocument(self._pdf)
        self._search_term = ""
        self._search_results: list[dict] = []
        self._search_timer = QTimer(self, singleShot=True, interval=120)
        self._search_timer.timeout.connect(self._collect_search)
        for sig in (self._search.rowsInserted, self._search.modelReset, self._search.rowsRemoved):
            sig.connect(lambda *_: self._search_timer.start())
        # Qt's search model looks at one page every 100 ms on its own. Asking
        # for each page's results searches it at once, so the whole document
        # is searched in a few short steps and we know when it is finished.
        self._search_next_page = 0
        self._search_step = QTimer(self, interval=0)
        self._search_step.timeout.connect(self._search_pages)

        self._view_timer = QTimer(self, singleShot=True, interval=800)
        self._view_timer.timeout.connect(self._persist)
        app.storeChanged.connect(self._sync_from_disk)
        app._doc = self

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
            self._ann = self._store.open_document(
                path, title=title, page_count=self._pdf.pageCount(), pdf_id=library.pdf_id(path)
            )
        except OSError as exc:
            self._pdf.close()
            self._fail(f"Could not read {path.name}: {exc}")
            return False
        self._base = self._store.read_dict(self._ann.sha256)
        self._app.watch()  # its folders may have just been made
        self._path = str(path.resolve())
        self._page_sizes = []
        for i in range(self._pdf.pageCount()):
            s = self._pdf.pagePointSize(i)
            self._page_sizes.append([s.width() or 612.0, s.height() or 792.0])
        self._outline = pdf.outline(self._pdf)
        self._outline_made = False
        if not self._outline:
            saved = contents.load(self._ann.sha256)
            if saved is None:
                self._outline_next = 0
                self._outline_step.start()
            else:
                self._outline, self._outline_made = saved, True
        self._error = ""
        self._revision += 1
        self.loadedChanged.emit()
        self.outlineChanged.emit()
        self.annotationsChanged.emit()
        self._app.refreshRecents()
        if self._ann.carried_from:
            self.message.emit("This PDF changed since you last read it; your annotations were carried over.")
            self._ann.carried_from = ""
            self._save()
        self._keep_copy()
        if self._store.is_library_copy(Path(self._path)) and any(Path(p).parent.is_dir() for p in self._ann.paths):
            self.message.emit("The original PDF wasn't found, so this is Dogear's copy of it.")
        self.opened.emit()
        if self._ann.is_empty():
            copies = library.find_copies(self._store, self._ann)
            if copies:
                self.copyFound.emit(library.entry(self._store, copies[0]))
        return True

    def _build_outline(self) -> None:
        """Read the next page or two's text (about 15 ms a step); at the end, make
        and save the table of contents."""
        if self._ann is None or self._outline_next < 0:
            self._outline_step.stop()
            return
        count = len(self._page_sizes)
        started = time.monotonic()
        while self._outline_next < count and time.monotonic() - started < 0.015:
            page = self._outline_next
            if page not in self._lines:
                self._lines[page] = pdf.text_lines(self._pdf, page)
            self._outline_next += 1
        if self._outline_next < count:
            return
        self._outline_step.stop()
        self._outline_next = -1
        labels = [self._pdf.pageLabel(i) or str(i + 1) for i in range(count)]
        self._outline = contents.build([self._lines[i] for i in range(count)], labels)
        self._outline_made = True
        contents.save(self._ann.sha256, self._outline)
        self.outlineChanged.emit()

    def _keep_copy(self) -> None:
        """Copy a marked-up PDF into the library (setting, on by default)."""
        if self._ann is None or self._ann.is_empty() or not self._app.settings.keep_copies:
            return
        before = self._ann.copy
        try:
            self._store.keep_copy(self._ann, Path(self._path))
        except OSError as exc:
            log.warning("Could not copy %s into the library: %s", self._path, exc)
        if self._ann.copy != before:
            self._save()

    @Slot(str)
    def adoptMarks(self, sha: str) -> None:
        """Bring the marks of another copy (from copyFound) into this one."""
        if self._ann is None or not self._store.has(sha) or sha == self._ann.sha256:
            return
        other = self._store.load(sha)
        self._ann.adopt_marks(other)
        self._ann.carried_from = ""
        self._changed()
        self.message.emit(f"Brought over {sum(other.counts().values())} marks. Check that they line up with this copy.")

    @Slot(str)
    def declineCopy(self, sha: str) -> None:
        """Don't offer marks from that copy for this document again."""
        if self._ann is not None and sha not in self._ann.declined:
            self._ann.declined.append(sha)
            self._save()

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
        self._pdf.close()
        self._ann = None
        self._base = None
        self._path = ""
        self._page_sizes = []
        self._outline = []
        self._outline_made = False
        self._outline_next = -1
        self._outline_step.stop()
        self._links = {}
        self._rules = {}
        self._lines = {}
        self._char_lefts = {}
        self._revision += 1
        self.loadedChanged.emit()
        self.outlineChanged.emit()
        self.annotationsChanged.emit()

    def close_for_move(self) -> str:
        """Close the document before the library moves; returns its hash."""
        sha = self._ann.sha256 if self._ann else ""
        self.close()
        return sha

    def reopen(self, sha: str) -> None:
        """Open a document again after the library moved."""
        path = self._store.openable_path(self._store.load(sha)) if self._store.has(sha) else ""
        if path:
            self.open(path)

    @Slot()
    def flush(self) -> None:
        self._persist()

    def _save(self) -> None:
        if self._ann is None:
            return
        try:
            saved, self._base, merged = self._store.save_synced(self._ann, self._base)
        except OSError as exc:
            log.error("Saving annotations failed: %s", exc)
            self.message.emit(f"Could not save annotations: {exc}")
            return
        if merged:
            self._take(saved)

    def _take(self, merged: DocAnnotations) -> None:
        """Show a version merged with changes from another computer."""
        if merged.to_dict() == self._ann.to_dict():
            return
        # Keep an answer that is open but still blank (blanks aren't saved).
        ids = {a.id for a in merged.answers}
        merged.answers += [a for a in self._ann.answers if not a.text.strip() and a.id not in ids]
        merged.answers.sort(key=Answer.sort_key)
        self._ann = merged
        self._revision += 1
        self.annotationsChanged.emit()
        self.message.emit("Updated with changes from another computer.")

    def _sync_from_disk(self) -> None:
        """The library folder changed: take in this document's changes."""
        if self._ann is None:
            return
        disk = self._store.read_dict(self._ann.sha256)
        if disk is not None and disk != self._base:
            self._save()

    def _changed(self) -> None:
        self._save()
        self._keep_copy()
        self._revision += 1
        self.annotationsChanged.emit()

    def _persist(self) -> None:
        self._view_timer.stop()
        self._save()

    # -- document properties
    loaded = Property(bool, lambda self: self._ann is not None, notify=loadedChanged)
    path = Property(str, lambda self: self._path, notify=loadedChanged)
    url = Property(QUrl, lambda self: QUrl.fromLocalFile(self._path) if self._path else QUrl(), notify=loadedChanged)
    # The document's own name, also when it was opened from the library copy.
    fileName = Property(
        str,
        lambda self: (self._ann.file_name or Path(self._path).name) if self._ann else "",
        notify=loadedChanged,
    )
    title = Property(
        str,
        lambda self: self._ann.display_name() if self._ann else "",
        notify=loadedChanged,
    )
    error = Property(str, lambda self: self._error, notify=loadedChanged)
    pageCount = Property(int, lambda self: len(self._page_sizes), notify=loadedChanged)
    pageSizes = Property("QVariantList", lambda self: self._page_sizes, notify=loadedChanged)
    outline = Property("QVariantList", lambda self: self._outline, notify=outlineChanged)
    # The outline was made by Dogear from the PDF's headings.
    outlineMade = Property(bool, lambda self: self._outline_made, notify=outlineChanged)
    outlineBuilding = Property(bool, lambda self: self._outline_next >= 0, notify=outlineChanged)
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

    @Property(bool, notify=loadedChanged)
    def hasPageLabels(self) -> bool:
        """The PDF numbers its pages its own way (i, ii, ... then 1, 2, ...)."""
        return any(self.pageLabel(i) != str(i + 1) for i in range(len(self._page_sizes)))

    @Slot(str, result=int)
    def findPage(self, text: str) -> int:
        """The page "Go to page" means, or -1. The PDF's own page label wins,
        so "5" is the page printed 5; a number no page is labeled with is
        the page's place in the file."""
        text = text.strip()
        if not text or self._ann is None:
            return -1
        labels = [self.pageLabel(i) for i in range(len(self._page_sizes))]
        if text in labels:
            return labels.index(text)
        folded = [label.casefold() for label in labels]
        if text.casefold() in folded:  # "IV" for "iv"
            return folded.index(text.casefold())
        if text.isdigit() and 1 <= int(text) <= len(labels):
            return int(text) - 1
        return -1

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

    # -- answers written on answer lines
    def _page_ok(self, page: int) -> bool:
        return self._ann is not None and 0 <= page < len(self._page_sizes)

    def _rules_on(self, page: int) -> list[dict]:
        if page not in self._rules:
            self._rules[page] = rules.page_rules(self._pdf, page)
        return self._rules[page]

    def _covering(self, page: int, rule: dict) -> Answer | None:
        """The answer already written on this line, if any."""
        for a in self._ann.answers_on_page(page):
            if not a.y - 0.5 <= rule["y"] <= a.bottom() + 0.5:
                continue
            if abs(rule["x"] - a.x) < 4.0 or (a.indent and abs(rule["y"] - a.y) < 0.5 and abs(rule["x"] - a.x - a.indent) < 4.0):
                return a
        return None

    def _answer_hit(self, page: int, x: float, y: float) -> Answer | None:
        for a in self._ann.answers_on_page(page):
            if a.x - 2 <= x <= a.x + a.w + 2 and a.y - max(a.size * 1.8, 12.0) <= y <= a.bottom() + 4.0:
                # Left of an indented first line is the question.
                if a.indent and y <= a.y + 4.0 and x < a.x + a.indent - 2:
                    continue
                return a
        return None

    def _group_start(self, page: int, index: int) -> int:
        """First line of the ruled block that line `index` belongs to."""
        found = self._rules_on(page)
        start = index
        for j in range(index - 1, -1, -1):
            slot = rules.slot_from(found, j)
            if slot["lines"] < 2 or slot["y"] + (slot["lines"] - 1) * slot["pitch"] < found[index]["y"] - 0.5:
                break
            start = j
        return start

    def _answer_on_rule(self, page: int, index: int) -> str:
        """The answer on line `index`, starting a new one if it is blank."""
        found = self._rules_on(page)
        existing = self._covering(page, found[index])
        # Only one answer is open at a time: blank ones left behind go.
        blank = [a.id for a in self._ann.answers if not a.text.strip() and a is not existing]
        for aid in blank:
            self._ann.remove_answer(aid)
        if existing:
            if blank:
                self._changed()
            return existing.id
        if page not in self._lines:
            self._lines[page] = pdf.text_lines(self._pdf, page)
        # Write in the same size as the page's own text.
        slot = rules.slot_from(found, index, rules.text_size(self._lines[page]))
        lines = self._lines[page]
        def char_lefts(i: int) -> list[float]:
            key = (page, i)
            if key not in self._char_lefts:
                self._char_lefts[key] = pdf.char_lefts(self._pdf, page, lines[i])
            return self._char_lefts[key]

        context = rules.context_for(lines, slot["x"] + slot["indent"], slot["y"], rules=found, char_lefts=char_lefts)
        ans = self._ann.add_answer(
            page, slot["x"], slot["y"], slot["w"], pitch=slot["pitch"], lines=slot["lines"],
            indent=slot["indent"], size=slot["size"], context=context,
        )
        self._changed()
        return ans.id

    @Slot(int, result="QVariantList")
    def answersOnPage(self, page: int) -> list[dict]:
        if self._ann is None:
            return []
        return [a.to_dict() for a in self._ann.answers_on_page(page)]

    @Slot(int, float, float, result="QVariantMap")
    def blankAt(self, page: int, x: float, y: float) -> dict:
        """The writing area under the mouse: an empty answer line, for the
        hover hint. Empty when there is none or it already has an answer."""
        if not self._page_ok(page) or self._answer_hit(page, x, y):
            return {}
        found = self._rules_on(page)
        index = rules.rule_at(found, x, y)
        if index < 0 or self._covering(page, found[index]):
            return {}
        return rules.slot_from(found, index)

    @Slot(int, float, float, result=str)
    def answerAt(self, page: int, x: float, y: float) -> str:
        """The answer at a clicked point, starting one when an empty answer
        line was clicked. Empty when the point is not on an answer line."""
        if not self._page_ok(page):
            return ""
        hit = self._answer_hit(page, x, y)
        if hit:
            return hit.id
        index = rules.rule_at(self._rules_on(page), x, y)
        return self._answer_on_rule(page, index) if index >= 0 else ""

    @Slot(str, int, result="QVariantMap")
    def adjacentAnswer(self, aid: str, step: int) -> dict:
        """The next (step 1) or previous (step -1) answer line after answer
        `aid`, on this page or the next few. Starts an answer there if the
        line is blank. Returns {"page", "id"}, or {} at the end."""
        cur = self._ann.answer(aid) if self._ann else None
        if cur is None:
            return {}
        last = len(self._page_sizes) - 1
        for page in range(cur.page, min(last, cur.page + 5) + 1) if step > 0 else range(cur.page, max(0, cur.page - 5) - 1, -1):
            found = self._rules_on(page)
            order = list(range(len(found)))
            if page == cur.page:
                start = cur.x + cur.indent
                if step > 0:
                    order = [i for i in order if found[i]["y"] > cur.bottom() + 1
                             or (abs(found[i]["y"] - cur.y) < 1 and found[i]["x"] > start + 1)]
                else:
                    order = [i for i in order if found[i]["y"] < cur.y - 1
                             or (abs(found[i]["y"] - cur.y) < 1 and found[i]["x"] < start - 1)]
            if not order:
                continue
            index = order[0] if step > 0 else self._group_start(page, order[-1])
            return {"page": page, "id": self._answer_on_rule(page, index)}
        return {}

    @Slot(int, float, result="QVariantMap")
    def answerFrom(self, page: int, y: float) -> dict:
        """The first answer line at or below y on `page` (or the next few
        pages), starting an answer there if it is blank. {"page", "id"} or {}."""
        if not self._page_ok(page):
            return {}
        for p in range(page, min(len(self._page_sizes) - 1, page + 5) + 1):
            found = self._rules_on(p)
            index = next((i for i, r in enumerate(found) if p > page or r["y"] >= y), -1)
            if index >= 0:
                return {"page": p, "id": self._answer_on_rule(p, index)}
        return {}

    @Slot(QQuickTextDocument, float, float)
    def setLinePitch(self, document: QQuickTextDocument, pitch: float, indent: float) -> None:
        """Space an answer editor's lines exactly `pitch` pixels apart, so
        each line of text sits on a printed line, and start its first line
        `indent` pixels in. QML's TextEdit has neither of its own."""
        doc = document.textDocument() if document is not None else None
        if doc is None or pitch <= 0:
            return
        # Formatting is not an edit: keep it out of a fresh undo history.
        fresh = not doc.isUndoAvailable()
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            first = block.blockNumber() == 0
            if (fmt.lineHeightType() != QTextBlockFormat.LineHeightTypes.FixedHeight.value
                    or abs(fmt.lineHeight() - pitch) > 0.01 or abs(fmt.textIndent() - (indent if first else 0)) > 0.01):
                fmt.setLineHeight(pitch, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
                fmt.setTextIndent(indent if first else 0)
                cursor = QTextCursor(block)
                cursor.setBlockFormat(fmt)
            block = block.next()
        if fresh:
            doc.clearUndoRedoStacks()

    @Slot(QQuickTextDocument, str, float, float, float, int, result=float)
    def fitAnswerPx(self, document: QQuickTextDocument, text: str, px: float, width: float, indent: float,
                    lines: int) -> float:
        """The text size in pixels, up to `px`, at which an answer editor's
        `text` wraps onto no more than `lines` lines of `width` (the first
        `indent` in). It shrinks only once the lines are full, to no less
        than 0.6 of `px`. Measured on a copy of the editor's own document,
        so font, wrapping and metrics are the ones it lays out with."""
        source = document.textDocument() if document is not None else None
        if source is None:
            return px
        doc = source.clone()
        if doc.toPlainText() != text:
            doc.setPlainText(text)
        doc.setTextWidth(max(1.0, width))
        cursor = QTextCursor(doc)
        fmt = cursor.blockFormat()
        fmt.setTextIndent(indent)
        cursor.setBlockFormat(fmt)
        font = QFont(doc.defaultFont())
        # QML rounds a font's pixelSize: measure at the size it will show.
        low = max(1, round(px * 0.6))
        size = round(px)
        while size > low:
            font.setPixelSize(size)
            doc.setDefaultFont(font)
            doc.documentLayout().documentSize()  # lays it out
            used = 0
            block = doc.begin()
            while block.isValid():
                used += block.layout().lineCount()
                block = block.next()
            if used <= lines:
                break
            size -= 1
        return float(size) if size < round(px) else px

    @Slot(str, result="QVariantMap")
    def answer(self, aid: str) -> dict:
        ans = self._ann.answer(aid) if self._ann else None
        return ans.to_dict() if ans else {}

    @Slot(str, str)
    def setAnswerText(self, aid: str, text: str) -> None:
        ans = self._ann.answer(aid) if self._ann else None
        if ans and ans.text != text:
            self._ann.set_answer_text(aid, text)
            # Saved shortly after typing stops; no revision bump, so the
            # editor keeps its focus and cursor.
            self._view_timer.start()

    @Slot(str, float)
    def setAnswerSize(self, aid: str, size: float) -> None:
        """Text size of an answer in points, for squeezing more onto a line."""
        ans = self._ann.answer(aid) if self._ann else None
        if ans and 4.0 <= size <= 36.0 and ans.size != size:
            self._ann.set_answer_size(aid, size)
            # Like typing: saved shortly after, no rebuild of the editor.
            self._view_timer.start()

    @Slot(str)
    def finishAnswer(self, aid: str) -> None:
        """Typing in an answer ended: drop it if it was left blank."""
        ans = self._ann.answer(aid) if self._ann else None
        if ans is None:
            return
        if ans.text.strip():
            self._persist()
        else:
            self.removeAnswer(aid)

    @Slot(str)
    def removeAnswer(self, aid: str) -> None:
        if self._ann and self._ann.remove_answer(aid):
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
        self._search_next_page = 0
        if term and self._pdf.pageCount() > 0:
            self._search_step.start()
        else:
            self._search_step.stop()
        self.searchChanged.emit()
        self._search_timer.start()

    def _search_pages(self) -> None:
        count = self._pdf.pageCount()
        end = min(self._search_next_page + 25, count)
        for page in range(self._search_next_page, end):
            self._search.resultsOnPage(page)
        self._search_next_page = end
        if end >= count:
            self._search_step.stop()
            self._search_timer.stop()
            self._collect_search()
            self.searchChanged.emit()

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
    # Still looking through the pages: "No matches" would be premature.
    searching = Property(bool, lambda self: self._search_step.isActive(), notify=searchChanged)

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
        self.message.emit(f"Exported to {_shown(target)}")
        return str(target)


class AppController(QObject):
    recentsChanged = Signal()
    settingsChanged = Signal()

    # Something in the library folder changed on disk (another computer's
    # edits synced in, or this one's own saves).
    storeChanged = Signal()

    def __init__(self, store: AnnotationStore, settings: config.Settings | None = None, parent=None):
        super().__init__(parent)
        self._store = store
        self.settings = settings or config.load_settings()
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(lambda *_: self._disk_timer.start())
        self._disk_timer = QTimer(self, singleShot=True, interval=400)
        self._disk_timer.timeout.connect(self._disk_changed)
        self._snapshot = self._folder_snapshot()
        self.watch()
        self._last_color = "yellow"
        self._recents: list[dict] = []
        self.refreshRecents()
        # Documents marked up before copies were kept get theirs shortly
        # after start, one per tick so the window stays responsive.
        self._backfill: list[str] | None = None
        QTimer.singleShot(3000, self._backfill_copy)

    def _backfill_copy(self) -> None:
        if not self.settings.keep_copies:
            return
        if self._backfill is None:
            self._backfill = [d.sha256 for d in self._store.documents()
                              if not d.is_empty() and not self._store.copy_path(d.sha256).is_file()]
        if not self._backfill:
            return
        doc = self._store.load(self._backfill.pop(0))
        path = self._store.openable_path(doc)
        if path:
            try:
                if self._store.keep_copy(doc, Path(path)):
                    self._store.save(doc)
            except OSError as exc:
                log.warning("Could not copy %s into the library: %s", path, exc)
        QTimer.singleShot(200, self._backfill_copy)

    # -- the library folder on disk
    def watch(self) -> None:
        """Watch the folders another computer's changes arrive in."""
        # The folder itself too, to notice .dogear/ and Library/ appearing.
        store = self._store
        dirs = [str(d) for d in (store.root, store.meta_dir, store.ann_dir, store.library_dir) if d.is_dir()]
        stale = [d for d in self._watcher.directories() if d not in dirs]
        if stale:
            self._watcher.removePaths(stale)
        new = [d for d in dirs if d not in self._watcher.directories()]
        if new:
            self._watcher.addPaths(new)

    def _folder_snapshot(self) -> dict:
        out = {}
        for d in (self._store.ann_dir, self._store.meta_dir, self._store.library_dir):
            try:
                for f in d.iterdir():
                    if not f.name.startswith("."):
                        st = f.stat()
                        out[str(f)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue
        return out

    def _disk_changed(self) -> None:
        self.watch()
        try:
            self._store.resolve_conflicts()
        except OSError as exc:
            log.warning("Merging sync conflict copies failed: %s", exc)
        snapshot = self._folder_snapshot()
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        self.storeChanged.emit()
        self.libraryChanged.emit()

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
        return _shown(self.settings.resolved_export_dir())

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

    dataDir = Property(str, lambda self: _shown(self._store.root), notify=settingsChanged)
    libraryDir = Property(str, lambda self: _shown(self._store.library_dir), notify=settingsChanged)
    removedDir = Property(str, lambda self: _shown(self._store.removed_dir), notify=settingsChanged)
    # The library folder: notes, categories and PDF copies, maybe synced.
    libraryFolder = Property(str, lambda self: _shown(self._store.root), notify=settingsChanged)

    @Property(bool, notify=settingsChanged)
    def libraryFolderIsDefault(self) -> bool:
        return self._store.root.resolve() == config.default_library_dir().resolve()

    @Slot(str, result=str)
    def setLibraryFolder(self, value: str) -> str:
        """Move the library to another folder (empty: the default one) and
        use it from now on. Returns an error message, or "" when done."""
        target = _to_path(value) if value.strip() else config.default_library_dir()
        if target.resolve() == self._store.root.resolve():
            return ""
        if target.exists() and not target.is_dir():
            return f"{target} is not a folder."
        doc = self._doc
        sha = doc.close_for_move() if doc is not None else ""
        try:
            self._store.move_to(target)
        except OSError as exc:
            log.error("Moving the library to %s failed: %s", target, exc)
            message = f"Could not move the library to {target}: {exc}"
        else:
            message = ""
            self.settings.library_dir = "" if target.resolve() == config.default_library_dir().resolve() else str(target)
            try:
                config.save_settings(self.settings)
            except OSError as exc:
                log.error("Saving settings failed: %s", exc)
        self._snapshot = self._folder_snapshot()
        self.watch()
        self.settingsChanged.emit()
        self.libraryChanged.emit()
        self.refreshRecents()
        if doc is not None and sha:
            doc.reopen(sha)
        return message

    _doc = None  # the DocumentController, set by it

    @Property(bool, notify=settingsChanged)
    def keepCopies(self) -> bool:
        return self.settings.keep_copies

    @Slot(bool)
    def setKeepCopies(self, value: bool) -> None:
        if self.settings.keep_copies == value:
            return
        self.settings.keep_copies = value
        try:
            config.save_settings(self.settings)
        except OSError as exc:
            log.error("Saving settings failed: %s", exc)
        self.settingsChanged.emit()

    @Slot(result=str)
    def copiesSize(self) -> str:
        """Disk space the library's PDF copies take, for Settings."""
        total = sum(f.stat().st_size for f in self._store.library_dir.glob("*.pdf")) if self._store.library_dir.is_dir() else 0
        for unit in ("bytes", "KB", "MB", "GB"):
            if total < 1024 or unit == "GB":
                return f"{total:.0f} {unit}" if unit == "bytes" else f"{total:.1f} {unit}"
            total /= 1024
        return ""

    # -- library
    libraryChanged = Signal()

    @Slot(str, str, str, result="QVariantList")
    def library(self, query: str, sort: str, category: str) -> list[dict]:
        return library.entries(self._store, query, sort, category)

    @Slot(result="QVariantList")
    def categoryList(self) -> list[dict]:
        return library.category_counts(self._store)

    categories = Property("QStringList", lambda self: self._store.categories(), notify=libraryChanged)

    @Slot(str, result=str)
    def addCategory(self, name: str) -> str:
        made = self._store.add_category(name)
        self.libraryChanged.emit()
        return made

    @Slot(str, str)
    def renameCategory(self, old: str, new: str) -> None:
        self._store.rename_category(old, new)
        self.libraryChanged.emit()

    @Slot(str)
    def removeCategory(self, name: str) -> None:
        self._store.remove_category(name)
        self.libraryChanged.emit()

    @Slot(str, str)
    def renameDocument(self, sha: str, name: str) -> None:
        if self._store.has(sha):
            self._store.rename_document(sha, name)
            self.libraryChanged.emit()
            self.refreshRecents()

    @Slot(str, result=str)
    def removeDocument(self, sha: str) -> str:
        """Remove a document from the library; returns where its marks went."""
        try:
            target = self._store.remove_document(sha)
        except OSError as exc:
            log.error("Removing %s failed: %s", sha, exc)
            return ""
        self.libraryChanged.emit()
        self.refreshRecents()
        return str(target or "")

    @Slot(str, "QStringList")
    def setCategories(self, sha: str, names: list[str]) -> None:
        if self._store.has(sha):
            self._store.set_categories(sha, list(names))
            self.libraryChanged.emit()

    lastColorChanged = Signal()
    lastColor = Property(str, lambda self: self._last_color, notify=lastColorChanged)

    @Slot(str)
    def setLastColor(self, color: str) -> None:
        if color in HIGHLIGHT_COLORS and color != self._last_color:
            self._last_color = color
            self.lastColorChanged.emit()
