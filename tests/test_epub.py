"""EPUB books: reading the package, and laying a book out as a PDF once."""

import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dogear import epub  # noqa: E402
from dogear.store import AnnotationStore  # noqa: E402

_spec = importlib.util.spec_from_file_location("make_sample_epub", ROOT / "tools" / "make_sample_epub.py")
sample = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sample)

try:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtPdf import QPdfDocument

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


class PackageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_nav_toc(self):
        path = sample.build(self.tmp / "b.epub", 2)
        with zipfile.ZipFile(path) as z:
            book = epub.read_book(z)
        self.assertEqual(book.title, "Sample Book")
        self.assertEqual(book.author, "Dogear Tests")
        self.assertEqual(book.identifier, "urn:uuid:12345678-dog-ear-sample")
        self.assertEqual([p for p, _ in book.spine], ["OEBPS/text/ch1.xhtml", "OEBPS/text/ch2.xhtml"])
        self.assertEqual(book.toc[:2], [
            {"title": "Chapter 1: Topic 1", "level": 0, "href": "OEBPS/text/ch1.xhtml"},
            {"title": "More about topic 1", "level": 1, "href": "OEBPS/text/ch1.xhtml#more"},
        ])

    def test_ncx_toc_without_leaders(self):
        path = sample.build(self.tmp / "b.epub", 2, toc="ncx")
        with zipfile.ZipFile(path) as z:
            book = epub.read_book(z)
        # "Chapter 1: Topic 1 ........ 3" in the NCX.
        self.assertEqual([(e["title"], e["level"]) for e in book.toc],
                         [("Chapter 1: Topic 1", 0), ("More about topic 1", 1),
                          ("Chapter 2: Topic 2", 0), ("More about topic 2", 1)])

    def test_is_epub(self):
        path = sample.build(self.tmp / "b.epub", 1)
        renamed = self.tmp / "book.bin"
        renamed.write_bytes(path.read_bytes())
        self.assertTrue(epub.is_epub(path))
        self.assertTrue(epub.is_epub(renamed))
        other = self.tmp / "x.pdf"
        other.write_bytes(b"%PDF-1.4\n")
        self.assertFalse(epub.is_epub(other))

    def test_not_an_epub(self):
        bad = self.tmp / "bad.epub"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("mimetype", "application/epub+zip")
        with zipfile.ZipFile(bad) as z, self.assertRaises(epub.EpubError):
            epub.read_book(z)

    def test_chapter_html(self):
        raw = ('<html><head><title>T</title><style>p{color:red}</style></head><body>'
               '<h1 id="a b">Hi</h1><p>See <a href="x.xhtml#y">there</a>.</p>'
               '<svg><image xlink:href="../img/p.png"/></svg><img src="../img/q.png" alt="Q"/></body></html>')
        seen = []
        out = epub.chapter_html(raw, 4, "OEBPS/text/c.xhtml", lambda p: seen.append(p) or f"k{len(seen)}")
        self.assertIn('id="dg4-a_b"', out)
        self.assertNotIn("href", out)
        self.assertNotIn("color:red", out)
        self.assertNotIn("<svg", out)
        self.assertEqual(seen, ["OEBPS/img/p.png", "OEBPS/img/q.png"])
        self.assertIn('<img src="k2" alt="Q" />', out)


