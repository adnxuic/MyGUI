"""Closed tagged normalizers for application settings.

Composite values use exact field sets. Production settings never use editable
JSON. This module does not import Qt or Matplotlib.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from .errors import SettingsValidationError
from .models import (
    Density,
    ExportBBoxInches,
    ExportFormatPreference,
    ExportMetadata,
    JpegSubsampling,
    PadInchesKind,
    PadInchesValue,
    ThemeMode,
    TiffCompression,
    WorkspaceExplorerMode,
    WorkspaceLayoutPayload,
)

HEX_COLOR = re.compile(
    r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"
)
METADATA_KEYS = frozenset(
    {
        "Title",
        "Author",
        "Description",
        "Copyright",
        "Software",
        "Comment",
        "Subject",
        "Keywords",
        "Creator",
        "Rights",
    }
)
MIN_UI_FONT_PT = 8
MAX_UI_FONT_PT = 16
DEFAULT_UI_FONT_PT = 9
MIN_FIGURE_INCHES = 0.1
MAX_FIGURE_INCHES = 100.0
MIN_DOCUMENT_DPI = 1.0
MAX_DOCUMENT_DPI = 2400.0
MIN_PAD_INCHES = 0.0
MAX_PAD_INCHES = 5.0
DEFAULT_PAD_INCHES = 0.1
MAX_SPLITTER_SIZE = 100_000
MIN_SPLITTER_SHARE = 0.01
WORKSPACE_LAYOUT_VERSION = 2
WORKSPACE_LAYOUT_KIND = "workspace_layout_v2"
PAD_NUMERIC_KIND = "numeric"
PAD_LAYOUT_KIND = "layout"
METADATA_KIND = "export_metadata"


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SettingsValidationError(f"{name} must be an object.")
    if not all(isinstance(key, str) for key in value):
        raise SettingsValidationError(f"{name} keys must be strings.")
    return dict(value)


def _exact(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise SettingsValidationError(
            f"{name} fields must be exactly {sorted(expected)!r}."
        )


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsValidationError(f"{name} must be a number.")
    result = float(value)
    if not math.isfinite(result):
        raise SettingsValidationError(f"{name} must be finite.")
    return result


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise SettingsValidationError(f"{name} must be an integer.")
    return int(value)


def normalize_bool(value: Any) -> bool:
    """Normalize a bool, including common preference-store coercions."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
    raise SettingsValidationError("Value must be a boolean.")


def normalize_theme_mode(value: Any) -> ThemeMode:
    """Reject unknown theme policies."""

    if isinstance(value, ThemeMode):
        return value
    try:
        return ThemeMode(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"Theme mode must be one of {[item.value for item in ThemeMode]}."
        ) from exc


def validate_theme_mode(value: ThemeMode) -> bool:
    return value in ThemeMode


def normalize_density(value: Any) -> Density:
    """Reject unknown density policies."""

    if isinstance(value, Density):
        return value
    try:
        return Density(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"Density must be one of {[item.value for item in Density]}."
        ) from exc


def validate_density(value: Density) -> bool:
    return value in Density


