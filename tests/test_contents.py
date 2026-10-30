"""Tables of contents made from a PDF's text lines (no Qt needed)."""

import os
import tempfile
import unittest
from unittest import mock

from dogear import contents


def line(text, y, h=10, x=72):
    return {"text": text, "rect": [x, y, 300, h], "start": 0}


def body(n, y=200):
    return [line(f"Body text line {i} about photosynthesis and light.", y + i * 14) for i in range(n)]


class TestBuild(unittest.TestCase):
    def test_headings_by_size_and_numbered_sections(self):
        pages = [
            [line("Light Reactions", 60, h=24)] + body(20),
            [line("SECTION 1", 60)] + body(20, 80),
            [line("Membranes", 60, h=16)] + body(20, 80),
            [line("The Calvin", 60, h=24), line("Cycle", 86, h=24)] + body(20, 120),
            body(20),
        ]
        got = contents.build(pages, ["1", "2", "3", "4", "5"])
        self.assertEqual(
            [(e["title"], e["level"], e["page"], e["y"]) for e in got],
            [("Light Reactions", 0, 0, 60), ("Section 1", 2, 1, 60), ("Membranes", 1, 2, 60),
             ("The Calvin Cycle", 0, 3, 60)],
        )

    def test_printed_contents_page(self):
        # The printed numbers are page labels; the cover and Contents come
        # first. "Preface ... iii" is printed as iii but is on PDF page 3.
        pages = [
            [line("Biology Workbook", 200, h=40)],
            [line("Contents", 60, h=14),
             line("Preface ............................ iii", 100),
             line("Light ................................ 1", 114),
             line("Membranes ........................ 2", 128, x=90),
             line("Carbon ............................... 3", 142)],
            [line("Preface", 60, h=16)] + body(10),
            [line("Light", 60, h=30)] + body(10),
            [line("Membranes", 60, h=16)] + body(10),
            [line("Carbon", 60, h=30), line("SECTION 1", 300)] + body(10),
        ]
        labels = ["i", "ii", "iv", "1", "2", "3"]
        got = contents.build(pages, labels)
        self.assertEqual(
            [(e["title"], e["level"], e["page"]) for e in got],
            [("Preface", 0, 2), ("Light", 0, 3), ("Membranes", 1, 4), ("Carbon", 0, 5), ("Section 1", 2, 5)],
        )

    def test_running_headers_and_forms_are_not_headings(self):
        # A big header on every page, and a form with big text everywhere.
        pages = [[line("Unit Notes", 20, h=16)] + body(10, 60) for _ in range(12)]
        self.assertEqual(contents.build(pages, [str(i + 1) for i in range(12)]), [])
        form = [[line(f"Field {i}", 60 + i * 30, h=14) for i in range(8)] + body(10, 400) for _ in range(3)]
        self.assertEqual(contents.build(form, ["1", "2", "3"]), [])

    def test_sentences_are_not_headings(self):
        pages = [
            [line("Light Reactions", 60, h=24), line("– You tell yourself the answer.", 100, h=14),
             line("and then carry on", 120, h=14), line("Section 3 of this unit is about light.", 140)] + body(10, 200),
            [line("Carbon Fixing", 60, h=24)] + body(10),
        ]
        self.assertEqual([e["title"] for e in contents.build(pages, ["1", "2"])], ["Light Reactions", "Carbon Fixing"])

    def test_nothing_found(self):
        self.assertEqual(contents.build([body(10), body(10)], ["1", "2"]), [])
        self.assertEqual(contents.build([], []), [])


class TestCache(unittest.TestCase):
    def test_saved_per_pdf_and_rebuilt_on_new_version(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DOGEAR_DATA_DIR": tmp}):
            self.assertIsNone(contents.load("abc"))
            entries = [{"title": "Light", "level": 0, "page": 3, "y": 60.0}]
            contents.save("abc", entries)
            self.assertEqual(contents.load("abc"), entries)
            contents.save("none", [])
            self.assertEqual(contents.load("none"), [])  # built, nothing found
            with mock.patch.object(contents, "VERSION", contents.VERSION + 1):
                self.assertIsNone(contents.load("abc"))


if __name__ == "__main__":
    unittest.main()
