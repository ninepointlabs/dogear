#!/usr/bin/env python3
"""Plays the demo scenes in the real Dogear, offscreen, and records them.

Run by make_media.py, which sets the environment: a scratch data, config and
library folder in work/, the site's palette as the Omarchy theme, and
QT_SCALE_FACTOR=1.5 so a 1280×720 window records at 1920×1080.

    record.py setup        open the demo PDFs once and mark the other courses
    record.py video        record work/out/<clip>.mp4 for each scene
    record.py shots        save the site's screenshots to work/out/shot-*.png

Recording runs in real time at 30 frames a second (a grab takes about 5 ms);
a frame that comes late is repeated, so the clip keeps time. The mouse
pointer is drawn into the frames; the app gets real mouse, wheel and key
events.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = HERE / "work"
OUT = WORK / "out"
PDFS = WORK / "home" / "Documents" / "Classes"
sys.path.insert(0, str(ROOT / "src"))

import time  # noqa: E402

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QWheelEvent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

FPS = 30
W, H = 1280, 720  # logical; frames are 1.5× that


class Recorder:
    def __init__(self):
        from dogear.__main__ import create

        self.app, self.engine, self.doc = create()
        if self.engine is None:
            sys.exit("QML failed to load")
        self.win = self.engine.rootObjects()[0]
        self.win.resize(W, H)
        self.win.show()
        self.store = self.engine._dogear_refs[2]
        self.state = self.engine._dogear_refs[3]
        self.ffmpeg = None
        self.t0 = 0.0
        self.written = 0
        self.cursor = QPointF(W * 0.6, H * 0.55)
        self.cursor_alpha = 0.0
        self.ripple = 0  # frames left of a click ring
        self.last = None
        self.frames(10)

    # -- frames
    def start(self, name: str):
        OUT.mkdir(parents=True, exist_ok=True)
        size = self.grab().size()
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{size.width()}x{size.height()}", "-r", str(FPS), "-i", "-",
             "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", str(OUT / f"{name}.mp4")],
            stdin=subprocess.PIPE)
        self.t0 = time.perf_counter()
        self.written = 0
        print(f"recording {name}", flush=True)

    def stop(self):
        if self.ffmpeg:
            self.ffmpeg.stdin.close()
            self.ffmpeg.wait()
            self.ffmpeg = None

    def grab(self) -> QImage:
        return self.win.grabWindow()

    def frames(self, n: int = 1):
        """Let n frame times (1/30 s each) pass, recording them."""
        for _ in range(max(1, n)):
            if self.ffmpeg is None:
                QTest.qWait(round(1000 / FPS))
                img = self.grab().convertToFormat(QImage.Format.Format_RGB888)
                self.draw_cursor(img)
                self.last = img
                continue
            # Wait for this frame's time, then grab it.
            due = self.t0 + (self.written + 1) / FPS
            wait = due - time.perf_counter()
            if wait > 0:
                QTest.qWait(max(1, round(wait * 1000)))
            else:
                QGuiApplication.processEvents()
            img = self.grab().convertToFormat(QImage.Format.Format_RGB888)
            self.draw_cursor(img)
            self.last = img
            raw = bytes(img.constBits())
            bpl, row = img.bytesPerLine(), img.width() * 3
            if bpl != row:
                raw = b"".join(raw[r * bpl:r * bpl + row] for r in range(img.height()))
            # Late? Repeat it, so the clip keeps real time.
            behind = int((time.perf_counter() - self.t0) * FPS) - self.written
            for _ in range(max(1, behind)):
                self.ffmpeg.stdin.write(raw)
                self.written += 1

    def hold(self, seconds: float):
        self.frames(round(seconds * FPS))

    def shot(self, name: str):
        self.frames(2)
        self.last.save(str(OUT / f"shot-{name}.png"))

    def draw_cursor(self, img: QImage):
        if self.cursor_alpha <= 0:
            return
        s = img.width() / W
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, y = self.cursor.x() * s, self.cursor.y() * s
        if self.ripple:
            r = (12 - self.ripple) * 2.2 * s + 6 * s
            p.setPen(QPen(QColor(244, 211, 94, int(220 * self.ripple / 12)), 3 * s))
            p.drawEllipse(QPointF(x, y), r, r)
            self.ripple -= 1
        path = QPainterPath()
        k = 1.25 * s
        pts = [(0, 0), (0, 17), (4.2, 13.2), (7.2, 20), (10, 18.8), (7, 12.2), (12.4, 12.2)]
        path.moveTo(x, y)
        for dx, dy in pts[1:]:
            path.lineTo(x + dx * k, y + dy * k)
        path.closeSubpath()
        a = int(255 * self.cursor_alpha)
        p.setPen(QPen(QColor(20, 20, 20, a), 1.6 * s))
        p.setBrush(QColor(255, 255, 255, a))
        p.drawPath(path)
        p.end()

    # -- the pointer
    def show_cursor(self, on: bool = True, frames: int = 6):
        for i in range(frames):
            self.cursor_alpha = (i + 1) / frames if on else 1 - (i + 1) / frames
            self.frames(1)

    def move(self, x: float, y: float, seconds: float = 0.7):
        if self.cursor_alpha < 1:
            self.show_cursor(True)
        start = QPointF(self.cursor)
        n = max(1, round(seconds * FPS))
        for i in range(1, n + 1):
            t = i / n
            e = 0.5 - math.cos(math.pi * t) / 2  # ease in and out
            self.cursor = QPointF(start.x() + (x - start.x()) * e, start.y() + (y - start.y()) * e)
            QTest.mouseMove(self.win, self.cursor.toPoint())
            self.frames(1)

    def click(self, x: float, y: float, seconds: float = 0.7, after: float = 0.25):
        self.move(x, y, seconds)
        QTest.mousePress(self.win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.cursor.toPoint())
        self.ripple = 12
        self.frames(2)
        QTest.mouseRelease(self.win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.cursor.toPoint())
        self.hold(after)

    def drag(self, x1, y1, x2, y2, seconds: float = 1.0):
        self.move(x1, y1)
        QTest.mousePress(self.win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.cursor.toPoint())
        self.frames(2)
        n = round(seconds * FPS)
        for i in range(1, n + 1):
            t = i / n
            e = 0.5 - math.cos(math.pi * t) / 2
            self.cursor = QPointF(x1 + (x2 - x1) * e, y1 + (y2 - y1) * e)
            QTest.mouseMove(self.win, self.cursor.toPoint())
            self.frames(1)
        QTest.mouseRelease(self.win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.cursor.toPoint())
        self.frames(3)

    def wheel(self, notches: int, gap_frames: int = 6):
        pos = QPointF(self.cursor)
        for _ in range(abs(notches)):
            ev = QWheelEvent(pos, self.win.mapToGlobal(pos), QPoint(), QPoint(0, -120 if notches > 0 else 120),
                             Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QGuiApplication.sendEvent(self.win, ev)
            self.frames(gap_frames)

    # -- keys
    def key(self, key, mods=Qt.KeyboardModifier.NoModifier, after: int = 4):
        QTest.keyClick(self.win, key, mods)
        self.frames(after)

    def type(self, text: str, per: int = 2):
        for ch in text:
            if ch == "\n":
                QTest.keyClick(self.win, Qt.Key.Key_Return)
            else:
                QTest.keyClick(self.win, ch)
            self.frames(per)

    # -- finding things
    def item(self, name: str) -> QQuickItem:
        found = self.win.findChild(QQuickItem, name)
        if found is None:
            sys.exit(f"no item {name}")
        return found

    def centre(self, item: QQuickItem, fx: float = 0.5, fy: float = 0.5) -> tuple[float, float]:
        p = item.mapToScene(QPointF(item.width() * fx, item.height() * fy))
        return p.x(), p.y()

    def delegate(self, list_name: str, test) -> QQuickItem:
        """A list delegate whose modelData passes `test`."""
        view = self.item(list_name)
        content = view.property("contentItem")
        for child in content.childItems():
            data = child.property("modelData")
            if data is not None:
                data = data.toVariant() if hasattr(data, "toVariant") else data
                if isinstance(data, dict) and test(data):
                    return child
        sys.exit(f"no matching row in {list_name}")

    def page_view(self) -> QQuickItem:
        return self.item("pageView")

    def pt(self, page: int, x: float, y: float) -> tuple[float, float]:
        """A point on a PDF page (points) in window coordinates."""
        view = self.page_view()
        s = view.property("pxPerPt")
        tops = view.property("tops")
        tops = tops.toVariant() if hasattr(tops, "toVariant") else tops
        size = self.doc.pageSizes[page]
        px = (view.property("contentW") - size[0] * s) / 2 + x * s - view.property("scrollX")
        py = tops[page] + y * s - view.property("scrollY")
        p = view.mapToScene(QPointF(px, py))
        return p.x(), p.y()

    def phrase(self, page: int, text: str) -> tuple[float, float, float, float]:
        """Where a phrase is printed on a page: (x1, y, x2, y) through the
        middle of its first and last lines, in points."""
        import re

        pdf = self.doc._pdf
        whole = pdf.getAllText(page).text()
        # The page's text breaks where its lines do.
        m = re.search(r"\s+".join(map(re.escape, text.split())), whole)
        if m is None:
            sys.exit(f"'{text}' not on page {page + 1}")
        i, j = m.span()
        first = pdf.getSelectionAtIndex(page, i, 1).boundingRectangle()
        last = pdf.getSelectionAtIndex(page, j - 1, 1).boundingRectangle()
        return (first.left() + 0.5, first.center().y(), last.right() - 0.5, last.center().y())

    def go_to(self, page: int, y: float = 0, animate: bool = False):
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(self.page_view(), "goToPage", Q_ARG("QVariant", page), Q_ARG("QVariant", y),
                                 Q_ARG("QVariant", animate))
        self.frames(6)


# ------------------------------------------------------------------ scenes

HANDOUT = PDFS / "Biology 101" / "Unit 3 - Photosynthesis.pdf"


def setup(r: Recorder):
    """Open each course PDF once and give the others a few marks, so the
    library looks lived in. Not recorded."""
    marks = {
        "Unit 2 - Cell Structure.pdf": ("Biology 101", ["mitochondria", "cell membrane"], ["Quiz Friday: organelles"]),
        "The Scientific Revolution.pdf": ("History 210", ["Galileo", "the printing press"], []),
        "Derivatives.pdf": ("Calculus I", ["chain rule"], ["Practice set 4, problems 1-12"]),
        "Preterite and Imperfect.pdf": ("Spanish 102", ["was happening", "completed"], []),
    }
    for path in sorted(PDFS.rglob("*.pdf")):
        if not r.doc.open(str(path)):
            sys.exit(f"could not open {path}")
        r.frames(8)
        category, words, notes = marks.get(path.name, ("Biology 101", [], []))
        for word in words:
            for page in range(r.doc.pageCount):
                whole = r.doc._pdf.getAllText(page).text()
                i = whole.find(word)
                if i >= 0:
                    sel = r.doc._pdf.getSelectionAtIndex(page, i, len(word))
                    rects = [[q.boundingRect().x(), q.boundingRect().y(), q.boundingRect().width(),
                              q.boundingRect().height()] for q in sel.bounds()]
                    r.doc.addHighlight(page, rects, word, "green" if "Spanish" in category else "yellow")
                    break
        for text in notes:
            r.doc.addNote(text)
        sha = r.store.identify(path)
        r.doc.close()
        r.state.setCategories(sha, [category])
    r.frames(10)


def scene_library(r: Recorder):
    r.start("02-library")
    r.hold(0.8)
    cat = r.delegate("categoryList", lambda d: d.get("name") == "Biology 101")
    r.click(*r.centre(cat, 0.3), seconds=0.9, after=0.6)
    r.click(*r.centre(r.item("librarySearch"), 0.25), after=0.2)
    r.type("unit", per=3)
    r.hold(0.6)
    row = r.delegate("libraryList", lambda d: d.get("fileName", "").startswith("Unit 3"))
    x, y = r.centre(row, 0.25)
    r.move(x, y, 0.6)
    r.hold(0.4)
    QTest.mouseDClick(r.win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r.cursor.toPoint())
    r.ripple = 12
    r.hold(1.2)
    r.stop()


def scene_read(r: Recorder):
    r.start("03-read")
    r.move(W * 0.55, H * 0.55, 0.5)
    r.show_cursor(False)
    r.hold(0.5)
    r.wheel(3, gap_frames=10)
    r.hold(0.9)
    r.key(Qt.Key.Key_J, after=6)
    r.key(Qt.Key.Key_J, after=6)
    r.key(Qt.Key.Key_J, after=12)
    r.wheel(4, gap_frames=3)
    r.hold(1.4)
    r.key(Qt.Key.Key_Home, after=20)
    r.stop()


def scene_highlight(r: Recorder):
    r.go_to(0, 150)
    r.frames(10)
    r.start("04-highlight")
    r.hold(0.4)
    x1, y1, _, _ = r.phrase(0, "Using only sunlight, water from the soil and carbon dioxide from the air")
    _, _, x3, y3 = r.phrase(0, "Using only sunlight, water from the soil and carbon dioxide from the air")
    a, b = r.pt(0, x1, y1), r.pt(0, x3, y3)
    r.drag(a[0], a[1], b[0], b[1], 1.2)
    r.hold(0.4)
    r.key(Qt.Key.Key_1, after=20)
    x1, y1, x2, y2 = r.phrase(0, "Their color comes from chlorophyll")
    a, b = r.pt(0, x1, y1), r.pt(0, x2, y2)
    r.drag(a[0], a[1], b[0], b[1], 0.9)
    r.hold(0.3)
    r.key(Qt.Key.Key_3, after=4)  # blue: the color the note goes with
    r.frames(6)
    # Click it to add a note.
    r.click(b[0] - 30, b[1], 0.5, after=0.4)
    r.key(Qt.Key.Key_E, after=4)
    r.type("Chlorophyll absorbs red + blue, reflects green", per=2)
    r.hold(0.4)
    r.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier, after=10)
    # Hover it: the note shows.
    r.move(b[0] - 60, b[1] - 2, 0.8)
    r.hold(1.6)
    r.shot("notes")
    r.move(W * 0.9, H * 0.5, 0.6)
    r.hold(0.3)
    r.stop()


def scene_answers(r: Recorder):
    last = r.doc.pageCount - 1
    r.go_to(last, 40)
    r.frames(12)
    r.start("05-answers")
    r.hold(0.5)
    rules = [x for x in r.doc.answersOnPage(last)]
    from dogear import rules as rules_mod

    found = rules_mod.page_rules(r.doc._pdf, last)
    first = found[0]
    r.click(*r.pt(last, first["x"] + 20, first["y"] - 4), 0.9, after=0.3)
    r.show_cursor(False)
    r.type("chlorophyll", per=2)
    r.key(Qt.Key.Key_Tab, after=6)
    r.type("red", per=2)
    r.key(Qt.Key.Key_Tab, after=6)
    r.type("blue", per=2)
    r.key(Qt.Key.Key_Tab, after=6)
    r.type("water", per=2)
    r.key(Qt.Key.Key_Tab, after=6)
    r.type("It fixes carbon dioxide from the air into sugar, using the ATP and\nNADPH that the light reactions made.", per=1)
    r.hold(0.4)
    r.key(Qt.Key.Key_Escape, after=10)
    r.hold(1.0)
    r.shot("answers")
    r.stop()
    del rules


def scene_sidebar(r: Recorder):
    # The site's hero: page one with its highlights listed. Not recorded.
    r.go_to(0, 40)
    r.frames(10)
    r.key(Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier, after=20)
    r.shot("hero")
    r.key(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, after=10)
    r.go_to(2, 60)
    r.frames(6)
    r.start("06-sidebar")
    r.hold(0.4)
    r.key(Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier, after=24)
    r.key(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, after=24)
    r.page_view().forceActiveFocus()
    r.key(Qt.Key.Key_B, after=8)
    r.key(Qt.Key.Key_Return, after=14)
    r.page_view().forceActiveFocus()
    r.key(Qt.Key.Key_Slash, after=4)
    r.type("rubisco", per=3)
    r.hold(0.8)
    r.key(Qt.Key.Key_Return, after=14)
    r.key(Qt.Key.Key_Return, after=14)
    r.shot("search")
    r.key(Qt.Key.Key_Escape, after=8)
    r.key(Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier, after=20)
    r.stop()


def scene_export(r: Recorder):
    r.start("07-export")
    r.hold(0.4)
    r.key(Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier, after=6)
    r.hold(2.0)
    r.stop()


def scene_sync(r: Recorder):
    r.key(Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier, after=10)
    r.frames(10)
    r.start("08-library")
    r.hold(0.6)
    search = r.item("librarySearch")
    r.click(*r.centre(search, 0.25), 0.7, after=0.2)
    r.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier, after=2)
    r.type("chlorophyll", per=3)
    r.hold(1.4)
    r.shot("library")
    r.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier, after=2)
    r.key(Qt.Key.Key_Backspace, after=10)
    r.click(*r.centre(r.item("librarySettings")), 0.8, after=0.6)
    field = r.item("libraryFolderField")
    r.click(*r.centre(field, 0.3), 0.6, after=0.2)
    r.type("~/Sync/Dogear", per=3)
    r.hold(1.6)
    r.shot("settings")
    r.key(Qt.Key.Key_Escape, after=10)
    r.hold(0.6)
    r.stop()


def video(r: Recorder):
    scene_library(r)
    scene_read(r)
    scene_highlight(r)
    scene_answers(r)
    scene_sidebar(r)
    scene_export(r)
    scene_sync(r)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "video"
    rec = Recorder()
    if what == "setup":
        setup(rec)
    elif what == "video":
        video(rec)
    rec.doc.close()
