"""Controller and runtime target for parent-bound Secondary Axes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.text import Text

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    ChildAxesRemovalHandle,
)
from ..models import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    EditorKind,
    PropertySpec,
    RestorePhase,
    UpdateImpact,
)
from ..property_values import (
    DEFAULT_FORMATTER,
    DEFAULT_MAJOR_LOCATOR,
    DEFAULT_MINOR_FORMATTER,
    DEFAULT_MINOR_LOCATOR,
    build_formatter,
    build_locator,
    normalize_font,
    normalize_formatter,
    normalize_locator,
    validate_fixed_ticker_pair,
)
from ..secondary_axis_values import (
    DEFAULT_SECONDARY_X_PLACEMENT,
    DEFAULT_UNIT_TRANSFORM,
    build_unit_transform_functions,
    normalize_secondary_axis_placement,
    normalize_unit_transform,
    parent_scale_domain_samples,
    validate_unit_transform_domain,
)
from ._helpers import (
    _DEFAULT_FONT_SPEC,
    _normalize_color,
    _read_color,
    _set_spine_bounds,
)


LOGGER = logging.getLogger(__name__)
_STRUCTURAL_KEYS = frozenset({"unit_transform", "placement"})
_TICKER_KEYS = frozenset(
    {
        "ticker_mode",
        "major_locator",
        "major_formatter",
        "minor_locator",
        "minor_formatter",
    }
)


def _optional_bounds(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ComponentValidationError("Spine bounds require two numbers or null.")
    lower, upper = float(value[0]), float(value[1])
    if not np.isfinite([lower, upper]).all():
        raise ComponentValidationError("Spine bounds must be finite.")
    return (lower, upper)


def _apply_font(texts: list[Text], value: dict[str, Any]) -> None:
    for text in texts:
        text.set_fontfamily(value["family"])
        text.set_fontsize(value["size"])
        text.set_fontweight(value["weight"])
        text.set_fontstyle(value["style"])
        text.set_fontstretch(value["stretch"])
        text.set_fontvariant(value["variant"])
        text.set_color(value["color"])


def _font_from_text(text: Text, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        return normalize_font(
            {
                "family": list(text.get_fontfamily()),
                "size": float(text.get_fontsize()),
                "weight": text.get_fontweight(),
                "style": text.get_fontstyle(),
                "stretch": text.get_fontproperties().get_stretch(),
                "variant": text.get_fontproperties().get_variant(),
                "color": _read_color(text.get_color()),
            }
        )
    except Exception:
        return deepcopy(fallback)


@dataclass(slots=True)
class SecondaryAxisRemovalHandle:
    runtime: "SecondaryAxisRuntime"
    matplotlib_handle: ChildAxesRemovalHandle

    @property
    def target(self) -> Axes:
        return self.matplotlib_handle.target

    @property
    def detached(self) -> bool:
        return self.matplotlib_handle.detached

    @property
    def subject(self) -> Axes:
        return self.runtime.parent_axes


class SecondaryAxisRuntime:
    """Stable Controller target wrapping a replaceable Matplotlib child Axes."""

    def __init__(
        self,
        parent_axes: Axes,
        orientation: str,
        unit_transform: dict[str, Any],
        placement: dict[str, Any],
        *,
        requested_visible: bool = True,
        warning_callback: Callable[[str], Any] | None = None,
    ) -> None:
        if orientation not in {"x", "y"}:
            raise ComponentValidationError("Secondary Axis orientation must be x or y.")
        self.parent_axes = parent_axes
        self.orientation = orientation
        self.unit_transform = normalize_unit_transform(unit_transform)
        self.placement = normalize_secondary_axis_placement(placement, orientation=orientation)
        self.requested_visible = bool(requested_visible)
        self._warning_callback = warning_callback
        self.domain_valid = True
        self._disposed = False
        self._reapply: Callable[[], None] | None = None
        self._callback_id = parent_axes.callbacks.connect(
            f"{orientation}lim_changed", self._parent_domain_changed
        )
        self.axis = self._create_axis()
        self.refresh_health()

    def set_reapply(self, callback: Callable[[], None]) -> None:
        self._reapply = callback

    def _limits(self) -> tuple[float, float]:
        return (
            self.parent_axes.get_xlim() if self.orientation == "x" else self.parent_axes.get_ylim()
        )

    def _guarded_functions(self):
        forward, inverse = build_unit_transform_functions(self.unit_transform)

        def guarded(function):
            def invoke(values):
                scalar = np.isscalar(values)
                if not self.domain_valid:
                    return float(values) if scalar else np.asarray(values, dtype=float)
                try:
                    output = function(values)
                    if not np.all(np.isfinite(np.asarray(output, dtype=float))):
                        raise ValueError("non-finite unit-transform output")
                    return output
                except (ArithmeticError, TypeError, ValueError):
                    # Matplotlib may probe function scales with sentinel
                    # infinities that are outside the visible parent domain.
                    # Health is owned by ``refresh_health`` over the actual
                    # limits, so probes must not permanently hide the axis.
                    return float(values) if scalar else np.asarray(values, dtype=float)

            return invoke

        return guarded(forward), guarded(inverse)

    def _create_axis(self):
        placement = self.placement
        transform = None
        if placement["kind"] == "edge":
            location: str | float = placement["side"]
        else:
            location = placement["value"]
            if placement["coordinate_system"] == "data":
                transform = self.parent_axes.transData
        functions = self._guarded_functions()
        create = (
            self.parent_axes.secondary_xaxis
            if self.orientation == "x"
            else self.parent_axes.secondary_yaxis
        )
        return create(location, functions=functions, transform=transform)

    def _set_health(self, valid: bool) -> None:
        changed = self.domain_valid != bool(valid)
        self.domain_valid = bool(valid)
        self.axis.set_visible(self.requested_visible and self.domain_valid)
        if changed and not valid:
            message = (
                f"Secondary {self.orientation.upper()} Axis hidden because its unit "
                "transform is invalid on the current parent domain."
            )
            LOGGER.warning(message)
            if self._warning_callback is not None:
                self._warning_callback(message)

    def refresh_health(self) -> bool:
        try:
            validate_unit_transform_domain(
                self.unit_transform,
                *self._limits(),
                source_values=parent_scale_domain_samples(self.parent_axes, self.orientation),
            )
        except ComponentValidationError:
            self._set_health(False)
        else:
            self._set_health(True)
        return self.domain_valid

    def _parent_domain_changed(self, _axes: Axes) -> None:
        self.refresh_health()

    def rebuild(
        self,
        *,
        unit_transform: dict[str, Any] | None = None,
        placement: dict[str, Any] | None = None,
        reapply: Callable[[], None] | None = None,
    ) -> None:
        new_transform = normalize_unit_transform(
            unit_transform if unit_transform is not None else self.unit_transform
        )
        new_placement = normalize_secondary_axis_placement(
            placement if placement is not None else self.placement,
            orientation=self.orientation,
        )
        validate_unit_transform_domain(
            new_transform,
            *self._limits(),
            source_values=parent_scale_domain_samples(self.parent_axes, self.orientation),
        )
        old_axis = self.axis
        old_transform = self.unit_transform
        old_placement = self.placement
        self.unit_transform = new_transform
        self.placement = new_placement
        replacement = None
        try:
            self.domain_valid = True
            self.axis = self._create_axis()
            replacement = self.axis
            self.axis.set_visible(self.requested_visible)
            callback = self._reapply if reapply is None else reapply
            if callback is not None:
                callback()
        except Exception:
            if replacement is not None:
                try:
                    replacement.remove()
                except Exception:
                    pass
            self.axis = old_axis
            self.unit_transform = old_transform
            self.placement = old_placement
            self.refresh_health()
            raise
        old_axis.remove()

    def prepare_remove(self) -> SecondaryAxisRemovalHandle:
        return SecondaryAxisRemovalHandle(
            self,
            MATPLOTLIB_REMOVAL.prepare_child_axes(
                self.axis,
                self.parent_axes,
            ),
        )

    def commit_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.commit(handle.matplotlib_handle)

    def rollback_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.rollback(handle.matplotlib_handle)

    def finalize_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        try:
            MATPLOTLIB_REMOVAL.finalize(handle.matplotlib_handle)
        finally:
            self.dispose()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        try:
            self.parent_axes.callbacks.disconnect(self._callback_id)
        except Exception:
            pass


class SecondaryAxisController(ComponentController[SecondaryAxisRuntime]):
    """Control one reversible, parent-bound Matplotlib Secondary Axis."""

    KIND = ComponentKind.SECONDARY_AXIS
    ROLES = frozenset({ComponentRole.SECONDARY_X_AXIS, ComponentRole.SECONDARY_Y_AXIS})
    DELETION_POLICY = DeletionPolicy.REMOVE
    RESTORE_PHASE = RestorePhase.SECONDARY_AXIS
    CAPABILITIES = frozenset({"secondary_axis", "unit_transform", "font", "color"})
    DELETE_IMPACTS = UpdateImpact.REDRAW
    REBUILD_KEYS = _STRUCTURAL_KEYS
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "unit_transform",
            dict,
            deepcopy(DEFAULT_UNIT_TRANSFORM),
            editor=EditorKind.UNIT_TRANSFORM_SPEC,
            normalizer=normalize_unit_transform,
        ),
        PropertySpec(
            "placement",
            dict,
            deepcopy(DEFAULT_SECONDARY_X_PLACEMENT),
            editor=EditorKind.SECONDARY_AXIS_PLACEMENT,
            normalizer=normalize_secondary_axis_placement,
        ),
        PropertySpec("label", str, "", editor=EditorKind.TEXT),
        PropertySpec("label_pad", float, 4.0, editor=EditorKind.NUMBER),
        PropertySpec("label_rotation", float, 0.0, editor=EditorKind.ROTATION),
        PropertySpec(
            "label_font",
            dict,
            deepcopy(_DEFAULT_FONT_SPEC),
            editor=EditorKind.FONT_SPEC,
            normalizer=normalize_font,
        ),
        PropertySpec(
            "ticker_mode",
            str,
            "automatic",
            editor=EditorKind.ENUM,
            choices=("automatic", "custom"),
        ),
        PropertySpec(
            "major_locator",
            dict,
            deepcopy(DEFAULT_MAJOR_LOCATOR),
            editor=EditorKind.LOCATOR_SPEC,
            normalizer=normalize_locator,
        ),
        PropertySpec(
            "major_formatter",
            dict,
            deepcopy(DEFAULT_FORMATTER),
            editor=EditorKind.FORMATTER_SPEC,
            normalizer=normalize_formatter,
        ),
        PropertySpec(
            "minor_locator",
            dict,
            deepcopy(DEFAULT_MINOR_LOCATOR),
            editor=EditorKind.LOCATOR_SPEC,
            normalizer=normalize_locator,
        ),
        PropertySpec(
            "minor_formatter",
            dict,
            deepcopy(DEFAULT_MINOR_FORMATTER),
            editor=EditorKind.FORMATTER_SPEC,
            normalizer=normalize_formatter,
        ),
        PropertySpec("major_ticks_visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec("major_labels_visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec("minor_ticks_visible", bool, False, editor=EditorKind.BOOL),
        PropertySpec("minor_labels_visible", bool, False, editor=EditorKind.BOOL),
        PropertySpec(
            "tick_direction", str, "out", editor=EditorKind.ENUM, choices=("in", "out", "inout")
        ),
        PropertySpec("tick_length", float, 3.5, editor=EditorKind.NUMBER, minimum=0.0),
        PropertySpec("tick_width", float, 0.8, editor=EditorKind.NUMBER, minimum=0.0),
        PropertySpec(
            "tick_color", str, "#000000", editor=EditorKind.COLOR, normalizer=_normalize_color
        ),
        PropertySpec("tick_pad", float, 3.5, editor=EditorKind.NUMBER),
        PropertySpec("tick_rotation", float, 0.0, editor=EditorKind.ROTATION),
        PropertySpec(
            "tick_font",
            dict,
            deepcopy(_DEFAULT_FONT_SPEC),
            editor=EditorKind.FONT_SPEC,
            normalizer=normalize_font,
        ),
        PropertySpec("offset_visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "offset_font",
            dict,
            deepcopy(_DEFAULT_FONT_SPEC),
            editor=EditorKind.FONT_SPEC,
            normalizer=normalize_font,
        ),
        PropertySpec("remove_overlapping_locs", bool, True, editor=EditorKind.BOOL),
        PropertySpec("spine_visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "spine_color", str, "#000000", editor=EditorKind.COLOR, normalizer=_normalize_color
        ),
        PropertySpec("spine_linewidth", float, 0.8, editor=EditorKind.NUMBER, minimum=0.0),
        PropertySpec("spine_linestyle", str, "solid", editor=EditorKind.LINE_STYLE),
        PropertySpec(
            "spine_bounds",
            (tuple, list),
            None,
            editor=EditorKind.RANGE,
            allow_none=True,
            normalizer=_optional_bounds,
        ),
        PropertySpec(
            "spine_alpha",
            float,
            None,
            editor=EditorKind.NUMBER,
            allow_none=True,
            minimum=0.0,
            maximum=1.0,
        ),
        PropertySpec("zorder", float, 0.0, editor=EditorKind.NUMBER, advanced=True),
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        super().__init__(state, **kwargs)
        target = kwargs.get("target")
        if isinstance(target, SecondaryAxisRuntime):
            target.set_reapply(self._apply_all)
            self._apply_all()

    @property
    def orientation(self) -> str:
        return "x" if self._state.role is ComponentRole.SECONDARY_X_AXIS else "y"

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector != {"object_id": state.id}:
            raise ComponentValidationError(
                "Secondary Axis selector requires only object_id equal to its component id."
            )
        if state.data:
            raise ComponentValidationError("Secondary Axis data must be empty.")
        orientation = "x" if state.role is ComponentRole.SECONDARY_X_AXIS else "y"
        normalize_secondary_axis_placement(state.properties["placement"], orientation=orientation)
        for level in ("major", "minor"):
            validate_fixed_ticker_pair(
                state.properties[f"{level}_locator"],
                state.properties[f"{level}_formatter"],
            )

    def _axis_object(self, runtime: SecondaryAxisRuntime):
        return runtime.axis.xaxis if self.orientation == "x" else runtime.axis.yaxis

    def _spine(self, runtime: SecondaryAxisRuntime):
        placement = runtime.placement
        if placement["kind"] == "edge":
            name = placement["side"]
        else:
            name = "top" if self.orientation == "x" else "right"
        return runtime.axis.spines[name]

    def _apply_all(self) -> None:
        self._apply_non_ticker_properties()
        runtime = self.resolve_target()
        if self._state.properties.get("ticker_mode") == "custom":
            self._apply_custom_tickers(self._axis_object(runtime))

    def _apply_non_ticker_properties(self) -> None:
        """Reapply appearance while retaining a fresh Axis' automatic tickers."""

        runtime = self.resolve_target()
        for spec in self.PROPERTY_SPECS:
            if spec.key not in _STRUCTURAL_KEYS | _TICKER_KEYS:
                self._write_property(runtime, spec, self._state.properties[spec.key])

    def _read_property(self, runtime: SecondaryAxisRuntime, spec: PropertySpec) -> Any:
        key = spec.key
        axis = self._axis_object(runtime)
        secondary = runtime.axis
        if key == "unit_transform":
            return deepcopy(runtime.unit_transform)
        if key == "placement":
            return deepcopy(runtime.placement)
        if key == "visible":
            return bool(runtime.requested_visible)
        if key == "label":
            return str(axis.label.get_text())
        if key == "label_pad":
            return float(axis.labelpad)
        if key == "label_rotation":
            return float(axis.label.get_rotation())
        if key == "label_font":
            return _font_from_text(axis.label, self._state.properties[key])
        if key == "tick_font":
            labels = [*axis.get_ticklabels(minor=False), *axis.get_ticklabels(minor=True)]
            return (
                _font_from_text(labels[0], self._state.properties[key])
                if labels
                else deepcopy(self._state.properties[key])
            )
        if key == "offset_visible":
            return bool(axis.get_offset_text().get_visible())
        if key == "offset_font":
            return _font_from_text(axis.get_offset_text(), self._state.properties[key])
        if key == "remove_overlapping_locs":
            return bool(axis.remove_overlapping_locs)
        if key == "spine_visible":
            return bool(self._spine(runtime).get_visible())
        if key == "spine_color":
            return _read_color(self._spine(runtime).get_edgecolor())
        if key == "spine_linewidth":
            return float(self._spine(runtime).get_linewidth())
        if key == "spine_linestyle":
            return str(self._state.properties[key])
        if key == "spine_bounds":
            bounds = self._spine(runtime).get_bounds()
            return None if bounds is None or None in bounds else bounds
        if key == "spine_alpha":
            return self._spine(runtime).get_alpha()
        if key == "zorder":
            return float(secondary.get_zorder())
        return deepcopy(self._state.properties[key])

    def _write_property(
        self, runtime: SecondaryAxisRuntime, spec: PropertySpec, value: Any
    ) -> None:
        key = spec.key
        if key == "unit_transform":
            runtime.rebuild(unit_transform=value)
            return
        if key == "placement":
            runtime.rebuild(
                placement=normalize_secondary_axis_placement(value, orientation=self.orientation)
            )
            return
        secondary = runtime.axis
        axis = self._axis_object(runtime)
        if key == "visible":
            runtime.requested_visible = bool(value)
            secondary.set_visible(runtime.requested_visible and runtime.domain_valid)
        elif key == "label":
            (secondary.set_xlabel if self.orientation == "x" else secondary.set_ylabel)(str(value))
        elif key == "label_pad":
            axis.labelpad = float(value)
        elif key == "label_rotation":
            axis.label.set_rotation(float(value))
        elif key == "label_font":
            _apply_font([axis.label], value)
        elif key == "ticker_mode":
            if value == "custom":
                self._apply_custom_tickers(axis)
            elif self._state.properties.get("ticker_mode") == "custom":
                runtime.rebuild(reapply=self._apply_non_ticker_properties)
        elif key in {"major_locator", "major_formatter", "minor_locator", "minor_formatter"}:
            if self._state.properties.get("ticker_mode") == "custom":
                self._apply_custom_tickers(axis, override=(key, value))
        elif key in {
            "major_ticks_visible",
            "major_labels_visible",
            "minor_ticks_visible",
            "minor_labels_visible",
            "tick_direction",
            "tick_length",
            "tick_width",
            "tick_color",
            "tick_pad",
            "tick_rotation",
        }:
            self._apply_tick_params(runtime, key, value)
        elif key == "tick_font":
            _apply_font([*axis.get_ticklabels(False), *axis.get_ticklabels(True)], value)
        elif key == "offset_visible":
            axis.get_offset_text().set_visible(bool(value))
        elif key == "offset_font":
            _apply_font([axis.get_offset_text()], value)
        elif key == "remove_overlapping_locs":
            axis.remove_overlapping_locs = bool(value)
        elif key == "spine_visible":
            self._spine(runtime).set_visible(bool(value))
        elif key == "spine_color":
            self._spine(runtime).set_edgecolor(value)
        elif key == "spine_linewidth":
            self._spine(runtime).set_linewidth(float(value))
        elif key == "spine_linestyle":
            self._spine(runtime).set_linestyle(value)
        elif key == "spine_bounds":
            _set_spine_bounds(self._spine(runtime), value)
        elif key == "spine_alpha":
            self._spine(runtime).set_alpha(value)
        elif key == "zorder":
            secondary.set_zorder(float(value))

    def _apply_custom_tickers(self, axis, override: tuple[str, Any] | None = None) -> None:
        values = deepcopy(self._state.properties)
        if override is not None:
            values[override[0]] = override[1]
        axis.set_major_locator(build_locator(values["major_locator"]))
        axis.set_major_formatter(build_formatter(values["major_formatter"]))
        axis.set_minor_locator(build_locator(values["minor_locator"]))
        axis.set_minor_formatter(build_formatter(values["minor_formatter"]))

    def reapply_runtime_style(self) -> None:
        """Refresh domain health and dynamic ticker Artists before a draw."""

        runtime = self.resolve_target()
        runtime.refresh_health()
        if self._state.properties["ticker_mode"] == "custom":
            self._apply_custom_tickers(self._axis_object(runtime))

    def _apply_tick_params(self, runtime: SecondaryAxisRuntime, key: str, value: Any) -> None:
        secondary = runtime.axis
        placement = runtime.placement
        first_side = placement["kind"] == "edge" and placement["side"] in {"bottom", "left"}
        if key.startswith("major_"):
            prefix = "" if key == "major_ticks_visible" else "label"
            first, second = (
                ("bottom", "top")
                if self.orientation == "x"
                else ("left", "right")
            )
            secondary.tick_params(
                axis=self.orientation,
                which="major",
                **{
                    f"{prefix}{first}": bool(value) if first_side else False,
                    f"{prefix}{second}": False if first_side else bool(value),
                },
            )
            return
        if key.startswith("minor_"):
            prefix = "" if key == "minor_ticks_visible" else "label"
            first, second = (
                ("bottom", "top")
                if self.orientation == "x"
                else ("left", "right")
            )
            secondary.tick_params(
                axis=self.orientation,
                which="minor",
                **{
                    f"{prefix}{first}": bool(value) if first_side else False,
                    f"{prefix}{second}": False if first_side else bool(value),
                },
            )
            return
        param = {
            "tick_direction": "direction",
            "tick_length": "length",
            "tick_width": "width",
            "tick_color": "color",
            "tick_pad": "pad",
            "tick_rotation": "labelrotation",
        }[key]
        secondary.tick_params(axis=self.orientation, which="both", **{param: value})

    def _request_updates(self, impacts: UpdateImpact, target: Any | None = None) -> None:
        if impacts == UpdateImpact.NONE:
            return
        runtime = target if isinstance(target, SecondaryAxisRuntime) else self.resolve_target()
        if self._registry is not None:
            self._registry.request_update(runtime.parent_axes, impacts)
        elif runtime.parent_axes.figure.canvas is not None:
            runtime.parent_axes.figure.canvas.draw_idle()

    def prepare_remove(self) -> SecondaryAxisRemovalHandle:
        return self.resolve_target().prepare_remove()

    def commit_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        handle.runtime.commit_remove(handle)

    def rollback_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        handle.runtime.rollback_remove(handle)

    def _finalize_remove(self, handle: SecondaryAxisRemovalHandle) -> None:
        handle.runtime.finalize_remove(handle)
