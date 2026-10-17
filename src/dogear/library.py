"""The library: every document Dogear has opened, for browsing (no Qt).

Builds the rows of the library view (search, sort, category filter) and
recognizes other copies of a document you have already marked up, such as a
re-download or a new edition, whose bytes (and so whose hash) differ.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .store import AnnotationStore, DocAnnotations

SORTS = ("recent", "title", "marks", "added")
UNCATEGORIZED = "\x00none"  # category filter for documents in no category

# Version numbers and dates: the parts of a file name that change between
# editions of the same book ("…_2.1.1.PE_FullText_20210325").
_VERSIONISH = re.compile(r"^(v?\d+(\.\d+)+[a-z.]*|\d{6,8}|v\d+|rev\d*|final|draft)$", re.IGNORECASE)
_SPLIT = re.compile(r"[\s_\-()\[\],]+")


def _name_tokens(name: str) -> list[str]:
    base = name[:-4] if name.lower().endswith(".pdf") else name
    return [t for t in _SPLIT.split(base.casefold()) if t]


def same_name(a: str, b: str) -> bool:
    """Whether two titles or file names name the same book, ignoring
    version numbers and dates. 'Lecture 1' and 'Lecture 2' differ."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb or len(ta) != len(tb):
        return False
    shared = 0
    for x, y in zip(ta, tb):
        if x == y:
            shared += 1 if not _VERSIONISH.match(x) else 0
        elif not (_VERSIONISH.match(x) and _VERSIONISH.match(y)):
            return False
    return shared > 0


def _close_page_count(a: int, b: int) -> bool:
    return abs(a - b) <= max(2, round(0.05 * max(a, b)))


def is_copy_of(doc: DocAnnotations, other: DocAnnotations) -> bool:
    """Whether `other` looks like another copy or edition of `doc`."""
    if other.sha256 == doc.sha256:
        return False
    if doc.pdf_id and doc.pdf_id == other.pdf_id:
        return True
    # By name, the page counts must be known and close.
    if not (doc.page_count and other.page_count) or not _close_page_count(doc.page_count, other.page_count):
        return False
    names = [n for n in (doc.title, doc.file_name) if n]
    others = [n for n in (other.title, other.file_name) if n]
    return any(same_name(a, b) for a in names for b in others)


def find_copies(store: AnnotationStore, doc: DocAnnotations) -> list[DocAnnotations]:
    """Marked-up documents that look like other copies of `doc`, most
    marked first. Copies the user already declined are left out."""
    found = [
        other for other in store.documents()
        if not other.is_empty() and other.sha256 not in doc.declined and is_copy_of(doc, other)
    ]
    found.sort(key=lambda d: (-sum(d.counts().values()), -d.opened))
    return found


def _when(ts: float) -> str:
    if not ts:
        return ""
    then = datetime.fromtimestamp(ts)
    now = datetime.now()
    if then.date() == now.date():
        return then.strftime("Today %H:%M")
    if then.year == now.year:
        return then.strftime("%b %-d")
    return then.strftime("%b %-d, %Y")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds") if ts else ""


def _folder(path: str) -> str:
    return str(Path(path).parent).replace(str(Path.home()), "~", 1) if path else ""


def _opened(store: AnnotationStore, doc: DocAnnotations) -> float:
    """When the document was last opened. Documents from before the library
    have no time of their own: use the recent list, else the file's age."""
    if doc.opened:
        return doc.opened
    recent = next((r.opened for r in store.recents() if r.sha256 == doc.sha256 and r.opened), 0.0)
    if recent:
        return recent
    try:
        return store.annotation_path(doc.sha256).stat().st_mtime
    except OSError:
        return 0.0


def entry(store: AnnotationStore, doc: DocAnnotations) -> dict:
    """One row of the library view."""
    opened = _opened(store, doc)
    path = store.openable_path(doc)
    original = path if path and not store.is_library_copy(Path(path)) else ""
    last_path = doc.paths[-1] if doc.paths else ""
    counts = doc.counts()
    return {
        "sha256": doc.sha256,
        "title": doc.display_name(),
        "label": doc.label,
        "pdfTitle": doc.title,
        "fileName": doc.file_name or (Path(last_path).name if last_path else ""),
        "path": path,  # "" when neither the file nor a copy can be found
        "folder": _folder(original or last_path),
        "original": bool(original),
        "copy": store.copy_path(doc.sha256, doc).is_file(),
        "opened": opened,
        "openedText": _when(opened),
        "added": doc.added or _iso(opened),
        "pages": doc.page_count,
        "categories": doc.categories,
        "marks": sum(counts.values()),
        **counts,
    }


def _matches_marks(doc: DocAnnotations, needle: str) -> bool:
    texts = [h.text for h in doc.highlights] + [h.note for h in doc.highlights]
    texts += [n.text for n in doc.notes] + [a.text for a in doc.answers] + [b.name for b in doc.bookmarks]
    return any(needle in t.casefold() for t in texts)


def entries(
    store: AnnotationStore, query: str = "", sort: str = "recent", category: str = ""
) -> list[dict]:
    """Library rows filtered by a search query and a category, sorted.

    The query matches titles, file names, folders and categories; a row
    that matches only inside its highlights, notes or answers is marked
    with "inMarks"."""
    needle = query.strip().casefold()
    rows = []
    for doc in store.documents():
        if category == UNCATEGORIZED:
            if doc.categories:
                continue
        elif category and category not in doc.categories:
            continue
        row = entry(store, doc)
        row["inMarks"] = False
        if needle:
            hay = " ".join([row["title"], doc.title, row["fileName"], row["folder"], *doc.categories]).casefold()
            if needle not in hay:
                if not _matches_marks(doc, needle):
                    continue
                row["inMarks"] = True
        rows.append(row)
    if sort == "title":
        rows.sort(key=lambda r: r["title"].casefold())
    elif sort == "marks":
        rows.sort(key=lambda r: (-r["marks"], -r["opened"]))
    elif sort == "added":
        rows.sort(key=lambda r: (r["added"], r["opened"]), reverse=True)
    else:
        rows.sort(key=lambda r: -r["opened"])
    return rows


def category_counts(store: AnnotationStore) -> list[dict]:
    """The categories with how many documents are in each, plus the
    'All' and 'Uncategorized' entries, for the library's side list."""
    docs = store.documents()
    out = [{"key": "", "name": "All documents", "count": len(docs), "user": False}]
    for name in store.categories():
        out.append({"key": name, "name": name, "count": sum(name in d.categories for d in docs), "user": True})
    out.append({
        "key": UNCATEGORIZED, "name": "Uncategorized",
        "count": sum(not d.categories for d in docs), "user": False,
    })
    return out


_PDF_ID = re.compile(rb"/ID\s*\[\s*<([0-9A-Fa-f]+)>")


def pdf_id(path: Path) -> str:
    """The permanent part of a PDF's document ID, from the trailer. It stays
    the same across saves of one document; editions may share it too."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 256 * 1024))
            tail = fh.read()
            ids = _PDF_ID.findall(tail)
            if not ids and size > 256 * 1024:
                fh.seek(0)
                ids = _PDF_ID.findall(fh.read(256 * 1024))
    except OSError:
        return ""
    return ids[-1].decode("ascii").upper() if ids else ""
