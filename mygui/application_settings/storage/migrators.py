"""Isolated legacy QSettings migrators for application and color documents."""

from __future__ import annotations

import json
from typing import Any

from mygui.application_settings.storage.keys import (
    LEGACY_COLOR_GROUP,
    LEGACY_COLOR_VERSION,
    LEGACY_EXPORT_GROUP,
    LEGACY_EXPORT_VERSION,
    LEGACY_WORKSPACE_GROUP,
    LEGACY_WORKSPACE_VERSIONS,
)

MAX_PERSISTED_SPLITTER_SIZE = 100_000
MIN_PERSISTED_SPLITTER_SHARE = 0.01
DEFAULT_UI_FONT_POINT_SIZE = 9
DEFAULT_DENSITY = "standard"
DEFAULT_FIGURE_WIDTH_IN = 6.4
DEFAULT_FIGURE_HEIGHT_IN = 4.8
DEFAULT_DOCUMENT_DPI = 100.0
EXPORT_FORMATS = frozenset({"png", "jpeg", "tiff", "webp", "pdf", "svg"})
JPEG_SUBSAMPLING_CHOICES = ("auto", "4:4:4", "4:2:2", "4:2:0")
TIFF_COMPRESSION_CHOICES = ("none", "packbits", "lzw", "adobe_deflate")
EXPLORER_MODES = frozenset({"table", "components"})
LEGACY_GROUPS = (
    LEGACY_WORKSPACE_GROUP,
    LEGACY_EXPORT_GROUP,
    LEGACY_COLOR_GROUP,
)


def default_appearance(*, migrated: bool) -> dict[str, Any]:
    """Return appearance defaults for a fresh install or a legacy migration."""

    return {
        "theme_mode": "light" if migrated else "system",
        "ui_font_point_size": DEFAULT_UI_FONT_POINT_SIZE,
        "density": DEFAULT_DENSITY,
    }


def default_workspace_payload() -> dict[str, Any]:
    """Return the built-in workspace document fragment."""

    return {"remember_layout": True, "layout": None}


def default_new_figure_payload() -> dict[str, Any]:
    """Return the built-in new-figure document fragment."""

    return {
        "width_in": DEFAULT_FIGURE_WIDTH_IN,
        "height_in": DEFAULT_FIGURE_HEIGHT_IN,
        "document_dpi": DEFAULT_DOCUMENT_DPI,
    }


def default_export_payload() -> dict[str, Any]:
    """Return the built-in figure-export document fragment."""

    return {
        "last_directory": "",
        "format": "png",
        "custom_dpi": DEFAULT_DOCUMENT_DPI,
        "use_project_dpi": True,
        "transparent": False,
        "facecolor": "auto",
        "edgecolor": "auto",
        "bbox_inches": "figure",
        "pad_inches": 0.1,
        "png_compress_level": 6,
        "png_optimize": False,
        "jpeg_quality": 75,
        "jpeg_optimize": False,
        "jpeg_progressive": False,
        "jpeg_subsampling": "auto",
        "tiff_compression": "none",
        "webp_lossless": False,
        "webp_quality": 80,
        "webp_alpha_quality": 100,
        "webp_method": 4,
        "webp_exact": False,
        "metadata": {},
    }


def default_color_library_payload() -> dict[str, Any]:
    """Return the built-in color-library document payload."""

    return {
        "recent_colors": [],
        "favorite_colors": [],
        "favorite_palette_ids": [],
        "custom_palettes": [],
    }


def default_application_settings_payload(*, migrated: bool = False) -> dict[str, Any]:
    """Return a complete application-settings payload."""

    return {
        "appearance": default_appearance(migrated=migrated),
        "workspace": default_workspace_payload(),
        "new_figure": default_new_figure_payload(),
        "export": default_export_payload(),
    }


def migrate_application_settings(settings) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Migrate workspace and export legacy domains independently."""

    workspace, workspace_notes, workspace_legacy = _migrate_workspace(settings)
    export, export_notes, export_legacy = _migrate_export(settings)
    migrated = workspace_legacy or export_legacy
    payload = {
        "appearance": default_appearance(migrated=migrated),
        "workspace": workspace,
        "new_figure": default_new_figure_payload(),
        "export": export,
    }
    notes: list[str] = [
        "bootstrap: migrated_from_legacy"
        if migrated
        else "bootstrap: fresh_defaults"
    ]
    notes.extend(workspace_notes)
    notes.extend(export_notes)
    return payload, tuple(notes)


def migrate_color_library_settings(settings) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Migrate the color-library legacy domain in isolation."""

    payload, notes, used = _migrate_color_library(settings)
    prefix = (
        "bootstrap: migrated_from_legacy" if used else "bootstrap: fresh_defaults"
    )
    return payload, (prefix, *notes)


