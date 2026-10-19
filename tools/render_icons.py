"""Render the scalable app icon to the hicolor PNG sizes (uses Qt's SVG support)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QIcon

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "packaging" / "icons" / "hicolor" / "scalable" / "apps" / "dogear.svg"


def main() -> int:
    app = QGuiApplication(sys.argv[:1])  # noqa: F841
    icon = QIcon(str(SVG))
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        out = ROOT / "packaging" / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "dogear.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        # Exact pixels, whatever the display scale of the session running this.
        if not icon.pixmap(QSize(size, size), 1.0).save(str(out)):
            print(f"failed: {out}", file=sys.stderr)
            return 1
        print(out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
