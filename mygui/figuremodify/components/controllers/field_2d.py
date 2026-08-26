"""Controllers for Pseudocolor, Heatmap, and Contour FIELD_2D roles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from mygui.figuremodify.components.property_values import (
    DEFAULT_COLOR_MAP,
    DEFAULT_CONTOUR_LABELS,
    DEFAULT_CONTOUR_LEVELS,
    DEFAULT_GRID_EDGE,
    apply_color_map_spec,
    normalize_color_map_spec,
    normalize_contour_label_spec,
    normalize_contour_levels_spec,
    normalize_grid_edge_spec,
    normalize_line_pattern,
)
from mygui.figuremodify.field_2d_runtime import Field2DRuntime
from mygui.figuremodify.matplotlib_adapter import (
    CONTOUR_ALGORITHM_CHOICES,
    CONTOUR_EXTEND_CHOICES,
    CONTOUR_MODE_CHOICES,
    IMAGE_INTERPOLATION_CHOICES,
    INTERPOLATION_STAGE_CHOICES,
    PSEUDOCOLOR_SHADING_CHOICES,
)

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..matplotlib_removal import MATPLOTLIB_REMOVAL, Field2DRemovalHandle
from ..models import (
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    KEEP_RUNTIME_DATA,
    EditorKind,
    Field2DData,
    PropertySpec,
    RestorePhase,
    UpdateImpact,
)
from ._helpers import (
    _ARTIST_EXPORT_PROPERTIES,
    _column_reference,
    _exact_data_fields,
    _nonnegative,
)

_FIELD_EXPORT_PROPERTIES = tuple(
    spec
    for spec in _ARTIST_EXPORT_PROPERTIES
    if spec.key in {"clip_on", "gid", "in_layout", "rasterized", "snap", "url"}
)

_COMMON_FIELD_PROPERTIES = (
    PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
    PropertySpec(
        "alpha",
        float,
        None,
        validator=lambda value: 0 <= value <= 1,
        editor=EditorKind.NUMBER,
        allow_none=True,
        minimum=0.0,
        maximum=1.0,
    ),
    PropertySpec(
        "colormap",
        dict,
        deepcopy(DEFAULT_COLOR_MAP),
        editor=EditorKind.COLOR_MAP_SPEC,
        normalizer=normalize_color_map_spec,
        impact=UpdateImpact.REDRAW,
    ),
    PropertySpec("zorder", float, 1.0, editor=EditorKind.NUMBER),
) + _FIELD_EXPORT_PROPERTIES


def _alpha_ok(value: Any) -> bool:
    return 0 <= value <= 1


class Field2DController(ComponentController[Field2DRuntime]):
    """Shared FIELD_2D controller contract for the three chart roles."""

    KIND = ComponentKind.FIELD_2D
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    CAPABILITIES = frozenset(
        {
            "field_2d",
            "data",
            "data_reference",
            "auto_refresh",
            "scalar_mappable",
        }
    )
    DELETE_IMPACTS = UpdateImpact.RELIM | UpdateImpact.AUTOSCALE | UpdateImpact.REDRAW
    REBUILD_KEYS = frozenset({"colormap"})

    def resolve_target(self) -> Field2DRuntime:
        target = super().resolve_target()
        if not isinstance(target, Field2DRuntime):
            raise ComponentValidationError(
                "FIELD_2D controller requires a Field2DRuntime target."
            )
        return target

    def _validate_data(self, state: ComponentState) -> None:
        _exact_data_fields(state, {"x_ref", "y_ref", "z_ref"})
        _column_reference(state.data["x_ref"], "x_ref")
        _column_reference(state.data["y_ref"], "y_ref")
        _column_reference(state.data["z_ref"], "z_ref")

    def prepare_remove(self) -> Field2DRemovalHandle:
        if self.DELETION_POLICY is not DeletionPolicy.REMOVE:
            raise ComponentValidationError(
                f"{type(self).__name__} does not support physical removal."
            )
        return MATPLOTLIB_REMOVAL.prepare_field_2d(self.resolve_target())

    def _read_property(self, target: Field2DRuntime, spec: PropertySpec) -> Any:
        if spec.key in self._state.properties:
            if spec.key in {
                "colormap",
                "edgecolor",
                "levels",
                "labels",
                "linestyle",
                "negative_linestyle",
                "shading",
                "mode",
                "interpolation",
                "interpolation_stage",
            }:
                return deepcopy(self._state.properties[spec.key])
        if spec.key == "visible":
            if target.iter_artists():
                return bool(target.iter_artists()[0].get_visible())
            return deepcopy(self._state.properties["visible"])
        if spec.key == "alpha":
            artists = target.iter_artists()
            if artists:
                return artists[0].get_alpha()
            return deepcopy(self._state.properties.get("alpha"))
        if spec.key == "zorder":
            artists = target.iter_artists()
            if artists:
                return float(artists[0].get_zorder())
            return float(self._state.properties["zorder"])
        return deepcopy(self._state.properties.get(spec.key, spec.default))

    def _write_property(
        self,
        target: Field2DRuntime,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        if spec.key == "colormap":
            target.apply_colormap(value)
            return
        if spec.key == "visible":
            target.set_visible(value)
            return
        if spec.key == "alpha":
            target.set_alpha(value)
            return
        if spec.key == "zorder":
            target.set_zorder(value)
            return
        if spec.key == "clip_on":
            target.set_clip_on(value)
            return
        if spec.key == "rasterized":
            target.set_rasterized(value)
            return
        if spec.key == "in_layout":
            target.set_in_layout(value)
            return
        if spec.key == "snap":
            target.set_snap(value)
            return
        if spec.key == "url":
            target.set_url(value)
            return
        if spec.key == "gid":
            if value:
                target.set_gid(value)
            return
        if spec.key in self.REBUILD_KEYS:
            return
        artist = target.primary
        if artist is None:
            return
        super()._write_property(artist, spec, value)

    def _validate_runtime_data(
        self,
        target: Field2DRuntime,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target, state
        if not isinstance(runtime_data, Field2DData):
            raise ComponentValidationError(
                "FIELD_2D runtime data must be Field2DData."
            )

    def _apply_runtime_data(
        self,
        target: Field2DRuntime,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)

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
        target: Field2DRuntime,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del state
        if isinstance(runtime_data, Field2DData):
            return bool(runtime_data.empty)
        return bool(getattr(target, "empty", False))

    def _is_empty(self, target: Field2DRuntime, state: ComponentState) -> bool:
        del state
        return bool(target.empty)

    def _capture_runtime_data(self, target: Field2DRuntime) -> dict[str, Any]:
        array = getattr(target.mappable, "get_array", lambda: None)()
        return {
            "empty": bool(target.empty),
            "array": (
                None
                if array is None
                else np.ma.asarray(array).copy()
            ),
            "cmap": deepcopy(self._state.properties.get("colormap")),
        }

    def _restore_runtime_data(
        self,
        target: Field2DRuntime,
        runtime_data: Any,
    ) -> None:
        if not isinstance(runtime_data, dict):
            return
        array = runtime_data.get("array")
        if array is not None and hasattr(target.mappable, "set_array"):
            target.mappable.set_array(array)
        colormap = runtime_data.get("cmap")
        if colormap is not None:
            apply_color_map_spec(target.mappable, colormap)

    def apply_role_data(
        self,
        data: dict[str, Any],
        *,
        drawable: Field2DData | None = None,
    ):
        return self.apply_mutation(
            ComponentMutation(
                self.component_id,
                data=data,
                runtime_data=(
                    drawable if drawable is not None else KEEP_RUNTIME_DATA
                ),
            )
        )


class PseudocolorController(Field2DController):
    """Controller for Axes.pcolormesh pseudocolor charts."""

    ROLES = frozenset({ComponentRole.PSEUDOCOLOR})
    REBUILD_KEYS = frozenset(
        {"colormap", "shading", "edgecolor", "linewidth", "antialiased"}
    )
    PROPERTY_SPECS = _COMMON_FIELD_PROPERTIES + (
        PropertySpec(
            "shading",
            str,
            "auto",
            editor=EditorKind.ENUM,
            choices=PSEUDOCOLOR_SHADING_CHOICES,
        ),
        PropertySpec(
            "edgecolor",
            dict,
            deepcopy(DEFAULT_GRID_EDGE),
            editor=EditorKind.GRID_EDGE_SPEC,
            normalizer=normalize_grid_edge_spec,
        ),
        PropertySpec(
            "linewidth",
            float,
            0.0,
            validator=_nonnegative,
            editor=EditorKind.NUMBER,
            minimum=0.0,
        ),
        PropertySpec("antialiased", bool, False, editor=EditorKind.BOOL, advanced=True),
    )


class HeatmapController(Field2DController):
    """Controller for Axes.imshow heatmap charts."""

    ROLES = frozenset({ComponentRole.HEATMAP})
    REBUILD_KEYS = frozenset({"colormap"})
    PROPERTY_SPECS = _COMMON_FIELD_PROPERTIES + (
        PropertySpec(
            "interpolation",
            str,
            "antialiased",
            editor=EditorKind.ENUM,
            choices=IMAGE_INTERPOLATION_CHOICES,
        ),
        PropertySpec(
            "interpolation_stage",
            str,
            "data",
            editor=EditorKind.ENUM,
            choices=INTERPOLATION_STAGE_CHOICES,
            advanced=True,
        ),
        PropertySpec("resample", bool, True, editor=EditorKind.BOOL),
        PropertySpec("filternorm", bool, True, editor=EditorKind.BOOL, advanced=True),
        PropertySpec(
            "filterrad",
            float,
            4.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            advanced=True,
        ),
    )

    def _write_property(
        self,
        target: Field2DRuntime,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        image = target.primary
        if spec.key == "interpolation" and image is not None:
            image.set_interpolation(value)
            return
        if spec.key == "interpolation_stage" and image is not None:
            image.set_interpolation_stage(value)
            return
        if spec.key == "resample" and image is not None:
            image.set_resample(value)
            return
        if spec.key == "filternorm" and image is not None:
            image.set_filternorm(value)
            return
        if spec.key == "filterrad" and image is not None:
            image.set_filterrad(value)
            return
        super()._write_property(target, spec, value)


class ContourController(Field2DController):
    """Controller for Axes.contour / contourf charts."""

    ROLES = frozenset({ComponentRole.CONTOUR})
    REBUILD_KEYS = frozenset(
        {
            "colormap",
            "mode",
            "levels",
            "corner_mask",
            "extend",
            "algorithm",
            "nchunk",
            "antialiased",
            "linewidth",
            "linestyle",
            "negative_linestyle",
            "labels",
        }
    )
    PROPERTY_SPECS = _COMMON_FIELD_PROPERTIES + (
        PropertySpec(
            "mode",
            str,
            "filled",
            editor=EditorKind.ENUM,
            choices=CONTOUR_MODE_CHOICES,
        ),
        PropertySpec(
            "levels",
            dict,
            deepcopy(DEFAULT_CONTOUR_LEVELS),
            editor=EditorKind.CONTOUR_LEVELS_SPEC,
            normalizer=normalize_contour_levels_spec,
        ),
        PropertySpec("corner_mask", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "extend",
            str,
            "neither",
            editor=EditorKind.ENUM,
            choices=CONTOUR_EXTEND_CHOICES,
        ),
        PropertySpec(
            "algorithm",
            str,
            "mpl2014",
            editor=EditorKind.ENUM,
            choices=CONTOUR_ALGORITHM_CHOICES,
            advanced=True,
        ),
        PropertySpec(
            "nchunk",
            int,
            0,
            editor=EditorKind.INT,
            minimum=0,
            advanced=True,
        ),
        PropertySpec("antialiased", bool, True, editor=EditorKind.BOOL, advanced=True),
        PropertySpec(
            "linewidth",
            float,
            1.0,
            validator=_nonnegative,
            editor=EditorKind.NUMBER,
            minimum=0.0,
        ),
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "-"},
            editor=EditorKind.LINE_PATTERN,
            normalizer=normalize_line_pattern,
        ),
        PropertySpec(
            "negative_linestyle",
            dict,
            {"kind": "preset", "value": "dashed"},
            editor=EditorKind.LINE_PATTERN,
            normalizer=normalize_line_pattern,
        ),
        PropertySpec(
            "labels",
            dict,
            deepcopy(DEFAULT_CONTOUR_LABELS),
            editor=EditorKind.CONTOUR_LABEL_SPEC,
            normalizer=normalize_contour_label_spec,
        ),
    )