@unittest.skipUnless(HAVE_QT, "PySide6 with QtPdf not installed")
class RenditionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_render(self):
        book = sample.build(self.tmp / "in" / "b.epub", 3)
        before = book.read_bytes()
        pdf, meta = epub.rendition(book, "a" * 64, [self.tmp / "lib"])
        self.assertEqual(pdf, self.tmp / "lib" / f"{'a' * 64}.pdf")
        self.assertEqual(book.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in book.parent.iterdir()), ["b.epub"])
        doc = QPdfDocument()
        doc.load(str(pdf))
        self.assertEqual(doc.pageCount(), meta["pages"])
        self.assertGreater(doc.pageCount(), 3)
        self.assertEqual(doc.metaData(QPdfDocument.MetaDataField.Title), "Sample Book")
        self.assertEqual(doc.pagePointSize(0).width(), epub.PAGE_W)
        contents = epub.load_contents(pdf.with_suffix(".json"))
        self.assertEqual([e["title"] for e in contents if e["level"] == 0],
                         ["Chapter 1: Topic 1", "Chapter 2: Topic 2", "Chapter 3: Topic 3"])
        # Each entry is at its heading.
        for e in contents:
            text = doc.getAllText(e["page"]).text()
            self.assertIn(e["title"], text)
            from dogear import pdf as pdftext

            line = next(ln for ln in pdftext.text_lines(doc, e["page"]) if ln["text"] == e["title"])
            self.assertLess(abs(line["rect"][1] - e["y"]), 20)
        # Chapters start on a new page; the paragraphs are there.
        self.assertEqual([e["page"] for e in contents if e["level"] == 0][0], 0)
        self.assertIn("Paragraph 1 of chapter 2", doc.getAllText(contents[2]["page"]).text())
        doc.close()

    def test_made_once(self):
        book = sample.build(self.tmp / "b.epub", 2)
        first, _ = epub.rendition(book, "b" * 64, [self.tmp / "lib", self.tmp / "local"])
        stamp = first.stat().st_mtime_ns
        again, meta = epub.rendition(book, "b" * 64, [self.tmp / "lib", self.tmp / "local"])
        self.assertEqual(again, first)
        self.assertEqual(again.stat().st_mtime_ns, stamp)
        self.assertEqual(meta["title"], "Sample Book")
        # One found in a later folder (this computer's) is used too.
        local, _ = epub.rendition(book, "c" * 64, [self.tmp / "local"])
        found, _ = epub.rendition(book, "c" * 64, [self.tmp / "lib", self.tmp / "local"])
        self.assertEqual(found, local)

    def test_unwritable_library_falls_back(self):
        book = sample.build(self.tmp / "b.epub", 1)
        blocked = self.tmp / "file-not-folder"
        blocked.write_text("")
        pdf, _ = epub.rendition(book, "d" * 64, [blocked / "renditions", self.tmp / "local"])
        self.assertEqual(pdf.parent, self.tmp / "local")

    def test_drm_refused(self):
        book = sample.build(self.tmp / "b.epub", 1)
        with zipfile.ZipFile(book, "a") as z:
            z.writestr("META-INF/encryption.xml",
                       '<encryption><EncryptedData><EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
                       "</EncryptedData></encryption>")
        with self.assertRaises(epub.EpubError) as caught:
            epub.rendition(book, "e" * 64, [self.tmp / "lib"])
        self.assertIn("DRM", str(caught.exception))
        self.assertEqual(list((self.tmp / "lib").iterdir()), [])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = AnnotationStore(self.tmp / "Dogear", local=self.tmp / "local")

    def tearDown(self):
        self._tmp.cleanup()

    def test_copy_keeps_epub_name(self):
        book = sample.build(self.tmp / "class" / "My Book.epub", 1)
        doc = self.store.open_document(book, title="Sample Book", page_count=4)
        doc.add_bookmark(0, "Start")
        self.assertTrue(self.store.keep_copy(doc, book))
        self.assertEqual(doc.copy, "Library/My Book.epub")
        self.assertEqual([f.name for f in self.store.copy_files()], ["My Book.epub"])
        book.unlink()
        self.assertEqual(self.store.openable_path(doc), str(self.tmp / "Dogear" / "Library" / "My Book.epub"))

    def test_rendition_folders(self):
        self.assertEqual(self.store.rendition_folders(),
                         [self.tmp / "Dogear" / ".dogear" / "renditions", self.tmp / "local" / "renditions"])

    def test_remove_and_move_take_renditions(self):
        book = sample.build(self.tmp / "b.epub", 1)
        doc = self.store.open_document(book, page_count=4)
        doc.add_bookmark(0, "Start")
        self.store.save(doc)
        r = self.store.renditions_dir
        r.mkdir(parents=True)
        (r / f"{doc.sha256}.pdf").write_bytes(b"%PDF")
        (r / f"{doc.sha256}.json").write_text(json.dumps({"contents": []}))
        self.store.move_to(self.tmp / "Moved")
        self.assertTrue((self.tmp / "Moved" / ".dogear" / "renditions" / f"{doc.sha256}.pdf").is_file())
        self.assertTrue((self.tmp / "Moved" / ".dogear" / "renditions" / f"{doc.sha256}.json").is_file())
        target = self.store.remove_document(doc.sha256)
        self.assertEqual(sorted(p.name for p in target.iterdir()), [f"{doc.sha256}.json", "rendition.json", "rendition.pdf"])
        self.assertEqual(list(self.store.renditions_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
