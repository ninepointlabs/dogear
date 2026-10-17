"""Find the answer lines on a page: printed rules, underscores, dotted lines.

Worksheets leave space for answers as horizontal lines. Dogear finds them in
the rendered page image instead of the text layer, because they come in
every form: drawn rules, runs of underscores, dot leaders, table borders.

The detection itself works on raw 8-bit grayscale bytes and has no Qt
dependency, so it is unit tested on synthetic images. `page_rules()` renders
a page with Qt PDF (UI thread only, see pdf.py) and feeds it in.

A rule is reported as a dict in PDF points, origin top-left:
    {"x", "y", "w"}  left end, vertical centre and length of the line
    "space"          blank height directly above it, where writing goes
"""

from __future__ import annotations

import re

from .store import clean_pdf_text

DARK = 200  # gray level below which a pixel counts as ink
_INK = bytes(1 if v < DARK else 0 for v in range(256))
_TO_MARK = bytes(ord("#") if v < DARK else ord(".") for v in range(256))

MIN_LENGTH_PT = 14.0  # shorter strokes are hyphens and dashes, not answer lines
SHORT_PT = 28.0  # below this a line needs clear space at both ends (not a dash)
SIDE_GAP_PT = 1.5
GROUP_MIN_PT = 120.0  # lines at least this long can form a ruled block
MAX_THICKNESS_PT = 3.0  # thicker is a filled bar or a picture
MIN_SPACE_PT = 7.0  # less room above means underlined text, not a blank
MAX_SPACE_PT = 40.0  # stop measuring the blank above at this height
GAP_PT = 2.5  # dots and dashes closer than this join into one line
MIN_FILL = 0.3  # share of a line's length that must be ink (dotted ok)


def _ink(row: bytes) -> int:
    """Number of ink pixels in a thresholded row of b'#' and b'.'."""
    return row.count(b"#")


def find_rules(gray: bytes, width: int, height: int, stride: int, scale: float) -> list[dict]:
    """Horizontal answer lines in a grayscale image of a page.

    `scale` is pixels per PDF point. Returns rules sorted top to bottom,
    then left to right.
    """
    if width <= 0 or height <= 0 or scale <= 0:
        return []
    marks = gray.translate(_TO_MARK)
    rows = [marks[r * stride:r * stride + width] for r in range(height)]
    gap = max(1, round(GAP_PT * scale))
    run_re = re.compile(rb"#(?:\.{0,%d}#)*" % gap)
    min_len = MIN_LENGTH_PT * scale

    # 1. Long, mostly-ink horizontal runs on each row.
    runs: list[tuple[int, int, int]] = []  # (row, x0, x1)
    for r, row in enumerate(rows):
        if _ink(row) < min_len * MIN_FILL:
            continue
        for m in run_re.finditer(row):
            x0, x1 = m.span()
            if x1 - x0 >= min_len and _ink(row[x0:x1]) >= (x1 - x0) * MIN_FILL:
                runs.append((r, x0, x1))

    # 2. Stack runs on neighbouring rows into bands (a line is 1-6 px thick).
    bands: list[list[int]] = []  # [top, bottom, x0, x1]
    open_bands: list[list[int]] = []
    for r, x0, x1 in runs:
        for band in open_bands:
            if band[1] >= r - 1 and min(x1, band[3]) - max(x0, band[2]) > 0.6 * min(x1 - x0, band[3] - band[2]):
                band[1] = r
                band[2] = min(band[2], x0)
                band[3] = max(band[3], x1)
                break
        else:
            band = [r, r, x0, x1]
            bands.append(band)
            open_bands.append(band)
        open_bands = [b for b in open_bands if b[1] >= r - 1]

    max_thick = max(1, round(MAX_THICKNESS_PT * scale))
    probe = max(2, round(1.0 * scale))
    max_space = round(MAX_SPACE_PT * scale)
    rules = []
    for top, bottom, x0, x1 in bands:
        if bottom - top + 1 > max_thick:
            continue
        span = x1 - x0
        inner0, inner1 = x0 + probe, x1 - probe

        # 3. Rows just below must be mostly blank. Text has strokes that run
        # on vertically; a line does not.
        below = bottom + probe
        if below < height and _ink(rows[below][x0:x1]) > 0.25 * span:
            continue

        # 4. A short line is only a blank with space at both ends (an em
        # dash looks the same but touches the letters beside it)...
        if span < SHORT_PT * scale and not (_clear_beside(rows, x0, top, bottom, scale, -1)
                                            and _clear_beside(rows, x1, top, bottom, scale, 1)):
            continue
        # ...and nothing right under it: the crossbar of an "H" or the top
        # of a "7" has its stems below.
        if span < SHORT_PT * scale and any(
            _ink(rows[r][x0:x1]) > 1 for r in range(bottom + 1, min(height, bottom + 1 + round(2.5 * scale)))
        ):
            continue

        # 5. A line with vertical strokes at both ends is the edge of a box
        # or a table, not something to write on.
        if _vertical_at(rows, x0, top, bottom, probe, scale) and _vertical_at(rows, x1 - probe, top, bottom, probe, scale):
            continue

        # 6. Measure the blank room above, where the answer is written.
        # Ignore a few stray pixels (descenders poking in, a table's
        # vertical borders at the ends).
        r = top - 1
        allowed = max(2, round(0.03 * span))
        while r >= 0 and top - r <= max_space and _ink(rows[r][inner0:inner1]) <= allowed:
            r -= 1
        space = (top - 1 - r) / scale
        if space < MIN_SPACE_PT:
            continue
        rules.append({
            "x": round(x0 / scale, 2),
            "y": round((top + bottom + 1) / 2 / scale, 2),
            "w": round(span / scale, 2),
            "space": round(space, 2),
        })
    rules.sort(key=lambda d: (d["y"], d["x"]))
    return _merge_split(rules)


