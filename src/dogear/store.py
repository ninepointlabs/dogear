"""Annotation store: highlights, notes, bookmarks and view state per PDF (no Qt).

Annotations live in a central app-data directory, one JSON file per document,
keyed by the SHA-256 of the PDF's bytes:

    $XDG_DATA_HOME/dogear/
        index.json                  recent files + path -> hash cache
        annotations/<sha256>.json   one document's annotations

Keying by content means a renamed or moved PDF keeps its annotations, the
original PDF is never written to, and nothing is dropped into class folders.
When the file at a known path changes (a new revision of the same handout),
its annotations are carried over to the new hash so they are not lost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fsutil import atomic_write_text

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink", "purple")
DEFAULT_COLOR = "yellow"
MAX_RECENTS = 30


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


_HYPHEN_BREAK = re.compile(r"(\w)-\s*\r?\n\s*(\w)")
_WS = re.compile(r"\s+")


def clean_pdf_text(text: str) -> str:
    """Turn text copied out of a PDF into one readable paragraph.

    PDF text comes with hard line breaks at every line end, and words split
    across lines keep their hyphen. Join lines with spaces and undo the
    hyphenation at line breaks.
    """
    text = text.replace("­", "")  # soft hyphens
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    return _WS.sub(" ", text).strip()


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def _str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


@dataclass
class Rect:
    """A rectangle in PDF points, origin at the page's top-left."""

    x: float
    y: float
    w: float
    h: float

    def to_list(self) -> list[float]:
        return [round(self.x, 2), round(self.y, 2), round(self.w, 2), round(self.h, 2)]

    @classmethod
    def from_any(cls, raw: Any) -> Rect | None:
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            vals = [_num(v, float("nan")) for v in raw]
            if all(v == v for v in vals) and vals[2] >= 0 and vals[3] >= 0:
                return cls(*vals)
        return None


@dataclass
class Highlight:
    id: str
    page: int
    rects: list[Rect]
    text: str
    color: str = DEFAULT_COLOR
    note: str = ""
    created: str = ""
    updated: str = ""

    def sort_key(self) -> tuple[int, float, float]:
        if not self.rects:
            return (self.page, 0.0, 0.0)
        top = min(r.y for r in self.rects)
        left = min(r.x for r in self.rects if r.y == top)
        return (self.page, top, left)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "page": self.page,
            "rects": [r.to_list() for r in self.rects],
            "text": self.text,
            "color": self.color,
            "note": self.note,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Highlight | None:
        rects = [r for r in (Rect.from_any(v) for v in raw.get("rects") or []) if r]
        page = _int(raw.get("page"), -1)
        if page < 0:
            return None
        color = _str(raw.get("color"), DEFAULT_COLOR)
        return cls(
            id=_str(raw.get("id")) or new_id(),
            page=page,
            rects=rects,
            text=_str(raw.get("text")),
            color=color if color in HIGHLIGHT_COLORS else DEFAULT_COLOR,
            note=_str(raw.get("note")),
            created=_str(raw.get("created")),
            updated=_str(raw.get("updated")),
        )


@dataclass
class Bookmark:
    id: str
    page: int
    name: str
    y: float = 0.0  # PDF points from the top of the page
    created: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "page": self.page, "name": self.name, "y": round(self.y, 2), "created": self.created}

    @classmethod
    def from_dict(cls, raw: dict) -> Bookmark | None:
        page = _int(raw.get("page"), -1)
        if page < 0:
            return None
        return cls(
            id=_str(raw.get("id")) or new_id(),
            page=page,
            name=_str(raw.get("name")),
            y=max(0.0, _num(raw.get("y"))),
            created=_str(raw.get("created")),
        )


@dataclass
class Note:
    """A general note about the document, not tied to a page."""

    id: str
    text: str
    created: str = ""
    updated: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "created": self.created, "updated": self.updated}

    @classmethod
    def from_dict(cls, raw: dict) -> Note:
        return cls(
            id=_str(raw.get("id")) or new_id(),
            text=_str(raw.get("text")),
            created=_str(raw.get("created")),
            updated=_str(raw.get("updated")),
        )


