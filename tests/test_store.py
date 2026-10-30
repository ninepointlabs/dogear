import json
import os
import tempfile
import unittest
from pathlib import Path

from dogear.store import (
    Answer,
    AnnotationStore,
    DocAnnotations,
    Highlight,
    Rect,
    ViewState,
    clean_pdf_text,
    file_sha256,
)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "data"
        self.pdf = self.tmp / "Biology 101.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake content one")
        self.store = AnnotationStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()


class TestDocAnnotations(unittest.TestCase):
    def test_highlight_crud_and_ordering(self):
        doc = DocAnnotations(sha256="x")
        low = doc.add_highlight(2, [Rect(72, 300, 100, 12)], "later on page")
        high = doc.add_highlight(2, [Rect(72, 100, 100, 12)], "earlier on page")
        first = doc.add_highlight(0, [Rect(72, 500, 100, 12)], "first page", color="green")
        self.assertEqual([h.id for h in doc.highlights], [first.id, high.id, low.id])
        doc.update_highlight(high.id, color="pink", note="remember this")
        self.assertEqual(doc.highlight(high.id).color, "pink")
        self.assertEqual(doc.highlight(high.id).note, "remember this")
        self.assertEqual(len(doc.highlights_on_page(2)), 2)
        self.assertTrue(doc.remove_highlight(low.id))
        self.assertFalse(doc.remove_highlight(low.id))
        self.assertEqual(len(doc.highlights), 2)

    def test_rejects_unknown_color(self):
        doc = DocAnnotations(sha256="x")
        with self.assertRaises(ValueError):
            doc.add_highlight(0, [], "t", color="chartreuse")
        hl = doc.add_highlight(0, [], "t")
        with self.assertRaises(ValueError):
            doc.update_highlight(hl.id, color="chartreuse")
        with self.assertRaises(KeyError):
            doc.update_highlight("missing", note="x")

    def test_bookmarks_default_name_and_order(self):
        doc = DocAnnotations(sha256="x")
        b2 = doc.add_bookmark(4, "  ")
        b1 = doc.add_bookmark(1, "Intro")
        self.assertEqual(b2.name, "Page 5")
        self.assertEqual([b.id for b in doc.bookmarks], [b1.id, b2.id])
        doc.rename_bookmark(b1.id, "Introduction")
        self.assertEqual(doc.bookmarks[0].name, "Introduction")
        self.assertTrue(doc.remove_bookmark(b1.id))
        self.assertEqual(len(doc.bookmarks), 1)

    def test_notes(self):
        doc = DocAnnotations(sha256="x")
        n = doc.add_note("exam on friday")
        stamp = n.updated
        doc.update_note(n.id, "exam on friday")
        self.assertEqual(n.updated, stamp)
        doc.update_note(n.id, "exam moved to monday")
        self.assertEqual(doc.notes[0].text, "exam moved to monday")
        self.assertTrue(doc.remove_note(n.id))
        self.assertTrue(doc.is_empty())

    def test_answers(self):
        doc = DocAnnotations(sha256="x")
        later = doc.add_answer(1, 90, 300, 400, pitch=24, lines=3, indent=150, size=12, context="2. Explain")
        first = doc.add_answer(1, 210, 120, 300, context="1. Name:")
        other = doc.add_answer(0, 50, 500, 200)
        self.assertEqual([a.id for a in doc.answers], [other.id, first.id, later.id])
        self.assertEqual(later.bottom(), 348)
        self.assertEqual(first.bottom(), 120)
        # The first line's indent is kept, and older files without one load.
        self.assertEqual(Answer.from_dict(later.to_dict()).indent, 150)
        self.assertEqual(Answer.from_dict({**first.to_dict(), "indent": None}).indent, 0)
        doc.set_answer_text(first.id, "Photosynthesis")
        self.assertEqual(doc.answer(first.id).text, "Photosynthesis")
        self.assertEqual(len(doc.answers_on_page(1)), 2)
        with self.assertRaises(KeyError):
            doc.set_answer_text("missing", "x")
        doc.set_answer_size(first.id, 9.5)
        self.assertEqual(doc.answer(first.id).size, 9.5)
        with self.assertRaises(ValueError):
            doc.set_answer_size(first.id, 500)
        self.assertFalse(doc.is_empty())
        self.assertTrue(doc.remove_answer(other.id))
        self.assertFalse(doc.remove_answer(other.id))

    def test_blank_answers_are_not_saved(self):
        doc = DocAnnotations(sha256="x")
        kept = doc.add_answer(0, 50, 100, 200, text="blue")
        doc.add_answer(0, 50, 200, 200, text="  ")
        data = doc.to_dict()
        self.assertEqual([a["id"] for a in data["answers"]], [kept.id])
        back = DocAnnotations.from_dict(data, "x")
        self.assertEqual([(a.text, a.x, a.y, a.w) for a in back.answers], [("blue", 50, 100, 200)])

    def test_answers_from_dict_tolerate_garbage(self):
        doc = DocAnnotations.from_dict({"answers": [
            {"page": 0, "x": 10, "y": 20, "w": 0, "text": "no width"},
            {"page": -1, "x": 10, "y": 20, "w": 50, "text": "bad page"},
            {"page": 2, "x": 10, "y": 20, "w": 50, "text": "ok", "size": 999, "lines": 0, "pitch": -3},
            "junk",
        ]}, "x")
        self.assertEqual(len(doc.answers), 1)
        a = doc.answers[0]
        self.assertEqual((a.size, a.lines, a.pitch), (11.0, 1, 0.0))

    def test_round_trip(self):
        doc = DocAnnotations(sha256="abc", file_name="a.pdf", title="A")
        doc.view = ViewState(page=7, offset=0.25, zoom=1.5, fit_width=False, x=0.1)
        doc.add_highlight(3, [Rect(1.234, 2, 3, 4)], "text", "blue", "note")
        doc.add_bookmark(2, "Mark", y=120.5)
        doc.add_note("general")
        again = DocAnnotations.from_dict(json.loads(json.dumps(doc.to_dict())), "abc")
        self.assertEqual(again.to_dict(), doc.to_dict())
        self.assertEqual(again.view.page, 7)
        self.assertFalse(again.view.fit_width)

    def test_from_dict_tolerates_garbage(self):
        raw = {
            "view": {"page": -3, "zoom": 99, "offset": 7},
            "highlights": [
                {"page": 1, "rects": [[1, 2, 3, 4], [1, 2], "x", [1, 2, -3, 4]], "color": "neon", "text": 5},
                {"page": "two"},
                "nonsense",
            ],
            "bookmarks": [{"page": 0, "name": "ok"}, {"name": "no page"}],
            "notes": [{"text": "hi"}, 3],
        }
        doc = DocAnnotations.from_dict(raw, "s")
        self.assertEqual(doc.view.page, 0)
        self.assertEqual(doc.view.zoom, 1.0)
        self.assertEqual(doc.view.offset, 1.0)
        self.assertEqual(len(doc.highlights), 1)
        hl = doc.highlights[0]
        self.assertEqual(len(hl.rects), 1)
        self.assertEqual(hl.color, "yellow")
        self.assertEqual(hl.text, "")
        self.assertTrue(hl.id)
        self.assertEqual(len(doc.bookmarks), 1)
        self.assertEqual(len(doc.notes), 1)

    def test_highlight_sort_key_without_rects(self):
        hl = Highlight("i", 3, [], "t")
        self.assertEqual(hl.sort_key(), (3, 0.0, 0.0))


