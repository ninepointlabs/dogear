"""A library folder shared between computers: merging, conflict copies,
moving the library and the first layout's migration (no Qt)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from dogear import config
from dogear.store import AnnotationStore, DocAnnotations, Rect
from dogear.sync import merge

SHA = "ab" * 32


def doc_with(*texts: str, sha: str = SHA) -> DocAnnotations:
    doc = DocAnnotations(sha)
    for text in texts:
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], text)
    return doc


def copy_of(doc: DocAnnotations) -> DocAnnotations:
    return DocAnnotations.from_dict(doc.to_dict(), doc.sha256)


def texts(doc: DocAnnotations) -> list[str]:
    return sorted(h.text for h in doc.highlights)


class TestMerge(unittest.TestCase):
    def test_three_way_keeps_both_sides_and_their_deletions(self):
        base = doc_with("one", "two")
        mine, theirs = copy_of(base), copy_of(base)
        mine.add_highlight(1, [Rect(1, 2, 3, 4)], "mine")
        mine.remove_highlight(mine.highlights[1].id)  # "two", deleted here
        theirs.add_highlight(1, [Rect(1, 2, 3, 4)], "theirs")
        theirs.update_highlight(theirs.highlights[0].id, note="noted there")
        out = merge(base, mine, theirs)
        self.assertEqual(texts(out), ["mine", "one", "theirs"])
        self.assertEqual(next(h for h in out.highlights if h.text == "one").note, "noted there")

    def test_edit_beats_deletion(self):
        base = doc_with("one")
        mine, theirs = copy_of(base), copy_of(base)
        mine.highlights = []
        theirs.update_highlight(theirs.highlights[0].id, note="still wanted")
        self.assertEqual([h.note for h in merge(base, mine, theirs).highlights], ["still wanted"])

    def test_both_edited_keeps_the_newer(self):
        base = doc_with("one")
        mine, theirs = copy_of(base), copy_of(base)
        mine.highlights[0].note, mine.highlights[0].updated = "older", "2026-01-01T10:00:00+00:00"
        theirs.highlights[0].note, theirs.highlights[0].updated = "newer", "2026-01-02T10:00:00+00:00"
        self.assertEqual(merge(base, mine, theirs).highlights[0].note, "newer")
        self.assertEqual(merge(base, theirs, mine).highlights[0].note, "newer")

    def test_fields_take_the_side_that_changed(self):
        base = doc_with("one")
        mine, theirs = copy_of(base), copy_of(base)
        theirs.label = "Book 5"
        mine.view.page = 7
        out = merge(base, mine, theirs)
        self.assertEqual((out.label, out.view.page), ("Book 5", 7))

    def test_conflict_copies_keep_everything(self):
        mine, theirs = doc_with("mine"), doc_with("theirs")
        mine.categories, theirs.categories = ["Ruhi"], ["Class"]
        out = merge(None, mine, theirs)
        self.assertEqual(texts(out), ["mine", "theirs"])
        self.assertEqual(out.categories, ["Class", "Ruhi"])


class TwoComputers(unittest.TestCase):
    """One synced library folder, two computers with their own local state."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.shared = self.tmp / "Sync" / "Dogear"
        self.a = AnnotationStore(self.shared, local=self.tmp / "a-local")
        self.b = AnnotationStore(self.shared, local=self.tmp / "b-local")

    def tearDown(self):
        self._tmp.cleanup()

    def pdf(self, rel: str, content: bytes = b"bio") -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 " + content)
        return path

    def test_open_document_takes_in_the_other_computers_edits(self):
        mine = self.a.open_document(self.pdf("a/Bio.pdf"))
        base = self.a.read_dict(mine.sha256)
        # Computer B, with its own copy of the PDF somewhere else.
        theirs = self.b.open_document(self.pdf("b/elsewhere/Bio.pdf"))
        theirs.add_highlight(0, [Rect(1, 2, 3, 4)], "from B")
        self.b.save(theirs)
        mine.add_bookmark(2, "from A")
        saved, base, merged = self.a.save_synced(mine, base)
        self.assertTrue(merged)
        self.assertEqual(texts(saved), ["from B"])
        self.assertEqual([b.name for b in saved.bookmarks], ["from A"])
        on_disk = self.b.load(mine.sha256)
        self.assertEqual((texts(on_disk), len(on_disk.bookmarks)), (["from B"], 1))
        # Each computer's own place for the PDF is kept.
        self.assertEqual(len(on_disk.paths), 2)
        # Saving again with nothing new from the file is a plain save.
        _, _, again = self.a.save_synced(saved, base)
        self.assertFalse(again)
        self.assertEqual(self.a.read_dict(mine.sha256), base)
        stamp = self.a.annotation_path(mine.sha256).stat().st_mtime_ns
        # B, which hasn't changed anything, takes A's merge without writing.
        b_base = theirs.to_dict()
        _, _, took = self.b.save_synced(theirs, b_base)
        self.assertTrue(took)
        self.assertEqual(self.a.annotation_path(mine.sha256).stat().st_mtime_ns, stamp)

    def test_copy_found_on_the_other_computer(self):
        doc = self.a.open_document(self.pdf("a/Bio.pdf"))
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], "x")
        self.assertTrue(self.a.keep_copy(doc, self.tmp / "a/Bio.pdf"))
        self.a.save(doc)
        # B never had the PDF anywhere but the synced folder (A's path is
        # on A's disk, not B's).
        (self.tmp / "a/Bio.pdf").unlink()
        self.assertEqual(self.b.openable_path(self.b.load(doc.sha256)), str(self.shared / "Library/Bio.pdf"))
        # Renamed by hand in the folder: still found, by its contents.
        os.replace(self.shared / "Library/Bio.pdf", self.shared / "Library/Biology.pdf")
        self.assertEqual(self.b.openable_path(self.b.load(doc.sha256)), str(self.shared / "Library/Biology.pdf"))

    def test_own_pdf_in_the_folder_needs_no_copy(self):
        own = self.shared / "Books" / "Bio.pdf"
        own.parent.mkdir(parents=True)
        own.write_bytes(b"%PDF-1.4 own")
        doc = self.a.open_document(own)
        self.assertEqual((doc.paths, doc.copy), ([], "Books/Bio.pdf"))
        self.assertTrue(self.a.keep_copy(doc, own))
        self.assertFalse(self.a.library_dir.exists())
        self.assertEqual(self.b.openable_path(self.b.load(doc.sha256)), str(own))

    def test_conflict_copy_is_merged_and_set_aside(self):
        doc = self.a.open_document(self.pdf("a/Bio.pdf"))
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], "kept here")
        self.a.save(doc)
        other = copy_of(doc)
        other.highlights = []
        other.add_highlight(1, [Rect(1, 2, 3, 4)], "kept there")
        conflict = self.a.ann_dir / f"{doc.sha256}.sync-conflict-20261017-101010-ABCDEFG.json"
        conflict.write_text(json.dumps(other.to_dict()))
        (self.a.meta_dir / "library.sync-conflict-20261017-101010-ABCDEFG.json").write_text(
            json.dumps({"categories": ["From B"]}))
        self.a.add_category("From A")
        self.assertEqual(self.a.resolve_conflicts(), [doc.sha256])
        self.assertEqual(texts(self.a.load(doc.sha256)), ["kept here", "kept there"])
        self.assertFalse(conflict.exists())
        self.assertTrue((self.a.removed_dir / "conflicts" / conflict.name).is_file())
        self.assertEqual(self.a.categories(), ["From A", "From B"])
        self.assertEqual([d.sha256 for d in self.a.documents()], [doc.sha256])

    def test_categories_sync(self):
        self.a.add_category("Ruhi")
        self.assertEqual(self.b.categories(), ["Ruhi"])


