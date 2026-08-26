"""Project-scoped Undo/Redo for committed Figure component mutations.

History is deliberately a Qt-facing orchestration layer.  It records immutable
``ComponentState`` deltas from committed Registry events and replays them only
through the existing Controllers, domain Services, deletion coordinator, and
component materializers.  Controller modules remain independent from Qt
history types and commands never retain Matplotlib or QWidget objects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand

from mygui import status_messages
from mygui.figuremodify.components import (
    ChangeStatus,
    ColorbarController,
    ComponentBatchChange,
    ComponentChange,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRole,
    ComponentState,
    FitCurveController,
    FunctionCurveController,
    Field2DController,
    InterpolationController,
    LegendController,
    ScatterController,
    TextController,
    XYData,
)
from mygui.figuremodify.component_services import DeleteReason, DeletionRequest

if TYPE_CHECKING:
    from mygui.database import TableRepository
    from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas


class HistoryReplayError(RuntimeError):
    """Report a replay that could not prove a committed target state."""


@dataclass(frozen=True, slots=True)
class FigureSelectionSnapshot:
    """Runtime-only authoritative component and Axes selection."""

    current_component_id: str | None
    current_axes_component_id: str | None


@dataclass(frozen=True, slots=True)
class FigureRuntimeSnapshot:
    """Small runtime mementos not represented by ``ComponentState``."""

    color_consumption: dict[str, Any]
    fit_state: dict[str, Any]

    def clone(self) -> "FigureRuntimeSnapshot":
        return FigureRuntimeSnapshot(
            deepcopy(self.color_consumption),
            deepcopy(self.fit_state),
        )


@dataclass(frozen=True, slots=True)
class FigureHistoryDelta:
    """Only the Component states changed by one committed user intent."""

    before_states: tuple[ComponentState, ...]
    after_states: tuple[ComponentState, ...]
    selection_before: FigureSelectionSnapshot
    selection_after: FigureSelectionSnapshot
    runtime_before: FigureRuntimeSnapshot
    runtime_after: FigureRuntimeSnapshot

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "before_states",
            tuple(state.clone() for state in self.before_states),
        )
        object.__setattr__(
            self,
            "after_states",
            tuple(state.clone() for state in self.after_states),
        )
        object.__setattr__(self, "runtime_before", self.runtime_before.clone())
        object.__setattr__(self, "runtime_after", self.runtime_after.clone())

    @property
    def structural(self) -> bool:
        """Return whether component membership changes across this delta."""

        return {
            state.id for state in self.before_states
        } != {state.id for state in self.after_states}

    @staticmethod
    def _map(states: Iterable[ComponentState]) -> dict[str, ComponentState]:
        return {state.id: state for state in states}

    def before_map(self) -> dict[str, ComponentState]:
        return self._map(self.before_states)

    def after_map(self) -> dict[str, ComponentState]:
        return self._map(self.after_states)

    def merged_with(self, newer: "FigureHistoryDelta") -> "FigureHistoryDelta":
        """Keep the first before-state and the latest after-state."""

        if self.structural or newer.structural:
            raise ValueError("Structural Figure commands cannot be merged.")
        before = self.before_map()
        after = newer.after_map()
        if set(before) != set(after):
            raise ValueError("Merged Figure commands must affect the same states.")
        return FigureHistoryDelta(
            tuple(before[key] for key in sorted(before)),
            tuple(after[key] for key in sorted(after)),
            self.selection_before,
            newer.selection_after,
            self.runtime_before,
            newer.runtime_after,
        )


class FigureEditCommand(QUndoCommand):
    """Replay one already-committed Figure delta on the project stack."""

    _COMMAND_ID = 0x4D594748

    def __init__(
        self,
        text: str,
        service: "FigureHistoryService",
        delta: FigureHistoryDelta,
        *,
        merge_key: tuple[Any, ...] | None = None,
    ) -> None:
        super().__init__(str(text))
        self.service = service
        self.delta = delta
        self.merge_key = tuple(merge_key) if merge_key is not None else None
        self._first_redo = True
        self.last_succeeded = False

    def id(self) -> int:
        """Allow only explicitly keyed non-structural edits to merge."""

        if self.merge_key is None or self.delta.structural:
            return -1
        return self._COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802 - Qt API
        if (
            not isinstance(other, FigureEditCommand)
            or other.service is not self.service
            or self.merge_key is None
            or self.merge_key != other.merge_key
            or self.delta.structural
            or other.delta.structural
        ):
            return False
        try:
            self.delta = self.delta.merged_with(other.delta)
        except ValueError:
            return False
        self.setText(other.text())
        self.last_succeeded = other.last_succeeded
        return True

    def redo(self) -> None:
        """Apply the after-state, skipping QUndoStack's initial push call."""

        if self._first_redo:
            self._first_redo = False
            self.last_succeeded = True
            return
        self.last_succeeded = self.service.replay(
            self.delta,
            use_after=True,
            command_text=self.text(),
        )

    def undo(self) -> None:
        """Apply the before-state."""

        self.last_succeeded = self.service.replay(
            self.delta,
            use_after=False,
            command_text=self.text(),
        )