@dataclass
class Answer:
    """Text written on an answer line in the PDF.

    Positions are PDF points from the page's top-left. `y` is the first
    line the text sits on; with `pitch` > 0 the text continues on `lines`
    evenly spaced lines below it, like ruled paper. `context` is the text
    printed around the line (the question), kept for the export.
    """

    id: str
    page: int
    x: float
    y: float
    w: float
    pitch: float = 0.0
    lines: int = 1
    size: float = 11.0
    text: str = ""
    context: str = ""
    created: str = ""
    updated: str = ""

    def sort_key(self) -> tuple[int, float, float]:
        return (self.page, self.y, self.x)

    def bottom(self) -> float:
        """The y of the last line the answer was given."""
        return self.y + max(0, self.lines - 1) * self.pitch

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "page": self.page,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "w": round(self.w, 2),
            "pitch": round(self.pitch, 2),
            "lines": self.lines,
            "size": round(self.size, 2),
            "text": self.text,
            "context": self.context,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Answer | None:
        page = _int(raw.get("page"), -1)
        w = _num(raw.get("w"))
        if page < 0 or w <= 0:
            return None
        size = _num(raw.get("size"), 11.0)
        return cls(
            id=_str(raw.get("id")) or new_id(),
            page=page,
            x=max(0.0, _num(raw.get("x"))),
            y=max(0.0, _num(raw.get("y"))),
            w=w,
            pitch=max(0.0, _num(raw.get("pitch"))),
            lines=max(1, _int(raw.get("lines"), 1)),
            size=size if 3.0 <= size <= 72.0 else 11.0,
            text=_str(raw.get("text")),
            context=_str(raw.get("context")),
            created=_str(raw.get("created")),
            updated=_str(raw.get("updated")),
        )


@dataclass
class ViewState:
    page: int = 0
    offset: float = 0.0  # fraction of the page height scrolled past, 0..1
    zoom: float = 1.0
    fit_width: bool = True
    x: float = 0.0  # horizontal scroll fraction when zoomed past the window

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "offset": round(self.offset, 4),
            "zoom": round(self.zoom, 4),
            "fit_width": self.fit_width,
            "x": round(self.x, 4),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> ViewState:
        if not isinstance(raw, dict):
            return cls()
        zoom = _num(raw.get("zoom"), 1.0)
        return cls(
            page=max(0, _int(raw.get("page"))),
            offset=min(1.0, max(0.0, _num(raw.get("offset")))),
            zoom=zoom if 0.1 <= zoom <= 8.0 else 1.0,
            fit_width=raw.get("fit_width", True) is not False,
            x=min(1.0, max(0.0, _num(raw.get("x")))),
        )


