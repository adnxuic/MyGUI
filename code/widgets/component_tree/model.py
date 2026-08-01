"""Qt model and search filter for the Components tree projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from Qt_core import *

from code.figuremodify.components import (
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRole,
    ComponentState,
)
from code.widgets.fig_control_window.component_editors.inspector import (
    EditorPlacement,
)

from .nodes import (
    COMPONENT_ID_ROLE,
    COMPONENT_KIND_ROLE,
    COMPONENT_ROLE_ROLE,
    COMPONENT_SEARCH_ROLE,
    NODE_KEY_ROLE,
    VIRTUAL_GROUP_ROLE,
    ComponentNodeKey,
    GroupNodeKey,
    TreeNodeKey,
)
from .presentation import TreePresentationResolver, normalized_query


@dataclass(slots=True)
class _TreePointer:
    node_key: TreeNodeKey
    component_id: str | None


@dataclass(frozen=True, slots=True)
class _VirtualGroup:
    node_key: GroupNodeKey
    parent_component_id: str
    label: str
    kind: ComponentKind | None = None
    role: ComponentRole | None = None


class ComponentTreeModel(QAbstractItemModel):
    """Project Registry Components with deterministic UI-only groups."""

    aboutToRefresh = Signal()
    refreshed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = None
        self.editor_registry = None
        self.presentation = TreePresentationResolver()
        self._unsubscribe = None
        self._node_children: dict[TreeNodeKey | None, list[TreeNodeKey]] = {}
        self._node_parents: dict[TreeNodeKey, TreeNodeKey | None] = {}
        self._component_children: dict[str | None, list[str]] = {}
        self._component_keys: dict[str, ComponentNodeKey] = {}
        self._pointers: dict[TreeNodeKey, _TreePointer] = {}
        self._groups: dict[GroupNodeKey, _VirtualGroup] = {}

    def set_registry(self, registry, editor_registry=None) -> None:
        """Bind a Registry and atomically replace the projected topology."""

        if registry is self.registry and editor_registry is self.editor_registry:
            return
        self._detach_registry()
        self.registry = registry
        self.editor_registry = editor_registry
        self.presentation = TreePresentationResolver(editor_registry)
        self._reset_from_registry()
        if registry is not None:
            subscribe_batches = getattr(registry, "subscribe_batches", None)
            self._unsubscribe = (
                subscribe_batches(self._component_events)
                if callable(subscribe_batches)
                else registry.subscribe(self._component_event)
            )

    @classmethod
    def validate_registry_projection(cls, registry, editor_registry=None) -> None:
        """Build and validate a candidate projection without publishing it."""

        candidate = cls()
        try:
            candidate.registry = registry
            candidate.editor_registry = editor_registry
            candidate.presentation = TreePresentationResolver(editor_registry)
            candidate._build_projection()
        finally:
            candidate.registry = None
            candidate.editor_registry = None
            candidate.deleteLater()

    def dispose(self) -> None:
        self._detach_registry()
        self.registry = None
        self.editor_registry = None
        self.presentation = TreePresentationResolver()
        self._reset_from_registry()

    def _detach_registry(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
        self._unsubscribe = None

    def _reset_from_registry(self) -> None:
        projection = self._build_projection()
        self.aboutToRefresh.emit()
        self.beginResetModel()
        (
            self._node_children,
            self._node_parents,
            self._component_children,
            self._component_keys,
            self._pointers,
            self._groups,
        ) = projection
        self.endResetModel()
        self.refreshed.emit()

    def component_display_label(self, state: ComponentState) -> str:
        return self.presentation.display_label(state)

    def _build_projection(self):
        node_children: dict[TreeNodeKey | None, list[TreeNodeKey]] = {}
        node_parents: dict[TreeNodeKey, TreeNodeKey | None] = {}
        component_children: dict[str | None, list[str]] = {}
        component_keys: dict[str, ComponentNodeKey] = {}
        pointers: dict[TreeNodeKey, _TreePointer] = {}
        groups: dict[GroupNodeKey, _VirtualGroup] = {}
        if self.registry is None:
            return (
                node_children, node_parents, component_children,
                component_keys, pointers, groups,
            )

        states = list(self.registry.states())
        states_by_id = {state.id: state for state in states}
        if len(states_by_id) != len(states):
            raise ValueError("Component tree contains duplicate component IDs.")
        for state in states:
            if state.parent_id is not None and state.parent_id not in states_by_id:
                raise ValueError(f"Component {state.id!r} has an unknown parent.")
            key = ComponentNodeKey(state.id)
            component_keys[state.id] = key
            pointers[key] = _TreePointer(key, state.id)
            component_children.setdefault(state.parent_id, []).append(state.id)
        for child_ids in component_children.values():
            child_ids.sort(
                key=lambda component_id: self.presentation.sort_key(
                    states_by_id[component_id]
                )
            )
        for root_id in component_children.get(None, ()):
            key = component_keys[root_id]
            node_parents[key] = None
            node_children.setdefault(None, []).append(key)

        def register_group(
            parent_id: str,
            group_kind: str,
            label: str,
            member_ids: list[str],
            kind: ComponentKind | None = None,
            role: ComponentRole | None = None,
        ) -> GroupNodeKey:
            key = GroupNodeKey(parent_id, group_kind, kind, role)
            if key in pointers:
                raise ValueError(f"Duplicate UI group key {key!r}.")
            groups[key] = _VirtualGroup(key, parent_id, label, kind, role)
            pointers[key] = _TreePointer(key, None)
            parent_key = component_keys[parent_id]
            node_parents[key] = parent_key
            node_children[key] = [component_keys[item] for item in member_ids]
            for component_id in member_ids:
                node_parents[component_keys[component_id]] = key
            return key

        for parent_id, child_ids in component_children.items():
            if parent_id is None:
                continue
            parent_state = states_by_id[parent_id]
            parent_key = component_keys[parent_id]
            entries: list[tuple[tuple[Any, ...], TreeNodeKey]] = []
            grouped_ids: set[str] = set()
            if parent_state.kind is ComponentKind.AXES:
                semantic_ids = [
                    component_id
                    for component_id in child_ids
                    if (
                        (profile := self.presentation.profile(
                            states_by_id[component_id]
                        ))
                        is not None
                        and profile.placement is EditorPlacement.SEMANTIC
                    )
                ]
                if semantic_ids:
                    key = register_group(
                        parent_id,
                        "axes_components",
                        "Axes Components",
                        semantic_ids,
                    )
                    entries.append(((-1, 0), key))
                    grouped_ids.update(semantic_ids)

            dynamic_groups: dict[
                tuple[ComponentKind, ComponentRole], list[str]
            ] = {}
            for component_id in child_ids:
                if component_id in grouped_ids:
                    continue
                state = states_by_id[component_id]
                spec = self.presentation.spec(state)
                if spec.group_title:
                    dynamic_groups.setdefault(
                        (state.kind, state.role), []
                    ).append(component_id)
            for (kind, role), member_ids in dynamic_groups.items():
                if len(member_ids) < 2:
                    continue
                spec = self.presentation.spec(states_by_id[member_ids[0]])
                key = register_group(
                    parent_id,
                    "component_group",
                    str(spec.group_title),
                    member_ids,
                    kind,
                    role,
                )
                entries.append(
                    (self.presentation.sort_key(states_by_id[member_ids[0]]), key)
                )
                grouped_ids.update(member_ids)
            for component_id in child_ids:
                if component_id in grouped_ids:
                    continue
                key = component_keys[component_id]
                node_parents[key] = parent_key
                entries.append(
                    (self.presentation.sort_key(states_by_id[component_id]), key)
                )
            entries.sort(key=lambda item: item[0])
            node_children[parent_key] = [key for _sort_key, key in entries]

        reachable: set[TreeNodeKey] = set()
        visiting: set[TreeNodeKey] = set()

        def visit(key: TreeNodeKey) -> None:
            if key in visiting:
                raise ValueError("Component tree presentation contains a cycle.")
            if key in reachable:
                raise ValueError(
                    "Component tree presentation contains a duplicate node."
                )
            visiting.add(key)
            reachable.add(key)
            for child in node_children.get(key, ()):
                visit(child)
            visiting.remove(key)

        for root_key in node_children.get(None, ()):
            visit(root_key)
        if set(component_keys.values()) - reachable:
            raise ValueError(
                "Component tree presentation contains unreachable components."
            )
        return (
            node_children, node_parents, component_children,
            component_keys, pointers, groups,
        )

    def _component_event(self, event: ComponentEvent) -> None:
        self._component_events((event,))

    def _component_events(self, events) -> None:
        events = tuple(events)
        if not events:
            return
        if any(
            event.kind in {ComponentEventKind.ADDED, ComponentEventKind.REMOVED}
            for event in events
        ):
            self._reset_from_registry()
            return
        if any(
            event.before is None
            or event.after is None
            or event.before.parent_id != event.after.parent_id
            or event.before.order != event.after.order
            or event.before.selector != event.after.selector
            for event in events
        ):
            self._reset_from_registry()
            return
        for event in events:
            index = self.index_for_component(event.component_id)
            if index.isValid():
                self.dataChanged.emit(
                    index,
                    index,
                    [Qt.DisplayRole, Qt.ToolTipRole, COMPONENT_SEARCH_ROLE],
                )

    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column != 0 or (parent.isValid() and parent.column() != 0):
            return QModelIndex()
        parent_key = self.node_key(parent) if parent.isValid() else None
        children = self._node_children.get(parent_key, ())
        if row >= len(children):
            return QModelIndex()
        node_key = children[row]
        return self.createIndex(row, column, self._pointers[node_key])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node_key = self.node_key(index)
        parent_key = self._node_parents.get(node_key)
        if parent_key is None:
            return QModelIndex()
        grandparent_key = self._node_parents.get(parent_key)
        try:
            row = self._node_children.get(grandparent_key, []).index(parent_key)
        except ValueError:
            return QModelIndex()
        return self.createIndex(row, 0, self._pointers[parent_key])

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        parent_key = self.node_key(parent) if parent.isValid() else None
        return len(self._node_children.get(parent_key, ()))

    def columnCount(self, _parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        node_key = self.node_key(index)
        group = self._groups.get(node_key)
        if group is not None:
            if role == Qt.DisplayRole:
                return group.label
            if role == Qt.ToolTipRole:
                return (
                    f"{group.label}\nUI-only group\n"
                    f"Parent: {group.parent_component_id}"
                )
            if role == COMPONENT_KIND_ROLE and group.kind is not None:
                return group.kind.value
            if role == COMPONENT_ROLE_ROLE and group.role is not None:
                return group.role.value
            if role == COMPONENT_SEARCH_ROLE:
                values = [group.label]
                if group.kind is not None:
                    values.append(group.kind.value)
                if group.role is not None:
                    values.append(group.role.value)
                return " ".join(values)
            if role == NODE_KEY_ROLE:
                return group.node_key
            if role == VIRTUAL_GROUP_ROLE:
                return True
            return None

        component_id = self.component_id(index)
        if not component_id or self.registry is None or component_id not in self.registry:
            return None
        state = self.registry.get(component_id).state
        if role == Qt.DisplayRole:
            parent_group = self._groups.get(
                self._node_parents.get(self._component_keys[component_id])
            )
            if parent_group is not None and parent_group.role is not None:
                try:
                    index_in_group = self._node_children[
                        parent_group.node_key
                    ].index(self._component_keys[component_id])
                except ValueError:
                    index_in_group = max(0, state.order)
                return self.presentation.grouped_label(state, index_in_group)
            return self.presentation.display_label(state)
        if role == Qt.ToolTipRole:
            return (
                f"ID: {state.id}\nKind: {state.kind.value}\n"
                f"Role: {state.role.value}\nParent: {state.parent_id or 'None'}"
            )
        if role == COMPONENT_ID_ROLE:
            return state.id
        if role == COMPONENT_KIND_ROLE:
            return state.kind.value
        if role == COMPONENT_ROLE_ROLE:
            return state.role.value
        if role == COMPONENT_SEARCH_ROLE:
            return " ".join(
                (
                    self.presentation.display_label(state),
                    str(self.data(index, Qt.DisplayRole) or ""),
                    state.kind.value,
                    state.role.value,
                )
            )
        if role == NODE_KEY_ROLE:
            return self._component_keys[state.id]
        if role == VIRTUAL_GROUP_ROLE:
            return False
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        if index.data(VIRTUAL_GROUP_ROLE):
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    @staticmethod
    def component_id(index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        pointer = index.internalPointer()
        return pointer.component_id if isinstance(pointer, _TreePointer) else None

    @staticmethod
    def node_key(index: QModelIndex) -> TreeNodeKey | None:
        if not index.isValid():
            return None
        pointer = index.internalPointer()
        return pointer.node_key if isinstance(pointer, _TreePointer) else None

    def index_for_node(self, node_key: TreeNodeKey) -> QModelIndex:
        parent_key = self._node_parents.get(node_key)
        try:
            row = self._node_children.get(parent_key, []).index(node_key)
        except ValueError:
            return QModelIndex()
        pointer = self._pointers.get(node_key)
        return self.createIndex(row, 0, pointer) if pointer is not None else QModelIndex()

    def index_for_component(self, component_id: str) -> QModelIndex:
        node_key = self._component_keys.get(str(component_id))
        pointer = self._pointers.get(node_key) if node_key is not None else None
        if pointer is None or pointer.component_id is None:
            return QModelIndex()
        return self.index_for_node(node_key)

    def children_ids(self, component_id: str | None) -> tuple[str, ...]:
        return tuple(self._component_children.get(component_id, ()))

    def visual_children_ids(
        self, node: str | TreeNodeKey | None
    ) -> tuple[str | TreeNodeKey, ...]:
        node_key = self._component_keys.get(node) if isinstance(node, str) else node
        return tuple(
            child.component_id if isinstance(child, ComponentNodeKey) else child
            for child in self._node_children.get(node_key, ())
        )


class ComponentTreeFilterProxyModel(QSortFilterProxyModel):
    """Filter Components while retaining every matching ancestor path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""
        self.setDynamicSortFilter(True)

    def set_query(self, query: str) -> None:
        query = normalized_query(query)
        if query == self._query:
            return
        self._query = query
        self.invalidateFilter()

    @property
    def query(self) -> str:
        return self._query

    def _matches(self, index: QModelIndex) -> bool:
        searchable = str(
            self.sourceModel().data(index, COMPONENT_SEARCH_ROLE) or ""
        ).casefold()
        return self._query in searchable

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._query:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if self._matches(index):
            return True
        ancestor = source_parent
        while ancestor.isValid():
            if self._matches(ancestor):
                return True
            ancestor = model.parent(ancestor)
        return any(
            self.filterAcceptsRow(child_row, index)
            for child_row in range(model.rowCount(index))
        )
