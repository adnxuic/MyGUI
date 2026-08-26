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
    DefaultValueMode,
    Density,
    ExportBBoxInches,
    ExportFormatPreference,
    ExportMetadata,
    InheritableValue,
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


INHERITABLE_KIND = "kind"
INHERITABLE_VALUE = "value"
INHERITABLE_FIELDS = frozenset({INHERITABLE_KIND, INHERITABLE_VALUE})
CLOSED_LINESTYLES = ("-", "--", "-.", ":", "None")
CLOSED_LINE_MARKERS = (
    "None",
    ".",
    ",",
    "o",
    "v",
    "^",
    "<",
    ">",
    "1",
    "2",
    "3",
    "4",
    "8",
    "s",
    "p",
    "P",
    "*",
    "h",
    "H",
    "+",
    "x",
    "X",
    "D",
    "d",
    "|",
    "_",
)
CLOSED_FONT_WEIGHTS = (
    "ultralight",
    "light",
    "normal",
    "regular",
    "book",
    "medium",
    "roman",
    "semibold",
    "demibold",
    "demi",
    "bold",
    "heavy",
    "extra bold",
    "black",
)
CLOSED_FONT_STYLES = ("normal", "italic", "oblique")
CLOSED_TICK_DIRECTIONS = ("in", "out", "inout")
CLOSED_AXISBELOW = (True, False, "line")
MIN_LINEWIDTH = 0.0
MAX_LINEWIDTH = 100.0
MIN_TICK_LENGTH = 0.0
MAX_TICK_LENGTH = 100.0
MIN_ROTATION = -360.0
MAX_ROTATION = 360.0
MIN_GRID_ALPHA = 0.0
MAX_GRID_ALPHA = 1.0
MIN_MARKERSIZE = 0.0
MAX_MARKERSIZE = 100.0
MIN_SCATTER_SIZE = 0.0
MAX_SCATTER_SIZE = 10_000.0
MIN_FONTSIZE = 1.0
MAX_FONTSIZE = 1_000.0
HEX_COMPONENT_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


def inheritable_to_wire(value: InheritableValue) -> dict[str, Any]:
    """Return the closed ``{kind, value}`` wire shape."""

    inner = value.value
    if isinstance(inner, float):
        inner = float(inner)
    return {"kind": value.mode.value, "value": inner}


def _inheritable_mapping(value: Any, name: str) -> dict[str, Any]:
    spec = _mapping(value, name)
    extra = set(spec) - INHERITABLE_FIELDS
    missing = INHERITABLE_FIELDS - set(spec)
    if extra or missing:
        raise SettingsValidationError(
            f"{name} fields must be exactly {sorted(INHERITABLE_FIELDS)!r}."
        )
    return spec


def _inheritable_mode(value: Any, name: str) -> DefaultValueMode:
    if isinstance(value, DefaultValueMode):
        return value
    try:
        return DefaultValueMode(str(value).strip().casefold())
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"{name} kind must be 'inherit' or 'override'."
        ) from exc


def _normalize_inheritable(
    value: Any,
    *,
    name: str,
    inner_normalizer,
) -> InheritableValue:
    if isinstance(value, InheritableValue):
        return InheritableValue(
            mode=value.mode,
            value=inner_normalizer(value.value),
        )
    spec = _inheritable_mapping(value, name)
    return InheritableValue(
        mode=_inheritable_mode(spec[INHERITABLE_KIND], name),
        value=inner_normalizer(spec[INHERITABLE_VALUE]),
    )


def normalize_component_color(value: Any) -> str:
    text = str(value or "").strip()
    if not HEX_COMPONENT_COLOR.match(text):
        raise SettingsValidationError(
            "Component color must be #RRGGBB or #RRGGBBAA."
        )
    return text.upper()


def validate_component_color(value: str) -> bool:
    return bool(HEX_COMPONENT_COLOR.match(value))


def normalize_inheritable_color(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Component color", inner_normalizer=normalize_component_color
    )


def validate_inheritable_color(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_component_color(str(value.value))
    )


def normalize_linestyle_preset(value: Any) -> str:
    if not isinstance(value, str):
        raise SettingsValidationError("Line style must be a string.")
    aliases = {
        "solid": "-",
        "dashed": "--",
        "dashdot": "-.",
        "dash-dot": "-.",
        "dotted": ":",
        "none": "None",
    }
    normalized = aliases.get(value.strip().casefold(), value)
    if normalized not in CLOSED_LINESTYLES:
        raise SettingsValidationError(
            "Line style must be one of '-', '--', '-.', ':', or 'None'."
        )
    return normalized


def validate_linestyle_preset(value: str) -> bool:
    return value in CLOSED_LINESTYLES


def normalize_inheritable_linestyle(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value,
        name="Line style",
        inner_normalizer=normalize_linestyle_preset,
    )


def validate_inheritable_linestyle(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_linestyle_preset(str(value.value))
    )


