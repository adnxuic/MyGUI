"""Annotation (text + target point + arrow) Controller."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from typing import Any

from matplotlib.text import Annotation

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    AnnotationArrowStyle,
    AnnotationConnectionStyle,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    CoordinateSystem,
    DeletionPolicy,
    PropertySpec,
    RestorePhase,
)
from ..property_values import (
    annotation_box_kwargs,
    normalize_annotation_box,
)
from ._helpers import (
    _positive,
    _normalize_color,
    _read_color,
    _pair,
    _rotation,
)

COORDINATE_SYSTEMS = (
    CoordinateSystem.DATA.value,
    CoordinateSystem.AXES_FRACTION.value,
    CoordinateSystem.FIGURE_FRACTION.value,
    CoordinateSystem.OFFSET_POINTS.value,
)
TARGET_COORDINATE_SYSTEMS = (
    CoordinateSystem.DATA.value,
    CoordinateSystem.AXES_FRACTION.value,
)
TEXT_COORDINATE_SYSTEMS = (
    CoordinateSystem.DATA.value,
    CoordinateSystem.AXES_FRACTION.value,
    CoordinateSystem.OFFSET_POINTS.value,
)

_MPL_COORDINATE_SYSTEMS = {
    CoordinateSystem.DATA.value: "data",
    CoordinateSystem.AXES_FRACTION.value: "axes fraction",
    CoordinateSystem.FIGURE_FRACTION.value: "figure fraction",
    CoordinateSystem.OFFSET_POINTS.value: "offset points",
}
_MPL_COORDINATE_SYSTEM_NAMES = {
    value: key for key, value in _MPL_COORDINATE_SYSTEMS.items()
}

ANNOTATION_ARROW_STYLES = {
    AnnotationArrowStyle.LINE.value: "-",
    AnnotationArrowStyle.ARROW.value: "->",
    AnnotationArrowStyle.FILLED_ARROW.value: "-|>",
    AnnotationArrowStyle.DOUBLE_ARROW.value: "<->",
}
ANNOTATION_CONNECTION_STYLES = {
    AnnotationConnectionStyle.STRAIGHT.value: "arc3,rad=0",
    AnnotationConnectionStyle.ANGLE.value: "angle3,angleA=0,angleB=90",
    AnnotationConnectionStyle.ARC.value: "arc3,rad=0.2",
}


def _finite_pair(value: Any) -> tuple[float, float]:
    result = _pair(value)
    if not all(math.isfinite(number) for number in result):
        raise ComponentValidationError("Annotation coordinates must be finite.")
    return result


def coordinate_system_name(value: Any) -> str:
    """Map a Matplotlib coordinate string to the closed wire value."""

    name = _MPL_COORDINATE_SYSTEM_NAMES.get(str(value))
    if name is None:
        raise ComponentValidationError(
            f"Unsupported Annotation coordinate system: {value!r}."
        )
    return name


def _arrow_patch(annotation: Annotation):
    patch = getattr(annotation, "arrow_patch", None)
    if patch is None:
        raise ComponentValidationError(
            "Annotation has no arrow patch; it was created without arrowprops."
        )
    return patch


class AnnotationController(ComponentController[Annotation]):
    """Coordinate state changes for Annotation components."""

    KIND = ComponentKind.ANNOTATION
    ROLES = frozenset({ComponentRole.ANNOTATION})
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec("text", str, "", editor="text"),
        PropertySpec("visible", bool, True, editor="check"),
        PropertySpec("label", str, "", editor="text"),
        PropertySpec(
            "xycoords",
            str,
            CoordinateSystem.DATA.value,
            editor="combo",
            choices=TARGET_COORDINATE_SYSTEMS,
        ),
        PropertySpec(
            "xy",
            tuple,
            (0.0, 0.0),
            editor="position",
            normalizer=_finite_pair,
        ),
        PropertySpec(
            "textcoords",
            str,
            CoordinateSystem.OFFSET_POINTS.value,
            editor="combo",
            choices=TEXT_COORDINATE_SYSTEMS,
        ),
        PropertySpec(
            "xytext",
            tuple,
            (20.0, 20.0),
            editor="position",
            normalizer=_finite_pair,
        ),
        PropertySpec("arrow_enabled", bool, True, editor="check"),
        PropertySpec(
            "arrow_style",
            str,
            AnnotationArrowStyle.ARROW.value,
            editor="combo",
            choices=tuple(ANNOTATION_ARROW_STYLES),
        ),
        PropertySpec(
            "arrow_color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda annotation: _read_color(
                _arrow_patch(annotation).get_color()
            ),
        ),
        PropertySpec(
            "arrow_linewidth",
            float,
            1.5,
            validator=lambda value: value >= 0,
            editor="double_spin",
            minimum=0.0,
        ),
        PropertySpec(
            "connection_style",
            str,
            AnnotationConnectionStyle.STRAIGHT.value,
            editor="combo",
            choices=tuple(ANNOTATION_CONNECTION_STYLES),
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
            getter=lambda annotation: str(annotation.get_fontfamily()[0]),
        ),
        PropertySpec(
            "fontsize",
            float,
            10.0,
            validator=_positive,
            editor="double_spin",
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
            "color",
            str,
            "#000000",
            editor="color",
            normalizer=_normalize_color,
            getter=lambda annotation: _read_color(annotation.get_color()),
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
        PropertySpec(
            "alpha",
            float,
            None,
            validator=lambda value: 0 <= value <= 1,
            editor="double_spin",
            allow_none=True,
        ),
        PropertySpec("usetex", bool, False, editor="check"),
        PropertySpec(
            "bbox",
            dict,
            {
                "enabled": False,
                "style": "rounded",
                "facecolor": "#ffffff",
                "edgecolor": "#000000",
                "linewidth": 1.0,
                "alpha": 1.0,
                "padding": 0.3,
            },
            editor="annotation_box",
            normalizer=normalize_annotation_box,
        ),
        PropertySpec("zorder", float, 3.0, editor="double_spin"),
        PropertySpec("clip_on", bool, True, editor="check"),
    )
    CAPABILITIES = frozenset({"text", "font", "color", "position", "arrow"})

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Set one property while keeping coordinate pairs atomic."""

        if key not in {"xycoords", "textcoords"}:
            return super().set_property(key, value)
        change = self.apply_mutation(
            ComponentMutation(self.component_id, properties={key: value})
        )
        return replace(change, property_key=key)

    def read_state(self, *, strict: bool = False) -> ComponentState:
        """Keep persisted TeX intent separate from the effective renderer."""

        state = super().read_state(strict=strict)
        properties = dict(state.properties)
        properties["usetex"] = bool(
            self._state.properties.get("usetex", False)
        )
        return state.clone(properties=properties)

    def apply_mutation(self, mutation: ComponentMutation) -> ComponentChange:
        """Expand coordinate-system edits into one authoritative pair change."""

        if mutation.component_id != self.component_id or not mutation.properties:
            return super().apply_mutation(mutation)
        try:
            properties = self._coordinate_property_patch(
                dict(mutation.properties)
            )
        except Exception as exc:
            return self._rejected(
                next(iter(mutation.properties), None),
                self._safe_snapshot(),
                str(exc),
            )
        return super().apply_mutation(
            ComponentMutation(
                mutation.component_id,
                properties=properties,
                data=mutation.data,
                runtime_data=mutation.runtime_data,
            )
        )

    def _coordinate_property_patch(
        self,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a safely ordered patch with coupled coordinates included."""

        if not {"xycoords", "textcoords"}.intersection(properties):
            return properties
        target = self.resolve_target()
        specs = self.property_specs()
        target_display = self._display_target(target)
        text_display = self._display_text(target)

        target_system = coordinate_system_name(target.xycoords)
        if "xycoords" in properties:
            target_system = specs["xycoords"].normalize(
                properties["xycoords"]
            )
            properties["xycoords"] = target_system
            if "xy" not in properties:
                transform = self._coordinate_transform(target, target_system)
                properties["xy"] = tuple(
                    transform.inverted().transform(target_display)
                )

        if "xy" in properties:
            target_position = specs["xy"].normalize(properties["xy"])
            properties["xy"] = target_position
            target_display = tuple(
                self._coordinate_transform(target, target_system).transform(
                    target_position
                )
            )

        if "textcoords" in properties:
            text_system = specs["textcoords"].normalize(
                properties["textcoords"]
            )
            properties["textcoords"] = text_system
            if "xytext" not in properties:
                properties["xytext"] = self._text_position_from_display(
                    target,
                    text_system,
                    text_display,
                    target_display,
                )

        # Controller.apply_state uses PROPERTY_SPECS order as well.  Keeping
        # the same order here makes explicit coordinate values win over the
        # display-preserving system conversion in every mutation path.
        return {
            spec.key: properties[spec.key]
            for spec in self.PROPERTY_SPECS
            if spec.key in properties
        }

    def _read_property(self, target: Annotation, spec: PropertySpec) -> Any:
        if spec.key == "bbox":
            return deepcopy(self._state.properties.get("bbox", {"enabled": False}))
        if spec.key == "xycoords":
            return coordinate_system_name(target.xycoords)
        if spec.key == "textcoords":
            return coordinate_system_name(target.anncoords)
        if spec.key == "xy":
            return _finite_pair(target.xy)
        if spec.key == "xytext":
            return _finite_pair(target.get_position())
        if spec.key == "arrow_enabled":
            return bool(_arrow_patch(target).get_visible())
        if spec.key == "arrow_style":
            return self._state.properties.get(
                "arrow_style",
                AnnotationArrowStyle.ARROW.value,
            )
        if spec.key == "arrow_color":
            return _read_color(_arrow_patch(target).get_edgecolor())
        if spec.key == "arrow_linewidth":
            return float(_arrow_patch(target).get_linewidth())
        if spec.key == "connection_style":
            return self._state.properties.get(
                "connection_style",
                AnnotationConnectionStyle.STRAIGHT.value,
            )
        return super()._read_property(target, spec)

    def _coordinate_transform(self, target: Annotation, system: str):
        axes = target.axes
        figure = target.figure
        if figure is None:
            raise ComponentValidationError("Annotation has no Figure transform.")
        if system in {"data", "axes_fraction"} and axes is None:
            raise ComponentValidationError(
                "Annotation target coordinates require an owning Axes."
            )
        return {
            CoordinateSystem.DATA.value: axes.transData if axes is not None else None,
            CoordinateSystem.AXES_FRACTION.value: (
                axes.transAxes if axes is not None else None
            ),
            CoordinateSystem.FIGURE_FRACTION.value: figure.transFigure,
        }[system]

    def _display_target(self, target: Annotation) -> tuple[float, float]:
        transform = self._coordinate_transform(
            target,
            coordinate_system_name(target.xycoords),
        )
        return tuple(transform.transform(_finite_pair(target.xy)))

    def _display_text(self, target: Annotation) -> tuple[float, float]:
        position = _finite_pair(target.get_position())
        current = coordinate_system_name(target.anncoords)
        if current == CoordinateSystem.OFFSET_POINTS.value:
            scale = target.figure.dpi / 72.0
            display_xy = self._display_target(target)
            return (
                display_xy[0] + position[0] * scale,
                display_xy[1] + position[1] * scale,
            )
        transform = self._coordinate_transform(target, current)
        return tuple(transform.transform(position))

    def _text_position_from_display(
        self,
        target: Annotation,
        system: str,
        display: tuple[float, float],
        target_display: tuple[float, float],
    ) -> tuple[float, float]:
        if system == CoordinateSystem.OFFSET_POINTS.value:
            scale = target.figure.dpi / 72.0
            return (
                (display[0] - target_display[0]) / scale,
                (display[1] - target_display[1]) / scale,
            )
        transform = self._coordinate_transform(target, system)
        return tuple(transform.inverted().transform(display))

    def _write_property(
        self,
        target: Annotation,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        key = spec.key
        if key == "xy":
            target.xy = tuple(value)
            target.stale = True
            return
        if key == "xycoords":
            target.xycoords = _MPL_COORDINATE_SYSTEMS[value]
            target.stale = True
            return
        if key == "xytext":
            target.xytext = tuple(value)
            target.set_position(tuple(value))
            target.stale = True
            return
        if key == "textcoords":
            self._write_textcoords(target, value)
            return
        if key == "arrow_enabled":
            _arrow_patch(target).set_visible(bool(value))
            target.stale = True
            return
        if key == "arrow_style":
            _arrow_patch(target).set_arrowstyle(ANNOTATION_ARROW_STYLES[value])
            target.stale = True
            return
        if key == "arrow_color":
            _arrow_patch(target).set_color(value)
            target.stale = True
            return
        if key == "arrow_linewidth":
            _arrow_patch(target).set_linewidth(float(value))
            target.stale = True
            return
        if key == "connection_style":
            _arrow_patch(target).set_connectionstyle(
                ANNOTATION_CONNECTION_STYLES[value]
            )
            target.stale = True
            return
        if key == "bbox":
            target.set_bbox(annotation_box_kwargs(value))
            return
        if key == "label":
            target.set_label(value)
            return
        if key == "fontfamily":
            target.set_fontfamily(value)
            return
        if key == "alpha":
            target.set_alpha(value)
            patch = getattr(target, "arrow_patch", None)
            if patch is not None:
                patch.set_alpha(value)
            target.stale = True
            return
        if key == "clip_on":
            target.set_clip_on(bool(value))
            patch = getattr(target, "arrow_patch", None)
            if patch is not None:
                patch.set_clip_on(bool(value))
            target.stale = True
            return
        super()._write_property(target, spec, value)

    def _write_textcoords(self, target: Annotation, value: str) -> None:
        target.anncoords = _MPL_COORDINATE_SYSTEMS[value]
        target.stale = True

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.properties.get("xycoords") not in TARGET_COORDINATE_SYSTEMS:
            raise ComponentValidationError(
                "Annotation target supports only data and axes_fraction "
                "coordinates."
            )
        if state.properties.get("textcoords") not in TEXT_COORDINATE_SYSTEMS:
            raise ComponentValidationError(
                "Annotation text position supports only data, axes_fraction, "
                "and offset_points coordinates."
            )