def clear_legacy_keys(settings) -> None:
    """Remove inert legacy groups. Not called on the production load path."""

    for group in LEGACY_GROUPS:
        settings.beginGroup(group)
        try:
            settings.remove("")
        finally:
            settings.endGroup()
    settings.sync()


def _group_has_entries(settings, group: str) -> bool:
    settings.beginGroup(group)
    try:
        return bool(list(settings.childKeys()) or list(settings.childGroups()))
    finally:
        settings.endGroup()


def _migrate_workspace(settings) -> tuple[dict[str, Any], list[str], bool]:
    default = default_workspace_payload()
    has_entries = _group_has_entries(settings, LEGACY_WORKSPACE_GROUP)
    if not has_entries:
        return default, ["workspace: no legacy keys"], False
    settings.beginGroup(LEGACY_WORKSPACE_GROUP)
    try:
        version = _read_int(settings.value("version"), None)
        if version not in LEGACY_WORKSPACE_VERSIONS:
            return (
                default,
                ["workspace: unknown version; using built-in default"],
                True,
            )
        outer = _valid_splitter_sizes(settings.value("outerSplitterSizes"))
        inner = _valid_splitter_sizes(settings.value("innerSplitterSizes"))
        if outer is None or inner is None:
            return (
                default,
                ["workspace: unusable splitter sizes; using built-in default"],
                True,
            )
        if version == 1:
            explorer_mode = "table"
            explorer_visible = _read_bool(settings.value("tableVisible"), True)
        else:
            explorer_mode = str(
                settings.value("explorerMode", "table") or "table"
            ).strip()
            if explorer_mode not in EXPLORER_MODES:
                explorer_mode = "table"
            explorer_visible = _read_bool(settings.value("explorerVisible"), True)
        layout = {
            "version": 2,
            "outerSplitterSizes": outer,
            "innerSplitterSizes": inner,
            "explorerMode": explorer_mode,
            "explorerVisible": explorer_visible,
        }
        return (
            {"remember_layout": True, "layout": layout},
            [f"workspace: migrated legacy v{version}"],
            True,
        )
    except Exception as exc:  # noqa: BLE001 - domain isolation
        return default, [f"workspace: migration failed ({exc}); using default"], True
    finally:
        settings.endGroup()


def _migrate_export(settings) -> tuple[dict[str, Any], list[str], bool]:
    default = default_export_payload()
    has_entries = _group_has_entries(settings, LEGACY_EXPORT_GROUP)
    if not has_entries:
        return default, ["export: no legacy keys"], False
    settings.beginGroup(LEGACY_EXPORT_GROUP)
    try:
        version = _read_int(settings.value("version"), None)
        if version != LEGACY_EXPORT_VERSION:
            return (
                default,
                ["export: unknown version; using built-in default"],
                True,
            )
        payload = default_export_payload()
        fmt = str(settings.value("format", payload["format"]) or "").strip().lower()
        if fmt in EXPORT_FORMATS:
            payload["format"] = fmt
        payload["last_directory"] = str(
            settings.value("lastDirectory", "") or ""
        ).strip()
        payload["custom_dpi"] = _read_dpi(
            settings.value("dpi"), DEFAULT_DOCUMENT_DPI
        )
        payload["use_project_dpi"] = _read_bool(
            settings.value("useProjectDpi"), True
        )
        payload["transparent"] = _read_bool(settings.value("transparent"), False)
        payload["facecolor"] = _read_color(settings.value("facecolor"), "auto")
        payload["edgecolor"] = _read_color(settings.value("edgecolor"), "auto")
        payload["bbox_inches"] = _read_bbox(settings.value("bboxInches"))
        payload["pad_inches"] = _read_pad(settings.value("padInches"), 0.1)
        payload["png_compress_level"] = _read_int_range(
            settings.value("pngCompressLevel"), 0, 9, 6
        )
        payload["png_optimize"] = _read_bool(settings.value("pngOptimize"), False)
        payload["jpeg_quality"] = _read_int_range(
            settings.value("jpegQuality"), 0, 95, 75
        )
        payload["jpeg_optimize"] = _read_bool(settings.value("jpegOptimize"), False)
        payload["jpeg_progressive"] = _read_bool(
            settings.value("jpegProgressive"), False
        )
        payload["jpeg_subsampling"] = _read_choice(
            settings.value("jpegSubsampling"),
            JPEG_SUBSAMPLING_CHOICES,
            "auto",
        )
        payload["tiff_compression"] = _read_choice(
            settings.value("tiffCompression"),
            TIFF_COMPRESSION_CHOICES,
            "none",
        )
        payload["webp_lossless"] = _read_bool(settings.value("webpLossless"), False)
        payload["webp_quality"] = _read_int_range(
            settings.value("webpQuality"), 0, 100, 80
        )
        payload["webp_alpha_quality"] = _read_int_range(
            settings.value("webpAlphaQuality"), 0, 100, 100
        )
        payload["webp_method"] = _read_int_range(
            settings.value("webpMethod"), 0, 6, 4
        )
        payload["webp_exact"] = _read_bool(settings.value("webpExact"), False)
        payload["metadata"] = _read_metadata(settings)
        if payload["format"] == "jpeg":
            payload["transparent"] = False
        return payload, ["export: migrated figureExport/v1"], True
    except Exception as exc:  # noqa: BLE001 - domain isolation
        return default, [f"export: migration failed ({exc}); using default"], True
    finally:
        settings.endGroup()


