"""A table of contents for PDFs that don't have one (no Qt).

Qt PDF gives text lines with their boxes, but no font names or weights, so
headings are recognised by what can be seen: a printed Contents page
("Life's Springtime ........ 1"), lines set clearly larger than the body
text, and lines like "SECTION 2" or "Chapter 4: Light" on their own.

Entries are {"title", "level", "page", "y"} like pdf.outline()'s, with
`y` the top of the heading in points. Building one reads every page's
text, so it is saved per PDF (by its hash) and only built once.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

from . import config
from .fsutil import atomic_write_text

log = logging.getLogger(__name__)

# Bump when the detection changes, so saved tables are built again.
VERSION = 1

# The printed Contents is looked for in the first pages only.
CONTENTS_PAGES = 15
# A line this much taller than the body text is a heading.
HEADING_RATIO = 1.2
# Levels of headings found by size; smaller sizes are left out.
MAX_SIZE_LEVELS = 3
# More headings of one size than this per page aren't headings.
MAX_PER_PAGE = 1.5

# "Title ........ 12", "Title . . . . 12" or "Title      xii"
_ENTRY = re.compile(r"^(?P<title>.*?\S)\s*(?:(?:\.\s*){3,}|…+|\s{3,})\s*(?P<page>\d{1,4}|[ivxlcdm]{1,7})$", re.I)
_NUMBERED = re.compile(
    r"^(?:section|chapter|unit|part|lesson|module)\s+(?:\d{1,3}|[ivxlc]{1,6}|[a-z])\b\s*(?:[.:–—-]\s*)?(?P<rest>.*)$", re.I
)
_CONTENTS_TITLE = re.compile(r"^(table of )?contents$", re.I)


def build(pages: list[list[dict]], labels: list[str]) -> list[dict]:
    """The table of contents for a document whose text lines are `pages`
    (pdf.text_lines() of each page) and page labels `labels`. Empty when
    nothing looks like headings."""
    heights = sorted(ln["rect"][3] for lines in pages for ln in lines if ln["rect"][3] > 2)
    if not heights:
        return []
    body = heights[len(heights) // 2]
    printed = _printed(pages, labels)
    if printed:
        # Headings before the first printed entry are the title pages and
        # the Contents itself; the printed entries say what the parts are.
        first = min(e["page"] for e in printed)
        deeper = max(e["level"] for e in printed) + 1
        extra = [
            {**h, "level": deeper} for h in _headings(pages, body, first)
            if not any(_same(h, e) for e in printed)
        ]
        out = printed + extra
    else:
        # The cover and title pages set the title in sizes used nowhere else.
        out = _headings(pages, body, 3 if len(pages) > 10 else 0)
    out.sort(key=lambda e: (e["page"], e["y"]))
    return out if len(out) >= 2 else []


def _cache_path(sha256: str) -> Path:
    return config.data_dir() / "contents" / f"{sha256}.json"


def load(sha256: str) -> list[dict] | None:
    """The saved table for this PDF; None when it hasn't been built (or
    was built by an older version). An empty list means no headings."""
    try:
        raw = json.loads(_cache_path(sha256).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("version") != VERSION or not isinstance(raw.get("entries"), list):
        return None
    out = []
    for e in raw["entries"]:
        try:
            out.append({"title": str(e["title"]), "level": int(e["level"]), "page": int(e["page"]), "y": float(e["y"])})
        except (KeyError, TypeError, ValueError):
            return None
    return out


def save(sha256: str, entries: list[dict]) -> None:
    try:
        atomic_write_text(_cache_path(sha256), json.dumps({"version": VERSION, "entries": entries}))
    except OSError as exc:
        log.warning("Could not save the table of contents: %s", exc)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'")).strip()


def _same(heading: dict, entry: dict) -> bool:
    """A found heading that is the printed entry itself."""
    if abs(heading["page"] - entry["page"]) > 1:
        return False
    a, b = _norm(heading["title"]), _norm(entry["title"])
    return bool(a) and bool(b) and (a == b or a.startswith(b) or b.startswith(a))


def _tidy(text: str) -> str:
    """Collapse spaces; SHOUTED headings in normal case."""
    text = " ".join(text.split())
    if text.isupper() and len(text) > 3:
        text = " ".join(w[:1] + w[1:].lower() for w in text.split(" "))
    return text


# -- the printed Contents page

def _printed(pages: list[list[dict]], labels: list[str]) -> list[dict]:
    by_label: dict[str, int] = {}
    for i, label in enumerate(labels):
        by_label.setdefault(label.strip().lower(), i)
    best: list[tuple[str, str, float, int]] = []
    for p, lines in enumerate(pages[:CONTENTS_PAGES]):
        entries = []
        pending = ""  # a long title's first line, before its page number
        for ln in lines:
            text = ln["text"].strip()
            m = _ENTRY.match(text)
            if m and re.search(r"[A-Za-z]", m["title"]):
                title = f"{pending} {m['title']}".strip() if pending else m["title"]
                entries.append((title.rstrip(" ."), m["page"].lower(), ln["rect"][0], p))
                pending = ""
            elif entries and not _CONTENTS_TITLE.match(text) and len(text) < 80:
                pending = text
            else:
                pending = ""
        # The Contents may run on to the next page.
        if best and entries and best[-1][3] == p - 1:
            best += entries
        elif len(entries) >= 3 and len(entries) > len(best):
            best = entries
    if len(best) < 3:
        return []
    contents_page = best[-1][3]  # the last, when it runs on
    lefts = sorted({round(x) for _, _, x, _ in best})
    levels: dict[int, int] = {}
    for x in lefts:  # indents a few points apart are the same level
        prev = next((k for k in levels if abs(k - x) <= 6), None)
        levels[x] = levels[prev] if prev is not None else len(set(levels.values()))
    out = []
    for title, label, x, _ in best:
        page = by_label.get(label)
        found = _find_title(pages, title, contents_page)
        # The printed numbers can differ from the PDF's own page labels
        # (a cover counted or not): where the title is printed wins.
        if found and (page is None or page <= contents_page or not _title_y(pages[page], title)):
            page = found[0]
        if page is None and label.isdigit():
            page = int(label) - 1
        if page is None or not 0 <= page < len(pages):
            continue
        y = found[1] if found and found[0] == page else _title_y(pages[page], title)
        out.append({"title": _tidy(title), "level": min(levels[round(x)], 2), "page": page, "y": y})
    return out if len(out) >= 3 else []


def _title_y(lines: list[dict], title: str) -> float:
    want = _norm(title)[:30]
    for ln in lines:
        if want and _norm(ln["text"]).startswith(want):
            return ln["rect"][1]
    return 0.0


def _find_title(pages: list[list[dict]], title: str, after: int) -> tuple[int, float] | None:
    """The page where a printed entry's title appears largest, after the
    Contents page."""
    want = _norm(title)[:30]
    best = None
    for p in range(after + 1, len(pages)):
        for ln in pages[p]:
            if want and _norm(ln["text"]).startswith(want):
                if best is None or ln["rect"][3] > best[2]:
                    best = (p, ln["rect"][1], ln["rect"][3])
    return (best[0], best[1]) if best else None


# -- headings in the text

def _headings(pages: list[list[dict]], body: float, start: int = 0) -> list[dict]:
    """Headings on pages from `start` on: lines set larger than the body
    text, the biggest the top level, then "Section 2" lines."""
    # Running headers and footers repeat on many pages: not headings.
    seen = Counter()
    for lines in pages:
        for t in {_norm(ln["text"]) for ln in lines}:
            seen[t] += 1
    repeated = {t for t, n in seen.items() if n > max(3, len(pages) // 10)}

    def usable(text: str) -> bool:
        n = _norm(text)
        return (
            2 <= len(text) <= 100 and n not in repeated and re.search(r"[A-Za-z]{2}", text) is not None
            and not _ENTRY.match(text) and not re.search(r"[$@]|:$", text)
        )

    found = []  # (size or 0 for "Section 2" lines, page, y, title)
    for p, lines in enumerate(pages):
        if p < start:
            continue
        i = 0
        while i < len(lines):
            ln = lines[i]
            text = ln["text"].strip()
            h = ln["rect"][3]
            # Headings start with a capital or a number and aren't sentences.
            if h >= body * HEADING_RATIO and usable(text) and re.match(r"[A-Z0-9]", text) and not re.search(r"[.,;]$", text):
                # A heading set on two or three lines is one entry.
                title, last = text, ln
                while (i + 1 < len(lines) and len(title) < 100
                       and abs(lines[i + 1]["rect"][3] - h) <= max(1.0, h * 0.08)
                       and 0 <= lines[i + 1]["rect"][1] - last["rect"][1] <= h * 1.6
                       and usable(lines[i + 1]["text"].strip())):
                    i += 1
                    last = lines[i]
                    title += " " + last["text"].strip()
                found.append((round(h), p, ln["rect"][1], title))
            elif len(text) <= 60 and _NUMBERED.match(text) and not re.search(r"[.,;]$", text) and usable(text):
                found.append((0, p, ln["rect"][1], text))
            i += 1
    # The biggest sizes are the top levels; "Section 2" lines go below them.
    sizes = sorted({s for s, *_ in found if s}, reverse=True)
    rank: dict[int, int] = {}
    for s in sizes:  # sizes within a point or two are one level
        prev = next((k for k in rank if abs(k - s) <= max(1, k * 0.08)), None)
        rank[s] = rank[prev] if prev is not None else len(set(rank.values()))
    # Headings are few: a size on every other line is a table or a form.
    per_level = Counter(rank[s] for s, *_ in found if s)
    scanned = max(1, len(pages) - start)
    kept = sorted(r for r, n in per_level.items() if n <= scanned * MAX_PER_PAGE)[:MAX_SIZE_LEVELS]
    out = []
    for s, p, y, title in found:
        if not s or rank[s] in kept:
            level = kept.index(rank[s]) if s else len(kept)
            out.append({"title": _tidy(title), "level": level, "page": p, "y": y})
    # Levels without gaps: 0, 1, 2.
    used = sorted({e["level"] for e in out})
    for e in out:
        e["level"] = min(used.index(e["level"]), MAX_SIZE_LEVELS - 1)
    return out
