"""Collection, reference-guide, and Scatter Controllers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
from matplotlib import colors as mcolors
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PathCollection, PolyCollection
from matplotlib.markers import MarkerStyle

from mygui.database import DataPreprocessSpec
from mygui.figuremodify.matplotlib_adapter import (
    copy_colormap,
)
from mygui.figuremodify.reference_marks_data import merged_reference_positions

from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    EditorKind,
    PropertySpec,
    RestorePhase,
    ScatterData,
    UpdateImpact,
    XYData,
)
from ..property_values import (
    DEFAULT_NORM,
    build_norm,
    map_scatter_sizes,
    marker_value,
    normalize_line_pattern,
    normalize_scatter_color_map,
    normalize_scatter_size_map,
)
from ._helpers import (
    _nonnegative,
    _optional_text,
    _url_sequence,
    _line_pattern,
    _marker_spec,
    _ARTIST_EXPORT_PROPERTIES,
    _normalize_color,
    _read_color,
    normalize_linestyle,
    normalize_reference_positions,
    complete_reference_marks_data,
    normalize_reference_marks_data,
    reflection_placement_is_automatic,
    _column_reference,
    _exact_data_fields,
)
from .lines import LineController

class CollectionController(ComponentController[Any]):
    """Coordinate state changes for collection components."""

    CAPABILITIES = frozenset({"collection"})


class ReferenceMarksController(CollectionController):
    """Coordinate one persisted reflection set and one LineCollection."""

    KIND = ComponentKind.REFERENCE_MARKS
    ROLES = frozenset({ComponentRole.REFLECTION_POSITIONS})
    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    PROPERTY_SPECS = (
        PropertySpec("label", str, "", editor=EditorKind.TEXT),
        PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "baseline",
            float,
            0.08,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.005,
            decimals=4,
        ),
        PropertySpec(
            "height",
            float,
            0.025,
            validator=lambda value: value > 0.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.005,
            decimals=9,
        ),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor=EditorKind.COLOR,
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "linewidth",
            float,
            0.8,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            step=0.1,
            decimals=3,
        ),
        PropertySpec(
            "linestyle",
            str,
            "-",
            editor=EditorKind.LINE_STYLE,
            normalizer=normalize_linestyle,
        ),
        PropertySpec(
            "alpha",
            float,
            1.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=3,
        ),
        PropertySpec("zorder", float, 2.0, editor=EditorKind.NUMBER),
        PropertySpec("clip_on", bool, True, editor=EditorKind.BOOL),
    )
    CAPABILITIES = CollectionController.CAPABILITIES | frozenset(
        {
            "reference_marks",
            "reflection_positions",
            "data",
            "data_reference",
            "auto_refresh",
        }
    )
    DELETE_IMPACTS = UpdateImpact.REDRAW

    def __init__(self, state: ComponentState, **kwargs: Any) -> None:
        state = state.clone(data=complete_reference_marks_data(state.data))
        super().__init__(state, **kwargs)
        self._table_repository = None
        self._table_project_id = None

    def bind_table(self, repository, project_id) -> None:
        """Attach the shared TableRepository used to resolve position_ref."""

        self._table_repository = repository
        self._table_project_id = str(project_id) if project_id else None

    @staticmethod
    def segments_for(
        positions: Any,
        baseline: float,
        height: float,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Build public LineCollection segments without sorting or deduping."""

        values = normalize_reference_positions(positions)
        start = float(baseline)
        stop = start + float(height)
        return [((position, start), (position, stop)) for position in values]

    def resolve_target(self) -> LineCollection:
        """Resolve and verify the exact Matplotlib target type."""

        target = super().resolve_target()
        if not isinstance(target, LineCollection):
            raise ComponentValidationError(
                "Reference Marks target must be a Matplotlib LineCollection."
            )
        return target

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Route state-owned geometry/style fields through one full mutation."""

        if (
            key == "baseline"
            and reflection_placement_is_automatic(
                self.state.data.get("placement")
            )
        ):
            return ComponentChange(
                self.component_id,
                "baseline",
                self.state,
                self.state,
                ChangeStatus.REJECTED,
                message=(
                    "Automatic Reflection baseline is read-only. Convert to "
                    "fixed position to edit it."
                ),
            )
        if key in {"baseline", "height", "linestyle"}:
            return self.apply_mutation(
                ComponentMutation(
                    self.component_id,
                    properties={key: value},
                )
            )
        return super().set_property(key, value)

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector != {"object_id": state.id}:
            raise ComponentValidationError(
                "Reference Marks selector requires only its stable object_id."
            )
        baseline = float(state.properties["baseline"])
        height = float(state.properties["height"])
        if baseline + height > 1.0:
            raise ComponentValidationError(
                "Reference Marks baseline plus height must not exceed 1."
            )

    def _validate_data(self, state: ComponentState) -> None:
        normalize_reference_marks_data(state.data)

    def _properties_require_data_apply(self, property_patch: dict[str, Any]) -> bool:
        return bool({"baseline", "height"} & set(property_patch))

    def _read_property(
        self,
        target: LineCollection,
        spec: PropertySpec,
    ) -> Any:
        if spec.key in {"baseline", "height", "linestyle"}:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        if spec.key == "color":
            colors = target.get_colors()
            if len(colors):
                saved = self._state.properties.get("color")
                if saved is not None:
                    try:
                        if np.allclose(
                            mcolors.to_rgba(saved)[:3],
                            tuple(colors[0])[:3],
                        ):
                            return _normalize_color(saved)
                    except (TypeError, ValueError):
                        pass
                return mcolors.to_hex(tuple(colors[0]), keep_alpha=False)
            return str(self._state.properties.get("color", "#000000"))
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
        return super()._read_property(target, spec)

    def _write_property(
        self,
        target: LineCollection,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        if spec.key in {"baseline", "height"}:
            geometry = deepcopy(self._state.properties)
            geometry[spec.key] = float(value)
            xs = [
                float(segment[0][0])
                for segment in target.get_segments()
            ]
            target.set_segments(
                self.segments_for(
                    xs,
                    geometry["baseline"],
                    geometry["height"],
                )
            )
            return
        if spec.key == "color":
            target.set_color(value)
            return
        if spec.key == "linewidth":
            target.set_linewidth(float(value))
            return
        if spec.key == "linestyle":
            target.set_linestyle(value)
            return
        super()._write_property(target, spec, value)

    def _apply_data(self, target: LineCollection, state: ComponentState) -> None:
        merged = merged_reference_positions(
            getattr(self, "_table_repository", None),
            getattr(self, "_table_project_id", None),
            state.data["positions"],
            state.data.get("position_ref"),
        )
        target.set_segments(
            self.segments_for(
                merged,
                state.properties["baseline"],
                state.properties["height"],
            )
        )

    def _capture_runtime_data(self, target: LineCollection) -> Any:
        return tuple(
            tuple(tuple(float(value) for value in point) for point in segment)
            for segment in target.get_segments()
        )

    def _restore_runtime_data(
        self,
        target: LineCollection,
        runtime_data: Any,
    ) -> None:
        target.set_segments(runtime_data)

    def _validate_runtime_data(
        self,
        target: LineCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        del target, state
        if runtime_data is None:
            raise ComponentValidationError(
                "Reference Marks runtime data must be a segment sequence."
            )

    def _apply_runtime_data(
        self,
        target: LineCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)
        target.set_segments(runtime_data)

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return UpdateImpact.REDRAW

    def _runtime_data_is_empty(
        self,
        target: LineCollection,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del target, state
        return not runtime_data

    def _restore_transaction_snapshot(
        self,
        snapshot: tuple[ComponentState, Any, dict[str, Any]],
    ) -> None:
        """Restore state-owned geometry before replaying target properties."""

        self._state = snapshot[0].clone()
        super()._restore_transaction_snapshot(snapshot)

    def _is_empty(
        self,
        target: LineCollection,
        state: ComponentState,
    ) -> bool:
        del target
        return (
            not state.data["positions"]
            and state.data.get("position_ref") is None
        )

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        del before, after
        return UpdateImpact.REDRAW


class _ReferenceGuideController(CollectionController):
    """Share strict state, transform, and rollback behavior for guides."""

    RESTORE_PHASE = RestorePhase.DYNAMIC
    DELETION_POLICY = DeletionPolicy.REMOVE
    DELETE_IMPACTS = UpdateImpact.REDRAW
    CAPABILITIES = CollectionController.CAPABILITIES | frozenset(
        {"reference_guide"}
    )
    GEOMETRY_KEYS = frozenset({"orientation", "span_start", "span_end"})

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Route geometry changes through one complete state mutation."""

        if key in self.GEOMETRY_KEYS:
            return self.apply_mutation(
                ComponentMutation(
                    self.component_id,
                    properties={key: value},
                    data=self._state.data,
                )
            )
        return super().set_property(key, value)

    def _validate_candidate(self, state: ComponentState) -> None:
        if state.selector != {"object_id": state.id}:
            raise ComponentValidationError(
                "Reference Guide selector requires only its stable object_id."
            )
        start = float(state.properties["span_start"])
        end = float(state.properties["span_end"])
        if not start < end:
            raise ComponentValidationError(
                "Reference Guide span_start must be less than span_end."
            )

    @staticmethod
    def _transform_for(target, orientation: str):
        axes = target.axes
        if not isinstance(axes, Axes):
            raise ComponentValidationError(
                "Reference Guide target must be attached to an ordinary Axes."
            )
        if orientation == "vertical":
            return axes.get_xaxis_transform()
        return axes.get_yaxis_transform()

    def _read_property(self, target, spec: PropertySpec) -> Any:
        if spec.key in self.GEOMETRY_KEYS or spec.key == "linestyle":
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        return super()._read_property(target, spec)

    def _write_property(self, target, spec: PropertySpec, value: Any) -> None:
        if spec.key in self.GEOMETRY_KEYS:
            # Geometry and the blended transform are rebuilt together in
            # ``_apply_data`` from the already validated complete candidate.
            return
        if spec.key == "linewidth":
            target.set_linewidth(float(value))
            return
        if spec.key == "linestyle":
            target.set_linestyle(value)
            return
        super()._write_property(target, spec, value)

    def _restore_transaction_snapshot(
        self,
        snapshot: tuple[ComponentState, Any, dict[str, Any]],
    ) -> None:
        """Restore state-owned geometry before replaying target properties."""

        self._state = snapshot[0].clone()
        super()._restore_transaction_snapshot(snapshot)

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        del before, after
        return UpdateImpact.REDRAW


