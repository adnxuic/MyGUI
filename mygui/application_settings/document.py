"""JSON-safe document payload conversion. No widgets, callbacks, or editors.

Composition (Integrator): inject DualSlotDocumentPort from
``create_settings_backend(...).application_settings_port()`` into
``ApplicationSettingsService(document=port)``. The service duck-types storage
``DocumentLoadResult`` / ``StorageCommitResult`` (``payload``, ``revision``,
``ok`` / ``success``). Do not construct a second QSettings here.

Nested conversion is driven by SettingsRegistry dotted keys. Composite leaves
such as ``workspace.layout`` and ``export.metadata`` are closed values.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import SettingsValidationError
from .keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    COMPONENTS_LINE_COLOR,
    COMPONENTS_LINE_LINESTYLE,
    COMPONENTS_LINE_LINEWIDTH,
    COMPONENTS_LINE_MARKER,
    COMPONENTS_LINE_MARKEREDGEWIDTH,
    COMPONENTS_LINE_MARKERSIZE,
    COMPONENTS_SCATTER_COLOR,
    COMPONENTS_SCATTER_LINEWIDTH,
    COMPONENTS_SCATTER_MARKER,
    COMPONENTS_SCATTER_SIZE,
    COMPONENTS_TEXT_COLOR,
    COMPONENTS_TEXT_FONTFAMILY,
    COMPONENTS_TEXT_FONTSIZE,
    COMPONENTS_TEXT_FONTSTYLE,
    COMPONENTS_TEXT_FONTWEIGHT,
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
    KEYS_BY_PAGE,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_EXPORT,
    PERSISTENT_KEYS,
    WORKSPACE_LAYOUT,
    WORKSPACE_REMEMBER_LAYOUT,
)
from .models import (
    AppearanceSettings,
    ApplicationSettingsSnapshot,
    ComponentDefaultsSettings,
    ExportSettings,
    LineComponentDefaults,
    NewFigureSettings,
    ScatterComponentDefaults,
    TextComponentDefaults,
    WorkspaceSettings,
    axes_defaults_from_values,
    axes_defaults_to_values,
)
from .registry import SettingsRegistry, production_settings_registry

REVISION_KEY = "revision"

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
    return {key: values[key] for key in KEYS_BY_PAGE[PAGE_EXPORT]}


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
        COMPONENTS_LINE_COLOR: snapshot.components.line.color,
        COMPONENTS_LINE_LINESTYLE: snapshot.components.line.linestyle,
        COMPONENTS_LINE_LINEWIDTH: snapshot.components.line.linewidth,
        COMPONENTS_LINE_MARKER: snapshot.components.line.marker,
        COMPONENTS_LINE_MARKERSIZE: snapshot.components.line.markersize,
        COMPONENTS_LINE_MARKEREDGEWIDTH: snapshot.components.line.markeredgewidth,
        COMPONENTS_SCATTER_COLOR: snapshot.components.scatter.color,
        COMPONENTS_SCATTER_MARKER: snapshot.components.scatter.marker,
        COMPONENTS_SCATTER_SIZE: snapshot.components.scatter.size,
        COMPONENTS_SCATTER_LINEWIDTH: snapshot.components.scatter.linewidth,
        COMPONENTS_TEXT_FONTFAMILY: snapshot.components.text.fontfamily,
        COMPONENTS_TEXT_FONTSIZE: snapshot.components.text.fontsize,
        COMPONENTS_TEXT_COLOR: snapshot.components.text.color,
        COMPONENTS_TEXT_FONTWEIGHT: snapshot.components.text.fontweight,
        COMPONENTS_TEXT_FONTSTYLE: snapshot.components.text.fontstyle,
        **axes_defaults_to_values(snapshot.components.axes),
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

    return ApplicationSettingsSnapshot(
        appearance=AppearanceSettings(
            theme_mode=values[APPEARANCE_THEME_MODE],
            ui_font_point_size=values[APPEARANCE_UI_FONT_POINT_SIZE],
            density=values[APPEARANCE_DENSITY],
        ),
        workspace=WorkspaceSettings(
            remember_layout=values[WORKSPACE_REMEMBER_LAYOUT],
            layout=values[WORKSPACE_LAYOUT],
        ),
        new_figure=NewFigureSettings(
            width_in=values[NEW_FIGURE_WIDTH_IN],
            height_in=values[NEW_FIGURE_HEIGHT_IN],
            document_dpi=values[NEW_FIGURE_DOCUMENT_DPI],
        ),
        components=ComponentDefaultsSettings(
            line=LineComponentDefaults(
                color=values[COMPONENTS_LINE_COLOR],
                linestyle=values[COMPONENTS_LINE_LINESTYLE],
                linewidth=values[COMPONENTS_LINE_LINEWIDTH],
                marker=values[COMPONENTS_LINE_MARKER],
                markersize=values[COMPONENTS_LINE_MARKERSIZE],
                markeredgewidth=values[COMPONENTS_LINE_MARKEREDGEWIDTH],
            ),
            scatter=ScatterComponentDefaults(
                color=values[COMPONENTS_SCATTER_COLOR],
                marker=values[COMPONENTS_SCATTER_MARKER],
                size=values[COMPONENTS_SCATTER_SIZE],
                linewidth=values[COMPONENTS_SCATTER_LINEWIDTH],
            ),
            text=TextComponentDefaults(
                fontfamily=values[COMPONENTS_TEXT_FONTFAMILY],
                fontsize=values[COMPONENTS_TEXT_FONTSIZE],
                color=values[COMPONENTS_TEXT_COLOR],
                fontweight=values[COMPONENTS_TEXT_FONTWEIGHT],
                fontstyle=values[COMPONENTS_TEXT_FONTSTYLE],
            ),
            axes=axes_defaults_from_values(values),
        ),
        export=ExportSettings(
            format=values[EXPORT_FORMAT],
            last_directory=values[EXPORT_LAST_DIRECTORY],
            use_project_dpi=values[EXPORT_USE_PROJECT_DPI],
            custom_dpi=values[EXPORT_CUSTOM_DPI],
            transparent=values[EXPORT_TRANSPARENT],
            facecolor=values[EXPORT_FACECOLOR],
            edgecolor=values[EXPORT_EDGECOLOR],
            bbox_inches=values[EXPORT_BBOX_INCHES],
            pad_inches=values[EXPORT_PAD_INCHES],
            png_compress_level=values[EXPORT_PNG_COMPRESS_LEVEL],
            png_optimize=values[EXPORT_PNG_OPTIMIZE],
            jpeg_quality=values[EXPORT_JPEG_QUALITY],
            jpeg_optimize=values[EXPORT_JPEG_OPTIMIZE],
            jpeg_progressive=values[EXPORT_JPEG_PROGRESSIVE],
            jpeg_subsampling=values[EXPORT_JPEG_SUBSAMPLING],
            tiff_compression=values[EXPORT_TIFF_COMPRESSION],
            webp_lossless=values[EXPORT_WEBP_LOSSLESS],
            webp_quality=values[EXPORT_WEBP_QUALITY],
            webp_alpha_quality=values[EXPORT_WEBP_ALPHA_QUALITY],
            webp_method=values[EXPORT_WEBP_METHOD],
            webp_exact=values[EXPORT_WEBP_EXACT],
            metadata=values[EXPORT_METADATA],
        ),
        revision=int(revision),
    )


def _key_segments(key: str) -> tuple[str, ...]:
    return tuple(part for part in key.split(".") if part)


def registry_leaf_paths(
    registry: SettingsRegistry,
) -> tuple[tuple[str, ...], ...]:
    """Return dotted-key paths that are closed payload leaves."""

    return tuple(_key_segments(spec.key) for spec in registry.persistent_specs())


_MISSING = object()


def build_path_trie(
    registry: SettingsRegistry | None = None,
) -> dict[str, Any]:
    """Build a nested dict of known payload segments. Leaves map to ``None``."""

    catalog = registry or production_settings_registry()
    trie: dict[str, Any] = {}
    for path in registry_leaf_paths(catalog):
        node = trie
        for index, part in enumerate(path):
            is_leaf = index == len(path) - 1
            existing = node.get(part, _MISSING)
            if is_leaf:
                if existing is not _MISSING and existing is not None:
                    raise SettingsValidationError(
                        f"Settings key path conflicts at {'.'.join(path)}."
                    )
                node[part] = None
                continue
            if existing is None:
                raise SettingsValidationError(
                    f"Settings key path conflicts at {'.'.join(path[: index + 1])}."
                )
            if existing is _MISSING:
                child: dict[str, Any] = {}
                node[part] = child
            else:
                child = existing
            node = child
    return trie


def snapshot_to_payload(
    snapshot: ApplicationSettingsSnapshot,
    registry: SettingsRegistry,
) -> dict[str, Any]:
    """Serialize a snapshot to a nested JSON-safe document. No UI fields."""

    values = flatten_snapshot(snapshot)
    payload: dict[str, Any] = {}
    for spec in registry.persistent_specs():
        parts = _key_segments(spec.key)
        node = payload
        for part in parts[:-1]:
            child = node.get(part)
            if child is None:
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = registry.spec(spec.key).wire_value(values[spec.key])
    payload[REVISION_KEY] = int(snapshot.revision)
    _assert_payload_is_data(payload)
    return payload


def payload_has_unknown_current_fields(
    payload: Mapping[str, Any] | None,
    registry: SettingsRegistry | None = None,
) -> bool:
    """Return whether a current-schema payload has fields this version does not own.

    Same-version unknown fields are treated as a future document: read-only,
    never rewritten by close-save after normalize-to-default. Incompatible
    stored shapes must bump ``schema_version``. Composite leaves are not
    inspected internally.
    """

    if not payload:
        return False
    trie = build_path_trie(registry)
    return _payload_has_unknown(payload, trie, ())


def _payload_has_unknown(
    node: Any,
    trie_node: dict[str, Any] | None,
    path: tuple[str, ...],
) -> bool:
    if trie_node is None:
        return False
    if not isinstance(node, Mapping):
        return False
    for key, value in node.items():
        if not path and key == REVISION_KEY:
            continue
        if key not in trie_node:
            return True
        child_trie = trie_node[key]
        if _payload_has_unknown(value, child_trie, (*path, key)):
            return True
    return False


def flatten_payload(
    payload: Mapping[str, Any] | None,
    registry: SettingsRegistry | None = None,
) -> dict[str, Any]:
    """Extract dotted keys from a nested document. Unknown keys are ignored."""

    if not payload:
        return {}
    catalog = registry or production_settings_registry()
    flat: dict[str, Any] = {}
    for spec in catalog.persistent_specs():
        parts = _key_segments(spec.key)
        node: Any = payload
        for part in parts:
            if not isinstance(node, Mapping) or part not in node:
                break
            node = node[part]
        else:
            flat[spec.key] = node
    return flat


def values_from_payload(
    payload: Mapping[str, Any] | None,
    registry: SettingsRegistry,
) -> tuple[dict[str, Any], int]:
    """Normalize a document field-by-field, falling back to defaults."""

    values = dict(registry.defaults())
    revision = 0
    if payload:
        raw_revision = payload.get(REVISION_KEY, 0)
        try:
            revision = int(raw_revision)
        except (TypeError, ValueError, OverflowError):
            revision = 0
        if revision < 0:
            revision = 0
    for key, raw in flatten_payload(payload, registry).items():
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