def _clear_beside(rows: list[bytes], x: int, top: int, bottom: int, scale: float, side: int) -> bool:
    """No ink just left (side -1) or right (side 1) of a line end, from
    a little above the line down to it."""
    gap = max(2, round(SIDE_GAP_PT * scale))
    c0, c1 = (x - gap, x) if side < 0 else (x + 1, x + 1 + gap)
    c0, c1 = max(0, c0), min(len(rows[0]) if rows else 0, c1)
    if c1 <= c0:
        return True
    r0 = max(0, top - round(6.0 * scale))
    return all(b"#" not in rows[r][c0:c1] for r in range(r0, bottom + 1))


def _vertical_at(rows: list[bytes], x: int, top: int, bottom: int, probe: int, scale: float) -> bool:
    """Whether a vertical stroke leaves the line at column x, up or down."""
    reach = round(6.0 * scale)

    def solid(r0: int, r1: int) -> bool:
        if r0 < 0 or r1 > len(rows):
            return False
        return all(b"#" in rows[r][max(0, x - 1):x + probe + 1] for r in range(r0, r1))

    return solid(bottom + 1, bottom + 1 + reach) or solid(top - reach, top)


def _merge_split(rules: list[dict]) -> list[dict]:
    """Join pieces of one line that a crossing border split in two."""
    out: list[dict] = []
    for rule in rules:
        prev = out[-1] if out else None
        if prev and abs(prev["y"] - rule["y"]) < 1.0 and 0 <= rule["x"] - (prev["x"] + prev["w"]) < 3.0:
            prev["w"] = round(rule["x"] + rule["w"] - prev["x"], 2)
            prev["space"] = min(prev["space"], rule["space"])
            continue
        out.append(dict(rule))
    return out