class TestMoving(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.local = self.tmp / "local"

    def tearDown(self):
        self._tmp.cleanup()

    def pdf(self, rel: str, content: bytes = b"bio") -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 " + content)
        return path

    def test_migrates_the_first_layout(self):
        old = self.local  # everything used to live in the data dir
        first = AnnotationStore(old, local=old)
        first.ann_dir, first.library_dir, first.removed_dir = old / "annotations", old / "library", old / "removed"
        src = self.pdf("class/Bio.pdf")
        doc = first.open_document(src)
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], "old mark")
        doc.categories = ["Ruhi"]
        first.save(doc)
        (old / "library").mkdir()
        (old / "library" / f"{doc.sha256}.pdf").write_bytes(src.read_bytes())
        (old / "removed" / "gone-1").mkdir(parents=True)
        index = json.loads((old / "index.json").read_text())
        index["categories"] = ["Ruhi", "Empty one"]
        (old / "index.json").write_text(json.dumps(index))
        # The new library folder already has this document from another computer.
        root = self.tmp / "Documents" / "Dogear"
        other = DocAnnotations(doc.sha256, file_name="Bio.pdf")
        other.add_bookmark(3, "from the other computer")
        AnnotationStore(root, local=self.tmp / "other-local").save(other)

        store = AnnotationStore(root, local=old)
        self.assertEqual(store.migrate_old_layout(old), 1)
        moved = store.load(doc.sha256)
        self.assertEqual(texts(moved), ["old mark"])
        self.assertEqual([b.name for b in moved.bookmarks], ["from the other computer"])
        self.assertEqual(moved.copy, "Library/Bio.pdf")
        self.assertEqual((root / "Library/Bio.pdf").read_bytes(), src.read_bytes())
        self.assertEqual(store.categories(), ["Empty one", "Ruhi"])
        self.assertTrue((store.removed_dir / "gone-1").is_dir())
        self.assertFalse((old / "annotations").exists())
        self.assertEqual(len(list(old.glob("annotations.moved-*/*.json"))), 1)
        self.assertTrue((old / "MOVED.txt").is_file())
        self.assertNotIn("categories", json.loads((old / "index.json").read_text()))
        # Recent files stay with this computer.
        self.assertEqual([r.path for r in store.recents()], [str(src.resolve())])
        self.assertEqual(store.migrate_old_layout(old), 0)

    def test_move_to_another_folder(self):
        store = AnnotationStore(self.tmp / "Documents" / "Dogear", local=self.local)
        doc = store.open_document(self.pdf("class/Bio.pdf"))
        doc.add_highlight(0, [Rect(1, 2, 3, 4)], "mark")
        store.keep_copy(doc, self.tmp / "class/Bio.pdf")
        store.save(doc)
        own = store.root / "Books" / "Own.pdf"
        own.parent.mkdir()
        own.write_bytes(b"%PDF-1.4 own")
        mine = store.open_document(own)
        store.set_categories(doc.sha256, ["Ruhi"])

        new = self.tmp / "Google Drive" / "Dogear"
        self.assertEqual(store.move_to(new), 2)
        self.assertEqual(store.root, new)
        self.assertEqual(texts(store.load(doc.sha256)), ["mark"])
        self.assertTrue((new / "Library/Bio.pdf").is_file())
        self.assertFalse((self.tmp / "Documents/Dogear/Library/Bio.pdf").exists())
        self.assertEqual(store.categories(), ["Ruhi"])
        # Your own PDF stays put, and is remembered where it is.
        self.assertTrue(own.is_file())
        self.assertEqual(store.openable_path(store.load(mine.sha256)), str(own.resolve()))
        self.assertTrue((self.tmp / "Documents/Dogear/.dogear/MOVED.txt").is_file())


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DOGEAR_DATA_DIR", "DOGEAR_LIBRARY_DIR")}

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_library_folder_and_export_default(self):
        os.environ.pop("DOGEAR_LIBRARY_DIR", None)
        os.environ["DOGEAR_DATA_DIR"] = "/tmp/trial"
        # A trial run never uses the real library folder.
        self.assertEqual(config.Settings().resolved_library_dir(), Path("/tmp/trial/Dogear"))
        chosen = config.Settings(library_dir="~/Sync/Dogear")
        self.assertEqual(chosen.resolved_library_dir(), Path.home() / "Sync/Dogear")
        self.assertEqual(chosen.resolved_export_dir(), Path.home() / "Sync/Dogear/Notes")
        os.environ["DOGEAR_LIBRARY_DIR"] = "/tmp/lib"
        self.assertEqual(chosen.resolved_library_dir(), Path("/tmp/lib"))


if __name__ == "__main__":
    unittest.main()