class FigureHistoryService:
    """Record user-intent Figure changes on one project's shared stack."""

    def __init__(
        self,
        *,
        repository: "TableRepository",
        project_id: str,
        canvas: "PyFigureCanvas",
        registry,
    ) -> None:
        self.repository = repository
        self.project_id = str(project_id)
        self.canvas = canvas
        self.registry = registry
        self._suspensions = 0
        self._capture_depth = 0
        self._captured_events: list[ComponentEvent] = []
        self._invalidated = False
        self._disposed = False
        self._interaction_context = None
        self._unsubscribe = registry.subscribe_batches(self._registry_events)
        self._known_states = self._states()
        self._stack = repository.undo_stack(self.project_id)
        self._last_stack_count = self._stack.count()
        self._stack.indexChanged.connect(self._stack_index_changed)

    @property
    def recording(self) -> bool:
        """Return whether a new outer user-intent capture may begin."""

        return not self._disposed and not self._invalidated and not self._suspensions

    def _registry_events(self, events: tuple[ComponentEvent, ...]) -> None:
        if self._capture_depth and not self._suspensions:
            self._captured_events.extend(events)
        elif not self._suspensions and self._known_states is not None:
            # Internal setup helpers may legitimately publish committed state
            # outside a user boundary (for example, ensuring an empty Legend).
            # Keep the boundary cache aligned without manufacturing a command.
            known = dict(self._known_states)
            for event in events:
                if event.after is None:
                    known.pop(event.component_id, None)
                else:
                    known[event.component_id] = event.after
            self._known_states = known

    def _stack_index_changed(self, _index: int) -> None:
        """Discard cached boundaries when an owner explicitly clears history."""

        count = self._stack.count()
        if not count and self._last_stack_count:
            self._known_states = None
        self._last_stack_count = count

    def _selection(self) -> FigureSelectionSnapshot:
        return FigureSelectionSnapshot(
            self.canvas.current_component_id,
            self.canvas.current_axes_component_id,
        )

    def _runtime(self) -> FigureRuntimeSnapshot:
        return FigureRuntimeSnapshot(
            self.canvas.color_consumption_ledger.history_snapshot(),
            self.canvas.fit_service.history_snapshot(),
        )

    def _states(self) -> dict[str, ComponentState]:
        """Read the persisted projection at one command boundary."""

        values = {}
        for controller in self.registry.query():
            try:
                state = controller.read_state()
            except Exception:
                state = controller.state
            values[state.id] = state
        return values

    @staticmethod
    def _axes_id_from_state(
        state: ComponentState,
        states: dict[str, ComponentState],
    ) -> str | None:
        """Resolve an Axes owner from one before/after state projection."""

        current = state
        visited: set[str] = set()
        while True:
            if current.kind is ComponentKind.AXES:
                return current.id
            parent_id = current.parent_id
            if parent_id is None or parent_id in visited:
                return None
            visited.add(parent_id)
            parent = states.get(parent_id)
            if parent is None:
                return None
            current = parent

    def _states_after_events(
        self,
        states_before: dict[str, ComponentState],
        events: tuple[ComponentEvent, ...],
        *,
        scan_all: bool,
    ) -> dict[str, ComponentState]:
        """Read every live owner that one committed event batch can affect."""

        structural_axes = any(
            event.kind in {ComponentEventKind.ADDED, ComponentEventKind.REMOVED}
            and (event.after or event.before).kind is ComponentKind.AXES
            for event in events
            if event.after is not None or event.before is not None
        )
        root_changed = any(
            (event.after or event.before).kind is ComponentKind.FIGURE
            for event in events
            if event.after is not None or event.before is not None
        )
        if scan_all or structural_axes or root_changed:
            return self._states()

        states_after = dict(states_before)
        candidates: set[str] = set()
        axes_ids: set[str] = set()
        for event in events:
            if event.after is None:
                states_after.pop(event.component_id, None)
            else:
                candidates.add(event.component_id)
            for state in (event.before, event.after):
                if state is None:
                    continue
                if state.kind is ComponentKind.COLORBAR:
                    source_id = state.data.get("source_component_id")
                    if isinstance(source_id, str):
                        candidates.add(source_id)
                axes_id = self._axes_id_from_state(state, states_before)
                if axes_id is None and state.id in self.registry:
                    owner = self.registry.ancestor(
                        state.id,
                        kind=ComponentKind.AXES,
                    )
                    axes_id = owner.component_id if owner is not None else None
                if axes_id is not None:
                    axes_ids.add(axes_id)

        for axes_id in axes_ids:
            if axes_id not in self.registry:
                continue
            candidates.add(axes_id)
            candidates.update(
                controller.component_id
                for controller in self.registry.descendants(axes_id)
                if controller.state.kind
                in {ComponentKind.TEXT, ComponentKind.LEGEND}
            )

        for component_id in candidates:
            if component_id not in self.registry:
                states_after.pop(component_id, None)
                continue
            controller = self.registry.get(component_id)
            try:
                states_after[component_id] = controller.read_state()
            except Exception:
                states_after[component_id] = controller.state
        return states_after

    @contextmanager
    def suspend_recording(self, *, resync: bool = True) -> Iterator[None]:
        """Prevent restore, refresh, and replay events from creating commands."""

        self._suspensions += 1
        try:
            yield
        finally:
            self._suspensions -= 1
            if resync and not self._suspensions:
                self._known_states = None

    @contextmanager
    def capture(
        self,
        text: str,
        *,
        merge_key: tuple[Any, ...] | None = None,
        scan_all: bool = False,
    ) -> Iterator[None]:
        """Capture committed events produced by one explicit user intent."""

        if not self.recording or self._capture_depth:
            self._capture_depth += 1
            try:
                yield
            finally:
                self._capture_depth -= 1
            return

        self._capture_depth = 1
        self._captured_events = []
        selection_before = self._selection()
        runtime_before = self._runtime()
        states_before = (
            self._states()
            if scan_all or self._known_states is None
            else self._known_states
        )
        succeeded = False
        try:
            yield
            succeeded = True
        finally:
            events, self._captured_events = self._captured_events, []
            self._capture_depth = 0
            if succeeded:
                self._commit_capture(
                    str(text),
                    events,
                    states_before,
                    selection_before,
                    runtime_before,
                    merge_key=merge_key,
                    scan_all=scan_all,
                )
            else:
                self._known_states = None

    def perform(
        self,
        text: str,
        operation: Callable[[], Any],
        *,
        merge_key: tuple[Any, ...] | None = None,
        scan_all: bool = False,
    ) -> Any:
        """Run and record one operation without changing its return contract."""

        with self.capture(text, merge_key=merge_key, scan_all=scan_all):
            return operation()

    def begin_interaction(self, text: str) -> bool:
        """Open a mouse/dialog interaction that commits in a later Qt event."""

        if (
            self._interaction_context is not None
            or not self.recording
            or self._capture_depth
        ):
            return False
        context = self.capture(str(text), scan_all=True)
        context.__enter__()
        self._interaction_context = context
        return True

    def end_interaction(self) -> None:
        """Commit the currently open interaction, if any."""

        context, self._interaction_context = self._interaction_context, None
        if context is not None:
            context.__exit__(None, None, None)

    def cancel_interaction(self) -> None:
        """Discard the currently open interaction without adding history."""

        context, self._interaction_context = self._interaction_context, None
        if context is None:
            return
        cancelled = RuntimeError("Figure history interaction cancelled.")
        context.__exit__(RuntimeError, cancelled, None)

    @staticmethod
    def _state_delta(
        before_states: dict[str, ComponentState],
        after_states: dict[str, ComponentState],
    ) -> tuple[tuple[ComponentState, ...], tuple[ComponentState, ...]]:
        changed_ids = sorted(
            component_id
            for component_id in set(before_states) | set(after_states)
            if before_states.get(component_id) != after_states.get(component_id)
        )
        before = tuple(
            before_states[component_id]
            for component_id in changed_ids
            if component_id in before_states
        )
        after = tuple(
            after_states[component_id]
            for component_id in changed_ids
            if component_id in after_states
        )
        return before, after

    def _commit_capture(
        self,
        text: str,
        events: Iterable[ComponentEvent],
        states_before: dict[str, ComponentState],
        selection_before: FigureSelectionSnapshot,
        runtime_before: FigureRuntimeSnapshot,
        *,
        merge_key: tuple[Any, ...] | None,
        scan_all: bool,
    ) -> None:
        committed_events = tuple(events)
        runtime_after = self._runtime()
        if not committed_events and runtime_before == runtime_after and not scan_all:
            return
        if committed_events or scan_all:
            states_after = self._states_after_events(
                states_before,
                committed_events,
                scan_all=scan_all,
            )
            self._known_states = states_after
        else:
            states_after = states_before
        before, after = self._state_delta(states_before, states_after)
        if (
            not before
            and not after
            and runtime_before == runtime_after
        ):
            return
        delta = FigureHistoryDelta(
            before,
            after,
            selection_before,
            self._selection(),
            runtime_before,
            runtime_after,
        )
        command = FigureEditCommand(
            text,
            self,
            delta,
            merge_key=None if delta.structural else merge_key,
        )
        self.repository.push(self.project_id, command)

    @staticmethod
    def _require_result(
        result: ComponentChange | ComponentBatchChange,
        fallback: str,
    ) -> None:
        if isinstance(result, ComponentBatchChange):
            if result.committed and all(change.ok for change in result.changes):
                return
            raise HistoryReplayError(result.message or fallback)
        if result.ok and result.status is not ChangeStatus.REJECTED:
            return
        raise HistoryReplayError(result.message or fallback)

    def _apply_specialized_state(self, state: ComponentState) -> None:
        """Restore one live target through its established domain boundary."""

        controller = self.registry.get(state.id)
        try:
            current = controller.read_state()
        except Exception:
            current = controller.state
        if current == state:
            return

        if isinstance(controller, TextController):
            result = self.canvas.text_render_service.apply(
                controller,
                state.properties,
            )
            self._require_result(result, "Could not restore Text state.")
        elif isinstance(controller, LegendController):
            result = self.canvas.axes_commands.apply_legend_properties(
                controller,
                state.properties,
            )
            self._require_result(result, "Could not restore Legend state.")
        elif isinstance(controller, ColorbarController):
            result = self.canvas.colorbar_service.apply_properties(
                controller,
                state.properties,
            )
            self._require_result(result, "Could not restore Colorbar state.")
        elif isinstance(controller, FunctionCurveController):
            data = state.data
            result = self.canvas.function_curve_service.update(
                controller,
                data["expression"],
                data["x_start"],
                data["x_stop"],
            )
            self._require_result(result, "Could not restore Function Curve data.")
        elif isinstance(controller, InterpolationController):
            data = state.data
            result = self.canvas.interpolation_service.configure(
                controller,
                x_ref=data["x_ref"],
                y_ref=data["y_ref"],
                preprocess=data["preprocess"],
                method=data["method"],
                k=data["k"],
                samples=data["samples"],
                lam=data["lam"],
                lam_auto=data["lam_auto"],
            )
            self._require_result(result, "Could not restore Interpolation data.")
        elif isinstance(controller, FitCurveController):
            data = state.data
            result = self.canvas.fit_service.set_sources(
                controller,
                data["x_ref"],
                data["y_ref"],
                data["preprocess"],
            )
            self._require_result(result, "Could not restore Fit sources.")
            pair = self.canvas.fit_service.resolve_sources(controller)
            if data.get("expression"):
                result = self.canvas.fit_service.apply_result(
                    controller,
                    engine=data["engine"],
                    fit_type=data["fit_type"],
                    fit_options=data["fit_options"],
                    fit_result=data["fit_result"],
                    expression=data["expression"],
                    x_start=data["x_start"],
                    x_stop=data["x_stop"],
                )
            else:
                result = controller.apply_role_data(
                    data,
                    drawable=XYData(pair.x, pair.y),
                )
            self._require_result(result, "Could not restore Fit data.")
        elif isinstance(controller, ScatterController) and "x_ref" in state.data:
            data = state.data
            result = self.canvas.chart_data_service.set_refs(
                controller,
                data["x_ref"],
                data["y_ref"],
                data["preprocess"],
            )
            self._require_result(result, "Could not restore Scatter data.")
            result = self.canvas.chart_data_service.configure_scatter_mapping(
                controller,
                color_ref=data.get("color_ref"),
                size_ref=data.get("size_ref"),
                color_mapping=state.properties["color_mapping"],
                size_mapping=state.properties["size_mapping"],
            )
            self._require_result(result, "Could not restore Scatter mapping.")
        elif isinstance(controller, Field2DController):
            data = state.data
            if current.data != state.data:
                result = self.canvas.field_2d_service.set_refs(
                    controller,
                    data["x_ref"],
                    data["y_ref"],
                    data["z_ref"],
                )
                self._require_result(result, "Could not restore FIELD_2D data.")
            if current.properties != state.properties:
                result = self.canvas.field_2d_service.apply_properties(
                    controller,
                    state.properties,
                )
                self._require_result(result, "Could not restore FIELD_2D properties.")
        elif state.role is ComponentRole.DATA_PLOT:
            data = state.data
            result = self.canvas.chart_data_service.set_refs(
                controller,
                data["x_ref"],
                data["y_ref"],
                data["preprocess"],
            )
            self._require_result(result, "Could not restore Plot data.")
        else:
            result = controller.apply_state(state)
            self._require_result(result, f"Could not restore component {state.id}.")

        if controller.state != state:
            result = controller.apply_state(state)
            self._require_result(result, f"Could not restore component {state.id}.")

    def _apply_states(self, states: Iterable[ComponentState]) -> None:
        for state in sorted(
            states,
            key=lambda item: (
                item.kind is not ComponentKind.FIGURE,
                item.kind is not ComponentKind.AXES,
                item.order,
                item.id,
            ),
        ):
            self._apply_specialized_state(state)

    def _restore_runtime(self, snapshot: FigureRuntimeSnapshot) -> None:
        self.canvas.color_consumption_ledger.restore_history_snapshot(
            snapshot.color_consumption
        )
        self.canvas.fit_service.restore_history_snapshot(snapshot.fit_state)

    def _apply_target(
        self,
        delta: FigureHistoryDelta,
        *,
        use_after: bool,
    ) -> None:
        desired = delta.after_map() if use_after else delta.before_map()
        affected = set(delta.before_map()) | set(delta.after_map())
        target_selection = (
            delta.selection_after if use_after else delta.selection_before
        )
        target_runtime = delta.runtime_after if use_after else delta.runtime_before

        current_ids = {component_id for component_id in affected if component_id in self.registry}
        removed_ids = current_ids - set(desired)
        if removed_ids:
            roots = tuple(
                component_id
                for component_id in sorted(removed_ids)
                if self.registry.get(component_id).state.parent_id not in removed_ids
            )
            request = DeletionRequest(
                roots,
                anchor_id=roots[0] if roots else None,
                reason=DeleteReason.PROGRAMMATIC,
            )
            deleted = self.canvas.deletion_coordinator.delete(
                request,
                present_success=False,
                present_result=False,
                fallback_id=target_selection.current_component_id,
            )
            if not deleted:
                outcome = self.canvas.deletion_coordinator.last_outcome
                raise HistoryReplayError(
                    outcome.message
                    if outcome is not None and outcome.message
                    else "Component deletion was rejected during history replay."
                )

        pre_materialize = [
            state
            for state in desired.values()
            if state.id in self.registry
            and state.kind in {ComponentKind.FIGURE, ComponentKind.AXES}
        ]
        self._apply_states(pre_materialize)

        added_ids = set(desired) - {
            controller.component_id for controller in self.registry.query()
        }
        if added_ids:
            full_target = {
                controller.component_id: controller.state
                for controller in self.registry.query()
                if controller.component_id not in affected
            }
            full_target.update(desired)
            self.canvas.materialize_history_states(
                tuple(full_target.values()),
                added_ids,
            )

        self._apply_states(desired.values())
        self.canvas.axes_layout_service.restore_persisted_geometry()
        self.canvas.axes_layout_service.restore_runtime_relationships(refresh=True)
        self._restore_runtime(target_runtime)
        self.registry.validate_tree()
        self.registry.validate_axes_targets()
        self.canvas.validate_component_snapshot()

        component_id = target_selection.current_component_id
        if component_id is None or component_id not in self.registry:
            component_id = self.canvas.root_component_id
        if self.canvas.current_component_id != component_id:
            if not self.canvas.select_component(component_id):
                raise HistoryReplayError(
                    f"Could not restore selection {component_id!r}."
                )
        axes_id = target_selection.current_axes_component_id
        self.canvas.current_axes_component_id = (
            axes_id if axes_id in self.registry else self.canvas._axes_ancestor_id(component_id)
        )

    def replay(
        self,
        delta: FigureHistoryDelta,
        *,
        use_after: bool,
        command_text: str,
    ) -> bool:
        """Atomically replay one direction and invalidate on uncertain failure."""

        if self._invalidated or self._disposed:
            return False
        direction = "redo" if use_after else "undo"
        self.canvas.message_presenter.discard_pending()
        try:
            self._replay_target(delta, use_after=use_after)
        except Exception as exc:
            rollback_error = None
            try:
                self._replay_target(delta, use_after=not use_after)
            except Exception as rollback_exc:
                rollback_error = rollback_exc
            self.canvas.message_presenter.discard_pending()
            detail = str(exc)
            if rollback_error is not None:
                detail += f" Replay rollback was incomplete: {rollback_error}"
            status_messages.show_error(
                f"Could not {direction} {command_text}: {detail}"
            )
            self.invalidate()
            return False
        desired = delta.after_map() if use_after else delta.before_map()
        affected = set(delta.before_map()) | set(delta.after_map())
        if self._known_states is None:
            self._known_states = self._states()
        else:
            known = dict(self._known_states)
            for component_id in affected:
                known.pop(component_id, None)
            known.update(desired)
            self._known_states = known
        self.canvas.message_presenter.discard_pending()
        status_messages.show_success(
            f"{'Redid' if use_after else 'Undid'} {command_text}"
        )
        return True

    def _replay_target(
        self,
        delta: FigureHistoryDelta,
        *,
        use_after: bool,
    ) -> None:
        """Apply then reconcile after coalesced Matplotlib updates flush."""

        with (
            self.suspend_recording(resync=False),
            self.registry.batch_events(),
            self.registry.batch_updates(),
            self.canvas.in_axes_service.suspend_refresh(),
        ):
            self._apply_target(delta, use_after=use_after)
        # AUTOSCALE and legend refreshes run when ``batch_updates`` exits.
        # Re-read and reapply the persisted target once without another
        # deferred update batch so those derived effects cannot drift state.
        with (
            self.suspend_recording(resync=False),
            self.registry.batch_events(),
            self.canvas.in_axes_service.suspend_refresh(),
        ):
            self._apply_target(delta, use_after=use_after)

    def invalidate(self) -> None:
        """Disable and asynchronously clear a cursor whose replay failed."""

        if self._invalidated:
            return
        self._invalidated = True
        stack = self.repository.undo_stack(self.project_id)

        def clear() -> None:
            stack.clear()
            self._invalidated = False

        QTimer.singleShot(0, clear)

    def undo(self) -> None:
        """Undo the latest Table or Figure command for this project."""

        if not self._invalidated:
            self.repository.undo_stack(self.project_id).undo()

    def redo(self) -> None:
        """Redo the latest Table or Figure command for this project."""

        if not self._invalidated:
            self.repository.undo_stack(self.project_id).redo()

    def dispose(self) -> None:
        """Detach the Registry observer without changing the project stack."""

        if self._disposed:
            return
        self.cancel_interaction()
        self._disposed = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        try:
            self._stack.indexChanged.disconnect(self._stack_index_changed)
        except (RuntimeError, TypeError):
            pass
        self._captured_events.clear()
        self._known_states = None
        self._interaction_context = None
        self.canvas = None
        self.registry = None
        self.repository = None
        self._stack = None


__all__ = [
    "FigureEditCommand",
    "FigureHistoryDelta",
    "FigureHistoryService",
    "FigureRuntimeSnapshot",
    "FigureSelectionSnapshot",
    "HistoryReplayError",
]
