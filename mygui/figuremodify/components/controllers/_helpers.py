"""Shared Controller value normalizers and first-party constants."""

from __future__ import annotations

import base64
from copy import deepcopy
from io import BytesIO
import math
from numbers import Real
from pathlib import Path
from typing import Any
import warnings

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.legend import Legend
from matplotlib.markers import MarkerStyle
from matplotlib.spines import Spine
from PIL import Image, ImageOps, UnidentifiedImageError

from mygui.database import ColumnRef
from mygui.resource_limits import load_resource_limits
from mygui.figuremodify.matplotlib_adapter import (
    available_style_names,
)

from ..errors import ComponentValidationError
from ..models import (
    ComponentState,
    PropertySpec,
)
from ..property_values import (
    normalize_connector,
    normalize_line_pattern,
    normalize_marker,
)

def _positive(value: float) -> bool:
    return value > 0


def _nonnegative(value: float) -> bool:
    return value >= 0


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _primary_font_family(value: Any) -> str:
    """Return one non-empty primary family from Matplotlib-compatible input."""

    if isinstance(value, str):
        if value.strip():
            return value
        raise ComponentValidationError("Font family cannot be empty.")
    if isinstance(value, (tuple, list)):
        if not value:
            raise ComponentValidationError("Font family list cannot be empty.")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ComponentValidationError(
                "Font family list entries must be non-empty strings."
            )
        return value[0]
    raise ComponentValidationError(
        "Font family must be a string or a non-empty string sequence."
    )


def _url_sequence(value: Any) -> tuple[str | None, ...]:
    if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
        raise ComponentValidationError("URLs must be an array.")
    return tuple(None if item is None else str(item) for item in value)


def _line_pattern(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"kind": "preset", "value": value}
    elif isinstance(value, tuple) and len(value) == 2:
        value = {"kind": "custom", "offset": value[0], "dashes": list(value[1])}
    return normalize_line_pattern(value)


def _marker_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        if isinstance(value, tuple) and len(value) == 3:
            value = {
                "kind": "regular_polygon",
                "sides": value[0],
                "style": value[1],
                "angle": value[2],
            }
        else:
            value = {"kind": "symbol", "value": value}
    return normalize_marker(value)


