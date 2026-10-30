"""Annotation store: highlights, notes, bookmarks and view state per PDF (no Qt).

Everything you make lives in the library folder (by default
~/Documents/Dogear), which can be synced between computers:

    <library folder>/
        Library/                    copies of the PDFs you mark up
        Notes/                      Markdown exports (the default export folder)
        .dogear/annotations/<sha256>.json   one document's annotations
        .dogear/library.json        your categories
        .dogear/removed/            documents taken out of the library

What belongs to one computer stays in $XDG_DATA_HOME/dogear/index.json:
the recent files and a cache of file hashes.

Annotations are keyed by the SHA-256 of the PDF's bytes, so a renamed or
moved PDF keeps them, the same PDF has the same annotations on every
computer, and the PDF itself is never written to. When the file at a known
path changes (a new revision of the same handout), its annotations are
carried over to the new hash so they are not lost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
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


def _strings(value: Any) -> list[str]:
    """A list of distinct non-empty strings, in order."""
    out: list[str] = []
    for v in value if isinstance(value, list) else []:
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


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
    indent: float = 0.0

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
    evenly spaced lines below it, like ruled paper. The first line starts
    `indent` right of `x` when it is a blank at the end of the question's
    own line. `context` is the text
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
    indent: float = 0.0

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
            "indent": round(self.indent, 2),
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
            indent=max(0.0, min(w, _num(raw.get("indent")))),
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
    # Library: categories the user filed it under, when it was first and
    # last opened, and what identifies other copies of the same book.
    categories: list[str] = field(default_factory=list)
    added: str = ""
    opened: float = 0.0  # unix time
    page_count: int = 0
    pdf_id: str = ""  # the PDF's permanent document ID (trailer /ID), hex
    declined: list[str] = field(default_factory=list)  # copies not to offer marks from again
    label: str = ""  # the user's own name for it; the PDF's title is re-read on every open
    # Where a copy of this PDF lives inside the library folder (relative,
    # with "/"), so the copy is found on every computer the folder syncs to.
    copy: str = ""

    def display_name(self) -> str:
        """What to call the document: your name for it, its title, its file name."""
        if self.label.strip():
            return self.label.strip()
        if self.title.strip():
            return self.title.strip()
        return Path(self.file_name).stem if self.file_name else self.sha256[:12]

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
        pitch: float = 0.0, lines: int = 1, indent: float = 0.0, size: float = 11.0, text: str = "",
        context: str = "",
    ) -> Answer:
        stamp = now_iso()
        ans = Answer(
            new_id(), page, x, y, w, max(0.0, pitch), max(1, lines), size, text, context, stamp, stamp,
            max(0.0, indent),
        )
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

    def counts(self) -> dict[str, int]:
        return {
            "highlights": len(self.highlights),
            "notes": len(self.notes) + sum(1 for h in self.highlights if h.note.strip()),
            "bookmarks": len(self.bookmarks),
            "answers": sum(1 for a in self.answers if a.text.strip()),
        }

    def adopt_marks(self, other: DocAnnotations) -> None:
        """Take over another copy's highlights, notes, bookmarks, answers,
        categories and reading position (as new items with new ids)."""
        copy = DocAnnotations.from_dict(other.to_dict(), self.sha256)
        for item in (*copy.highlights, *copy.bookmarks, *copy.notes, *copy.answers):
            item.id = new_id()
        self.highlights += copy.highlights
        self.bookmarks += copy.bookmarks
        self.notes += copy.notes
        self.answers += copy.answers
        self.highlights.sort(key=Highlight.sort_key)
        self.bookmarks.sort(key=lambda b: (b.page, b.y))
        self.answers.sort(key=Answer.sort_key)
        self.categories = sorted(set(self.categories) | set(copy.categories), key=str.casefold)
        if not self.view.page and not self.view.offset:
            self.view = copy.view
        self.carried_from = other.sha256

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
        data.update({
            "categories": self.categories,
            "added": self.added,
            "opened": round(self.opened, 3),
            "page_count": self.page_count,
            "pdf_id": self.pdf_id,
            "declined": self.declined,
            "label": self.label,
            "copy": self.copy,
        })
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
            categories=_strings(raw.get("categories")),
            added=_str(raw.get("added")),
            opened=max(0.0, _num(raw.get("opened"))),
            page_count=max(0, _int(raw.get("page_count"))),
            pdf_id=_str(raw.get("pdf_id")),
            declined=_strings(raw.get("declined")),
            label=_str(raw.get("label")),
            copy=_str(raw.get("copy")),
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


META_DIR = ".dogear"  # Dogear's own files inside the library folder
LIBRARY_DIR = "Library"  # copies of the PDFs inside the library folder
_SHA = re.compile(r"[0-9a-f]{64}")
# A sync service's conflict copy of <sha>.json: Syncthing's
# "<sha>.sync-conflict-….json", Dropbox's "<sha> (… conflicted copy …).json",
# Google Drive's "<sha> (1).json".
_CONFLICT = re.compile(r"^([0-9a-f]{64})(.+)\.json$")
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class AnnotationStore:
    """The library folder and this computer's own state.

    `root` is the library folder (by default ~/Documents/Dogear), which can be
    synced between computers. `local` holds what belongs to this computer
    only: the recent files and the cache of file hashes."""

    def __init__(self, root: Path, local: Path | None = None):
        self._set_root(root)
        self.local = local or root / META_DIR / "local"
        self.index_path = self.local / "index.json"
        self._legacy_categories: list[str] = []
        self._index = self._load_index()
        if self._legacy_categories:
            # Categories used to live in the local index; they sync now.
            for name in self._legacy_categories:
                self.add_category(name)
            self._save_index()

    def _set_root(self, root: Path) -> None:
        self.root = root
        self.meta_dir = root / META_DIR
        self.ann_dir = self.meta_dir / "annotations"
        self.removed_dir = self.meta_dir / "removed"
        self.library_path = self.meta_dir / "library.json"
        self.library_dir = root / LIBRARY_DIR
        self._copies: tuple[int, dict[str, Path]] | None = None

    # -- index (recents + hash cache), local to this computer
    def _load_index(self) -> dict:
        raw = self._read_json(self.index_path)
        if not isinstance(raw, dict):
            raw = {}
        files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
        recents = raw.get("recent") if isinstance(raw.get("recent"), list) else []
        self._legacy_categories = _strings(raw.get("categories"))
        return {
            "dogear": SCHEMA_VERSION,
            "files": files,
            "recent": [r for r in recents if isinstance(r, dict)],
        }

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

    def read_dict(self, sha: str) -> dict | None:
        """The document's file as last written, by any computer."""
        raw = self._read_json(self.annotation_path(sha))
        return raw if isinstance(raw, dict) else None

    def load(self, sha: str) -> DocAnnotations:
        raw = self.read_dict(sha)
        if raw is None:
            return DocAnnotations(sha256=sha)
        return DocAnnotations.from_dict(raw, sha)

    def has(self, sha: str) -> bool:
        return self.annotation_path(sha).is_file()

    def save(self, doc: DocAnnotations) -> dict:
        """Write the document's file; returns what was written."""
        data = doc.to_dict()
        atomic_write_text(self.annotation_path(doc.sha256), json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return data

    def save_synced(self, doc: DocAnnotations, base: dict | None) -> tuple[DocAnnotations, dict, bool]:
        """Save a document that is open here, keeping changes that reached
        its file since `base` (what this computer last read or wrote), such
        as edits synced in from another computer.

        Returns (the document as saved, what is on disk, whether it took in
        changes from the file)."""
        disk = self.read_dict(doc.sha256)
        if disk is None or base is None or disk == base:
            return doc, self.save(doc), False
        from .sync import merge

        merged = merge(DocAnnotations.from_dict(base, doc.sha256), doc, DocAnnotations.from_dict(disk, doc.sha256))
        data = merged.to_dict()
        if data != disk:
            # Only write what differs: an unchanged file must not bounce back
            # and forth between computers.
            data = self.save(merged)
        return merged, data, True

    def in_folder(self, path: Path) -> str | None:
        """The path inside the library folder ("Library/x.pdf"), or None
        when the file is somewhere else."""
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except (ValueError, OSError):
            return None

    def open_document(
        self, path: Path, title: str = "", *, page_count: int = 0, pdf_id: str = ""
    ) -> DocAnnotations:
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
                doc.copy = ""
        rel = self.in_folder(path)
        if rel is None or not doc.file_name:
            doc.file_name = path.name
        if title:
            doc.title = title
        if rel is None:
            # A place on this computer; the library folder's own files are
            # found through `copy` instead, on every computer.
            if str(path) not in doc.paths:
                doc.paths.append(str(path))
        elif not doc.copy or not (self.root / doc.copy).is_file():
            doc.copy = rel
        doc.added = doc.added or now_iso()
        doc.opened = time.time()
        doc.page_count = page_count or doc.page_count
        doc.pdf_id = pdf_id or doc.pdf_id
        self.save(doc)
        self.touch_recent(path, sha, doc.display_name())
        return doc

    # -- library
    def documents(self) -> list[DocAnnotations]:
        """Every document Dogear has opened."""
        out = []
        for f in sorted(self.ann_dir.glob("*.json")) if self.ann_dir.is_dir() else []:
            if _SHA.fullmatch(f.stem):
                out.append(self.load(f.stem))
        return out

    def _scan_copies(self) -> dict[str, Path]:
        """The PDFs in the Library folder by hash, for copies whose file was
        renamed there or that synced in before their notes did."""
        try:
            stamp = self.library_dir.stat().st_mtime_ns
        except OSError:
            return {}
        if self._copies and self._copies[0] == stamp:
            return self._copies[1]
        found: dict[str, Path] = {}
        before = len(self._index["files"])
        for f in sorted(self.library_dir.glob("*.pdf")):
            try:
                sha = self.identify(f)
                self._remember_path(f.resolve(), sha)
            except OSError:
                continue
            found.setdefault(sha, f)
        if len(self._index["files"]) != before:
            self._save_index()
        self._copies = (stamp, found)
        return found

    def _copy_name(self, doc: DocAnnotations) -> str:
        """A readable file name for a new copy: the PDF's own file name."""
        name = doc.file_name or f"{doc.display_name()}.pdf"
        stem = _UNSAFE_NAME.sub(" ", Path(name).stem).strip(" .") or doc.sha256[:12]
        if (self.library_dir / f"{stem}.pdf").exists():
            # Another PDF with the same name ("Lecture 1.pdf" from two classes).
            return f"{stem} ({doc.sha256[:8]}).pdf"
        return f"{stem}.pdf"

    def copy_path(self, sha: str, doc: DocAnnotations | None = None) -> Path:
        """The library folder's copy of a PDF, or where a new one would go."""
        doc = doc if doc is not None else self.load(sha)
        if doc.copy and (self.root / doc.copy).is_file():
            return self.root / doc.copy
        found = self._scan_copies().get(sha)
        if found is not None:
            return found
        return self.library_dir / self._copy_name(doc)

    def is_library_copy(self, path: Path) -> bool:
        """Whether a file lives inside the library folder."""
        return self.in_folder(path) is not None

    def keep_copy(self, doc: DocAnnotations, source: Path) -> bool:
        """Make sure the library folder holds this PDF, copying it into
        Library/ once. Sets `doc.copy`; the caller saves the document.
        True if the folder holds the PDF after."""
        existing = self.copy_path(doc.sha256, doc)
        if existing.is_file():
            doc.copy = self.in_folder(existing) or doc.copy
            return True
        if not source.is_file():
            return False
        own = self.in_folder(source)
        if own is not None:  # already in the folder: no second copy
            doc.copy = own
            return True
        self.library_dir.mkdir(parents=True, exist_ok=True)
        tmp = existing.with_name(f".{existing.name}.tmp")
        try:
            shutil.copyfile(source, tmp)
            if file_sha256(tmp) != doc.sha256:  # the source changed under us
                tmp.unlink()
                return False
            os.replace(tmp, existing)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        self._copies = None
        doc.copy = self.in_folder(existing) or ""
        return True

    def openable_path(self, doc: DocAnnotations) -> str:
        """Where to open a document from: the most recent path on this
        computer that still holds this exact file, else the library
        folder's copy, else ""."""
        for p in reversed(doc.paths):
            path = Path(p)
            try:
                if path.is_file() and self.identify(path) == doc.sha256:
                    return p
            except OSError:
                continue
        copy = self.copy_path(doc.sha256, doc)
        try:
            if copy.is_file() and self.identify(copy) == doc.sha256:
                return str(copy)
        except OSError:
            pass
        found = self._scan_copies().get(doc.sha256)
        return str(found) if found is not None else ""

    # -- categories, kept in the library folder so they sync
    def _listed_categories(self) -> list[str]:
        raw = self._read_json(self.library_path)
        return _strings(raw.get("categories")) if isinstance(raw, dict) else []

    def _write_categories(self, names: list[str]) -> None:
        data = {"dogear": SCHEMA_VERSION, "categories": sorted(dict.fromkeys(names), key=str.casefold)}
        atomic_write_text(self.library_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def categories(self) -> list[str]:
        """Your categories, including any a document synced in with before
        the category list itself arrived."""
        names = self._listed_categories()
        seen = {n.casefold() for n in names}
        for doc in self.documents():
            for c in doc.categories:
                if c.casefold() not in seen:
                    names.append(c)
                    seen.add(c.casefold())
        return sorted(names, key=str.casefold)

    def add_category(self, name: str) -> str:
        name = name.strip()
        cats = self._listed_categories()
        same = next((c for c in cats if c.casefold() == name.casefold()), None)
        if same is not None or not name:
            return same or ""
        self._write_categories(cats + [name])
        return name

    def rename_category(self, old: str, new: str) -> None:
        new = new.strip()
        cats = self._listed_categories()
        in_docs = any(old in d.categories for d in self.documents())
        if not new or (old not in cats and not in_docs):
            return
        clash = next((c for c in cats if c.casefold() == new.casefold() and c != old), None)
        cats = [c for c in cats if c != old]
        if clash is None:
            cats.append(new)
        self._write_categories(cats)
        target = clash or new
        for doc in self.documents():
            if old in doc.categories:
                doc.categories = sorted({target if c == old else c for c in doc.categories}, key=str.casefold)
                self.save(doc)

    def remove_category(self, name: str) -> None:
        """Delete a category. Documents in it stay in the library."""
        cats = self._listed_categories()
        if name in cats:
            self._write_categories([c for c in cats if c != name])
        for doc in self.documents():
            if name in doc.categories:
                doc.categories = [c for c in doc.categories if c != name]
                self.save(doc)

    def set_categories(self, sha: str, names: list[str]) -> DocAnnotations:
        doc = self.load(sha)
        doc.categories = sorted({self.add_category(n) for n in names if n.strip()} - {""}, key=str.casefold)
        self.save(doc)
        return doc

    def rename_document(self, sha: str, label: str) -> DocAnnotations:
        """Give a document your own name; empty goes back to its own title."""
        doc = self.load(sha)
        doc.label = label.strip()
        self.save(doc)
        for r in self._index["recent"]:
            if r.get("sha256") == sha:
                r["title"] = doc.display_name()
        self._save_index()
        return doc

    def remove_document(self, sha: str) -> Path | None:
        """Take a document out of the library: its marks and Dogear's copy of
        the PDF move to .dogear/removed/<sha>-<time>/ (restore by moving them
        back), and it leaves the recent list. The PDF itself is not touched,
        nor a PDF of yours that sits elsewhere in the library folder.
        Returns the folder they went to, or None if there was nothing."""
        ann = self.annotation_path(sha)
        doc = self.load(sha)
        copy = self.copy_path(sha, doc)
        dogear_copy = copy.is_file() and copy.parent.resolve() == self.library_dir.resolve()
        if not ann.is_file() and not dogear_copy:
            return None
        target = self.removed_dir / f"{sha}-{int(time.time())}"
        target.mkdir(parents=True, exist_ok=True)
        if ann.is_file():
            os.replace(ann, target / ann.name)
        if dogear_copy:
            os.replace(copy, target / copy.name)
            self._copies = None
        self._index["recent"] = [r for r in self._index["recent"] if r.get("sha256") != sha]
        # Forget which paths held it, so opening the PDF again starts fresh.
        self._index["files"] = {
            k: v for k, v in self._index["files"].items() if not (isinstance(v, dict) and v.get("sha256") == sha)
        }
        self._save_index()
        return target

    # -- sync conflicts and moving the library
    def resolve_conflicts(self) -> list[str]:
        """Merge the conflict copies a sync service left next to document
        files (and the category list) into them. Nothing is dropped: both
        versions' marks are kept, and the conflict copy itself moves to
        .dogear/removed/conflicts/. Returns the documents merged."""
        from .sync import merge

        merged: list[str] = []
        keep = self.removed_dir / "conflicts"
        for f in sorted(self.ann_dir.glob("*.json")) if self.ann_dir.is_dir() else []:
            m = _CONFLICT.match(f.name)
            if not m:
                continue
            sha = m.group(1)
            raw = self._read_json(f)
            if isinstance(raw, dict):
                theirs = DocAnnotations.from_dict(raw, sha)
                self.save(merge(None, self.load(sha), theirs) if self.has(sha) else theirs)
                merged.append(sha)
            if f.exists():
                keep.mkdir(parents=True, exist_ok=True)
                os.replace(f, keep / f.name)
        for f in sorted(self.meta_dir.glob("library*.json")) if self.meta_dir.is_dir() else []:
            if f.name == self.library_path.name:
                continue
            raw = self._read_json(f)
            if isinstance(raw, dict):
                self._write_categories(self._listed_categories() + _strings(raw.get("categories")))
            if f.exists():
                keep.mkdir(parents=True, exist_ok=True)
                os.replace(f, keep / f.name)
        if merged:
            log.info("Merged sync conflict copies of %d document(s)", len(merged))
        return merged

    def _absorb(self, src_ann: Path, copies: dict[str, Path], src_root: Path | None, src_removed: Path) -> int:
        """Take in documents from another library folder (or the old
        layout), merging with ones already here and moving their PDF copies
        into Library/. Returns how many documents came over."""
        from .sync import merge

        count = 0
        for f in sorted(src_ann.glob("*.json")):
            if not _SHA.fullmatch(f.stem):
                continue
            raw = self._read_json(f)
            if not isinstance(raw, dict):
                continue
            sha = f.stem
            theirs = DocAnnotations.from_dict(raw, sha)
            src_rel = theirs.copy
            doc = merge(None, self.load(sha), theirs) if self.has(sha) else theirs
            doc.copy = ""
            if src_rel and src_root is not None and sha not in copies:
                # A PDF of yours in the old folder stays there: remember it
                # as a place this computer has it.
                own = src_root / src_rel
                if own.is_file() and str(own.resolve()) not in doc.paths:
                    doc.paths.append(str(own.resolve()))
            target = self.copy_path(sha, doc)
            src_copy = copies.get(sha)
            if not target.is_file() and src_copy is not None and src_copy.is_file():
                self.library_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_copy), str(target))
                self._copies = None
            if target.is_file():
                doc.copy = self.in_folder(target) or ""
            self.save(doc)
            count += 1
        if src_removed.is_dir():
            for d in sorted(src_removed.iterdir()):
                dest = self.removed_dir / d.name
                if not dest.exists():
                    self.removed_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(d), str(dest))
        return count

    def _leave_note(self, folder: Path, moved_ann: Path) -> None:
        note = (
            f"Dogear moved this library to {self.root} on {now_iso()}.\n"
            f"The notes files as they were before the move are kept in {moved_ann.name}/.\n"
        )
        try:
            atomic_write_text(folder / "MOVED.txt", note)
        except OSError:
            pass

    def migrate_old_layout(self, old: Path) -> int:
        """Move a library from Dogear's first layout, where everything lived
        in $XDG_DATA_HOME/dogear, into the library folder. The old notes
        files are kept, renamed, next to a MOVED.txt. Returns how many
        documents came over."""
        src_ann = old / "annotations"
        if not src_ann.is_dir() or src_ann.resolve() == self.ann_dir.resolve():
            return 0
        copies = {f.stem: f for f in (old / "library").glob("*.pdf") if _SHA.fullmatch(f.stem)}
        count = self._absorb(src_ann, copies, None, old / "removed")
        moved = old / f"annotations.moved-{int(time.time())}"
        os.replace(src_ann, moved)
        for leftover in (old / "library", old / "removed"):
            try:
                leftover.rmdir()  # only when empty
            except OSError:
                pass
        self._leave_note(old, moved)
        log.info("Moved %d document(s) from %s to %s", count, old, self.root)
        return count

    def move_to(self, new_root: Path) -> int:
        """Move the library to another folder and use it from now on. A
        library already there (say, synced from another computer) is merged
        with this one. Your own PDFs elsewhere in the old folder stay where
        they are. Returns how many documents came over."""
        new_root = new_root.expanduser()
        if new_root.resolve() == self.root.resolve():
            return 0
        old_root, old_ann, old_meta, old_library = self.root, self.ann_dir, self.meta_dir, self.library_dir
        old_removed = self.removed_dir
        copies = {}
        for doc in self.documents():
            p = self.copy_path(doc.sha256, doc)
            if p.is_file() and p.parent.resolve() == old_library.resolve():
                copies[doc.sha256] = p
        cats = self._listed_categories()
        self._set_root(new_root)
        self.ann_dir.mkdir(parents=True, exist_ok=True)
        if cats:
            self._write_categories(self._listed_categories() + cats)
        count = self._absorb(old_ann, copies, old_root, old_removed) if old_ann.is_dir() else 0
        if old_ann.is_dir():
            moved = old_meta / f"annotations.moved-{int(time.time())}"
            os.replace(old_ann, moved)
            self._leave_note(old_meta, moved)
        log.info("Moved the library (%d document(s)) from %s to %s", count, old_root, self.root)
        return count

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
