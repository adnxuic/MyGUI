"""Application services for Controller-managed Matplotlib components.

Controllers remain independent from Qt and the table repository.  These
services adapt application data, fitting and render validation to the atomic
Controller mutation API without becoming a second state store.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
import warnings
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure

from mygui import tex_config
from mygui.font_diagnostics import (
    capture_font_diagnostics,
    normalize_font_diagnostic,
)
from mygui.database import (
    ColumnRef,
    DataPreprocessSpec,
    PreprocessedPair,
    TableRepository,
    resolve_preprocessed_pair,
)
from mygui.database.interpolate_func import interpolate_curve
from mygui.database.fit_result import (
    normalize_fit_options_for_storage,
    normalize_fit_result_for_storage,
)
from mygui.database.safe_expression import (
    GENERATED_FIT_EXPRESSION_LIMITS,
    evaluate_curve_expression,
)
from mygui.figuremodify.components import (
    AxesController,
    ChangeStatus,
    CONTROLLER_TYPES,
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentNotice,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    ColorbarController,
    DataPlotController,
    DeletionPolicy,
    FitCurveController,
    FitEngine,
    FunctionCurveController,
    InterpolationController,
    LegendController,
    MessageLevel,
    ReferenceBandController,
    ReferenceLineController,
    ReferenceMarksController,
    ObserverFailure,
    ScatterController,
    ScatterData,
    TextController,
    UpdateImpact,
    XYData,
    normalize_reference_marks_data,
    reflection_placement_is_automatic,
)
from mygui.figuremodify.reference_marks_data import (
    between_table_range_extrema,
    merged_reference_positions,
)
from mygui.figuremodify.x_axis_tight import apply_tight_xlim
from mygui.figuremodify.y_axis_reserve import apply_y_lower_reserve
from mygui.figuremodify.components.property_values import (
    legend_anchor_value,
    legend_location_value,
)
from mygui.figuremodify.components.matplotlib_removal import MATPLOTLIB_REMOVAL
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
    PaletteSource,
    normalize_color,
)
from mygui.figuremodify.style_base.creation_defaults import resolve_style_palette


def _controller(
    registry: ComponentRegistry,
    value,
    expected_type=None,
):
    result = registry.get(value) if isinstance(value, str) else value
    if expected_type is not None and not isinstance(result, expected_type):
        raise TypeError(
            f"Expected {expected_type.__name__}, got {type(result).__name__}."
        )
    return result


def _rejected(controller, message: str) -> ComponentChange:
    state = controller.state
    return ComponentChange(
        controller.component_id,
        None,
        state,
        state,
        ChangeStatus.REJECTED,
        message=str(message),
    )


def _notices(
    change: ComponentChange,
    *notices: ComponentNotice,
) -> ComponentChange:
    return replace(
        change,
        notices=tuple(change.notices) + tuple(notices),
    )


def _warning(message: str) -> ComponentNotice:
    return ComponentNotice(MessageLevel.WARNING, message)


class ReferenceMarksService:
    """Create and edit one reflection set through one LineCollection."""

    def __init__(
        self,
        registry: ComponentRegistry,
        repository: TableRepository | None = None,
        project_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.project_id = project_id

    def _owner_axes(self, owner_axes_id: str) -> Axes:
        controller = self.registry.get(str(owner_axes_id))
        if controller.state.kind is not ComponentKind.AXES:
            raise ComponentValidationError(
                "Reference Marks owner must be an ordinary Axes component."
            )
        target = self.registry.resolve_target(controller.component_id)
        if not isinstance(target, Axes):
            raise ComponentValidationError(
                "Reference Marks owner target must be a Matplotlib Axes."
            )
        return target

    def _merged_positions(self, positions: Any, position_ref: Any) -> list[float]:
        return merged_reference_positions(
            self.repository,
            self.project_id,
            positions,
            position_ref,
        )

    @staticmethod
    def _data_y_to_axes_fraction(owner: Axes, value: float) -> float:
        transformed = np.asarray(
            owner.transLimits.transform([(0.0, float(value))]),
            dtype=float,
        ).reshape(-1, 2)
        fraction = float(transformed[0, 1])
        if not np.isfinite(fraction):
            raise ComponentValidationError(
                "Automatic Reflection placement could not convert data values "
                "to Axes coordinates."
            )
        return fraction

    def _ensure_owner_autoscale(self, owner: Axes, owner_axes_id: str) -> None:
        if not owner.get_autoscaley_on() or not owner.has_data():
            return
        owner.relim()
        # Matplotlib 3.9 Axes.relim() ignores Collections. Scatter offsets must
        # be folded back into dataLim so Observed Yobs participates in autoscale
        # before automatic Reflection placement.
        for controller in self.registry.query(kind=ComponentKind.SCATTER):
            if controller.state.parent_id != str(owner_axes_id):
                continue
            collection = controller.resolve_target()
            if collection is None:
                continue
            offsets = collection.get_offsets()
            if len(offsets) == 0:
                continue
            owner.update_datalim(collection.get_datalim(owner.transData))
        owner.autoscale_view()
        apply_tight_xlim(owner)
        apply_y_lower_reserve(owner)

    def compute_automatic_baseline(
        self,
        owner_axes_id: str,
        placement: Any,
        height: float,
    ) -> float:
        """Return the Axes-fraction baseline centered in the table-range gap."""

        owner = self._owner_axes(owner_axes_id)
        self._ensure_owner_autoscale(owner, owner_axes_id)
        lower_top_data, upper_bottom_data = between_table_range_extrema(
            self.repository,
            self.project_id,
            placement,
        )
        lower_top = self._data_y_to_axes_fraction(owner, lower_top_data)
        upper_bottom = self._data_y_to_axes_fraction(owner, upper_bottom_data)
        gap = upper_bottom - lower_top
        mark_height = float(height)
        if not np.isfinite(mark_height) or mark_height <= 0.0:
            raise ComponentValidationError(
                "Reflection height must be a positive finite number."
            )
        if gap + 1e-12 < mark_height:
            raise ComponentValidationError(
                "The gap between the residual and the main intensities is too "
                "small for the current Reflection height."
            )
        baseline = (lower_top + upper_bottom) / 2.0 - mark_height / 2.0
        if baseline < -1e-12 or baseline + mark_height > 1.0 + 1e-12:
            raise ComponentValidationError(
                "Automatic Reflection placement does not fit inside the Axes."
            )
        return float(max(0.0, min(baseline, 1.0 - mark_height)))

    def preflight(
        self,
        owner_axes_id: str,
        positions: Any,
        properties: dict[str, Any] | None = None,
        position_ref: Any = None,
        placement: Any = None,
    ) -> tuple[list[float], dict[str, str] | None, dict[str, Any], list[float], dict[str, Any]]:
        """Validate a complete candidate before creating runtime state."""

        self._owner_axes(owner_axes_id)
        specs = ReferenceMarksController.property_specs()
        requested = dict(properties or {})
        unknown = set(requested) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown Reference Marks properties: {sorted(unknown)!r}."
            )
        normalized = ReferenceMarksController.default_properties()
        normalized.update(
            {key: specs[key].normalize(value) for key, value in requested.items()}
        )
        data = normalize_reference_marks_data(
            {
                "positions": positions,
                "position_ref": position_ref,
                "placement": placement,
            }
        )
        if reflection_placement_is_automatic(data["placement"]):
            normalized["baseline"] = self.compute_automatic_baseline(
                owner_axes_id,
                data["placement"],
                normalized["height"],
            )
        merged = self._merged_positions(data["positions"], data["position_ref"])
        candidate = ComponentState(
            id="reference-marks-preflight",
            kind=ComponentKind.REFERENCE_MARKS,
            role=ComponentRole.REFLECTION_POSITIONS,
            parent_id=str(owner_axes_id),
            order=0,
            selector={"object_id": "reference-marks-preflight"},
            properties=normalized,
            data=data,
        )
        ReferenceMarksController(candidate)
        return (
            data["positions"],
            data["position_ref"],
            normalized,
            merged,
            data["placement"],
        )

    def create_runtime(
        self,
        owner_axes_id: str,
        positions: Any,
        properties: dict[str, Any] | None = None,
        position_ref: Any = None,
        placement: Any = None,
    ) -> tuple[
        LineCollection,
        list[float],
        dict[str, str] | None,
        dict[str, Any],
        dict[str, Any],
    ]:
        """Create exactly one staged LineCollection with a blended transform."""

        (
            normalized_positions,
            normalized_ref,
            normalized,
            merged,
            normalized_placement,
        ) = self.preflight(
            owner_axes_id,
            positions,
            properties,
            position_ref,
            placement,
        )
        owner = self._owner_axes(owner_axes_id)
        runtime = LineCollection(
            ReferenceMarksController.segments_for(
                merged,
                normalized["baseline"],
                normalized["height"],
            ),
            colors=[normalized["color"]],
            linewidths=[normalized["linewidth"]],
            linestyles=normalized["linestyle"],
            alpha=normalized["alpha"],
            visible=normalized["visible"],
            zorder=normalized["zorder"],
            clip_on=normalized["clip_on"],
            label=normalized["label"],
            transform=owner.get_xaxis_transform(),
        )
        try:
            owner.add_collection(runtime, autolim=False)
            if runtime.axes is not owner:
                raise ComponentValidationError(
                    "Matplotlib did not attach Reference Marks to its owner Axes."
                )
        except Exception:
            self.destroy_runtime(runtime)
            raise
        return (
            runtime,
            normalized_positions,
            normalized_ref,
            normalized,
            normalized_placement,
        )

    @staticmethod
    def destroy_runtime(runtime: LineCollection) -> None:
        """Remove a staged Reference Marks collection during rollback."""

        if not isinstance(runtime, LineCollection):
            return
        try:
            runtime.remove()
        except (RuntimeError, ValueError):
            pass

    @staticmethod
    def _verify_render(controller: ReferenceMarksController) -> None:
        runtime = controller.resolve_target()
        canvas = runtime.figure.canvas if runtime.figure is not None else None
        if canvas is not None:
            canvas.draw()

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply property edits and geometry as one verified transaction."""

        controller = _controller(
            self.registry,
            component,
            ReferenceMarksController,
        )
        patch = dict(properties)
        try:
            if reflection_placement_is_automatic(
                controller.state.data.get("placement")
            ):
                if "baseline" in patch:
                    return _rejected(
                        controller,
                        "Automatic Reflection baseline is read-only. Convert to "
                        "fixed position to edit it.",
                    )
                if "height" in patch:
                    patch["baseline"] = self.compute_automatic_baseline(
                        controller.state.parent_id,
                        controller.state.data.get("placement"),
                        patch["height"],
                    )
        except Exception as exc:
            return _rejected(controller, str(exc))
        batch = self.registry.apply_transaction(
            (
                ComponentMutation(
                    controller.component_id,
                    properties=patch,
                ),
            ),
            verifier=lambda: self._verify_render(controller),
        )
        if not batch.committed or not batch.changes:
            return _rejected(
                controller,
                batch.message or "Reference Marks render verification failed.",
            )
        return batch.changes[0]

    def update_data(
        self,
        component,
        positions: Any,
        position_ref: Any,
        placement: Any = None,
    ) -> ComponentChange:
        """Replace persisted positions, column ref, and placement."""

        controller = _controller(
            self.registry,
            component,
            ReferenceMarksController,
        )
        try:
            data = normalize_reference_marks_data(
                {
                    "positions": positions,
                    "position_ref": position_ref,
                    "placement": (
                        controller.state.data.get("placement")
                        if placement is None
                        else placement
                    ),
                }
            )
            properties = dict(controller.state.properties)
            if reflection_placement_is_automatic(data["placement"]):
                properties["baseline"] = self.compute_automatic_baseline(
                    controller.state.parent_id,
                    data["placement"],
                    properties["height"],
                )
            merged = self._merged_positions(data["positions"], data["position_ref"])
            runtime_data = ReferenceMarksController.segments_for(
                merged,
                properties["baseline"],
                properties["height"],
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        mutation_kwargs: dict[str, Any] = {
            "data": data,
            "runtime_data": runtime_data,
        }
        if properties["baseline"] != controller.state.properties["baseline"]:
            mutation_kwargs["properties"] = {"baseline": properties["baseline"]}
        batch = self.registry.apply_transaction(
            (
                ComponentMutation(
                    controller.component_id,
                    **mutation_kwargs,
                ),
            ),
            verifier=lambda: self._verify_render(controller),
        )
        if not batch.committed or not batch.changes:
            return _rejected(
                controller,
                batch.message or "Reference Marks render verification failed.",
            )
        return batch.changes[0]

    def update_positions(
        self,
        component,
        positions: Any,
    ) -> ComponentChange:
        """Replace only the authoritative ordered position sequence."""

        controller = _controller(
            self.registry,
            component,
            ReferenceMarksController,
        )
        return self.update_data(
            controller,
            positions,
            controller.state.data.get("position_ref"),
        )

    def convert_to_fixed_placement(self, component) -> ComponentChange:
        """Atomically store the current baseline and height as fixed placement."""

        controller = _controller(
            self.registry,
            component,
            ReferenceMarksController,
        )
        try:
            data = normalize_reference_marks_data(
                {
                    **controller.state.data,
                    "placement": {"kind": "fixed"},
                }
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        if data == controller.state.data:
            return ComponentChange(
                controller.component_id,
                None,
                controller.state,
                controller.state,
                ChangeStatus.NOOP,
            )
        return self.update_data(
            controller,
            data["positions"],
            data["position_ref"],
            data["placement"],
        )

    def refresh(
        self,
        component,
    ) -> ComponentChange:
        """Rebuild segments from persisted positions plus the live column."""

        controller = _controller(
            self.registry,
            component,
            ReferenceMarksController,
        )
        data = controller.state.data
        try:
            properties = dict(controller.state.properties)
            if reflection_placement_is_automatic(data.get("placement")):
                properties["baseline"] = self.compute_automatic_baseline(
                    controller.state.parent_id,
                    data.get("placement"),
                    properties["height"],
                )
            merged = self._merged_positions(
                data.get("positions", []),
                data.get("position_ref"),
            )
            runtime_data = ReferenceMarksController.segments_for(
                merged,
                properties["baseline"],
                properties["height"],
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        mutation_kwargs: dict[str, Any] = {"runtime_data": runtime_data}
        if properties["baseline"] != controller.state.properties["baseline"]:
            mutation_kwargs["properties"] = {"baseline": properties["baseline"]}
        batch = self.registry.apply_transaction(
            (
                ComponentMutation(
                    controller.component_id,
                    **mutation_kwargs,
                ),
            ),
            verifier=lambda: self._verify_render(controller),
        )
        if not batch.committed or not batch.changes:
            return _rejected(
                controller,
                batch.message or "Reference Marks render verification failed.",
            )
        return batch.changes[0]

    @staticmethod
    def _placement_refs(data: dict[str, Any]) -> set[ColumnRef]:
        refs: set[ColumnRef] = set()
        raw = data.get("position_ref")
        if raw is not None:
            try:
                refs.add(_column_ref(raw))
            except (TypeError, ValueError):
                pass
        placement = data.get("placement") or {}
        if placement.get("kind") != "between_table_ranges":
            return refs
        try:
            refs.add(_column_ref(placement.get("lower_ref")))
        except (TypeError, ValueError):
            pass
        for item in placement.get("upper_refs") or ():
            try:
                refs.add(_column_ref(item))
            except (TypeError, ValueError):
                continue
        return refs

    def refresh_affected(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> list[ComponentChange]:
        """Refresh Reflection Positions bound to changed Number columns."""

        changed = set(changed_columns)
        results: list[ComponentChange] = []
        with self.registry.batch_updates():
            for controller in self.registry.query(
                capabilities={"data_reference"}
            ):
                if not isinstance(controller, ReferenceMarksController):
                    continue
                if not self._placement_refs(controller.state.data).intersection(
                    changed
                ):
                    continue
                results.append(self.refresh(controller))
        return results


class ReferenceGuideService:
    """Create and edit constant Reference Lines and Bands transactionally."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def _owner_axes(self, owner_axes_id: str) -> Axes:
        controller = self.registry.get(str(owner_axes_id))
        if controller.state.kind is not ComponentKind.AXES:
            raise ComponentValidationError(
                "Reference Guide owner must be an ordinary Axes component."
            )
        target = self.registry.resolve_target(controller.component_id)
        if not isinstance(target, Axes):
            raise ComponentValidationError(
                "Reference Guide owner target must be a Matplotlib Axes."
            )
        return target

    def _preflight(
        self,
        owner_axes_id: str,
        controller_type,
        role: ComponentRole,
        properties: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self._owner_axes(owner_axes_id)
        specs = controller_type.property_specs()
        requested = dict(properties or {})
        unknown = set(requested) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown Reference Guide properties: {sorted(unknown)!r}."
            )
        normalized = controller_type.default_properties()
        normalized.update(
            {key: specs[key].normalize(value) for key, value in requested.items()}
        )
        candidate_id = f"{role.value}-preflight"
        candidate = ComponentState(
            id=candidate_id,
            kind=ComponentKind.REFERENCE_GUIDE,
            role=role,
            parent_id=str(owner_axes_id),
            order=0,
            selector={"object_id": candidate_id},
            properties=normalized,
            data={},
        )
        controller_type(candidate)
        return normalized

    def preflight_line(
        self,
        owner_axes_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a complete Reference Line candidate."""

        return self._preflight(
            owner_axes_id,
            ReferenceLineController,
            ComponentRole.REFERENCE_LINE,
            properties,
        )

    def preflight_band(
        self,
        owner_axes_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a complete Reference Band candidate."""

        return self._preflight(
            owner_axes_id,
            ReferenceBandController,
            ComponentRole.REFERENCE_BAND,
            properties,
        )

    def create_line_runtime(
        self,
        owner_axes_id: str,
        properties: dict[str, Any] | None = None,
    ) -> tuple[LineCollection, dict[str, Any]]:
        """Create one staged LineCollection without changing data limits."""

        normalized = self.preflight_line(owner_axes_id, properties)
        owner = self._owner_axes(owner_axes_id)
        runtime = LineCollection(
            [ReferenceLineController.segment_for(normalized)],
            colors=[normalized["color"]],
            linewidths=[normalized["linewidth"]],
            linestyles=normalized["linestyle"],
            alpha=normalized["alpha"],
            visible=normalized["visible"],
            zorder=normalized["zorder"],
            clip_on=normalized["clip_on"],
            label=normalized["label"],
            transform=(
                owner.get_xaxis_transform()
                if normalized["orientation"] == "vertical"
                else owner.get_yaxis_transform()
            ),
        )
        try:
            owner.add_collection(runtime, autolim=False)
            if runtime.axes is not owner:
                raise ComponentValidationError(
                    "Matplotlib did not attach Reference Line to its owner Axes."
                )
        except Exception:
            self.destroy_runtime(runtime)
            raise
        return runtime, normalized

    def create_band_runtime(
        self,
        owner_axes_id: str,
        properties: dict[str, Any] | None = None,
    ) -> tuple[PolyCollection, dict[str, Any]]:
        """Create one staged PolyCollection without changing data limits."""

        normalized = self.preflight_band(owner_axes_id, properties)
        owner = self._owner_axes(owner_axes_id)
        runtime = PolyCollection(
            [ReferenceBandController.polygon_for(normalized)],
            facecolors=[normalized["facecolor"]],
            edgecolors=[normalized["edgecolor"]],
            linewidths=[normalized["linewidth"]],
            linestyles=normalized["linestyle"],
            alpha=normalized["alpha"],
            visible=normalized["visible"],
            zorder=normalized["zorder"],
            clip_on=normalized["clip_on"],
            label=normalized["label"],
            transform=(
                owner.get_xaxis_transform()
                if normalized["orientation"] == "vertical"
                else owner.get_yaxis_transform()
            ),
        )
        try:
            owner.add_collection(runtime, autolim=False)
            if runtime.axes is not owner:
                raise ComponentValidationError(
                    "Matplotlib did not attach Reference Band to its owner Axes."
                )
        except Exception:
            self.destroy_runtime(runtime)
            raise
        return runtime, normalized

    @staticmethod
    def destroy_runtime(runtime) -> None:
        """Remove a staged guide Collection during rollback."""

        if not isinstance(runtime, (LineCollection, PolyCollection)):
            return
        try:
            runtime.remove()
        except (RuntimeError, ValueError):
            pass

    @staticmethod
    def verify_render(controller) -> None:
        """Render-probe a staged or edited guide before publication."""

        runtime = controller.resolve_target()
        canvas = runtime.figure.canvas if runtime.figure is not None else None
        if canvas is not None:
            canvas.draw()

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply geometry and style through one verified Registry mutation."""

        controller = _controller(self.registry, component)
        if not isinstance(
            controller,
            (ReferenceLineController, ReferenceBandController),
        ):
            raise TypeError(
                "Reference Guide edits require a Line or Band Controller."
            )
        batch = self.registry.apply_transaction(
            (
                ComponentMutation(
                    controller.component_id,
                    properties=dict(properties),
                    data={},
                ),
            ),
            verifier=lambda: self.verify_render(controller),
        )
        if not batch.committed or not batch.changes:
            return _rejected(
                controller,
                batch.message or "Reference Guide render verification failed.",
            )
        return batch.changes[0]

@dataclass(frozen=True, slots=True)
class ColorbarSourceResolution:
    """Validated source/owner targets for one Colorbar operation."""

    source_controller: ScatterController
    mappable: Any
    owner_axes_id: str
    owner_axes: Axes


class ColorbarSourceResolverRegistry:
    """Resolve scalar-mappable sources through exact component contracts."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry
        self._resolvers: dict[tuple[ComponentKind, ComponentRole], Callable] = {}

    def register(
        self,
        kind: ComponentKind,
        role: ComponentRole,
        resolver: Callable,
    ) -> None:
        key = (ComponentKind(kind), ComponentRole(role))
        if key in self._resolvers:
            raise ComponentValidationError(
                f"Duplicate Colorbar source resolver for {kind.value}/{role.value}."
            )
        if not callable(resolver):
            raise TypeError("Colorbar source resolver must be callable.")
        self._resolvers[key] = resolver

    def resolve(self, component) -> ColorbarSourceResolution:
        controller = _controller(self.registry, component)
        state = controller.state
        resolver = self._resolvers.get((state.kind, state.role))
        if resolver is None:
            raise ComponentValidationError(
                f"{state.kind.value}/{state.role.value} cannot be used as a "
                "Colorbar source."
            )
        return resolver(controller)


class ScatterColorbarSourceResolver:
    """First-party resolver for scalar-mapped Scatter components."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def __call__(self, component) -> ColorbarSourceResolution:
        controller = _controller(self.registry, component, ScatterController)
        state = controller.state
        mapping = state.properties.get("color_mapping", {})
        if not bool(mapping.get("enabled")):
            raise ComponentValidationError(
                "Scatter scalar color mapping must be enabled before adding a Colorbar."
            )
        # Existing-Figure discovery may register an external scalar mappable
        # without TableRepository data. Persisted/project-managed Scatter
        # sources always require a stable color_ref.
        if state.data and state.data.get("color_ref") is None:
            raise ComponentValidationError(
                "Scatter Colorbar sources require a valid color_ref."
            )
        mappable = controller.resolve_target()
        if getattr(mappable, "get_array", lambda: None)() is None:
            raise ComponentValidationError(
                "Scatter source is not an active Matplotlib ScalarMappable."
            )
        owner_axes_id = state.parent_id
        if owner_axes_id is None:
            raise ComponentValidationError("Scatter source has no owner Axes.")
        owner_axes = self.registry.resolve_target(owner_axes_id)
        if not isinstance(owner_axes, Axes) or getattr(mappable, "axes", None) is not owner_axes:
            raise ComponentValidationError(
                "Scatter source and owner Axes targets are inconsistent."
            )
        return ColorbarSourceResolution(
            controller,
            mappable,
            owner_axes_id,
            owner_axes,
        )


def production_colorbar_source_resolvers(
    registry: ComponentRegistry,
) -> ColorbarSourceResolverRegistry:
    """Build the closed first-party Colorbar source resolver registry."""

    resolvers = ColorbarSourceResolverRegistry(registry)
    resolvers.register(
        ComponentKind.SCATTER,
        ComponentRole.SCATTER,
        ScatterColorbarSourceResolver(registry),
    )
    return resolvers


class ColorbarService:
    """Create, rebuild, refresh, and inspect Colorbars transactionally."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        source_resolvers: ColorbarSourceResolverRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.source_resolvers = (
            source_resolvers or production_colorbar_source_resolvers(registry)
        )

    def dependents(self, source_component_id: str) -> tuple[ColorbarController, ...]:
        return tuple(
            controller
            for controller in self.registry.query(kind=ComponentKind.COLORBAR)
            if controller.state.data.get("source_component_id")
            == str(source_component_id)
        )

    def has_dependents(self, source_component_id: str) -> bool:
        return bool(self.dependents(source_component_id))

    def validate_source(
        self,
        owner_axes_id: str,
        source_component_id: str,
    ) -> ColorbarSourceResolution:
        """Resolve one eligible source before beginning a creation transaction."""

        source = self.source_resolvers.resolve(source_component_id)
        if source.owner_axes_id != str(owner_axes_id):
            raise ComponentValidationError(
                "Colorbar source must belong to the selected owner Axes."
            )
        if self.has_dependents(source_component_id):
            raise ComponentValidationError(
                "The selected Scatter already has a Colorbar."
            )
        return source

    def eligible_sources(self, owner_axes_id: str) -> tuple[ColorbarSourceResolution, ...]:
        existing = {
            controller.state.data["source_component_id"]
            for controller in self.registry.query(kind=ComponentKind.COLORBAR)
        }
        resolved = []
        for controller in self.registry.query(parent_id=owner_axes_id):
            if controller.component_id in existing:
                continue
            try:
                source = self.source_resolvers.resolve(controller)
            except (ComponentValidationError, TypeError):
                continue
            if source.owner_axes_id == owner_axes_id:
                resolved.append(source)
        return tuple(
            sorted(
                resolved,
                key=lambda item: (
                    item.source_controller.state.order,
                    item.source_controller.component_id,
                ),
            )
        )

    @staticmethod
    def source_preview(source: ColorbarSourceResolution) -> str:
        state = source.source_controller.state
        label = str(state.properties.get("label", "")).strip()
        return label or f"Scatter {state.id[:8]}"

    @staticmethod
    def _constructor_kwargs(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": properties["location"],
            "fraction": properties["fraction"],
            "shrink": properties["shrink"],
            "aspect": properties["aspect"],
            "pad": properties["pad"],
            "extend": properties["extend"],
            "spacing": properties["spacing"],
            "drawedges": properties["drawedges"],
            "ticklocation": properties["ticklocation"],
        }

    @staticmethod
    def _restore_owner(
        owner: Axes,
        active_position,
        original_position,
        subplotspec,
        anchor,
    ) -> None:
        if subplotspec is not None:
            owner.set_subplotspec(subplotspec)
        owner._set_position(original_position, which="original")
        owner._set_position(active_position, which="active")
        owner.set_anchor(anchor)

    def _create_runtime(
        self,
        source: ColorbarSourceResolution,
        properties: dict[str, Any],
    ) -> Colorbar:
        owner = source.owner_axes
        figure = owner.figure
        if not isinstance(figure, Figure):
            raise ComponentValidationError("Colorbar owner Axes has no Figure.")
        before_axes = tuple(figure.axes)
        active_position = owner.get_position().frozen()
        original_position = owner.get_position(original=True).frozen()
        subplotspec = getattr(owner, "get_subplotspec", lambda: None)()
        anchor = owner.get_anchor()
        try:
            colorbar = figure.colorbar(
                source.mappable,
                ax=owner,
                use_gridspec=True,
                **self._constructor_kwargs(properties),
            )
            if not isinstance(colorbar, Colorbar) or colorbar.mappable is not source.mappable:
                raise ComponentValidationError(
                    "Matplotlib did not create the requested Colorbar."
                )
            colorbar._mygui_owner_restore_state = (
                (
                    owner,
                    active_position,
                    original_position,
                    subplotspec,
                    anchor,
                ),
            )
            return colorbar
        except Exception:
            leaked = getattr(source.mappable, "colorbar", None)
            if isinstance(leaked, Colorbar) and leaked.ax not in before_axes:
                try:
                    leaked.remove()
                except Exception:
                    pass
            for axes in tuple(figure.axes):
                if axes not in before_axes:
                    try:
                        figure.delaxes(axes)
                    except Exception:
                        pass
            self._restore_owner(
                owner,
                active_position,
                original_position,
                subplotspec,
                anchor,
            )
            raise

    def create_runtime(
        self,
        owner_axes_id: str,
        source_component_id: str,
        properties: dict[str, Any],
    ) -> tuple[Colorbar, dict[str, Any]]:
        """Create one runtime Colorbar after complete source preflight."""

        source = self.validate_source(owner_axes_id, source_component_id)
        specs = ColorbarController.property_specs()
        normalized = ColorbarController.default_properties()
        unknown = set(properties) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown Colorbar properties: {sorted(unknown)!r}."
            )
        normalized.update(
            {
                key: specs[key].normalize(value)
                for key, value in properties.items()
            }
        )
        candidate = ComponentState(
            "colorbar-preflight",
            ComponentKind.COLORBAR,
            ComponentRole.COLORBAR,
            str(owner_axes_id),
            0,
            {"object_id": "colorbar-preflight"},
            normalized,
            {"source_component_id": str(source_component_id)},
        )
        ColorbarController(candidate)
        return self._create_runtime(source, normalized), normalized

    @staticmethod
    def destroy_runtime(colorbar: Colorbar) -> None:
        """Remove a staged Colorbar and restore its pre-creation owner layout."""

        if not isinstance(colorbar, Colorbar):
            return
        try:
            handle = MATPLOTLIB_REMOVAL.prepare_colorbar(colorbar)
            MATPLOTLIB_REMOVAL.commit(handle)
            MATPLOTLIB_REMOVAL.finalize(handle)
        except (AttributeError, KeyError, RuntimeError, ValueError):
            figure = getattr(colorbar.ax, "figure", None)
            if isinstance(figure, Figure) and colorbar.ax in figure.axes:
                figure.delaxes(colorbar.ax)
            mappable = getattr(colorbar, "mappable", None)
            if mappable is not None and getattr(mappable, "colorbar", None) is colorbar:
                mappable.colorbar = None
                mappable.colorbar_cid = None

    def refresh_source(self, source_component_id: str) -> None:
        """Synchronize dependent Colorbars without copying source state."""

        source = self.source_resolvers.resolve(source_component_id)
        for controller in self.dependents(source_component_id):
            target = controller.resolve_target()
            target.update_normal(source.mappable)
            state = controller.state
            for key in (
                "locator",
                "formatter",
                "minor_ticks",
                "ticklocation",
                "label_font",
                "tick_font",
                "outline_visible",
                "outline_color",
                "outline_linewidth",
            ):
                controller._write_property(
                    target,
                    controller.property_specs()[key],
                    deepcopy(state.properties[key]),
                )
            controller._request_updates(UpdateImpact.REDRAW, target)

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply safe edits in place and rebuild constructor-sensitive edits."""

        controller = _controller(self.registry, component, ColorbarController)
        patch = dict(properties)
        try:
            old = controller.resolve_target()

            def verify_render() -> None:
                canvas = old.ax.figure.canvas
                if canvas is not None:
                    canvas.draw()

            if not set(patch).intersection(controller.REBUILD_KEYS):
                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_render,
                )
                if not batch.changes:
                    return _rejected(controller, batch.message or "Colorbar render failed.")
                return batch.changes[0]

            before = controller.state
            merged = deepcopy(before.properties)
            specs = controller.property_specs()
            for key, value in patch.items():
                if key not in specs:
                    raise ComponentValidationError(
                        f"Unknown Colorbar property {key!r}."
                    )
                merged[key] = specs[key].normalize(value)
            candidate = before.clone(properties=merged)
            controller._validate_replacement(candidate)
            source = self.source_resolvers.resolve(
                before.data["source_component_id"]
            )
            runtime_snapshot = (
                deepcopy(controller._constructor_properties),
                deepcopy(controller._label_font_value),
                deepcopy(controller._tick_font_value),
                controller._minor_ticks,
                controller._ticklocation,
            )
            old_handle = controller.prepare_remove()
            controller.commit_remove(old_handle)
            new = None
            try:
                new = self._create_runtime(source, merged)
                temporary = ColorbarController(candidate, target=new)
                configured = temporary.apply_state(candidate)
                if not configured.ok:
                    raise ComponentValidationError(configured.message)
                self.registry.locator.bind(controller.component_id, new)
                controller._label_font_value = deepcopy(temporary._label_font_value)
                controller._tick_font_value = deepcopy(temporary._tick_font_value)
                controller._minor_ticks = temporary._minor_ticks
                controller._ticklocation = temporary._ticklocation

                def verify_new_render() -> None:
                    canvas = new.ax.figure.canvas
                    if canvas is not None:
                        canvas.draw()

                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_new_render,
                )
                if not batch.committed or not batch.changes:
                    raise ComponentValidationError(
                        batch.message or "Colorbar render failed."
                    )
                change = batch.changes[0]
            except Exception:
                if new is not None:
                    self.destroy_runtime(new)
                self.registry.locator.bind(controller.component_id, old)
                (
                    controller._constructor_properties,
                    controller._label_font_value,
                    controller._tick_font_value,
                    controller._minor_ticks,
                    controller._ticklocation,
                ) = runtime_snapshot
                controller._state = before.clone()
                controller.rollback_remove(old_handle)
                raise
            controller._finalize_remove(old_handle)
            return change
        except Exception as exc:
            return _rejected(controller, str(exc))


class DeleteReason(str, Enum):
    """Describe the runtime workflow that requested physical deletion."""

    SINGLE = "single"
    BATCH = "batch"
    AXES = "axes"
    DATA_DEPENDENCY = "data_dependency"
    PROGRAMMATIC = "programmatic"


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    """Identify one atomic physical-deletion request by stable IDs."""

    component_ids: tuple[str, ...]
    anchor_id: str | None = None
    reason: DeleteReason = DeleteReason.PROGRAMMATIC

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_ids",
            tuple(dict.fromkeys(str(item) for item in self.component_ids)),
        )
        object.__setattr__(
            self,
            "anchor_id",
            str(self.anchor_id) if self.anchor_id is not None else None,
        )
        object.__setattr__(self, "reason", DeleteReason(self.reason))


@dataclass(frozen=True, slots=True)
class ColorCycleDeletionEffect:
    """Declare that deletion releases an ordered Axes palette slot."""


@dataclass(slots=True)
class _ColorConsumption:
    component_id: str
    before: dict[str, Any] | None
    after: dict[str, Any]
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class ColorLedgerDeletionPlan:
    """Prepared runtime-only ledger changes for a committed deletion."""

    removed_ids: frozenset[str]
    released_axes_ids: frozenset[str]


class ColorConsumptionLedger:
    """Track only palette slots confirmed by this live Canvas session."""

    def __init__(self) -> None:
        self._entries: dict[str, list[_ColorConsumption]] = {}

    def history_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Return a runtime-only, Artist-free memento for Figure history."""

        return {
            axes_id: [
                {
                    "component_id": entry.component_id,
                    "before": deepcopy(entry.before),
                    "after": deepcopy(entry.after),
                    "deleted": bool(entry.deleted),
                }
                for entry in entries
            ]
            for axes_id, entries in self._entries.items()
        }

    def restore_history_snapshot(
        self,
        snapshot: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Restore the exact palette-consumption ledger after replay."""

        restored: dict[str, list[_ColorConsumption]] = {}
        for axes_id, raw_entries in deepcopy(dict(snapshot)).items():
            entries = []
            for raw in raw_entries:
                after = deepcopy(raw["after"])
                ColorCycleState.from_dict(after)
                before = deepcopy(raw.get("before"))
                if before is not None:
                    ColorCycleState.from_dict(before)
                entries.append(
                    _ColorConsumption(
                        str(raw["component_id"]),
                        before,
                        after,
                        bool(raw.get("deleted", False)),
                    )
                )
            if entries:
                restored[str(axes_id)] = entries
        self._entries = restored

    def record(
        self,
        axes_id: str,
        component_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        """Record one committed palette advance, ignoring custom colors."""

        if after is None or before == after:
            return
        ColorCycleState.from_dict(after)
        self._entries.setdefault(str(axes_id), []).append(
            _ColorConsumption(
                str(component_id),
                deepcopy(before),
                deepcopy(after),
            )
        )

    def prepare_deletion(
        self,
        registry: ComponentRegistry,
        removed_ids: Iterable[str],
    ) -> tuple[tuple[ComponentState, ...], ColorLedgerDeletionPlan]:
        """Release only a confirmed, contiguous deleted ledger tail."""

        removed = frozenset(str(component_id) for component_id in removed_ids)
        replacements: list[ComponentState] = []
        released_axes: set[str] = set()
        for axes_id, entries in self._entries.items():
            if not entries or axes_id not in registry:
                continue
            if axes_id in removed:
                released_axes.add(axes_id)
                continue
            future_deleted = [
                entry.deleted or entry.component_id in removed for entry in entries
            ]
            suffix_start = len(entries)
            while suffix_start and future_deleted[suffix_start - 1]:
                suffix_start -= 1
            if suffix_start == len(entries):
                continue
            if not any(
                entry.component_id in removed for entry in entries[suffix_start:]
            ):
                continue
            axes = registry.get(axes_id)
            current = axes.state.properties.get("color_cycle")
            if current != entries[-1].after:
                # A palette reapply or other explicit edit superseded this
                # session ledger. Never infer a release from artist colors.
                continue
            properties = dict(axes.state.properties)
            properties["color_cycle"] = deepcopy(entries[suffix_start].before)
            replacements.append(axes.state.clone(properties=properties))
            released_axes.add(axes_id)
        return (
            tuple(replacements),
            ColorLedgerDeletionPlan(removed, frozenset(released_axes)),
        )

    def commit_deletion(self, plan: ColorLedgerDeletionPlan) -> None:
        """Advance the ledger only after structural deletion commits."""

        for axes_id, entries in tuple(self._entries.items()):
            for entry in entries:
                if entry.component_id in plan.removed_ids:
                    entry.deleted = True
            if axes_id in plan.released_axes_ids:
                while entries and entries[-1].deleted:
                    entries.pop()
            if not entries:
                self._entries.pop(axes_id, None)


@dataclass(frozen=True, slots=True)
class DeletionHandler:
    """Declare physical ownership and explicit cross-component effects."""

    owns_subtree: bool = False
    effects: tuple[object, ...] = ()


class DeletionHandlerRegistry:
    """Resolve one explicit deletion contract for every removable Editor key."""

    def __init__(self) -> None:
        self._handlers: dict[
            tuple[ComponentKind, ComponentRole],
            DeletionHandler,
        ] = {}

    def register(
        self,
        kind: ComponentKind,
        role: ComponentRole,
        handler: DeletionHandler,
    ) -> None:
        key = (ComponentKind(kind), ComponentRole(role))
        if key in self._handlers:
            raise ValueError(
                f"Duplicate deletion handler for {key[0].value}/{key[1].value}."
            )
        self._handlers[key] = handler

    def resolve(self, controller) -> DeletionHandler | None:
        state = controller.state
        return self._handlers.get((state.kind, state.role))

    def validate(self, expected) -> None:
        expected_keys = set(expected)
        actual_keys = set(self._handlers)
        missing = sorted(
            expected_keys - actual_keys,
            key=lambda item: (item[0].value, item[1].value),
        )
        unexpected = sorted(
            actual_keys - expected_keys,
            key=lambda item: (item[0].value, item[1].value),
        )
        if not missing and not unexpected:
            return
        details = []
        if missing:
            details.append(
                "missing "
                + ", ".join(
                    f"{kind.value}/{role.value}" for kind, role in missing
                )
            )
        if unexpected:
            details.append(
                "unexpected "
                + ", ".join(
                    f"{kind.value}/{role.value}" for kind, role in unexpected
                )
            )
        raise ValueError("Invalid production deletion handlers: " + "; ".join(details))


def production_deletion_handlers() -> DeletionHandlerRegistry:
    """Build and validate the first-party physical-deletion contracts."""

    handlers = DeletionHandlerRegistry()
    handlers.register(
        ComponentKind.AXES,
        ComponentRole.AXES,
        DeletionHandler(owns_subtree=True),
    )
    palette_leaf = DeletionHandler(effects=(ColorCycleDeletionEffect(),))
    for role in (
        ComponentRole.LINE,
        ComponentRole.FUNCTION_CURVE,
        ComponentRole.DATA_PLOT,
        ComponentRole.FIT_CURVE,
        ComponentRole.INTERPOLATION,
    ):
        handlers.register(ComponentKind.LINE, role, palette_leaf)
    handlers.register(ComponentKind.SCATTER, ComponentRole.SCATTER, palette_leaf)
    handlers.register(
        ComponentKind.REFERENCE_MARKS,
        ComponentRole.REFLECTION_POSITIONS,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.REFERENCE_GUIDE,
        ComponentRole.REFERENCE_LINE,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.REFERENCE_GUIDE,
        ComponentRole.REFERENCE_BAND,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.COLORBAR,
        ComponentRole.COLORBAR,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.TEXT,
        ComponentRole.TEXT,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_ZOOM,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_IMAGE,
        DeletionHandler(),
    )
    handlers.validate(
        key
        for key, controller_type in CONTROLLER_TYPES.items()
        if controller_type.DELETION_POLICY is DeletionPolicy.REMOVE
    )
    return handlers


@dataclass(frozen=True, slots=True)
class DeletionPlan:
    """Prepared, validated runtime-only deletion state."""

    requested_ids: tuple[str, ...]
    root_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    state_replacements: tuple[ComponentState, ...]
    fallback_id: str | None = None
    color_ledger_plan: ColorLedgerDeletionPlan | None = None


@dataclass(frozen=True, slots=True)
class DeletionOutcome:
    """Report one committed deletion or its complete/incomplete rollback."""

    committed: bool
    rollback_complete: bool
    removed_ids: tuple[str, ...] = ()
    selected_component_id: str | None = None
    changes: tuple[ComponentChange, ...] = ()
    notices: tuple[ComponentNotice, ...] = ()
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.committed and all(change.ok for change in self.changes)

    def as_batch_change(self) -> ComponentBatchChange:
        return ComponentBatchChange(
            self.changes,
            self.committed,
            notices=self.notices,
            message=self.message,
            rollback_complete=self.rollback_complete,
        )


@dataclass(slots=True)
class PreparedDeletion:
    """Execute an already validated deletion plan exactly once."""

    service: "ComponentDeletionService"
    request: DeletionRequest
    plan: DeletionPlan
    _executed: bool = False

    def set_fallback(self, component_id: str | None) -> None:
        if self._executed:
            raise RuntimeError("A committed deletion plan cannot be changed.")
        self.plan = replace(
            self.plan,
            fallback_id=(
                str(component_id) if component_id is not None else None
            ),
        )

    def execute(
        self,
        *,
        verifier: Callable[[], None] | None = None,
    ) -> DeletionOutcome:
        if self._executed:
            raise RuntimeError("Prepared deletion has already been executed.")
        self._executed = True
        result = self.service.registry.delete_transaction(
            self.plan.root_ids,
            state_replacements=self.plan.state_replacements,
            verifier=verifier,
        )
        if result.committed and self.plan.color_ledger_plan is not None:
            self.service.color_ledger.commit_deletion(self.plan.color_ledger_plan)
        return DeletionOutcome(
            committed=result.committed,
            rollback_complete=result.rollback_complete,
            removed_ids=self.plan.removed_ids if result.committed else (),
            selected_component_id=(
                self.plan.fallback_id if result.committed else None
            ),
            changes=result.changes,
            notices=result.notices,
            message=result.message,
        )


def _axes_replacements_for_deletion(
    registry: ComponentRegistry,
    removed_ids: Iterable[str],
) -> tuple[ComponentState, ...]:
    """Keep surviving Axes order/selectors contiguous without moving layout."""

    removed = set(str(component_id) for component_id in removed_ids)
    if not any(
        component_id in registry
        and registry.get(component_id).state.kind is ComponentKind.AXES
        for component_id in removed
    ):
        return ()
    registry.validate_tree()
    remaining = sorted(
        (
            controller
            for controller in registry.query(kind=ComponentKind.AXES)
            if controller.component_id not in removed
        ),
        key=lambda controller: int(
            controller.state.selector.get("index", controller.state.order)
        ),
    )
    replacements = []
    for index, controller in enumerate(remaining):
        cached_state = controller.state
        if cached_state.order == index and cached_state.selector.get("index") == index:
            continue
        live_state = controller.read_state(strict=True)
        replacements.append(
            live_state.clone(
                order=index,
                selector={"index": index},
            )
        )
    return tuple(replacements)


def _expand_primary_twin_deletions(
    registry: ComponentRegistry,
    component_ids: Iterable[str],
) -> tuple[str, ...]:
    """Include a right-Y sibling when its primary Axes is deleted."""

    expanded = list(dict.fromkeys(str(item) for item in component_ids))
    axes = tuple(registry.query(kind=ComponentKind.AXES))
    for component_id in tuple(expanded):
        controller = registry.get(component_id)
        if controller.state.kind is not ComponentKind.AXES:
            continue
        subplot = controller.state.data.get("subplot", {})
        if subplot.get("layer") != "primary":
            continue
        key = (
            subplot.get("layout_id"),
            subplot.get("row"),
            subplot.get("column"),
        )
        for sibling in axes:
            sibling_subplot = sibling.state.data.get("subplot", {})
            sibling_key = (
                sibling_subplot.get("layout_id"),
                sibling_subplot.get("row"),
                sibling_subplot.get("column"),
            )
            if sibling_key == key and sibling_subplot.get("layer") == "right_y":
                if sibling.component_id not in expanded:
                    expanded.append(sibling.component_id)
                break
    return tuple(expanded)


def _expand_colorbar_source_deletions(
    registry: ComponentRegistry,
    component_ids: Iterable[str],
) -> tuple[str, ...]:
    """Plan Colorbar cascades before a source Scatter deletion commits."""

    expanded = list(dict.fromkeys(str(item) for item in component_ids))
    removed_sources = {
        component_id
        for component_id in expanded
        if component_id in registry
        and registry.get(component_id).state.kind is ComponentKind.SCATTER
    }
    if not removed_sources:
        return tuple(expanded)
    dependents = [
        controller.component_id
        for controller in registry.query(kind=ComponentKind.COLORBAR)
        if controller.state.data.get("source_component_id") in removed_sources
    ]
    # Commit dependent Colorbar removal before detaching its ScalarMappable.
    # Both remain independent deletion roots under the owner Axes, but are
    # still executed by the same Registry/DeletionCoordinator transaction.
    return tuple(
        [*dependents, *(item for item in expanded if item not in dependents)]
    )


def _layout_replacements_for_deletion(
    registry: ComponentRegistry,
    removed_ids: Iterable[str],
) -> tuple[ComponentState, ...]:
    """Repair persisted layout/share/legend state for Axes survivors."""

    removed = set(str(component_id) for component_id in removed_ids)
    surviving_axes = tuple(
        controller
        for controller in registry.query(kind=ComponentKind.AXES)
        if controller.component_id not in removed
    )
    group_counts: dict[tuple[str, str], int] = {}
    for controller in surviving_axes:
        subplot = controller.state.data.get("subplot", {})
        for dimension, key in (("x", "share_x_group"), ("y", "share_y_group")):
            group = subplot.get(key)
            if group is not None:
                group_counts[(dimension, str(group))] = (
                    group_counts.get((dimension, str(group)), 0) + 1
                )

    replacements: list[ComponentState] = []
    right_cells = {
        (
            controller.state.data["subplot"].get("layout_id"),
            controller.state.data["subplot"].get("row"),
            controller.state.data["subplot"].get("column"),
        )
        for controller in surviving_axes
        if controller.state.data.get("subplot", {}).get("layer") == "right_y"
    }
    for controller in surviving_axes:
        state = controller.state
        subplot = deepcopy(state.data.get("subplot", {}))
        changed = False
        for dimension, key in (("x", "share_x_group"), ("y", "share_y_group")):
            group = subplot.get(key)
            if group is not None and group_counts.get((dimension, str(group)), 0) < 2:
                subplot[key] = None
                changed = True
        if changed:
            data = deepcopy(state.data)
            data["subplot"] = subplot
            replacements.append(state.clone(data=data))

        if subplot.get("layer") != "primary":
            continue
        cell = (subplot.get("layout_id"), subplot.get("row"), subplot.get("column"))
        if cell in right_cells:
            continue
        for child in registry.children(controller.component_id):
            child_state = child.state
            if (
                child_state.kind is ComponentKind.LEGEND
                and child_state.role is ComponentRole.LEGEND
                and child_state.properties.get("entry_scope") == "twin_pair"
            ):
                properties = deepcopy(child_state.properties)
                properties["entry_scope"] = "axes"
                replacements.append(child_state.clone(properties=properties))
                break

    used_layouts = {
        controller.state.data.get("subplot", {}).get("layout_id")
        for controller in surviving_axes
    }
    for figure in registry.query(kind=ComponentKind.FIGURE):
        state = figure.state
        layouts = state.data.get("layouts")
        if not isinstance(layouts, list):
            continue
        filtered = [
            deepcopy(item)
            for item in layouts
            if item.get("id") in used_layouts
        ]
        if filtered != layouts:
            replacements.append(state.clone(data={"layouts": filtered}))
    return tuple(replacements)


def _column_ref(value: ColumnRef | dict[str, Any]) -> ColumnRef:
    return value if isinstance(value, ColumnRef) else ColumnRef.from_dict(value)


@dataclass(frozen=True, slots=True)
class AxesPaletteStatus:
    """Describe the effective palette source displayed for one Axes."""

    mode: str
    palette: PaletteDefinition
    figure_style: str

    @property
    def uses_style_default(self) -> bool:
        """Return whether the current palette follows the Figure style."""

        return self.mode == "style"


class AxesCommandService:
    """Atomic commands spanning an Axes and its semantic child components."""

    def __init__(self, registry: ComponentRegistry):
        self.registry = registry

    def _axes(self, axes_id: str) -> AxesController:
        return _controller(self.registry, axes_id, AxesController)

    def semantic(
        self,
        axes_id: str,
        *,
        kind=None,
        role=None,
        selector=None,
        recursive: bool = True,
    ):
        """Return the Controller for an axes semantic component."""

        return self.registry.find_one(
            parent_id=axes_id,
            kind=kind,
            role=role,
            selector=selector,
            recursive=recursive,
        )

    def set_label_style(
        self,
        axes_id: str,
        *,
        fontfamily: str | None = None,
        fontsize: float | None = None,
    ) -> ComponentBatchChange:
        """Set label style."""

        patch = {}
        if fontfamily is not None:
            patch["fontfamily"] = fontfamily
        if fontsize is not None:
            patch["fontsize"] = float(fontsize)
        controllers = (
            self.semantic(axes_id, role=ComponentRole.X_LABEL),
            self.semantic(axes_id, role=ComponentRole.Y_LABEL),
        )
        return self.registry.apply_transaction(
            ComponentMutation(item.component_id, properties=patch)
            for item in controllers
        )

    def set_label_positions(
        self,
        axes_id: str,
        x_position,
        y_position,
    ) -> ComponentBatchChange:
        """Set label positions."""

        x_label = self.semantic(axes_id, role=ComponentRole.X_LABEL)
        y_label = self.semantic(axes_id, role=ComponentRole.Y_LABEL)
        return self.registry.apply_transaction(
            (
                ComponentMutation(
                    x_label.component_id,
                    properties={"position": tuple(x_position)},
                ),
                ComponentMutation(
                    y_label.component_id,
                    properties={"position": tuple(y_position)},
                ),
            )
        )

    def set_spine_visible(
        self,
        axes_id: str,
        side: str,
        visible: bool,
    ) -> ComponentBatchChange:
        """Set spine visible."""

        spine = self.semantic(
            axes_id,
            kind=ComponentKind.SPINE,
            selector={"name": side},
        )
        return self.registry.apply_transaction(
            (
                ComponentMutation(
                    spine.component_id,
                    properties={"visible": bool(visible)},
                ),
            )
        )

    def ensure_legend(self, axes_id: str):
        """Return the current legend, creating it only when necessary."""

        controller = self.semantic(
            axes_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
        )
        target = self.registry.resolve_target(controller.component_id)
        if target is not None:
            return controller, target
        axes = self.registry.resolve_target(axes_id)
        if not isinstance(axes, Axes):
            raise ValueError("Axes target is unavailable.")
        handles, labels = axes.get_legend_handles_labels()
        peer = getattr(axes, "_mygui_merged_legend_peer", None)
        if isinstance(peer, Axes) and peer in axes.figure.axes:
            peer_handles, peer_labels = peer.get_legend_handles_labels()
            handles = [*handles, *peer_handles]
            labels = [*labels, *peer_labels]
        legend = axes.legend(handles, labels)
        self.registry.locator.bind(controller.component_id, legend)
        return controller, legend

    def set_legend_position(
        self,
        axes_id: str,
        position,
    ) -> ComponentChange:
        """Set legend position."""

        controller, legend = self.ensure_legend(axes_id)
        del legend
        return controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "location": position,
                    "visible": True,
                },
            )
        )

    def apply_legend_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply Legend properties, rebuilding constructor-only layout safely."""

        controller = _controller(self.registry, component, LegendController)
        try:
            controller, old = self.ensure_legend(controller.state.parent_id)
            patch = dict(properties)

            def verify_render() -> None:
                old.figure.canvas.draw()

            rebuild = bool(set(patch) & controller.REBUILD_KEYS)
            if not rebuild:
                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_render,
                )
                if not batch.changes:
                    return _rejected(
                        controller,
                        batch.message or "Legend render failed.",
                    )
                change = batch.changes[0]
                if not batch.committed:
                    return replace(
                        change,
                        message=(
                            "Legend render failed; keeping the last valid legend."
                        ),
                    )
                return change
            state = controller.read_state(strict=True)
            merged = deepcopy(state.properties)
            merged.update(patch)
            candidate = state.clone(properties=merged)
            controller._validate_replacement(candidate)
            axes = old.axes
            handles, labels = axes.get_legend_handles_labels()
            peer = getattr(axes, "_mygui_merged_legend_peer", None)
            if isinstance(peer, Axes) and peer in axes.figure.axes:
                peer_handles, peer_labels = peer.get_legend_handles_labels()
                handles = [*handles, *peer_handles]
                labels = [*labels, *peer_labels]
            kwargs = {
                "loc": legend_location_value(merged["location"]),
                "bbox_to_anchor": legend_anchor_value(
                    merged["bbox_to_anchor"]
                ),
                "ncols": merged["ncols"],
                "mode": merged["mode"],
                "alignment": merged["alignment"],
                "reverse": merged["reverse"],
                "markerfirst": merged["markerfirst"],
                "numpoints": merged["numpoints"],
                "scatterpoints": merged["scatterpoints"],
                "scatteryoffsets": merged["scatteryoffsets"],
                "markerscale": merged["markerscale"],
                "borderpad": merged["borderpad"],
                "labelspacing": merged["labelspacing"],
                "handlelength": merged["handlelength"],
                "handleheight": merged["handleheight"],
                "handletextpad": merged["handletextpad"],
                "borderaxespad": merged["borderaxespad"],
                "columnspacing": merged["columnspacing"],
                "fancybox": merged["fancybox"],
                "shadow": merged["shadow"],
                "frameon": merged["frameon"],
            }
            new = axes.legend(handles, labels, **kwargs)
            old_visible = old.get_visible()
            runtime_snapshot = (
                deepcopy(controller._constructor_properties),
                controller._entry_scope,
            )
            try:
                old.set_visible(False)
                self.registry.locator.bind(controller.component_id, new)
                specs = controller.property_specs()
                for key, value in merged.items():
                    if key in patch or key in controller.REBUILD_KEYS:
                        continue
                    controller._write_property(new, specs[key], deepcopy(value))
                batch = self.registry.apply_transaction(
                    (
                        ComponentMutation(
                            controller.component_id,
                            properties=patch,
                        ),
                    ),
                    verifier=verify_render,
                )
                if not batch.committed:
                    raise ComponentValidationError(
                        batch.message or "Legend render failed."
                    )
                change = batch.changes[0]
            except Exception:
                (
                    controller._constructor_properties,
                    controller._entry_scope,
                ) = runtime_snapshot
                try:
                    new.remove()
                finally:
                    if old.axes is None:
                        axes.add_artist(old)
                    axes.legend_ = old
                    old.set_visible(old_visible)
                    self.registry.locator.bind(controller.component_id, old)
                raise
            if old is not new:
                try:
                    old.remove()
                except ValueError:
                    pass
            axes.legend_ = new
            return change
        except Exception as exc:
            return _rejected(controller, str(exc))

    def cycle_state(self, axes_id: str) -> ColorCycleState:
        """Return the axes color-cycle state, creating it when absent."""

        value = self._axes(axes_id).state.properties.get("color_cycle")
        return ColorCycleState.from_dict(value)

    def _figure_style(self, axes_id: str) -> str:
        axes_state = self._axes(axes_id).state
        figure_id = axes_state.parent_id
        if figure_id is None:
            raise ValueError("Axes is not attached to a Figure component.")
        figure_state = self.registry.get(figure_id).state
        if figure_state.kind is not ComponentKind.FIGURE:
            raise ValueError("Axes parent is not a Figure component.")
        return str(
            figure_state.properties.get("style", "default")
        )

    def style_palette(self, axes_id: str) -> PaletteDefinition:
        """Resolve the current Figure style palette for an Axes."""

        return resolve_style_palette(self._figure_style(axes_id))

    def palette_status(self, axes_id: str) -> AxesPaletteStatus:
        """Return the effective Style-default or user-selected palette."""

        figure_style = self._figure_style(axes_id)
        style_palette = self.style_palette(axes_id)
        active = self.cycle_state(axes_id).active_palette
        if (
            active is not None
            and active.source is not PaletteSource.MATPLOTLIB_STYLE
        ):
            return AxesPaletteStatus(
                "user",
                active,
                figure_style,
            )
        return AxesPaletteStatus(
            "style",
            style_palette,
            figure_style,
        )

    def peek_color(self, axes_id: str) -> ColorSelection:
        """Preview the next chart color without advancing the cycle."""

        cycle = self.cycle_state(axes_id)
        palette = cycle.active_palette
        if palette is None:
            return cycle.peek()
        return self.preview_color_cycle(
            axes_id,
            palette,
            cycle.next_index,
        ).peek()

    def preview_color_cycle(
        self,
        axes_id: str,
        fallback_palette: PaletteDefinition,
        fallback_index: int,
    ) -> ColorCycleState:
        """Return the user cycle or a non-mutating style-cycle preview."""

        cycle = self.cycle_state(axes_id)
        active = cycle.active_palette
        if active is not None and (
            active.source is not PaletteSource.MATPLOTLIB_STYLE
            or active.id == fallback_palette.id
        ):
            preview = ColorCycleState.from_dict(cycle.to_dict())
        else:
            preview = ColorCycleState(
                fallback_palette,
                max(0, int(fallback_index)) % len(fallback_palette.colors),
            )
        palette = preview.active_palette
        if palette is None:
            return preview
        occupied: set[int] = set()
        for controller in self.registry.query(
            parent_id=axes_id,
            recursive=True,
            capabilities={"color", "data"},
        ):
            try:
                color = normalize_color(
                    controller.state.properties["color"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            occupied.update(
                index
                for index, palette_color in enumerate(palette.colors)
                if palette_color == color
            )
        start = preview.next_index
        for offset in range(len(palette.colors)):
            candidate = (start + offset) % len(palette.colors)
            if candidate not in occupied:
                preview.activate(palette, candidate)
                break
        return preview

    def commit_color_selection(
        self,
        axes_id: str,
        selection: ColorSelection,
        *,
        preview_cycle: ColorCycleState | None = None,
    ) -> ComponentChange:
        """Commit a previewed color after component creation succeeds."""

        # Preview and commit are deliberately separate: cancelled or failed
        # chart creation must not consume a color from the axes sequence.
        cycle = (
            ColorCycleState.from_dict(preview_cycle.to_dict())
            if preview_cycle is not None
            else self.cycle_state(axes_id)
        )
        cycle.commit(selection)
        return self._axes(axes_id).set_property(
            "color_cycle",
            cycle.to_dict(),
        )

    def apply_palette(
        self,
        axes_id: str,
        palette: PaletteDefinition,
    ) -> ComponentBatchChange:
        """Apply palette."""

        controllers = self.registry.query(
            capabilities={"color", "data"},
            parent_id=axes_id,
            recursive=True,
        )
        cycle = ColorCycleState()
        cycle.commit_palette_for_count(palette, len(controllers))
        mutations = [
            ComponentMutation(
                controller.component_id,
                properties={
                    "color": palette.colors[
                        index % len(palette.colors)
                    ]
                },
            )
            for index, controller in enumerate(controllers)
        ]
        mutations.append(
            ComponentMutation(
                axes_id,
                properties={"color_cycle": cycle.to_dict()},
            )
        )
        result = self.registry.apply_transaction(mutations)
        if controllers or not result.ok:
            return result
        return replace(
            result,
            notices=(
                _warning(
                    "Palette selected for future charts; the current "
                    "axes has no chart components to recolor."
                ),
            ),
            message="Palette selected for future charts.",
        )


class FunctionCurveService:
    """Evaluate and atomically update a function curve definition."""

    def __init__(self, registry: ComponentRegistry):
        self.registry = registry

    def update(
        self,
        component,
        expression: str,
        x_start: float,
        x_stop: float,
        *,
        samples: int | None = None,
    ) -> ComponentChange:
        """Apply the supplied component changes."""

        controller = _controller(
            self.registry,
            component,
            FunctionCurveController,
        )
        try:
            start = float(x_start)
            stop = float(x_stop)
            if not np.isfinite(start) or not np.isfinite(stop):
                raise ValueError("Curve range must be finite.")
            if samples is None:
                target = controller.resolve_target()
                samples = len(target.get_xdata()) or 1000
            samples = max(2, int(samples))
            x_values = np.linspace(start, stop, samples)
            y_values = evaluate_curve_expression(expression, x_values)
        except Exception as exc:
            return _rejected(controller, str(exc))
        return controller.apply_role_data(
            {
                "expression": str(expression),
                "x_start": start,
                "x_stop": stop,
            },
            drawable=XYData(x_values, y_values),
        )


class ChartDataService:
    """Resolve table references and refresh Plot/Scatter components."""

    def __init__(
        self,
        repository,
        registry: ComponentRegistry,
    ):
        self.repository = repository
        self.registry = registry
        self.interpolation_service: InterpolationService | None = None
        self.colorbar_service: ColorbarService | None = None
        self._observer_failures: list[ObserverFailure] = []

    def _refresh_colorbar_source(
        self,
        controller,
        change: ComponentChange,
    ) -> ComponentChange:
        if (
            not isinstance(controller, ScatterController)
            or not change.ok
            or self.colorbar_service is None
            or not self.colorbar_service.has_dependents(controller.component_id)
        ):
            return change
        try:
            self.colorbar_service.refresh_source(controller.component_id)
        except Exception as exc:
            return _notices(
                change,
                _warning(f"Scatter updated, but its Colorbar refresh failed: {exc}"),
            )
        return change

    def drain_observer_failures(self) -> tuple[ObserverFailure, ...]:
        """Return and clear refresh failures isolated from table commits."""

        failures, self._observer_failures = (
            tuple(self._observer_failures),
            [],
        )
        return failures

    @staticmethod
    def refs_for(controller) -> tuple[ColumnRef, ColumnRef]:
        """Return the data references stored by a component."""

        data = controller.state.data
        return (
            _column_ref(data["x_ref"]),
            _column_ref(data["y_ref"]),
        )

    def _validate_refs(
        self,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
    ) -> None:
        if not self.repository.has_ref(x_ref) or not self.repository.has_ref(y_ref):
            raise ValueError("Chart data source was removed.")

    @staticmethod
    def preprocess_for(controller) -> DataPreprocessSpec:
        """Return the persisted preprocessing specification."""

        return DataPreprocessSpec.from_dict(controller.state.data["preprocess"])

    def _pair(self, controller, x_ref, y_ref, preprocess):
        self._validate_refs(x_ref, y_ref)
        return resolve_preprocessed_pair(
            self.repository,
            x_ref,
            y_ref,
            preprocess,
            preserve_gaps=isinstance(controller, DataPlotController),
        )

    def _scatter_data(
        self,
        controller: ScatterController,
        pair: PreprocessedPair,
        data: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> ScatterData:
        """Resolve optional color/size refs against the exact X/Y row mask."""

        props = properties or controller.state.properties
        base_mask = np.asarray(pair.valid_mask, dtype=bool)
        x_values = np.asarray(pair.x)
        y_values = np.asarray(pair.y)
        keep = np.ones(len(x_values), dtype=bool)
        colors = None
        sizes = None

        def mapped_values(key: str) -> np.ndarray:
            raw_ref = data.get(key)
            if raw_ref is None:
                raise ValueError(f"Scatter mapping requires {key}.")
            ref = _column_ref(raw_ref)
            if not self.repository.has_ref(ref):
                raise ValueError("Scatter mapping data source was removed.")
            raw = np.asarray(self.repository.series(ref))
            if len(raw) < len(base_mask):
                raise ValueError("Scatter mapping column is not row-aligned.")
            try:
                numeric = raw[: len(base_mask)].astype(float)
            except (TypeError, ValueError) as exc:
                raise ValueError("Scatter mapping columns must be numeric.") from exc
            return numeric[base_mask]

        color_spec = props["color_mapping"]
        if color_spec["enabled"]:
            colors = mapped_values("color_ref")
            if color_spec["nonfinite"] == "drop":
                keep &= np.isfinite(colors)
        size_spec = props["size_mapping"]
        if size_spec["enabled"]:
            sizes = mapped_values("size_ref")
            keep &= np.isfinite(sizes)
        return ScatterData(
            x_values[keep],
            y_values[keep],
            None if colors is None else colors[keep],
            None if sizes is None else sizes[keep],
        )

    def set_refs(
        self,
        component,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
    ) -> ComponentChange:
        """Set refs."""

        controller = _controller(self.registry, component)
        if not isinstance(
            controller,
            (DataPlotController, ScatterController),
        ):
            raise TypeError(
                "ChartDataService supports Plot and Scatter components."
            )
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            spec = DataPreprocessSpec.from_dict(
                preprocess
                if preprocess is not None
                else controller.state.data["preprocess"]
            )
            pair = self._pair(controller, x_ref, y_ref, spec)
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = deepcopy(controller.state.data)
        data.update(
            x_ref=x_ref.to_dict(),
            y_ref=y_ref.to_dict(),
            preprocess=spec.to_dict(),
        )
        drawable = (
            self._scatter_data(controller, pair, data)
            if isinstance(controller, ScatterController)
            else XYData(pair.x, pair.y)
        )
        change = controller.apply_role_data(
            data,
            drawable=drawable,
        )
        change = self._refresh_colorbar_source(controller, change)
        notices = []
        if pair.excluded_count:
            notices.append(
                _warning(
                    f"Preprocessing ignored or masked {pair.excluded_count} "
                    "rows with missing or non-finite values."
                )
            )
        if change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning("Chart has no valid data yet; its editor and style were kept.")
            )
        return _notices(change, *notices)

    def configure_scatter_mapping(
        self,
        component,
        *,
        color_ref: ColumnRef | dict[str, Any] | None,
        size_ref: ColumnRef | dict[str, Any] | None,
        color_mapping: dict[str, Any],
        size_mapping: dict[str, Any],
    ) -> ComponentChange:
        """Atomically change Scatter mapping refs, specs, and drawable arrays."""

        controller = _controller(self.registry, component, ScatterController)
        data = deepcopy(controller.state.data)
        data["color_ref"] = None if color_ref is None else _column_ref(color_ref).to_dict()
        data["size_ref"] = None if size_ref is None else _column_ref(size_ref).to_dict()
        properties = deepcopy(controller.state.properties)
        specs = controller.property_specs()
        properties["color_mapping"] = specs["color_mapping"].normalize(color_mapping)
        properties["size_mapping"] = specs["size_mapping"].normalize(size_mapping)
        if (
            controller.state.properties["color_mapping"]["enabled"]
            and not properties["color_mapping"]["enabled"]
            and self.colorbar_service is not None
            and self.colorbar_service.has_dependents(controller.component_id)
        ):
            return _rejected(
                controller,
                "Delete the dependent Colorbar before disabling scalar color mapping.",
            )
        try:
            x_ref, y_ref = self.refs_for(controller)
            pair = self._pair(
                controller,
                x_ref,
                y_ref,
                self.preprocess_for(controller),
            )
            drawable = self._scatter_data(controller, pair, data, properties)
        except Exception as exc:
            return _rejected(controller, str(exc))
        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "color_mapping": properties["color_mapping"],
                    "size_mapping": properties["size_mapping"],
                },
                data=data,
                runtime_data=drawable,
            )
        )
        return self._refresh_colorbar_source(controller, change)

    def refresh(self, component) -> ComponentChange:
        """Refresh the component from its current data references."""

        controller = _controller(self.registry, component)
        try:
            x_ref, y_ref = self.refs_for(controller)
        except Exception as exc:
            return _rejected(controller, str(exc))
        return self.set_refs(
            controller,
            x_ref,
            y_ref,
            self.preprocess_for(controller),
        )

    def refresh_affected(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> list[ComponentChange]:
        """Refresh components affected by changed table data."""

        changed = set(changed_columns)
        results: list[ComponentChange] = []
        with self.registry.batch_updates():
            for controller in self.registry.query(
                capabilities={"data_reference", "auto_refresh"}
            ):
                if isinstance(controller, ReferenceMarksController):
                    continue
                try:
                    refs = set(self.refs_for(controller))
                    if isinstance(controller, ScatterController):
                        for key in ("color_ref", "size_ref"):
                            raw = controller.state.data.get(key)
                            if raw is not None:
                                refs.add(_column_ref(raw))
                except Exception as exc:
                    self._observer_failures.append(
                        ObserverFailure(
                            "ChartDataService",
                            "data-reference",
                            exc,
                            component_id=controller.component_id,
                            reference=deepcopy(controller.state.data),
                        )
                    )
                    continue
                if not refs.intersection(changed):
                    continue
                if isinstance(controller, InterpolationController):
                    if self.interpolation_service is not None:
                        results.append(
                            self.interpolation_service.refresh(controller)
                        )
                    continue
                results.append(self.refresh(controller))
        return results


class InterpolationService:
    """Compute interpolation output and commit parameters atomically."""

    def __init__(
        self,
        repository,
        registry: ComponentRegistry,
    ):
        self.repository = repository
        self.registry = registry

    def configure(
        self,
        component,
        *,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        method: str,
        k: int,
        samples: int,
        lam: float | None,
        lam_auto: bool,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        preserve_on_failure: bool = True,
    ) -> ComponentChange:
        """Configure the service with its current registry dependencies."""

        controller = _controller(
            self.registry,
            component,
            InterpolationController,
        )
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            if not self.repository.has_ref(x_ref) or not self.repository.has_ref(y_ref):
                raise ValueError("Interpolation data source was removed.")
            spec = DataPreprocessSpec.from_dict(
                preprocess
                if preprocess is not None
                else controller.state.data["preprocess"]
            )
            pair = resolve_preprocessed_pair(
                self.repository,
                x_ref,
                y_ref,
                spec,
                preserve_gaps=False,
            )
            data = {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
                "preprocess": spec.to_dict(),
                "method": str(method),
                "k": int(k),
                "samples": int(samples),
                "lam": None if lam is None else float(lam),
                "lam_auto": bool(lam_auto),
            }
            # Validate configuration through a temporary state before doing
            # potentially expensive interpolation work.
            controller._validate_controller_state(
                controller.state.clone(data=data)
            )
            if pair.x.size:
                x_values, y_values = interpolate_curve(
                    pair.x,
                    pair.y,
                    method,
                    k=int(k),
                    samples=int(samples),
                    lam=lam,
                    lam_auto=bool(lam_auto),
                )
            else:
                x_values, y_values = np.asarray([]), np.asarray([])
        except Exception as exc:
            if preserve_on_failure:
                return _rejected(controller, str(exc))
            data = deepcopy(controller.state.data)
            change = controller.apply_role_data(
                data,
                drawable=XYData([], []),
            )
            return _notices(change, _warning(str(exc)))

        change = controller.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )
        notices = []
        if pair.excluded_count:
            notices.append(
                _warning(
                    f"Preprocessing ignored {pair.excluded_count} rows "
                    "with missing or non-finite values."
                )
            )
        if change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning(
                    "Interpolation has no valid data yet; its editor and style were kept."
                )
            )
        return _notices(change, *notices)

    def refresh(self, component) -> ComponentChange:
        """Refresh the component from its current data references."""

        controller = _controller(
            self.registry,
            component,
            InterpolationController,
        )
        data = controller.state.data
        return self.configure(
            controller,
            x_ref=data["x_ref"],
            y_ref=data["y_ref"],
            method=data["method"],
            k=data["k"],
            samples=data["samples"],
            lam=data["lam"],
            lam_auto=data["lam_auto"],
            preprocess=data["preprocess"],
            preserve_on_failure=False,
        )


class FitService:
    """Manage persistent Fit state while keeping fitting explicitly manual."""

    def __init__(
        self,
        repository,
        registry: ComponentRegistry,
    ):
        self.repository = repository
        self.registry = registry
        self._request_generation: dict[str, int] = {}
        self._pending_source_changes: set[str] = set()
        self._observer_failures: list[ObserverFailure] = []

    def history_snapshot(self) -> dict[str, Any]:
        """Capture runtime-only pending/generation state for Figure history."""

        return {
            "request_generation": dict(self._request_generation),
            "pending_source_changes": sorted(self._pending_source_changes),
        }

    def restore_history_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore Fit runtime state without publishing component changes."""

        value = deepcopy(dict(snapshot))
        self._request_generation = {
            str(component_id): int(generation)
            for component_id, generation in dict(
                value.get("request_generation", {})
            ).items()
        }
        self._pending_source_changes = {
            str(component_id)
            for component_id in value.get("pending_source_changes", ())
            if str(component_id) in self.registry
        }

    def drain_observer_failures(self) -> tuple[ObserverFailure, ...]:
        """Return and clear stale-marking reference failures."""

        failures, self._observer_failures = (
            tuple(self._observer_failures),
            [],
        )
        return failures

    def mark_sources_changed(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> tuple[str, ...]:
        """Mark manual Fit components stale without changing persisted state."""

        changed = set(changed_columns)
        affected = []
        live_fit_ids = set()
        for controller in self.registry.query(role=ComponentRole.FIT_CURVE):
            live_fit_ids.add(controller.component_id)
            try:
                refs = {
                    _column_ref(controller.state.data["x_ref"]),
                    _column_ref(controller.state.data["y_ref"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                self._observer_failures.append(
                    ObserverFailure(
                        "FitService",
                        "data-reference",
                        exc,
                        component_id=controller.component_id,
                        reference=deepcopy(controller.state.data),
                    )
                )
                continue
            if refs.intersection(changed):
                self._pending_source_changes.add(controller.component_id)
                self.cancel(controller.component_id)
                affected.append(controller.component_id)
        self._pending_source_changes.intersection_update(live_fit_ids)
        return tuple(affected)

    def has_pending_source_change(self, component_id: str) -> bool:
        """Return whether source data changed since the last explicit fit."""

        if component_id not in self.registry:
            self._pending_source_changes.discard(component_id)
            return False
        return component_id in self._pending_source_changes

    def set_sources(
        self,
        component,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
    ) -> ComponentChange:
        """Set sources."""

        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            if not self.repository.has_ref(x_ref) or not self.repository.has_ref(y_ref):
                raise ValueError("Fit data source was removed.")
            spec = DataPreprocessSpec.from_dict(
                preprocess
                if preprocess is not None
                else controller.state.data["preprocess"]
            )
            pair = resolve_preprocessed_pair(
                self.repository,
                x_ref,
                y_ref,
                spec,
                preserve_gaps=False,
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = deepcopy(controller.state.data)
        data.update(
            x_ref=x_ref.to_dict(),
            y_ref=y_ref.to_dict(),
            preprocess=spec.to_dict(),
        )
        change = controller.apply_mutation(
            ComponentMutation(controller.component_id, data=data)
        )
        if change.changed:
            self.cancel(controller.component_id)
            self._pending_source_changes.add(controller.component_id)
        message = "Fit preprocessing updated; run fitting to recompute."
        if pair.excluded_count:
            message = f"Fit preprocessing excluded {pair.excluded_count} rows; run fitting to recompute."
        return _notices(change, _warning(message)) if change.changed else change

    def resolve_sources(self, component) -> PreprocessedPair:
        """Resolve the current Fit sources without mutating the component."""

        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        data = controller.state.data
        return resolve_preprocessed_pair(
            self.repository,
            _column_ref(data["x_ref"]),
            _column_ref(data["y_ref"]),
            DataPreprocessSpec.from_dict(data["preprocess"]),
            preserve_gaps=False,
        )

    def next_request(self, component_id: str) -> int:
        """Start a new generation used to reject stale async results."""

        generation = self._request_generation.get(component_id, 0) + 1
        self._request_generation[component_id] = generation
        return generation

    def request_is_current(
        self,
        component_id: str,
        generation: int,
    ) -> bool:
        """Return whether an asynchronous result is still current."""

        return (
            component_id in self.registry
            and self._request_generation.get(component_id) == generation
        )

    def cancel(self, component_id: str) -> None:
        """Close the dialog without applying pending changes."""

        self._request_generation[component_id] = (
            self._request_generation.get(component_id, 0) + 1
        )

    def apply_result(
        self,
        component,
        *,
        engine: FitEngine | str,
        fit_type,
        fit_options,
        fit_result,
        expression: str,
        x_start: float,
        x_stop: float,
        clear_pending: bool = True,
    ) -> ComponentChange:
        """Apply a completed result only if it belongs to the current request."""

        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        try:
            engine = FitEngine(engine)
            start = float(x_start)
            stop = float(x_stop)
            persisted_options = normalize_fit_options_for_storage(fit_options)
            persisted_result = normalize_fit_result_for_storage(fit_result)
            x_values = np.linspace(start, stop, 1000)
            y_values = evaluate_curve_expression(
                expression,
                x_values,
                limits=GENERATED_FIT_EXPRESSION_LIMITS,
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = deepcopy(controller.state.data)
        data.update(
            engine=engine.value,
            fit_type=deepcopy(fit_type),
            fit_options=persisted_options,
            fit_result=persisted_result,
            expression=str(expression),
            x_start=start,
            x_stop=stop,
        )
        change = controller.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )
        if change.ok and clear_pending:
            self._pending_source_changes.discard(controller.component_id)
        return change

    def update_display_range(
        self,
        component,
        x_start: float,
        x_stop: float,
    ) -> ComponentChange:
        """Update display range."""

        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        data = controller.state.data
        return self.apply_result(
            controller,
            engine=data["engine"],
            fit_type=data["fit_type"],
            fit_options=data["fit_options"],
            fit_result=data["fit_result"],
            expression=data["expression"],
            x_start=x_start,
            x_stop=x_stop,
            clear_pending=False,
        )


class TextRenderService:
    """Verify render-sensitive Text changes before publishing them."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        tex_enabled: Callable[[], bool] = tex_config.is_tex_enabled,
    ):
        self.registry = registry
        self.tex_enabled = tex_enabled
        self._tex_effective_overrides: set[str] = set()
        self._last_tex_availability: bool | None = None

    def effective_usetex(self, component_id: str) -> bool:
        """Return runtime TeX use without changing the persisted request."""

        controller = _controller(
            self.registry,
            component_id,
            TextController,
        )
        requested = bool(controller.state.properties.get("usetex"))
        return requested and component_id not in self._tex_effective_overrides

    def apply_tex_availability(
        self,
        enabled: bool,
        *,
        force: bool = False,
    ) -> ComponentBatchChange:
        """Apply a runtime-only effective TeX override to requested Text."""

        enabled = bool(enabled)
        if not force and self._last_tex_availability is enabled:
            return ComponentBatchChange((), True)
        self._last_tex_availability = enabled
        requested = [
            controller
            for controller in self.registry.query()
            if isinstance(controller, TextController)
            and bool(controller.state.properties.get("usetex"))
        ]
        if not requested:
            self._tex_effective_overrides.clear()
            return ComponentBatchChange((), True)
        targets = [controller.resolve_target() for controller in requested]
        figures = []
        seen: set[int] = set()
        for target in targets:
            figure = target.figure
            if id(figure) not in seen:
                seen.add(id(figure))
                figures.append(figure)
        try:
            for target in targets:
                target.set_usetex(enabled)
            if enabled:
                for figure in figures:
                    figure.canvas.draw()
            else:
                for figure in figures:
                    figure.canvas.draw_idle()
        except Exception as exc:
            # Enabling TeX failed its render probe. Keep every requested Text
            # on the known-safe Matplotlib renderer while preserving state.
            # A failed availability transition must still leave requested
            # Text on the known-safe non-TeX renderer.  Restoring ``True``
            # after a failed disable would contradict the global capability.
            safe_values = [False] * len(targets)
            for target, safe_value in zip(targets, safe_values):
                try:
                    target.set_usetex(safe_value)
                except Exception:
                    pass
            for figure in figures:
                try:
                    figure.canvas.draw_idle()
                except Exception:
                    pass
            self._tex_effective_overrides.update(
                controller.component_id for controller in requested
            )
            return ComponentBatchChange(
                (),
                False,
                message=(
                    "TeX availability changed, but the render probe failed; "
                    f"safe text rendering was kept: {exc}"
                ),
                rollback_complete=True,
            )
        if enabled:
            self._tex_effective_overrides.difference_update(
                controller.component_id for controller in requested
            )
        else:
            self._tex_effective_overrides.update(
                controller.component_id for controller in requested
            )
        return ComponentBatchChange((), True)

    def apply(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply the pending values through the component Controller."""

        controller = _controller(
            self.registry,
            component,
            TextController,
        )
        result = self.apply_many(((controller, properties),))
        if not result.changes:
            return _rejected(
                controller,
                result.message or "Text render failed.",
            )
        change = result.changes[-1] if not result.committed else result.changes[0]
        if not result.committed:
            return replace(
                change,
                message=result.message or (
                    "Text render failed; keeping the last valid text and "
                    "rendering settings."
                ),
            )
        return _notices(change, *result.notices)

    def apply_many(
        self,
        patches: Iterable[tuple[object, dict[str, Any]]],
    ) -> ComponentBatchChange:
        """Apply multiple Text patches in one transaction and render probe."""

        resolved: list[tuple[TextController, dict[str, Any]]] = []
        for component, properties in patches:
            controller = _controller(
                self.registry,
                component,
                TextController,
            )
            patch = dict(properties)
            if patch.get("usetex") and not self.tex_enabled():
                return ComponentBatchChange(
                    (
                        _rejected(
                            controller,
                            "Enable TeX before using TeX rendering for this text.",
                        ),
                    ),
                    False,
                    message=(
                        "Enable TeX before using TeX rendering for this text."
                    ),
                )
            resolved.append((controller, patch))

        if not resolved:
            return ComponentBatchChange((), True)

        glyph_messages: dict[str, str] = {}

        def verify() -> None:
            figures = []
            seen: set[int] = set()
            for controller, _properties in resolved:
                figure = controller.resolve_target().figure
                if id(figure) in seen:
                    continue
                seen.add(id(figure))
                figures.append(figure)
            for figure in figures:
                with (
                    capture_font_diagnostics() as captured,
                    warnings.catch_warnings(record=True) as caught,
                ):
                    warnings.simplefilter("always", UserWarning)
                    figure.canvas.draw()
                for warning in caught:
                    message = str(warning.message)
                    notice = normalize_font_diagnostic(message)
                    if (
                        notice is not None
                        and notice.key.startswith("matplotlib-glyph:")
                    ):
                        glyph_messages.setdefault(notice.key, notice.message)
                        tex_config.tex_logger().warning(
                            "Matplotlib text glyph warning action=component-render message=%s",
                            message,
                        )
                    else:
                        warnings.warn(
                            warning.message,
                            warning.category,
                            stacklevel=2,
                        )
                for notice in captured.notices:
                    if not notice.key.startswith("matplotlib-glyph:"):
                        continue
                    glyph_messages.setdefault(notice.key, notice.message)
                    tex_config.tex_logger().warning(
                        "Matplotlib text glyph warning action=component-render message=%s",
                        notice.message,
                    )
            if glyph_messages:
                codepoints = [
                    key.removeprefix("matplotlib-glyph:")
                    for key in glyph_messages
                    if key != "matplotlib-glyph:unknown"
                ]
                detail = (
                    "glyphs "
                    + ", ".join(f"U+{codepoint}" for codepoint in codepoints)
                    if codepoints
                    else "one or more glyphs"
                )
                raise ValueError(
                    f"The current text font cannot render {detail}; "
                    "the text was not updated."
                )

        result = self.registry.apply_transaction(
            tuple(
                ComponentMutation(
                    controller.component_id,
                    properties=properties,
                )
                for controller, properties in resolved
            ),
            verifier=verify,
        )
        if not result.committed:
            tex_config.tex_logger().warning(
                "Text render failed action=component-render error=%s",
                result.message,
            )
            detail = result.message.strip()
            message = (
                "Text render failed; keeping the last valid text and "
                "rendering settings."
            )
            if detail:
                message += f" {detail}"
            return replace(
                result,
                message=message,
            )
        return result


class ComponentDeletionService:
    """Prepare and commit every production physical deletion."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        handlers: DeletionHandlerRegistry | None = None,
        color_ledger: ColorConsumptionLedger | None = None,
    ):
        self.registry = registry
        self.handlers = handlers or production_deletion_handlers()
        self.color_ledger = color_ledger or ColorConsumptionLedger()

    def prepare(self, request: DeletionRequest) -> PreparedDeletion:
        """Validate IDs, ownership, subtree coverage, and survivor effects."""

        if not isinstance(request, DeletionRequest):
            raise TypeError("Deletion preparation requires DeletionRequest.")
        requested = _expand_colorbar_source_deletions(
            self.registry,
            _expand_primary_twin_deletions(
                self.registry,
                request.component_ids,
            ),
        )
        requested_controllers = {
            component_id: self.registry.get(component_id)
            for component_id in requested
        }
        requested_set = set(requested)
        roots: list[str] = []
        for component_id in requested:
            controller = requested_controllers[component_id]
            if controller.DELETION_POLICY is not DeletionPolicy.REMOVE:
                raise ComponentValidationError(
                    f"Component {component_id!r} uses deletion policy "
                    f"{controller.DELETION_POLICY.value!r}."
                )
            parent_id = controller.state.parent_id
            visited: set[str] = set()
            while parent_id is not None and parent_id not in requested_set:
                if parent_id in visited:
                    raise ComponentValidationError(
                        "Component tree contains an ancestor cycle."
                    )
                visited.add(parent_id)
                parent = (
                    self.registry.get(parent_id)
                    if parent_id in self.registry
                    else None
                )
                parent_id = parent.state.parent_id if parent is not None else None
            if parent_id is None:
                roots.append(component_id)

        removed: set[str] = set()
        postorder: list[str] = []

        def collect(component_id: str, visiting: set[str]) -> None:
            if component_id in visiting:
                raise ComponentValidationError(
                    "Component tree contains a deletion cycle."
                )
            if component_id in removed:
                return
            visiting.add(component_id)
            children = sorted(
                self.registry.children(component_id),
                key=lambda child: (child.state.order, child.component_id),
            )
            for child in children:
                collect(child.component_id, visiting)
            visiting.remove(component_id)
            removed.add(component_id)
            postorder.append(component_id)

        for component_id in roots:
            collect(component_id, set())

        for component_id in roots:
            controller = requested_controllers[component_id]
            handler = self.handlers.resolve(controller)
            if handler is None:
                state = controller.state
                raise ComponentValidationError(
                    f"No deletion handler is registered for {state.kind.value}/{state.role.value}."
                )
            owns_descendants = False
            for item_id in removed:
                if item_id == component_id:
                    continue
                parent_id = self.registry.get(item_id).state.parent_id
                visited: set[str] = set()
                while parent_id is not None and parent_id not in visited:
                    if parent_id == component_id:
                        owns_descendants = True
                        break
                    visited.add(parent_id)
                    parent = (
                        self.registry.get(parent_id)
                        if parent_id in self.registry
                        else None
                    )
                    parent_id = parent.state.parent_id if parent is not None else None
                if owns_descendants:
                    break
            if owns_descendants and not handler.owns_subtree:
                raise ComponentValidationError(
                    f"Leaf deletion handler for {component_id!r} cannot own "
                    "registered child components."
                )

        color_replacements, color_ledger_plan = self.color_ledger.prepare_deletion(
            self.registry, removed
        )
        replacements = [
            *_axes_replacements_for_deletion(self.registry, removed),
            *_layout_replacements_for_deletion(self.registry, removed),
            *color_replacements,
        ]
        replacement_by_id: dict[str, ComponentState] = {}
        changed_fields: dict[str, dict[str, Any]] = {}
        for state in replacements:
            base = self.registry.get(state.id).state
            pending = changed_fields.setdefault(state.id, {})
            for field in ("parent_id", "order", "selector", "properties", "data"):
                value = getattr(state, field)
                if value == getattr(base, field):
                    continue
                if field in pending and pending[field] != value:
                    raise ComponentValidationError(
                        f"Conflicting deletion effects for {state.id!r}."
                    )
                pending[field] = deepcopy(value)
            replacement_by_id[state.id] = base.clone(**pending)
        plan = DeletionPlan(
            requested_ids=requested,
            root_ids=tuple(roots),
            removed_ids=tuple(postorder),
            state_replacements=tuple(replacement_by_id.values()),
            color_ledger_plan=color_ledger_plan,
        )
        return PreparedDeletion(self, request, plan)

    def delete(
        self,
        request: DeletionRequest,
        *,
        verifier: Callable[[], None] | None = None,
    ) -> DeletionOutcome:
        """Prepare and atomically execute one deletion request."""

        try:
            prepared = self.prepare(request)
        except Exception as exc:
            return DeletionOutcome(
                committed=False,
                rollback_complete=True,
                message=str(exc),
            )
        return prepared.execute(verifier=verifier)


@dataclass(frozen=True, slots=True)
class ComponentDependencySnapshot:
    """Runtime-only Undo snapshot for dependents and parent palettes."""

    component_states: tuple[ComponentState, ...]
    axes_states: tuple[ComponentState, ...] = ()
    selected_component_id: str | None = None

    def __bool__(self) -> bool:
        return bool(self.component_states)

    def __len__(self) -> int:
        return len(self.component_states)

    def __iter__(self):
        return iter(self.component_states)


class ComponentDependencyService:
    """Query and delete table-bound components from Registry state."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        restore_state: Callable[[ComponentState], Any],
        deletion_service: ComponentDeletionService | None = None,
    ):
        self.registry = registry
        self.restore_state = restore_state
        self.deletion_service = deletion_service or ComponentDeletionService(registry)

    @staticmethod
    def _refs(state: ComponentState) -> set[ColumnRef]:
        refs: set[ColumnRef] = set()
        for key in ("x_ref", "y_ref", "color_ref", "size_ref", "position_ref"):
            try:
                refs.add(_column_ref(state.data[key]))
            except (KeyError, ValueError, TypeError):
                continue
        placement = state.data.get("placement")
        if not isinstance(placement, dict):
            return refs
        if placement.get("kind") != "between_table_ranges":
            return refs
        try:
            refs.add(_column_ref(placement.get("lower_ref")))
        except (TypeError, ValueError):
            pass
        for item in placement.get("upper_refs") or ():
            try:
                refs.add(_column_ref(item))
            except (TypeError, ValueError):
                continue
        return refs

    def dependent_states(
        self,
        refs: Iterable[ColumnRef],
    ) -> list[ComponentState]:
        """Return data-backed component states affected by this source."""

        requested = set(refs)
        return [
            controller.state.clone()
            for controller in self.registry.query(
                capabilities={"data_reference"}
            )
            if self._refs(controller.state).intersection(requested)
        ]

    def capture(
        self,
        refs: Iterable[ColumnRef],
        *,
        selected_component_id: str | None = None,
    ) -> ComponentDependencySnapshot:
        """Capture dependents and their exact parent Axes palette state."""

        states = tuple(self.dependent_states(refs))
        axes_ids = {
            ancestor.component_id
            for state in states
            if (
                ancestor := self.registry.ancestor(
                    state.id,
                    kind=ComponentKind.AXES,
                )
            )
            is not None
        }
        axes_states = tuple(
            self.registry.get(component_id).state.clone()
            for component_id in sorted(axes_ids)
        )
        return ComponentDependencySnapshot(
            states,
            axes_states,
            selected_component_id=(
                str(selected_component_id)
                if selected_component_id is not None
                else None
            ),
        )

    def restore_states(
        self,
        snapshots: ComponentDependencySnapshot | Iterable[ComponentState],
    ) -> None:
        """Restore stable IDs, data refs, and parent palette cursors."""

        states = (
            snapshots.component_states
            if isinstance(snapshots, ComponentDependencySnapshot)
            else tuple(snapshots)
        )
        with self.registry.registration_transaction() as transaction:
            for state in sorted(
                states,
                key=lambda item: (item.order, item.id),
            ):
                if state.id not in self.registry:
                    self.restore_state(state.clone())
            if isinstance(snapshots, ComponentDependencySnapshot):
                for axes_state in snapshots.axes_states:
                    if axes_state.id not in self.registry:
                        raise ComponentValidationError(
                            f"Parent Axes {axes_state.id!r} is unavailable."
                        )
                    controller = self.registry.get(axes_state.id)
                    transaction.watch_existing(axes_state.id)
                    change = controller.apply_state(axes_state.clone())
                    if not change.ok:
                        raise ComponentValidationError(
                            change.message
                            or f"Could not restore Axes {axes_state.id!r}."
                        )
