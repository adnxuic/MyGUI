"""Title, axis-label, and free Text Controllers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.text import Text


from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    PropertySpec,
    RestorePhase,
)
from ..property_values import (
    normalize_text_box,
    text_box_kwargs,
)
from ._helpers import (
    _positive,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    _pair,
    _rotation,
    _axis_name,
)

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
            # Omitting transform deliberately selects Axes.transAxes, matching
            # Matplotlib's public Axis.set_label_coords coordinate contract.
            parent.set_label_coords(
                float(value[0]),
                float(value[1]),
            )
            return
        super()._write_property(target, spec, value)
