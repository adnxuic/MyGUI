"""Concrete controllers for the first-party Matplotlib component set."""

from __future__ import annotations

import base64
from copy import deepcopy
from io import BytesIO
import math
from pathlib import Path
from typing import Any
import warnings

import numpy as np
from matplotlib import style as mpl_style
from matplotlib import colors as mcolors
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.spines import Spine
from matplotlib.text import Text
from PIL import Image, ImageOps, UnidentifiedImageError

from mygui.database.interpolate_func import (
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    SMOOTHING_SPLINE_METHOD,
    interpolate_dict,
)
from mygui.database import DataPreprocessSpec
from mygui.database.fit_result import (
    normalize_fit_options_for_storage,
    normalize_fit_result_for_storage,
)
from mygui.database.safe_expression import compile_math_expression
from mygui.resource_limits import load_resource_limits

from .base import ComponentController
from .errors import ComponentNotFoundError, ComponentValidationError
from .matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    AxesRemovalHandle,
    InAxesRemovalHandle,
)
from .models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    EditorKind,
    FitEngine,
    PropertySpec,
    RestorePhase,
    ScatterData,
    UpdateImpact,
    XYData,
)
from .property_values import (
    DEFAULT_FORMATTER,
    DEFAULT_MAJOR_LOCATOR,
    DEFAULT_MINOR_FORMATTER,
    DEFAULT_MINOR_LOCATOR,
    DEFAULT_NORM,
    DEFAULT_SCALE,
    apply_figure_layout,
    apply_line_pattern,
    apply_scale,
    build_formatter,
    build_locator,
    build_norm,
    default_scale_for_name,
    formatter_from_axis,
    locator_from_axis,
    legend_anchor_value,
    legend_location_value,
    map_scatter_sizes,
    marker_value,
    markevery_value,
    normalize_connector,
    normalize_figure_layout,
    normalize_font,
    normalize_formatter,
    normalize_line_pattern,
    normalize_legend_anchor,
    normalize_legend_location,
    normalize_locator,
    normalize_marker,
    normalize_markevery,
    normalize_norm,
    normalize_scale,
    normalize_scatter_color_map,
    normalize_scatter_size_map,
    normalize_text_box,
    scale_from_axis,
    text_box_kwargs,
    validate_fixed_ticker_pair,
)


def _positive(value: float) -> bool:
    return value > 0


def _nonnegative(value: float) -> bool:
    return value >= 0


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


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


