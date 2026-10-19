"""Keep AppImage variables away from the programs Dogear starts.

The AppImage runtime sets APPIMAGE, APPDIR, ARGV0 and OWD, and our launcher
(packaging/appimage/AppRun) marks the process with DOGEAR_APPIMAGE=1. It
exports nothing else: the bundled Python and Qt find their libraries through
RUNPATH. Dogear itself needs none of these, and children such as xdg-open,
fc-match or hyprctl must not see them (some programs act on APPIMAGE, e.g.
to update themselves).

Outside the Dogear AppImage this does nothing.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

MARKER = "DOGEAR_APPIMAGE"
RUNTIME_VARS = ("APPIMAGE", "APPDIR", "ARGV0", "OWD")


def restore(environ: MutableMapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    if env.pop(MARKER, None) is None:
        return
    for name in RUNTIME_VARS:
        env.pop(name, None)
