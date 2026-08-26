"""JSON-safe document payload conversion. No widgets, callbacks, or editors.

Composition (Integrator): inject DualSlotDocumentPort from
``create_settings_backend(...).application_settings_port()`` into
``ApplicationSettingsService(document=port)``. The service duck-types storage
``DocumentLoadResult`` / ``StorageCommitResult`` (``payload``, ``revision``,
``ok`` / ``success``). Do not construct a second QSettings here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import SettingsValidationError
from .keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    EXPORT_BBOX_INCHES,
    EXPORT_CUSTOM_DPI,
    EXPORT_EDGECOLOR,
    EXPORT_FACECOLOR,
    EXPORT_FORMAT,
    EXPORT_JPEG_OPTIMIZE,
    EXPORT_JPEG_PROGRESSIVE,
    EXPORT_JPEG_QUALITY,
    EXPORT_JPEG_SUBSAMPLING,
    EXPORT_LAST_DIRECTORY,
    EXPORT_METADATA,
    EXPORT_PAD_INCHES,
    EXPORT_PNG_COMPRESS_LEVEL,
    EXPORT_PNG_OPTIMIZE,
    EXPORT_TIFF_COMPRESSION,
    EXPORT_TRANSPARENT,
    EXPORT_USE_PROJECT_DPI,
    EXPORT_WEBP_ALPHA_QUALITY,
    EXPORT_WEBP_EXACT,
    EXPORT_WEBP_LOSSLESS,
    EXPORT_WEBP_METHOD,
    EXPORT_WEBP_QUALITY,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_APPEARANCE,
    PAGE_EXPORT,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
    PERSISTENT_KEYS,
    WORKSPACE_LAYOUT,
    WORKSPACE_REMEMBER_LAYOUT,
)
from .models import (
    AppearanceSettings,
    ApplicationSettingsSnapshot,
    ExportSettings,
    NewFigureSettings,
    WorkspaceSettings,
)
from .registry import SettingsRegistry

_SECTION_KEYS = {
    PAGE_APPEARANCE: (
        APPEARANCE_THEME_MODE,
        APPEARANCE_UI_FONT_POINT_SIZE,
        APPEARANCE_DENSITY,
    ),
    PAGE_WORKSPACE: (WORKSPACE_REMEMBER_LAYOUT, WORKSPACE_LAYOUT),
    PAGE_NEW_FIGURE: (
        NEW_FIGURE_WIDTH_IN,
        NEW_FIGURE_HEIGHT_IN,
        NEW_FIGURE_DOCUMENT_DPI,
    ),
    PAGE_EXPORT: (
        EXPORT_FORMAT,
        EXPORT_LAST_DIRECTORY,
        EXPORT_USE_PROJECT_DPI,
        EXPORT_CUSTOM_DPI,
        EXPORT_TRANSPARENT,
        EXPORT_FACECOLOR,
        EXPORT_EDGECOLOR,
        EXPORT_BBOX_INCHES,
        EXPORT_PAD_INCHES,
        EXPORT_PNG_COMPRESS_LEVEL,
        EXPORT_PNG_OPTIMIZE,
        EXPORT_JPEG_QUALITY,
        EXPORT_JPEG_OPTIMIZE,
        EXPORT_JPEG_PROGRESSIVE,
        EXPORT_JPEG_SUBSAMPLING,
        EXPORT_TIFF_COMPRESSION,
        EXPORT_WEBP_LOSSLESS,
        EXPORT_WEBP_QUALITY,
        EXPORT_WEBP_ALPHA_QUALITY,
        EXPORT_WEBP_METHOD,
        EXPORT_WEBP_EXACT,
        EXPORT_METADATA,
    ),
}

_FIELD_BY_KEY = {
    APPEARANCE_THEME_MODE: "theme_mode",
    APPEARANCE_UI_FONT_POINT_SIZE: "ui_font_point_size",
    APPEARANCE_DENSITY: "density",
    WORKSPACE_REMEMBER_LAYOUT: "remember_layout",
    WORKSPACE_LAYOUT: "layout",
    NEW_FIGURE_WIDTH_IN: "width_in",
    NEW_FIGURE_HEIGHT_IN: "height_in",
    NEW_FIGURE_DOCUMENT_DPI: "document_dpi",
    EXPORT_FORMAT: "format",
    EXPORT_LAST_DIRECTORY: "last_directory",
    EXPORT_USE_PROJECT_DPI: "use_project_dpi",
    EXPORT_CUSTOM_DPI: "custom_dpi",
    EXPORT_TRANSPARENT: "transparent",
    EXPORT_FACECOLOR: "facecolor",
    EXPORT_EDGECOLOR: "edgecolor",
    EXPORT_BBOX_INCHES: "bbox_inches",
    EXPORT_PAD_INCHES: "pad_inches",
    EXPORT_PNG_COMPRESS_LEVEL: "png_compress_level",
    EXPORT_PNG_OPTIMIZE: "png_optimize",
    EXPORT_JPEG_QUALITY: "jpeg_quality",
    EXPORT_JPEG_OPTIMIZE: "jpeg_optimize",
    EXPORT_JPEG_PROGRESSIVE: "jpeg_progressive",
    EXPORT_JPEG_SUBSAMPLING: "jpeg_subsampling",
    EXPORT_TIFF_COMPRESSION: "tiff_compression",
    EXPORT_WEBP_LOSSLESS: "webp_lossless",
    EXPORT_WEBP_QUALITY: "webp_quality",
    EXPORT_WEBP_ALPHA_QUALITY: "webp_alpha_quality",
    EXPORT_WEBP_METHOD: "webp_method",
    EXPORT_WEBP_EXACT: "webp_exact",
    EXPORT_METADATA: "metadata",
}

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "callback",
        "callbacks",
        "widget",
        "widgets",
        "editor",
        "normalizer",
        "validator",
        "qwidget",
        "QWidget",
    }
)


def export_settings_to_patch(settings: ExportSettings) -> dict[str, Any]:
    """Return the export-page patch for ``commit_patch`` / ``ExportPreferencesPort``."""

    values = flatten_snapshot(ApplicationSettingsSnapshot(export=settings))
    return {key: values[key] for key in _SECTION_KEYS[PAGE_EXPORT]}


def flatten_snapshot(
    snapshot: ApplicationSettingsSnapshot,
) -> dict[str, Any]:
    """Return persisted key -> typed value, excluding revision."""

    return {
        APPEARANCE_THEME_MODE: snapshot.appearance.theme_mode,
        APPEARANCE_UI_FONT_POINT_SIZE: snapshot.appearance.ui_font_point_size,
        APPEARANCE_DENSITY: snapshot.appearance.density,
        WORKSPACE_REMEMBER_LAYOUT: snapshot.workspace.remember_layout,
        WORKSPACE_LAYOUT: snapshot.workspace.layout,
        NEW_FIGURE_WIDTH_IN: snapshot.new_figure.width_in,
        NEW_FIGURE_HEIGHT_IN: snapshot.new_figure.height_in,
        NEW_FIGURE_DOCUMENT_DPI: snapshot.new_figure.document_dpi,
        EXPORT_FORMAT: snapshot.export.format,
        EXPORT_LAST_DIRECTORY: snapshot.export.last_directory,
        EXPORT_USE_PROJECT_DPI: snapshot.export.use_project_dpi,
        EXPORT_CUSTOM_DPI: snapshot.export.custom_dpi,
        EXPORT_TRANSPARENT: snapshot.export.transparent,
        EXPORT_FACECOLOR: snapshot.export.facecolor,
        EXPORT_EDGECOLOR: snapshot.export.edgecolor,
        EXPORT_BBOX_INCHES: snapshot.export.bbox_inches,
        EXPORT_PAD_INCHES: snapshot.export.pad_inches,
        EXPORT_PNG_COMPRESS_LEVEL: snapshot.export.png_compress_level,
        EXPORT_PNG_OPTIMIZE: snapshot.export.png_optimize,
        EXPORT_JPEG_QUALITY: snapshot.export.jpeg_quality,
        EXPORT_JPEG_OPTIMIZE: snapshot.export.jpeg_optimize,
        EXPORT_JPEG_PROGRESSIVE: snapshot.export.jpeg_progressive,
        EXPORT_JPEG_SUBSAMPLING: snapshot.export.jpeg_subsampling,
        EXPORT_TIFF_COMPRESSION: snapshot.export.tiff_compression,
        EXPORT_WEBP_LOSSLESS: snapshot.export.webp_lossless,
        EXPORT_WEBP_QUALITY: snapshot.export.webp_quality,
        EXPORT_WEBP_ALPHA_QUALITY: snapshot.export.webp_alpha_quality,
        EXPORT_WEBP_METHOD: snapshot.export.webp_method,
        EXPORT_WEBP_EXACT: snapshot.export.webp_exact,
        EXPORT_METADATA: snapshot.export.metadata,
    }


def snapshot_from_values(
    values: Mapping[str, Any],
    *,
    revision: int,
) -> ApplicationSettingsSnapshot:
    """Build a snapshot from a complete persisted-key mapping."""

    appearance = {
        _FIELD_BY_KEY[key]: values[key] for key in _SECTION_KEYS[PAGE_APPEARANCE]
    }
    workspace = {
        _FIELD_BY_KEY[key]: values[key] for key in _SECTION_KEYS[PAGE_WORKSPACE]
    }
    new_figure = {
        _FIELD_BY_KEY[key]: values[key] for key in _SECTION_KEYS[PAGE_NEW_FIGURE]
    }
    export = {
        _FIELD_BY_KEY[key]: values[key] for key in _SECTION_KEYS[PAGE_EXPORT]
    }
    return ApplicationSettingsSnapshot(
        appearance=AppearanceSettings(**appearance),
        workspace=WorkspaceSettings(**workspace),
        new_figure=NewFigureSettings(**new_figure),
        export=ExportSettings(**export),
        revision=int(revision),
    )


def snapshot_to_payload(
    snapshot: ApplicationSettingsSnapshot,
    registry: SettingsRegistry,
) -> dict[str, Any]:
    """Serialize a snapshot to a nested JSON-safe document. No UI fields."""

    values = flatten_snapshot(snapshot)
    payload: dict[str, Any] = {}
    for page_id, keys in _SECTION_KEYS.items():
        section: dict[str, Any] = {}
        for key in keys:
            field_name = _FIELD_BY_KEY[key]
            section[field_name] = registry.spec(key).wire_value(values[key])
        payload[page_id] = section
    payload["revision"] = int(snapshot.revision)
    _assert_payload_is_data(payload)
    return payload


def payload_has_unknown_current_fields(payload: Mapping[str, Any] | None) -> bool:
    """Return whether a current-schema payload has fields this version does not own.

    Same-version unknown fields are treated as a future document: read-only,
    never rewritten by close-save after normalize-to-default. Incompatible
    stored shapes must bump ``schema_version``.
    """

    if not payload:
        return False
    known_top = set(_SECTION_KEYS) | {"revision"}
    if set(payload) - known_top:
        return True
    for page_id, keys in _SECTION_KEYS.items():
        section = payload.get(page_id)
        if not isinstance(section, Mapping):
            continue
        known_fields = {_FIELD_BY_KEY[key] for key in keys}
        if set(section) - known_fields:
            return True
    return False


def flatten_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract dotted keys from a nested document. Unknown keys are ignored."""

    if not payload:
        return {}
    flat: dict[str, Any] = {}
    for page_id, keys in _SECTION_KEYS.items():
        section = payload.get(page_id)
        if not isinstance(section, Mapping):
            continue
        for key in keys:
            field_name = _FIELD_BY_KEY[key]
            if field_name in section:
                flat[key] = section[field_name]
    return flat


