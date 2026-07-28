"""Runtime registry and update coordinator for Figure components."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
import json
from typing import TYPE_CHECKING, Any

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .base import apply_update_impacts
from .errors import ComponentNotFoundError, ComponentValidationError
from .locator import ComponentLocator
from .models import (
    ChangeStatus,
    ComponentBatchChange,
    ComponentChange,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    UpdateImpact,
)

if TYPE_CHECKING:
    from .base import ComponentController


_STANDARD_SPINES = frozenset({"left", "right", "bottom", "top"})
_AXIS_NAMES = frozenset({"x", "y"})
_TICK_LEVELS = frozenset({"major", "minor"})
_CHART_KINDS = frozenset({ComponentKind.LINE, ComponentKind.SCATTER})


class ComponentRegistry:
    """Owns controllers, their hierarchy and coalesced redraw work."""

    def __init__(self, locator: ComponentLocator | None = None) -> None:
        self.locator = locator or ComponentLocator()
        self.locator.set_parent_resolver(self.resolve_target)
        self._controllers: dict[str, ComponentController[Any]] = {}
        self._children: dict[str | None, set[str]] = defaultdict(set)
        self._batch_depth = 0
        self._pending: dict[int, tuple[Axes | Figure, UpdateImpact]] = {}
        self._cleanup_callbacks: dict[
            str, list[Callable[[ComponentState], None]]
        ] = defaultdict(list)
        self._remove_listeners: list[Callable[[ComponentState], None]] = []
        self._event_subscribers: list[
            tuple[
                Callable[[ComponentEvent], None],
                frozenset[ComponentEventKind] | None,
            ]
        ] = []
        self._transaction_depth = 0
        self._event_buffer: list[ComponentEvent] = []

    def __len__(self) -> int:
        return len(self._controllers)

    def __contains__(self, component_id: object) -> bool:
        return component_id in self._controllers

    def __iter__(self) -> Iterator[ComponentController[Any]]:
        return iter(self.query())

    def register(
        self,
        controller: ComponentController[Any],
        *,
        target: Any | None = None,
        require_parent: bool = True,
    ) -> ComponentController[Any]:
        state = controller.state
        if state.id in self._controllers:
            raise ComponentValidationError(
                f"Duplicate component id {state.id!r}."
            )
        if (
            require_parent
            and state.parent_id is not None
            and state.parent_id not in self._controllers
        ):
            raise ComponentValidationError(
                f"Parent component {state.parent_id!r} is not registered."
            )
        if target is None:
            try:
                target = controller.resolve_target()
            except Exception:
                target = None
        controller.attach(self, self.locator)
        if target is not None:
            self.locator.bind(state.id, target)
        self._controllers[state.id] = controller
        self._children[state.parent_id].add(state.id)
        self._queue_event(
            ComponentEvent(
                ComponentEventKind.ADDED,
                state.id,
                None,
                state.clone(),
            )
        )
        return controller

    def get(self, component_id: str) -> ComponentController[Any]:
        try:
            return self._controllers[component_id]
        except KeyError as exc:
            raise ComponentNotFoundError(
                f"Unknown component id {component_id!r}."
            ) from exc

    def resolve_target(self, component_id: str) -> Any | None:
        controller = self._controllers.get(component_id)
        if controller is None or controller.deleted:
            return None
        try:
            return self.locator.resolve(controller.state)
        except (KeyError, RuntimeError):
            return None

    def children(self, component_id: str | None) -> list[ComponentController[Any]]:
        return self._ordered(
            self._controllers[item]
            for item in self._children.get(component_id, ())
            if item in self._controllers
        )

    def descendants(
        self, component_id: str
    ) -> list[ComponentController[Any]]:
        if component_id not in self._controllers:
            raise ComponentNotFoundError(
                f"Unknown component id {component_id!r}."
            )
        result: list[ComponentController[Any]] = []
        queue = list(self.children(component_id))
        while queue:
            controller = queue.pop(0)
            result.append(controller)
            queue.extend(self.children(controller.component_id))
        return self._ordered(result)

    def query(
        self,
        *,
        kind: ComponentKind | str | None = None,
        role: ComponentRole | str | None = None,
        capabilities: str | Iterable[str] | None = None,
        parent_id: str | None = None,
        recursive: bool = False,
    ) -> list[ComponentController[Any]]:
        kind_value = ComponentKind(kind) if kind is not None else None
        role_value = ComponentRole(role) if role is not None else None
        if isinstance(capabilities, str):
            required = frozenset({capabilities})
        else:
            required = frozenset(capabilities or ())

        if parent_id is not None:
            candidates = (
                self.descendants(parent_id)
                if recursive
                else self.children(parent_id)
            )
        else:
            candidates = list(self._controllers.values())

        return self._ordered(
            controller
            for controller in candidates
            if (kind_value is None or controller.state.kind is kind_value)
            and (role_value is None or controller.state.role is role_value)
            and required.issubset(controller.capabilities())
        )

    def find_one(
        self,
        *,
        parent_id: str | None = None,
        kind: ComponentKind | str | None = None,
        role: ComponentRole | str | None = None,
        selector: dict[str, Any] | None = None,
        recursive: bool = False,
    ) -> ComponentController[Any]:
        """Return exactly one semantic match or raise a validation error."""

        matches = self.query(
            parent_id=parent_id,
            kind=kind,
            role=role,
            recursive=recursive,
        )
        expected = dict(selector or {})
        if expected:
            matches = [
                controller
                for controller in matches
                if all(
                    controller.state.selector.get(key) == value
                    for key, value in expected.items()
                )
            ]
        if not matches:
            raise ComponentNotFoundError(
                "No component matches the requested semantic selector."
            )
        if len(matches) != 1:
            raise ComponentValidationError(
                "The semantic selector matches multiple components."
            )
        return matches[0]

    def snapshot(
        self, component_ids: Iterable[str] | None = None
    ) -> dict[str, ComponentState]:
        ids = (
            list(component_ids)
            if component_ids is not None
            else [controller.component_id for controller in self.query()]
        )
        return {component_id: self.get(component_id).snapshot() for component_id in ids}

    def restore(
        self, snapshots: dict[str, ComponentState]
    ) -> list[ComponentChange]:
        originals = self.snapshot(snapshots)
        changes: list[ComponentChange] = []
        with self.batch_updates():
            for component_id, snapshot in snapshots.items():
                change = self.get(component_id).restore(snapshot)
                changes.append(change)
                if change.status is ChangeStatus.REJECTED:
                    for rollback_id, original in originals.items():
                        self.get(rollback_id).restore(original)
                    break
        return changes

    def set_properties(
        self, operations: Iterable[tuple[str, str, Any]]
    ) -> list[ComponentChange]:
        patches: dict[str, dict[str, Any]] = {}
        for component_id, key, value in operations:
            patches.setdefault(component_id, {})[key] = value
        result = self.apply_transaction(
            ComponentMutation(component_id, properties=properties)
            for component_id, properties in patches.items()
        )
        return list(result.changes)

    def apply_transaction(
        self,
        mutations: Iterable[ComponentMutation],
        *,
        verifier: Callable[[], None] | None = None,
    ) -> ComponentBatchChange:
        """Apply multiple Controller mutations atomically.

        Target and Controller state are restored on the first rejection.
        Lifecycle/change events stay buffered until the whole transaction
        commits, so Editors never observe a half-applied operation.
        """

        mutations = tuple(mutations)
        if not mutations:
            return ComponentBatchChange((), True)
        ids = tuple(dict.fromkeys(item.component_id for item in mutations))
        snapshots = {
            component_id: self.get(
                component_id
            )._transaction_snapshot()
            for component_id in ids
        }
        prior_pending = dict(self._pending)
        event_start = len(self._event_buffer)
        changes: list[ComponentChange] = []
        failure: ComponentChange | None = None
        self._transaction_depth += 1
        try:
            with self.batch_updates():
                for mutation in mutations:
                    change = self.get(
                        mutation.component_id
                    ).apply_mutation(mutation)
                    changes.append(change)
                    if not change.ok:
                        failure = change
                        break
                if failure is None and verifier is not None:
                    try:
                        verifier()
                    except Exception as exc:
                        state = self.get(ids[0]).state
                        failure = ComponentChange(
                            ids[0],
                            None,
                            state,
                            state,
                            ChangeStatus.REJECTED,
                            message=str(exc),
                        )
                        changes.append(failure)
                if failure is not None:
                    self._pending = prior_pending
                    for component_id in reversed(ids):
                        controller = self.get(component_id)
                        controller._restore_transaction_snapshot(
                            snapshots[component_id]
                        )
                    # The transaction never committed or published an event.
                    # Restoring the artists re-establishes the last displayed
                    # state; scheduling a second draw here can repeat the same
                    # render failure that caused verifier rejection.
                    del self._event_buffer[event_start:]
        finally:
            self._transaction_depth -= 1
        if failure is not None:
            return ComponentBatchChange(
                tuple(changes),
                False,
                message=failure.message,
            )
        if self._transaction_depth == 0:
            self._flush_events()
        return ComponentBatchChange(tuple(changes), True)

    def delete(self, component_id: str) -> ComponentChange:
        return self.get(component_id).delete()

    def add_cleanup_callback(
        self,
        component_id: str,
        callback: Callable[[ComponentState], None],
    ) -> Callable[[], None]:
        """Run ``callback`` once when this component leaves the registry.

        Editors, color bindings and data-dependency indexes can register their
        own reversible cleanup without being imported by the core layer.
        """

        self.get(component_id)
        if not callable(callback):
            raise TypeError("Cleanup callback must be callable.")
        self._cleanup_callbacks[component_id].append(callback)

        def unsubscribe() -> None:
            callbacks = self._cleanup_callbacks.get(component_id, [])
            try:
                callbacks.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def add_remove_listener(
        self, callback: Callable[[ComponentState], None]
    ) -> Callable[[], None]:
        if not callable(callback):
            raise TypeError("Remove listener must be callable.")
        self._remove_listeners.append(callback)

        def unsubscribe() -> None:
            try:
                self._remove_listeners.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def subscribe(
        self,
        callback: Callable[[ComponentEvent], None],
        *,
        kinds: Iterable[ComponentEventKind | str] | None = None,
    ) -> Callable[[], None]:
        """Subscribe to committed component lifecycle/change events."""

        if not callable(callback):
            raise TypeError("Component event subscriber must be callable.")
        kind_filter = (
            None
            if kinds is None
            else frozenset(ComponentEventKind(kind) for kind in kinds)
        )
        registration = (callback, kind_filter)
        self._event_subscribers.append(registration)

        def unsubscribe() -> None:
            try:
                self._event_subscribers.remove(registration)
            except ValueError:
                pass

        return unsubscribe

    def clear(self, *, delete_targets: bool = False) -> None:
        roots = [
            controller.component_id
            for controller in self.children(None)
        ]
        if delete_targets:
            for component_id in roots:
                if component_id in self._controllers:
                    self._controllers[component_id].delete()
        else:
            for component_id in list(self._controllers):
                controller = self._controllers[component_id]
                self._notify_removed(controller.state)
                controller._deleted = True
                self.locator.unbind(component_id)
            self._controllers.clear()
            self._children.clear()
            self._cleanup_callbacks.clear()
        self._pending.clear()

    def states(self) -> list[ComponentState]:
        return [controller.state for controller in self.query()]

    def request_update(
        self,
        subject: Axes | Figure | None,
        impacts: UpdateImpact,
    ) -> None:
        if subject is None or impacts == UpdateImpact.NONE:
            return
        key = id(subject)
        previous = self._pending.get(key)
        if previous is None:
            self._pending[key] = (subject, impacts)
        else:
            self._pending[key] = (subject, previous[1] | impacts)
        if self._batch_depth == 0:
            self.flush_updates()

    @contextmanager
    def batch_updates(self) -> Iterator["ComponentRegistry"]:
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self.flush_updates()

    def flush_updates(self) -> None:
        pending = list(self._pending.values())
        self._pending.clear()

        figure_impacts: dict[int, tuple[Figure, UpdateImpact]] = {}
        for subject, impacts in pending:
            non_redraw = impacts & ~UpdateImpact.REDRAW
            apply_update_impacts(subject, non_redraw)
            if (
                isinstance(subject, Axes)
                and non_redraw
                & (UpdateImpact.RELIM | UpdateImpact.AUTOSCALE)
            ):
                component_id = self.locator.find_id(subject)
                controller = (
                    self._controllers.get(component_id)
                    if component_id is not None
                    else None
                )
                if (
                    controller is not None
                    and controller.state.kind is ComponentKind.AXES
                ):
                    before = controller.state
                    after = controller.sync_from_target()
                    if before != after:
                        self._queue_event(
                            ComponentEvent(
                                ComponentEventKind.CHANGED,
                                component_id,
                                before,
                                after,
                                None,
                            )
                        )
            figure = subject.figure if isinstance(subject, Axes) else subject
            previous = figure_impacts.get(id(figure))
            redraw = impacts & UpdateImpact.REDRAW
            if previous is None:
                figure_impacts[id(figure)] = (figure, redraw)
            else:
                figure_impacts[id(figure)] = (figure, previous[1] | redraw)
        for figure, impacts in figure_impacts.values():
            apply_update_impacts(figure, impacts)

    def validate_tree(self) -> None:
        roots = [
            controller
            for controller in self._controllers.values()
            if controller.state.parent_id is None
        ]
        if len(roots) != 1 or roots[0].state.kind is not ComponentKind.FIGURE:
            raise ComponentValidationError(
                "Registry must have exactly one Figure root."
            )
        root = roots[0].state
        if root.selector.get("scope") != "figure":
            raise ComponentValidationError(
                "Figure selector must use scope='figure'."
            )

        children_by_parent: dict[str | None, list[ComponentState]] = (
            defaultdict(list)
        )
        for controller in self._controllers.values():
            state = controller.state
            if state.parent_id is not None and state.parent_id not in self._controllers:
                raise ComponentValidationError(
                    f"Component {state.id!r} has an unknown parent."
                )
            indexed_parents = [
                parent_id
                for parent_id, component_ids in self._children.items()
                if state.id in component_ids
            ]
            if indexed_parents != [state.parent_id]:
                raise ComponentValidationError(
                    f"Component {state.id!r} hierarchy index is out of sync."
                )
            children_by_parent[state.parent_id].append(state)
            if state.parent_id is not None:
                parent = self._controllers[state.parent_id].state
                self._validate_parent_kind(state, parent)
            self._validate_semantic_selector(state)

        for parent_id, component_ids in self._children.items():
            for component_id in component_ids:
                if component_id not in self._controllers:
                    raise ComponentValidationError(
                        f"Hierarchy index contains unknown component "
                        f"{component_id!r} under {parent_id!r}."
                    )

        visited: set[str] = set()
        active: set[str] = set()

        def visit(component_id: str) -> None:
            if component_id in active:
                raise ComponentValidationError("Component tree contains a cycle.")
            if component_id in visited:
                return
            active.add(component_id)
            for child in self._children.get(component_id, ()):
                visit(child)
            active.remove(component_id)
            visited.add(component_id)

        visit(roots[0].component_id)
        if visited != set(self._controllers):
            raise ComponentValidationError(
                "Component tree contains disconnected nodes."
            )

        semantic_keys: set[tuple[str | None, ComponentKind, str]] = set()
        for controller in self._controllers.values():
            state = controller.state
            try:
                selector_key = json.dumps(
                    state.selector,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError) as exc:
                raise ComponentValidationError(
                    f"Component {state.id!r} selector is not JSON-compatible."
                ) from exc
            semantic_key = (state.parent_id, state.kind, selector_key)
            if semantic_key in semantic_keys:
                raise ComponentValidationError(
                    f"Duplicate semantic selector for {state.kind.value!r} "
                    f"under parent {state.parent_id!r}."
                )
            semantic_keys.add(semantic_key)

        axes_states = [
            controller.state
            for controller in self._controllers.values()
            if controller.state.kind is ComponentKind.AXES
        ]
        axes_indexes = sorted(
            state.selector["index"] for state in axes_states
        )
        if axes_indexes != list(range(len(axes_states))):
            raise ComponentValidationError(
                "Axes selector indexes must be contiguous from zero."
            )
        for axes_state in axes_states:
            self._validate_axes_semantics(
                axes_state,
                children_by_parent,
            )

        chart_orders = [
            controller.state.order
            for controller in self._controllers.values()
            if controller.state.kind in _CHART_KINDS
        ]
        if len(chart_orders) != len(set(chart_orders)):
            raise ComponentValidationError(
                "Chart component order values must be unique."
            )

    @staticmethod
    def _validate_parent_kind(
        state: ComponentState,
        parent: ComponentState,
    ) -> None:
        kind = state.kind
        role = state.role
        parent_kind = parent.kind
        if kind is ComponentKind.AXES:
            valid = parent_kind is ComponentKind.FIGURE
        elif kind in {
            ComponentKind.AXIS,
            ComponentKind.SPINE,
            ComponentKind.LEGEND,
        }:
            valid = parent_kind is ComponentKind.AXES
        elif kind is ComponentKind.TICK_GROUP:
            valid = parent_kind is ComponentKind.AXIS
        elif kind is ComponentKind.TICK_LABEL_GROUP:
            valid = parent_kind is ComponentKind.TICK_GROUP
        elif kind is ComponentKind.GRID:
            valid = parent_kind is ComponentKind.AXIS
        elif kind in _CHART_KINDS:
            valid = parent_kind is ComponentKind.AXES
        elif kind is ComponentKind.TEXT:
            if role is ComponentRole.TITLE:
                valid = parent_kind is ComponentKind.AXES
            elif role in {
                ComponentRole.X_LABEL,
                ComponentRole.Y_LABEL,
            }:
                valid = parent_kind is ComponentKind.AXIS
            else:
                valid = parent_kind in {
                    ComponentKind.FIGURE,
                    ComponentKind.AXES,
                }
        else:
            valid = False
        if not valid:
            raise ComponentValidationError(
                f"Component {state.id!r} ({kind.value}/{role.value}) "
                f"cannot have parent kind {parent_kind.value!r}."
            )

    def _validate_semantic_selector(
        self,
        state: ComponentState,
    ) -> None:
        selector = state.selector
        if state.kind is ComponentKind.FIGURE:
            return
        if state.kind is ComponentKind.AXES:
            index = selector.get("index")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
            ):
                raise ComponentValidationError(
                    f"Axes component {state.id!r} requires a non-negative "
                    "integer selector index."
                )
            return
        if state.kind is ComponentKind.AXIS:
            expected = (
                "x"
                if state.role is ComponentRole.X_AXIS
                else "y"
            )
            if selector.get("axis") != expected:
                raise ComponentValidationError(
                    f"Axis component {state.id!r} requires axis={expected!r}."
                )
            return
        if state.kind is ComponentKind.SPINE:
            if selector.get("name") not in _STANDARD_SPINES:
                raise ComponentValidationError(
                    f"Spine component {state.id!r} requires a standard "
                    "spine selector."
                )
            return
        if state.kind in {
            ComponentKind.TICK_GROUP,
            ComponentKind.TICK_LABEL_GROUP,
            ComponentKind.GRID,
        }:
            axis_name = selector.get("axis")
            level = selector.get("level")
            if axis_name not in _AXIS_NAMES or level not in _TICK_LEVELS:
                raise ComponentValidationError(
                    f"Component {state.id!r} requires axis=x|y and "
                    "level=major|minor selectors."
                )
            parent = self._controllers[state.parent_id].state
            parent_axis = parent.selector.get("axis")
            parent_level = parent.selector.get("level")
            if parent_axis != axis_name:
                raise ComponentValidationError(
                    f"Component {state.id!r} axis selector does not match "
                    "its parent."
                )
            if (
                state.kind is ComponentKind.TICK_LABEL_GROUP
                and parent_level != level
            ):
                raise ComponentValidationError(
                    f"Tick-label component {state.id!r} level does not "
                    "match its parent."
                )
            if state.kind is ComponentKind.TICK_GROUP:
                expected_role = (
                    ComponentRole.MAJOR_TICK
                    if level == "major"
                    else ComponentRole.MINOR_TICK
                )
                if state.role is not expected_role:
                    raise ComponentValidationError(
                        f"Tick component {state.id!r} role does not match "
                        "its level selector."
                    )
            elif state.kind is ComponentKind.TICK_LABEL_GROUP:
                expected_role = (
                    ComponentRole.MAJOR_TICK_LABEL
                    if level == "major"
                    else ComponentRole.MINOR_TICK_LABEL
                )
                if state.role is not expected_role:
                    raise ComponentValidationError(
                        f"Tick-label component {state.id!r} role does not "
                        "match its level selector."
                    )
            return
        if state.role in {
            ComponentRole.X_LABEL,
            ComponentRole.Y_LABEL,
        }:
            expected = (
                "x"
                if state.role is ComponentRole.X_LABEL
                else "y"
            )
            parent = self._controllers[state.parent_id].state
            if (
                selector.get("axis") != expected
                or parent.selector.get("axis") != expected
            ):
                raise ComponentValidationError(
                    f"Axis-label component {state.id!r} requires "
                    f"axis={expected!r}."
                )
            return
        if state.kind in _CHART_KINDS:
            if selector.get("object_id") != state.id:
                raise ComponentValidationError(
                    f"Chart component {state.id!r} requires object_id "
                    "equal to its component id."
                )
            return
        if state.kind is ComponentKind.TEXT and state.role is ComponentRole.TEXT:
            if selector.get("object_id") != state.id:
                raise ComponentValidationError(
                    f"Text component {state.id!r} requires object_id "
                    "equal to its component id."
                )
            scope = selector.get("scope")
            if scope is not None:
                parent = self._controllers[state.parent_id].state
                expected_scope = (
                    "figure"
                    if parent.kind is ComponentKind.FIGURE
                    else "axes"
                )
                if scope != expected_scope:
                    raise ComponentValidationError(
                        f"Text component {state.id!r} scope does not match "
                        "its parent."
                    )

    @staticmethod
    def _validate_axes_semantics(
        axes_state: ComponentState,
        children_by_parent: dict[str | None, list[ComponentState]],
    ) -> None:
        direct = children_by_parent.get(axes_state.id, [])
        axes_description = f"Axes component {axes_state.id!r}"

        axis_components = [
            child for child in direct
            if child.kind is ComponentKind.AXIS
        ]
        axis_by_name = {
            child.selector.get("axis"): child
            for child in axis_components
        }
        if (
            len(axis_components) != 2
            or set(axis_by_name) != _AXIS_NAMES
        ):
            raise ComponentValidationError(
                f"{axes_description} must contain exactly one x and one "
                "y Axis component."
            )

        spine_components = [
            child for child in direct
            if child.kind is ComponentKind.SPINE
        ]
        spine_names = [
            child.selector.get("name") for child in spine_components
        ]
        if (
            len(spine_components) != len(_STANDARD_SPINES)
            or set(spine_names) != _STANDARD_SPINES
        ):
            raise ComponentValidationError(
                f"{axes_description} must contain exactly one of each "
                "standard Spine component."
            )

        titles = [
            child for child in direct
            if child.role is ComponentRole.TITLE
        ]
        legends = [
            child for child in direct
            if child.kind is ComponentKind.LEGEND
        ]
        if len(titles) != 1:
            raise ComponentValidationError(
                f"{axes_description} must contain exactly one Title "
                "component."
            )
        if len(legends) != 1:
            raise ComponentValidationError(
                f"{axes_description} must contain exactly one Legend "
                "component."
            )

        for axis_name, axis_state in axis_by_name.items():
            axis_children = children_by_parent.get(axis_state.id, [])
            label_role = (
                ComponentRole.X_LABEL
                if axis_name == "x"
                else ComponentRole.Y_LABEL
            )
            labels = [
                child for child in axis_children
                if child.role is label_role
            ]
            ticks = [
                child for child in axis_children
                if child.kind is ComponentKind.TICK_GROUP
            ]
            grids = [
                child for child in axis_children
                if child.kind is ComponentKind.GRID
            ]
            if len(labels) != 1:
                raise ComponentValidationError(
                    f"{axes_description} {axis_name}-axis must contain "
                    "exactly one label component."
                )
            if (
                len(ticks) != 2
                or {
                    child.selector.get("level") for child in ticks
                } != _TICK_LEVELS
            ):
                raise ComponentValidationError(
                    f"{axes_description} {axis_name}-axis must contain "
                    "major and minor Tick components."
                )
            if (
                len(grids) != 2
                or {
                    child.selector.get("level") for child in grids
                } != _TICK_LEVELS
            ):
                raise ComponentValidationError(
                    f"{axes_description} {axis_name}-axis must contain "
                    "major and minor Grid components."
                )
            for tick in ticks:
                tick_labels = [
                    child
                    for child in children_by_parent.get(tick.id, [])
                    if child.kind is ComponentKind.TICK_LABEL_GROUP
                ]
                if len(tick_labels) != 1:
                    raise ComponentValidationError(
                        f"Tick component {tick.id!r} must contain exactly "
                        "one Tick Label component."
                    )

    def _forget_subtree(self, component_id: str) -> None:
        if component_id not in self._controllers:
            return
        descendants = self.descendants(component_id)
        ids = [item.component_id for item in reversed(descendants)]
        ids.append(component_id)
        for item_id in ids:
            controller = self._controllers.pop(item_id, None)
            if controller is None:
                continue
            state = controller.state
            self._notify_removed(state)
            controller._deleted = True
            self._children[state.parent_id].discard(item_id)
            self._children.pop(item_id, None)
            self.locator.unbind(item_id)

    def _notify_removed(self, state: ComponentState) -> None:
        callbacks = self._cleanup_callbacks.pop(state.id, [])
        for callback in (*callbacks, *self._remove_listeners):
            try:
                callback(state.clone())
            except Exception:
                # Cleanup is best-effort: one stale editor must not prevent
                # the artist and all remaining registrations being released.
                continue
        self._queue_event(
            ComponentEvent(
                ComponentEventKind.REMOVED,
                state.id,
                state.clone(),
                None,
            )
        )

    def _record_change(self, change: ComponentChange) -> None:
        self._queue_event(
            ComponentEvent(
                ComponentEventKind.CHANGED,
                change.component_id,
                change.before.clone()
                if change.before is not None
                else None,
                change.after.clone()
                if change.after is not None
                else None,
                change,
            )
        )

    def _queue_event(self, event: ComponentEvent) -> None:
        self._event_buffer.append(event)
        if self._transaction_depth == 0:
            self._flush_events()

    def _flush_events(self) -> None:
        if self._transaction_depth or not self._event_buffer:
            return
        events, self._event_buffer = self._event_buffer, []
        for event in events:
            for callback, kinds in tuple(self._event_subscribers):
                if kinds is not None and event.kind not in kinds:
                    continue
                try:
                    callback(event)
                except Exception:
                    # Runtime/editor observers are isolated from Controller
                    # commits just like cleanup callbacks.
                    continue

    @staticmethod
    def _ordered(
        controllers: Iterable[ComponentController[Any]],
    ) -> list[ComponentController[Any]]:
        return sorted(
            controllers,
            key=lambda item: (item.state.order, item.component_id),
        )
