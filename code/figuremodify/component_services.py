"""Application services for Controller-managed Matplotlib components.

Controllers remain independent from Qt and the table repository.  These
services adapt application data, fitting and render validation to the atomic
Controller mutation API without becoming a second state store.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import re
import warnings
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from matplotlib.axes import Axes

from code import tex_config
from code.database import ColumnRef
from code.database.interpolate_func import interpolate_curve
from code.database.safe_expression import evaluate_curve_expression
from code.figuremodify.components import (
    AxesController,
    ChangeStatus,
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentNotice,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    MessageLevel,
    ScatterController,
    TextController,
    XYData,
)
from code.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
)


def _controller(
    registry: ComponentRegistry,
    value,
    expected_type=None,
):
    result = registry.get(value) if isinstance(value, str) else value
    if expected_type is not None and not isinstance(result, expected_type):
        raise TypeError(
            f"Expected {expected_type.__name__}, got "
            f"{type(result).__name__}."
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


def _column_ref(value: ColumnRef | dict[str, Any]) -> ColumnRef:
    return value if isinstance(value, ColumnRef) else ColumnRef.from_dict(value)


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
        axis_name = "y" if side in {"left", "right"} else "x"
        axis_role = (
            ComponentRole.X_AXIS
            if axis_name == "x"
            else ComponentRole.Y_AXIS
        )
        spine = self.semantic(
            axes_id,
            kind=ComponentKind.SPINE,
            selector={"name": side},
        )
        axis = self.semantic(
            axes_id,
            kind=ComponentKind.AXIS,
            role=axis_role,
        )
        return self.registry.apply_transaction(
            (
                ComponentMutation(
                    spine.component_id,
                    properties={"visible": bool(visible)},
                ),
                ComponentMutation(
                    axis.component_id,
                    properties={"visible": bool(visible)},
                ),
            )
        )

    def ensure_legend(self, axes_id: str):
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
        legend = axes.legend(handles, labels)
        self.registry.locator.bind(controller.component_id, legend)
        return controller, legend

    def set_legend_position(
        self,
        axes_id: str,
        position,
    ) -> ComponentChange:
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

    def cycle_state(self, axes_id: str) -> ColorCycleState:
        value = self._axes(axes_id).state.properties.get("color_cycle")
        return ColorCycleState.from_dict(value)

    def peek_color(self, axes_id: str) -> ColorSelection:
        return self.cycle_state(axes_id).peek()

    def commit_color_selection(
        self,
        axes_id: str,
        selection: ColorSelection,
    ) -> ComponentChange:
        cycle = self.cycle_state(axes_id)
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
        controllers = self.registry.query(
            capabilities={"color", "data"},
            parent_id=axes_id,
            recursive=True,
        )
        if not controllers:
            return ComponentBatchChange(
                (),
                True,
                notices=(
                    _warning(
                        "The current axes has no color-capable chart "
                        "components."
                    ),
                ),
                message="No color-capable components.",
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
        return self.registry.apply_transaction(mutations)


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

    @staticmethod
    def refs_for(controller) -> tuple[ColumnRef, ColumnRef]:
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
        if (
            not self.repository.has_ref(x_ref)
            or not self.repository.has_ref(y_ref)
        ):
            raise ValueError("Chart data source was removed.")

    def _pair(self, controller, x_ref, y_ref):
        self._validate_refs(x_ref, y_ref)
        if isinstance(controller, DataPlotController):
            return self.repository.line_pair(x_ref, y_ref)
        return self.repository.valid_pair(x_ref, y_ref)

    def set_refs(
        self,
        component,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
    ) -> ComponentChange:
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
            pair = self._pair(controller, x_ref, y_ref)
        except Exception as exc:
            return _rejected(controller, str(exc))
        change = controller.apply_role_data(
            {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
            },
            drawable=XYData(pair.x, pair.y),
        )
        notices = []
        if pair.missing_count:
            notices.append(
                _warning(
                    f"Ignored or masked {pair.missing_count} rows with "
                    "missing values."
                )
            )
        if change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning(
                    "Chart has no valid data yet; its editor and style "
                    "were kept."
                )
            )
        return _notices(change, *notices)

    def refresh(self, component) -> ComponentChange:
        controller = _controller(self.registry, component)
        try:
            x_ref, y_ref = self.refs_for(controller)
        except Exception as exc:
            return _rejected(controller, str(exc))
        return self.set_refs(controller, x_ref, y_ref)

    def refresh_affected(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> list[ComponentChange]:
        changed = set(changed_columns)
        results: list[ComponentChange] = []
        with self.registry.batch_updates():
            for controller in self.registry.query(
                capabilities={"data_reference", "auto_refresh"}
            ):
                try:
                    refs = set(self.refs_for(controller))
                except Exception:
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
        preserve_on_failure: bool = True,
    ) -> ComponentChange:
        controller = _controller(
            self.registry,
            component,
            InterpolationController,
        )
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            if (
                not self.repository.has_ref(x_ref)
                or not self.repository.has_ref(y_ref)
            ):
                raise ValueError("Interpolation data source was removed.")
            pair = self.repository.valid_pair(x_ref, y_ref)
            data = {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
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
        if pair.missing_count:
            notices.append(
                _warning(
                    f"Interpolation ignored {pair.missing_count} rows "
                    "with missing values."
                )
            )
        if change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning(
                    "Interpolation has no valid data yet; its editor and "
                    "style were kept."
                )
            )
        return _notices(change, *notices)

    def refresh(self, component) -> ComponentChange:
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

    def set_sources(
        self,
        component,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
    ) -> ComponentChange:
        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            if (
                not self.repository.has_ref(x_ref)
                or not self.repository.has_ref(y_ref)
            ):
                raise ValueError("Fit data source was removed.")
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = deepcopy(controller.state.data)
        data.update(
            x_ref=x_ref.to_dict(),
            y_ref=y_ref.to_dict(),
        )
        return controller.apply_mutation(
            ComponentMutation(controller.component_id, data=data)
        )

    def next_request(self, component_id: str) -> int:
        generation = self._request_generation.get(component_id, 0) + 1
        self._request_generation[component_id] = generation
        return generation

    def request_is_current(
        self,
        component_id: str,
        generation: int,
    ) -> bool:
        return (
            component_id in self.registry
            and self._request_generation.get(component_id) == generation
        )

    def cancel(self, component_id: str) -> None:
        self._request_generation[component_id] = (
            self._request_generation.get(component_id, 0) + 1
        )

    def apply_result(
        self,
        component,
        *,
        engine: str,
        fit_type,
        fit_options,
        fit_result,
        expression: str,
        x_start: float,
        x_stop: float,
    ) -> ComponentChange:
        controller = _controller(
            self.registry,
            component,
            FitCurveController,
        )
        try:
            start = float(x_start)
            stop = float(x_stop)
            x_values = np.linspace(start, stop, 1000)
            y_values = evaluate_curve_expression(expression, x_values)
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = deepcopy(controller.state.data)
        data.update(
            engine=engine,
            fit_type=deepcopy(fit_type),
            fit_options=deepcopy(fit_options),
            fit_result=deepcopy(fit_result),
            expression=str(expression),
            x_start=start,
            x_stop=stop,
        )
        return controller.apply_role_data(
            data,
            drawable=XYData(x_values, y_values),
        )

    def update_display_range(
        self,
        component,
        x_start: float,
        x_stop: float,
    ) -> ComponentChange:
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
        )


def _missing_glyph_message(message: str) -> str | None:
    if "Glyph" not in message or "missing from font" not in message:
        return None
    match = re.search(r"Glyph\s+(\d+)", message)
    if not match:
        return (
            "Current font is missing a glyph; text may render "
            "incorrectly."
        )
    codepoint = int(match.group(1))
    return (
        f"Current font is missing glyph U+{codepoint:04X}; "
        "text may render incorrectly."
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

    def apply(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
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
                message=(
                    "Text render failed; keeping the last valid text "
                    "and rendering settings."
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

        glyph_notices: list[ComponentNotice] = []

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
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", UserWarning)
                    figure.canvas.draw()
                for warning in caught:
                    message = str(warning.message)
                    glyph_message = _missing_glyph_message(message)
                    if glyph_message is not None:
                        tex_config.tex_logger().warning(
                            "Matplotlib text glyph warning "
                            "action=component-render message=%s",
                            message,
                        )
                        glyph_notices.append(_warning(glyph_message))
                    else:
                        warnings.warn(
                            warning.message,
                            warning.category,
                            stacklevel=2,
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
            return replace(
                result,
                message=(
                    "Text render failed; keeping the last valid text "
                    "and rendering settings."
                ),
            )
        return replace(
            result,
            notices=tuple(result.notices) + tuple(glyph_notices),
        )


class ComponentDependencyService:
    """Query and delete table-bound components from Registry state."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        restore_state: Callable[[ComponentState], Any],
    ):
        self.registry = registry
        self.restore_state = restore_state

    @staticmethod
    def _refs(state: ComponentState) -> set[ColumnRef]:
        refs: set[ColumnRef] = set()
        for key in ("x_ref", "y_ref"):
            try:
                refs.add(_column_ref(state.data[key]))
            except (KeyError, ValueError, TypeError):
                continue
        return refs

    def dependent_states(
        self,
        refs: Iterable[ColumnRef],
    ) -> list[ComponentState]:
        requested = set(refs)
        return [
            controller.state
            for controller in self.registry.query(
                capabilities={"data_reference"}
            )
            if self._refs(controller.state).intersection(requested)
        ]

    def delete_states(
        self,
        snapshots: Iterable[ComponentState],
    ) -> None:
        with self.registry.batch_updates():
            for state in snapshots:
                if state.id in self.registry:
                    self.registry.delete(state.id)

    def restore_states(
        self,
        snapshots: Iterable[ComponentState],
    ) -> None:
        for state in sorted(
            snapshots,
            key=lambda item: (item.order, item.id),
        ):
            if state.id not in self.registry:
                self.restore_state(state.clone())