def values_from_payload(
    payload: Mapping[str, Any] | None,
    registry: SettingsRegistry,
) -> tuple[dict[str, Any], int]:
    """Normalize a document field-by-field, falling back to defaults."""

    values = dict(registry.defaults())
    revision = 0
    if payload:
        raw_revision = payload.get("revision", 0)
        try:
            revision = int(raw_revision)
        except (TypeError, ValueError, OverflowError):
            revision = 0
        if revision < 0:
            revision = 0
    for key, raw in flatten_payload(payload).items():
        try:
            values[key] = registry.spec(key).normalize(raw)
        except SettingsValidationError:
            continue
    return values, revision


def apply_patch_values(
    base: Mapping[str, Any],
    patch: Mapping[str, Any],
    registry: SettingsRegistry,
) -> dict[str, Any]:
    """Return a new complete value map with a validated patch applied."""

    merged = dict(base)
    for key, raw in patch.items():
        if key not in PERSISTENT_KEYS:
            raise SettingsValidationError(
                f"Unknown or non-persistent setting {key!r}."
            )
        merged[key] = registry.spec(key).normalize(raw)
    return merged


def _assert_payload_is_data(payload: Mapping[str, Any]) -> None:
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop()
        if callable(item) and not isinstance(item, (str, bytes)):
            raise SettingsValidationError(
                "Settings payload must not contain callbacks."
            )
        if isinstance(item, Mapping):
            for key, value in item.items():
                if key in FORBIDDEN_PAYLOAD_KEYS:
                    raise SettingsValidationError(
                        f"Settings payload must not contain UI key {key!r}."
                    )
                stack.append(value)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
