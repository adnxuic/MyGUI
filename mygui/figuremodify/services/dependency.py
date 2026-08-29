"""Table-dependency capture, restore, and cascade helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


from mygui.database import (
    ColumnRef,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRegistry,
    ComponentState,
    ComponentValidationError,
)
from ._helpers import (
    _column_ref,
)
from .deletion import ComponentDeletionService

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
        for key in ("x_ref", "y_ref", "z_ref", "color_ref", "size_ref", "position_ref"):
            try:
                refs.add(_column_ref(state.data[key]))
            except (KeyError, ValueError, TypeError):
                continue
        for key in ("xerr", "yerr"):
            for ref in ComponentDependencyService._nested_refs(state.data.get(key)):
                refs.add(ref)
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

    @staticmethod
    def _nested_refs(value: Any) -> list[ColumnRef]:
        """Recursively collect column references inside one data value.

        Error Bar error specs embed their column references one or two levels
        deep, so the generic recursion keeps cascade deletion aligned with
        any closed nested shape instead of hard-coding spec keys.
        """

        refs: list[ColumnRef] = []
        if isinstance(value, dict):
            try:
                refs.append(_column_ref(value))
                return refs
            except (TypeError, ValueError):
                pass
            for item in value.values():
                refs.extend(ComponentDependencyService._nested_refs(item))
        elif isinstance(value, (list, tuple)):
            for item in value:
                refs.extend(ComponentDependencyService._nested_refs(item))
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