class TestAnnotationStore(StoreTestCase):
    def test_open_creates_and_persists(self):
        doc = self.store.open_document(self.pdf, title="Bio")
        self.assertEqual(doc.sha256, file_sha256(self.pdf))
        doc.add_highlight(0, [Rect(0, 0, 10, 10)], "cell", "green", "note")
        doc.view.page = 4
        self.store.save(doc)

        reopened = AnnotationStore(self.root).open_document(self.pdf)
        self.assertEqual(len(reopened.highlights), 1)
        self.assertEqual(reopened.highlights[0].note, "note")
        self.assertEqual(reopened.view.page, 4)
        self.assertEqual(reopened.title, "Bio")
        self.assertEqual(reopened.paths, [str(self.pdf.resolve())])

    def test_never_writes_next_to_pdf(self):
        before = self.pdf.read_bytes()
        doc = self.store.open_document(self.pdf)
        doc.add_note("x")
        self.store.save(doc)
        self.assertEqual(self.pdf.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["Biology 101.pdf", "data"])

    def test_survives_rename_and_move(self):
        doc = self.store.open_document(self.pdf)
        doc.add_bookmark(2, "Chapter 2")
        self.store.save(doc)
        moved = self.tmp / "elsewhere" / "renamed.pdf"
        moved.parent.mkdir()
        os.replace(self.pdf, moved)
        again = AnnotationStore(self.root).open_document(moved)
        self.assertEqual([b.name for b in again.bookmarks], ["Chapter 2"])
        self.assertEqual(again.file_name, "renamed.pdf")
        self.assertEqual(len(again.paths), 2)

    def test_identical_copies_share_annotations(self):
        copy = self.tmp / "copy.pdf"
        copy.write_bytes(self.pdf.read_bytes())
        doc = self.store.open_document(self.pdf)
        doc.add_note("shared")
        self.store.save(doc)
        self.assertEqual(self.store.open_document(copy).notes[0].text, "shared")

    def test_changed_file_at_same_path_carries_annotations(self):
        doc = self.store.open_document(self.pdf)
        old_sha = doc.sha256
        doc.add_highlight(1, [Rect(1, 1, 1, 1)], "kept")
        self.store.save(doc)
        self.pdf.write_bytes(b"%PDF-1.4 revised handout, different bytes")
        again = self.store.open_document(self.pdf)
        self.assertNotEqual(again.sha256, old_sha)
        self.assertEqual(again.carried_from, old_sha)
        self.assertEqual([h.text for h in again.highlights], ["kept"])
        # The old annotation file is left in place.
        self.assertTrue(self.store.has(old_sha))

    def test_changed_file_does_not_clobber_existing_annotations(self):
        other = self.tmp / "other.pdf"
        other.write_bytes(b"%PDF-1.4 revised handout, different bytes")
        o = self.store.open_document(other)
        o.add_note("other's note")
        self.store.save(o)
        doc = self.store.open_document(self.pdf)
        doc.add_note("first version note")
        self.store.save(doc)
        self.pdf.write_bytes(other.read_bytes())
        again = self.store.open_document(self.pdf)
        self.assertEqual([n.text for n in again.notes], ["other's note"])

    def test_hash_cache_avoids_rehash(self):
        self.store.open_document(self.pdf)
        key = str(self.pdf.resolve())
        self.store._index["files"][key]["sha256"] = "cached-value"
        self.assertEqual(self.store.identify(self.pdf), "cached-value")
        self.pdf.write_bytes(b"%PDF-1.4 changed length!!")
        self.assertEqual(self.store.identify(self.pdf), file_sha256(self.pdf))

    def test_recents_order_dedupe_and_forget(self):
        b = self.tmp / "b.pdf"
        b.write_bytes(b"%PDF b")
        self.store.open_document(self.pdf)
        self.store.open_document(b)
        self.store.open_document(self.pdf)
        paths = [r.path for r in AnnotationStore(self.root).recents()]
        self.assertEqual(paths, [str(self.pdf.resolve()), str(b.resolve())])
        self.store.forget_recent(str(b.resolve()))
        self.assertEqual([r.path for r in self.store.recents()], [str(self.pdf.resolve())])

    def test_recents_capped(self):
        for i in range(40):
            p = self.tmp / f"f{i}.pdf"
            p.write_bytes(f"%PDF {i}".encode())
            self.store.open_document(p)
        self.assertEqual(len(self.store.recents()), 30)

    def test_corrupt_annotation_file_is_backed_up(self):
        doc = self.store.open_document(self.pdf)
        path = self.store.annotation_path(doc.sha256)
        path.write_text("{ not json")
        fresh = self.store.load(doc.sha256)
        self.assertTrue(fresh.is_empty())
        backups = list(path.parent.glob(f"{path.name}.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "{ not json")

    def test_corrupt_index_is_tolerated(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "index.json").write_text("[1, 2")
        store = AnnotationStore(self.root)
        self.assertEqual(store.recents(), [])
        store.open_document(self.pdf)
        self.assertEqual(len(store.recents()), 1)

    def test_saved_file_is_valid_json_with_schema(self):
        doc = self.store.open_document(self.pdf)
        data = json.loads(self.store.annotation_path(doc.sha256).read_text())
        self.assertEqual(data["dogear"], 1)
        self.assertEqual(data["sha256"], doc.sha256)
        self.assertNotIn(".tmp", " ".join(p.name for p in self.store.ann_dir.iterdir()))


class TestCleanText(unittest.TestCase):
    def test_joins_lines_and_dehyphenates(self):
        self.assertEqual(
            clean_pdf_text("The photo-\r\nsynthesis process\r\nconverts  light"),
            "The photosynthesis process converts light",
        )

    def test_soft_hyphen_and_whitespace(self):
        self.assertEqual(clean_pdf_text("  chloro­phyll \n\n is green "), "chlorophyll is green")

    def test_keeps_real_hyphen_mid_line(self):
        self.assertEqual(clean_pdf_text("well-known fact"), "well-known fact")


if __name__ == "__main__":
    unittest.main()
