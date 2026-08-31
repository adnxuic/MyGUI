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
            connectors = tuple(runtime.connectors)
            if not connectors:
                return
            for connector, connector_spec in zip(
                connectors,
                value,
                strict=True,
            ):
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
