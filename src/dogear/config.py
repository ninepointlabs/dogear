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


@dataclass
class Settings:
    export_dir: str = ""
    # Keep a private copy of every PDF you mark up in the library folder,
    # so your marks always have their PDF even if the original goes away.
    keep_copies: bool = True

    def resolved_export_dir(self) -> Path:
        if self.export_dir.strip():
            return Path(self.export_dir).expanduser()
        return documents_dir() / "Dogear"


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
    return Settings(
        export_dir=export_dir if isinstance(export_dir, str) else "",
        keep_copies=raw.get("keep_copies", True) is not False,
    )


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_dir() / "settings.json"
    atomic_write_text(path, json.dumps(asdict(settings), indent=2) + "\n")
