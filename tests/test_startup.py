"""Start-up details: GTK's program name and the Qt log categories we quiet."""

import ctypes
import ctypes.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PySide6.QtCore import QLoggingCategory, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtPdf import QPdfDocument

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

from dogear import __main__ as entry


def _fit_outline_pdf(path: Path) -> None:
    """Two pages whose outline entries go to "fit page" destinations, as
    reportlab writes them; Qt PDF warns about each one."""
    stream = "BT /F1 24 Tf 72 700 Td (Hello) Tj ET"
    page = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 6 0 R >> >> >>"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R /Outlines 7 0 R >>",
        "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        page,
        page,
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Outlines /First 8 0 R /Last 9 0 R /Count 2 >>",
        "<< /Title (One) /Parent 7 0 R /Next 9 0 R /Dest [3 0 R /Fit] >>",
        "<< /Title (Two) /Parent 7 0 R /Prev 8 0 R /Dest [4 0 R /Fit] >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_text(out, encoding="latin-1")


@unittest.skipUnless(HAVE_QT, "PySide6 with QtPdf not installed")
class QtLoggingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls._tmp.name) / "fit.pdf"
        _fit_outline_pdf(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        QLoggingCategory.setFilterRules("")
        cls._tmp.cleanup()

    def outline_messages(self) -> list[str]:
        from dogear import pdf

        messages = []
        qInstallMessageHandler(lambda mode, context, message: messages.append(f"{context.category}: {message}"))
        try:
            doc = QPdfDocument()
            doc.load(str(self.pdf))
            outline = pdf.outline(doc)
            doc.close()
        finally:
            qInstallMessageHandler(None)
        self.assertEqual([(o["title"], o["page"], o["y"]) for o in outline], [("One", 0, 0.0), ("Two", 1, 0.0)])
        return [m for m in messages if m.startswith("qt.pdf.")]

    def test_bookmark_warnings_only_with_debug(self):
        QLoggingCategory.setFilterRules("")
        entry._quiet_qt_logging(True)
        self.assertTrue(self.outline_messages(), "the fixture should make Qt PDF warn")
        entry._quiet_qt_logging(False)
        self.assertEqual(self.outline_messages(), [])


class GtkProgramNameTest(unittest.TestCase):
    def test_sets_glib_prgname(self):
        name = ctypes.util.find_library("glib-2.0")
        if not name:
            self.skipTest("GLib not installed")
        glib = ctypes.CDLL(name)
        glib.g_get_prgname.restype = ctypes.c_char_p
        entry._set_gtk_program_name("dogear")
        self.assertEqual(glib.g_get_prgname(), b"dogear")


if __name__ == "__main__":
    unittest.main()
