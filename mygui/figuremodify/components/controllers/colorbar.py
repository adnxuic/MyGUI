"""Colorbar Controller."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from matplotlib.colorbar import Colorbar
from matplotlib.text import Text


from ..base import ComponentController
from ..errors import ComponentValidationError
from ..matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    ColorbarRemovalHandle,
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
    build_formatter,
    build_locator,
    formatter_from_axis,
    locator_from_axis,
    normalize_font,
    normalize_formatter,
    normalize_locator,
    validate_fixed_ticker_pair,
)
from ._helpers import (
    _DEFAULT_FONT_SPEC,
    _normalize_color,
    _read_color,
)


@dataclass(frozen=True, slots=True)
class ColorbarRuntimeConfiguration:
    """Controller-owned non-Artist configuration for a rebuilt Colorbar."""

    constructor_properties: dict[str, Any]
    label_font: dict[str, Any]
    tick_font: dict[str, Any]
    minor_ticks: bool
    ticklocation: str


class ColorbarController(ComponentController[Colorbar]):
    """Control one Colorbar without duplicating its source mapping state."""

    KIND = ComponentKind.COLORBAR
    ROLES = frozenset({ComponentRole.COLORBAR})
    DELETION_POLICY = DeletionPolicy.REMOVE
    RESTORE_PHASE = RestorePhase.COLORBAR
    CAPABILITIES = frozenset({"colorbar", "source_dependency", "font", "color"})
    DELETE_IMPACTS = UpdateImpact.REDRAW
    REBUILD_KEYS = frozenset(
        {
            "location",
            "fraction",
            "shrink",
            "aspect",
            "pad",
            "extend",
            "spacing",
            "drawedges",
        }
    )
    PROPERTY_SPECS = (
        PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec("label", str, "", editor=EditorKind.TEXT),
        PropertySpec(
            "location",
            str,
            "right",
            editor=EditorKind.ENUM,
            choices=("left", "right", "top", "bottom"),
        ),
        PropertySpec(
            "fraction",
            float,
            0.15,
            editor=EditorKind.NUMBER,
            minimum=0.001,
            maximum=1.0,
        ),
        PropertySpec(
            "shrink",
            float,
            1.0,
            editor=EditorKind.NUMBER,
            minimum=0.001,
            maximum=1.0,
        ),
        PropertySpec(
            "aspect",
            float,
            20.0,
            editor=EditorKind.NUMBER,
            minimum=0.001,
        ),
        PropertySpec(
            "pad",
            float,
            0.05,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
        ),
        PropertySpec(
            "extend",
            str,
            "neither",
            editor=EditorKind.ENUM,
            choices=("neither", "both", "min", "max"),
            advanced=True,
        ),
        PropertySpec(
            "spacing",
            str,
            "uniform",
            editor=EditorKind.ENUM,
            choices=("uniform", "proportional"),
            advanced=True,
        ),
        PropertySpec(
            "drawedges",
            bool,
            False,
            editor=EditorKind.BOOL,
            advanced=True,
        ),
        PropertySpec(
            "locator",
            dict,
            deepcopy(DEFAULT_MAJOR_LOCATOR),
            editor=EditorKind.LOCATOR_SPEC,
            normalizer=normalize_locator,
        ),
        PropertySpec(
            "formatter",
            dict,
            deepcopy(DEFAULT_FORMATTER),
            editor=EditorKind.FORMATTER_SPEC,
            normalizer=normalize_formatter,
        ),
        PropertySpec(
            "minor_ticks",
            bool,
            False,
            editor=EditorKind.BOOL,
        ),
        PropertySpec(
            "ticklocation",
            str,
            "auto",
            editor=EditorKind.ENUM,
            choices=("auto", "left", "right", "top", "bottom"),
        ),
        PropertySpec(
            "label_font",
            dict,
            deepcopy(_DEFAULT_FONT_SPEC),
            editor=EditorKind.FONT_SPEC,
            normalizer=normalize_font,
        ),
        PropertySpec(
            "tick_font",
            dict,
            deepcopy(_DEFAULT_FONT_SPEC),
            editor=EditorKind.FONT_SPEC,
            normalizer=normalize_font,
        ),
        PropertySpec(
            "outline_visible",
            bool,
            True,
            editor=EditorKind.BOOL,
        ),
        PropertySpec(
            "outline_color",
            str,
            "#000000",
            editor=EditorKind.COLOR,
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "outline_linewidth",
            float,
            0.8,
            editor=EditorKind.NUMBER,
            minimum=0.0,
        ),
    )

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        self._constructor_properties = {
            key: self.property_specs()[key].normalize(
                deepcopy(state.properties.get(key, self.property_specs()[key].default))
            )
            for key in self.REBUILD_KEYS
        }
        self._label_font_value = normalize_font(
            state.properties.get("label_font", deepcopy(_DEFAULT_FONT_SPEC))
        )
        self._tick_font_value = normalize_font(
            state.properties.get("tick_font", deepcopy(_DEFAULT_FONT_SPEC))
        )
        self._minor_ticks = bool(state.properties.get("minor_ticks", False))
        self._ticklocation = str(state.properties.get("ticklocation", "auto"))
        super().__init__(state, **kwargs)

    def runtime_configuration(self) -> ColorbarRuntimeConfiguration:
        """Return an immutable copy of Controller-owned runtime configuration."""

        return ColorbarRuntimeConfiguration(
            deepcopy(self._constructor_properties),
            deepcopy(self._label_font_value),
            deepcopy(self._tick_font_value),
            self._minor_ticks,
            self._ticklocation,
        )

    def adopt_runtime_configuration(
        self,
        configuration: ColorbarRuntimeConfiguration,
        *,
        include_constructor_properties: bool = True,
    ) -> None:
        """Adopt validated configuration from a temporary Controller.

        A constructor-sensitive property edit defers the authoritative
        constructor mapping until the Registry mutation is committed. Source-
        driven runtime rebuilds may adopt the complete mapping immediately.
        """

        if not isinstance(configuration, ColorbarRuntimeConfiguration):
            raise TypeError("Colorbar runtime configuration is invalid.")
        if include_constructor_properties:
            self._constructor_properties = deepcopy(
                configuration.constructor_properties
            )
        self._label_font_value = deepcopy(configuration.label_font)
        self._tick_font_value = deepcopy(configuration.tick_font)
        self._minor_ticks = bool(configuration.minor_ticks)
        self._ticklocation = str(configuration.ticklocation)

    @staticmethod
    def _orientation(location: str) -> str:
        return "vertical" if location in {"left", "right"} else "horizontal"

    def _axis(self, target: Colorbar):
        return (
            target.ax.yaxis
            if self._orientation(self._constructor_properties["location"])
            == "vertical"
            else target.ax.xaxis
        )

    @staticmethod
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

    @staticmethod
    def _apply_font(texts: list[Text], value: dict[str, Any]) -> None:
        for text in texts:
            text.set_fontfamily(value["family"])
            text.set_fontsize(value["size"])
            text.set_fontweight(value["weight"])
            text.set_fontstyle(value["style"])
            text.set_fontstretch(value["stretch"])
            text.set_fontvariant(value["variant"])
            text.set_color(value["color"])

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector.get("object_id") != state.id:
            raise ComponentValidationError(
                "Colorbar selector object_id must equal its component id."
            )
        location = str(state.properties["location"])
        ticklocation = str(state.properties["ticklocation"])
        allowed = (
            {"auto", "left", "right"}
            if location in {"left", "right"}
            else {"auto", "top", "bottom"}
        )
        if ticklocation not in allowed:
            raise ComponentValidationError(
                f"Tick location {ticklocation!r} is incompatible with "
                f"Colorbar location {location!r}."
            )
        validate_fixed_ticker_pair(
            state.properties["locator"],
            state.properties["formatter"],
        )

    def _validate_data(self, state: ComponentState) -> None:
        if set(state.data) != {"source_component_id"}:
            raise ComponentValidationError(
                "Colorbar data requires only source_component_id."
            )
        source_id = state.data["source_component_id"]
        if not isinstance(source_id, str) or not source_id.strip():
            raise ComponentValidationError(
                "Colorbar source_component_id must be a non-empty string."
            )

    def _read_property(self, target: Colorbar, spec: PropertySpec) -> Any:
        key = spec.key
        if key in self.REBUILD_KEYS:
            return deepcopy(self._constructor_properties[key])
        axis = self._axis(target)
        if key == "visible":
            return bool(target.ax.get_visible())
        if key == "label":
            return str(axis.label.get_text())
        if key == "locator":
            return locator_from_axis(
                target.locator,
                self._state.properties.get(key, spec.default),
                minor=False,
            )
        if key == "formatter":
            return formatter_from_axis(
                target.formatter,
                self._state.properties.get(key, spec.default),
                minor=False,
            )
        if key == "minor_ticks":
            return self._minor_ticks
        if key == "ticklocation":
            return self._ticklocation
        if key == "label_font":
            return self._font_from_text(axis.label, self._label_font_value)
        if key == "tick_font":
            labels = list(axis.get_ticklabels(minor=False))
            return (
                self._font_from_text(labels[0], self._tick_font_value)
                if labels
                else deepcopy(self._tick_font_value)
            )
        if key == "outline_visible":
            return bool(target.outline.get_visible())
        if key == "outline_color":
            return _read_color(target.outline.get_edgecolor())
        if key == "outline_linewidth":
            return float(target.outline.get_linewidth())
        return super()._read_property(target, spec)

    def _write_property(
        self, target: Colorbar, spec: PropertySpec, value: Any
    ) -> None:
        key = spec.key
        if key in self.REBUILD_KEYS:
            self._constructor_properties[key] = deepcopy(value)
            return
        axis = self._axis(target)
        if key == "visible":
            target.ax.set_visible(bool(value))
            return
        if key == "label":
            target.set_label(str(value))
            return
        if key == "locator":
            target.locator = build_locator(value)
            target.update_ticks()
            return
        if key == "formatter":
            target.formatter = build_formatter(value)
            target.update_ticks()
            return
        if key == "minor_ticks":
            target.minorticks_on() if value else target.minorticks_off()
            self._minor_ticks = bool(value)
            return
        if key == "ticklocation":
            actual = self._constructor_properties["location"] if value == "auto" else value
            axis.set_ticks_position(actual)
            self._ticklocation = str(value)
            return
        if key == "label_font":
            self._label_font_value = normalize_font(value)
            self._apply_font([axis.label], self._label_font_value)
            return
        if key == "tick_font":
            self._tick_font_value = normalize_font(value)
            self._apply_font(
                [
                    *axis.get_ticklabels(minor=False),
                    *axis.get_ticklabels(minor=True),
                ],
                self._tick_font_value,
            )
            return
        if key == "outline_visible":
            target.outline.set_visible(bool(value))
            return
        if key == "outline_color":
            target.outline.set_edgecolor(value)
            return
        if key == "outline_linewidth":
            target.outline.set_linewidth(float(value))
            return
        super()._write_property(target, spec, value)

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        if impacts == UpdateImpact.NONE:
            return
        colorbar = target if isinstance(target, Colorbar) else self.resolve_target()
        figure = colorbar.ax.figure
        if self._registry is not None:
            self._registry.request_update(figure, impacts)
        elif figure.canvas is not None and UpdateImpact.REDRAW in impacts:
            figure.canvas.draw_idle()

    def prepare_remove(self) -> ColorbarRemovalHandle:
        return MATPLOTLIB_REMOVAL.prepare_colorbar(self.resolve_target())

    def commit_remove(self, handle: ColorbarRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.commit(handle)

    def rollback_remove(self, handle: ColorbarRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.rollback(handle)

    def _finalize_remove(self, handle: ColorbarRemovalHandle) -> None:
        MATPLOTLIB_REMOVAL.finalize(handle)
