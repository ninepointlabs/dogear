"""Dogear entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import APP_ID, APP_NAME, COPYRIGHT, CREATED, LICENSE_NAME, ORGANIZATION, SUPPORT_EMAIL, TAGLINE, __version__, hostenv

HERE = Path(__file__).resolve().parent


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: {TAGLINE}")
    parser.add_argument("file", nargs="?", help="PDF to open")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    # Packaging check (AppImage CI): start the full UI, open the file if
    # given, report, quit; non-zero exit on QML errors or a failed open.
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def create(argv0: str = APP_ID):
    """Build the application, controllers and QML engine.

    Returns (app, engine, doc); engine is None if the QML failed to load.
    Split out of main() so the UI smoke test can drive the real app.
    """
    # Every control is our own template; never let a platform style leak in.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    import PySide6
    from PySide6.QtCore import Property, QObject, QTimer, QUrl, Slot, qVersion
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
    from PySide6 import QtQuick  # noqa: F401  (root object must resolve to QQuickWindow)

    from . import config
    from .controllers import AppController, DocumentController
    from .store import AnnotationStore
    from .theme.theme import Theme

    app = QGuiApplication.instance() or QGuiApplication([argv0])
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
        # For the About dialog.
        organization = Property(str, lambda self: ORGANIZATION, constant=True)
        supportEmail = Property(str, lambda self: SUPPORT_EMAIL, constant=True)
        created = Property(str, lambda self: CREATED, constant=True)
        license = Property(str, lambda self: LICENSE_NAME, constant=True)
        copyright = Property(str, lambda self: COPYRIGHT, constant=True)
        pysideVersion = Property(str, lambda self: PySide6.__version__, constant=True)
        pythonVersion = Property(str, lambda self: sys.version.split()[0], constant=True)
        icon = Property(QUrl, lambda self: QUrl.fromLocalFile(str(HERE / "assets" / "dogear.svg")), constant=True)

        @Property(str, constant=True)
        def licenseText(self) -> str:
            try:
                text = (HERE / "assets" / "LICENSE.txt").read_text(encoding="utf-8")
            except OSError:
                return f"{LICENSE_NAME}, {COPYRIGHT}"
            # One line per paragraph, so it wraps to the dialog's width.
            return "\n\n".join(" ".join(p.split()) for p in text.split("\n\n") if p.strip())

        @Property(str, constant=True)
        def details(self) -> str:
            """Version details to paste into a support email."""
            return (
                f"{APP_NAME} {__version__}\n"
                f"Qt {qVersion()}, PySide6 {PySide6.__version__}, Python {sys.version.split()[0]}\n"
                f"{os.environ.get('XDG_CURRENT_DESKTOP', 'unknown desktop')}, {QGuiApplication.platformName()}"
            )

        @Slot(str)
        def copy(self, text: str) -> None:
            QGuiApplication.clipboard().setText(text)

    info = AppInfo()
    theme = Theme()
    settings = config.load_settings()
    store = AnnotationStore(settings.resolved_library_dir(), local=config.data_dir())
    try:
        # Dogear's first layout kept everything in the data dir.
        store.migrate_old_layout(config.data_dir())
        store.resolve_conflicts()
    except OSError as exc:
        logging.getLogger(__name__).error("Could not set up the library folder %s: %s", store.root, exc)
    state = AppController(store, settings)
    doc = DocumentController(store, state)
    qmlRegisterSingletonInstance(AppInfo, "Dogear", 1, 0, "AppInfo", info)
    qmlRegisterSingletonInstance(Theme, "Dogear", 1, 0, "Theme", theme)
    qmlRegisterSingletonInstance(AppController, "Dogear", 1, 0, "App", state)
    qmlRegisterSingletonInstance(DocumentController, "Dogear", 1, 0, "Doc", doc)

    engine = QQmlApplicationEngine()
    engine.load(str(HERE / "qml" / "Main.qml"))
    if not engine.rootObjects():
        return app, None, doc
    # Keep Python wrappers alive as long as the engine.
    engine._dogear_refs = (info, theme, store, state, doc)

    return app, engine, doc


def main(argv: list[str] | None = None) -> int:
    # From the AppImage: programs we start (xdg-open, fc-match, hyprctl) must
    # not see the AppImage runtime's variables.
    hostenv.restore()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from PySide6.QtCore import QTimer

    qml_errors: list[str] = []
    if args.self_test:
        _collect_qml_errors(qml_errors)

    app, engine, doc = create()
    if engine is None:
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

    if args.self_test:
        QTimer.singleShot(int(os.environ.get("DOGEAR_SELF_TEST_DELAY", "1500")),
                          lambda: app.exit(_self_test_report(app, engine, doc, args.file, qml_errors)))

    return app.exec()


def _collect_qml_errors(errors: list[str]) -> None:
    """Record QML warnings (missing modules, plugins, type errors), still printing everything."""
    from PySide6.QtCore import QtMsgType, qFormatLogMessage, qInstallMessageHandler

    def handler(mode, context, message):
        print(qFormatLogMessage(mode, context, message), file=sys.stderr, flush=True)
        qml = (context.category or "").startswith(("qml", "js")) or ".qml" in message
        if mode != QtMsgType.QtDebugMsg and mode != QtMsgType.QtInfoMsg and qml:
            errors.append(message)

    qInstallMessageHandler(handler)


def _self_test_report(app, engine, doc, file: str | None, qml_errors: list[str]) -> int:
    from PySide6.QtGui import QDesktopServices, QGuiApplication

    from .theme.theme import Theme

    win = engine.rootObjects()[0]
    theme = Theme(watch=False)
    print(
        f"self-test: platform={QGuiApplication.platformName()} app_id={QGuiApplication.desktopFileName()} "
        f"visible={win.isVisible()} theme={theme.source}/{'dark' if theme.isDark else 'light'} "
        f"radius={theme.radius} pdf_pages={doc.pageCount if doc.loaded else '-'}",
        flush=True,
    )
    # CI points this at a fake xdg-open to check what child processes inherit.
    url = os.environ.get("DOGEAR_SELF_TEST_URL")
    if url:
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl(url))
    for message in qml_errors:
        print(f"self-test: QML problem: {message}", flush=True)
    ok = win.isVisible() and not qml_errors and (not file or doc.loaded)
    print(f"self-test: {'OK' if ok else 'FAILED'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
