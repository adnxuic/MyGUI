"""Concrete controllers for the first-party Matplotlib component set."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any, ClassVar

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

from code.database.interpolate_func import (
    B_SPLINE_METHOD,
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    SMOOTHING_SPLINE_METHOD,
    interpolate_dict,
)
from code.database.safe_expression import compile_math_expression

from .base import ComponentController
from .errors import ComponentNotFoundError, ComponentValidationError
from .models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    PropertySpec,
    UpdateImpact,
    XYData,
)


def _positive(value: float) -> bool:
    return value > 0


def _nonnegative(value: float) -> bool:
    return value >= 0


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
    if value is None:
        if state.role in {
            ComponentRole.X_AXIS,
            ComponentRole.X_LABEL,
        }:
            value = "x"
        elif state.role in {
            ComponentRole.Y_AXIS,
            ComponentRole.Y_LABEL,
        }:
            value = "y"
    if value not in {"x", "y"}:
        raise ComponentValidationError(
            "Axis component selector requires axis='x' or axis='y'."
        )
    return value


def _level(state: ComponentState) -> str:
    value = state.selector.get("level")
    if value is None:
        value = (
            "minor"
            if state.role
            in {
                ComponentRole.MINOR_TICK,
                ComponentRole.MINOR_TICK_LABEL,
            }
            else "major"
        )
    if value not in {"major", "minor"}:
        raise ComponentValidationError(
            "Tick/grid selector requires level='major' or level='minor'."
        )
    return value


class ContainerController(ComponentController[Any]):
    CAPABILITIES = frozenset({"container"})


class FigureController(ContainerController):
    KIND = ComponentKind.FIGURE
    ROLES = frozenset({ComponentRole.FIGURE})
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
            "constrained_layout",
            bool,
            False,
            editor="check",
            getter="get_constrained_layout",
            setter=lambda figure, value: figure.set_layout_engine(
                "constrained" if value else "none"
            ),
        ),
    )
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

    def set_property_callback(self, callback) -> None:
        """Attach an optional host synchronizer without introducing Qt."""

        self._property_callback = callback

    def _read_property(self, target: Figure, spec: PropertySpec) -> Any:
        if spec.key in self._metadata:
            return self._metadata[spec.key]
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

    def _delete_target(self, target: Figure) -> None:
        target.clear()


class AxesController(ContainerController):
    KIND = ComponentKind.AXES
    ROLES = frozenset({ComponentRole.AXES})
    PROPERTY_SPECS = (
        PropertySpec(
            "position",
            tuple,
            (0.125, 0.11, 0.775, 0.77),
            editor="rectangle",
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
            "xscale",
            str,
            "linear",
            editor="combo",
            choices=("linear", "log", "symlog", "logit"),
        ),
        PropertySpec(
            "yscale",
            str,
            "linear",
            editor="combo",
            choices=("linear", "log", "symlog", "logit"),
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
        PropertySpec("autoscale_on", bool, True, editor="check"),
        PropertySpec(
            "color_cycle",
            dict,
            None,
            editor="auto",
            allow_none=True,
            getter=lambda _axes: None,
            setter=lambda _axes, _value: None,
        ),
    )
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
        expected = {"layout_group", "nrows", "ncols", "slot"}
        if set(subplot) != expected:
            raise ComponentValidationError(
                "Axes subplot fields must be "
                f"{sorted(expected)!r}."
            )
        for key in ("layout_group", "nrows", "ncols", "slot"):
            value = subplot[key]
            minimum = 0 if key == "layout_group" else 1
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
            ):
                raise ComponentValidationError(
                    f"Axes subplot {key} is invalid."
                )
        if subplot["slot"] > subplot["nrows"] * subplot["ncols"]:
            raise ComponentValidationError(
                "Axes subplot slot exceeds the layout size."
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


class AxisComponentController(ComponentController[Any]):
    CAPABILITIES = frozenset({"axis_component"})

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)

    def delete(self) -> ComponentChange:
        """Fixed axis semantics remain in the tree and delete means hide."""

        return self.set_property("visible", False)


class AxisController(AxisComponentController):
    KIND = ComponentKind.AXIS
    ROLES = frozenset({ComponentRole.X_AXIS, ComponentRole.Y_AXIS})
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "scale",
            str,
            "linear",
            editor="combo",
            choices=("linear", "log", "symlog", "logit"),
        ),
        PropertySpec(
            "ticks_position",
            str,
            "default",
            editor="combo",
        ),
        PropertySpec(
            "label_position",
            str,
            "bottom",
            editor="combo",
        ),
        PropertySpec("inverted", bool, False, editor="check"),
    )
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"axis_scale"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        super()._validate_candidate(state)
        axis_name = _axis_name(state)
        tick_positions = (
            {"top", "bottom", "both", "default", "none"}
            if axis_name == "x"
            else {"left", "right", "both", "default", "none"}
        )
        label_positions = (
            {"top", "bottom"}
            if axis_name == "x"
            else {"left", "right"}
        )
        if state.properties.get("ticks_position") not in tick_positions:
            raise ComponentValidationError(
                f"Invalid {axis_name}-axis tick position."
            )
        if state.properties.get("label_position") not in label_positions:
            raise ComponentValidationError(
                f"Invalid {axis_name}-axis label position."
            )

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        axes = target.axes
        axis_name = _axis_name(self._state)
        if spec.key == "scale":
            return target.get_scale()
        if spec.key == "ticks_position":
            return target.get_ticks_position()
        if spec.key == "label_position":
            return target.get_label_position()
        if spec.key == "inverted":
            return (
                axes.xaxis_inverted()
                if axis_name == "x"
                else axes.yaxis_inverted()
            )
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        axes = target.axes
        axis_name = _axis_name(self._state)
        if spec.key == "scale":
            (
                axes.set_xscale(value)
                if axis_name == "x"
                else axes.set_yscale(value)
            )
            return
        if spec.key == "ticks_position":
            valid = (
                {"top", "bottom", "both", "default", "none"}
                if axis_name == "x"
                else {"left", "right", "both", "default", "none"}
            )
            if value not in valid:
                raise ComponentValidationError(
                    f"Invalid {axis_name}-axis tick position {value!r}."
                )
            target.set_ticks_position(value)
            return
        if spec.key == "label_position":
            valid = {"top", "bottom"} if axis_name == "x" else {"left", "right"}
            if value not in valid:
                raise ComponentValidationError(
                    f"Invalid {axis_name}-axis label position {value!r}."
                )
            target.set_label_position(value)
            return
        if spec.key == "inverted":
            current = (
                axes.xaxis_inverted()
                if axis_name == "x"
                else axes.yaxis_inverted()
            )
            if bool(value) != bool(current):
                axes.invert_xaxis() if axis_name == "x" else axes.invert_yaxis()
            return
        super()._write_property(target, spec, value)


class XAxisController(AxisController):
    ROLES = frozenset({ComponentRole.X_AXIS})


class YAxisController(AxisController):
    ROLES = frozenset({ComponentRole.Y_AXIS})

    @classmethod
    def default_properties(cls) -> dict[str, Any]:
        properties = super().default_properties()
        properties["label_position"] = "left"
        return properties


class SpineController(AxisComponentController):
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
            str,
            "-",
            editor="line_style",
            normalizer=normalize_linestyle,
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
    )
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"color", "line_style"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        name = state.selector.get("name", state.selector.get("side"))
        if name not in {"left", "right", "top", "bottom"}:
            raise ComponentValidationError(
                "Spine selector requires a standard spine name."
            )

    def _read_property(self, target: Spine, spec: PropertySpec) -> Any:
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


class TickGroupController(AxisComponentController):
    KIND = ComponentKind.TICK_GROUP
    ROLES = frozenset(
        {ComponentRole.MAJOR_TICK, ComponentRole.MINOR_TICK}
    )
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
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
        PropertySpec(
            "pad",
            float,
            3.5,
            validator=_nonnegative,
            editor="double_spin",
        ),
    )
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

    def _selected_sides(self) -> tuple[str, ...]:
        axis_name = _axis_name(self._state)
        default = ("bottom",) if axis_name == "x" else ("left",)
        sides = self._state.selector.get("sides", default)
        if isinstance(sides, str):
            sides = (sides,)
        valid = {"bottom", "top"} if axis_name == "x" else {"left", "right"}
        if not sides or not set(sides).issubset(valid):
            raise ComponentValidationError("Invalid tick side selector.")
        return tuple(sides)

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        tick = ticks[0]
        sides = self._selected_sides()
        primary = (
            "bottom" in sides or "left" in sides
        )
        line = tick.tick1line if primary else tick.tick2line
        if spec.key == "visible":
            return any(
                (
                    tick.tick1line.get_visible()
                    if side in {"bottom", "left"}
                    else tick.tick2line.get_visible()
                )
                for side in sides
            )
        if spec.key == "direction":
            return getattr(tick, "_tickdir", "out")
        if spec.key == "length":
            return float(line.get_markersize())
        if spec.key == "width":
            return float(line.get_markeredgewidth())
        if spec.key == "color":
            return _read_color(line.get_color())
        if spec.key == "pad":
            return float(tick.get_pad())
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key == "visible":
            axis_name = _axis_name(self._state)
            sides = self._selected_sides()
            valid = ("bottom", "top") if axis_name == "x" else ("left", "right")
            kwargs = {side: bool(value) if side in sides else False for side in valid}
            target.set_tick_params(which=level, **kwargs)
            return
        target.set_tick_params(which=level, **{spec.key: value})

    def _delete_target(self, target: Axis) -> None:
        self._write_property(
            target, self.property_specs()["visible"], False
        )


class TickLabelGroupController(AxisComponentController):
    KIND = ComponentKind.TICK_LABEL_GROUP
    ROLES = frozenset(
        {
            ComponentRole.MAJOR_TICK_LABEL,
            ComponentRole.MINOR_TICK_LABEL,
        }
    )
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
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
    )
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

    def _selected_sides(self) -> tuple[str, ...]:
        axis_name = _axis_name(self._state)
        default = ("bottom",) if axis_name == "x" else ("left",)
        sides = self._state.selector.get("sides", default)
        if isinstance(sides, str):
            sides = (sides,)
        valid = {"bottom", "top"} if axis_name == "x" else {"left", "right"}
        if not sides or not set(sides).issubset(valid):
            raise ComponentValidationError("Invalid tick-label side selector.")
        return tuple(sides)

    def _label(self, tick: Any) -> Text:
        sides = self._selected_sides()
        return (
            tick.label1
            if "bottom" in sides or "left" in sides
            else tick.label2
        )

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        if spec.key == "visible":
            sides = self._selected_sides()
            return any(
                (
                    tick.label1.get_visible()
                    if side in {"bottom", "left"}
                    else tick.label2.get_visible()
                )
                for tick in ticks
                for side in sides
            )
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
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key == "visible":
            axis_name = _axis_name(self._state)
            sides = self._selected_sides()
            names = (
                ("bottom", "labelbottom"),
                ("top", "labeltop"),
            ) if axis_name == "x" else (
                ("left", "labelleft"),
                ("right", "labelright"),
            )
            kwargs = {
                option: bool(value) if side in sides else False
                for side, option in names
            }
            target.set_tick_params(which=level, **kwargs)
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
        self._write_property(
            target, self.property_specs()["visible"], False
        )


class GridController(AxisComponentController):
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
            str,
            "-",
            editor="line_style",
            normalizer=normalize_linestyle,
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
    )
    CAPABILITIES = AxisComponentController.CAPABILITIES | frozenset(
        {"grid_style", "color", "line_style"}
    )

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
        return getattr(line, f"get_{spec.key}")()

    def _write_property(
        self, target: Axis, spec: PropertySpec, value: Any
    ) -> None:
        level = _level(self._state)
        if spec.key == "visible":
            target.grid(bool(value), which=level)
            return
        visible = bool(
            self._read_property(target, self.property_specs()["visible"])
        )
        target.grid(True, which=level, **{spec.key: value})
        target.grid(visible, which=level)

    def _delete_target(self, target: Axis) -> None:
        target.grid(False, which=_level(self._state))


class TextController(ComponentController[Text]):
    KIND = ComponentKind.TEXT
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
            editor="font_weight",
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
    )
    CAPABILITIES = frozenset({"text", "font", "color", "position"})


class TitleController(TextController):
    ROLES = frozenset({ComponentRole.TITLE})

    def delete(self) -> ComponentChange:
        return self.set_property("visible", False)

    def _write_property(
        self, target: Text, spec: PropertySpec, value: Any
    ) -> None:
        if spec.key == "position" and isinstance(target.axes, Axes):
            target.axes._autotitlepos = False
        super()._write_property(target, spec, value)


class AxisLabelController(TextController):
    ROLES = frozenset({ComponentRole.X_LABEL, ComponentRole.Y_LABEL})

    def _validate_candidate(self, state: ComponentState) -> None:
        _axis_name(state)

    def delete(self) -> ComponentChange:
        return self.set_property("visible", False)


class LegendController(ComponentController[Legend]):
    KIND = ComponentKind.LEGEND
    ROLES = frozenset({ComponentRole.LEGEND})
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec(
            "location",
            (str, int, tuple),
            "best",
            editor="legend_position",
            normalizer=_legend_location,
        ),
        PropertySpec(
            "ncols",
            int,
            1,
            validator=lambda value: value >= 1,
            editor="spin",
        ),
        PropertySpec(
            "fontsize",
            float,
            10.0,
            validator=_positive,
            editor="double_spin",
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
    )
    CAPABILITIES = frozenset({"legend", "font", "color"})

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._fontsize_value = float(
            state.properties.get("fontsize", 10.0)
        )
        super().__init__(state, **kwargs)

    def read_state(self, *, strict: bool = False) -> ComponentState:
        try:
            return super().read_state(strict=strict)
        except ComponentNotFoundError:
            if strict:
                raise
            return self.state

    def delete(self) -> ComponentChange:
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
        if spec.key == "location":
            location = getattr(target, "_loc", "best")
            if isinstance(location, int):
                return next(
                    (
                        name
                        for name, code in Legend.codes.items()
                        if code == location and name != "right"
                    ),
                    "best",
                )
            return location
        if spec.key == "ncols":
            return int(getattr(target, "_ncols", 1))
        if spec.key == "fontsize":
            texts = target.get_texts()
            return (
                float(texts[0].get_fontsize())
                if texts
                else float(
                    getattr(
                        target,
                        "_mygui_fontsize",
                        self._fontsize_value,
                    )
                )
            )
        if spec.key == "facecolor":
            return self._frame_color(target, "facecolor")
        if spec.key == "edgecolor":
            return self._frame_color(target, "edgecolor")
        if spec.key == "framealpha":
            return target.get_frame().get_alpha()
        if spec.key == "title":
            return target.get_title().get_text()
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
        if spec.key == "location":
            target.set_loc(value)
            return
        if spec.key == "ncols":
            target.set_ncols(value)
            return
        if spec.key == "fontsize":
            self._fontsize_value = float(value)
            target._mygui_fontsize = float(value)
            for text in target.get_texts():
                text.set_fontsize(value)
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
        super()._write_property(target, spec, value)


class LineController(ComponentController[Line2D]):
    KIND = ComponentKind.LINE
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
            str,
            "-",
            editor="line_style",
            normalizer=normalize_linestyle,
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
            str,
            "None",
            editor="marker",
            normalizer=_marker,
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
    )
    CAPABILITIES = frozenset(
        {"line", "data", "label", "color", "line_style", "marker"}
    )
    DELETE_IMPACTS = (
        UpdateImpact.RELIM
        | UpdateImpact.AUTOSCALE
        | UpdateImpact.LEGEND
        | UpdateImpact.REDRAW
    )

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
            _exact_data_fields(state, {"x_ref", "y_ref"})
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
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
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
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
            }
            _exact_data_fields(state, expected)
            _column_reference(state.data["x_ref"], "x_ref")
            _column_reference(state.data["y_ref"], "y_ref")
            if state.data["engine"] not in {"Python", "Matlab"}:
                raise ComponentValidationError(
                    "Fitting engine must be Python or Matlab."
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
        drawable: XYData,
    ) -> ComponentChange:
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
    ROLES = frozenset({ComponentRole.FUNCTION_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"function_curve"}
    )


class DataPlotController(LineController):
    ROLES = frozenset({ComponentRole.DATA_PLOT})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh"}
    )


class FitCurveController(LineController):
    ROLES = frozenset({ComponentRole.FIT_CURVE})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "manual_refresh", "fit"}
    )


class InterpolationController(LineController):
    ROLES = frozenset({ComponentRole.INTERPOLATION})
    CAPABILITIES = LineController.CAPABILITIES | frozenset(
        {"data_reference", "auto_refresh", "interpolation"}
    )


class CollectionController(ComponentController[Any]):
    CAPABILITIES = frozenset({"collection"})


class ScatterController(CollectionController):
    KIND = ComponentKind.SCATTER
    ROLES = frozenset({ComponentRole.SCATTER})
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
            str,
            "o",
            editor="marker",
            normalizer=_marker,
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
    )
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
        self._marker_value = str(state.properties.get("marker", "o"))
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        # A free-standing Matplotlib collection can be registered without
        # a table source. Project-managed scatter components always retain
        # their two stable column references.
        if not state.data:
            return
        _exact_data_fields(state, {"x_ref", "y_ref"})
        _column_reference(state.data["x_ref"], "x_ref")
        _column_reference(state.data["y_ref"], "y_ref")

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
            return self._marker_value
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
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
            marker = MarkerStyle(value)
            path = marker.get_path().transformed(marker.get_transform())
            target.set_paths([path])
            self._marker_value = value
            return
        if spec.key == "linewidth":
            target.set_linewidths([value])
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
        if not isinstance(runtime_data, XYData):
            raise ComponentValidationError(
                "Scatter runtime data must be XYData."
            )
        self._validate_xy_values(runtime_data.x, runtime_data.y)

    def _capture_runtime_data(
        self,
        target: PathCollection,
    ) -> XYData:
        offsets = np.asarray(target.get_offsets()).copy()
        if offsets.size:
            return XYData(offsets[:, 0], offsets[:, 1])
        return XYData(np.asarray([]), np.asarray([]))

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

    def _restore_runtime_data(
        self,
        target: PathCollection,
        runtime_data: Any,
    ) -> None:
        if not isinstance(runtime_data, XYData):
            return
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        target.set_offsets(
            np.column_stack((x_values, y_values))
            if len(x_values)
            else np.empty((0, 2))
        )

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
        drawable: XYData,
    ) -> ComponentChange:
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
}


def controller_type_for(
    state: ComponentState,
) -> type[ComponentController[Any]]:
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
    return controller_type_for(state)(
        state,
        target=target,
        locator=locator,
        registry=registry,
    )
