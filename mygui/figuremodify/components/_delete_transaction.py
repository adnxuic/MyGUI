"""Internal five-phase Registry deletion procedure.

The Registry remains the only deletion and event authority. This module holds
the ephemeral memento and compensation diagnostics for one transaction.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .errors import ComponentValidationError
from .models import (
    ChangeStatus,
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentNotice,
    ComponentState,
    DeletionPolicy,
    MessageLevel,
)


@dataclass
class DeleteTransactionMemento:
    """Identity, order, bindings, and rollback diagnostics for one deletion."""

    requested: tuple[str, ...]
    replacements: tuple[ComponentState, ...]
    requested_controllers: dict[str, Any]
    roots: list[str]
    postorder_ids: list[str]
    removed_ids: set[str]
    replacement_by_id: dict[str, ComponentState]
    removed_controllers: dict[str, Any] = field(default_factory=dict)
    removed_states: dict[str, ComponentState] = field(default_factory=dict)
    locator_targets: dict[str, Any] = field(default_factory=dict)
    rollback_snapshots: dict[str, tuple[ComponentState, Any, dict[str, Any]]] = field(
        default_factory=dict
    )
    handles: list[tuple[Any, Any]] = field(default_factory=list)
    changes: list[ComponentChange] = field(default_factory=list)
    failure: ComponentChange | None = None
    prior_pending: dict[Any, Any] = field(default_factory=dict)
    event_start: int = 0
    original_controllers: dict[str, Any] = field(default_factory=dict)
    original_children: Any = None
    staged_tree: bool = False
    unbinding_ids: list[str] = field(default_factory=list)
    notices: list[ComponentNotice] = field(default_factory=list)
    rollback_errors: list[str] = field(default_factory=list)


def _failed_prepare(exc: BaseException) -> ComponentBatchChange:
    return ComponentBatchChange((), False, message=str(exc))


def prepare_delete_transaction(
    registry: Any,
    component_ids: Iterable[str],
    state_replacements: Iterable[ComponentState],
) -> ComponentBatchChange | DeleteTransactionMemento:
    """Collect roots, post-order IDs, replacements, and identity snapshots."""

    requested = tuple(dict.fromkeys(str(component_id) for component_id in component_ids))
    replacements = tuple(state_replacements)
    if not requested and not replacements:
        return ComponentBatchChange((), True)

    try:
        requested_controllers = {
            component_id: registry.get(component_id)
            for component_id in requested
        }
        requested_set = set(requested)
        roots: list[str] = []
        for component_id in requested:
            parent_id = requested_controllers[component_id].state.parent_id
            visited_parents: set[str] = set()
            while parent_id is not None and parent_id not in requested_set:
                if parent_id in visited_parents:
                    raise ComponentValidationError(
                        "Component tree contains an ancestor cycle."
                    )
                visited_parents.add(parent_id)
                parent = registry._controllers.get(parent_id)
                parent_id = (
                    parent.state.parent_id if parent is not None else None
                )
            if parent_id is None:
                roots.append(component_id)
        for component_id in roots:
            controller = requested_controllers[component_id]
            if controller.DELETION_POLICY is not DeletionPolicy.REMOVE:
                raise ComponentValidationError(
                    f"Component {component_id!r} uses deletion policy "
                    f"{controller.DELETION_POLICY.value!r}."
                )
    except Exception as exc:
        return _failed_prepare(exc)

    removed_ids: set[str] = set()
    postorder_ids: list[str] = []
    collecting: set[str] = set()

    def collect(component_id: str) -> None:
        if component_id in collecting:
            raise ComponentValidationError(
                "Component tree contains a deletion cycle."
            )
        if component_id in removed_ids:
            return
        collecting.add(component_id)
        children = sorted(
            registry._children.get(component_id, ()),
            key=lambda child_id: (
                registry._controllers[child_id].state.order,
                child_id,
            ),
        )
        for child_id in children:
            collect(child_id)
        collecting.remove(component_id)
        removed_ids.add(component_id)
        postorder_ids.append(component_id)

    try:
        for component_id in roots:
            collect(component_id)
    except Exception as exc:
        return _failed_prepare(exc)

    replacement_by_id: dict[str, ComponentState] = {}
    try:
        for state in replacements:
            if not isinstance(state, ComponentState):
                raise ComponentValidationError(
                    "State replacements must contain ComponentState values."
                )
            if state.id in replacement_by_id:
                raise ComponentValidationError(
                    f"Duplicate state replacement {state.id!r}."
                )
            if state.id in removed_ids:
                raise ComponentValidationError(
                    f"Cannot replace removed component {state.id!r}."
                )
            registry.get(state.id)
            replacement_by_id[state.id] = state
    except Exception as exc:
        return _failed_prepare(exc)

    return DeleteTransactionMemento(
        requested=requested,
        replacements=replacements,
        requested_controllers=requested_controllers,
        roots=roots,
        postorder_ids=postorder_ids,
        removed_ids=removed_ids,
        replacement_by_id=replacement_by_id,
        removed_controllers={
            component_id: registry._controllers[component_id]
            for component_id in postorder_ids
        },
        removed_states={
            component_id: registry._controllers[component_id].state
            for component_id in postorder_ids
        },
        locator_targets={
            component_id: target
            for component_id in postorder_ids
            if (target := registry.locator.bound_target(component_id)) is not None
        },
        prior_pending=dict(registry._pending),
        event_start=len(registry._event_buffer),
        original_controllers=registry._controllers,
        original_children=registry._children,
    )


def apply_delete_transaction(registry: Any, memento: DeleteTransactionMemento) -> None:
    """Detach artists and stage the candidate Registry tree."""

    for component_id in memento.roots:
        controller = memento.requested_controllers[component_id]
        memento.handles.append((controller, controller.prepare_remove()))

    snapshot_ids = list(memento.replacement_by_id)
    if any(
        registry.get(component_id).state.kind is ComponentKind.AXES
        for component_id in memento.replacement_by_id
    ):
        snapshot_ids.extend(
            controller.component_id
            for controller in registry.query(kind=ComponentKind.AXES)
            if controller.component_id not in snapshot_ids
        )
    memento.rollback_snapshots = {
        component_id: registry.get(component_id)._transaction_snapshot()
        for component_id in snapshot_ids
    }
    for component_id, state in memento.replacement_by_id.items():
        controller = registry.get(component_id)
        change = controller.apply_state(state)
        memento.changes.append(change)
        if not change.ok:
            memento.failure = change
            raise ComponentValidationError(
                change.message
                or f"Could not replace component {component_id!r}."
            )

    for controller, handle in memento.handles:
        controller.commit_remove(handle)

    candidate_controllers = {
        component_id: controller
        for component_id, controller in memento.original_controllers.items()
        if component_id not in memento.removed_ids
    }
    candidate_children: dict[str | None, set[str]] = defaultdict(set)
    for parent_id, child_ids in memento.original_children.items():
        if parent_id in memento.removed_ids:
            continue
        candidate_children[parent_id].update(
            child_id
            for child_id in child_ids
            if child_id not in memento.removed_ids
        )
    registry._controllers = candidate_controllers
    registry._children = candidate_children
    memento.staged_tree = True


def verify_delete_transaction(
    registry: Any,
    memento: DeleteTransactionMemento,
    verifier: Callable[[], None] | None,
) -> None:
    """Validate the staged tree, run the external verifier, then unbind locators."""

    if any(
        controller.state.kind is ComponentKind.FIGURE
        for controller in registry._controllers.values()
    ):
        registry.validate_tree()
    if verifier is not None:
        verifier()
    for component_id in memento.postorder_ids:
        memento.unbinding_ids.append(component_id)
        registry.locator.unbind(component_id)


def rollback_delete_transaction(
    registry: Any,
    memento: DeleteTransactionMemento,
    exc: BaseException,
) -> ComponentBatchChange:
    """Restore object identity, order, bindings, and record compensation faults."""

    if memento.failure is None:
        state = (
            memento.requested_controllers[memento.roots[0]].state
            if memento.roots
            else next(iter(memento.replacement_by_id.values()), None)
        )
        memento.failure = ComponentChange(
            state.id if state is not None else "",
            None,
            state.clone() if state is not None else None,
            state.clone() if state is not None else None,
            ChangeStatus.REJECTED,
            message=str(exc),
        )
        memento.changes.append(memento.failure)
    if memento.staged_tree:
        registry._controllers = memento.original_controllers
        registry._children = memento.original_children
    rollback_handles = sorted(
        memento.handles,
        key=lambda item: (
            id(getattr(item[1], "owner", item[1])),
            int(getattr(item[1], "index", 0)),
        ),
    )
    for controller, handle in rollback_handles:
        try:
            controller.rollback_remove(handle)
        except Exception as rollback_exc:
            # Compensation must keep going; record the identity that failed.
            memento.rollback_errors.append(
                f"{controller.component_id}: artist rollback failed "
                f"({rollback_exc})"
            )
            try:
                registry._force_restore_removal_handle(handle)
            except Exception as force_exc:
                memento.rollback_errors.append(
                    f"{controller.component_id}: forced artist "
                    f"restoration failed ({force_exc})"
                )
    for component_id in memento.rollback_snapshots:
        try:
            memento.original_controllers[
                component_id
            ]._restore_transaction_snapshot(
                memento.rollback_snapshots[component_id]
            )
        except Exception as rollback_exc:
            memento.rollback_errors.append(
                f"{component_id}: state rollback failed "
                f"({rollback_exc})"
            )
            try:
                controller = memento.original_controllers[component_id]
                type(controller)._restore_transaction_snapshot(
                    controller,
                    memento.rollback_snapshots[component_id],
                )
            except Exception as force_exc:
                memento.rollback_errors.append(
                    f"{component_id}: forced state restoration failed "
                    f"({force_exc})"
                )
    for component_id, snapshot in memento.rollback_snapshots.items():
        controller = memento.original_controllers[component_id]
        raw = snapshot[2]
        for key in ("autoscalex_on", "autoscaley_on", "autoscale_on"):
            spec = controller.property_specs().get(key)
            if spec is None or key not in raw:
                continue
            try:
                controller._write_property(
                    controller.resolve_target(),
                    spec,
                    deepcopy(raw[key]),
                )
            except Exception as rollback_exc:
                memento.rollback_errors.append(
                    f"{component_id}: {key} rollback failed "
                    f"({rollback_exc})"
                )
                try:
                    type(controller)._write_property(
                        controller,
                        controller.resolve_target(),
                        spec,
                        deepcopy(raw[key]),
                    )
                except Exception as force_exc:
                    memento.rollback_errors.append(
                        f"{component_id}: forced {key} restoration "
                        f"failed ({force_exc})"
                    )
    for component_id in reversed(memento.unbinding_ids):
        if component_id not in memento.locator_targets:
            continue
        try:
            registry.locator.bind(
                component_id,
                memento.locator_targets[component_id],
            )
        except Exception as rollback_exc:
            memento.rollback_errors.append(
                f"{component_id}: Locator rollback failed "
                f"({rollback_exc})"
            )
            try:
                target = memento.locator_targets[component_id]
                registry.locator._targets[component_id] = target
            except TypeError:
                registry.locator._strong_targets[component_id] = target
            except Exception as force_exc:
                memento.rollback_errors.append(
                    f"{component_id}: forced Locator restoration "
                    f"failed ({force_exc})"
                )
    registry._pending = memento.prior_pending
    del registry._event_buffer[memento.event_start:]
    registry._batch_depth -= 1
    registry._transaction_depth -= 1
    message = memento.failure.message
    if memento.rollback_errors:
        message = (
            f"{message} Rollback was incomplete: "
            + "; ".join(memento.rollback_errors)
        ).strip()
    return ComponentBatchChange(
        tuple(memento.changes),
        False,
        message=message,
        rollback_complete=not memento.rollback_errors,
    )


def publish_delete_transaction(
    registry: Any,
    memento: DeleteTransactionMemento,
) -> ComponentBatchChange:
    """Emit one lifecycle batch after the staged tree has been verified."""

    survivor_events = registry._event_buffer[memento.event_start:]
    del registry._event_buffer[memento.event_start:]
    for component_id in memento.postorder_ids:
        controller = memento.removed_controllers[component_id]
        controller._deleted = True
    for controller, handle in memento.handles:
        try:
            controller._finalize_remove(handle)
        except Exception as exc:
            memento.notices.append(
                ComponentNotice(
                    MessageLevel.WARNING,
                    f"Component was removed, but Matplotlib cleanup "
                    f"reported: {exc}",
                )
            )
        registry.request_update(handle.subject, controller.DELETE_IMPACTS)
    for component_id in memento.postorder_ids:
        registry._notify_removed(memento.removed_states[component_id])
    registry._event_buffer.extend(survivor_events)
    for component_id in memento.roots:
        state = memento.removed_states[component_id]
        memento.changes.append(
            ComponentChange(
                component_id,
                None,
                state,
                None,
                ChangeStatus.DELETED,
                memento.requested_controllers[component_id].DELETE_IMPACTS,
            )
        )

    registry._batch_depth -= 1
    if registry._batch_depth == 0:
        try:
            registry.flush_updates()
        except Exception as exc:
            memento.notices.append(
                ComponentNotice(
                    MessageLevel.WARNING,
                    f"Components were removed, but repaint failed: {exc}",
                )
            )
    registry._transaction_depth -= 1
    if registry._transaction_depth == 0:
        registry._flush_events()
    return ComponentBatchChange(
        tuple(memento.changes),
        True,
        notices=tuple(memento.notices),
    )


def run_delete_transaction(
    registry: Any,
    component_ids: Iterable[str],
    state_replacements: Iterable[ComponentState],
    verifier: Callable[[], None] | None,
) -> ComponentBatchChange:
    """Run prepare, apply, verify, then rollback or publish."""

    prepared = prepare_delete_transaction(
        registry,
        component_ids,
        state_replacements,
    )
    if isinstance(prepared, ComponentBatchChange):
        return prepared
    memento = prepared
    registry._transaction_depth += 1
    registry._batch_depth += 1
    try:
        apply_delete_transaction(registry, memento)
        verify_delete_transaction(registry, memento, verifier)
    except Exception as exc:
        return rollback_delete_transaction(registry, memento, exc)
    return publish_delete_transaction(registry, memento)
