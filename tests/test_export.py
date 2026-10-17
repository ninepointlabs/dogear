import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dogear.export import export_filename, export_markdown, page_heading, render_markdown
from dogear.store import DocAnnotations, Rect

SHA = "a" * 64
FIXED = datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)


def sample_doc() -> DocAnnotations:
    doc = DocAnnotations(sha256=SHA, file_name="Bio 101.pdf", title="Biology 101")
    doc.add_note("Exam covers chapters 1-3.\n\n- bring calculator")
    doc.add_highlight(2, [Rect(72, 400, 200, 12)], "The Calvin cycle fixes carbon.", "green", "Key exam point")
    doc.add_highlight(2, [Rect(72, 100, 200, 12)], "Light reactions happen in thylakoids.", "yellow")
    doc.add_highlight(0, [Rect(72, 100, 200, 12)], "Intro text", "blue")
    doc.add_bookmark(2, "Chapter 2 start")
    doc.add_bookmark(5, "Practice questions")
    return doc


class TestRender(unittest.TestCase):
    def setUp(self):
        self.md = render_markdown(sample_doc(), source_path="/home/t/Bio 101.pdf", exported_at=FIXED)

    def test_front_matter(self):
        lines = self.md.splitlines()
        self.assertEqual(lines[0], "---")
        self.assertIn('title: "Biology 101"', lines)
        self.assertIn('source: "/home/t/Bio 101.pdf"', lines)
        self.assertIn(f"sha256: {SHA}", lines)
        self.assertIn("exported: 2026-10-16T20:00:00+00:00", lines)
        self.assertIn("highlights: 3", lines)
        self.assertIn("tags: [dogear]", lines)

    def test_notes_section_before_pages(self):
        self.assertIn("## Notes\n\nExam covers chapters 1-3.\n\n- bring calculator\n", self.md)
        self.assertLess(self.md.index("## Notes"), self.md.index("## Page 1"))

    def test_grouped_by_page_in_order(self):
        order = [self.md.index(h) for h in ("## Page 1", "## Page 3", "## Page 6")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("## Page 2", self.md)

    def test_highlights_quoted_with_page_and_note(self):
        page3 = self.md[self.md.index("## Page 3"):self.md.index("## Page 6")]
        self.assertIn("- **Bookmark:** Chapter 2 start", page3)
        self.assertIn("> Light reactions happen in thylakoids.\n> — p. 3 · yellow\n", page3)
        self.assertIn("> The Calvin cycle fixes carbon.\n> — p. 3 · green\n\nKey exam point\n", page3)
        # Top-to-bottom order on the page.
        self.assertLess(page3.index("Light reactions"), page3.index("Calvin"))

    def test_bookmark_only_page(self):
        page6 = self.md[self.md.index("## Page 6"):]
        self.assertIn("- **Bookmark:** Practice questions", page6)
        self.assertNotIn(">", page6)

    def test_page_labels(self):
        md = render_markdown(sample_doc(), page_label=lambda p: ["i", "ii", "1"][p] if p < 3 else str(p + 1))
        self.assertIn("## Page 1 (i)", md)
        self.assertIn("## Page 3 (1)", md)
        self.assertIn("## Page 6\n", md)

    def test_multiline_quote(self):
        doc = DocAnnotations(sha256=SHA, file_name="x.pdf")
        doc.add_highlight(0, [], "line one\nline two")
        md = render_markdown(doc)
        self.assertIn("> line one\n> line two\n> — p. 1 · yellow", md)

    def test_answers_in_reading_order_with_questions(self):
        doc = DocAnnotations(sha256=SHA, file_name="w.pdf", title="Worksheet")
        doc.add_highlight(0, [Rect(72, 300, 200, 12)], "Between the questions.", "yellow")
        doc.add_answer(0, 162, 623 - 400, 107, text="red", context="3. Plants absorb ___ and ___ light.")
        doc.add_answer(0, 300, 623 - 400, 107, text="blue", context="3. Plants absorb ___ and ___ light.")
        doc.add_answer(0, 90, 532, 430, pitch=24, lines=3, text="Line one\nLine two", context="2. Explain it.")
        doc.add_answer(0, 90, 700, 430, text="   ")  # blank: left out
        md = render_markdown(doc, exported_at=FIXED)
        self.assertIn("answers: 3", md.splitlines())
        self.assertIn(
            "**Q:** 3. Plants absorb ___ and ___ light.  \n**A:** red  \n**A:** blue  \n\n"
            "> Between the questions.\n> — p. 1 · yellow\n\n"
            "**Q:** 2. Explain it.  \n**A:** Line one  \nLine two  \n",
            md,
        )

    def test_answer_without_question(self):
        doc = DocAnnotations(sha256=SHA, file_name="w.pdf")
        doc.add_answer(4, 90, 100, 300, text="just an answer")
        md = render_markdown(doc, exported_at=FIXED)
        self.assertIn("## Page 5\n\n**A:** just an answer", md)
        self.assertNotIn("**Q:**", md)

    def test_empty_doc(self):
        md = render_markdown(DocAnnotations(sha256=SHA, file_name="x.pdf"))
        self.assertIn("# x", md)
        self.assertIn("*No highlights, notes, bookmarks or answers yet.*", md)
        self.assertTrue(md.endswith("\n") and not md.endswith("\n\n"))

    def test_title_quotes_escaped(self):
        doc = DocAnnotations(sha256=SHA, title='Say "hi"')
        self.assertIn('title: "Say \\"hi\\""', render_markdown(doc))


class TestFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "vault" / "Dogear"

    def tearDown(self):
        self._tmp.cleanup()

    def test_filename(self):
        self.assertEqual(export_filename(sample_doc()), "Bio 101.md")
        self.assertEqual(export_filename(DocAnnotations(sha256=SHA, file_name='a:b?c.pdf')), "a b c.md")
        self.assertEqual(export_filename(DocAnnotations(sha256=SHA)), "document.md")

    def test_page_heading(self):
        self.assertEqual(page_heading(0, ""), "Page 1")
        self.assertEqual(page_heading(0, "1"), "Page 1")
        self.assertEqual(page_heading(4, "iv"), "Page 5 (iv)")

    def test_export_creates_folder_and_overwrites_own_file(self):
        doc = sample_doc()
        path = export_markdown(doc, self.out)
        self.assertEqual(path, self.out / "Bio 101.md")
        doc.add_note("added later")
        again = export_markdown(doc, self.out)
        self.assertEqual(again, path)
        self.assertIn("added later", path.read_text())

    def test_same_name_other_document_gets_suffix(self):
        export_markdown(sample_doc(), self.out)
        other = sample_doc()
        other.sha256 = "b" * 64
        path = export_markdown(other, self.out)
        self.assertEqual(path.name, "Bio 101 (bbbbbbbb).md")
        self.assertIn(SHA, (self.out / "Bio 101.md").read_text())

    def test_never_overwrites_users_own_file(self):
        self.out.mkdir(parents=True)
        mine = self.out / "Bio 101.md"
        mine.write_text("my handwritten notes")
        path = export_markdown(sample_doc(), self.out)
        self.assertNotEqual(path, mine)
        self.assertEqual(mine.read_text(), "my handwritten notes")


if __name__ == "__main__":
    unittest.main()
