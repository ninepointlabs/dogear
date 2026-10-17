"""Library: copies, categories, search, sort and matching other copies (no Qt)."""

import tempfile
import time
import unittest
from pathlib import Path

from dogear.library import (
    UNCATEGORIZED,
    category_counts,
    entries,
    find_copies,
    is_copy_of,
    pdf_id,
    same_name,
)
from dogear.store import AnnotationStore, DocAnnotations, Rect


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = AnnotationStore(self.tmp / "data")

    def tearDown(self):
        self._tmp.cleanup()

    def pdf(self, rel: str, content: bytes) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 " + content)
        return path

    def open(self, rel: str, content: bytes, pages=10, pid="", title="") -> DocAnnotations:
        return self.store.open_document(self.pdf(rel, content), title=title, page_count=pages, pdf_id=pid)


class TestNames(unittest.TestCase):
    def test_editions_match(self):
        self.assertTrue(same_name("RUHI0110_CC1_BK3_EN_2.1.1.PE_FullText_20210325.pdf",
                                  "RUHI0110_CC1_BK3_EN_2.2.1.PE_FullText_20210930.pdf"))
        self.assertTrue(same_name("Biology notes v2.pdf", "biology notes v3"))
        self.assertTrue(same_name("Biology 101.pdf", "Biology 101.pdf"))

    def test_different_books_do_not(self):
        self.assertFalse(same_name("Lecture 1.pdf", "Lecture 2.pdf"))
        self.assertFalse(same_name("Ruhi Book 12.1", "Ruhi Book 4"))
        self.assertFalse(same_name("2020.pdf", "2021.pdf"))  # nothing but versions
        self.assertFalse(same_name("Biology.pdf", "Chemistry.pdf"))
        self.assertFalse(same_name("", "x"))


class TestCopies(LibraryTestCase):
    def test_same_name_close_page_count(self):
        a = DocAnnotations("a", file_name="Bio 101.pdf", page_count=200)
        self.assertTrue(is_copy_of(a, DocAnnotations("b", file_name="Bio 101.pdf", page_count=204)))
        self.assertFalse(is_copy_of(a, DocAnnotations("b", file_name="Bio 101.pdf", page_count=150)))
        self.assertFalse(is_copy_of(a, DocAnnotations("b", file_name="Bio 101.pdf")))  # pages unknown
        self.assertFalse(is_copy_of(a, DocAnnotations("a", file_name="Bio 101.pdf", page_count=200)))  # itself

    def test_same_pdf_id_matches_whatever_the_name(self):
        a = DocAnnotations("a", file_name="download.pdf", pdf_id="ABC")
        self.assertTrue(is_copy_of(a, DocAnnotations("b", file_name="Bio 101.pdf", pdf_id="ABC")))
        self.assertFalse(is_copy_of(a, DocAnnotations("b", file_name="Bio 101.pdf", pdf_id="DEF")))

    def test_find_copies_only_marked_and_not_declined(self):
        old = self.open("v1/Bio 101.pdf", b"one")
        old.add_highlight(0, [Rect(1, 2, 3, 4)], "marked")
        self.store.save(old)
        self.open("v2/Bio 101.pdf", b"two")  # no marks: not offered
        new = self.open("v3/Bio 101.pdf", b"three")
        self.assertEqual([d.sha256 for d in find_copies(self.store, new)], [old.sha256])
        new.declined.append(old.sha256)
        self.assertEqual(find_copies(self.store, new), [])

    def test_adopt_marks(self):
        old = self.open("v1/Bio 101.pdf", b"one")
        hl = old.add_highlight(2, [Rect(1, 2, 3, 4)], "marked", note="exam")
        old.add_answer(3, 90, 100, 200, text="blue")
        old.add_note("doc note")
        old.add_bookmark(1, "Ch 1")
        old.categories = ["Biology"]
        old.view.page = 7
        new = self.open("v2/Bio 101.pdf", b"two")
        new.adopt_marks(old)
        self.assertEqual(new.counts(), {"highlights": 1, "notes": 2, "bookmarks": 1, "answers": 1})
        self.assertNotEqual(new.highlights[0].id, hl.id)
        self.assertEqual(new.highlights[0].note, "exam")
        self.assertEqual(new.categories, ["Biology"])
        self.assertEqual(new.view.page, 7)
        self.assertEqual(len(old.highlights), 1)  # the other copy keeps its own

    def test_pdf_id(self):
        path = self.pdf("x.pdf", b"stuff\ntrailer\n<< /ID [<0a1b2c> <ffee>] >>\n%%EOF")
        self.assertEqual(pdf_id(path), "0A1B2C")
        self.assertEqual(pdf_id(self.pdf("y.pdf", b"no id")), "")
        self.assertEqual(pdf_id(self.tmp / "missing.pdf"), "")


