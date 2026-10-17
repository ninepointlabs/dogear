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

    def serif_word(self, page, x, y, w, size=10):
        """Letters standing on the baseline, with serif feet along it."""
        page.text(x, y, w, size)
        for i in range(int(w / 3)):
            page.fill(x + i * 3 - 0.5, y - 1, 2.4, 1)

    def test_blank_with_a_word_close_after_it(self):
        # "______ and ______ light.": the word after the first blank starts
        # within dot-joining distance, and its feet sit on the line.
        page = Page()
        page.line(50, 100, 100, thick=1)
        self.serif_word(page, 152, 100.5, 18)
        page.line(176, 100, 60, thick=1)
        rules = page.rules()
        self.assertEqual(len(rules), 2, rules)
        self.assertAlmostEqual(rules[0]["x"], 50, delta=0.6)
        self.assertAlmostEqual(rules[0]["w"], 100, delta=1.5)

    def test_dot_leader_into_a_title_is_not_a_blank(self):
        # "Life's Springtime ........ 1" in a table of contents.
        page = Page()
        self.serif_word(page, 30, 100.5, 60)
        for i in range(40):
            page.fill(91 + i * 4, 99.2, 1.5, 1.5)
        self.assertEqual(page.rules(), [])

    def test_hyphen_is_not_a_line(self):
        page = Page()
        page.line(50, 100, 8)
        self.assertEqual(page.rules(), [])

    def test_short_blank_before_a_sentence(self):
        page = Page()
        page.line(50, 100, 22)
        page.text(80, 100, 150)
        rules = page.rules()
        self.assertEqual(len(rules), 1)
        self.assertAlmostEqual(rules[0]["w"], 22, delta=1)

    def test_letter_crossbars_are_not_lines(self):
        # "H"-like shapes: a bar with stems going down from it.
        page = Page()
        page.fill(50, 92, 20, 0.8)
        for x in (50, 58, 69):
            page.fill(x, 92, 1, 8)
        self.assertEqual(page.rules(), [])

    def test_em_dash_between_words_is_not_a_line(self):
        page = Page()
        page.text(20, 100, 60)
        page.line(80.5, 96, 16)  # touches the words on both sides
        page.text(97, 100, 60)
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

    def test_stacked_short_blanks_stay_separate(self):
        # "___ sentence" one per line, evenly spaced: answer each on its own.
        rules = self.rules((100, 100, 24, 20), (100, 130, 24, 20), (100, 160, 24, 20))
        self.assertEqual(slot_from(rules, 0)["lines"], 1)

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

    def test_drawn_blanks_and_a_wrapped_question(self):
        # "1. The pigment … green is ______, and it absorbs mostly
        #  ______ and ______ light." with the blanks drawn as lines: the
        # text has no characters for them, and the second line starts with one.
        # The comma after the first blank starts right at its end.
        lines = [
            {"text": "1. The pigment is , and it absorbs mostly", "rect": [97, 126, 300, 11]},
            {"text": "and light.", "rect": [218, 152, 160, 11]},
            {"text": "2. Next question", "rect": [97, 195, 200, 11]},
        ]
        rules = [{"x": 190.0, "y": 134.0, "w": 24.0}, {"x": 108.0, "y": 160.0, "w": 100.0},
                 {"x": 241.5, "y": 160.0, "w": 100.0}]

        def char_lefts(i):
            # Evenly spaced characters, with a gap where each blank is.
            text = lines[i]["text"]
            x = lines[i]["rect"][0]
            out = []
            for ch in text:
                out.append(x)
                x += 5.0
                if i == 0 and len(out) == len("1. The pigment is "):
                    x = 212.0
                if i == 1 and len(out) == len("and "):
                    x = 345.0
            return out

        want = "1. The pigment is ___, and it absorbs mostly ___ and ___ light."
        for blank in rules:
            got = context_for(lines, blank["x"] + 5, blank["y"], rules=rules, char_lefts=char_lefts)
            self.assertEqual(got, want)
        # Without the character positions, the text still reads as one question.
        self.assertEqual(context_for(lines, 110, 160, rules=rules), "1. The pigment is, and it absorbs mostly and light.")

    def test_nothing_near(self):
        self.assertEqual(context_for(self.LINES, 90, 760), "")
        self.assertEqual(context_for([], 90, 100), "")


if __name__ == "__main__":
    unittest.main()