def _connectors(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ComponentValidationError("Zoom inset requires four connector specs.")
    return tuple(normalize_connector(item) for item in value)


def _optional_sketch(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__") or len(value) != 3:
        raise ComponentValidationError("Sketch parameters require three values.")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ComponentValidationError("Sketch parameters must be finite.")
    if any(item <= 0 for item in result):
        raise ComponentValidationError("Sketch parameters must be positive.")
    return result


def _set_sketch(artist: Any, value: Any) -> None:
    if value is None:
        artist.set_sketch_params(None)
    else:
        artist.set_sketch_params(*value)


_ARTIST_EXPORT_PROPERTIES = (
    PropertySpec("clip_on", bool, True, editor="check", advanced=True),
    PropertySpec(
        "gid",
        str,
        None,
        editor="text",
        allow_none=True,
        normalizer=_optional_text,
        advanced=True,
    ),
    PropertySpec("in_layout", bool, True, editor="check", advanced=True),
    PropertySpec("rasterized", bool, False, editor="check", advanced=True),
    PropertySpec(
        "sketch_params",
        tuple,
        None,
        editor="triplet",
        allow_none=True,
        normalizer=_optional_sketch,
        setter=_set_sketch,
        advanced=True,
    ),
    PropertySpec(
        "snap",
        bool,
        None,
        editor="combo",
        choices=(None, True, False),
        allow_none=True,
        advanced=True,
    ),
    PropertySpec(
        "url",
        str,
        None,
        editor="text",
        allow_none=True,
        normalizer=_optional_text,
        advanced=True,
    ),
)


def _normalize_color(value: Any) -> str:
    if not mcolors.is_color_like(value):
        raise ComponentValidationError(f"Invalid Matplotlib color: {value!r}.")
    rgba = mcolors.to_rgba(value)
    return mcolors.to_hex(rgba, keep_alpha=rgba[3] < 1)


def _read_color(value: Any) -> str:
    try:
        return _normalize_color(value)
    except (ComponentValidationError, ValueError):
        return str(value)


def _pair(value: Any) -> tuple[float, float]:
    if (
        isinstance(value, (str, bytes))
        or not hasattr(value, "__len__")
        or len(value) != 2
    ):
        raise ComponentValidationError("Expected a pair of numbers.")
    return float(value[0]), float(value[1])


def _nondegenerate_pair(value: tuple[float, float]) -> bool:
    return value[0] != value[1]


def _positive_pair(value: tuple[float, float]) -> bool:
    return value[0] > 0 and value[1] > 0


def _anchor(value: Any) -> str | tuple[float, float]:
    if isinstance(value, str):
        candidate = value.upper()
        if candidate not in {"C", "SW", "S", "SE", "E", "NE", "N", "NW", "W"}:
            raise ComponentValidationError("Invalid Axes anchor.")
        return candidate
    candidate = _pair(value)
    if not all(0 <= item <= 1 for item in candidate):
        raise ComponentValidationError("Axes anchor coordinates must be between zero and one.")
    return candidate


def _legend_anchor(value: Any) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__") or len(value) not in {2, 4}:
        raise ComponentValidationError("Legend anchor requires two or four values.")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ComponentValidationError("Legend anchor must be finite.")
    return result


_DEFAULT_FONT_SPEC = {
    "family": ["sans-serif"],
    "size": 10.0,
    "weight": "normal",
    "style": "normal",
    "stretch": "normal",
    "variant": "normal",
    "color": "#000000",
}


def _rectangle(value: Any) -> tuple[float, float, float, float]:
    if (
        isinstance(value, (str, bytes))
        or not hasattr(value, "__len__")
        or len(value) != 4
    ):
        raise ComponentValidationError("Expected four rectangle values.")
    result = tuple(float(item) for item in value)
    if result[2] <= 0 or result[3] <= 0:
        raise ComponentValidationError(
            "Rectangle width and height must be positive."
        )
    return result


def _in_axes_rectangle(value: Any) -> tuple[float, float, float, float]:
    result = _rectangle(value)
    if not all(math.isfinite(item) for item in result):
        raise ComponentValidationError("Inset bounds must be finite.")
    return result


def _in_axes_range(value: Any) -> tuple[float, float]:
    result = _pair(value)
    if not all(math.isfinite(item) for item in result):
        raise ComponentValidationError("Inset limits must be finite.")
    if result[0] == result[1]:
        raise ComponentValidationError("Inset limits must not be degenerate.")
    return result


def _optional_extent(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__") or len(value) != 4:
        raise ComponentValidationError("Image extent requires four values.")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ComponentValidationError("Image extent must be finite.")
    if result[0] == result[1] or result[2] == result[3]:
        raise ComponentValidationError("Image extent must be non-degenerate.")
    return result


IN_AXES_IMAGE_MIMES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


def _validate_in_axes_image_data(data: dict[str, Any]) -> bytes:
    expected = {"filename", "mime_type", "payload_base64"}
    if set(data) != expected:
        raise ComponentValidationError(
            "Image inset data fields must be filename, mime_type, and "
            "payload_base64."
        )
    filename = data.get("filename")
    mime_type = data.get("mime_type")
    payload = data.get("payload_base64")
    if not isinstance(filename, str) or not filename.strip():
        raise ComponentValidationError("Image inset filename must be non-empty.")
    if Path(filename).name != filename:
        raise ComponentValidationError(
            "Image inset filename must not contain a directory path."
        )
    if mime_type not in set(IN_AXES_IMAGE_MIMES.values()):
        raise ComponentValidationError("Image inset MIME type is unsupported.")
    if not isinstance(payload, str) or not payload:
        raise ComponentValidationError("Image inset payload must be non-empty.")
    limits = load_resource_limits()
    maximum_base64_length = 4 * ((limits.max_image_bytes + 2) // 3)
    if len(payload) > maximum_base64_length:
        raise ComponentValidationError(
            "Image inset payload exceeds the configured byte budget."
        )
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise ComponentValidationError(
            "Image inset payload is not valid Base64."
        ) from exc
    if len(decoded) > limits.max_image_bytes:
        raise ComponentValidationError(
            "Image inset payload exceeds the configured byte budget."
        )
    return decoded


def decode_in_axes_image(data: dict[str, Any]) -> np.ndarray:
    """Decode and verify one embedded image-inset payload."""

    payload = _validate_in_axes_image_data(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as image:
                limits = load_resource_limits()
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width > limits.max_image_dimension
                    or height > limits.max_image_dimension
                    or width * height > limits.max_image_pixels
                ):
                    raise ComponentValidationError(
                        "Image inset dimensions exceed the configured pixel budget."
                    )
                detected_format = str(image.format or "").upper()
                detected_mime = IN_AXES_IMAGE_MIMES.get(detected_format)
                if detected_mime is None:
                    raise ComponentValidationError(
                        "Image inset format must be PNG, JPEG, BMP, or TIFF."
                    )
                if detected_mime != data["mime_type"]:
                    raise ComponentValidationError(
                        "Image inset MIME type does not match its payload."
                    )
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA")
                return np.asarray(image).copy()
    except ComponentValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise ComponentValidationError(
            "Image inset payload could not be decoded safely."
        ) from exc


def _optional_pair(value: Any) -> tuple[float, float] | None:
    return None if value is None else _pair(value)


def _aspect(value: Any) -> str | float:
    if isinstance(value, str):
        lowered = value.lower()
        if lowered not in {"auto", "equal"}:
            raise ComponentValidationError(
                "Axes aspect must be 'auto', 'equal', or a positive number."
            )
        return lowered
    result = float(value)
    if result <= 0:
        raise ComponentValidationError("Axes aspect must be positive.")
    return result


def _spine_position(value: Any) -> str | tuple[str, float]:
    if isinstance(value, str):
        if value not in {"center", "zero"}:
            raise ComponentValidationError(
                "Spine position must be 'center', 'zero', or a position pair."
            )
        return value
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ComponentValidationError("Spine position must be a pair.")
    kind = str(value[0])
    if kind not in {"outward", "axes", "data"}:
        raise ComponentValidationError(
            "Unknown spine position coordinate system."
        )
    return kind, float(value[1])


def _set_spine_bounds(spine: Spine, value: Any) -> None:
    if value is not None:
        spine.set_bounds(*value)
        return
    # Matplotlib's public set_bounds(None, None) explicitly means "keep the
    # current limits"; it provides no public operation for restoring the
    # documented get_bounds() == None state.
    spine._bounds = None
    spine.stale = True


LINESTYLE_ALIASES = {
    "solid": "-",
    "dashed": "--",
    "dashdot": "-.",
    "dash-dot": "-.",
    "dotted": ":",
    "none": "None",
}


def normalize_linestyle(value: Any) -> str:
    """Normalize linestyle."""

    if not isinstance(value, str):
        raise ComponentValidationError("Line style must be a string.")
    normalized = LINESTYLE_ALIASES.get(value.strip().lower(), value)
    if normalized not in {"-", "--", "-.", ":", "None"}:
        raise ComponentValidationError(
            f"Invalid Matplotlib line style: {value!r}."
        )
    return normalized


def normalize_reference_positions(value: Any) -> list[float]:
    """Normalize an ordered finite reflection-position sequence."""

    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ComponentValidationError(
                "Reflection positions must be one-dimensional."
            )
        values = value.tolist()
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise ComponentValidationError(
            "Reflection positions must be a numeric sequence."
        )
    normalized: list[float] = []
    for index, item in enumerate(values):
        if isinstance(item, bool) or not isinstance(item, Real):
            raise ComponentValidationError(
                f"Reflection position {index} must be a number."
            )
        number = float(item)
        if not math.isfinite(number):
            raise ComponentValidationError(
                f"Reflection position {index} must be finite."
            )
        normalized.append(number)
    return normalized


def normalize_position_ref(value: Any) -> dict[str, str] | None:
    """Normalize a nullable Number-column reference for Reflection Positions."""

    if value is None:
        return None
    if isinstance(value, ColumnRef):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise ComponentValidationError(
            "Reflection position_ref must be null or a column reference."
        )
    if set(value) != {"project_id", "sheet_id", "column_id"}:
        raise ComponentValidationError(
            "Reflection position_ref requires only project_id, sheet_id, "
            "and column_id."
        )
    try:
        return ColumnRef.from_dict(value).to_dict()
    except (TypeError, ValueError) as exc:
        raise ComponentValidationError(
            "Reflection position_ref is not a valid column reference."
        ) from exc


FIXED_REFLECTION_PLACEMENT = {"kind": "fixed"}
REFERENCE_MARKS_DATA_KEYS = frozenset({"positions", "position_ref", "placement"})


def _required_position_ref(value: Any, *, field: str) -> dict[str, str]:
    normalized = normalize_position_ref(value)
    if normalized is None:
        raise ComponentValidationError(
            f"Reflection placement {field} must be a column reference."
        )
    return normalized


def normalize_reflection_placement(value: Any) -> dict[str, Any]:
    """Normalize the closed tagged Reflection Positions placement contract."""

    if value is None:
        return dict(FIXED_REFLECTION_PLACEMENT)
    if not isinstance(value, dict):
        raise ComponentValidationError(
            "Reflection placement must be a tagged object."
        )
    kind = value.get("kind")
    if kind == "fixed":
        if set(value) != {"kind"}:
            raise ComponentValidationError(
                "Fixed Reflection placement may only contain kind."
            )
        return dict(FIXED_REFLECTION_PLACEMENT)
    if kind == "between_table_ranges":
        if set(value) != {"kind", "lower_ref", "upper_refs"}:
            raise ComponentValidationError(
                "between_table_ranges placement requires kind, lower_ref, "
                "and upper_refs."
            )
        upper_refs = value.get("upper_refs")
        if not isinstance(upper_refs, (list, tuple)) or len(upper_refs) != 2:
            raise ComponentValidationError(
                "between_table_ranges upper_refs must contain exactly two "
                "column references."
            )
        return {
            "kind": "between_table_ranges",
            "lower_ref": _required_position_ref(
                value.get("lower_ref"),
                field="lower_ref",
            ),
            "upper_refs": [
                _required_position_ref(item, field=f"upper_refs[{index}]")
                for index, item in enumerate(upper_refs)
            ],
        }
    raise ComponentValidationError(
        "Reflection placement kind must be 'fixed' or 'between_table_ranges'."
    )


def complete_reference_marks_data(data: Any) -> dict[str, Any]:
    """Fill v15 defaults then normalize the closed Reflection Positions data."""

    if not isinstance(data, dict):
        raise ComponentValidationError(
            "Reference Marks data must be a mapping."
        )
    payload = dict(data)
    payload.setdefault("position_ref", None)
    payload.setdefault("placement", dict(FIXED_REFLECTION_PLACEMENT))
    return normalize_reference_marks_data(payload)


def normalize_reference_marks_data(data: Any) -> dict[str, Any]:
    """Normalize the closed schema-v15 Reflection Positions data object."""

    if not isinstance(data, dict):
        raise ComponentValidationError(
            "Reference Marks data must be a mapping."
        )
    if set(data) != REFERENCE_MARKS_DATA_KEYS:
        raise ComponentValidationError(
            "Reference Marks data requires positions, position_ref, and "
            "placement."
        )
    return {
        "positions": normalize_reference_positions(data["positions"]),
        "position_ref": normalize_position_ref(data.get("position_ref")),
        "placement": normalize_reflection_placement(data.get("placement")),
    }


def reflection_placement_is_automatic(value: Any) -> bool:
    """Return whether baseline is owned by between-table-range placement."""

    return normalize_reflection_placement(value)["kind"] == "between_table_ranges"


def _y_lower_reserve_value(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and 0.0 <= number < 0.9


def _figure_style(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComponentValidationError(
            "Figure style must be a non-empty string."
        )
    style = value.strip()
    if (
        style != "default"
        and style not in available_style_names()
        and not Path(style).is_file()
    ):
        raise ComponentValidationError(
            f"Unknown Matplotlib style: {style!r}."
        )
    return style


def _rotation(value: Any) -> str | float:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"horizontal", "vertical"}:
            return lowered
        try:
            value = float(value)
        except ValueError as exc:
            raise ComponentValidationError(
                "Text rotation must be a number, 'horizontal', or 'vertical'."
            ) from exc
    result = float(value)
    if not math.isfinite(result):
        raise ComponentValidationError("Text rotation must be finite.")
    return result


def _legend_location(value: Any) -> str | int | tuple[float, float]:
    if isinstance(value, bool):
        raise ComponentValidationError("Legend location is invalid.")
    if isinstance(value, str):
        if value not in Legend.codes:
            raise ComponentValidationError(
                f"Unknown legend location: {value!r}."
            )
        return value
    if isinstance(value, int):
        valid_codes = set(Legend.codes.values())
        if value not in valid_codes:
            raise ComponentValidationError(
                f"Unknown legend location code: {value!r}."
            )
        return value
    return _pair(value)


def _column_reference(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ComponentValidationError(
            f"{name} must be a column reference object."
        )
    expected = {"project_id", "sheet_id", "column_id"}
    if set(value) != expected or any(
        not isinstance(value[key], str) or not value[key].strip()
        for key in expected
    ):
        raise ComponentValidationError(f"{name} is not a valid column reference.")
    return deepcopy(value)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ComponentValidationError(f"{name} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ComponentValidationError(
            f"{name} must be a finite number."
        ) from exc
    if not math.isfinite(result):
        raise ComponentValidationError(f"{name} must be a finite number.")
    return result


def _exact_data_fields(
    state: ComponentState,
    expected: set[str],
) -> None:
    if set(state.data) != expected:
        raise ComponentValidationError(
            f"{state.role.value} data fields must be "
            f"{sorted(expected)!r}."
        )


def _marker(value: Any) -> str:
    if not isinstance(value, str):
        raise ComponentValidationError("Marker must be a string.")
    try:
        MarkerStyle(value)
    except (TypeError, ValueError) as exc:
        raise ComponentValidationError(
            f"Unknown Matplotlib marker {value!r}."
        ) from exc
    return value


def _axis_name(state: ComponentState) -> str:
    value = state.selector.get("axis")
    if value not in {"x", "y"}:
        raise ComponentValidationError(
            "Axis component selector requires axis='x' or axis='y'."
        )
    return value


def _level(state: ComponentState) -> str:
    value = state.selector.get("level")
    if value not in {"major", "minor"}:
        raise ComponentValidationError(
            "Tick/grid selector requires level='major' or level='minor'."
        )
    return value


def bind_closed_property_handlers(
    *,
    specs: tuple[PropertySpec, ...],
    readers: dict[str, Any],
    writers: dict[str, Any],
    owner: str,
) -> None:
    """Fail closed unless every PropertySpec has exactly one read and write handler."""

    keys = {spec.key for spec in specs}
    read_keys = set(readers)
    write_keys = set(writers)
    if read_keys != keys or write_keys != keys:
        raise RuntimeError(
            f"{owner} property handlers must cover every PropertySpec exactly; "
            f"missing_read={sorted(keys - read_keys)} "
            f"extra_read={sorted(read_keys - keys)} "
            f"missing_write={sorted(keys - write_keys)} "
            f"extra_write={sorted(write_keys - keys)}."
        )


def lookup_property_handler(
    table: dict[str, Any],
    spec: PropertySpec,
    *,
    owner: str,
    action: str,
) -> Any:
    """Return one registered handler or fail closed for an unknown property."""

    try:
        return table[spec.key]
    except KeyError as exc:
        raise ComponentValidationError(
            f"{owner} has no {action} handler for {spec.key!r}."
        ) from exc


def closed_handler_subset(
    table: dict[str, Any],
    specs: tuple[PropertySpec, ...],
    *,
    owner: str,
) -> dict[str, Any]:
    """Return the handler subset required by ``specs``, failing if any key is missing."""

    keys = {spec.key for spec in specs}
    missing = keys - set(table)
    if missing:
        raise RuntimeError(
            f"{owner} handler table is missing {sorted(missing)}."
        )
    return {key: table[key] for key in keys}
