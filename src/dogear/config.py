"""XDG paths and user settings (no Qt)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .fsutil import atomic_write_text

log = logging.getLogger(__name__)


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


def data_dir() -> Path:
    override = os.environ.get("DOGEAR_DATA_DIR")
    return Path(override) if override else _xdg("XDG_DATA_HOME", ".local/share") / "dogear"


def config_dir() -> Path:
    override = os.environ.get("DOGEAR_CONFIG_DIR")
    return Path(override) if override else _xdg("XDG_CONFIG_HOME", ".config") / "dogear"


def state_home() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def documents_dir() -> Path:
    """$XDG_DOCUMENTS_DIR from user-dirs.dirs, else ~/Documents."""
    dirs_file = config_home() / "user-dirs.dirs"
    try:
        for line in dirs_file.read_text().splitlines():
            if line.startswith("XDG_DOCUMENTS_DIR="):
                value = line.split("=", 1)[1].strip().strip('"')
                return Path(value.replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return Path.home() / "Documents"


def default_library_dir() -> Path:
    """~/Documents/Dogear. DOGEAR_LIBRARY_DIR overrides it; with only
    DOGEAR_DATA_DIR set (tests, trial runs) it sits inside that, so a trial
    never touches the real library."""
    override = os.environ.get("DOGEAR_LIBRARY_DIR")
    if override:
        return Path(override)
    if os.environ.get("DOGEAR_DATA_DIR"):
        return data_dir() / "Dogear"
    return documents_dir() / "Dogear"


@dataclass
class Settings:
    export_dir: str = ""
    # The library folder: your notes, categories and copies of the PDFs.
    # Empty means ~/Documents/Dogear. Point it at a synced folder to have
    # the same library on several computers.
    library_dir: str = ""
    # Keep a private copy of every PDF you mark up in the library folder,
    # so your marks always have their PDF even if the original goes away.
    keep_copies: bool = True

    def resolved_library_dir(self) -> Path:
        if self.library_dir.strip() and not os.environ.get("DOGEAR_LIBRARY_DIR"):
            return Path(self.library_dir).expanduser()
        return default_library_dir()

    def resolved_export_dir(self) -> Path:
        if self.export_dir.strip():
            return Path(self.export_dir).expanduser()
        return self.resolved_library_dir() / "Notes"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_dir() / "settings.json"
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable settings %s: %s", path, exc)
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    export_dir = raw.get("export_dir", "")
    library_dir = raw.get("library_dir", "")
    return Settings(
        export_dir=export_dir if isinstance(export_dir, str) else "",
        library_dir=library_dir if isinstance(library_dir, str) else "",
        keep_copies=raw.get("keep_copies", True) is not False,
    )


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_dir() / "settings.json"
    atomic_write_text(path, json.dumps(asdict(settings), indent=2) + "\n")
