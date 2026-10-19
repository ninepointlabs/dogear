"""Theme parsing and live theme following (simulated `omarchy theme set`)."""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from dogear.theme.parser import resolve

# Never open real windows from tests, whatever the desktop session sets.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PySide6.QtGui import QGuiApplication

    from dogear.theme.watcher import PathWatcher, omarchy_watch_paths

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

DARK = """
mode = "dark"
accent = "#4A8AB0"
background = "#14131A"
foreground = "#C4C1B8"
yellow = "#f5d547"
green = "#334433"
red = "#9A4A32"
"""

GREY = """
background = "#ffffff"
foreground = "#000000"
accent = "#888888"
yellow = "#999999"
"""


def write_theme(current: Path, colors: str, name: str) -> None:
    """What `omarchy theme set` does: stage next-theme, swap it in, write the name last."""
    nxt = current / "next-theme"
    nxt.mkdir(parents=True)
    (nxt / "colors.toml").write_text(colors)
    shutil.rmtree(current / "theme", ignore_errors=True)
    nxt.rename(current / "theme")
    (current / "theme.name").write_text(name + "\n")


class TestParser(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.current = Path(self._tmp.name) / "current"

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_theme(self):
        write_theme(self.current, DARK, "forge")
        data = resolve(self.current / "theme")
        self.assertEqual(data.name, "forge")
        self.assertEqual(data.source, "omarchy")
        self.assertTrue(data.is_dark)
        self.assertEqual(data.colors["accent"].hex(), "#4a8ab0")

    def test_highlight_colors_use_bright_theme_hues_only(self):
        write_theme(self.current, DARK, "forge")
        hl = resolve(self.current / "theme").highlights
        self.assertEqual(hl["yellow"].hex(), "#f5d547")  # theme's own, bright
        self.assertEqual(hl["green"].hex(), "#7fd66b")  # theme's too dark -> classic marker
        self.assertEqual(set(hl), {"yellow", "green", "blue", "pink", "purple"})

    def test_grey_theme_gets_classic_markers(self):
        write_theme(self.current, GREY, "white")
        data = resolve(self.current / "theme")
        self.assertFalse(data.is_dark)
        self.assertEqual(data.highlights["yellow"].hex(), "#f5d547")

    def test_missing_theme_falls_back(self):
        data = resolve(self.current / "nope")
        self.assertEqual(data.source, "fallback")
        self.assertTrue(data.is_dark)
        self.assertEqual(len(data.highlights), 5)

    def test_missing_theme_follows_light_preference(self):
        data = resolve(self.current / "nope", prefer_light=True)
        self.assertEqual(data.source, "fallback")
        self.assertFalse(data.is_dark)
        self.assertEqual(data.colors["bg"].hex(), "#e1e2e7")
        self.assertEqual(len(data.highlights), 5)

    def test_light_preference_never_overrides_omarchy(self):
        write_theme(self.current, DARK, "forge")
        data = resolve(self.current / "theme", prefer_light=True)
        self.assertEqual(data.source, "omarchy")
        self.assertTrue(data.is_dark)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestThemeDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "DOGEAR_THEME_DIR")}
        os.environ.pop("DOGEAR_THEME_DIR", None)
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        self.current = root / "state" / "omarchy" / "current" / "theme"
        self.legacy = root / "config" / "omarchy" / "current" / "theme"

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_state_dir_when_nothing_exists(self):
        from dogear.theme.theme import current_theme_dir

        self.assertEqual(current_theme_dir(), self.current)

    def test_legacy_config_dir(self):
        from dogear.theme.theme import current_theme_dir

        self.legacy.mkdir(parents=True)
        self.assertEqual(current_theme_dir(), self.legacy)
        self.current.mkdir(parents=True)
        self.assertEqual(current_theme_dir(), self.current)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestWatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A QGuiApplication (not QCoreApplication) so the UI smoke test can
        # share the process-wide instance.
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def spin(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_theme_swap_fires_once_and_rearms(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            current = tmp / "current"
            current.mkdir()
            write_theme(current, DARK, "forge")
            watcher = PathWatcher(omarchy_watch_paths(current, tmp / "fontconfig", tmp), debounce_ms=50)
            hits = []
            watcher.changed.connect(lambda: hits.append(1))

            write_theme(current, GREY, "white")
            self.assertTrue(self.spin(lambda: hits))
            self.spin(lambda: False, timeout=0.3)
            self.assertEqual(len(hits), 1)

            self.assertIn(str(current / "theme" / "colors.toml"), watcher.watched())
            write_theme(current, DARK, "forge")
            self.assertTrue(self.spin(lambda: len(hits) >= 2))


if __name__ == "__main__":
    unittest.main()