def _migrate_color_library(settings) -> tuple[dict[str, Any], list[str], bool]:
    default = default_color_library_payload()
    has_entries = _group_has_entries(settings, LEGACY_COLOR_GROUP)
    if not has_entries:
        return default, ["colorLibrary: no legacy keys"], False
    settings.beginGroup(LEGACY_COLOR_GROUP)
    try:
        version = _read_int(settings.value("version"), None)
        if version != LEGACY_COLOR_VERSION:
            return (
                default,
                ["colorLibrary: unknown version; using built-in default"],
                True,
            )
        raw_state = settings.value("state", "")
        if not raw_state:
            return default, ["colorLibrary: empty state; using built-in default"], True
        state = _parse_json_object(raw_state)
        if state is None:
            return (
                default,
                ["colorLibrary: invalid state; using built-in default"],
                True,
            )
        payload = {**default, **state}
        return payload, ["colorLibrary: migrated colorLibrary/v1"], True
    except Exception as exc:  # noqa: BLE001 - domain isolation
        return default, [f"colorLibrary: migration failed ({exc}); using default"], True
    finally:
        settings.endGroup()


def _parse_json_object(raw: object) -> dict[str, Any] | None:
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _read_int(value: Any, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _read_int_range(value: Any, minimum: int, maximum: int, default: int) -> int:
    number = _read_int(value, default)
    if number is None or number < minimum or number > maximum:
        return default
    return number


def _read_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _read_dpi(value: Any, default: float) -> float:
    try:
        dpi = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if dpi != dpi or dpi < 1.0 or dpi > 10_000.0:
        return float(default)
    return dpi


def _read_color(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if text == "auto" or (
        text.startswith("#") and len(text) in {4, 5, 7, 9}
    ):
        return text
    return default


def _read_bbox(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text == "tight":
        return "tight"
    return "figure"


def _read_pad(value: Any, default: float) -> float | str:
    if str(value).strip().casefold() == "layout":
        return "layout"
    try:
        pad = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if pad != pad or pad < 0:
        return default
    return pad


def _read_choice(value: Any, choices: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip()
    if text in choices:
        return text
    return default


def _read_metadata(settings) -> dict[str, str]:
    settings.beginGroup("metadata")
    try:
        result: dict[str, str] = {}
        for key in settings.childKeys():
            text = str(settings.value(key, "") or "")
            if text.strip():
                result[str(key)] = text
        return result
    finally:
        settings.endGroup()


def _valid_splitter_sizes(value: Any) -> list[int] | None:
    if isinstance(value, str):
        value = value.strip().strip("[]()")
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        sizes = [int(item) for item in value]
    except (TypeError, ValueError, OverflowError):
        return None
    if any(size <= 0 or size > MAX_PERSISTED_SPLITTER_SIZE for size in sizes):
        return None
    total = sum(sizes)
    if total <= 0 or min(sizes) / total < MIN_PERSISTED_SPLITTER_SHARE:
        return None
    return sizes
