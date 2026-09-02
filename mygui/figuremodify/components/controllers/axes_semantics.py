"""Fixed Axes semantic-child Controllers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.axis import Axis
from matplotlib.lines import Line2D
from matplotlib.spines import Spine
from matplotlib.text import Text


from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    PropertySpec,
)
from ..property_values import (
    DEFAULT_FORMATTER,
    DEFAULT_MAJOR_LOCATOR,
    DEFAULT_MINOR_FORMATTER,
    DEFAULT_MINOR_LOCATOR,
    DEFAULT_SCALE,
    apply_line_pattern,
    apply_scale,
    build_formatter,
    build_locator,
    default_scale_for_name,
    formatter_from_axis,
    locator_from_axis,
    normalize_font,
    normalize_formatter,
    normalize_line_pattern,
    normalize_locator,
    normalize_scale,
    normalize_text_box,
    scale_from_axis,
    text_box_kwargs,
    validate_fixed_ticker_pair,
)
from ._helpers import (
    _positive,
    _nonnegative,
    _primary_font_family,
    _line_pattern,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    _optional_pair,
    _spine_position,
    _set_spine_bounds,
    _axis_name,
    _level,
    apply_font_spec,
)

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
            advanced=True,
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
            advanced=True,
        ),
        PropertySpec("offset_visible", bool, True, editor="check", advanced=True),
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
                scale=self._state.properties.get("scale") if minor else None,
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
            apply_font_spec([target.get_offset_text()], value)
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
            advanced=True,
        ),
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
            advanced=True,
        ),
        PropertySpec("capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round"), advanced=True),
        PropertySpec("joinstyle", str, "miter", editor="combo", choices=("miter", "round", "bevel"), advanced=True),
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
        PropertySpec("zorder", float, 2.01, editor="double_spin", advanced=True),
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

    def _safe_snapshot(self) -> ComponentState:
        """Keep incidental Tick recreation from replacing business state."""

        return self._state.clone()

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Submit one edit through the full-style mutation transaction."""

        return self.apply_mutation(
            ComponentMutation(self.component_id, properties={key: value})
        )

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            if _level(self._state) == "minor":
                pending = getattr(target, "_minor_tick_kw", {})
                if spec.key == "primary_visible":
                    return bool(pending.get("tick1On", spec.default))
                if spec.key == "secondary_visible":
                    return bool(pending.get("tick2On", spec.default))
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

    def _properties_require_data_apply(
        self, property_patch: dict[str, Any]
    ) -> bool:
        """Replay the complete style after a batch may recreate Tick objects."""

        return bool(property_patch)

    def _apply_data(self, target: Axis, state: ComponentState) -> None:
        """Apply authoritative line style to every currently active Tick."""

        specs = self.property_specs()
        for key, value in state.properties.items():
            self._write_property(target, specs[key], deepcopy(value))

    def reapply_runtime_style(self) -> None:
        """Replay authoritative style after Matplotlib recreates Tick objects."""

        self._apply_data(self.resolve_target(), self._state)

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
            str,
            "sans-serif",
            editor="font",
            normalizer=_primary_font_family,
        ),
        PropertySpec(
            "pad",
            float,
            3.5,
            validator=_nonnegative,
            editor="double_spin",
            advanced=True,
        ),
        PropertySpec(
            "fontweight",
            (str, int, float),
            "normal",
            editor="named_number",
            advanced=True,
        ),
        PropertySpec("fontstyle", str, "normal", editor="combo", choices=("normal", "italic", "oblique"), advanced=True),
        PropertySpec("fontstretch", (str, int, float), "normal", editor="named_number", getter=lambda text: text.get_fontproperties().get_stretch(), advanced=True),
        PropertySpec("fontvariant", str, "normal", editor="combo", choices=("normal", "small-caps"), advanced=True),
        PropertySpec("alpha", float, None, editor="double_spin", allow_none=True, minimum=0.0, maximum=1.0, advanced=True),
        PropertySpec("rotation_mode", str, "default", editor="combo", choices=("default", "anchor", "xtick", "ytick"), advanced=True),
        PropertySpec("horizontalalignment", str, "center", editor="combo", choices=("left", "center", "right"), advanced=True),
        PropertySpec("verticalalignment", str, "baseline", editor="combo", choices=("top", "center", "bottom", "baseline", "center_baseline"), advanced=True),
        PropertySpec("multialignment", str, None, editor="combo", choices=(None, "left", "center", "right"), allow_none=True, getter=lambda text: getattr(text, "_multialignment", None), advanced=True),
        PropertySpec("wrap", bool, False, editor="check", advanced=True),
        PropertySpec("linespacing", float, 1.2, editor="double_spin", minimum=0.0, getter=lambda text: float(getattr(text, "_linespacing", 1.2)), advanced=True),
        PropertySpec("math_fontfamily", str, "dejavusans", editor="text", advanced=True),
        PropertySpec("parse_math", bool, True, editor="check", advanced=True),
        PropertySpec("usetex", bool, False, editor="check", advanced=True),
        PropertySpec("bbox", dict, {"enabled": False}, editor="text_box", normalizer=normalize_text_box, advanced=True),
        PropertySpec("zorder", float, 3.0, editor="double_spin", advanced=True),
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

    def _safe_snapshot(self) -> ComponentState:
        """Keep incidental Tick recreation from replacing business state."""

        return self._state.clone()

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Submit one edit through the full-style mutation transaction."""

        return self.apply_mutation(
            ComponentMutation(self.component_id, properties={key: value})
        )

    def _label(self, tick: Any) -> Text:
        return tick.label1

    def _read_property(self, target: Axis, spec: PropertySpec) -> Any:
        ticks = self._ticks(target)
        if not ticks:
            if _level(self._state) == "minor":
                pending = getattr(target, "_minor_tick_kw", {})
                if spec.key == "primary_visible":
                    return bool(pending.get("label1On", spec.default))
                if spec.key == "secondary_visible":
                    return bool(pending.get("label2On", spec.default))
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
            return _primary_font_family(label.get_fontfamily())
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

    def _properties_require_data_apply(
        self, property_patch: dict[str, Any]
    ) -> bool:
        """Replay the complete style after a batch may recreate Tick objects."""

        return bool(property_patch)

    def _apply_data(self, target: Axis, state: ComponentState) -> None:
        """Apply authoritative text style to every currently active Tick."""

        specs = self.property_specs()
        for key, value in state.properties.items():
            self._write_property(target, specs[key], deepcopy(value))

    def reapply_runtime_style(self) -> None:
        """Replay authoritative style after Matplotlib recreates Tick objects."""

        self._apply_data(self.resolve_target(), self._state)

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
            advanced=True,
        ),
        PropertySpec(
            "gapcolor",
            str,
            None,
            editor="optional_color",
            allow_none=True,
            normalizer=lambda value: None if value is None else _normalize_color(value),
            advanced=True,
        ),
        PropertySpec("dash_capstyle", str, "butt", editor="combo", choices=("butt", "projecting", "round"), advanced=True),
        PropertySpec("dash_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel"), advanced=True),
        PropertySpec("solid_capstyle", str, "projecting", editor="combo", choices=("butt", "projecting", "round"), advanced=True),
        PropertySpec("solid_joinstyle", str, "round", editor="combo", choices=("miter", "round", "bevel"), advanced=True),
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
            if _level(self._state) == "minor" and spec.key == "visible":
                pending = getattr(target, "_minor_tick_kw", {})
                return bool(pending.get("gridOn", spec.default))
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
