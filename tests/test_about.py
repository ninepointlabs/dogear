"""The About dialog's facts (no Qt)."""

import unittest
from pathlib import Path

import dogear

ROOT = Path(__file__).resolve().parents[1]


class TestAbout(unittest.TestCase):
    def test_bundled_license_is_the_license(self):
        # The app ships its own copy for the About dialog; it must not drift.
        bundled = ROOT / "src" / "dogear" / "assets" / "LICENSE.txt"
        self.assertEqual(bundled.read_text(), (ROOT / "LICENSE").read_text())

    def test_facts_agree_with_the_license(self):
        license_text = (ROOT / "LICENSE").read_text()
        self.assertTrue(license_text.startswith("MIT License"))
        self.assertEqual(dogear.LICENSE_NAME, "MIT License")
        self.assertIn(dogear.COPYRIGHT.replace("©", "Copyright (c)"), license_text)
        self.assertEqual(dogear.SUPPORT_EMAIL, "help@ninepointlabs.com")


if __name__ == "__main__":
    unittest.main()