def normalize_ui_font_point_size(value: Any) -> int:
    """Require an integer point size in 8–16. Reject bools and non-integers."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsValidationError(
            f"UI font size must be an integer from {MIN_UI_FONT_PT} to "
            f"{MAX_UI_FONT_PT}."
        )
    if value < MIN_UI_FONT_PT or value > MAX_UI_FONT_PT:
        raise SettingsValidationError(
            f"UI font size must be between {MIN_UI_FONT_PT} and "
            f"{MAX_UI_FONT_PT}."
        )
    return int(value)


def validate_ui_font_point_size(value: int) -> bool:
    return MIN_UI_FONT_PT <= value <= MAX_UI_FONT_PT


def _splitter_sizes(value: Any, name: str) -> tuple[int, int]:
    if isinstance(value, str):
        text = value.strip().strip("[]()")
        value = [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple)) and len(value) == 2:
        sizes = tuple(_int(item, name) for item in value)
    else:
        raise SettingsValidationError(f"{name} must be two positive integers.")
    if any(size <= 0 or size > MAX_SPLITTER_SIZE for size in sizes):
        raise SettingsValidationError(
            f"{name} values must be between 1 and {MAX_SPLITTER_SIZE}."
        )
    total = sum(sizes)
    if min(sizes) / total < MIN_SPLITTER_SHARE:
        raise SettingsValidationError(
            f"{name} must keep each pane above {MIN_SPLITTER_SHARE:.0%} of the total."
        )
    return sizes[0], sizes[1]


def _coerce_workspace_layout_aliases(spec: dict[str, Any]) -> dict[str, Any]:
    """Accept storage-migrator camelCase v2 objects without a kind tag."""

    outer = spec.get("outer_splitter_sizes", spec.get("outerSplitterSizes"))
    inner = spec.get("inner_splitter_sizes", spec.get("innerSplitterSizes"))
    explorer_mode = spec.get("explorer_mode", spec.get("explorerMode"))
    explorer_visible = spec.get("explorer_visible", spec.get("explorerVisible"))
    if outer is None or inner is None or explorer_mode is None:
        return spec
    if explorer_visible is None and "explorerVisible" not in spec:
        if "explorer_visible" not in spec:
            return spec
    return {
        "kind": WORKSPACE_LAYOUT_KIND,
        "version": spec.get("version", WORKSPACE_LAYOUT_VERSION),
        "outer_splitter_sizes": outer,
        "inner_splitter_sizes": inner,
        "explorer_mode": explorer_mode,
        "explorer_visible": True if explorer_visible is None else explorer_visible,
    }


def normalize_workspace_layout(value: Any) -> WorkspaceLayoutPayload:
    """Normalize the typed workspaceLayout v2 structure."""

    if isinstance(value, WorkspaceLayoutPayload):
        value = {
            "kind": WORKSPACE_LAYOUT_KIND,
            "version": value.version,
            "outer_splitter_sizes": list(value.outer_splitter_sizes),
            "inner_splitter_sizes": list(value.inner_splitter_sizes),
            "explorer_mode": value.explorer_mode.value,
            "explorer_visible": value.explorer_visible,
        }
    spec = _mapping(value, "Workspace layout")
    if spec.get("kind") != WORKSPACE_LAYOUT_KIND:
        spec = _coerce_workspace_layout_aliases(spec)
    if spec.get("kind") != WORKSPACE_LAYOUT_KIND:
        raise SettingsValidationError(
            f"Workspace layout kind must be {WORKSPACE_LAYOUT_KIND!r}."
        )
    _exact(
        spec,
        {
            "kind",
            "version",
            "outer_splitter_sizes",
            "inner_splitter_sizes",
            "explorer_mode",
            "explorer_visible",
        },
        "Workspace layout",
    )
    version = _int(spec["version"], "Workspace layout version")
    if version != WORKSPACE_LAYOUT_VERSION:
        raise SettingsValidationError(
            f"Workspace layout version must be {WORKSPACE_LAYOUT_VERSION}."
        )
    try:
        explorer_mode = WorkspaceExplorerMode(
            str(spec["explorer_mode"]).strip().casefold()
        )
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            "Explorer mode must be 'table' or 'components'."
        ) from exc
    return WorkspaceLayoutPayload(
        version=WORKSPACE_LAYOUT_VERSION,
        outer_splitter_sizes=_splitter_sizes(
            spec["outer_splitter_sizes"], "outer_splitter_sizes"
        ),
        inner_splitter_sizes=_splitter_sizes(
            spec["inner_splitter_sizes"], "inner_splitter_sizes"
        ),
        explorer_mode=explorer_mode,
        explorer_visible=normalize_bool(spec["explorer_visible"]),
    )


def validate_workspace_layout(value: WorkspaceLayoutPayload) -> bool:
    return value.version == WORKSPACE_LAYOUT_VERSION


def workspace_layout_to_wire(value: WorkspaceLayoutPayload) -> dict[str, Any]:
    """Return the tagged JSON-safe layout payload."""

    return {
        "kind": WORKSPACE_LAYOUT_KIND,
        "version": int(value.version),
        "outer_splitter_sizes": list(value.outer_splitter_sizes),
        "inner_splitter_sizes": list(value.inner_splitter_sizes),
        "explorer_mode": value.explorer_mode.value,
        "explorer_visible": bool(value.explorer_visible),
    }


def normalize_figure_inches(value: Any) -> float:
    result = _finite(value, "Figure size")
    if result < MIN_FIGURE_INCHES or result > MAX_FIGURE_INCHES:
        raise SettingsValidationError(
            f"Figure size must be between {MIN_FIGURE_INCHES} and "
            f"{MAX_FIGURE_INCHES} inches."
        )
    return result


def validate_figure_inches(value: float) -> bool:
    return MIN_FIGURE_INCHES <= value <= MAX_FIGURE_INCHES


def normalize_document_dpi(value: Any) -> float:
    result = _finite(value, "Document DPI")
    if result < MIN_DOCUMENT_DPI or result > MAX_DOCUMENT_DPI:
        raise SettingsValidationError(
            f"Document DPI must be between {MIN_DOCUMENT_DPI:g} and "
            f"{MAX_DOCUMENT_DPI:g}."
        )
    return result


def validate_document_dpi(value: float) -> bool:
    return MIN_DOCUMENT_DPI <= value <= MAX_DOCUMENT_DPI


def normalize_export_format(value: Any) -> ExportFormatPreference:
    if isinstance(value, ExportFormatPreference):
        return value
    try:
        return ExportFormatPreference(str(value).strip().casefold())
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            "Export format must be png, jpeg, tiff, webp, pdf, or svg."
        ) from exc


def validate_export_format(value: ExportFormatPreference) -> bool:
    return value in ExportFormatPreference


def normalize_directory(value: Any) -> str:
    text = str(value or "").strip()
    if "\x00" in text:
        raise SettingsValidationError("Directory path must not contain NUL.")
    return text


def validate_directory(value: str) -> bool:
    return "\x00" not in value


def normalize_export_color(value: Any) -> str:
    text = str(value or "").strip()
    if text.casefold() == "auto":
        return "auto"
    if HEX_COLOR.match(text):
        return text
    raise SettingsValidationError(
        "Color must be 'auto' or a hex color (#RGB, #RRGGBB, or with alpha)."
    )


def validate_export_color(value: str) -> bool:
    return value == "auto" or bool(HEX_COLOR.match(value))


def normalize_bbox_inches(value: Any) -> ExportBBoxInches:
    if isinstance(value, ExportBBoxInches):
        return value
    if value is None:
        return ExportBBoxInches.FIGURE
    text = str(value).strip().casefold()
    if text in {"", "none", "figure"}:
        return ExportBBoxInches.FIGURE
    if text == "tight":
        return ExportBBoxInches.TIGHT
    raise SettingsValidationError("bbox_inches must be 'figure' or 'tight'.")


def validate_bbox_inches(value: ExportBBoxInches) -> bool:
    return value in ExportBBoxInches


def normalize_pad_inches(value: Any) -> PadInchesValue:
    """Normalize tagged pad-inches. Accepts a number or 'layout' as shortcuts."""

    if isinstance(value, PadInchesValue):
        return _validated_pad(value)
    if isinstance(value, str) and value.strip().casefold() == "layout":
        return PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None)
    if isinstance(value, Mapping):
        spec = _mapping(value, "pad_inches")
        kind = str(spec.get("kind", "")).strip().casefold()
        if kind == PAD_LAYOUT_KIND:
            _exact(spec, {"kind"}, "layout pad_inches")
            return PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None)
        if kind == PAD_NUMERIC_KIND:
            _exact(spec, {"kind", "inches"}, "numeric pad_inches")
            inches = _finite(spec["inches"], "pad_inches")
            return _validated_pad(
                PadInchesValue(kind=PadInchesKind.NUMERIC, inches=inches)
            )
        raise SettingsValidationError(
            "pad_inches kind must be 'numeric' or 'layout'."
        )
    inches = _finite(value, "pad_inches")
    return _validated_pad(PadInchesValue(kind=PadInchesKind.NUMERIC, inches=inches))


def _validated_pad(value: PadInchesValue) -> PadInchesValue:
    if value.kind is PadInchesKind.LAYOUT:
        return PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None)
    inches = _finite(value.inches, "pad_inches")
    if inches < MIN_PAD_INCHES or inches > MAX_PAD_INCHES:
        raise SettingsValidationError(
            f"pad_inches must be between {MIN_PAD_INCHES} and {MAX_PAD_INCHES}."
        )
    return PadInchesValue(kind=PadInchesKind.NUMERIC, inches=inches)


def validate_pad_inches(value: PadInchesValue) -> bool:
    if value.kind is PadInchesKind.LAYOUT:
        return value.inches is None
    return (
        value.inches is not None
        and MIN_PAD_INCHES <= value.inches <= MAX_PAD_INCHES
    )


def pad_inches_to_wire(value: PadInchesValue) -> dict[str, Any]:
    if value.kind is PadInchesKind.LAYOUT:
        return {"kind": PAD_LAYOUT_KIND}
    return {"kind": PAD_NUMERIC_KIND, "inches": float(value.inches or 0.0)}


def _int_range(value: Any, minimum: int, maximum: int, name: str) -> int:
    number = _int(value, name)
    if number < minimum or number > maximum:
        raise SettingsValidationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return number


def normalize_png_compress_level(value: Any) -> int:
    return _int_range(value, 0, 9, "PNG compression level")


def validate_png_compress_level(value: int) -> bool:
    return 0 <= value <= 9


def normalize_jpeg_quality(value: Any) -> int:
    return _int_range(value, 0, 95, "JPEG quality")


def validate_jpeg_quality(value: int) -> bool:
    return 0 <= value <= 95


def normalize_jpeg_subsampling(value: Any) -> JpegSubsampling:
    if isinstance(value, JpegSubsampling):
        return value
    text = str(value).strip()
    folded = text.casefold()
    if folded in {"auto", "automatic"}:
        return JpegSubsampling.AUTO
    try:
        return JpegSubsampling(text)
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            "JPEG subsampling must be auto, 4:4:4, 4:2:2, or 4:2:0."
        ) from exc


def validate_jpeg_subsampling(value: JpegSubsampling) -> bool:
    return value in JpegSubsampling


def normalize_tiff_compression(value: Any) -> TiffCompression:
    if isinstance(value, TiffCompression):
        return value
    text = str(value).strip().casefold()
    aliases = {
        "none": TiffCompression.NONE,
        "uncompressed": TiffCompression.NONE,
        "packbits": TiffCompression.PACKBITS,
        "lzw": TiffCompression.LZW,
        "adobe_deflate": TiffCompression.ADOBE_DEFLATE,
        "adobe deflate": TiffCompression.ADOBE_DEFLATE,
    }
    if text in aliases:
        return aliases[text]
    raise SettingsValidationError(
        "TIFF compression must be none, packbits, lzw, or adobe_deflate."
    )


def validate_tiff_compression(value: TiffCompression) -> bool:
    return value in TiffCompression


def normalize_webp_quality(value: Any) -> int:
    return _int_range(value, 0, 100, "WebP quality")


def validate_webp_quality(value: int) -> bool:
    return 0 <= value <= 100


def normalize_webp_method(value: Any) -> int:
    return _int_range(value, 0, 6, "WebP method")


def validate_webp_method(value: int) -> bool:
    return 0 <= value <= 6


def normalize_export_metadata(value: Any) -> ExportMetadata:
    """Normalize tagged export metadata. Unknown keys are rejected."""

    if isinstance(value, ExportMetadata):
        fields = dict(value.fields)
    elif isinstance(value, Mapping) and "kind" in value:
        spec = _mapping(value, "export metadata")
        if spec.get("kind") != METADATA_KIND:
            raise SettingsValidationError(
                f"Export metadata kind must be {METADATA_KIND!r}."
            )
        _exact(spec, {"kind", "fields"}, "export metadata")
        fields = _mapping(spec["fields"], "export metadata fields")
    elif isinstance(value, Mapping):
        fields = _mapping(value, "export metadata")
    else:
        raise SettingsValidationError("Export metadata must be an object.")
    cleaned: dict[str, str] = {}
    for key, item in fields.items():
        if key not in METADATA_KEYS:
            raise SettingsValidationError(
                f"Unsupported export metadata key {key!r}."
            )
        text = str(item)
        if not text.strip():
            continue
        cleaned[key] = text
    return ExportMetadata(fields=cleaned)


def validate_export_metadata(value: ExportMetadata) -> bool:
    return all(key in METADATA_KEYS for key in value.fields)


def export_metadata_to_wire(value: ExportMetadata) -> dict[str, Any]:
    return {
        "kind": METADATA_KIND,
        "fields": dict(value.fields),
    }


def always_true(_value: Any) -> bool:
    return True
