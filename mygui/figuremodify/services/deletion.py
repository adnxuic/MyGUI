"""Physical deletion planning, handlers, and ledger services."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from collections.abc import Callable, Iterable
from typing import Any


from mygui.figuremodify.components import (
    CONTROLLER_TYPES,
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentNotice,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    DeletionPolicy,
)
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
)

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
    handlers.register(ComponentKind.ERRORBAR, ComponentRole.ERROR_BAR, palette_leaf)
    field_leaf = DeletionHandler()
    for role in (
        ComponentRole.PSEUDOCOLOR,
        ComponentRole.HEATMAP,
        ComponentRole.CONTOUR,
    ):
        handlers.register(ComponentKind.FIELD_2D, role, field_leaf)
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
    for role in (
        ComponentRole.SECONDARY_X_AXIS,
        ComponentRole.SECONDARY_Y_AXIS,
    ):
        handlers.register(
            ComponentKind.SECONDARY_AXIS,
            role,
            DeletionHandler(),
        )
    handlers.register(
        ComponentKind.TEXT,
        ComponentRole.TEXT,
        DeletionHandler(),
    )
    handlers.register(
        ComponentKind.ANNOTATION,
        ComponentRole.ANNOTATION,
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
    """Plan Colorbar cascades before a scalar-mappable source deletion commits."""

    expanded = list(dict.fromkeys(str(item) for item in component_ids))
    removed_sources = {
        component_id
        for component_id in expanded
        if component_id in registry
        and registry.get(component_id).state.kind
        in {ComponentKind.SCATTER, ComponentKind.FIELD_2D}
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
