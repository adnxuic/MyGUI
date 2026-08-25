"""Reflection-set and reference-guide domain services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PolyCollection

from mygui.database import (
    ColumnRef,
    TableRepository,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    ReferenceBandController,
    ReferenceLineController,
    ReferenceMarksController,
    normalize_reference_marks_data,
    reflection_placement_is_automatic,
)
from mygui.figuremodify.reference_marks_data import (
    between_table_range_extrema,
    merged_reference_positions,
)
from mygui.figuremodify.x_axis_tight import apply_tight_xlim
from mygui.figuremodify.y_axis_reserve import apply_y_lower_reserve
from ._helpers import (
    _column_ref,
    _controller,
    _rejected,
)

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