@dataclass
class DocAnnotations:
    sha256: str
    file_name: str = ""
    title: str = ""
    paths: list[str] = field(default_factory=list)
    view: ViewState = field(default_factory=ViewState)
    highlights: list[Highlight] = field(default_factory=list)
    bookmarks: list[Bookmark] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    answers: list[Answer] = field(default_factory=list)
    carried_from: str = ""

    # -- highlights
    def add_highlight(self, page: int, rects: list[Rect], text: str, color: str = DEFAULT_COLOR, note: str = "") -> Highlight:
        if color not in HIGHLIGHT_COLORS:
            raise ValueError(f"unknown highlight color: {color}")
        stamp = now_iso()
        hl = Highlight(new_id(), page, list(rects), text, color, note, stamp, stamp)
        self.highlights.append(hl)
        self.highlights.sort(key=Highlight.sort_key)
        return hl

    def highlight(self, hid: str) -> Highlight | None:
        return next((h for h in self.highlights if h.id == hid), None)

    def update_highlight(self, hid: str, *, color: str | None = None, note: str | None = None) -> Highlight:
        hl = self.highlight(hid)
        if hl is None:
            raise KeyError(hid)
        if color is not None:
            if color not in HIGHLIGHT_COLORS:
                raise ValueError(f"unknown highlight color: {color}")
            hl.color = color
        if note is not None:
            hl.note = note
        hl.updated = now_iso()
        return hl

    def remove_highlight(self, hid: str) -> bool:
        before = len(self.highlights)
        self.highlights = [h for h in self.highlights if h.id != hid]
        return len(self.highlights) != before

    def highlights_on_page(self, page: int) -> list[Highlight]:
        return [h for h in self.highlights if h.page == page]

    # -- bookmarks
    def add_bookmark(self, page: int, name: str, y: float = 0.0) -> Bookmark:
        bm = Bookmark(new_id(), page, name.strip() or f"Page {page + 1}", max(0.0, y), now_iso())
        self.bookmarks.append(bm)
        self.bookmarks.sort(key=lambda b: (b.page, b.y))
        return bm

    def rename_bookmark(self, bid: str, name: str) -> Bookmark:
        bm = next((b for b in self.bookmarks if b.id == bid), None)
        if bm is None:
            raise KeyError(bid)
        bm.name = name.strip() or f"Page {bm.page + 1}"
        return bm

    def remove_bookmark(self, bid: str) -> bool:
        before = len(self.bookmarks)
        self.bookmarks = [b for b in self.bookmarks if b.id != bid]
        return len(self.bookmarks) != before

    # -- document notes
    def add_note(self, text: str = "") -> Note:
        stamp = now_iso()
        note = Note(new_id(), text, stamp, stamp)
        self.notes.append(note)
        return note

    def update_note(self, nid: str, text: str) -> Note:
        note = next((n for n in self.notes if n.id == nid), None)
        if note is None:
            raise KeyError(nid)
        if note.text != text:
            note.text = text
            note.updated = now_iso()
        return note

    def remove_note(self, nid: str) -> bool:
        before = len(self.notes)
        self.notes = [n for n in self.notes if n.id != nid]
        return len(self.notes) != before

    # -- answers written on the page
    def add_answer(
        self, page: int, x: float, y: float, w: float, *,
        pitch: float = 0.0, lines: int = 1, size: float = 11.0, text: str = "", context: str = "",
    ) -> Answer:
        stamp = now_iso()
        ans = Answer(new_id(), page, x, y, w, max(0.0, pitch), max(1, lines), size, text, context, stamp, stamp)
        self.answers.append(ans)
        self.answers.sort(key=Answer.sort_key)
        return ans

    def answer(self, aid: str) -> Answer | None:
        return next((a for a in self.answers if a.id == aid), None)

    def set_answer_text(self, aid: str, text: str) -> Answer:
        ans = self.answer(aid)
        if ans is None:
            raise KeyError(aid)
        if ans.text != text:
            ans.text = text
            ans.updated = now_iso()
        return ans

    def set_answer_size(self, aid: str, size: float) -> Answer:
        ans = self.answer(aid)
        if ans is None:
            raise KeyError(aid)
        if not 3.0 <= size <= 72.0:
            raise ValueError(f"answer text size out of range: {size}")
        ans.size = size
        ans.updated = now_iso()
        return ans

    def remove_answer(self, aid: str) -> bool:
        before = len(self.answers)
        self.answers = [a for a in self.answers if a.id != aid]
        return len(self.answers) != before

    def answers_on_page(self, page: int) -> list[Answer]:
        return [a for a in self.answers if a.page == page]

    def is_empty(self) -> bool:
        return not (self.highlights or self.bookmarks or self.notes or self.answers)

    # -- serialization
    def to_dict(self) -> dict:
        data = {
            "dogear": SCHEMA_VERSION,
            "sha256": self.sha256,
            "file_name": self.file_name,
            "title": self.title,
            "paths": self.paths,
            "view": self.view.to_dict(),
            "highlights": [h.to_dict() for h in self.highlights],
            "bookmarks": [b.to_dict() for b in self.bookmarks],
            "notes": [n.to_dict() for n in self.notes],
            # Blank answers are only an open editor; they are not kept.
            "answers": [a.to_dict() for a in self.answers if a.text.strip()],
        }
        if self.carried_from:
            data["carried_from"] = self.carried_from
        return data

    @classmethod
    def from_dict(cls, raw: dict, sha256: str) -> DocAnnotations:
        def items(key: str) -> list[dict]:
            value = raw.get(key)
            return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

        doc = cls(
            sha256=sha256,
            file_name=_str(raw.get("file_name")),
            title=_str(raw.get("title")),
            paths=[p for p in raw.get("paths") or [] if isinstance(p, str)],
            view=ViewState.from_dict(raw.get("view")),
            highlights=[h for h in (Highlight.from_dict(v) for v in items("highlights")) if h],
            bookmarks=[b for b in (Bookmark.from_dict(v) for v in items("bookmarks")) if b],
            notes=[Note.from_dict(v) for v in items("notes")],
            answers=[a for a in (Answer.from_dict(v) for v in items("answers")) if a and a.text.strip()],
            carried_from=_str(raw.get("carried_from")),
        )
        doc.highlights.sort(key=Highlight.sort_key)
        doc.bookmarks.sort(key=lambda b: (b.page, b.y))
        doc.answers.sort(key=Answer.sort_key)
        return doc


@dataclass
class RecentFile:
    path: str
    sha256: str
    title: str
    opened: float  # unix time

    def exists(self) -> bool:
        return Path(self.path).is_file()


