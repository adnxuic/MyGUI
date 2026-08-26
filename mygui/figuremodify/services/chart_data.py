"""Table-backed chart, interpolation, and fit services."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable
from typing import Any

import numpy as np

from mygui.database import (
    ColumnRef,
    DataPreprocessSpec,
    PreprocessedPair,
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
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    DataPlotController,
    FitCurveController,
    FitEngine,
    FunctionCurveController,
    InterpolationController,
    ReferenceMarksController,
    ObserverFailure,
    ScatterController,
    ScatterData,
    XYData,
)
from ._helpers import (
    _column_ref,
    _controller,
    _notices,
    _rejected,
    _warning,
)
from .colorbar import ColorbarService

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
                if controller.state.kind is ComponentKind.FIELD_2D:
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