class TestLibraryCopies(LibraryTestCase):
    def test_copy_kept_and_used_when_original_is_gone(self):
        doc = self.open("class/Bio.pdf", b"bio")
        src = self.tmp / "class/Bio.pdf"
        self.assertTrue(self.store.keep_copy(doc.sha256, src))
        copy = self.store.copy_path(doc.sha256)
        self.assertEqual(copy.read_bytes(), src.read_bytes())
        self.assertEqual(self.store.openable_path(doc), str(src))
        src.unlink()
        self.assertEqual(self.store.openable_path(doc), str(copy))
        # Opening the copy doesn't record it as a place the user keeps the file.
        again = self.store.open_document(copy)
        self.assertEqual(again.paths, [str(src)])
        self.assertEqual(again.file_name, "Bio.pdf")

    def test_changed_file_at_old_path_is_not_this_document(self):
        doc = self.open("class/Bio.pdf", b"bio")
        self.pdf("class/Bio.pdf", b"a different file now")
        self.assertEqual(self.store.openable_path(doc), "")

    def test_copy_not_made_from_wrong_bytes(self):
        doc = self.open("class/Bio.pdf", b"bio")
        self.pdf("class/Bio.pdf", b"changed")
        self.assertFalse(self.store.keep_copy(doc.sha256, self.tmp / "class/Bio.pdf"))
        self.assertFalse(self.store.copy_path(doc.sha256).exists())


class TestCategories(LibraryTestCase):
    def test_add_rename_remove(self):
        a = self.open("a.pdf", b"a")
        b = self.open("b.pdf", b"b")
        self.assertEqual(self.store.add_category(" Biology "), "Biology")
        self.assertEqual(self.store.add_category("biology"), "Biology")  # no duplicates by case
        self.store.set_categories(a.sha256, ["Biology", "Exam 1"])
        self.store.set_categories(b.sha256, ["Exam 1"])
        self.assertEqual(self.store.categories(), ["Biology", "Exam 1"])
        self.store.rename_category("Exam 1", "Midterm")
        self.assertEqual(self.store.load(a.sha256).categories, ["Biology", "Midterm"])
        self.store.rename_category("Midterm", "biology")  # merge into an existing one
        self.assertEqual(self.store.categories(), ["Biology"])
        self.assertEqual(self.store.load(a.sha256).categories, ["Biology"])
        self.assertEqual(self.store.load(b.sha256).categories, ["Biology"])
        self.store.remove_category("Biology")
        self.assertEqual(self.store.categories(), [])
        self.assertEqual(self.store.load(a.sha256).categories, [])
        self.assertTrue(self.store.has(a.sha256))  # documents stay

    def test_counts(self):
        a = self.open("a.pdf", b"a")
        self.open("b.pdf", b"b")
        self.store.set_categories(a.sha256, ["Biology"])
        counts = {c["name"]: c["count"] for c in category_counts(self.store)}
        self.assertEqual(counts, {"All documents": 2, "Biology": 1, "Uncategorized": 1})

    def test_survive_reload(self):
        a = self.open("a.pdf", b"a")
        self.store.set_categories(a.sha256, ["Biology"])
        again = AnnotationStore(self.tmp / "data")
        self.assertEqual(again.categories(), ["Biology"])
        self.assertEqual(again.load(a.sha256).categories, ["Biology"])


