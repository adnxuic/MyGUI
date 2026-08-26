"""QSettings group and document-slot key names for application settings storage."""

from __future__ import annotations

APPLICATION_SETTINGS_GROUP = "applicationSettings"
COLOR_LIBRARY_SETTINGS_GROUP = "colorLibrarySettings"
SLOT_A = "slotA"
SLOT_B = "slotB"
SLOTS: tuple[str, str] = (SLOT_A, SLOT_B)

SCHEMA_APPLICATION_SETTINGS = "mygui.applicationSettings"
SCHEMA_COLOR_LIBRARY_SETTINGS = "mygui.colorLibrarySettings"
CURRENT_SCHEMA_VERSION = 1

LEGACY_WORKSPACE_GROUP = "workspaceLayout"
LEGACY_EXPORT_GROUP = "figureExport"
LEGACY_COLOR_GROUP = "colorLibrary"
LEGACY_WORKSPACE_VERSIONS = frozenset({1, 2})
LEGACY_EXPORT_VERSION = 1
LEGACY_COLOR_VERSION = 1

MAX_ENVELOPE_BYTES = 1_048_576
MIN_REVISION = 1
MAX_REVISION = (2**63) - 1


def slot_key(group: str, slot: str) -> str:
    """Return the QSettings key for one document slot."""

    return f"{group}/{slot}"
