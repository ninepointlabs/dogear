"""Answer-line detection on synthetic page images (no Qt needed)."""

import unittest

from dogear.rules import context_for, find_rules, rule_at, slot_from, text_size

SCALE = 2.0  # pixels per point, as page_rules() renders


class Page:
    """A white grayscale page, sized in PDF points, drawn in points."""

    def __init__(self, w_pt=300, h_pt=300):
        self.w, self.h = int(w_pt * SCALE), int(h_pt * SCALE)
        self.px = bytearray(b"\xff" * (self.w * self.h))

    def fill(self, x, y, w, h, value=0):
        for r in range(int(y * SCALE), int((y + h) * SCALE)):
            for c in range(int(x * SCALE), int((x + w) * SCALE)):
                self.px[r * self.w + c] = value

    def line(self, x, y, w, thick=0.8):
        self.fill(x, y - thick / 2, w, thick)

    def text(self, x, y, w, size=10):
        """Glyph-like ink: short vertical strokes, as text renders."""
        for i in range(int(w / 3)):
            self.fill(x + i * 3, y - size * 0.7, 1.2, size * 0.7)

    def rules(self):
        return find_rules(bytes(self.px), self.w, self.h, self.w, SCALE)


class TestFindRules(unittest.TestCase):
    def test_single_line(self):
        page = Page()
        page.line(50, 100, 200)
        rules = page.rules()
        self.assertEqual(len(rules), 1)
        r = rules[0]
        self.assertAlmostEqual(r["x"], 50, delta=0.6)
        self.assertAlmostEqual(r["y"], 100, delta=0.6)
        self.assertAlmostEqual(r["w"], 200, delta=1)
        self.assertGreater(r["space"], 30)

    def test_text_is_not_a_line(self):
        page = Page()
        page.text(20, 60, 260)
        self.assertEqual(page.rules(), [])

    def test_short_dash_is_not_a_line(self):
        page = Page()
        page.line(50, 100, 15)
        self.assertEqual(page.rules(), [])

    def test_underlined_text_is_not_a_blank(self):
        page = Page()
        page.text(50, 98, 200)
        page.line(50, 100, 200)
        self.assertEqual(page.rules(), [])

    def test_thick_bar_is_not_a_line(self):
        page = Page()
        page.fill(50, 100, 200, 8)
        self.assertEqual(page.rules(), [])

    def test_box_edges_are_not_lines(self):
        page = Page()
        page.line(40, 60, 220)  # top
        page.line(40, 200, 220)  # bottom
        page.fill(40, 60, 0.8, 140)  # left
        page.fill(259.2, 60, 0.8, 140)  # right
        self.assertEqual(page.rules(), [])

    def test_dotted_line(self):
        page = Page()
        for i in range(40):
            page.fill(50 + i * 4, 100, 1.5, 1)
        self.assertEqual(len(page.rules()), 1)

    def test_label_beside_line(self):
        page = Page()
        page.text(20, 100, 60)
        page.line(90, 100, 180)
        rules = page.rules()
        self.assertEqual(len(rules), 1)
        self.assertAlmostEqual(rules[0]["x"], 90, delta=1)

    def test_space_stops_at_text_above(self):
        page = Page()
        page.text(50, 80, 200)
        page.line(50, 100, 200)
        rules = page.rules()
        self.assertEqual(len(rules), 1)
        self.assertAlmostEqual(rules[0]["space"], 20, delta=2)

    def test_sorted_top_to_bottom_left_to_right(self):
        page = Page()
        page.line(160, 150, 100)
        page.line(30, 150, 100)
        page.line(30, 80, 100)
        self.assertEqual([(round(r["x"]), round(r["y"])) for r in page.rules()], [(30, 80), (30, 150), (160, 150)])


class TestSlots(unittest.TestCase):
    def rules(self, *rows):
        return [{"x": x, "y": y, "w": w, "space": s} for x, y, w, s in rows]

    def test_ruled_block_grouped(self):
        rules = self.rules((50, 100, 400, 30), (50, 124, 400, 22), (50, 148, 400, 22), (50, 230, 400, 60))
        slot = slot_from(rules, 0)
        self.assertEqual(slot["lines"], 3)
        self.assertEqual(slot["pitch"], 24)
        self.assertEqual(slot["w"], 400)
        self.assertLessEqual(slot["size"], 12)
        # Starting on the second line keeps the rest of the block.
        self.assertEqual(slot_from(rules, 1)["lines"], 2)

    def test_blanks_in_sentences_stay_separate(self):
        # Fill-in-the-blank lines at different positions are separate answers.
        rules = self.rules((200, 100, 250, 20), (90, 118, 360, 15), (90, 136, 120, 15), (260, 136, 190, 15))
        self.assertEqual(slot_from(rules, 0)["lines"], 1)
        self.assertEqual(slot_from(rules, 1)["lines"], 1)

    def test_single_line_size_from_space(self):
        slot = slot_from(self.rules((50, 100, 200, 14)), 0)
        self.assertEqual(slot["pitch"], 0)
        self.assertAlmostEqual(slot["size"], 14 * 0.55, places=2)

    def test_size_follows_page_text(self):
        rules = self.rules((50, 100, 200, 40), (50, 200, 200, 12))
        self.assertAlmostEqual(slot_from(rules, 0, 10.5)["size"], 10.5)
        # Shrunk when the space above the line is tight.
        self.assertAlmostEqual(slot_from(rules, 1, 10.5)["size"], 12 * 0.8)
        lines = [{"text": "t", "rect": [0, y, 100, h]} for y, h in ((10, 10), (30, 10), (50, 20), (70, 1))]
        self.assertAlmostEqual(text_size(lines), 10.5)
        self.assertEqual(text_size([]), 0.0)

    def test_rule_at(self):
        rules = self.rules((50, 100, 200, 30), (50, 130, 200, 22))
        self.assertEqual(rule_at(rules, 100, 95), 0)  # just above the first line
        self.assertEqual(rule_at(rules, 100, 101), 0)  # on it
        self.assertEqual(rule_at(rules, 100, 120), 1)  # in the space of the second
        self.assertEqual(rule_at(rules, 10, 95), -1)  # left of the line
        self.assertEqual(rule_at(rules, 100, 60), -1)  # far above


class TestContext(unittest.TestCase):
    LINES = [
        {"text": "Review questions", "rect": [72, 400, 120, 14]},
        {"text": "1. Name of the process:", "rect": [72, 452, 130, 11]},
        {"text": "2. Explain the Calvin cycle in", "rect": [72, 492, 300, 11]},
        {"text": "your own words.", "rect": [72, 506, 120, 11]},
        {"text": "3. Plants absorb ________ and ________ light.", "rect": [72, 612, 300, 11]},
    ]

    def test_label_on_the_same_row(self):
        self.assertEqual(context_for(self.LINES, 210, 464), "1. Name of the process:")

    def test_question_above_ruled_lines(self):
        self.assertEqual(context_for(self.LINES, 90, 532), "2. Explain the Calvin cycle in your own words.")

    def test_underscore_blanks_collapsed(self):
        self.assertEqual(context_for(self.LINES, 160, 623), "3. Plants absorb ___ and ___ light.")

    def test_nothing_near(self):
        self.assertEqual(context_for(self.LINES, 90, 760), "")
        self.assertEqual(context_for([], 90, 100), "")


if __name__ == "__main__":
    unittest.main()
