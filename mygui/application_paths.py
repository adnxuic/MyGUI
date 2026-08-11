"""Resolve writable per-user application locations."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def user_data_directory() -> Path:
    """Return the writable MyGUI data directory without touching the repo."""

    configured = os.environ.get("MYGUI_USER_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    location = QStandardPaths.writableLocation(
        QStandardPaths.GenericDataLocation
    )
    base = Path(location) if location else Path.home() / ".local" / "share"
    return base / "MyGUI"


def user_cache_directory() -> Path:
    """Return the writable MyGUI cache directory."""

    configured = os.environ.get("MYGUI_USER_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return user_data_directory() / "cache"


def user_log_directory() -> Path:
    """Return the writable MyGUI log directory."""

    configured = os.environ.get("MYGUI_USER_LOG_DIR")
    if configured:
        return Path(configured).expanduser()
    return user_data_directory() / "logs"
