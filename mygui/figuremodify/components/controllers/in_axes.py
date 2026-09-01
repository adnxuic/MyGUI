"""In-Axes zoom and image Controllers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from matplotlib.axes import Axes


from ..base import ComponentController
from ..errors import ComponentValidationError
from ..matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    InAxesRemovalHandle,
)
from ..models import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    PropertySpec,
    RestorePhase,
    UpdateImpact,
)
from ..property_values import (
    apply_line_pattern,
)
from ._helpers import (
    _nonnegative,
    _optional_text,
    _line_pattern,
    _connectors,
    _optional_sketch,
    _set_sketch,
    _normalize_color,
    _read_color,
    _in_axes_rectangle,
    _in_axes_range,
    _optional_extent,
    _validate_in_axes_image_data,
    decode_in_axes_image,
    bind_closed_property_handlers,
    closed_handler_subset,
    lookup_property_handler,
)

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
        for connector, corner in zip(connectors, corners, strict=True):
            connector.set_positions(connector.xy1, corner)

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector.get("object_id") != state.id:
            raise ComponentValidationError(
                "Inset selector object_id must equal its component id."
            )

    def _read_property(self, runtime: Any, spec: PropertySpec) -> Any:
        handler = lookup_property_handler(
            _IN_AXES_READERS,
            spec,
            owner="In-Axes",
            action="read",
        )
        return handler(self, runtime, spec)

    def _write_property(
        self, runtime: Any, spec: PropertySpec, value: Any
    ) -> None:
        handler = lookup_property_handler(
            _IN_AXES_WRITERS,
            spec,
            owner="In-Axes",
            action="write",
        )
        handler(self, runtime, spec, value)

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


_IN_AXES_IMAGE_GETTERS = {
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
_IN_AXES_IMAGE_SETTERS = {
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
_IN_AXES_REGION_SETTERS = {
    "region_color": "set_edgecolor",
    "region_facecolor": "set_facecolor",
    "region_linewidth": "set_linewidth",
    "region_alpha": "set_alpha",
    "region_fill": "set_fill",
    "region_hatch": "set_hatch",
    "region_zorder": "set_zorder",
}


def _in_axes_read_bounds(controller, runtime, spec):
    del controller, spec
    return tuple(getattr(runtime.bounds_locator, "bounds"))


def _in_axes_read_visible(controller, runtime, spec):
    del spec
    return bool(controller._runtime_axes(runtime).get_visible())


def _in_axes_read_zorder(controller, runtime, spec):
    del spec
    return float(controller._runtime_axes(runtime).get_zorder())


def _in_axes_read_facecolor(controller, runtime, spec):
    del spec
    return _read_color(controller._runtime_axes(runtime).get_facecolor())


def _in_axes_read_frameon(controller, runtime, spec):
    del spec
    return bool(controller._runtime_axes(runtime).get_frame_on())


def _in_axes_read_edgecolor(controller, runtime, spec):
    del spec
    axes = controller._runtime_axes(runtime)
    return _read_color(axes.spines["left"].get_edgecolor())


def _in_axes_read_linewidth(controller, runtime, spec):
    del spec
    axes = controller._runtime_axes(runtime)
    return float(axes.spines["left"].get_linewidth())


def _in_axes_read_xlim(controller, runtime, spec):
    del spec
    return tuple(float(value) for value in controller._runtime_axes(runtime).get_xlim())


def _in_axes_read_ylim(controller, runtime, spec):
    del spec
    return tuple(float(value) for value in controller._runtime_axes(runtime).get_ylim())


def _in_axes_read_ticks_visible(controller, runtime, spec):
    del spec
    axes = controller._runtime_axes(runtime)
    return bool(axes.xaxis.get_visible() and axes.yaxis.get_visible())


def _in_axes_read_region_visible(controller, runtime, spec):
    del controller, spec
    return bool(getattr(runtime, "region_visible", True))


def _in_axes_read_region(controller, runtime, spec):
    key = spec.key
    rectangle = getattr(runtime, "indicator_rectangle", None)
    if rectangle is None:
        return controller._state.properties[key]
    if key == "region_color":
        return _read_color(rectangle.get_edgecolor())
    if key == "region_facecolor":
        return _read_color(rectangle.get_facecolor())
    if key == "region_linestyle":
        return deepcopy(
            getattr(
                runtime,
                "region_line_pattern",
                controller._state.properties[key],
            )
        )
    if key == "region_linewidth":
        return float(rectangle.get_linewidth())
    if key == "region_alpha":
        value = rectangle.get_alpha()
        return 1.0 if value is None else float(value)
    return getattr(rectangle, f"get_{key.removeprefix('region_')}")()


def _in_axes_read_connectors(controller, runtime, spec):
    key = spec.key
    return deepcopy(
        tuple(getattr(runtime, "connector_specs", controller._state.properties[key]))
    )


def _in_axes_read_opacity(controller, runtime, spec):
    del spec
    image = getattr(runtime, "image_artist", None)
    if image is None:
        return float(controller._state.properties.get("opacity", 1.0))
    value = image.get_alpha()
    return 1.0 if value is None else float(value)


def _in_axes_read_fit_mode(controller, runtime, spec):
    del controller, spec
    return str(getattr(runtime, "fit_mode", "contain"))


def _in_axes_read_interpolation(controller, runtime, spec):
    del spec
    image = getattr(runtime, "image_artist", None)
    if image is None:
        return str(controller._state.properties.get("interpolation", "antialiased"))
    return str(image.get_interpolation())


def _in_axes_read_image(controller, runtime, spec):
    key = spec.key
    image = getattr(runtime, "image_artist", None)
    if image is None:
        return deepcopy(controller._state.properties.get(key, spec.default))
    accessor = getattr(image, _IN_AXES_IMAGE_GETTERS[key])
    result = accessor() if callable(accessor) else accessor
    if key == "extent":
        return tuple(float(item) for item in result)
    if key in {"filterrad", "image_zorder"}:
        return float(result)
    return result


def _in_axes_write_bounds(controller, runtime, spec, value):
    del spec
    runtime.bounds_locator.bounds = tuple(value)
    controller._runtime_axes(runtime).stale = True


def _in_axes_write_visible(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_visible(bool(value))
    controller._sync_indicator_visibility(runtime)


def _in_axes_write_zorder(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_zorder(value)


def _in_axes_write_facecolor(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_facecolor(value)


def _in_axes_write_frameon(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_frame_on(bool(value))


def _in_axes_write_edgecolor(controller, runtime, spec, value):
    del spec
    for spine in controller._runtime_axes(runtime).spines.values():
        spine.set_edgecolor(value)


def _in_axes_write_linewidth(controller, runtime, spec, value):
    del spec
    for spine in controller._runtime_axes(runtime).spines.values():
        spine.set_linewidth(value)


def _in_axes_write_xlim(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_xlim(*value)
    controller._sync_indicator_positions(runtime)


def _in_axes_write_ylim(controller, runtime, spec, value):
    del spec
    controller._runtime_axes(runtime).set_ylim(*value)
    controller._sync_indicator_positions(runtime)


def _in_axes_write_ticks_visible(controller, runtime, spec, value):
    del spec
    axes = controller._runtime_axes(runtime)
    axes.xaxis.set_visible(bool(value))
    axes.yaxis.set_visible(bool(value))


def _in_axes_write_region_visible(controller, runtime, spec, value):
    del spec
    runtime.region_visible = bool(value)
    controller._sync_indicator_visibility(runtime)


def _in_axes_write_region(controller, runtime, spec, value):
    del controller
    key = spec.key
    rectangle = getattr(runtime, "indicator_rectangle", None)
    if rectangle is None:
        return
    if key == "region_linestyle":
        apply_line_pattern(rectangle, value)
        runtime.region_line_pattern = deepcopy(value)
        return
    getattr(rectangle, _IN_AXES_REGION_SETTERS[key])(value)


def _in_axes_write_connectors(controller, runtime, spec, value):
    del spec
    runtime.connector_specs = deepcopy(tuple(value))
    connectors = tuple(runtime.connectors)
    if not connectors:
        return
    for connector, connector_spec in zip(connectors, value, strict=True):
        connector.set_edgecolor(connector_spec["color"])
        pattern = connector_spec["line_pattern"]
        connector.set_linestyle(
            pattern["value"]
            if pattern["kind"] == "preset"
            else (pattern["offset"], pattern["dashes"])
        )
        connector.set_linewidth(connector_spec["linewidth"])
        connector.set_alpha(connector_spec["alpha"])
        connector.set_zorder(connector_spec["zorder"])
    controller._sync_indicator_visibility(runtime)


def _in_axes_write_opacity(controller, runtime, spec, value):
    del controller, spec
    image = getattr(runtime, "image_artist", None)
    if image is not None:
        image.set_alpha(value)


def _in_axes_write_fit_mode(controller, runtime, spec, value):
    del spec
    runtime.fit_mode = str(value)
    controller._runtime_axes(runtime).set_aspect(
        "equal" if value == "contain" else "auto"
    )


def _in_axes_write_interpolation(controller, runtime, spec, value):
    del controller, spec
    image = getattr(runtime, "image_artist", None)
    if image is not None:
        image.set_interpolation(value)


def _in_axes_write_image(controller, runtime, spec, value):
    del controller
    key = spec.key
    image = getattr(runtime, "image_artist", None)
    if image is None:
        return
    if key == "image_sketch_params":
        _set_sketch(image, value)
        return
    name = _IN_AXES_IMAGE_SETTERS[key]
    if name == "origin":
        image.origin = value
        image.stale = True
        return
    getattr(image, name)(value)


_IN_AXES_READERS: dict[str, Any] = {
    "bounds": _in_axes_read_bounds,
    "visible": _in_axes_read_visible,
    "zorder": _in_axes_read_zorder,
    "facecolor": _in_axes_read_facecolor,
    "frameon": _in_axes_read_frameon,
    "edgecolor": _in_axes_read_edgecolor,
    "linewidth": _in_axes_read_linewidth,
    "xlim": _in_axes_read_xlim,
    "ylim": _in_axes_read_ylim,
    "ticks_visible": _in_axes_read_ticks_visible,
    "region_visible": _in_axes_read_region_visible,
    "region_color": _in_axes_read_region,
    "region_linestyle": _in_axes_read_region,
    "region_linewidth": _in_axes_read_region,
    "region_alpha": _in_axes_read_region,
    "region_facecolor": _in_axes_read_region,
    "region_fill": _in_axes_read_region,
    "region_hatch": _in_axes_read_region,
    "region_zorder": _in_axes_read_region,
    "connectors": _in_axes_read_connectors,
    "opacity": _in_axes_read_opacity,
    "fit_mode": _in_axes_read_fit_mode,
    "interpolation": _in_axes_read_interpolation,
}
_IN_AXES_READERS.update(
    {key: _in_axes_read_image for key in _IN_AXES_IMAGE_GETTERS}
)
_IN_AXES_WRITERS: dict[str, Any] = {
    "bounds": _in_axes_write_bounds,
    "visible": _in_axes_write_visible,
    "zorder": _in_axes_write_zorder,
    "facecolor": _in_axes_write_facecolor,
    "frameon": _in_axes_write_frameon,
    "edgecolor": _in_axes_write_edgecolor,
    "linewidth": _in_axes_write_linewidth,
    "xlim": _in_axes_write_xlim,
    "ylim": _in_axes_write_ylim,
    "ticks_visible": _in_axes_write_ticks_visible,
    "region_visible": _in_axes_write_region_visible,
    "region_color": _in_axes_write_region,
    "region_linestyle": _in_axes_write_region,
    "region_linewidth": _in_axes_write_region,
    "region_alpha": _in_axes_write_region,
    "region_facecolor": _in_axes_write_region,
    "region_fill": _in_axes_write_region,
    "region_hatch": _in_axes_write_region,
    "region_zorder": _in_axes_write_region,
    "connectors": _in_axes_write_connectors,
    "opacity": _in_axes_write_opacity,
    "fit_mode": _in_axes_write_fit_mode,
    "interpolation": _in_axes_write_interpolation,
}
_IN_AXES_WRITERS.update(
    {key: _in_axes_write_image for key in _IN_AXES_IMAGE_SETTERS}
)
for _in_axes_type in (ZoomInAxesController, ImageInAxesController):
    bind_closed_property_handlers(
        specs=_in_axes_type.PROPERTY_SPECS,
        readers=closed_handler_subset(
            _IN_AXES_READERS,
            _in_axes_type.PROPERTY_SPECS,
            owner=_in_axes_type.__name__,
        ),
        writers=closed_handler_subset(
            _IN_AXES_WRITERS,
            _in_axes_type.PROPERTY_SPECS,
            owner=_in_axes_type.__name__,
        ),
        owner=_in_axes_type.__name__,
    )

