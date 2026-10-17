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
    from PySide6.QtGui import QGuiApplication, QWheelEvent
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
        from PySide6.QtCore import qInstallMessageHandler

        # Qt warnings the app must never cause, collected for the test.
        cls.qt_warnings = []

        def collect(mode, context, message):
            if "inefficient loading" in message:
                cls.qt_warnings.append(message)

        qInstallMessageHandler(collect)
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
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(None)
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

        # Hovering a highlight that has a note shows the note; moving off hides it.
        QTest.mouseMove(self.window, self.pt_to_window(0, 150, 139))
        self.wait(350)
        self.assertTrue(self.page_view().property("noteTipVisible"))
        QTest.mouseMove(self.window, self.pt_to_window(0, 150, 300))
        self.wait(100)
        self.assertFalse(self.page_view().property("noteTipVisible"))
        # Hovering a highlight without a note shows nothing.
        QTest.mouseMove(self.window, self.pt_to_window(0, 150, 99))
        self.wait(350)
        self.assertFalse(self.page_view().property("noteTipVisible"))

        # One mouse-wheel notch glides down by one wheel step.
        y0 = self.page_view().property("scrollY")
        pos = QPointF(self.pt_to_window(0, 300, 300))
        QGuiApplication.sendEvent(self.window, QWheelEvent(
            pos, self.window.mapToGlobal(pos), QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        self.wait(40)
        mid = self.page_view().property("scrollY")
        self.wait(400)
        step = self.page_view().property("wheelStep")
        self.assertAlmostEqual(self.page_view().property("scrollY"), y0 + step, delta=1)
        self.assertLess(mid, y0 + step - 1, "wheel scroll should animate, not jump")
        # Notches in quick succession speed up: four fast ones go further
        # than four single steps.
        y1 = self.page_view().property("scrollY")
        for _ in range(4):
            QGuiApplication.sendEvent(self.window, QWheelEvent(
                pos, self.window.mapToGlobal(pos), QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
            self.wait(30)
        self.wait(400)
        self.assertGreater(self.page_view().property("scrollY") - y1, 4 * step * 1.2)
        self.page_view().forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Home)
        self.wait()

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

        # Answers: the last page is a worksheet with answer lines. Clicking
        # just above a line starts typing there; Tab moves to the next line.
        from PySide6.QtCore import QMetaObject, Q_ARG
        QMetaObject.invokeMethod(self.page_view(), "goToPage", Q_ARG("QVariant", 5), Q_ARG("QVariant", 400), Q_ARG("QVariant", False))
        self.wait(400)
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         self.pt_to_window(5, 300, 457))
        self.wait()
        self.type_text("Photosynthesis?")  # "?" must type, not open the shortcuts
        self.key(Qt.Key.Key_Tab)
        self.type_text("Carbon is fixed")
        self.key(Qt.Key.Key_Return)  # ruled lines: Enter is a new line
        self.type_text("into sugar")
        self.key(Qt.Key.Key_Tab)
        self.type_text("red")
        self.key(Qt.Key.Key_Return)  # a single blank: Enter moves on
        self.type_text("blue")
        # Qt fires no shortcut for a key combination listed twice, so each
        # Shortcut must list each combination once (StandardKey included).
        from PySide6.QtCore import QObject
        from PySide6.QtGui import QKeySequence
        shortcuts = [o for o in self.window.findChildren(QObject) if o.metaObject().className() == "QQuickShortcut"]
        self.assertGreater(len(shortcuts), 10)
        for sc in shortcuts:
            # (Qt reports a StandardKey entry twice; identical entries are one.)
            listed = list(dict.fromkeys(sc.property("sequences") or [])) or [sc.property("sequence")]
            combos = []
            for seq in listed:
                if isinstance(seq, int):
                    combos += [k.toString() for k in QKeySequence.keyBindings(QKeySequence.StandardKey(seq))]
                elif seq:
                    combos.append(QKeySequence(str(seq)).toString())
            self.assertEqual(len(combos), len(set(combos)), f"shortcut lists a key twice: {combos}")
        # Ctrl+= grows the answer's text, not the page.
        zoom_before = self.page_view().property("zoom")
        size_before = self.doc.answersOnPage(5)[-1]["size"]
        self.key(Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.page_view().property("zoom"), zoom_before)
        self.assertGreater(self.doc.answersOnPage(5)[-1]["size"], size_before)
        # Text too long for its line is squeezed to fit: Ctrl+= then can't
        # grow it, and A− / Ctrl+- shrinks it at once from the size shown.
        # (QTest can't send Ctrl+- on offscreen; the shortcut check above
        # covers the key reaching resizeAnswer.)
        editor = self.page_view().property("activeAnswer")
        size = editor.property("size")
        for words in range(2, 40):  # just too long, but not wrapping
            editor.setProperty("text", "blue " * words)
            self.wait(20)
            if editor.property("shownSize") < size * 0.85:
                break
        squeezed = editor.property("shownSize")
        self.assertLess(squeezed, size - 1)
        self.key(Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.property("size"), size)
        QMetaObject.invokeMethod(self.page_view(), "resizeAnswer", Q_ARG("QVariant", -1))
        self.wait()
        self.assertAlmostEqual(editor.property("shownSize"), squeezed / 1.1, delta=0.3)
        editor.setProperty("text", "blue")
        editor.setProperty("cursorPosition", 4)
        self.wait()
        self.type_text("!")  # still typing in the same answer
        self.key(Qt.Key.Key_Escape)
        answers = [a for p in range(6) for a in self.doc.answersOnPage(p)]
        self.assertEqual([a["text"] for a in answers], ["Photosynthesis?", "Carbon is fixed\ninto sugar", "red", "blue!"])
        self.assertEqual(answers[0]["context"], "1. Name of the process:")
        self.assertEqual(answers[1]["lines"], 3)
        self.assertEqual(answers[2]["context"], "3. Plants absorb ___ and ___ light.")
        # Clicking an empty spot that is not an answer line starts nothing;
        # clicking a line and leaving it blank leaves nothing behind.
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         self.pt_to_window(5, 300, 700))
        self.wait()
        self.assertEqual(sum(len(self.doc.answersOnPage(p)) for p in range(6)), 4)
        # Clicking an answer edits it: select all and delete removes it.
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         self.pt_to_window(5, 330, 619))
        self.wait()
        self.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.key(Qt.Key.Key_Delete)
        self.key(Qt.Key.Key_Escape)
        self.wait(100)
        self.assertEqual([a["text"] for a in self.doc.answersOnPage(5)], ["Photosynthesis?", "Carbon is fixed\ninto sugar", "red"])

        # Go to page 5 and zoom in; this is the position to restore.
        self.page_view().forceActiveFocus()
        self.page_view().setProperty("fitWidth", False)
        self.key(Qt.Key.Key_Plus)
        zoom = self.page_view().property("zoom")
        self.assertFalse(self.page_view().property("fitWidth"))
        self.page_view().metaObject()  # keep the wrapper alive
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
        self.assertIn("**Q:** 1. Name of the process:  \n**A:** Photosynthesis?", md)
        self.assertIn("**A:** Carbon is fixed  \ninto sugar", md)

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
        self.assertEqual(len(self.doc.answersOnPage(5)), 3)
        self.assertEqual(self.page_view().property("currentPage"), 4)
        self.assertAlmostEqual(self.page_view().property("zoom"), zoom, places=3)

        # Zooming never makes a page image reload the PDF file on its own
        # (an image left without its shared document does that).
        self.assertEqual(self.qt_warnings, [])

        # The original PDF was never touched and nothing was written next to it.
        self.assertEqual([p.name for p in self.pdf.parent.iterdir()], ["class notes.pdf"])
        self.assertEqual(self.pdf.read_bytes(), self.pdf_bytes)


    def library_rows(self):
        view = self.window.findChild(QQuickItem, "library")
        rows = view.property("rows")
        return rows.toVariant() if hasattr(rows, "toVariant") else rows

    def test_library_flow(self):
        """Runs after the end-to-end flow (alphabetical order) and uses its marks."""
        from PySide6.QtCore import QObject

        store = self.engine._dogear_refs[2]
        if not self.doc.loaded:
            self.assertTrue(self.doc.open(str(self.pdf)))
            self.wait(300)
        first_sha = store.identify(self.pdf)
        self.assertGreater(len(self.doc.highlights), 0, "needs the marks from test_end_to_end")
        # A marked-up PDF gets a private copy in the library.
        self.assertTrue(store.copy_path(first_sha).is_file())

        # Another download of the same book: different bytes, same name and pages.
        second = Path(self._tmp.name) / "new download" / "class notes.pdf"
        second.parent.mkdir()
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_pdf.py"), str(second), "6"],
                       check=True, capture_output=True)
        self.assertNotEqual(store.identify(second), first_sha)
        self.assertTrue(self.doc.open(str(second)))
        self.wait(300)
        dialog = self.window.findChild(QObject, "copyDialog")
        self.assertTrue(dialog.property("opened"), "offer to bring marks over")
        self.key(Qt.Key.Key_Return)
        self.wait(200)
        self.assertEqual(len(self.doc.highlights), 2)
        self.assertEqual(sum(len(self.doc.answersOnPage(p)) for p in range(6)), 3)
        second_sha = store.identify(second)
        self.assertTrue(store.copy_path(second_sha).is_file())

        # Back to the library (Ctrl+L): both copies, newest first.
        self.key(Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
        self.wait(300)
        self.assertFalse(self.doc.loaded)
        rows = self.library_rows()
        self.assertEqual([r["sha256"] for r in rows], [second_sha, first_sha])

        # File the newest under a new category with c, typing its name.
        self.key(Qt.Key.Key_C)
        self.type_text("Biology")
        self.key(Qt.Key.Key_Return)  # adds and ticks it
        self.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)  # saves
        self.wait(200)
        self.assertEqual(store.categories(), ["Biology"])
        self.assertEqual(store.load(second_sha).categories, ["Biology"])
        self.assertEqual(self.library_rows()[0]["categories"], ["Biology"])

        # Search inside marks: "/" then text from a note.
        self.key(Qt.Key.Key_Slash)
        self.type_text("on the exam")
        rows = self.library_rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["inMarks"] for r in rows))
        self.key(Qt.Key.Key_Escape)
        self.assertEqual(len(self.library_rows()), 2)

        # The original goes away: the library opens Dogear's copy.
        second.unlink()
        self.window.findChild(QQuickItem, "library").setProperty("rev", 99)
        self.wait(100)
        row = self.library_rows()[0]
        self.assertFalse(row["original"])
        self.assertEqual(row["path"], str(store.copy_path(second_sha)))
        self.key(Qt.Key.Key_Return)
        self.wait(300)
        self.assertTrue(self.doc.loaded)
        self.assertEqual(len(self.doc.highlights), 2)
        self.assertEqual(self.doc.fileName, "class notes.pdf")
        self.assertEqual(Path(self.doc.path), store.copy_path(second_sha))

        # Rename it (F2) for easier identification, then remove it (Del).
        self.key(Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
        self.wait(300)
        self.assertEqual(self.library_rows()[0]["sha256"], second_sha)
        self.key(Qt.Key.Key_F2)
        self.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.type_text("Biology, second download")
        self.key(Qt.Key.Key_Return)
        self.wait(200)
        row = self.library_rows()[0]
        self.assertEqual(row["title"], "Biology, second download")
        self.assertEqual(row["pdfTitle"], "Dogear sample")
        self.key(Qt.Key.Key_Delete)
        self.assertTrue(self.window.findChild(QObject, "confirmDialog").property("opened"))
        self.key(Qt.Key.Key_Return)
        self.wait(200)
        self.assertEqual([r["sha256"] for r in self.library_rows()], [first_sha])
        self.assertFalse(store.has(second_sha))
        self.assertEqual(len(list(store.removed_dir.glob(f"{second_sha}-*/{second_sha}.json"))), 1)
        # The first copy and its PDF are untouched.
        self.assertTrue(self.pdf.is_file())
        self.assertGreater(len(store.load(first_sha).highlights), 0)

    def test_sync_flow(self):
        """Runs last (alphabetical order): the library folder shared with
        another computer, and moving it from Settings."""
        import json

        store = self.engine._dogear_refs[2]
        if not self.doc.loaded:
            self.assertTrue(self.doc.open(str(self.pdf)))
            self.wait(300)
        sha = store.identify(self.pdf)
        self.assertEqual(store.root, Path(self._tmp.name) / "data" / "Dogear")
        self.assertTrue((store.ann_dir / f"{sha}.json").is_file())

        # Another computer adds a highlight; it syncs into the open document.
        before = len(self.doc.highlights)
        data = json.loads(store.annotation_path(sha).read_text())
        data["highlights"].append({"id": "fromotherpc", "page": 1, "rects": [[72, 100, 200, 14]],
                                   "text": "synced in", "color": "green", "created": "2026-10-17T10:00:00+00:00"})
        store.annotation_path(sha).with_name(".sync.tmp").write_text(json.dumps(data))
        os.replace(store.annotation_path(sha).with_name(".sync.tmp"), store.annotation_path(sha))
        self.wait_for(lambda: len(self.doc.highlights) == before + 1, msg="synced highlight")
        # This computer's next edit keeps it.
        self.doc.addBookmark(0, 0, "after sync")
        on_disk = json.loads(store.annotation_path(sha).read_text())
        self.assertIn("fromotherpc", [h["id"] for h in on_disk["highlights"]])
        self.assertIn("after sync", [b["name"] for b in on_disk["bookmarks"]])

        # Settings: move the library to a "Google Drive" folder.
        target = Path(self._tmp.name) / "Google Drive" / "Dogear"
        self.assertEqual(self.app_state.setLibraryFolder(str(target)), "")
        self.assertEqual(store.root, target)
        self.assertEqual(self.app_state.libraryFolder, str(target))
        self.assertTrue((target / ".dogear" / "annotations" / f"{sha}.json").is_file())
        self.assertTrue(store.copy_path(sha).is_file())
        self.assertEqual(store.copy_path(sha).parent, target / "Library")
        # The open document came along and still has its marks.
        self.assertTrue(self.doc.loaded)
        self.assertIn("synced in", [h["text"] for h in self.doc.highlights])
        from dogear import config

        self.assertEqual(config.load_settings().library_dir, str(target))
        # The export default follows the library folder (when not set).
        self.app_state.setExportDir("")
        self.assertEqual(self.app_state.exportDir, str(target / "Notes"))


if __name__ == "__main__":
    unittest.main()
