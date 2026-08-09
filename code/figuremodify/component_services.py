"""Application services for Controller-managed Matplotlib components.

Controllers remain independent from Qt and the table repository.  These
services adapt application data, fitting and render validation to the atomic
Controller mutation API without becoming a second state store.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
import re
import warnings
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from matplotlib.axes import Axes

from code import tex_config
from code.database import (
    ColumnRef,
    DataPreprocessSpec,
    PreprocessedPair,
    resolve_preprocessed_pair,
)
from code.database.interpolate_func import interpolate_curve
from code.database.safe_expression import evaluate_curve_expression
from code.figuremodify.components import (
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
    DataPlotController,
    DeletionPolicy,
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
    normalize_color,
)
from code.figuremodify.style_base.creation_defaults import (
    MATPLOTLIB_STYLE_PALETTE_SOURCE,
    resolve_style_palette,
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


def _color_cycle_replacements_for_deletion(
    registry: ComponentRegistry,
    component_ids: Iterable[str],
    *,
    is_palette_component: Callable[[Any], bool] | None = None,
) -> tuple[ComponentState, ...]:
    """Release palette slots consumed by chart components being removed.

    The replacement states are submitted with the structural deletion, so a
    failed detach/tree verification restores the exact original cursor.
    """

    requested = tuple(
        dict.fromkeys(str(component_id) for component_id in component_ids)
    )
    existing = {
        component_id: registry.get(component_id)
        for component_id in requested
        if component_id in registry
    }
    requested_set = set(existing)
    roots = []
    for component_id, controller in existing.items():
        parent_id = controller.state.parent_id
        visited: set[str] = set()
        while parent_id is not None and parent_id not in requested_set:
            if parent_id in visited:
                return ()
            visited.add(parent_id)
            parent = registry.get(parent_id) if parent_id in registry else None
            parent_id = parent.state.parent_id if parent is not None else None
        if parent_id is None:
            roots.append(component_id)

    removed_ids: set[str] = set()
    for component_id in roots:
        removed_ids.add(component_id)
        removed_ids.update(
            controller.component_id
            for controller in registry.descendants(component_id)
        )

    is_palette_component = is_palette_component or (
        lambda controller: {"color", "data"}.issubset(
            controller.capabilities()
        )
    )
    deleted_by_axes: dict[str, list[Any]] = {}
    for component_id in removed_ids:
        controller = registry.get(component_id)
        if not is_palette_component(controller):
            continue
        parent_id = controller.state.parent_id
        if parent_id is None or parent_id in removed_ids:
            continue
        try:
            parent = registry.get(parent_id)
        except Exception:
            continue
        if parent.state.kind is not ComponentKind.AXES:
            continue
        deleted_by_axes.setdefault(parent_id, []).append(controller)

    replacements: list[ComponentState] = []
    for axes_id, deleted in deleted_by_axes.items():
        axes = registry.get(axes_id)
        cycle = ColorCycleState.from_dict(
            axes.state.properties.get("color_cycle")
        )
        palette = cycle.active_palette
        if palette is None:
            continue

        occupied: set[int] = set()
        for controller in registry.query(
            parent_id=axes_id,
            recursive=True,
        ):
            if not is_palette_component(controller):
                continue
            if controller.component_id in removed_ids:
                continue
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

        released: list[tuple[int, int, str]] = []
        for controller in deleted:
            state = controller.state
            try:
                color = normalize_color(state.properties["color"])
            except (KeyError, TypeError, ValueError):
                continue
            matching = [
                index
                for index, palette_color in enumerate(palette.colors)
                if palette_color == color
            ]
            if not matching:
                # A one-off custom color never advanced this palette.
                continue
            expected = int(state.order) % len(palette.colors)
            index = expected if expected in matching else matching[0]
            released.append((int(state.order), index, state.id))

        available = [
            index
            for _order, index, _component_id in sorted(released)
            if index not in occupied
        ]
        if not available:
            continue
        next_index = available[0]
        if cycle.next_index == next_index:
            continue
        cycle.activate(palette, next_index)
        state = axes.state
        properties = dict(state.properties)
        properties["color_cycle"] = cycle.to_dict()
        replacements.append(state.clone(properties=properties))
    return tuple(replacements)


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
        if (
            cached_state.order == index
            and cached_state.selector.get("index") == index
        ):
            continue
        live_state = controller.read_state(strict=True)
        replacements.append(
            live_state.clone(
                order=index,
                selector={"index": index},
            )
        )
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
            and active.source != MATPLOTLIB_STYLE_PALETTE_SOURCE
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
            active.source != MATPLOTLIB_STYLE_PALETTE_SOURCE
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
        if (
            not self.repository.has_ref(x_ref)
            or not self.repository.has_ref(y_ref)
        ):
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
        change = controller.apply_role_data(
            data,
            drawable=XYData(pair.x, pair.y),
        )
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
                _warning(
                    "Chart has no valid data yet; its editor and style "
                    "were kept."
                )
            )
        return _notices(change, *notices)

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
            if (
                not self.repository.has_ref(x_ref)
                or not self.repository.has_ref(y_ref)
            ):
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
                    "Interpolation has no valid data yet; its editor and "
                    "style were kept."
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
            if (
                not self.repository.has_ref(x_ref)
                or not self.repository.has_ref(y_ref)
            ):
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
        message = "Fit preprocessing updated; run fitting to recompute."
        if pair.excluded_count:
            message = (
                f"Fit preprocessing excluded {pair.excluded_count} rows; "
                "run fitting to recompute."
            )
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
        engine: str,
        fit_type,
        fit_options,
        fit_result,
        expression: str,
        x_start: float,
        x_stop: float,
    ) -> ComponentChange:
        """Apply a completed result only if it belongs to the current request."""

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


class ComponentDeletionService:
    """Prepare and commit every production physical deletion."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        handlers: DeletionHandlerRegistry | None = None,
    ):
        self.registry = registry
        self.handlers = handlers or production_deletion_handlers()

    def _palette_component(self, controller) -> bool:
        handler = self.handlers.resolve(controller)
        return bool(
            handler
            and any(
                isinstance(effect, ColorCycleDeletionEffect)
                for effect in handler.effects
            )
        )

    def prepare(self, request: DeletionRequest) -> PreparedDeletion:
        """Validate IDs, ownership, subtree coverage, and survivor effects."""

        if not isinstance(request, DeletionRequest):
            raise TypeError("Deletion preparation requires DeletionRequest.")
        requested = request.component_ids
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
                    "No deletion handler is registered for "
                    f"{state.kind.value}/{state.role.value}."
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
                    parent_id = (
                        parent.state.parent_id if parent is not None else None
                    )
                if owns_descendants:
                    break
            if owns_descendants and not handler.owns_subtree:
                raise ComponentValidationError(
                    f"Leaf deletion handler for {component_id!r} cannot own "
                    "registered child components."
                )

        replacements = [
            *_axes_replacements_for_deletion(self.registry, removed),
            *_color_cycle_replacements_for_deletion(
                self.registry,
                roots,
                is_palette_component=self._palette_component,
            ),
        ]
        replacement_by_id: dict[str, ComponentState] = {}
        for state in replacements:
            previous = replacement_by_id.get(state.id)
            if previous is not None and previous != state:
                raise ComponentValidationError(
                    f"Conflicting deletion effects for {state.id!r}."
                )
            replacement_by_id[state.id] = state
        plan = DeletionPlan(
            requested_ids=requested,
            root_ids=tuple(roots),
            removed_ids=tuple(postorder),
            state_replacements=tuple(replacement_by_id.values()),
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

    def delete_states(
        self,
        snapshots: ComponentDependencySnapshot | Iterable[ComponentState],
    ) -> ComponentBatchChange:
        """Delete table dependents through the shared physical transaction."""

        states = (
            snapshots.component_states
            if isinstance(snapshots, ComponentDependencySnapshot)
            else tuple(snapshots)
        )
        ids = tuple(
            state.id
            for state in states
            if state.id in self.registry
        )
        return self.deletion_service.delete(
            DeletionRequest(ids, reason=DeleteReason.DATA_DEPENDENCY)
        ).as_batch_change()

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
                change = self.registry.get(axes_state.id).apply_state(
                    axes_state.clone()
                )
                if not change.ok:
                    raise ComponentValidationError(
                        change.message
                        or f"Could not restore Axes {axes_state.id!r}."
                    )
