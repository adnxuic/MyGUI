"""Legend Controller."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.legend import Legend


from ..base import ComponentController
from ..errors import ComponentNotFoundError, ComponentValidationError
from ..models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    PropertySpec,
    UpdateImpact,
)
from ..property_values import (
    apply_line_pattern,
    legend_anchor_value,
    legend_location_value,
    normalize_font,
    normalize_legend_anchor,
    normalize_legend_location,
)
from ._helpers import (
    _optional_text,
    _line_pattern,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    _DEFAULT_FONT_SPEC,
    apply_font_spec,
    bind_closed_property_handlers,
    lookup_property_handler,
)

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
        handler = lookup_property_handler(
            _LEGEND_READERS,
            spec,
            owner="Legend",
            action="read",
        )
        return handler(self, target, spec)

    def _write_property(
        self, target: Legend, spec: PropertySpec, value: Any
    ) -> None:
        handler = lookup_property_handler(
            _LEGEND_WRITERS,
            spec,
            owner="Legend",
            action="write",
        )
        handler(self, target, spec, value)

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


def _legend_read_entry_scope(controller, target, spec):
    del target, spec
    return controller._entry_scope


def _legend_read_constructor(controller, target, spec):
    del target
    return deepcopy(controller._constructor_properties[spec.key])


def _legend_read_ncols(controller, target, spec):
    del controller, spec
    return int(getattr(target, "_ncols", 1))


def _legend_read_frame_color(controller, target, spec):
    return controller._frame_color(target, spec.key)


def _legend_read_framealpha(controller, target, spec):
    del controller, spec
    return target.get_frame().get_alpha()


def _legend_read_title(controller, target, spec):
    del controller, spec
    return target.get_title().get_text()


def _legend_read_alignment(controller, target, spec):
    del controller, spec
    return str(target.get_alignment())


def _legend_read_font(controller, target, spec):
    text = (
        target.get_title()
        if spec.key == "title_font"
        else (target.get_texts()[0] if target.get_texts() else None)
    )
    if text is None:
        return deepcopy(
            controller._title_font_value
            if spec.key == "title_font"
            else controller._label_font_value
        )
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


def _legend_read_frame_linewidth(controller, target, spec):
    del controller, spec
    return float(target.get_frame().get_linewidth())


def _legend_read_cached(controller, target, spec):
    del target
    return deepcopy(controller._state.properties[spec.key])


def _legend_read_frame_hatch(controller, target, spec):
    del controller, spec
    return target.get_frame().get_hatch()


def _legend_read_draggable(controller, target, spec):
    del controller, spec
    return target.get_draggable()


def _legend_read_draggable_update(controller, target, spec):
    del target
    return str(controller._state.properties[spec.key])


def _legend_read_via_base(controller, target, spec):
    return ComponentController._read_property(controller, target, spec)


def _legend_write_entry_scope(controller, target, spec, value):
    del target, spec
    controller._entry_scope = str(value)


def _legend_write_rebuild(controller, target, spec, value):
    controller._constructor_properties[spec.key] = deepcopy(value)
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


def _legend_write_facecolor(controller, target, spec, value):
    del controller, spec
    target.get_frame().set_facecolor(value)


def _legend_write_edgecolor(controller, target, spec, value):
    del controller, spec
    target.get_frame().set_edgecolor(value)


def _legend_write_framealpha(controller, target, spec, value):
    del controller, spec
    target.get_frame().set_alpha(value)


def _legend_write_title(controller, target, spec, value):
    del controller, spec
    target.set_title(value)


def _legend_write_font(controller, target, spec, value):
    if spec.key == "title_font":
        controller._title_font_value = normalize_font(value)
        texts = [target.get_title()]
    else:
        controller._label_font_value = normalize_font(value)
        texts = target.get_texts()
    apply_font_spec(texts, value)


def _legend_write_draggable(controller, target, spec, value):
    del spec
    target.set_draggable(
        bool(value),
        update=controller._state.properties.get("draggable_update", "loc"),
    )


def _legend_write_draggable_update(controller, target, spec, value):
    del spec
    target.set_draggable(
        bool(controller._state.properties.get("draggable", False)),
        update=value,
    )


def _legend_write_frame_linewidth(controller, target, spec, value):
    del controller, spec
    target.get_frame().set_linewidth(value)


def _legend_write_frame_linestyle(controller, target, spec, value):
    del controller, spec
    apply_line_pattern(target.get_frame(), value)


def _legend_write_frame_hatch(controller, target, spec, value):
    del controller, spec
    target.get_frame().set_hatch(value)


def _legend_write_via_base(controller, target, spec, value):
    ComponentController._write_property(controller, target, spec, value)


_LEGEND_CONSTRUCTOR_READ_KEYS = LegendController.REBUILD_KEYS - {
    "ncols",
    "frameon",
    "alignment",
}
_LEGEND_READERS: dict[str, Any] = {
    "entry_scope": _legend_read_entry_scope,
    "ncols": _legend_read_ncols,
    "facecolor": _legend_read_frame_color,
    "edgecolor": _legend_read_frame_color,
    "framealpha": _legend_read_framealpha,
    "title": _legend_read_title,
    "alignment": _legend_read_alignment,
    "label_font": _legend_read_font,
    "title_font": _legend_read_font,
    "frame_linewidth": _legend_read_frame_linewidth,
    "frame_linestyle": _legend_read_cached,
    "frame_hatch": _legend_read_frame_hatch,
    "draggable": _legend_read_draggable,
    "draggable_update": _legend_read_draggable_update,
}
_LEGEND_READERS.update(
    {key: _legend_read_constructor for key in _LEGEND_CONSTRUCTOR_READ_KEYS}
)
_LEGEND_READERS.update(
    {
        key: _legend_read_via_base
        for key in (
            "visible",
            "frameon",
            "zorder",
            "alpha",
            "label",
            "clip_on",
            "gid",
            "in_layout",
            "rasterized",
            "sketch_params",
            "snap",
            "url",
        )
    }
)
_LEGEND_WRITERS: dict[str, Any] = {
    "entry_scope": _legend_write_entry_scope,
    "facecolor": _legend_write_facecolor,
    "edgecolor": _legend_write_edgecolor,
    "framealpha": _legend_write_framealpha,
    "title": _legend_write_title,
    "label_font": _legend_write_font,
    "title_font": _legend_write_font,
    "draggable": _legend_write_draggable,
    "draggable_update": _legend_write_draggable_update,
    "frame_linewidth": _legend_write_frame_linewidth,
    "frame_linestyle": _legend_write_frame_linestyle,
    "frame_hatch": _legend_write_frame_hatch,
}
_LEGEND_WRITERS.update(
    {key: _legend_write_rebuild for key in LegendController.REBUILD_KEYS}
)
_LEGEND_WRITERS.update(
    {
        key: _legend_write_via_base
        for key in (
            "visible",
            "zorder",
            "alpha",
            "label",
            "clip_on",
            "gid",
            "in_layout",
            "rasterized",
            "sketch_params",
            "snap",
            "url",
        )
    }
)
bind_closed_property_handlers(
    specs=LegendController.PROPERTY_SPECS,
    readers=_LEGEND_READERS,
    writers=_LEGEND_WRITERS,
    owner="LegendController",
)