def _positive_range(value: Any, minimum: float, maximum: float, name: str) -> float:
    result = _finite(value, name)
    if result < minimum or result > maximum:
        raise SettingsValidationError(
            f"{name} must be between {minimum:g} and {maximum:g}."
        )
    return result


def normalize_linewidth(value: Any) -> float:
    return _positive_range(value, MIN_LINEWIDTH, MAX_LINEWIDTH, "Line width")


def validate_linewidth(value: float) -> bool:
    return MIN_LINEWIDTH <= value <= MAX_LINEWIDTH


def normalize_inheritable_linewidth(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Line width", inner_normalizer=normalize_linewidth
    )


def validate_inheritable_linewidth(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_linewidth(float(value.value))


def normalize_markersize(value: Any) -> float:
    return _positive_range(value, MIN_MARKERSIZE, MAX_MARKERSIZE, "Marker size")


def validate_markersize(value: float) -> bool:
    return MIN_MARKERSIZE <= value <= MAX_MARKERSIZE


def normalize_inheritable_markersize(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Marker size", inner_normalizer=normalize_markersize
    )


def validate_inheritable_markersize(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_markersize(float(value.value))


def normalize_markeredgewidth(value: Any) -> float:
    return _positive_range(
        value, MIN_LINEWIDTH, MAX_LINEWIDTH, "Marker edge width"
    )


def validate_markeredgewidth(value: float) -> bool:
    return MIN_LINEWIDTH <= value <= MAX_LINEWIDTH


def normalize_inheritable_markeredgewidth(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value,
        name="Marker edge width",
        inner_normalizer=normalize_markeredgewidth,
    )


def validate_inheritable_markeredgewidth(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_markeredgewidth(float(value.value))
    )


def normalize_line_marker(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SettingsValidationError("Marker must be a closed Matplotlib preset.")
    if isinstance(value, int):
        raise SettingsValidationError("Marker must be a closed string preset.")
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null"}:
        return "None"
    if text not in CLOSED_LINE_MARKERS:
        raise SettingsValidationError(
            f"Marker must be one of {list(CLOSED_LINE_MARKERS)!r}."
        )
    return text


def validate_line_marker(value: str) -> bool:
    return value in CLOSED_LINE_MARKERS


def normalize_inheritable_line_marker(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Line marker", inner_normalizer=normalize_line_marker
    )


def validate_inheritable_line_marker(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_line_marker(str(value.value))


def normalize_scatter_marker(value: Any) -> str:
    marker = normalize_line_marker(value)
    if marker == "None":
        raise SettingsValidationError("Scatter marker cannot be None.")
    return marker


def validate_scatter_marker(value: str) -> bool:
    return value in CLOSED_LINE_MARKERS and value != "None"


def normalize_inheritable_scatter_marker(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value,
        name="Scatter marker",
        inner_normalizer=normalize_scatter_marker,
    )


def validate_inheritable_scatter_marker(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_scatter_marker(str(value.value))
    )


def normalize_scatter_size(value: Any) -> float:
    return _positive_range(value, MIN_SCATTER_SIZE, MAX_SCATTER_SIZE, "Scatter size")


def validate_scatter_size(value: float) -> bool:
    return MIN_SCATTER_SIZE <= value <= MAX_SCATTER_SIZE


def normalize_inheritable_scatter_size(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Scatter size", inner_normalizer=normalize_scatter_size
    )


def validate_inheritable_scatter_size(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode and validate_scatter_size(float(value.value))
    )


def normalize_fontfamily(value: Any) -> str:
    if not isinstance(value, str):
        raise SettingsValidationError("Font family must be a string.")
    text = value.strip()
    if not text or "\x00" in text:
        raise SettingsValidationError("Font family must be a non-empty string.")
    return text


def validate_fontfamily(value: str) -> bool:
    return bool(value) and "\x00" not in value


def normalize_inheritable_fontfamily(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Font family", inner_normalizer=normalize_fontfamily
    )


def validate_inheritable_fontfamily(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_fontfamily(str(value.value))


def normalize_fontsize(value: Any) -> float:
    return _positive_range(value, MIN_FONTSIZE, MAX_FONTSIZE, "Font size")


def validate_fontsize(value: float) -> bool:
    return MIN_FONTSIZE <= value <= MAX_FONTSIZE


def normalize_inheritable_fontsize(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Font size", inner_normalizer=normalize_fontsize
    )


def validate_inheritable_fontsize(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_fontsize(float(value.value))


def normalize_fontweight(value: Any) -> str | int:
    if isinstance(value, bool):
        raise SettingsValidationError("Font weight must be a name or integer.")
    if isinstance(value, int):
        if value < 1 or value > 1000:
            raise SettingsValidationError("Numeric font weight must be 1–1000.")
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return normalize_fontweight(int(value))
    if not isinstance(value, str):
        raise SettingsValidationError("Font weight must be a name or integer.")
    text = value.strip().casefold()
    for name in CLOSED_FONT_WEIGHTS:
        if name == text:
            return name
    raise SettingsValidationError(
        "Font weight must be a Matplotlib named weight or 1–1000."
    )


def validate_fontweight(value: str | int) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return 1 <= value <= 1000
    return value in CLOSED_FONT_WEIGHTS


def normalize_inheritable_fontweight(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Font weight", inner_normalizer=normalize_fontweight
    )


def validate_inheritable_fontweight(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_fontweight(value.value)


def normalize_fontstyle(value: Any) -> str:
    if not isinstance(value, str):
        raise SettingsValidationError("Font style must be a string.")
    text = value.strip().casefold()
    if text not in CLOSED_FONT_STYLES:
        raise SettingsValidationError(
            "Font style must be 'normal', 'italic', or 'oblique'."
        )
    return text


def validate_fontstyle(value: str) -> bool:
    return value in CLOSED_FONT_STYLES


def normalize_inheritable_fontstyle(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Font style", inner_normalizer=normalize_fontstyle
    )


def validate_inheritable_fontstyle(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_fontstyle(str(value.value))


def validate_inheritable_value(value: InheritableValue) -> bool:
    return isinstance(value, InheritableValue) and value.mode in DefaultValueMode


def normalize_closed_bool(value: Any) -> bool:
    if value is True or value is False:
        return value
    raise SettingsValidationError("Value must be a boolean.")


def validate_closed_bool(value: bool) -> bool:
    return value is True or value is False


def normalize_inheritable_bool(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Boolean", inner_normalizer=normalize_closed_bool
    )


def validate_inheritable_bool(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_closed_bool(value.value)


def normalize_axisbelow(value: Any) -> bool | str:
    if value is True or value is False:
        return value
    if isinstance(value, str) and value.strip().casefold() == "line":
        return "line"
    raise SettingsValidationError("axisbelow must be True, False, or 'line'.")


def validate_axisbelow(value: bool | str) -> bool:
    return value in CLOSED_AXISBELOW


def normalize_inheritable_axisbelow(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="axisbelow", inner_normalizer=normalize_axisbelow
    )


def validate_inheritable_axisbelow(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_axisbelow(value.value)


def normalize_tick_direction(value: Any) -> str:
    if not isinstance(value, str):
        raise SettingsValidationError("Tick direction must be a string.")
    text = value.strip().casefold()
    if text not in CLOSED_TICK_DIRECTIONS:
        raise SettingsValidationError(
            "Tick direction must be 'in', 'out', or 'inout'."
        )
    return text


def validate_tick_direction(value: str) -> bool:
    return value in CLOSED_TICK_DIRECTIONS


def normalize_inheritable_tick_direction(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value,
        name="Tick direction",
        inner_normalizer=normalize_tick_direction,
    )


def validate_inheritable_tick_direction(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_tick_direction(str(value.value))
    )


def normalize_tick_length(value: Any) -> float:
    return _positive_range(
        value, MIN_TICK_LENGTH, MAX_TICK_LENGTH, "Tick length"
    )


def validate_tick_length(value: float) -> bool:
    return MIN_TICK_LENGTH <= value <= MAX_TICK_LENGTH


def normalize_inheritable_tick_length(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Tick length", inner_normalizer=normalize_tick_length
    )


def validate_inheritable_tick_length(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode and validate_tick_length(float(value.value))
    )


def normalize_tick_pad(value: Any) -> float:
    return _positive_range(value, MIN_TICK_LENGTH, MAX_TICK_LENGTH, "Tick pad")


def validate_tick_pad(value: float) -> bool:
    return MIN_TICK_LENGTH <= value <= MAX_TICK_LENGTH


def normalize_inheritable_tick_pad(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Tick pad", inner_normalizer=normalize_tick_pad
    )


def validate_inheritable_tick_pad(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_tick_pad(float(value.value))


def normalize_rotation(value: Any) -> float:
    return _positive_range(value, MIN_ROTATION, MAX_ROTATION, "Rotation")


def validate_rotation(value: float) -> bool:
    return MIN_ROTATION <= value <= MAX_ROTATION


def normalize_inheritable_rotation(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value, name="Rotation", inner_normalizer=normalize_rotation
    )


def validate_inheritable_rotation(value: InheritableValue) -> bool:
    return value.mode in DefaultValueMode and validate_rotation(float(value.value))


def normalize_optional_grid_alpha(value: Any) -> float | None:
    if value is None:
        return None
    return _positive_range(
        value, MIN_GRID_ALPHA, MAX_GRID_ALPHA, "Grid alpha"
    )


def validate_optional_grid_alpha(value: float | None) -> bool:
    if value is None:
        return True
    return MIN_GRID_ALPHA <= float(value) <= MAX_GRID_ALPHA


def normalize_inheritable_optional_grid_alpha(value: Any) -> InheritableValue:
    return _normalize_inheritable(
        value,
        name="Grid alpha",
        inner_normalizer=normalize_optional_grid_alpha,
    )


def validate_inheritable_optional_grid_alpha(value: InheritableValue) -> bool:
    return (
        value.mode in DefaultValueMode
        and validate_optional_grid_alpha(value.value)
    )
