"""Where the app keeps its data, and where bundled resources live."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LiveTranslate"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_windows() -> bool:
    return sys.platform == "win32"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Settings/log directory. Order: env override, portable exe, %APPDATA%, ~/.config."""
    override = os.environ.get("LIVETRANSLATE_HOME")
    if override:
        path = Path(override)
    elif is_frozen() and (Path(sys.executable).parent / "portable.txt").exists():
        path = Path(sys.executable).parent
    elif _is_windows():
        path = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        path = Path.home() / ".config" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(rel: str) -> Path:
    """Path of a file bundled with the app (PyInstaller unpacks into sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", _REPO_ROOT)) if is_frozen() else _REPO_ROOT
    return base / rel