def text_size(lines: list[dict]) -> float:
    """The page's usual font size in points, from its text line heights
    (0 when the page has no text)."""
    heights = sorted(ln["rect"][3] for ln in lines if ln["rect"][3] > 2)
    if not heights:
        return 0.0
    return heights[len(heights) // 2] * 1.05


def slot_from(rules: list[dict], index: int, size: float = 0.0) -> dict:
    """The writing area that starts at rules[index]: that line plus the
    evenly spaced lines right below it with the same left and right ends,
    like ruled paper under a question.

    Returns {"x", "y", "w", "pitch", "lines", "size"}: `y` is the first
    line, `pitch` the distance between lines (0 for a single line) and
    `size` a font size in points: the page's text size when given,
    shrunk if needed to fit the space.
    """
    first = rules[index]
    group = [first]
    pitch = 0.0
    # Short blanks stacked in a column (one per sentence) are separate
    # answers; ruled lines for writing are wide.
    for rule in rules[index + 1:] if first["w"] >= GROUP_MIN_PT else []:
        last = group[-1]
        d = rule["y"] - last["y"]
        if d < 1.0:
            continue  # another blank further along the same row
        if abs(rule["x"] - first["x"]) > 4.0 or abs(rule["x"] + rule["w"] - first["x"] - first["w"]) > 4.0:
            break
        if not 9.0 <= d <= 40.0 or (pitch and abs(d - pitch) > 0.15 * pitch):
            break
        pitch = pitch or d
        group.append(rule)
    room = min(first["space"], pitch) if pitch else first["space"]
    return {
        "x": first["x"],
        "y": first["y"],
        "w": round(min(r["x"] + r["w"] for r in group) - first["x"], 2),
        "pitch": round(pitch, 2),
        "lines": len(group),
        "size": round(max(6.0, min(size or 12.0, 13.0, room * (0.8 if size else 0.55))), 2),
    }


def rule_at(rules: list[dict], x: float, y: float) -> int:
    """Index of the line whose writing area contains (x, y), or -1.

    The area is the blank above the line (up to 24 pt) plus a little below
    it, so clicking on the line itself works too.
    """
    best, best_d = -1, 1e9
    for i, rule in enumerate(rules):
        if not rule["x"] - 2 <= x <= rule["x"] + rule["w"] + 2:
            continue
        above = min(rule["space"], 24.0)
        if rule["y"] - above <= y <= rule["y"] + 4.0:
            d = abs(rule["y"] - y)
            if d < best_d:
                best, best_d = i, d
    return best


def page_rules(doc, page: int) -> list[dict]:
    """Render `page` of a QPdfDocument and find its answer lines."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage

    size = doc.pagePointSize(page)
    w_pt, h_pt = size.width() or 612.0, size.height() or 792.0
    # Two pixels per point catches hairlines; keep huge pages bounded.
    scale = min(2.0, 2400.0 / max(w_pt, h_pt))
    img = doc.render(page, QSize(round(w_pt * scale), round(h_pt * scale)))
    if img.isNull():
        return []
    # Pages without a background render transparent; put them on white.
    if img.hasAlphaChannel():
        flat = QImage(img.size(), QImage.Format.Format_RGB32)
        flat.fill(0xFFFFFF)
        from PySide6.QtGui import QPainter

        painter = QPainter(flat)
        painter.drawImage(0, 0, img)
        painter.end()
        img = flat
    gray = img.convertToFormat(QImage.Format.Format_Grayscale8)
    data = bytes(gray.constBits())
    return find_rules(data, gray.width(), gray.height(), gray.bytesPerLine(), gray.width() / w_pt)


_ITEM = re.compile(r"^\s*(?:\(?[0-9]{1,3}[.)]|\(?[a-zA-Z][.)]|[ivxIVX]{1,4}[.)]|[•·\-–])\s")
_BLANK = re.compile(r"_{2,}|(?:\.\s?){4,}")
_SPACES = re.compile(r"\s+")


def context_for(lines: list[dict], x: float, y: float, max_lines: int = 3) -> str:
    """The printed text that goes with an answer line: the text on the
    line's row and the lines of the same item above it (the question).

    `lines` are the page's text lines in reading order, each
    {"text", "rect": [x, y, w, h]} in PDF points. Blanks printed as
    underscores or dots come out as "___".
    """
    def overlap(rect: list[float]) -> float:
        return min(rect[1] + rect[3], y + 1.0) - max(rect[1], y - 12.0)

    row = max(range(len(lines)), key=lambda i: overlap(lines[i]["rect"]), default=-1)
    if row < 0 or overlap(lines[row]["rect"]) <= 0:
        # The line has a row of its own: the question is the text above it.
        above = [i for i, ln in enumerate(lines) if ln["rect"][1] + ln["rect"][3] <= y]
        if not above:
            return ""
        row = max(above, key=lambda i: lines[i]["rect"][1] + lines[i]["rect"][3])
        if y - (lines[row]["rect"][1] + lines[row]["rect"][3]) > 60.0:
            return ""
    picked = [row]
    while len(picked) < max_lines and not _ITEM.match(lines[picked[0]]["text"]):
        prev = picked[0] - 1
        if prev < 0:
            break
        a, b = lines[prev]["rect"], lines[picked[0]]["rect"]
        # Contiguous: the same column and no paragraph gap in between.
        if not (0 <= b[1] - (a[1] + a[3]) <= max(a[3], b[3]) + 6.0) or abs(a[0] - b[0]) > 60.0:
            break
        picked.insert(0, prev)
    text = clean_pdf_text("\n".join(lines[i]["text"] for i in picked))
    text = _SPACES.sub(" ", _BLANK.sub("___", text)).strip()
    return text if len(text) <= 300 else "…" + text[-299:]