class TestEntries(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.bio = self.open("class/Biology.pdf", b"bio", title="Biology")
        self.bio.add_highlight(0, [Rect(1, 2, 3, 4)], "The Calvin cycle fixes carbon")
        self.bio.add_highlight(1, [Rect(1, 2, 3, 4)], "Thylakoids")
        self.store.save(self.bio)
        time.sleep(0.01)
        self.art = self.open("hobby/Art.pdf", b"art", title="Art history")
        self.art.add_answer(0, 1, 2, 3, text="Monet")
        self.store.save(self.art)
        self.store.set_categories(self.bio.sha256, ["Science"])

    def titles(self, **kw):
        return [r["title"] for r in entries(self.store, **kw)]

    def test_sorts(self):
        self.assertEqual(self.titles(sort="recent"), ["Art history", "Biology"])
        self.assertEqual(self.titles(sort="title"), ["Art history", "Biology"])
        self.assertEqual(self.titles(sort="marks"), ["Biology", "Art history"])
        self.assertEqual(self.titles(sort="added"), ["Art history", "Biology"])

    def test_search_titles_folders_categories(self):
        self.assertEqual(self.titles(query="ART"), ["Art history"])
        self.assertEqual(self.titles(query="hobby"), ["Art history"])
        self.assertEqual(self.titles(query="science"), ["Biology"])
        self.assertEqual(self.titles(query="nothing like it"), [])

    def test_search_inside_marks(self):
        rows = entries(self.store, query="calvin")
        self.assertEqual([r["title"] for r in rows], ["Biology"])
        self.assertTrue(rows[0]["inMarks"])
        self.assertEqual(self.titles(query="monet"), ["Art history"])

    def test_category_filter(self):
        self.assertEqual(self.titles(category="Science"), ["Biology"])
        self.assertEqual(self.titles(category=UNCATEGORIZED), ["Art history"])
        self.assertEqual(self.titles(category=""), ["Art history", "Biology"])

    def test_row_fields(self):
        row = next(r for r in entries(self.store) if r["title"] == "Biology")
        self.assertEqual((row["highlights"], row["answers"], row["marks"]), (2, 0, 2))
        self.assertTrue(row["original"])
        self.assertEqual(row["fileName"], "Biology.pdf")
        self.assertTrue(row["openedText"])
        (self.tmp / "class/Biology.pdf").unlink()
        row = next(r for r in entries(self.store) if r["title"] == "Biology")
        self.assertEqual(row["path"], "")  # no copy was kept
        self.assertFalse(row["original"])


if __name__ == "__main__":
    unittest.main()


class TestRenameRemove(LibraryTestCase):
    def test_rename_survives_reopen_and_clears(self):
        doc = self.open("class/RUHI0110_CC1_BK3.pdf", b"bk3", title="RUHI0110_CC1_BK3")
        self.store.rename_document(doc.sha256, "  Book 3: Children's Classes  ")
        again = self.store.open_document(self.tmp / "class/RUHI0110_CC1_BK3.pdf", title="RUHI0110_CC1_BK3")
        self.assertEqual(again.display_name(), "Book 3: Children's Classes")
        self.assertEqual(again.title, "RUHI0110_CC1_BK3")
        row = entries(self.store)[0]
        self.assertEqual((row["title"], row["pdfTitle"]), ("Book 3: Children's Classes", "RUHI0110_CC1_BK3"))
        # Search finds it by either name.
        self.assertEqual(len(entries(self.store, query="children")), 1)
        self.assertEqual(len(entries(self.store, query="cc1_bk3")), 1)
        self.store.rename_document(doc.sha256, "")
        self.assertEqual(self.store.load(doc.sha256).display_name(), "RUHI0110_CC1_BK3")

    def test_display_name_fallbacks(self):
        self.assertEqual(DocAnnotations("a" * 64, file_name="x.pdf").display_name(), "x")
        self.assertEqual(DocAnnotations("a" * 64).display_name(), "a" * 12)

    def test_remove_moves_marks_and_copy_aside(self):
        doc = self.open("class/Bio.pdf", b"bio")
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], "kept safe")
        self.store.save(doc)
        src = self.tmp / "class/Bio.pdf"
        self.store.keep_copy(doc.sha256, src)
        target = self.store.remove_document(doc.sha256)
        self.assertFalse(self.store.has(doc.sha256))
        self.assertFalse(self.store.copy_path(doc.sha256).exists())
        self.assertEqual(entries(self.store), [])
        self.assertEqual([r for r in self.store.recents() if r.sha256 == doc.sha256], [])
        self.assertTrue(src.is_file())  # the PDF itself is untouched
        self.assertTrue((target / f"{doc.sha256}.json").is_file())
        self.assertTrue((target / f"{doc.sha256}.pdf").is_file())
        self.assertIsNone(self.store.remove_document(doc.sha256))
        # Opening the PDF again starts a fresh, empty document.
        again = self.store.open_document(src)
        self.assertTrue(again.is_empty())