class ReferenceLineController(_ReferenceGuideController):
    """Coordinate one constant Reference Line and one LineCollection."""

    KIND = ComponentKind.REFERENCE_GUIDE
    ROLES = frozenset({ComponentRole.REFERENCE_LINE})
    GEOMETRY_KEYS = _ReferenceGuideController.GEOMETRY_KEYS | frozenset(
        {"value"}
    )
    PROPERTY_SPECS = (
        PropertySpec("label", str, "", editor=EditorKind.TEXT),
        PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "orientation",
            str,
            "vertical",
            editor=EditorKind.ENUM,
            choices=("vertical", "horizontal"),
        ),
        PropertySpec("value", float, 0.0, editor=EditorKind.NUMBER),
        PropertySpec(
            "span_start",
            float,
            0.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=4,
            advanced=True,
        ),
        PropertySpec(
            "span_end",
            float,
            1.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=4,
            advanced=True,
        ),
        PropertySpec(
            "color",
            str,
            "#000000",
            editor=EditorKind.COLOR,
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "linewidth",
            float,
            0.8,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            step=0.1,
            decimals=3,
        ),
        PropertySpec(
            "linestyle",
            str,
            "-",
            editor=EditorKind.LINE_STYLE,
            normalizer=normalize_linestyle,
        ),
        PropertySpec(
            "alpha",
            float,
            1.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=3,
        ),
        PropertySpec("zorder", float, 2.0, editor=EditorKind.NUMBER),
        PropertySpec("clip_on", bool, True, editor=EditorKind.BOOL),
    )
    CAPABILITIES = _ReferenceGuideController.CAPABILITIES | frozenset(
        {"reference_line"}
    )

    @staticmethod
    def segment_for(properties: dict[str, Any]):
        """Return the exact blended-coordinate segment for one line."""

        value = float(properties["value"])
        start = float(properties["span_start"])
        end = float(properties["span_end"])
        if properties["orientation"] == "vertical":
            return ((value, start), (value, end))
        return ((start, value), (end, value))

    def resolve_target(self) -> LineCollection:
        target = super().resolve_target()
        if not isinstance(target, LineCollection):
            raise ComponentValidationError(
                "Reference Line target must be a Matplotlib LineCollection."
            )
        return target

    def _read_property(
        self,
        target: LineCollection,
        spec: PropertySpec,
    ) -> Any:
        if spec.key == "color":
            colors = target.get_colors()
            if len(colors):
                saved = self._state.properties.get("color")
                if saved is not None:
                    try:
                        if np.allclose(
                            mcolors.to_rgba(saved)[:3],
                            tuple(colors[0])[:3],
                        ):
                            return _normalize_color(saved)
                    except (TypeError, ValueError):
                        pass
                return mcolors.to_hex(tuple(colors[0]), keep_alpha=False)
            return str(self._state.properties.get("color", "#000000"))
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
        return super()._read_property(target, spec)

    def _write_property(
        self,
        target: LineCollection,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        if spec.key == "color":
            target.set_color(value)
            return
        super()._write_property(target, spec, value)

    def _apply_data(
        self,
        target: LineCollection,
        state: ComponentState,
    ) -> None:
        target.set_transform(
            self._transform_for(target, state.properties["orientation"])
        )
        target.set_segments([self.segment_for(state.properties)])

    def _capture_runtime_data(self, target: LineCollection) -> Any:
        return tuple(
            tuple(tuple(float(value) for value in point) for point in segment)
            for segment in target.get_segments()
        )

    def _restore_runtime_data(
        self,
        target: LineCollection,
        runtime_data: Any,
    ) -> None:
        target.set_segments(runtime_data)


class ReferenceBandController(_ReferenceGuideController):
    """Coordinate one constant Reference Band and one PolyCollection."""

    KIND = ComponentKind.REFERENCE_GUIDE
    ROLES = frozenset({ComponentRole.REFERENCE_BAND})
    GEOMETRY_KEYS = _ReferenceGuideController.GEOMETRY_KEYS | frozenset(
        {"lower", "upper"}
    )
    PROPERTY_SPECS = (
        PropertySpec("label", str, "", editor=EditorKind.TEXT),
        PropertySpec("visible", bool, True, editor=EditorKind.BOOL),
        PropertySpec(
            "orientation",
            str,
            "vertical",
            editor=EditorKind.ENUM,
            choices=("vertical", "horizontal"),
        ),
        PropertySpec("lower", float, 0.0, editor=EditorKind.NUMBER),
        PropertySpec("upper", float, 1.0, editor=EditorKind.NUMBER),
        PropertySpec(
            "span_start",
            float,
            0.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=4,
            advanced=True,
        ),
        PropertySpec(
            "span_end",
            float,
            1.0,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=4,
            advanced=True,
        ),
        PropertySpec(
            "facecolor",
            str,
            "#B0B0B0",
            editor=EditorKind.COLOR,
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "edgecolor",
            str,
            "#000000",
            editor=EditorKind.COLOR,
            normalizer=_normalize_color,
        ),
        PropertySpec(
            "linewidth",
            float,
            0.8,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            step=0.1,
            decimals=3,
        ),
        PropertySpec(
            "linestyle",
            str,
            "-",
            editor=EditorKind.LINE_STYLE,
            normalizer=normalize_linestyle,
        ),
        PropertySpec(
            "alpha",
            float,
            0.25,
            editor=EditorKind.NUMBER,
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=3,
        ),
        PropertySpec("zorder", float, 1.5, editor=EditorKind.NUMBER),
        PropertySpec("clip_on", bool, True, editor=EditorKind.BOOL),
    )
    CAPABILITIES = _ReferenceGuideController.CAPABILITIES | frozenset(
        {"reference_band"}
    )

    def _validate_candidate(self, state: ComponentState) -> None:
        super()._validate_candidate(state)
        if not float(state.properties["lower"]) < float(
            state.properties["upper"]
        ):
            raise ComponentValidationError(
                "Reference Band lower must be less than upper."
            )

    @staticmethod
    def polygon_for(properties: dict[str, Any]):
        """Return the exact blended-coordinate polygon for one band."""

        lower = float(properties["lower"])
        upper = float(properties["upper"])
        start = float(properties["span_start"])
        end = float(properties["span_end"])
        if properties["orientation"] == "vertical":
            return (
                (lower, start),
                (upper, start),
                (upper, end),
                (lower, end),
            )
        return (
            (start, lower),
            (end, lower),
            (end, upper),
            (start, upper),
        )

    def resolve_target(self) -> PolyCollection:
        target = super().resolve_target()
        if not isinstance(target, PolyCollection):
            raise ComponentValidationError(
                "Reference Band target must be a Matplotlib PolyCollection."
            )
        return target

    def _read_color(self, target: PolyCollection, key: str) -> str:
        colors = (
            target.get_facecolors()
            if key == "facecolor"
            else target.get_edgecolors()
        )
        saved = self._state.properties.get(key)
        if len(colors):
            if saved is not None:
                try:
                    if np.allclose(
                        mcolors.to_rgba(saved)[:3],
                        tuple(colors[0])[:3],
                    ):
                        return _normalize_color(saved)
                except (TypeError, ValueError):
                    pass
            return mcolors.to_hex(tuple(colors[0]), keep_alpha=False)
        return str(saved or "#000000")

    def _read_property(
        self,
        target: PolyCollection,
        spec: PropertySpec,
    ) -> Any:
        if spec.key in {"facecolor", "edgecolor"}:
            return self._read_color(target, spec.key)
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
        return super()._read_property(target, spec)

    def _write_property(
        self,
        target: PolyCollection,
        spec: PropertySpec,
        value: Any,
    ) -> None:
        if spec.key == "facecolor":
            target.set_facecolor(value)
            return
        if spec.key == "edgecolor":
            target.set_edgecolor(value)
            return
        super()._write_property(target, spec, value)

    def _apply_data(
        self,
        target: PolyCollection,
        state: ComponentState,
    ) -> None:
        target.set_transform(
            self._transform_for(target, state.properties["orientation"])
        )
        target.set_verts([self.polygon_for(state.properties)])

    def _capture_runtime_data(self, target: PolyCollection) -> Any:
        return tuple(
            tuple(tuple(float(value) for value in point) for point in path.vertices)
            for path in target.get_paths()
        )

    def _restore_runtime_data(
        self,
        target: PolyCollection,
        runtime_data: Any,
    ) -> None:
        target.set_verts(runtime_data)


class ScatterController(CollectionController):
    """Coordinate state changes for scatter components."""

    KIND = ComponentKind.SCATTER
    RESTORE_PHASE = RestorePhase.DYNAMIC
    ROLES = frozenset({ComponentRole.SCATTER})
    DELETION_POLICY = DeletionPolicy.REMOVE
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
            dict,
            {"kind": "symbol", "value": "o"},
            editor="marker_spec",
            normalizer=_marker_spec,
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
        PropertySpec(
            "linestyle",
            dict,
            {"kind": "preset", "value": "None"},
            editor="line_pattern",
            normalizer=_line_pattern,
        ),
        PropertySpec("hatch", str, None, editor="text", allow_none=True, normalizer=_optional_text),
        PropertySpec(
            "capstyle", str, None, editor="combo", allow_none=True,
            choices=(None, "butt", "projecting", "round"),
        ),
        PropertySpec(
            "joinstyle", str, None, editor="combo", allow_none=True,
            choices=(None, "miter", "round", "bevel"),
        ),
        PropertySpec("antialiased", bool, True, editor="check", advanced=True),
        PropertySpec(
            "urls",
            tuple,
            (),
            editor="string_list",
            getter="get_urls",
            setter="set_urls",
            normalizer=_url_sequence,
            advanced=True,
        ),
        PropertySpec(
            "color_mapping",
            dict,
            {
                "enabled": False,
                "cmap": "viridis",
                "norm": deepcopy(DEFAULT_NORM),
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
            editor="scatter_color_map",
            normalizer=normalize_scatter_color_map,
        ),
        PropertySpec(
            "size_mapping",
            dict,
            {"enabled": False, "input": None, "output": [12.0, 120.0], "clamp": True},
            editor="scatter_size_map",
            normalizer=normalize_scatter_size_map,
        ),
    ) + _ARTIST_EXPORT_PROPERTIES
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
        if state.data and "preprocess" not in state.data:
            data = deepcopy(state.data)
            data["preprocess"] = DataPreprocessSpec().to_dict()
            state = state.clone(data=data)
        if state.data:
            data = deepcopy(state.data)
            data.setdefault("color_ref", None)
            data.setdefault("size_ref", None)
            state = state.clone(data=data)
        self._marker_value = deepcopy(state.properties.get("marker", {"kind": "symbol", "value": "o"}))
        super().__init__(state, **kwargs)

    def _validate_data(self, state: ComponentState) -> None:
        # A free-standing Matplotlib collection can be registered without
        # a table source. Project-managed scatter components always retain
        # their two stable column references.
        if not state.data:
            return
        _exact_data_fields(
            state,
            {"x_ref", "y_ref", "color_ref", "size_ref", "preprocess"},
        )
        _column_reference(state.data["x_ref"], "x_ref")
        _column_reference(state.data["y_ref"], "y_ref")
        for key in ("color_ref", "size_ref"):
            if state.data[key] is not None:
                _column_reference(state.data[key], key)
        DataPreprocessSpec.from_dict(state.data["preprocess"])
        if state.properties["color_mapping"]["enabled"] and state.data["color_ref"] is None:
            raise ComponentValidationError("Scatter color mapping requires color_ref.")
        if state.properties["size_mapping"]["enabled"] and state.data["size_ref"] is None:
            raise ComponentValidationError("Scatter size mapping requires size_ref.")

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
            return deepcopy(self._marker_value)
        if spec.key == "linewidth":
            widths = target.get_linewidths()
            return float(widths[0]) if len(widths) else 0.0
        if spec.key == "linestyle":
            return deepcopy(self._state.properties.get(spec.key, spec.default))
        if spec.key in {"color_mapping", "size_mapping"}:
            return deepcopy(self._state.properties.get(spec.key, spec.default))
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
            marker = MarkerStyle(marker_value(value))
            path = marker.get_path().transformed(marker.get_transform())
            target.set_paths([path])
            self._marker_value = deepcopy(value)
            return
        if spec.key == "linewidth":
            target.set_linewidths([value])
            return
        if spec.key == "linestyle":
            pattern = normalize_line_pattern(value)
            linestyle = pattern["value"] if pattern["kind"] == "preset" else (pattern["offset"], pattern["dashes"])
            target.set_linestyle(linestyle)
            return
        if spec.key == "capstyle" and value is None:
            target._capstyle = None
            return
        if spec.key == "joinstyle" and value is None:
            target._joinstyle = None
            return
        if spec.key in {"color_mapping", "size_mapping"}:
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
        if not isinstance(runtime_data, (XYData, ScatterData)):
            raise ComponentValidationError(
                "Scatter runtime data must be XYData."
            )
        self._validate_xy_values(runtime_data.x, runtime_data.y)
        length = len(np.asarray(runtime_data.x))
        if isinstance(runtime_data, ScatterData):
            for name, values in (("colors", runtime_data.colors), ("sizes", runtime_data.sizes)):
                if values is not None and len(np.asarray(values)) != length:
                    raise ComponentValidationError(
                        f"Scatter {name} must match X/Y length."
                    )

    def _capture_runtime_data(
        self,
        target: PathCollection,
    ) -> dict[str, Any]:
        offsets = np.asarray(target.get_offsets()).copy()
        return {
            "offsets": offsets,
            "array": (
                None
                if target.get_array() is None
                else np.ma.asarray(target.get_array()).copy()
            ),
            "sizes": np.asarray(target.get_sizes()).copy(),
            "facecolors": np.asarray(target.get_facecolors()).copy(),
            "edgecolors": np.asarray(target.get_edgecolors()).copy(),
            "cmap": target.get_cmap(),
            "norm": target.norm,
        }

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
        if isinstance(runtime_data, ScatterData):
            color_spec = state.properties["color_mapping"]
            if color_spec["enabled"] and runtime_data.colors is not None:
                cmap = copy_colormap(color_spec["cmap"])
                cmap.set_bad(color_spec["bad"])
                if color_spec["under"] is not None:
                    cmap.set_under(color_spec["under"])
                if color_spec["over"] is not None:
                    cmap.set_over(color_spec["over"])
                target.set_cmap(cmap)
                target.set_norm(build_norm(color_spec["norm"]))
                target.set_array(np.asarray(runtime_data.colors, dtype=float))
            else:
                target.set_array(None)
                target.set_facecolor(state.properties["color"])
            if state.properties["size_mapping"]["enabled"] and runtime_data.sizes is not None:
                target.set_sizes(map_scatter_sizes(runtime_data.sizes, state.properties["size_mapping"]))
            else:
                target.set_sizes([state.properties["size"]])

    def _restore_runtime_data(
        self,
        target: PathCollection,
        runtime_data: Any,
    ) -> None:
        if isinstance(runtime_data, dict):
            target.set_offsets(runtime_data["offsets"])
            target.set_cmap(runtime_data["cmap"])
            target.set_norm(runtime_data["norm"])
            target.set_array(runtime_data["array"])
            target.set_sizes(runtime_data["sizes"])
            target.set_facecolors(runtime_data["facecolors"])
            target.set_edgecolors(runtime_data["edgecolors"])
            return
        if not isinstance(runtime_data, (XYData, ScatterData)):
            return
        x_values = np.asarray(runtime_data.x)
        y_values = np.asarray(runtime_data.y)
        target.set_offsets(
            np.column_stack((x_values, y_values))
            if len(x_values)
            else np.empty((0, 2))
        )
        if isinstance(runtime_data, ScatterData):
            target.set_array(None if runtime_data.colors is None else np.asarray(runtime_data.colors))
            target.set_sizes(np.asarray(runtime_data.sizes) if runtime_data.sizes is not None else [])

    def _restore_transaction_snapshot(self, snapshot) -> None:
        super()._restore_transaction_snapshot(snapshot)
        self._restore_runtime_data(self.resolve_target(), snapshot[1])

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

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        collection = target if target is not None else self.resolve_target()
        axes = getattr(collection, "axes", None)
        if UpdateImpact.RELIM in impacts and isinstance(axes, Axes):
            axes.relim()
            if len(collection.get_offsets()):
                axes.update_datalim(collection.get_datalim(axes.transData))
            impacts &= ~UpdateImpact.RELIM
        super()._request_updates(impacts, collection)

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
        drawable: XYData | ScatterData,
    ) -> ComponentChange:
        """Apply role data."""

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
        """Set xy data."""

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
