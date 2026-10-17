"""Markdown export of a document's highlights, notes and bookmarks (no Qt).

The output is meant for a notes vault such as Obsidian: YAML front matter,
document notes first, then one section per page holding that page's
bookmarks, highlights (quoted, each with its note underneath) and the
answers written on its answer lines, in reading order.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .fsutil import atomic_write_text
from .store import DocAnnotations

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _quote(text: str) -> str:
    lines = text.strip().splitlines() or [""]
    return "\n".join(f"> {line}".rstrip() for line in lines)


def _tags(categories: list[str]) -> list[str]:
    """Library categories as Obsidian tags: 'Ruhi Book 5' -> ruhi-book-5."""
    out = []
    for name in categories:
        tag = re.sub(r"[^\w/-]+", "-", name.strip().casefold()).strip("-")
        if tag and not tag.isdigit() and tag not in out:
            out.append(tag)
    return out


def _answer(text: str) -> str:
    """'**A:** text', keeping the answer's own line breaks."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "**A:** " + "  \n".join(lines) + "  "


def page_heading(page: int, label: str) -> str:
    """'Page 3', or 'Page 3 (iii)' when the PDF labels the page differently."""
    number = str(page + 1)
    if label and label != number:
        return f"Page {number} ({label})"
    return f"Page {number}"


def export_filename(doc: DocAnnotations, fallback: str = "document") -> str:
    base = Path(doc.file_name).stem if doc.file_name else (doc.title or fallback)
    base = _UNSAFE_NAME.sub(" ", base).strip(" .") or fallback
    return f"{base}.md"


def render_markdown(
    doc: DocAnnotations,
    *,
    source_path: str = "",
    page_label: Callable[[int], str] | None = None,
    exported_at: datetime | None = None,
) -> str:
    title = doc.title or (Path(doc.file_name).stem if doc.file_name else "Untitled")
    stamp = (exported_at or datetime.now().astimezone()).isoformat(timespec="seconds")
    label = page_label or (lambda p: "")
    answers = [a for a in doc.answers if a.text.strip()]

    out: list[str] = [
        "---",
        f"title: {_yaml_str(title)}",
    ]
    if source_path:
        out.append(f"source: {_yaml_str(source_path)}")
    out += [
        f"sha256: {doc.sha256}",
        f"exported: {stamp}",
        f"highlights: {len(doc.highlights)}",
        f"bookmarks: {len(doc.bookmarks)}",
        f"answers: {len(answers)}",
        f"tags: [{', '.join(['dogear', *_tags(doc.categories)])}]",
        "---",
        "",
        f"# {title}",
        "",
        "*Exported from Dogear. This file is regenerated on every export, so keep your own edits elsewhere.*",
        "",
    ]

    if doc.notes:
        out += ["## Notes", ""]
        for note in doc.notes:
            text = note.text.strip()
            if text:
                out += [text, ""]

    pages = sorted({h.page for h in doc.highlights} | {b.page for b in doc.bookmarks} | {a.page for a in answers})
    for page in pages:
        out += [f"## {page_heading(page, label(page))}", ""]
        for bm in (b for b in doc.bookmarks if b.page == page):
            out.append(f"- **Bookmark:** {bm.name}")
        if any(b.page == page for b in doc.bookmarks):
            out.append("")
        # Highlights and answers interleaved top to bottom, as on the page.
        items: list[tuple[tuple, str, object]] = [(h.sort_key(), "h", h) for h in doc.highlights if h.page == page]
        items += [(a.sort_key(), "a", a) for a in answers if a.page == page]
        items.sort(key=lambda item: item[0])
        last_context = None
        for _, kind, item in items:
            if kind == "h":
                if last_context is not None:
                    out.append("")
                last_context = None
                out.append(_quote(item.text or "(no text)"))
                out.append(f"> — p. {page + 1} · {item.color}")
                out.append("")
                if item.note.strip():
                    out += [item.note.strip(), ""]
                continue
            # Blanks on one printed line share their question: show it once.
            if item.context and item.context != last_context:
                if last_context is not None:
                    out.append("")
                out.append(f"**Q:** {item.context}  ")
            last_context = item.context
            out.append(_answer(item.text))
        if last_context is not None:
            out.append("")

    if not doc.notes and not pages:
        out += ["*No highlights, notes, bookmarks or answers yet.*", ""]

    return "\n".join(out).rstrip("\n") + "\n"


def _belongs_to_other(path: Path, sha: str) -> bool:
    try:
        with path.open(encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    match = re.search(r"^sha256: ([0-9a-f]{64})$", head, re.MULTILINE)
    # A file without our front matter is the user's own: never overwrite it.
    return match is None or match.group(1) != sha


def export_markdown(
    doc: DocAnnotations,
    out_dir: Path,
    *,
    source_path: str = "",
    page_label: Callable[[int], str] | None = None,
) -> Path:
    target = out_dir / export_filename(doc)
    if _belongs_to_other(target, doc.sha256):
        # Two PDFs with the same file name (e.g. "Lecture 1.pdf" from two
        # classes) must not overwrite each other's export.
        target = target.with_name(f"{target.stem} ({doc.sha256[:8]}).md")
    atomic_write_text(target, render_markdown(doc, source_path=source_path, page_label=page_label))
    return target
