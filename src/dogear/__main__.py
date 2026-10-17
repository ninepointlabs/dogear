"""Dogear entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import APP_ID, APP_NAME, TAGLINE, __version__

HERE = Path(__file__).resolve().parent


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: {TAGLINE}")
    parser.add_argument("file", nargs="?", help="PDF to open")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Every control is our own template; never let a platform style leak in.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    from PySide6.QtCore import Property, QObject, QTimer, qVersion
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
    from PySide6 import QtQuick  # noqa: F401  (root object must resolve to QQuickWindow)

    from . import config
    from .controllers import AppController, DocumentController
    from .pdf import PROVIDER_ID, PageImageProvider
    from .store import AnnotationStore
    from .theme.theme import Theme

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    # Wayland app_id -> Hyprland `class:dogear`, and .desktop association.
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(HERE / "assets" / "dogear.svg"))))

    class AppInfo(QObject):
        name = Property(str, lambda self: APP_NAME, constant=True)
        tagline = Property(str, lambda self: TAGLINE, constant=True)
        version = Property(str, lambda self: __version__, constant=True)
        qtVersion = Property(str, lambda self: qVersion(), constant=True)

    info = AppInfo()
    theme = Theme()
    store = AnnotationStore(config.data_dir())
    provider = PageImageProvider()
    state = AppController(store)
    doc = DocumentController(store, provider, state)
    qmlRegisterSingletonInstance(AppInfo, "Dogear", 1, 0, "AppInfo", info)
    qmlRegisterSingletonInstance(Theme, "Dogear", 1, 0, "Theme", theme)
    qmlRegisterSingletonInstance(AppController, "Dogear", 1, 0, "App", state)
    qmlRegisterSingletonInstance(DocumentController, "Dogear", 1, 0, "Doc", doc)

    engine = QQmlApplicationEngine()
    engine.addImageProvider(PROVIDER_ID, provider)
    engine.load(str(HERE / "qml" / "Main.qml"))
    if not engine.rootObjects():
        return 1

    app.aboutToQuit.connect(doc.close)
    if args.file:
        QTimer.singleShot(0, lambda: doc.open(str(Path(args.file).expanduser().resolve())))

    # Development aid: DOGEAR_SCREENSHOT=out.png grabs the window after a
    # short delay and exits.
    shot = os.environ.get("DOGEAR_SCREENSHOT")
    if shot:
        def grab():
            try:
                engine.rootObjects()[0].grabWindow().save(shot)
            finally:
                app.quit()

        QTimer.singleShot(int(os.environ.get("DOGEAR_SCREENSHOT_DELAY", "2000")), grab)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