def _figure_style(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComponentValidationError(
            "Figure style must be a non-empty string."
        )
    style = value.strip()
    if (
        style != "default"
        and style not in mpl_style.available
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


class ContainerController(ComponentController[Any]):
    """Coordinate state changes for container components."""

    CAPABILITIES = frozenset({"container"})


class FigureController(ContainerController):
    """Coordinate state changes for figure components."""

    KIND = ComponentKind.FIGURE
    ROLES = frozenset({ComponentRole.FIGURE})
    DELETION_POLICY = DeletionPolicy.FORBID
    PROPERTY_SPECS = (
        PropertySpec(
            "name",
            str,
            "",
            editor="text",
            getter=lambda _figure: "",
            setter=lambda _figure, _value: None,
        ),
        PropertySpec(
            "style",
            str,
            "default",
            editor="text",
            normalizer=_figure_style,
            getter=lambda _figure: "default",
            setter=lambda _figure, _value: None,
        ),
        PropertySpec(
            "size_inches",
            tuple,
            (6.4, 4.8),
            validator=_positive_pair,
            editor="size",
            normalizer=_pair,
        ),
        PropertySpec(
            "dpi",
            float,
            100.0,
            validator=_positive,
            editor="double_spin",
        ),
        PropertySpec(
            "facecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda figure: _read_color(figure.get_facecolor()),
        ),
        PropertySpec(
            "edgecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda figure: _read_color(figure.get_edgecolor()),
        ),
        PropertySpec("frameon", bool, True, editor="check"),
        PropertySpec(
            "linewidth",
            float,
            0.0,
            editor="double_spin",
            validator=_nonnegative,
            minimum=0.0,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
        ),
        PropertySpec(
            "layout_engine",
            dict,
            {"kind": "none", "params": {}},
            editor="layout_spec",
            normalizer=normalize_figure_layout,
            setter=apply_figure_layout,
        ),
        PropertySpec("label", str, "", editor="text", advanced=True),
        PropertySpec("visible", bool, True, editor="check", advanced=True),
        PropertySpec("zorder", float, 0.0, editor="double_spin", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = ContainerController.CAPABILITIES | frozenset(
        {"figure_style"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._property_callback = None
        self._metadata = {
            "name": str(state.properties.get("name", "")),
            "style": str(state.properties.get("style", "default")),
            "dpi": float(state.properties.get("dpi", 100.0)),
        }
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        """Require the schema-v10 layout collection."""

        _exact_data_fields(state, {"layouts"})
        layouts = state.data.get("layouts")
        if not isinstance(layouts, list):
            raise ComponentValidationError("Figure layouts must be an array.")
        layout_ids: set[str] = set()
        for raw in layouts:
            if not isinstance(raw, dict):
                raise ComponentValidationError("Each Figure layout must be an object.")
            expected = {
                "id",
                "nrows",
                "ncols",
                "width_ratios",
                "height_ratios",
                "margins",
                "spacing",
            }
            if set(raw) != expected:
                raise ComponentValidationError(
                    f"Figure layout fields must be {sorted(expected)!r}."
                )
            layout_id = raw.get("id")
            if not isinstance(layout_id, str) or not layout_id.strip():
                raise ComponentValidationError("Figure layout id is invalid.")
            if layout_id in layout_ids:
                raise ComponentValidationError("Figure layout ids must be unique.")
            layout_ids.add(layout_id)
            nrows = raw.get("nrows")
            ncols = raw.get("ncols")
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 6
                for value in (nrows, ncols)
            ):
                raise ComponentValidationError(
                    "Figure layout rows and columns must be between 1 and 6."
                )
            width_ratios = raw.get("width_ratios")
            height_ratios = raw.get("height_ratios")
            if (
                not isinstance(width_ratios, list)
                or len(width_ratios) != ncols
                or not isinstance(height_ratios, list)
                or len(height_ratios) != nrows
            ):
                raise ComponentValidationError(
                    "Figure layout ratios must match its grid dimensions."
                )
            for value in (*width_ratios, *height_ratios):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or float(value) <= 0
                ):
                    raise ComponentValidationError(
                        "Figure layout ratios must be positive finite numbers."
                    )
            margins = raw.get("margins")
            spacing = raw.get("spacing")
            if not isinstance(margins, dict) or set(margins) != {
                "left",
                "right",
                "bottom",
                "top",
            }:
                raise ComponentValidationError("Figure layout margins are invalid.")
            if not isinstance(spacing, dict) or set(spacing) != {
                "wspace",
                "hspace",
            }:
                raise ComponentValidationError("Figure layout spacing is invalid.")
            try:
                left = float(margins["left"])
                right = float(margins["right"])
                bottom = float(margins["bottom"])
                top = float(margins["top"])
                wspace = float(spacing["wspace"])
                hspace = float(spacing["hspace"])
            except (TypeError, ValueError) as exc:
                raise ComponentValidationError(
                    "Figure layout geometry must contain numbers."
                ) from exc
            if not all(
                math.isfinite(value)
                for value in (left, right, bottom, top, wspace, hspace)
            ):
                raise ComponentValidationError(
                    "Figure layout geometry must be finite."
                )
            if not 0 <= left < right <= 1 or not 0 <= bottom < top <= 1:
                raise ComponentValidationError("Figure layout margins are invalid.")
            if wspace < 0 or hspace < 0:
                raise ComponentValidationError("Figure layout spacing is invalid.")

    def set_property_callback(self, callback) -> None:
        """Attach an optional host synchronizer without introducing Qt."""

        self._property_callback = callback

    def _read_property(self, target: Figure, spec: PropertySpec) -> Any:
        if spec.key in self._metadata:
            return self._metadata[spec.key]
        if spec.key == "layout_engine":
            engine = target.get_layout_engine()
            name = "none" if engine is None else type(engine).__name__.lower()
            if "tight" in name:
                kind = "tight"
            elif "constrained" in name:
                kind = "compressed" if bool(getattr(engine, "_compress", False)) else "constrained"
            else:
                kind = "none"
            saved = self._state.properties.get("layout_engine")
            if isinstance(saved, dict) and saved.get("kind") == kind:
                return deepcopy(saved)
            if kind == "tight":
                return normalize_figure_layout(
                    {"kind": kind, "params": {"pad": None, "w_pad": None, "h_pad": None, "rect": None}}
                )
            if kind in {"constrained", "compressed"}:
                return normalize_figure_layout(
                    {"kind": kind, "params": {"w_pad": None, "h_pad": None, "wspace": None, "hspace": None, "rect": None}}
                )
            return normalize_figure_layout({"kind": "none", "params": {}})
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Figure, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key in self._metadata:
            self._metadata[spec.key] = value
            if spec.key == "dpi":
                target.set_dpi(value)
        else:
            super()._write_property(target, spec, value)
        if self._property_callback is not None:
            self._property_callback(spec.key, deepcopy(value))

class AxesController(ContainerController):
    """Coordinate state changes for axes components."""

    KIND = ComponentKind.AXES
    ROLES = frozenset({ComponentRole.AXES})
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec(
            "position",
            tuple,
            (0.125, 0.11, 0.775, 0.77),
            editor="rectangle",
            persistent=False,
            normalizer=_rectangle,
            getter=lambda axes: tuple(axes.get_position().bounds),
        ),
        PropertySpec(
            "xlim",
            tuple,
            (0.0, 1.0),
            validator=_nondegenerate_pair,
            editor="range",
            normalizer=_pair,
        ),
        PropertySpec(
            "ylim",
            tuple,
            (0.0, 1.0),
            validator=_nondegenerate_pair,
            editor="range",
            normalizer=_pair,
        ),
        PropertySpec(
            "aspect",
            (str, float),
            "auto",
            editor="aspect",
            normalizer=_aspect,
        ),
        PropertySpec(
            "facecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda axes: _read_color(axes.get_facecolor()),
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "autoscalex_on",
            bool,
            True,
            editor="check",
            getter="get_autoscalex_on",
            setter="set_autoscalex_on",
        ),
        PropertySpec(
            "autoscaley_on",
            bool,
            True,
            editor="check",
            getter="get_autoscaley_on",
            setter="set_autoscaley_on",
        ),
        PropertySpec(
            "color_cycle",
            dict,
            None,
            editor="auto",
            allow_none=True,
            getter=lambda _axes: None,
            setter=lambda _axes, _value: None,
        ),
        PropertySpec("xmargin", float, 0.05, editor="double_spin", minimum=-0.5, maximum=10.0),
        PropertySpec("ymargin", float, 0.05, editor="double_spin", minimum=-0.5, maximum=10.0),
        PropertySpec("adjustable", str, "box", editor="combo", choices=("box", "datalim")),
        PropertySpec(
            "anchor",
            (str, tuple),
            "C",
            editor="axes_anchor",
            normalizer=_anchor,
        ),
        PropertySpec(
            "box_aspect",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
        ),
        PropertySpec(
            "axisbelow",
            (bool, str),
            "line",
            editor="combo",
            choices=(True, False, "line"),
        ),
        PropertySpec(
            "frameon",
            bool,
            True,
            editor="check",
            getter="get_frame_on",
            setter="set_frame_on",
        ),
        PropertySpec("zorder", float, 0.0, editor="double_spin"),
        PropertySpec(
            "rasterization_zorder",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            advanced=True,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
            advanced=True,
        ),
        PropertySpec("label", str, "", editor="text", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = ContainerController.CAPABILITIES | frozenset(
        {"axes_style", "range"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._color_cycle = deepcopy(state.properties.get("color_cycle"))
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        _exact_data_fields(state, {"subplot"})
        subplot = state.data["subplot"]
        if not isinstance(subplot, dict):
            raise ComponentValidationError(
                "Axes subplot data must be an object."
            )
        expected = {
            "layout_id",
            "row",
            "column",
            "layer",
            "share_x_group",
            "share_y_group",
        }
        if set(subplot) != expected:
            raise ComponentValidationError(
                f"Axes subplot fields must be {sorted(expected)!r}."
            )
        if not isinstance(subplot["layout_id"], str) or not subplot[
            "layout_id"
        ].strip():
            raise ComponentValidationError("Axes layout id is invalid.")
        for key in ("row", "column"):
            value = subplot[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ComponentValidationError(f"Axes subplot {key} is invalid.")
        if subplot["layer"] not in {"primary", "right_y"}:
            raise ComponentValidationError("Axes subplot layer is invalid.")
        for key in ("share_x_group", "share_y_group"):
            value = subplot[key]
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ComponentValidationError(
                    f"Axes subplot {key} is invalid."
                )
        if subplot["layer"] == "right_y" and subplot["share_y_group"] is not None:
            raise ComponentValidationError(
                "A right Y Axes cannot join a shared Y group."
            )

    def _read_property(self, target: Axes, spec: PropertySpec) -> Any:
        if spec.key == "color_cycle":
            return deepcopy(self._color_cycle)
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axes, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "color_cycle":
            self._color_cycle = deepcopy(value)
            return
        super()._write_property(target, spec, value)

    def _restore_transaction_snapshot(self, snapshot) -> None:
        super()._restore_transaction_snapshot(snapshot)
        target_properties = snapshot[2]
        specs = self.property_specs()
        # Margins and box/aspect setters may invoke autoscale_view.  Restore
        # ordered limits after those side effects, then restore autoscale flags.
        for key in ("xlim", "ylim", "autoscalex_on", "autoscaley_on"):
            if key in target_properties:
                self._write_property(
                    self.resolve_target(),
                    specs[key],
                    deepcopy(target_properties[key]),
                )

    def prepare_remove(self) -> "AxesRemovalHandle":
        """Capture Matplotlib's pinned Axes containers without mutating them."""

        return MATPLOTLIB_REMOVAL.prepare_axes(self.resolve_target())

    def commit_remove(self, handle: "AxesRemovalHandle") -> None:
        """Temporarily detach an Axes without notifying Matplotlib observers."""

        MATPLOTLIB_REMOVAL.commit(handle)

    def rollback_remove(self, handle: "AxesRemovalHandle") -> None:
        """Restore the exact Axes containers and current-Axes stack."""

        MATPLOTLIB_REMOVAL.rollback(handle)

    def _finalize_remove(self, handle: "AxesRemovalHandle") -> None:
        """Publish Matplotlib's Axes removal only after Registry commit."""

        MATPLOTLIB_REMOVAL.finalize(handle)


class AxisComponentController(ComponentController[Any]):
    """Coordinate state changes for axis component components."""

    CAPABILITIES = frozenset({"axis_component"})
    DELETION_POLICY = DeletionPolicy.HIDE

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)

class AxisController(AxisComponentController):
    """Coordinate state changes for axis components."""

    KIND = ComponentKind.AXIS
    ROLES = frozenset({ComponentRole.X_AXIS, ComponentRole.Y_AXIS})
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "scale",
            dict,
            deepcopy(DEFAULT_SCALE),
            editor="scale_spec",
            tooltip="Configure the axis scale and its validated parameters.",
            normalizer=lambda value: (
                default_scale_for_name(value)
                if isinstance(value, str)
                else normalize_scale(value)
            ),
        ),
        PropertySpec(
            "major_locator",
            dict,
            deepcopy(DEFAULT_MAJOR_LOCATOR),
            editor="locator_spec",
            tooltip="Configure how major tick locations are generated.",
            normalizer=normalize_locator,
        ),
        PropertySpec(
            "major_formatter",
            dict,
            deepcopy(DEFAULT_FORMATTER),
            editor="formatter_spec",
            tooltip="Configure how major tick labels are formatted.",
            normalizer=normalize_formatter,
        ),
        PropertySpec(
            "minor_locator",
            dict,
            deepcopy(DEFAULT_MINOR_LOCATOR),
            editor="locator_spec",
            tooltip="Configure how minor tick locations are generated.",
            normalizer=normalize_locator,
        ),
        PropertySpec(
            "minor_formatter",
            dict,
            deepcopy(DEFAULT_MINOR_FORMATTER),
            editor="formatter_spec",
            tooltip="Configure how minor tick labels are formatted.",
            normalizer=normalize_formatter,
        ),
        PropertySpec(
            "label_position",
            str,
            "bottom",
            editor="combo",
            choices=("bottom", "top", "left", "right"),
        ),
        PropertySpec(
            "remove_overlapping_locs",
            bool,
            True,
            editor="check",
        ),
        PropertySpec(
            "offset_font",
            dict,
            {
                "family": ["sans-serif"],
                "size": 10.0,
                "weight": "normal",
                "style": "normal",
                "stretch": "normal",
                "variant": "normal",
                "color": "#000000",
            },
            editor="font_spec",
            tooltip="Configure the offset text font and color.",
            normalizer=normalize_font,
        ),
        PropertySpec("offset_visible", bool, True, editor="check"),
        PropertySpec("zorder", float, 1.5, editor="double_spin", advanced=True),
        PropertySpec(
            "alpha",
            float,
            None,
            editor="double_spin",
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
            advanced=True,
        ),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"axis_scale"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        super()._validate_candidate(state)
        axis_name = _axis_name(state)
        label_positions = (
            {"top", "bottom"}
            if axis_name == "x"
            else {"left", "right"}
        )
        if state.properties.get("label_position") not in label_positions:
            raise ComponentValidationError(
                f"Invalid {axis_name}-axis label position."
            )
        for level in ("major", "minor"):
            validate_fixed_ticker_pair(
                state.properties[f"{level}_locator"],
                state.properties[f"{level}_formatter"],
            )

    def _capture_runtime_data(self, target: Axis) -> dict[str, Any]:
        return {
            "major_locator": target.get_major_locator(),
            "major_formatter": target.get_major_formatter(),
            "minor_locator": target.get_minor_locator(),
            "minor_formatter": target.get_minor_formatter(),
        }

    def _restore_runtime_data(self, target: Axis, snapshot: Any) -> None:
        if not isinstance(snapshot, dict):
            return
        target.set_major_locator(snapshot["major_locator"])
        target.set_major_formatter(snapshot["major_formatter"])
        target.set_minor_locator(snapshot["minor_locator"])
        target.set_minor_formatter(snapshot["minor_formatter"])

    def _restore_transaction_snapshot(self, snapshot) -> None:
        super()._restore_transaction_snapshot(snapshot)
        self._restore_runtime_data(self.resolve_target(), snapshot[1])

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        if spec.key == "scale":
            return scale_from_axis(target, self._state.properties.get("scale"))
        if spec.key in {"major_locator", "minor_locator"}:
            minor = spec.key.startswith("minor")
            locator = target.get_minor_locator() if minor else target.get_major_locator()
            return locator_from_axis(
                locator,
                self._state.properties.get(spec.key),
                minor=minor,
            )
        if spec.key in {"major_formatter", "minor_formatter"}:
            minor = spec.key.startswith("minor")
            formatter = target.get_minor_formatter() if minor else target.get_major_formatter()
            return formatter_from_axis(
                formatter,
                self._state.properties.get(spec.key),
                minor=minor,
            )
        if spec.key == "label_position":
            return target.get_label_position()
        if spec.key == "offset_font":
            offset = target.get_offset_text()
            return normalize_font(
                {
                    "family": list(offset.get_fontfamily()),
                    "size": float(offset.get_fontsize()),
                    "weight": offset.get_fontweight(),
                    "style": offset.get_fontstyle(),
                    "stretch": offset.get_fontproperties().get_stretch(),
                    "variant": offset.get_fontproperties().get_variant(),
                    "color": _read_color(offset.get_color()),
                }
            )
        if spec.key == "offset_visible":
            return bool(target.get_offset_text().get_visible())
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        axes = target.axes
        axis_name = _axis_name(self._state)
        if spec.key == "scale":
            apply_scale(axes, axis_name, value)
            # Matplotlib installs scale-specific default tickers as a side
            # effect. The persistent Axis ticker specs remain authoritative,
            # so always restore them after the scale change.
            target.set_major_locator(
                build_locator(self._state.properties["major_locator"])
            )
            target.set_major_formatter(
                build_formatter(self._state.properties["major_formatter"])
            )
            target.set_minor_locator(
                build_locator(self._state.properties["minor_locator"])
            )
            target.set_minor_formatter(
                build_formatter(self._state.properties["minor_formatter"])
            )
            return
        if spec.key in {"major_locator", "minor_locator"}:
            locator = build_locator(value)
            (target.set_minor_locator if spec.key.startswith("minor") else target.set_major_locator)(locator)
            return
        if spec.key in {"major_formatter", "minor_formatter"}:
            formatter = build_formatter(value)
            (target.set_minor_formatter if spec.key.startswith("minor") else target.set_major_formatter)(formatter)
            return
        if spec.key == "label_position":
            valid = {"top", "bottom"} if axis_name == "x" else {"left", "right"}
            if value not in valid:
                raise ComponentValidationError(
                    f"Invalid {axis_name}-axis label position {value!r}."
                )
            target.set_label_position(value)
            return
        if spec.key == "offset_font":
            offset = target.get_offset_text()
            offset.set_fontfamily(value["family"])
            offset.set_fontsize(value["size"])
            offset.set_fontweight(value["weight"])
            offset.set_fontstyle(value["style"])
            offset.set_fontstretch(value["stretch"])
            offset.set_fontvariant(value["variant"])
            offset.set_color(value["color"])
            return
        if spec.key == "offset_visible":
            target.get_offset_text().set_visible(bool(value))
            return
        super()._write_property(target, spec, value)


class XAxisController(AxisController):
    """Coordinate state changes for xaxis components."""

    ROLES = frozenset({ComponentRole.X_AXIS})
    PROPERTY_SPECS = tuple(
        PropertySpec(
            "label_position",
            str,
            "bottom",
            editor="combo",
            choices=("bottom", "top"),
        )
        if spec.key == "label_position"
        else spec
        for spec in AxisController.PROPERTY_SPECS
    )


class YAxisController(AxisController):
    """Coordinate state changes for yaxis components."""

    ROLES = frozenset({ComponentRole.Y_AXIS})
    PROPERTY_SPECS = tuple(
        PropertySpec(
            "label_position",
            str,
            "left",
            editor="combo",
            choices=("left", "right"),
        )
        if spec.key == "label_position"
        else spec
        for spec in AxisController.PROPERTY_SPECS
    ) + (
        PropertySpec(
            "offset_position",
            str,
            "left",
            editor="combo",
            choices=("left", "right"),
        ),
    )

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        if spec.key == "offset_position":
            return str(getattr(target, "offset_text_position", "left"))
        return super()._read_property(target, spec)

    def _write_property(self, target: Axis, spec: PropertySpec, value: Any) -> None:
        if spec.key == "offset_position":
            target.set_offset_position(value)
            return
        super()._write_property(target, spec, value)

    @classmethod
    def default_properties(cls) -> dict[str, Any]:
        """Return the default properties."""

        properties = super().default_properties()
        properties["label_position"] = "left"
        return properties


class SpineController(AxisComponentController):
    """Coordinate state changes for spine components."""

    KIND = ComponentKind.SPINE
    ROLES = frozenset({ComponentRole.SPINE})
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda spine: _read_color(spine.get_edgecolor()),
            setter="set_edgecolor",
        ),
        PropertySpec(
            "linewidth",
            float,
            0.8,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
        ),
        PropertySpec(
            "position",
            (str, tuple),
            ("outward", 0.0),
            editor="spine_position",
            normalizer=_spine_position,
        ),
        PropertySpec(
            "bounds",
            tuple,
            None,
            editor="range",
            normalizer=_optional_pair,
            allow_none=True,
            getter=lambda spine: (
                None
                if spine.get_bounds() is None
                else tuple(spine.get_bounds())
            ),
            setter=_set_spine_bounds,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("joinstyle", str, "miter", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
        PropertySpec("zorder", float, 2.5, editor="double_spin", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"color", "line_style"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._line_pattern_value = _line_pattern(
            state.properties.get(
                "linestyle", {"kind": "preset", "value": "-"}
            )
        )
        super().__init__(state, **kwargs)

    def _validate_candidate(self, state: ComponentState) -> None:
        name = state.selector.get("name")
        if name not in {"left", "right", "top", "bottom"}:
            raise ComponentValidationError(
                "Spine selector requires a standard spine name."
            )

    def _read_property(self, target: Spine, spec: PropertySpec) -> Any:
        if spec.key == "linestyle":
            return deepcopy(self._line_pattern_value)
        if spec.key != "color":
            return super()._read_property(target, spec)
        value = _read_color(target.get_edgecolor())
        if target.get_alpha() is None:
            return value
        actual_rgba = mcolors.to_rgba(value)
        saved = self._state.properties.get("color")
        if saved is not None:
            try:
                saved_rgba = mcolors.to_rgba(saved)
            except (TypeError, ValueError):
                saved_rgba = None
            if (
                saved_rgba is not None
                and np.allclose(actual_rgba[:3], saved_rgba[:3])
            ):
                return _normalize_color(saved)
        return mcolors.to_hex(actual_rgba, keep_alpha=False)

    def _write_property(
        self, target: Spine, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "linestyle":
            apply_line_pattern(target, value)
            self._line_pattern_value = deepcopy(value)
            return
        super()._write_property(target, spec, value)


class TickGroupController(AxisComponentController):
    """Coordinate state changes for tick group components."""

    KIND = ComponentKind.TICK_GROUP
    ROLES = frozenset(
        {ComponentRole.MAJOR_TICK, ComponentRole.MINOR_TICK}
    )
    PROPERTY_SPECS = (
        PropertySpec("primary_visible", bool, True, editor="check"),
        PropertySpec("secondary_visible", bool, False, editor="check"),
        PropertySpec(
            "direction",
            str,
            "out",
            editor="combo",
            choices=("in", "out", "inout"),
        ),
        PropertySpec(
            "length",
            float,
            3.5,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "width",
            float,
            0.8,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec("zorder", float, 2.01, editor="double_spin"),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"tick_style", "color"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)
        _level(state)

    def _ticks(self, target: Axis) -> list[Any]:
        return (
            target.get_major_ticks()
            if _level(self._state) == "major"
            else target.get_minor_ticks()
        )

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        tick = ticks[0]
        line = tick.tick1line
        if spec.key == "primary_visible":
            return any(item.tick1line.get_visible() for item in ticks)
        if spec.key == "secondary_visible":
            return any(item.tick2line.get_visible() for item in ticks)
        if spec.key == "direction":
            return getattr(tick, "_tickdir", "out")
        if spec.key == "length":
            return float(line.get_markersize())
        if spec.key == "width":
            return float(line.get_markeredgewidth())
        if spec.key == "color":
            return _read_color(line.get_color())
        if spec.key == "zorder":
            return float(line.get_zorder())
        if spec.key == "antialiased":
            return bool(line.get_antialiased())
        if spec.key in {item.key for item in _ARTIST_EXPORT_PROPERTIES}:
            return super()._read_property(line, spec)
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key in {"primary_visible", "secondary_visible"}:
            axis_name = _axis_name(self._state)
            valid = ("bottom", "top") if axis_name == "x" else ("left", "right")
            side = valid[0] if spec.key == "primary_visible" else valid[1]
            target.set_tick_params(which=level, **{side: bool(value)})
            return
        if spec.key in {"zorder", "antialiased"} or spec.key in {item.key for item in _ARTIST_EXPORT_PROPERTIES}:
            setter = spec.setter
            for tick in self._ticks(target):
                for line in (tick.tick1line, tick.tick2line):
                    if callable(setter):
                        setter(line, value)
                    else:
                        name = setter if isinstance(setter, str) else f"set_{spec.key}"
                        getattr(line, name)(value)
            return
        target.set_tick_params(which=level, **{spec.key: value})

    def _delete_target(self, target: Axis) -> None:
        self._write_property(target, self.property_specs()["primary_visible"], False)
        self._write_property(target, self.property_specs()["secondary_visible"], False)

    def _hide_for_delete(self) -> ComponentChange:
        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                properties={"primary_visible": False, "secondary_visible": False},
            )
        )


class TickLabelGroupController(AxisComponentController):
    """Coordinate state changes for tick label group components."""

    KIND = ComponentKind.TICK_LABEL_GROUP
    ROLES = frozenset(
        {
            ComponentRole.MAJOR_TICK_LABEL,
            ComponentRole.MINOR_TICK_LABEL,
        }
    )
    PROPERTY_SPECS = (
        PropertySpec("primary_visible", bool, True, editor="check"),
        PropertySpec("secondary_visible", bool, False, editor="check"),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "fontsize",
            float,
            10.0,
            validator=_positive,
            editor="double_spin",
        ),
        PropertySpec("rotation", float, 0.0, editor="double_spin"),
        PropertySpec(
            "fontfamily",
            (str, tuple, list),
            "sans-serif",
            editor="font",
        ),
        PropertySpec(
            "pad",
            float,
            3.5,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "fontweight",
            (str, int, float),
            "normal",
            editor="named_number",
        ),
        PropertySpec("fontstyle", str, "normal", editor="combo", choices=("normal", "italic", "oblique")),
        PropertySpec("fontstretch", (str, int, float), "normal", editor="named_number", getter=lambda text: text.get_fontproperties().get_stretch()),
        PropertySpec("fontvariant", str, "normal", editor="combo", choices=("normal", "small-caps")),
        PropertySpec("alpha", float, None, editor="double_spin", allow_none=True, minimum=0.0, maximum=1.0),
        PropertySpec("rotation_mode", str, "default", editor="combo", choices=("default", "anchor", "xtick", "ytick")),
        PropertySpec("horizontalalignment", str, "center", editor="combo", choices=("left", "center", "right")),
        PropertySpec("verticalalignment", str, "baseline", editor="combo", choices=("top", "center", "bottom", "baseline", "center_baseline")),
        PropertySpec("multialignment", str, None, editor="combo", choices=(None, "left", "center", "right"), allow_none=True, getter=lambda text: getattr(text, "_multialignment", None)),
        PropertySpec("wrap", bool, False, editor="check"),
        PropertySpec("linespacing", float, 1.2, editor="double_spin", minimum=0.0, getter=lambda text: float(getattr(text, "_linespacing", 1.2))),
        PropertySpec("math_fontfamily", str, "dejavusans", editor="text"),
        PropertySpec("parse_math", bool, True, editor="check"),
        PropertySpec("usetex", bool, False, editor="check"),
        PropertySpec("bbox", dict, {"enabled": False}, editor="text_box", normalizer=normalize_text_box),
        PropertySpec("zorder", float, 3.0, editor="double_spin"),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
        PropertySpec("transform_rotates_text", bool, False, editor="check", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"tick_label_style", "color", "font"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)
        _level(state)

    def _ticks(self, target: Axis) -> list[Any]:
        return (
            target.get_major_ticks()
            if _level(self._state) == "major"
            else target.get_minor_ticks()
        )

    def _label(self, tick: Any) -> Text:
        return tick.label1

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        if spec.key == "primary_visible":
            return any(tick.label1.get_visible() for tick in ticks)
        if spec.key == "secondary_visible":
            return any(tick.label2.get_visible() for tick in ticks)
        label = self._label(ticks[0])
        if spec.key == "color":
            return _read_color(label.get_color())
        if spec.key == "fontsize":
            return float(label.get_fontsize())
        if spec.key == "rotation":
            return float(label.get_rotation())
        if spec.key == "fontfamily":
            return list(label.get_fontfamily())
        if spec.key == "pad":
            return float(ticks[0].get_pad())
        if spec.key == "bbox":
            return deepcopy(self._state.properties.get("bbox", {"enabled": False}))
        if spec.key in {item.key for item in _ARTIST_EXPORT_PROPERTIES} or spec.key in {
            "fontweight", "fontstyle", "fontstretch", "fontvariant", "alpha",
            "rotation_mode", "horizontalalignment", "verticalalignment",
            "multialignment", "wrap", "linespacing", "math_fontfamily",
            "parse_math", "usetex", "zorder", "antialiased", "transform_rotates_text",
        }:
            return super()._read_property(label, spec)
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key in {"primary_visible", "secondary_visible"}:
            axis_name = _axis_name(self._state)
            names = (
                ("bottom", "labelbottom"),
                ("top", "labeltop"),
            ) if axis_name == "x" else (
                ("left", "labelleft"),
                ("right", "labelright"),
            )
            index = 0 if spec.key == "primary_visible" else 1
            target.set_tick_params(which=level, **{names[index][1]: bool(value)})
            return
        if spec.key == "bbox":
            for tick in self._ticks(target):
                for label in (tick.label1, tick.label2):
                    label.set_bbox(text_box_kwargs(value))
            return
        if spec.key in {item.key for item in _ARTIST_EXPORT_PROPERTIES} or spec.key in {
            "fontweight", "fontstyle", "fontstretch", "fontvariant", "alpha",
            "rotation_mode", "horizontalalignment", "verticalalignment",
            "multialignment", "wrap", "linespacing", "math_fontfamily",
            "parse_math", "usetex", "zorder", "antialiased", "transform_rotates_text",
        }:
            for tick in self._ticks(target):
                for label in (tick.label1, tick.label2):
                    if spec.key == "multialignment" and value is None:
                        label._multialignment = None
                        label.stale = True
                        continue
                    if callable(spec.setter):
                        spec.setter(label, value)
                    else:
                        name = spec.setter if isinstance(spec.setter, str) else f"set_{spec.key}"
                        getattr(label, name)(value)
            return
        option = {
            "color": "labelcolor",
            "fontsize": "labelsize",
            "rotation": "labelrotation",
            "fontfamily": "labelfontfamily",
            "pad": "pad",
        }[spec.key]
        target.set_tick_params(which=level, **{option: value})

    def _delete_target(self, target: Axis) -> None:
        self._write_property(target, self.property_specs()["primary_visible"], False)
        self._write_property(target, self.property_specs()["secondary_visible"], False)

    def _hide_for_delete(self) -> ComponentChange:
        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                properties={"primary_visible": False, "secondary_visible": False},
            )
        )


class GridController(AxisComponentController):
    """Coordinate state changes for grid components."""

    KIND = ComponentKind.GRID
    ROLES = frozenset({ComponentRole.GRID})
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, False, editor="check"),
        PropertySpec(
            "color",
            str,
            "#b0b0b0",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
        ),
        PropertySpec(
            "linewidth",
            float,
            0.8,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "alpha",
            float,
            1.0,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec(
            "gapcolor",
            str,
            None,
            editor="optional_color",
            allow_none=True,
            normalizer=lambda value: None if value is None else _normalize_color(value),
        ),
        PropertySpec("dash_capstyle", str, "butt", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("dash_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("solid_capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("solid_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"grid_style", "color", "line_style"}
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._line_pattern_value = _line_pattern(
            state.properties.get(
                "linestyle", {"kind": "preset", "value": "-"}
            )
        )
        super().__init__(state, **kwargs)

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)
        _level(state)

    def _gridlines(self, target: Axis) -> list[Line2D]:
        ticks = (
            target.get_major_ticks()
            if _level(self._state) == "major"
            else target.get_minor_ticks()
        )
        return [tick.gridline for tick in ticks]

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        lines = self._gridlines(target)
        if not lines:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        line = lines[0]
        if spec.key == "visible":
            return any(item.get_visible() for item in lines)
        if spec.key == "color":
            return _read_color(line.get_color())
        if spec.key == "alpha":
            alpha = line.get_alpha()
            return 1.0 if alpha is None else float(alpha)
        if spec.key == "linestyle":
            return deepcopy(self._line_pattern_value)
        return getattr(line, f"get_{spec.key}")()

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key == "visible":
            target.grid(bool(value), which=level)
            return
        visible = bool(self._read_property(target, self.property_specs()["visible"]))
        if spec.key == "linestyle":
            pattern = normalize_line_pattern(value)
            linestyle = (
                pattern["value"]
                if pattern["kind"] == "preset"
                else (pattern["offset"], pattern["dashes"])
            )
            target.grid(
                True,
                which=level,
                linestyle=linestyle,
            )
            for line in self._gridlines(target):
                apply_line_pattern(line, pattern)
            self._line_pattern_value = deepcopy(pattern)
            target.grid(visible, which=level)
            return
        if spec.key in {item.key for item in _ARTIST_EXPORT_PROPERTIES}:
            for line in self._gridlines(target):
                if callable(spec.setter):
                    spec.setter(line, value)
                else:
                    name = spec.setter if isinstance(spec.setter, str) else f"set_{spec.key}"
                    getattr(line, name)(value)
        else:
            target.grid(True, which=level, **{spec.key: value})
            target.grid(visible, which=level)

    def _delete_target(self, target: Axis) -> None:
        target.grid(False, which=_level(self._state))


class TextController(ComponentController[Text]):
    """Coordinate state changes for text components."""

    KIND = ComponentKind.TEXT
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    ROLES = frozenset(
        {
            ComponentRole.TITLE,
            ComponentRole.X_LABEL,
            ComponentRole.Y_LABEL,
            ComponentRole.TEXT,
        }
    )
    PROPERTY_SPECS = (
        PropertySpec("text", str, "", editor="text"),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "position",
            tuple,
            (0.0, 0.0),
            editor="position",
            normalizer=_pair,
        ),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda text: _read_color(text.get_color()),
        ),
        PropertySpec(
            "fontsize",
            float,
            10.0,
            validator=_positive,
            editor="double_spin",
        ),
        PropertySpec(
            "fontfamily",
            str,
            "sans-serif",
            editor="font",
            normalizer=lambda value: (
                str(value[0])
                if isinstance(value, (tuple, list)) and value
                else str(value)
            ),
            getter=lambda text: str(text.get_fontfamily()[0]),
        ),
        PropertySpec(
            "fontweight",
            (str, int, float),
            "normal",
            editor="named_number",
        ),
        PropertySpec(
            "fontstyle",
            str,
            "normal",
            editor="combo",
            choices=("normal", "italic", "oblique"),
        ),
        PropertySpec(
            "rotation",
            (str, float),
            0.0,
            editor="rotation",
            normalizer=_rotation,
        ),
        PropertySpec(
            "horizontalalignment",
            str,
            "left",
            editor="combo",
            choices=("left", "center", "right"),
        ),
        PropertySpec(
            "verticalalignment",
            str,
            "baseline",
            editor="combo",
            choices=("top", "center", "bottom", "baseline", "center_baseline"),
        ),
        PropertySpec("usetex", bool, False, editor="check"),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("zorder", float, 3.0, editor="double_spin"),
        PropertySpec("bbox", dict, {"enabled": False}, editor="text_box", normalizer=normalize_text_box),
        PropertySpec("wrap", bool, False, editor="check"),
        PropertySpec("linespacing", float, 1.2, editor="double_spin", minimum=0.0, getter=lambda text: float(getattr(text, "_linespacing", 1.2))),
        PropertySpec("multialignment", str, None, editor="combo", choices=(None, "left", "center", "right"), allow_none=True, getter=lambda text: getattr(text, "_multialignment", None)),
        PropertySpec("rotation_mode", str, "default", editor="combo", choices=("default", "anchor")),
        PropertySpec("fontstretch", (str, int, float), "normal", editor="named_number", getter=lambda text: text.get_fontproperties().get_stretch()),
        PropertySpec("fontvariant", str, "normal", editor="combo", choices=("normal", "small-caps")),
        PropertySpec("math_fontfamily", str, "dejavusans", editor="text"),
        PropertySpec("parse_math", bool, True, editor="check"),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
        PropertySpec("transform_rotates_text", bool, False, editor="check", advanced=True),
        PropertySpec(
            "coordinate_system",
            str,
            "data",
            editor="combo",
            choices=("data", "axes", "figure"),
        ),
        PropertySpec("label", str, "", editor="text", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = frozenset({"text", "font", "color", "position"})

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._coordinate_system = str(
            state.properties.get(
                "coordinate_system",
                (
                    "figure"
                    if state.selector.get("scope") == "figure"
                    else "data"
                ),
            )
        )
        super().__init__(state, **kwargs)

    def read_state(self, *, strict: bool = False) -> ComponentState:
        """Keep persisted TeX intent separate from the effective artist mode."""

        state = super().read_state(strict=strict)
        properties = dict(state.properties)
        properties["usetex"] = bool(
            self._state.properties.get("usetex", False)
        )
        return state.clone(properties=properties)

    def _read_property(self, target: Text, spec: PropertySpec) -> Any:
        if spec.key == "bbox":
            return deepcopy(self._state.properties.get("bbox", {"enabled": False}))
        if spec.key == "coordinate_system":
            return self._coordinate_system
        return super()._read_property(target, spec)

    def _write_property(self, target: Text, spec: PropertySpec, value: Any) -> None:
        if spec.key == "bbox":
            target.set_bbox(text_box_kwargs(value))
            return
        if spec.key == "coordinate_system":
            axes = target.axes
            figure = target.figure
            if figure is None:
                raise ComponentValidationError("Text has no Figure transform.")
            if value in {"data", "axes"} and axes is None:
                raise ComponentValidationError(
                    "Figure text supports only figure coordinates."
                )
            display = target.get_transform().transform(target.get_position())
            transform = {
                "data": axes.transData if axes is not None else None,
                "axes": axes.transAxes if axes is not None else None,
                "figure": figure.transFigure,
            }[value]
            target.set_transform(transform)
            target.set_position(tuple(transform.inverted().transform(display)))
            self._coordinate_system = str(value)
            return
        if spec.key == "multialignment" and value is None:
            target._multialignment = None
            target.stale = True
            return
        super()._write_property(target, spec, value)


class TitleController(TextController):
    """Coordinate state changes for title components."""

    ROLES = frozenset({ComponentRole.TITLE})
    RESTORE_PHASE = None
    DELETION_POLICY = DeletionPolicy.HIDE
    PROPERTY_SPECS = tuple(
        spec for spec in TextController.PROPERTY_SPECS
        if spec.key != "coordinate_system"
    )

    def _write_property(
        self, target: Text, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "position" and isinstance(target.axes, Axes):
            target.axes._autotitlepos = False
        super()._write_property(target, spec, value)


class AxisLabelController(TextController):
    """Coordinate state changes for axis label components."""

    ROLES = frozenset({ComponentRole.X_LABEL, ComponentRole.Y_LABEL})
    RESTORE_PHASE = None
    DELETION_POLICY = DeletionPolicy.HIDE
    PROPERTY_SPECS = tuple(
        spec for spec in TextController.PROPERTY_SPECS
        if spec.key != "coordinate_system"
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)

    def _write_property(
        self, target: Text, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "position" and self._registry is not None:
            parent_id = self._state.parent_id
            parent = (
                self._registry.get(parent_id).resolve_target()
                if parent_id is not None and parent_id in self._registry
                else None
            )
            if not isinstance(parent, Axis):
                raise ComponentValidationError(
                    "Axis label has no parent Axis target."
                )
            # Axis draw recomputes an automatic label coordinate from renderer
            # extents.  Once a v10 position is restored or edited, retain the
            # existing transform but explicitly disable that automatic pass so
            # the persisted value remains stable across save/open/draw cycles.
            parent.set_label_coords(
                float(value[0]),
                float(value[1]),
                transform=target.get_transform(),
            )
            return
        super()._write_property(target, spec, value)

class LegendController(ComponentController[Legend]):
    """Coordinate state changes for legend components."""

    KIND = ComponentKind.LEGEND
    ROLES = frozenset({ComponentRole.LEGEND})
    DELETION_POLICY = DeletionPolicy.HIDE
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "location",
            dict,
            {"kind": "preset", "value": "best"},
            editor="legend_position",
            normalizer=normalize_legend_location,
        ),
        PropertySpec(
            "ncols",
            int,
            1,
            validator=lambda value: value >= 1,
            editor="spin",
        ),
        PropertySpec(
            "frameon",
            bool,
            True,
            editor="check",
            getter="get_frame_on",
            setter="set_frame_on",
        ),
        PropertySpec(
            "facecolor",
            str,
            "#ffffff",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "edgecolor",
            str,
            "#cccccc",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "framealpha",
            float,
            0.8,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("title", str, "", editor="text"),
        PropertySpec(
            "entry_scope",
            str,
            "axes",
            editor="combo",
            choices=("axes", "twin_pair"),
            getter=lambda _legend: "axes",
            setter=lambda _legend, _value: None,
        ),
        PropertySpec(
            "bbox_to_anchor",
            dict,
            {"kind": "none"},
            editor="legend_anchor",
            normalizer=normalize_legend_anchor,
        ),
        PropertySpec("mode", str, None, editor="combo", choices=(None, "expand"), allow_none=True),
        PropertySpec("alignment", str, "center", editor="combo", choices=("left", "center", "right")),
        PropertySpec("reverse", bool, False, editor="check"),
        PropertySpec("markerfirst", bool, True, editor="check"),
        PropertySpec("draggable", bool, False, editor="check"),
        PropertySpec("draggable_update", str, "loc", editor="combo", choices=("loc", "bbox")),
        PropertySpec("label_font", dict, deepcopy(_DEFAULT_FONT_SPEC), editor="font_spec", normalizer=normalize_font),
        PropertySpec("title_font", dict, deepcopy(_DEFAULT_FONT_SPEC), editor="font_spec", normalizer=normalize_font),
        PropertySpec("numpoints", int, 1, editor="spin", minimum=1),
        PropertySpec("scatterpoints", int, 1, editor="spin", minimum=1),
        PropertySpec("scatteryoffsets", tuple, (0.375, 0.5, 0.3125), editor="number_sequence", normalizer=lambda value: tuple(float(item) for item in value)),
        PropertySpec("markerscale", float, 1.0, editor="double_spin", minimum=0.0),
        PropertySpec("borderpad", float, 0.4, editor="double_spin", minimum=0.0),
        PropertySpec("labelspacing", float, 0.5, editor="double_spin", minimum=0.0),
        PropertySpec("handlelength", float, 2.0, editor="double_spin", minimum=0.0),
        PropertySpec("handleheight", float, 0.7, editor="double_spin", minimum=0.0),
        PropertySpec("handletextpad", float, 0.8, editor="double_spin", minimum=0.0),
        PropertySpec("borderaxespad", float, 0.5, editor="double_spin", minimum=0.0),
        PropertySpec("columnspacing", float, 2.0, editor="double_spin", minimum=0.0),
        PropertySpec("fancybox", bool, True, editor="check"),
        PropertySpec("shadow", bool, False, editor="check"),
        PropertySpec("frame_linewidth", float, 1.0, editor="double_spin", minimum=0.0),
        PropertySpec("frame_linestyle", dict, {"kind": "preset", "value": "-"}, editor="line_pattern", normalizer=_line_pattern),
        PropertySpec("frame_hatch", str, None, editor="text", allow_none=True, normalizer=_optional_text),
        PropertySpec("zorder", float, 5.0, editor="double_spin"),
        PropertySpec("alpha", float, None, editor="double_spin", allow_none=True, minimum=0.0, maximum=1.0, advanced=True),
        PropertySpec("label", str, "", editor="text", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    REBUILD_KEYS = frozenset(
        {
            "location", "bbox_to_anchor", "ncols", "mode", "alignment",
            "reverse", "markerfirst", "numpoints", "scatterpoints",
            "scatteryoffsets", "markerscale", "borderpad", "labelspacing",
            "handlelength", "handleheight", "handletextpad", "borderaxespad",
            "columnspacing", "fancybox", "shadow", "frameon",
        }
    )
    CAPABILITIES = frozenset({"legend", "font", "color"})

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._entry_scope = str(state.properties.get("entry_scope", "axes"))
        self._label_font_value = normalize_font(
            state.properties.get("label_font", deepcopy(_DEFAULT_FONT_SPEC))
        )
        self._title_font_value = normalize_font(
            state.properties.get("title_font", deepcopy(_DEFAULT_FONT_SPEC))
        )
        self._constructor_properties = {
            key: spec.normalize(
                deepcopy(state.properties.get(key, spec.default))
            )
            for key, spec in self.property_specs().items()
            if key in self.REBUILD_KEYS
        }
        super().__init__(state, **kwargs)

    def read_state(self, *, strict: bool = False) -> ComponentState:
        """Read state."""

        try:
            return super().read_state(strict=strict)
        except ComponentNotFoundError:
            if strict:
                raise
            return self.state

    def _hide_for_delete(self) -> ComponentChange:
        """Hide semantic state even when no concrete Legend exists yet."""

        state = self.state
        properties = dict(state.properties)
        properties["visible"] = False
        return self.apply_state(state.clone(properties=properties))

    def apply_state(self, state: ComponentState) -> ComponentChange:
        """Restore hidden legend state even before Matplotlib creates it.

        A semantic Legend component exists for every Axes, while the concrete
        Matplotlib ``Legend`` artist only exists after there are handles to
        display.  Hidden project state is therefore valid without a live
        target.  Visible state still requires an artist so callers cannot
        silently request a legend that was never created.
        """

        try:
            self.resolve_target()
        except ComponentNotFoundError:
            before = self.state
            try:
                self._validate_replacement(state)
                specs = self.property_specs()
                properties = deepcopy(state.properties)
                for key, value in state.properties.items():
                    spec = specs.get(key)
                    if spec is not None:
                        properties[key] = spec.normalize(value)
                candidate = state.clone(properties=properties)
                self._validate_candidate(candidate)
                if candidate.properties.get("visible") is not False:
                    raise ComponentValidationError(
                        "A visible legend requires a live Matplotlib Legend target."
                    )
            except Exception as exc:
                return self._rejected(None, before, str(exc))

            # The public apply_state operation owns detached state commits;
            # callers never need to reach into controller internals.
            if candidate.to_dict() == before.to_dict():
                return ComponentChange(
                    self.component_id,
                    None,
                    before,
                    self.state,
                    ChangeStatus.NOOP,
                    UpdateImpact.NONE,
                )
            self._state = candidate
            return ComponentChange(
                self.component_id,
                None,
                before,
                self.state,
                ChangeStatus.APPLIED,
                UpdateImpact.NONE,
            )

        return super().apply_state(state)

    def _read_property(self, target: Legend, spec: PropertySpec) -> Any:
        if spec.key == "entry_scope":
            return self._entry_scope
        if spec.key in self.REBUILD_KEYS and spec.key not in {
            "location", "ncols", "frameon", "alignment", "bbox_to_anchor"
        }:
            return deepcopy(self._constructor_properties[spec.key])
        if spec.key == "location":
            return deepcopy(self._constructor_properties[spec.key])
        if spec.key == "ncols":
            return int(getattr(target, "_ncols", 1))
        if spec.key == "facecolor":
            return self._frame_color(target, "facecolor")
        if spec.key == "edgecolor":
            return self._frame_color(target, "edgecolor")
        if spec.key == "framealpha":
            return target.get_frame().get_alpha()
        if spec.key == "title":
            return target.get_title().get_text()
        if spec.key == "bbox_to_anchor":
            return deepcopy(self._constructor_properties[spec.key])
        if spec.key == "alignment":
            return str(target.get_alignment())
        if spec.key in {"label_font", "title_font"}:
            text = target.get_title() if spec.key == "title_font" else (target.get_texts()[0] if target.get_texts() else None)
            if text is None:
                return deepcopy(
                    self._title_font_value
                    if spec.key == "title_font"
                    else self._label_font_value
                )
            return normalize_font({
                "family": list(text.get_fontfamily()), "size": float(text.get_fontsize()),
                "weight": text.get_fontweight(), "style": text.get_fontstyle(),
                "stretch": text.get_fontproperties().get_stretch(),
                "variant": text.get_fontproperties().get_variant(),
                "color": _read_color(text.get_color()),
            })
        frame = target.get_frame()
        if spec.key == "frame_linewidth":
            return float(frame.get_linewidth())
        if spec.key == "frame_linestyle":
            return deepcopy(self._state.properties[spec.key])
        if spec.key == "frame_hatch":
            return frame.get_hatch()
        if spec.key == "draggable":
            return target.get_draggable()
        if spec.key == "draggable_update":
            return str(self._state.properties[spec.key])
        return super()._read_property(target, spec)

    def _frame_color(self, target: Legend, key: str) -> str:
        frame = target.get_frame()
        getter = (
            frame.get_facecolor
            if key == "facecolor"
            else frame.get_edgecolor
        )
        value = _read_color(getter())
        if frame.get_alpha() is None:
            return value
        actual_rgba = mcolors.to_rgba(value)
        saved = self._state.properties.get(key)
        if saved is not None:
            try:
                saved_rgba = mcolors.to_rgba(saved)
            except (TypeError, ValueError):
                saved_rgba = None
            if (
                saved_rgba is not None
                and np.allclose(actual_rgba[:3], saved_rgba[:3])
            ):
                return _normalize_color(saved)
        return mcolors.to_hex(actual_rgba, keep_alpha=False)

    def _write_property(
        self, target: Legend, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "entry_scope":
            self._entry_scope = str(value)
            return
        if spec.key in self.REBUILD_KEYS:
            self._constructor_properties[spec.key] = deepcopy(value)
            if spec.key == "alignment":
                target.set_alignment(value)
            elif spec.key == "bbox_to_anchor":
                target.set_bbox_to_anchor(legend_anchor_value(value))
            elif spec.key == "frameon":
                target.set_frame_on(value)
            elif spec.key == "location":
                target.set_loc(legend_location_value(value))
            elif spec.key == "ncols":
                target.set_ncols(value)
            return
        if spec.key == "location":
            target.set_loc(value)
            return
        if spec.key == "ncols":
            target.set_ncols(value)
            return
        if spec.key == "facecolor":
            target.get_frame().set_facecolor(value)
            return
        if spec.key == "edgecolor":
            target.get_frame().set_edgecolor(value)
            return
        if spec.key == "framealpha":
            target.get_frame().set_alpha(value)
            return
        if spec.key == "title":
            target.set_title(value)
            return
        if spec.key in {"label_font", "title_font"}:
            if spec.key == "title_font":
                self._title_font_value = normalize_font(value)
            else:
                self._label_font_value = normalize_font(value)
            texts = [target.get_title()] if spec.key == "title_font" else target.get_texts()
            for text in texts:
                text.set_fontfamily(value["family"])
                text.set_fontsize(value["size"])
                text.set_fontweight(value["weight"])
                text.set_fontstyle(value["style"])
                text.set_fontstretch(value["stretch"])
                text.set_fontvariant(value["variant"])
                text.set_color(value["color"])
            return
        if spec.key == "draggable":
            target.set_draggable(bool(value), update=self._state.properties.get("draggable_update", "loc"))
            return
        if spec.key == "draggable_update":
            target.set_draggable(bool(self._state.properties.get("draggable", False)), update=value)
            return
        if spec.key == "frame_linewidth":
            target.get_frame().set_linewidth(value)
            return
        if spec.key == "frame_linestyle":
            apply_line_pattern(target.get_frame(), value)
            return
        if spec.key == "frame_hatch":
            target.get_frame().set_hatch(value)
            return
        super()._write_property(target, spec, value)


_IN_AXES_COMMON_PROPERTIES = (
    PropertySpec(
        "bounds",
        tuple,
        (0.6, 0.6, 0.35, 0.35),
        editor="rectangle",
        normalizer=_in_axes_rectangle,
    ),
    PropertySpec("visible", bool, True, editor="check"),
    PropertySpec("zorder", float, 5.0, editor="double_spin"),
    PropertySpec(
        "facecolor",
        str,
        "#ffffff",
        editor="color",
        normalizer=_normalize_color,
    ),
    PropertySpec("frameon", bool, True, editor="check"),
    PropertySpec(
        "edgecolor",
        str,
        "#000000",
        editor="color",
        normalizer=_normalize_color,
    ),
    PropertySpec(
        "linewidth",
        float,
        0.8,
        validator=_nonnegative,
        editor="double_spin",
    ),
)


class InAxesController(ComponentController[Any]):
    """Base Controller for a removable child Axes represented as an Element."""

    KIND = ComponentKind.IN_AXES
    DELETION_POLICY = DeletionPolicy.REMOVE
    CAPABILITIES = frozenset({"in_axes"})
    DELETE_IMPACTS = UpdateImpact.REDRAW

    @staticmethod
    def _runtime_axes(runtime: Any) -> Axes:
        axes = getattr(runtime, "axes", None)
        if not isinstance(axes, Axes):
            raise ComponentValidationError(
                "Inset runtime does not contain a child Axes."
            )
        return axes

    @staticmethod
    def _sync_indicator_visibility(runtime: Any) -> None:
        axes = InAxesController._runtime_axes(runtime)
        enabled = bool(axes.get_visible())
        rectangle = getattr(runtime, "indicator_rectangle", None)
        if rectangle is not None:
            rectangle.set_visible(
                enabled and bool(getattr(runtime, "region_visible", True))
            )
        defaults = tuple(getattr(runtime, "connector_defaults", ()))
        specs = tuple(getattr(runtime, "connector_specs", ()))
        for index, connector in enumerate(
            tuple(getattr(runtime, "connectors", ()))
        ):
            default_visible = defaults[index] if index < len(defaults) else True
            connector.set_visible(
                enabled
                and (
                    bool(specs[index].get("visible", True))
                    if index < len(specs)
                    else True
                )
                and bool(default_visible)
            )

    @staticmethod
    def _sync_indicator_positions(runtime: Any) -> None:
        axes = InAxesController._runtime_axes(runtime)
        rectangle = getattr(runtime, "indicator_rectangle", None)
        connectors = tuple(getattr(runtime, "connectors", ()))
        if rectangle is None:
            return
        x0, x1 = (float(value) for value in axes.get_xlim())
        y0, y1 = (float(value) for value in axes.get_ylim())
        rectangle.set_bounds(x0, y0, x1 - x0, y1 - y0)
        corners = ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
        for connector, corner in zip(connectors, corners):
            connector.set_positions(connector.xy1, corner)

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector.get("object_id") != state.id:
            raise ComponentValidationError(
                "Inset selector object_id must equal its component id."
            )

    def _read_property(self, runtime: Any, spec: PropertySpec) -> Any:
        axes = self._runtime_axes(runtime)
        key = spec.key
        if key == "bounds":
            return tuple(getattr(runtime.bounds_locator, "bounds"))
        if key == "visible":
            return bool(axes.get_visible())
        if key == "zorder":
            return float(axes.get_zorder())
        if key == "facecolor":
            return _read_color(axes.get_facecolor())
        if key == "frameon":
            return bool(axes.get_frame_on())
        if key == "edgecolor":
            return _read_color(axes.spines["left"].get_edgecolor())
        if key == "linewidth":
            return float(axes.spines["left"].get_linewidth())
        if key == "xlim":
            return tuple(float(value) for value in axes.get_xlim())
        if key == "ylim":
            return tuple(float(value) for value in axes.get_ylim())
        if key == "ticks_visible":
            return bool(axes.xaxis.get_visible() and axes.yaxis.get_visible())
        if key == "region_visible":
            return bool(getattr(runtime, "region_visible", True))
        if key in {"region_facecolor", "region_fill", "region_hatch", "region_zorder", "region_color", "region_linestyle", "region_linewidth", "region_alpha"}:
            rectangle = getattr(runtime, "indicator_rectangle", None)
            if rectangle is None:
                return self._state.properties[key]
            if key == "region_color":
                return _read_color(rectangle.get_edgecolor())
            if key == "region_facecolor":
                return _read_color(rectangle.get_facecolor())
            if key == "region_linestyle":
                return deepcopy(
                    getattr(
                        runtime,
                        "region_line_pattern",
                        self._state.properties[key],
                    )
                )
            if key == "region_linewidth":
                return float(rectangle.get_linewidth())
            if key == "region_alpha":
                value = rectangle.get_alpha()
                return 1.0 if value is None else float(value)
            return getattr(rectangle, f"get_{key.removeprefix('region_')}")()
        if key == "connectors":
            return deepcopy(tuple(getattr(runtime, "connector_specs", self._state.properties[key])))
        if key == "opacity":
            image = getattr(runtime, "image_artist", None)
            if image is None:
                return float(self._state.properties.get(key, 1.0))
            value = image.get_alpha()
            return 1.0 if value is None else float(value)
        if key == "fit_mode":
            return str(getattr(runtime, "fit_mode", "contain"))
        if key == "interpolation":
            image = getattr(runtime, "image_artist", None)
            if image is None:
                return str(self._state.properties.get(key, "antialiased"))
            return str(image.get_interpolation())
        image_getters = {
            "origin": "origin",
            "extent": "get_extent",
            "resample": "get_resample",
            "filternorm": "get_filternorm",
            "filterrad": "get_filterrad",
            "interpolation_stage": "get_interpolation_stage",
            "image_visible": "get_visible",
            "image_zorder": "get_zorder",
            "image_clip_on": "get_clip_on",
            "image_rasterized": "get_rasterized",
            "image_in_layout": "get_in_layout",
            "image_snap": "get_snap",
            "image_gid": "get_gid",
            "image_label": "get_label",
            "image_sketch_params": "get_sketch_params",
            "image_url": "get_url",
        }
        if key in image_getters:
            image = getattr(runtime, "image_artist", None)
            if image is None:
                return deepcopy(self._state.properties.get(key, spec.default))
            accessor = getattr(image, image_getters[key])
            result = accessor() if callable(accessor) else accessor
            if key == "extent":
                return tuple(float(item) for item in result)
            if key in {"filterrad", "image_zorder"}:
                return float(result)
            return result
        return super()._read_property(runtime, spec)

    def _write_property(
        self, runtime: Any, spec: PropertySpec, value: Any
    ) -> None:
        axes = self._runtime_axes(runtime)
        key = spec.key
        if key == "bounds":
            runtime.bounds_locator.bounds = tuple(value)
            axes.stale = True
            return
        if key == "visible":
            axes.set_visible(bool(value))
            self._sync_indicator_visibility(runtime)
            return
        if key == "zorder":
            axes.set_zorder(value)
            return
        if key == "facecolor":
            axes.set_facecolor(value)
            return
        if key == "frameon":
            axes.set_frame_on(bool(value))
            return
        if key == "edgecolor":
            for spine in axes.spines.values():
                spine.set_edgecolor(value)
            return
        if key == "linewidth":
            for spine in axes.spines.values():
                spine.set_linewidth(value)
            return
        if key == "xlim":
            axes.set_xlim(*value)
            self._sync_indicator_positions(runtime)
            return
        if key == "ylim":
            axes.set_ylim(*value)
            self._sync_indicator_positions(runtime)
            return
        if key == "ticks_visible":
            axes.xaxis.set_visible(bool(value))
            axes.yaxis.set_visible(bool(value))
            return
        if key == "region_visible":
            runtime.region_visible = bool(value)
            self._sync_indicator_visibility(runtime)
            return
        if key in {"region_facecolor", "region_fill", "region_hatch", "region_zorder", "region_color", "region_linestyle", "region_linewidth", "region_alpha"}:
            rectangle = getattr(runtime, "indicator_rectangle", None)
            if rectangle is not None:
                if key == "region_linestyle":
                    apply_line_pattern(rectangle, value)
                    runtime.region_line_pattern = deepcopy(value)
                    return
                setter_name = {
                    "region_color": "set_edgecolor",
                    "region_facecolor": "set_facecolor",
                    "region_linewidth": "set_linewidth",
                    "region_alpha": "set_alpha",
                    "region_fill": "set_fill",
                    "region_hatch": "set_hatch",
                    "region_zorder": "set_zorder",
                }[key]
                getattr(rectangle, setter_name)(value)
            return
        if key == "connectors":
            runtime.connector_specs = deepcopy(tuple(value))
            for connector, connector_spec in zip(runtime.connectors, value):
                connector.set_edgecolor(connector_spec["color"])
                pattern = connector_spec["line_pattern"]
                connector.set_linestyle(pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"]))
                connector.set_linewidth(connector_spec["linewidth"])
                connector.set_alpha(connector_spec["alpha"])
                connector.set_zorder(connector_spec["zorder"])
            self._sync_indicator_visibility(runtime)
            return
        if key == "opacity":
            image = getattr(runtime, "image_artist", None)
            if image is not None:
                image.set_alpha(value)
            return
        if key == "fit_mode":
            runtime.fit_mode = str(value)
            axes.set_aspect("equal" if value == "contain" else "auto")
            return
        if key == "interpolation":
            image = getattr(runtime, "image_artist", None)
            if image is not None:
                image.set_interpolation(value)
            return
        image_setters = {
            "origin": "origin",
            "extent": "set_extent",
            "resample": "set_resample",
            "filternorm": "set_filternorm",
            "filterrad": "set_filterrad",
            "interpolation_stage": "set_interpolation_stage",
            "image_visible": "set_visible",
            "image_zorder": "set_zorder",
            "image_clip_on": "set_clip_on",
            "image_rasterized": "set_rasterized",
            "image_in_layout": "set_in_layout",
            "image_snap": "set_snap",
            "image_gid": "set_gid",
            "image_label": "set_label",
            "image_sketch_params": "set_sketch_params",
            "image_url": "set_url",
        }
        if key in image_setters:
            image = getattr(runtime, "image_artist", None)
            if image is not None:
                if key == "image_sketch_params":
                    _set_sketch(image, value)
                    return
                name = image_setters[key]
                if name == "origin":
                    image.origin = value
                    image.stale = True
                else:
                    getattr(image, name)(value)
            return
        super()._write_property(runtime, spec, value)

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        if impacts == UpdateImpact.NONE:
            return
        runtime = target if target is not None else self.resolve_target()
        parent = getattr(runtime, "parent_axes", None)
        if self._registry is not None and isinstance(parent, Axes):
            self._registry.request_update(parent, impacts)
            return
        super()._request_updates(impacts, runtime)

    def prepare_remove(self) -> InAxesRemovalHandle:
        """Capture child-Axes and indicator containers without publishing removal."""

        return MATPLOTLIB_REMOVAL.prepare_in_axes(self.resolve_target())

    def commit_remove(self, handle: InAxesRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.commit(handle)

    def rollback_remove(self, handle: InAxesRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.rollback(handle)

    def _finalize_remove(self, handle: InAxesRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.finalize(handle)


class ZoomInAxesController(InAxesController):
    """Coordinate a live zoom inset and its parent-Axes indicator."""

    ROLES = frozenset({ComponentRole.IN_AXES_ZOOM})
    RESTORE_PHASE = RestorePhase.IN_AXES
    PROPERTY_SPECS = _IN_AXES_COMMON_PROPERTIES + (
        PropertySpec(
            "xlim",
            tuple,
            (0.0, 1.0),
            editor="position",
            normalizer=_in_axes_range,
        ),
        PropertySpec(
            "ylim",
            tuple,
            (0.0, 1.0),
            editor="position",
            normalizer=_in_axes_range,
        ),
        PropertySpec("ticks_visible", bool, True, editor="check"),
        PropertySpec("region_visible", bool, True, editor="check"),
        PropertySpec(
            "region_color",
            str,
            "#808080",
            editor="color",
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "region_linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
        ),
        PropertySpec(
            "region_linewidth",
            float,
            1.0,
            validator=_nonnegative,
            editor="double_spin",
        ),
        PropertySpec(
            "region_alpha",
            float,
            0.5,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
        ),
        PropertySpec("region_facecolor", str, "#00000000", editor="color", normalizer=_normalize_color),
        PropertySpec("region_fill", bool, False, editor="check"),
        PropertySpec("region_hatch", str, None, editor="text", allow_none=True, normalizer=_optional_text),
        PropertySpec("region_zorder", float, 4.99, editor="double_spin"),
        PropertySpec(
            "connectors",
            tuple,
            tuple(
                {
                    "visible": True,
                    "color": "#808080",
                    "line_pattern": {"kind": "preset", "value": "-"},
                    "linewidth": 1.0,
                    "alpha": 0.5,
                    "zorder": 4.99,
                }
                for _index in range(4)
            ),
            editor="connectors",
            normalizer=_connectors,
        ),
    )

    def _is_empty(self, runtime: Any, state: ComponentState) -> bool:
        del state
        return not tuple(getattr(runtime, "content_artists", ()))


class ImageInAxesController(InAxesController):
    """Coordinate one embedded raster image displayed in a child Axes."""

    ROLES = frozenset({ComponentRole.IN_AXES_IMAGE})
    RESTORE_PHASE = RestorePhase.IN_AXES
    PROPERTY_SPECS = _IN_AXES_COMMON_PROPERTIES + (
        PropertySpec(
            "opacity",
            float,
            1.0,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
        ),
        PropertySpec(
            "fit_mode",
            str,
            "contain",
            editor="combo",
            choices=("contain", "stretch"),
        ),
        PropertySpec(
            "interpolation",
            str,
            "antialiased",
            editor="combo",
            choices=(
                "none", "antialiased", "nearest", "bilinear", "bicubic",
                "spline16", "spline36", "hanning", "hamming", "hermite",
                "kaiser", "quadric", "catrom", "gaussian", "bessel",
                "mitchell", "sinc", "lanczos", "blackman",
            ),
        ),
        PropertySpec("origin", str, "upper", editor="combo", choices=("upper", "lower")),
        PropertySpec("extent", tuple, None, editor="rectangle", allow_none=True, normalizer=_optional_extent),
        PropertySpec("resample", bool, True, editor="check"),
        PropertySpec("filternorm", bool, True, editor="check", advanced=True),
        PropertySpec("filterrad", float, 4.0, editor="double_spin", minimum=0.0, advanced=True),
        PropertySpec("interpolation_stage", str, "data", editor="combo", choices=("data", "rgba"), advanced=True),
        PropertySpec("image_visible", bool, True, editor="check"),
        PropertySpec("image_zorder", float, 0.0, editor="double_spin"),
        PropertySpec("image_clip_on", bool, True, editor="check", advanced=True),
        PropertySpec("image_rasterized", bool, False, editor="check", advanced=True),
        PropertySpec("image_in_layout", bool, True, editor="check", advanced=True),
        PropertySpec("image_snap", bool, None, editor="combo", choices=(None, True, False), allow_none=True, advanced=True),
        PropertySpec("image_gid", str, None, editor="text", allow_none=True, normalizer=_optional_text, advanced=True),
        PropertySpec("image_label", str, "", editor="text", advanced=True),
        PropertySpec(
            "image_sketch_params",
            tuple,
            None,
            editor="triplet",
            allow_none=True,
            normalizer=_optional_sketch,
            advanced=True,
        ),
        PropertySpec("image_url", str, None, editor="text", allow_none=True, normalizer=_optional_text, advanced=True),
    )

    def _validate_data(self, state: ComponentState) -> None:
        _validate_in_axes_image_data(state.data)

    def _apply_data(self, runtime: Any, state: ComponentState) -> None:
        array = decode_in_axes_image(state.data)
        axes = self._runtime_axes(runtime)
        previous = getattr(runtime, "image_artist", None)
        candidate = None
        try:
            candidate = axes.imshow(
                array,
                alpha=state.properties["opacity"],
                interpolation=state.properties["interpolation"],
                origin=state.properties["origin"],
                extent=state.properties["extent"],
                resample=state.properties["resample"],
                filternorm=state.properties["filternorm"],
                filterrad=state.properties["filterrad"],
                interpolation_stage=state.properties["interpolation_stage"],
                aspect=(
                    "equal"
                    if state.properties["fit_mode"] == "contain"
                    else "auto"
                ),
                label="_nolegend_",
            )
            candidate.set_visible(state.properties["image_visible"])
            candidate.set_zorder(state.properties["image_zorder"])
            candidate.set_clip_on(state.properties["image_clip_on"])
            candidate.set_rasterized(state.properties["image_rasterized"])
            candidate.set_in_layout(state.properties["image_in_layout"])
            candidate.set_snap(state.properties["image_snap"])
            candidate.set_gid(state.properties["image_gid"])
            candidate.set_url(state.properties["image_url"])
            if previous is not None:
                previous.remove()
            runtime.image_artist = candidate
            runtime.content_artists = [candidate]
            runtime.fit_mode = state.properties["fit_mode"]
            axes.set_axis_off()
            axes.set_frame_on(state.properties["frameon"])
        except Exception:
            if candidate is not None:
                try:
                    candidate.remove()
                except Exception:
                    pass
            raise

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        del before, after
        return UpdateImpact.REDRAW


class LineController(ComponentController[Line2D]):
    """Coordinate state changes for line components."""

    KIND = ComponentKind.LINE
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    ROLES = frozenset(
        {
            ComponentRole.LINE,
            ComponentRole.FUNCTION_CURVE,
            ComponentRole.DATA_PLOT,
            ComponentRole.FIT_CURVE,
            ComponentRole.INTERPOLATION,
        }
    )
    PROPERTY_SPECS = (
        PropertySpec(
            "label",
            str,
            "",
            editor="text",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "color",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda line: _read_color(line.get_color()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor="line_pattern",
            normalizer=_line_pattern,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "linewidth",
            float,
            1.5,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "marker",
            dict,
            {"kind": "symbol", "value": "None"},
            editor="marker_spec",
            normalizer=_marker_spec,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markersize",
            float,
            6.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markerfacecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda line: _read_color(line.get_markerfacecolor()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markeredgecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda line: _read_color(line.get_markeredgecolor()),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "markeredgewidth",
            float,
            1.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec("zorder", float, 2.0, editor="double_spin"),
        PropertySpec("drawstyle", str, "default", editor="combo", choices=("default", "steps", "steps-pre", "steps-mid", "steps-post")),
        PropertySpec("fillstyle", str, "full", editor="combo", choices=("full", "left", "right", "bottom", "top", "none")),
        PropertySpec(
            "markerfacecoloralt",
            str,
            "none",
            editor="optional_color",
            normalizer=lambda value: str(value) if str(value).lower() == "none" else _normalize_color(value),
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec("markevery", dict, {"kind": "all"}, editor="markevery", normalizer=normalize_markevery),
        PropertySpec(
            "gapcolor",
            str,
            None,
            editor="optional_color",
            allow_none=True,
            normalizer=lambda value: None if value is None else _normalize_color(value),
        ),
        PropertySpec("dash_capstyle", str, "butt", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("dash_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("solid_capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round")),
        PropertySpec("solid_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel")),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = frozenset(
        {"line", "data", "label", "color", "line_style", "marker"}
    )
    DELETE_IMPACTS = (
        UpdateImpact.RELIM
        | UpdateImpact.AUTOSCALE
        | UpdateImpact.LEGEND
        | UpdateImpact.REDRAW
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        if (
            state.role
            in {
                ComponentRole.DATA_PLOT,
                ComponentRole.INTERPOLATION,
                ComponentRole.FIT_CURVE,
            }
            and "preprocess" not in state.data
        ):
            data = deepcopy(state.data)
            data["preprocess"] = DataPreprocessSpec().to_dict()
            state = state.clone(data=data)
        self._line_pattern_value = _line_pattern(
            state.properties.get("linestyle", {"kind": "preset", "value": "-"})
        )
        self._marker_spec_value = _marker_spec(
            state.properties.get("marker", {"kind": "symbol", "value": "None"})
        )
        self._markevery_spec_value = normalize_markevery(
            state.properties.get("markevery", {"kind": "all"})
        )
        super().__init__(state, **kwargs)

    def _read_property(self, target: Line2D, spec: PropertySpec) -> Any:
        if spec.key in {"linestyle", "marker", "markevery"}:
            return deepcopy(
                {
                    "linestyle": self._line_pattern_value,
                    "marker": self._marker_spec_value,
                    "markevery": self._markevery_spec_value,
                }[spec.key]
            )
        return super()._read_property(target, spec)

    def _write_property(self, target: Line2D, spec: PropertySpec, value: Any) -> None:
        if spec.key == "linestyle":
            apply_line_pattern(target, value)
            self._line_pattern_value = _line_pattern(value)
            return
        if spec.key == "marker":
            target.set_marker(marker_value(value))
            self._marker_spec_value = _marker_spec(value)
            return
        if spec.key == "markevery":
            target.set_markevery(markevery_value(value))
            self._markevery_spec_value = normalize_markevery(value)
            return
        super()._write_property(target, spec, value)

    def _validate_data(self, state: ComponentState) -> None:
        role = state.role
        if role is ComponentRole.LINE:
            _exact_data_fields(state, {"x", "y"})
            self._validate_xy_values(state.data["x"], state.data["y"])
            return
        if role is ComponentRole.FUNCTION_CURVE:
            _exact_data_fields(
                state, {"expression", "x_start", "x_stop"}
            )
            expression = state.data["expression"]
            if not isinstance(expression, str) or not expression.strip():
                raise ComponentValidationError(
                    "Function curve expression must be non-empty."
                )
            try:
                compile_math_expression(expression, {"x"})
            except ValueError as exc:
                raise ComponentValidationError(
                    f"Function curve expression is invalid: {exc}"
                ) from exc
            _finite_number(state.data["x_start"], "x_start")
            _finite_number(state.data["x_stop"], "x_stop")
            return
        if role is ComponentRole.DATA_PLOT:
            _exact_data_fields(state, {"x_ref", "y_ref", "preprocess"})
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            return
        if role is ComponentRole.INTERPOLATION:
            expected = {
                "x_ref",
                "y_ref",
                "method",
                "k",
                "samples",
                "lam",
                "lam_auto",
                "preprocess",
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            method = state.data["method"]
            if method not in interpolate_dict:
                raise ComponentValidationError(
                    f"Unknown interpolation method: {method!r}."
                )
            k = state.data["k"]
            if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 5:
                raise ComponentValidationError(
                    "Interpolation order k must be between 1 and 5."
                )
            samples = state.data["samples"]
            if (
                isinstance(samples, bool)
                or not isinstance(samples, int)
                or not MIN_INTERPOLATION_SAMPLES
                <= samples
                <= MAX_INTERPOLATION_SAMPLES
            ):
                raise ComponentValidationError(
                    "Interpolation samples are outside the supported range."
                )
            lam_auto = state.data["lam_auto"]
            if not isinstance(lam_auto, bool):
                raise ComponentValidationError(
                    "Interpolation lam_auto must be boolean."
                )
            lam = state.data["lam"]
            if lam is not None and _finite_number(lam, "lam") < 0:
                raise ComponentValidationError(
                    "Interpolation lambda cannot be negative."
                )
            if (
                method == SMOOTHING_SPLINE_METHOD
                and not lam_auto
                and lam is None
            ):
                raise ComponentValidationError(
                    "Manual smoothing spline requires lambda."
                )
            return
        if role is ComponentRole.FIT_CURVE:
            expected = {
                "x_ref",
                "y_ref",
                "engine",
                "fit_type",
                "fit_options",
                "fit_result",
                "expression",
                "x_start",
                "x_stop",
                "preprocess",
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            DataPreprocessSpec.from_dict(state.data["preprocess"])
            try:
                FitEngine(state.data["engine"])
            except ValueError as exc:
                raise ComponentValidationError(
                    "Fitting engine must be Python or Matlab."
                ) from exc
            try:
                normalized_options = normalize_fit_options_for_storage(
                    state.data["fit_options"]
                )
                normalized_result = normalize_fit_result_for_storage(
                    state.data["fit_result"]
                )
            except ValueError as exc:
                raise ComponentValidationError(str(exc)) from exc
            if normalized_options != state.data["fit_options"]:
                raise ComponentValidationError(
                    "Fit options must use null for unbounded values."
                )
            if normalized_result != state.data["fit_result"]:
                raise ComponentValidationError(
                    "Fit result must use null for undefined statistics."
                )
            if not isinstance(state.data["expression"], str):
                raise ComponentValidationError(
                    "Fit expression must be a string."
                )
            if state.data["expression"].strip():
                try:
                    compile_math_expression(
                        state.data["expression"],
                        {"x"},
                    )
                except ValueError as exc:
                    raise ComponentValidationError(
                        f"Fit expression is invalid: {exc}"
                    ) from exc
            _finite_number(state.data["x_start"], "x_start")
            _finite_number(state.data["x_stop"], "x_stop")
            return
        raise ComponentValidationError(
            f"Unsupported line role: {role.value!r}."
        )

    @staticmethod
    def _validate_xy_values(
        x: Any,
        y: Any,
        *,
        allow_gaps: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        x_values = np.asarray(x)
        y_values = np.asarray(y)
        if x_values.ndim != 1 or y_values.ndim != 1:
            raise ComponentValidationError(
                "Line data must be one-dimensional."
            )
        if len(x_values) != len(y_values):
            raise ComponentValidationError(
                "Line X and Y data must have the same length."
            )
        try:
            numeric_y = y_values.astype(float)
            if np.issubdtype(x_values.dtype, np.datetime64):
                invalid_x = np.zeros(len(x_values), dtype=bool)
                missing_x = np.isnat(x_values.astype("datetime64[ns]"))
            else:
                numeric_x = x_values.astype(float)
                invalid_x = np.isinf(numeric_x)
                missing_x = np.isnan(numeric_x)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                "Line data must contain numeric or datetime X values "
                "and numeric Y values."
            ) from exc
        if allow_gaps:
            if invalid_x.any() or np.isinf(numeric_y).any():
                raise ComponentValidationError(
                    "Line data must not contain infinity."
                )
            # A masked row may be represented by NaN/NaT in either axis.
            # Matplotlib uses these values to create intentional line gaps.
            del missing_x
        elif (
            invalid_x.any()
            or missing_x.any()
            or not np.isfinite(numeric_y).all()
        ):
            raise ComponentValidationError(
                "Line data must not contain NaN, NaT, or infinity."
            )
        return x_values, y_values

    def _validate_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target
        if not isinstance(runtime_data, XYData):
            raise ComponentValidationError(
                "Line runtime data must be XYData."
            )
        self._validate_xy_values(
            runtime_data.x,
            runtime_data.y,
            allow_gaps=state.role is ComponentRole.DATA_PLOT,
        )

    def _capture_runtime_data(self, target: Line2D) -> XYData:
        return XYData(
            np.asarray(target.get_xdata()).copy(),
            np.asarray(target.get_ydata()).copy(),
        )

    def _apply_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)
        target.set_data(
            np.asarray(runtime_data.x),
            np.asarray(runtime_data.y),
        )

    def _restore_runtime_data(
        self,
        target: Line2D,
        runtime_data: Any,
    ) -> None:
        if isinstance(runtime_data, XYData):
            target.set_data(runtime_data.x, runtime_data.y)

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.REDRAW
        )

    def _runtime_data_is_empty(
        self,
        target: Line2D,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del target, state
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        if not len(x_values):
            return True
        if np.issubdtype(x_values.dtype, np.datetime64):
            x_valid = ~np.isnat(x_values.astype("datetime64[ns]"))
        else:
            try:
                x_valid = np.isfinite(x_values.astype(float))
            except (TypeError, ValueError):
                return False
        try:
            y_valid = np.isfinite(y_values.astype(float))
        except (TypeError, ValueError):
            return False
        return not bool((x_valid & y_valid).any())

    def apply_role_data(
        self,
        data: dict[str, Any],
        *,
        drawable: XYData | ScatterData,
    ) -> ComponentChange:
        """Apply role data."""

        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                data=data,
                runtime_data=drawable,
            )
        )

    def set_xy_data(
        self,
        x: Any,
        y: Any,
        *,
        persist: bool = False,
    ) -> ComponentChange:
        """Set xy data."""

        x_values = np.asarray(x)
        y_values = np.asarray(y)
        data = deepcopy(self._state.data)
        if persist or self._state.role is ComponentRole.LINE:
            data.update(
                x=x_values.tolist(),
                y=y_values.tolist(),
            )
        return self.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )

    def _apply_data(self, target: Line2D, state: ComponentState) -> None:
        if "x" in state.data or "y" in state.data:
            if "x" not in state.data or "y" not in state.data:
                raise ComponentValidationError(
                    "Persisted line data requires both x and y."
                )
            x_values = np.asarray(state.data["x"])
            y_values = np.asarray(state.data["y"])
            if x_values.ndim != 1 or y_values.ndim != 1 or len(x_values) != len(y_values):
                raise ComponentValidationError("Persisted line data is invalid.")
            target.set_data(x_values, y_values)

    def _is_empty(self, target: Line2D, state: ComponentState) -> bool:
        return len(target.get_xdata()) == 0

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        if "x" in after.data or "y" in after.data:
            return (
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            )
        return UpdateImpact.NONE


class FunctionCurveController(LineController):
    """Coordinate state changes for function curve components."""

    ROLES = frozenset({ComponentRole.FUNCTION_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"function_curve"}
    )


class DataPlotController(LineController):
    """Coordinate state changes for data plot components."""

    ROLES = frozenset({ComponentRole.DATA_PLOT})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh"}
    )


class FitCurveController(LineController):
    """Coordinate state changes for fit curve components."""

    ROLES = frozenset({ComponentRole.FIT_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "manual_refresh", "fit"}
    )


class InterpolationController(LineController):
    """Coordinate state changes for interpolation components."""

    ROLES = frozenset({ComponentRole.INTERPOLATION})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh", "interpolation"}
    )


class CollectionController(ComponentController[Any]):
    """Coordinate state changes for collection components."""

    CAPABILITIES = frozenset({"collection"})


class ScatterController(CollectionController):
    """Coordinate state changes for scatter components."""

    KIND = ComponentKind.SCATTER
    RESTORE_PHASE = RestorePhase.DYNAMIC
    ROLES = frozenset({ComponentRole.SCATTER})
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec(
            "label",
            str,
            "",
            editor="text",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "color",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "edgecolor",
            str,
            "#1f77b4",
            editor="color",
            normalizer=_normalize_color,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "size",
            float,
            36.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "marker",
            dict,
            {"kind": "symbol", "value": "o"},
            editor="marker_spec",
            normalizer=_marker_spec,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "linewidth",
            float,
            1.0,
            validator=_nonnegative,
            editor="double_spin",
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec("zorder", float, 1.0, editor="double_spin"),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "None"},
            editor="line_pattern",
            normalizer=_line_pattern,
        ),
        PropertySpec("hatch", str, None, editor="text", allow_none=True, normalizer=_optional_text),
        PropertySpec(
            "capstyle", str, None, editor="combo", allow_none=True,
            choices=(None, "butt", "projecting", "round"),
        ),
        PropertySpec(
            "joinstyle", str, None, editor="combo", allow_none=True,
            choices=(None, "miter", "round", "bevel"),
        ),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
        PropertySpec(
            "urls",
            tuple,
            (),
            editor="string_list",
            getter="get_urls",
            setter="set_urls",
            normalizer=_url_sequence,
            advanced=True,
        ),
        PropertySpec(
            "color_mapping",
            dict,
            {
                "enabled": False,
                "cmap": "viridis",
                "norm": deepcopy(DEFAULT_NORM),
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
            editor="scatter_color_map",
            normalizer=normalize_scatter_color_map,
        ),
        PropertySpec(
            "size_mapping",
            dict,
            {"enabled": False, "input": None, "output": [12.0, 120.0], "clamp": True},
            editor="scatter_size_map",
            normalizer=normalize_scatter_size_map,
        ),
    ) + _ARTIST_EXPORT_PROPERTIES
    CAPABILITIES = CollectionController.CAPABILITIES | frozenset(
        {
            "scatter",
            "data",
            "label",
            "color",
            "marker",
            "data_reference",
            "auto_refresh",
        }
    )
    DELETE_IMPACTS = LineController.DELETE_IMPACTS

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        if state.data and "preprocess" not in state.data:
            data = deepcopy(state.data)
            data["preprocess"] = DataPreprocessSpec().to_dict()
            state = state.clone(data=data)
        if state.data:
            data = deepcopy(state.data)
            data.setdefault("color_ref", None)
            data.setdefault("size_ref", None)
            state = state.clone(data=data)
        self._marker_value = deepcopy(state.properties.get("marker", {"kind": "symbol", "value": "o"}))
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        # A free-standing Matplotlib collection can be registered without
        # a table source. Project-managed scatter components always retain
        # their two stable column references.
        if not state.data:
            return
        _exact_data_fields(
            state,
            {"x_ref", "y_ref", "color_ref", "size_ref", "preprocess"},
        )
        _column_reference(state.data["x_ref"], "x_ref")
        _column_reference(state.data["y_ref"], "y_ref")
        for key in ("color_ref", "size_ref"):
            if state.data[key] is not None:
                _column_reference(state.data[key], key)
        DataPreprocessSpec.from_dict(state.data["preprocess"])
        if state.properties["color_mapping"]["enabled"] and state.data["color_ref"] is None:
            raise ComponentValidationError("Scatter color mapping requires color_ref.")
        if state.properties["size_mapping"]["enabled"] and state.data["size_ref"] is None:
            raise ComponentValidationError("Scatter size mapping requires size_ref.")

    def _first_color(
        self, values: np.ndarray, fallback: str
    ) -> str:
        return _read_color(values[0]) if len(values) else fallback

    def _read_property(
        self, target: PathCollection, spec: PropertySpec
    ) -> Any:
        if spec.key == "color":
            value = self._first_color(
                target.get_facecolors(),
                self._state.properties.get("color", "#1f77b4"),
            )
            return self._color_without_collection_alpha(
                target,
                value,
                self._state.properties.get("color"),
            )
        if spec.key == "edgecolor":
            value = self._first_color(
                target.get_edgecolors(),
                self._state.properties.get("edgecolor", "#1f77b4"),
            )
            return self._color_without_collection_alpha(
                target,
                value,
                self._state.properties.get("edgecolor"),
            )
        if spec.key == "size":
            sizes = target.get_sizes()
            return float(sizes[0]) if len(sizes) else 36.0
        if spec.key == "marker":
            return deepcopy(self._marker_value)
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
        if spec.key == "linestyle":
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        if spec.key in {"color_mapping", "size_mapping"}:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        return super()._read_property(target, spec)

    @staticmethod
    def _color_without_collection_alpha(
        target: PathCollection,
        value: str,
        saved: Any,
    ) -> str:
        """Keep collection color and global alpha as independent properties."""

        if target.get_alpha() is None:
            return value
        actual_rgba = mcolors.to_rgba(value)
        if saved is not None:
            try:
                saved_rgba = mcolors.to_rgba(saved)
            except (TypeError, ValueError):
                saved_rgba = None
            if (
                saved_rgba is not None
                and np.allclose(actual_rgba[:3], saved_rgba[:3])
            ):
                return _normalize_color(saved)
        return mcolors.to_hex(actual_rgba, keep_alpha=False)

    def _write_property(
        self, target: PathCollection, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "color":
            target.set_facecolor(value)
            return
        if spec.key == "edgecolor":
            target.set_edgecolor(value)
            return
        if spec.key == "size":
            target.set_sizes([value])
            return
        if spec.key == "marker":
            marker = MarkerStyle(marker_value(value))
            path = marker.get_path().transformed(marker.get_transform())
            target.set_paths([path])
            self._marker_value = deepcopy(value)
            return
        if spec.key == "linewidth":
            target.set_linewidths([value])
            return
        if spec.key == "linestyle":
            pattern = normalize_line_pattern(value)
            linestyle = pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"])
            target.set_linestyle(linestyle)
            return
        if spec.key == "capstyle" and value is None:
            target._capstyle = None
            return
        if spec.key == "joinstyle" and value is None:
            target._joinstyle = None
            return
        if spec.key in {"color_mapping", "size_mapping"}:
            return
        super()._write_property(target, spec, value)

    @staticmethod
    def _validate_xy_values(
        x: Any,
        y: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        x_values = np.asarray(x)
        y_values = np.asarray(y)
        if x_values.ndim != 1 or y_values.ndim != 1:
            raise ComponentValidationError(
                "Scatter data must be one-dimensional."
            )
        if len(x_values) != len(y_values):
            raise ComponentValidationError(
                "Scatter X and Y data must have the same length."
            )
        try:
            numeric_x = x_values.astype(float)
            numeric_y = y_values.astype(float)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                "Scatter data must contain only numbers."
            ) from exc
        if (
            not np.isfinite(numeric_x).all()
            or not np.isfinite(numeric_y).all()
        ):
            raise ComponentValidationError(
                "Scatter data must not contain NaN or infinity."
            )
        return x_values, y_values

    def _validate_runtime_data(
        self,
        target: PathCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target, state
        if not isinstance(runtime_data, (XYData, ScatterData)):
            raise ComponentValidationError(
                "Scatter runtime data must be XYData."
            )
        self._validate_xy_values(runtime_data.x, runtime_data.y)
        length = len(np.asarray(runtime_data.x))
        if isinstance(runtime_data, ScatterData):
            for name, values in (("colors", runtime_data.colors), ("sizes", runtime_data.sizes)):
                if values is not None and len(np.asarray(values)) != length:
                    raise ComponentValidationError(
                        f"Scatter {name} must match X/Y length."
                    )

    def _capture_runtime_data(
        self,
        target: PathCollection,
    ) -> dict[str, Any]:
        offsets = np.asarray(target.get_offsets()).copy()
        return {
            "offsets": offsets,
            "array": (
                None
                if target.get_array() is None
                else np.ma.asarray(target.get_array()).copy()
            ),
            "sizes": np.asarray(target.get_sizes()).copy(),
            "facecolors": np.asarray(target.get_facecolors()).copy(),
            "edgecolors": np.asarray(target.get_edgecolors()).copy(),
            "cmap": target.get_cmap(),
            "norm": target.norm,
        }

    def _apply_runtime_data(
        self,
        target: PathCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        target.set_offsets(
            np.column_stack((x_values, y_values))
            if len(x_values)
            else np.empty((0, 2))
        )
        if isinstance(runtime_data, ScatterData):
            color_spec = state.properties["color_mapping"]
            if color_spec["enabled"] and runtime_data.colors is not None:
                cmap = __import__("matplotlib").colormaps[color_spec["cmap"]].copy()
                cmap.set_bad(color_spec["bad"])
                if color_spec["under"] is not None:
                    cmap.set_under(color_spec["under"])
                if color_spec["over"] is not None:
                    cmap.set_over(color_spec["over"])
                target.set_cmap(cmap)
                target.set_norm(build_norm(color_spec["norm"]))
                target.set_array(np.asarray(runtime_data.colors, dtype=float))
            else:
                target.set_array(None)
                target.set_facecolor(state.properties["color"])
            if state.properties["size_mapping"]["enabled"] and runtime_data.sizes is not None:
                target.set_sizes(map_scatter_sizes(runtime_data.sizes, state.properties["size_mapping"]))
            else:
                target.set_sizes([state.properties["size"]])

    def _restore_runtime_data(
        self,
        target: PathCollection,
        runtime_data: Any,
    ) -> None:
        if isinstance(runtime_data, dict):
            target.set_offsets(runtime_data["offsets"])
            target.set_cmap(runtime_data["cmap"])
            target.set_norm(runtime_data["norm"])
            target.set_array(runtime_data["array"])
            target.set_sizes(runtime_data["sizes"])
            target.set_facecolors(runtime_data["facecolors"])
            target.set_edgecolors(runtime_data["edgecolors"])
            return
        if not isinstance(runtime_data, (XYData, ScatterData)):
            return
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        target.set_offsets(
            np.column_stack((x_values, y_values))
            if len(x_values)
            else np.empty((0, 2))
        )
        if isinstance(runtime_data, ScatterData):
            target.set_array(None if runtime_data.colors is None else np.asarray(runtime_data.colors))
            target.set_sizes(np.asarray(runtime_data.sizes) if runtime_data.sizes is not None else [])

    def _restore_transaction_snapshot(self, snapshot) -> None:
        super()._restore_transaction_snapshot(snapshot)
        self._restore_runtime_data(self.resolve_target(), snapshot[1])

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.REDRAW
        )

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        collection = target if target is not None else self.resolve_target()
        axes = getattr(collection, "axes", None)
        if UpdateImpact.RELIM in impacts and isinstance(axes, Axes):
            axes.relim()
            if len(collection.get_offsets()):
                axes.update_datalim(collection.get_datalim(axes.transData))
            impacts &= ~UpdateImpact.RELIM
        super()._request_updates(impacts, collection)

    def _runtime_data_is_empty(
        self,
        target: PathCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del target, state
        return len(np.asarray(runtime_data.x)) == 0

    def apply_role_data(
        self,
        data: dict[str, Any],
        *,
        drawable: XYData | ScatterData,
    ) -> ComponentChange:
        """Apply role data."""

        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                data=data,
                runtime_data=drawable,
            )
        )

    def set_xy_data(
        self,
        x: Any,
        y: Any,
        *,
        persist: bool = False,
    ) -> ComponentChange:
        """Set xy data."""

        x_values = np.asarray(x)
        y_values = np.asarray(y)
        data = deepcopy(self._state.data)
        if persist:
            data.update(
                x=x_values.tolist(),
                y=y_values.tolist(),
            )
        return self.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )

    def _apply_data(
        self, target: PathCollection, state: ComponentState
    ) -> None:
        if "x" in state.data or "y" in state.data:
            if "x" not in state.data or "y" not in state.data:
                raise ComponentValidationError(
                    "Persisted scatter data requires both x and y."
                )
            x_values = np.asarray(state.data["x"])
            y_values = np.asarray(state.data["y"])
            if x_values.ndim != 1 or y_values.ndim != 1 or len(x_values) != len(y_values):
                raise ComponentValidationError("Persisted scatter data is invalid.")
            target.set_offsets(
                np.column_stack((x_values, y_values))
                if len(x_values)
                else np.empty((0, 2))
            )

    def _is_empty(
        self, target: PathCollection, state: ComponentState
    ) -> bool:
        return len(target.get_offsets()) == 0

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        if "x" in after.data or "y" in after.data:
            return (
                UpdateImpact.RELIM
                | UpdateImpact.AUTOSCALE
                | UpdateImpact.REDRAW
            )
        return UpdateImpact.NONE


CONTROLLER_TYPES: dict[
    tuple[ComponentKind, ComponentRole],
    type[ComponentController[Any]],
] = {
    (ComponentKind.FIGURE, ComponentRole.FIGURE): FigureController,
    (ComponentKind.AXES, ComponentRole.AXES): AxesController,
    (ComponentKind.AXIS, ComponentRole.X_AXIS): XAxisController,
    (ComponentKind.AXIS, ComponentRole.Y_AXIS): YAxisController,
    (ComponentKind.SPINE, ComponentRole.SPINE): SpineController,
    (ComponentKind.TICK_GROUP, ComponentRole.MAJOR_TICK): TickGroupController,
    (ComponentKind.TICK_GROUP, ComponentRole.MINOR_TICK): TickGroupController,
    (
        ComponentKind.TICK_LABEL_GROUP,
        ComponentRole.MAJOR_TICK_LABEL,
    ): TickLabelGroupController,
    (
        ComponentKind.TICK_LABEL_GROUP,
        ComponentRole.MINOR_TICK_LABEL,
    ): TickLabelGroupController,
    (ComponentKind.GRID, ComponentRole.GRID): GridController,
    (ComponentKind.TEXT, ComponentRole.TITLE): TitleController,
    (ComponentKind.TEXT, ComponentRole.X_LABEL): AxisLabelController,
    (ComponentKind.TEXT, ComponentRole.Y_LABEL): AxisLabelController,
    (ComponentKind.TEXT, ComponentRole.TEXT): TextController,
    (ComponentKind.LEGEND, ComponentRole.LEGEND): LegendController,
    (ComponentKind.LINE, ComponentRole.LINE): LineController,
    (
        ComponentKind.LINE,
        ComponentRole.FUNCTION_CURVE,
    ): FunctionCurveController,
    (ComponentKind.LINE, ComponentRole.DATA_PLOT): DataPlotController,
    (ComponentKind.LINE, ComponentRole.FIT_CURVE): FitCurveController,
    (
        ComponentKind.LINE,
        ComponentRole.INTERPOLATION,
    ): InterpolationController,
    (ComponentKind.SCATTER, ComponentRole.SCATTER): ScatterController,
    (
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_ZOOM,
    ): ZoomInAxesController,
    (
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_IMAGE,
    ): ImageInAxesController,
}


def validate_controller_contracts() -> dict[
    tuple[ComponentKind, ComponentRole], RestorePhase
]:
    """Validate first-party Controller declarations and return materializers.

    The returned mapping is derived only from the Controller contracts, so it
    is an independent completeness source for the Canvas materializer registry.
    """

    materializers: dict[
        tuple[ComponentKind, ComponentRole], RestorePhase
    ] = {}
    for key, controller_type in CONTROLLER_TYPES.items():
        kind, role = key
        if controller_type.KIND is not kind or role not in controller_type.ROLES:
            raise ComponentValidationError(
                "Controller contract does not match registry key "
                f"{kind.value}/{role.value}."
            )
        specs = controller_type.PROPERTY_SPECS
        spec_keys = [spec.key for spec in specs]
        if len(spec_keys) != len(set(spec_keys)):
            raise ComponentValidationError(
                f"Controller {controller_type.__name__} declares duplicate "
                "PropertySpec keys."
            )
        for spec in specs:
            if not isinstance(spec.editor, EditorKind):
                raise ComponentValidationError(
                    f"Property {controller_type.__name__}.{spec.key} does not "
                    "declare a valid EditorKind."
                )
            if spec.editor is EditorKind.ENUM and not spec.choices:
                raise ComponentValidationError(
                    f"Property {controller_type.__name__}.{spec.key} declares "
                    "an enum editor without choices."
                )
        phase = controller_type.RESTORE_PHASE
        if phase is not None:
            if not isinstance(phase, RestorePhase):
                raise ComponentValidationError(
                    f"Controller {controller_type.__name__} declares an invalid "
                    "restore phase."
                )
            materializers[key] = phase
    return materializers


def controller_type_for(
    state: ComponentState,
) -> type[ComponentController[Any]]:
    """Return the Controller class registered for the component state."""

    try:
        return CONTROLLER_TYPES[(state.kind, state.role)]
    except KeyError as exc:
        raise ComponentValidationError(
            f"No controller is registered for "
            f"{state.kind.value}/{state.role.value}."
        ) from exc


def create_controller(
    state: ComponentState,
    *,
    target: Any | None = None,
    locator: Any | None = None,
    registry: Any | None = None,
) -> ComponentController[Any]:
    """Create controller."""

    return controller_type_for(state)(
        state,
        target=target,
        locator=locator,
        registry=registry,
    )
