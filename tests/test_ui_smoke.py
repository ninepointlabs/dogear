"""End-to-end smoke test: drive the real QML app offscreen with mouse and keys.

Skipped when PySide6/QtPdf or Ghostscript (to build the sample PDF) is missing.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Never open real windows from tests, whatever the desktop session sets.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtPdf import QPdfDocument  # noqa: F401
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 with QtPdf not installed")
@unittest.skipUnless(shutil.which("gs"), "ghostscript needed to build the sample PDF")
class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        os.environ["DOGEAR_DATA_DIR"] = str(tmp / "data")
        os.environ["DOGEAR_CONFIG_DIR"] = str(tmp / "config")
        os.environ["DOGEAR_THEME_DIR"] = str(tmp / "no-theme")
        (tmp / "class").mkdir()
        cls.pdf = tmp / "class" / "class notes.pdf"
        cls.export_dir = tmp / "vault" / "Dogear"
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_pdf.py"), str(cls.pdf), "6"],
                       check=True, capture_output=True)
        cls.pdf_bytes = cls.pdf.read_bytes()
        from dogear.__main__ import create

        cls.app, cls.engine, cls.doc = create()
        assert cls.engine is not None, "QML failed to load"
        cls.window = cls.engine.rootObjects()[0]
        cls.window.resize(1200, 900)
        cls.app_state = cls.engine._dogear_refs[3]
        cls.app_state.setExportDir(str(cls.export_dir))

    @classmethod
    def tearDownClass(cls):
        cls.doc.close()
        cls.engine.deleteLater()
        cls._tmp.cleanup()

    # -- helpers
    def wait(self, ms=150):
        QTest.qWait(ms)

    def wait_for(self, cond, timeout=3000, msg="condition"):
        waited = 0
        while not cond():
            if waited >= timeout:
                self.fail(f"timed out waiting for {msg}")
            QTest.qWait(25)
            waited += 25

    def page_view(self) -> QQuickItem:
        return self.window.findChild(QQuickItem, "pageView")

    def pt_to_window(self, page: int, x: float, y: float) -> QPoint:
        view = self.page_view()
        s = view.property("pxPerPt")
        tops = view.property("tops").toVariant()
        content_w = view.property("contentW")
        size = self.doc.pageSizes[page]
        px = (content_w - size[0] * s) / 2 + x * s - view.property("scrollX")
        py = tops[page] + y * s - view.property("scrollY")
        p = view.mapToScene(QPointF(px, py))
        return QPoint(round(p.x()), round(p.y()))

    def drag(self, page, x1, y1, x2, y2):
        a, b = self.pt_to_window(page, x1, y1), self.pt_to_window(page, x2, y2)
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
        for i in range(1, 6):
            QTest.mouseMove(self.window, QPoint(a.x() + (b.x() - a.x()) * i // 5, a.y() + (b.y() - a.y()) * i // 5))
            self.wait(20)
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
        self.wait()

    def key(self, key, mods=Qt.KeyboardModifier.NoModifier, text=None):
        QTest.keyClick(self.window, key, mods)
        self.wait(60)

    def type_text(self, text):
        for ch in text:
            QTest.keyClick(self.window, ch)
        self.wait(60)

    # -- the flow
    def test_end_to_end(self):
        self.assertTrue(self.doc.open(str(self.pdf)))
        self.wait_for(lambda: self.page_view() is not None and self.page_view().property("ready"), msg="view ready")
        self.assertEqual(self.doc.pageCount, 6)
        self.assertEqual(len(self.doc.outline), 6)

        # Select line 1.1 on page 1 and highlight it green with key "2".
        self.drag(0, 73, 99, 330, 99)
        sel = self.page_view().property("selection")
        sel = sel.toVariant() if hasattr(sel, "toVariant") else sel
        self.assertTrue(sel and sel["text"].startswith("1.1 Photosynthesis"), sel)
        self.key(Qt.Key.Key_2)
        hls = self.doc.highlights
        self.assertEqual(len(hls), 1)
        self.assertEqual(hls[0]["color"], "green")
        self.assertTrue(hls[0]["text"].startswith("1.1 Photosynthesis"))

        # Select line 1.3, press "a" to highlight with a note, type, Ctrl+Enter.
        self.drag(0, 73, 139, 300, 139)
        self.key(Qt.Key.Key_A)
        self.type_text("on the exam")
        self.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        hls = self.doc.highlights
        self.assertEqual(len(hls), 2)
        noted = [h for h in hls if h["note"]]
        self.assertEqual(len(noted), 1)
        self.assertEqual(noted[0]["note"], "on the exam")
        self.assertEqual(noted[0]["color"], "green")  # last used color

        # Click the first highlight and recolor it pink with key "4".
        self.page_view().forceActiveFocus()
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         self.pt_to_window(0, 120, 99))
        self.wait()
        self.key(Qt.Key.Key_4)
        self.key(Qt.Key.Key_Escape)
        first = next(h for h in self.doc.highlights if h["text"].startswith("1.1"))
        self.assertEqual(first["color"], "pink")

        # Next page (J), bookmark it with b + Enter (default name from the outline).
        self.page_view().forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_J, Qt.KeyboardModifier.ShiftModifier)
        self.wait()
        self.assertEqual(self.page_view().property("currentPage"), 1)
        self.key(Qt.Key.Key_B)
        self.key(Qt.Key.Key_Return)
        self.assertEqual([b["name"] for b in self.doc.bookmarks], ["Chapter 2: Topic 2"])
        self.assertEqual(self.doc.bookmarks[0]["page"], 1)

        # A document note via Ctrl+N.
        self.key(Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        self.wait(200)
        self.type_text("Read chapter 3 before Monday")
        self.wait(600)
        self.key(Qt.Key.Key_Escape)
        self.assertEqual([n["text"] for n in self.doc.notes], ["Read chapter 3 before Monday"])

        # Search with "/" and jump to the first hit.
        self.page_view().forceActiveFocus()
        self.key(Qt.Key.Key_Slash)
        self.type_text("Calvin")
        self.wait_for(lambda: len(self.doc.searchResults) > 0, msg="search results")
        self.wait_for(lambda: self.page_view().property("searchIndex") >= 0, msg="jump to first hit")
        first_hit = self.page_view().property("searchIndex")
        # Search starts from the page being read (page 2), not page 1.
        self.assertGreaterEqual(self.doc.searchResults[first_hit]["page"], 1)
        self.key(Qt.Key.Key_Return)
        self.assertEqual(self.page_view().property("searchIndex"), first_hit + 1)
        self.key(Qt.Key.Key_Escape)
        self.assertEqual(self.doc.searchTerm, "")

        # Go to page 5 and zoom in; this is the position to restore.
        self.page_view().forceActiveFocus()
        self.page_view().setProperty("fitWidth", False)
        self.key(Qt.Key.Key_Plus)
        zoom = self.page_view().property("zoom")
        self.assertFalse(self.page_view().property("fitWidth"))
        self.page_view().metaObject()  # keep the wrapper alive
        from PySide6.QtCore import QMetaObject, Q_ARG
        QMetaObject.invokeMethod(self.page_view(), "goToPage", Q_ARG("QVariant", 4), Q_ARG("QVariant", 0), Q_ARG("QVariant", False))
        self.wait(500)
        self.assertEqual(self.page_view().property("currentPage"), 4)

        # Export to Markdown with Ctrl+E.
        self.key(Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
        md = (self.export_dir / "class notes.md").read_text()
        self.assertIn("## Page 1", md)
        self.assertIn("> 1.1 Photosynthesis", md)
        self.assertIn("on the exam", md)
        self.assertIn("- **Bookmark:** Chapter 2: Topic 2", md)
        self.assertIn("Read chapter 3 before Monday", md)

        if os.environ.get("DOGEAR_SMOKE_SHOT"):
            self.window.grabWindow().save(os.environ["DOGEAR_SMOKE_SHOT"])

        # Close (Ctrl+W) and reopen: everything comes back, including position.
        self.key(Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
        self.assertFalse(self.doc.loaded)
        self.assertTrue(self.doc.open(str(self.pdf)))
        self.wait_for(lambda: self.page_view() is not None and self.page_view().property("ready"), msg="view ready again")
        self.wait(200)
        self.assertEqual(len(self.doc.highlights), 2)
        self.assertEqual(len(self.doc.bookmarks), 1)
        self.assertEqual(len(self.doc.notes), 1)
        self.assertEqual(self.page_view().property("currentPage"), 4)
        self.assertAlmostEqual(self.page_view().property("zoom"), zoom, places=3)

        # The original PDF was never touched and nothing was written next to it.
        self.assertEqual([p.name for p in self.pdf.parent.iterdir()], ["class notes.pdf"])
        self.assertEqual(self.pdf.read_bytes(), self.pdf_bytes)


if __name__ == "__main__":
    unittest.main()