class AnnotationStore:
    def __init__(self, root: Path):
        self.root = root
        self.ann_dir = root / "annotations"
        self.index_path = root / "index.json"
        self._index = self._load_index()

    # -- index (recents + hash cache)
    def _load_index(self) -> dict:
        raw = self._read_json(self.index_path)
        if not isinstance(raw, dict):
            raw = {}
        files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
        recents = raw.get("recent") if isinstance(raw.get("recent"), list) else []
        return {"dogear": SCHEMA_VERSION, "files": files, "recent": [r for r in recents if isinstance(r, dict)]}

    def _save_index(self) -> None:
        atomic_write_text(self.index_path, json.dumps(self._index, indent=2, ensure_ascii=False) + "\n")

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            # Keep the damaged file for recovery instead of overwriting it.
            backup = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            log.warning("Unreadable %s (%s); moved to %s", path, exc, backup)
            try:
                os.replace(path, backup)
            except OSError:
                pass
            return None

    def identify(self, path: Path) -> str:
        """SHA-256 of the file, cached by (path, size, mtime) so big PDFs are
        only hashed once per change."""
        path = path.resolve()
        st = path.stat()
        key = str(path)
        cached = self._index["files"].get(key)
        if (
            isinstance(cached, dict)
            and cached.get("size") == st.st_size
            and cached.get("mtime_ns") == st.st_mtime_ns
            and isinstance(cached.get("sha256"), str)
        ):
            return cached["sha256"]
        return file_sha256(path)

    def _remember_path(self, path: Path, sha: str) -> str | None:
        """Update the hash cache; returns the hash this path had before, if different."""
        st = path.stat()
        key = str(path)
        prev = self._index["files"].get(key)
        prev_sha = prev.get("sha256") if isinstance(prev, dict) else None
        self._index["files"][key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": sha}
        return prev_sha if isinstance(prev_sha, str) and prev_sha != sha else None

    # -- documents
    def annotation_path(self, sha: str) -> Path:
        return self.ann_dir / f"{sha}.json"

    def load(self, sha: str) -> DocAnnotations:
        raw = self._read_json(self.annotation_path(sha))
        if not isinstance(raw, dict):
            return DocAnnotations(sha256=sha)
        return DocAnnotations.from_dict(raw, sha)

    def has(self, sha: str) -> bool:
        return self.annotation_path(sha).is_file()

    def save(self, doc: DocAnnotations) -> None:
        atomic_write_text(
            self.annotation_path(doc.sha256),
            json.dumps(doc.to_dict(), indent=2, ensure_ascii=False) + "\n",
        )

    def open_document(self, path: Path, title: str = "") -> DocAnnotations:
        """Find (or create) the annotations for the PDF at `path`, and record
        it as recently opened. Does not write to the PDF."""
        path = path.resolve()
        sha = self.identify(path)
        prev_sha = self._remember_path(path, sha)
        doc = self.load(sha)
        if prev_sha and not self.has(sha) and self.has(prev_sha):
            # Same path, new content: carry the old annotations over.
            old = self.load(prev_sha)
            if not old.is_empty() or old.view.page:
                log.info("%s changed; carrying annotations over from %s", path, prev_sha[:12])
                doc = DocAnnotations.from_dict(old.to_dict(), sha)
                doc.carried_from = prev_sha
        doc.file_name = path.name
        if title:
            doc.title = title
        if str(path) not in doc.paths:
            doc.paths.append(str(path))
        self.save(doc)
        self.touch_recent(path, sha, title or doc.title or path.stem)
        return doc

    # -- recents
    def recents(self) -> list[RecentFile]:
        out = []
        for r in self._index["recent"]:
            if isinstance(r.get("path"), str):
                out.append(
                    RecentFile(
                        path=r["path"],
                        sha256=_str(r.get("sha256")),
                        title=_str(r.get("title")) or Path(r["path"]).stem,
                        opened=_num(r.get("opened")),
                    )
                )
        return out

    def touch_recent(self, path: Path, sha: str, title: str) -> None:
        key = str(path)
        rest = [r for r in self._index["recent"] if r.get("path") != key]
        self._index["recent"] = [{"path": key, "sha256": sha, "title": title, "opened": time.time()}] + rest[: MAX_RECENTS - 1]
        self._save_index()

    def forget_recent(self, path: str) -> None:
        self._index["recent"] = [r for r in self._index["recent"] if r.get("path") != path]
        self._save_index()
