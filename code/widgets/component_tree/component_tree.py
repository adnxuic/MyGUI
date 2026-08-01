"""Project-scoped host for Components tree navigation and actions."""

from __future__ import annotations

from dataclasses import dataclass, field
import os

from Qt_core import *

from code.figuremodify.components import (
    ComponentKind,
    ComponentState,
    DeletionPolicy,
)
from code.widgets import qss_func
from code.widgets.common_widget.py_empty_state import PyEmptyState

from .dialogs import ComponentBatchDeleteDialog
from .model import ComponentTreeFilterProxyModel, ComponentTreeModel
from .nodes import TreeNodeKey
from .view import ComponentTreeView


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


@dataclass(slots=True)
class _TreeSession:
    expanded_keys: set[TreeNodeKey] = field(default_factory=set)


class ComponentTreeHost(QFrame):
    """Bind the Components tree to the active project's authoritative Canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("component_tree_host")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self._canvas = None
        self._canvas_selection_connection = None
        self._project_id: str | None = None
        self._sessions: dict[str, _TreeSession] = {}
        self._refresh_state: tuple[str | None, set[TreeNodeKey]] | None = None
        self._syncing_selection = False
        self._disposed = False

        self.search_input = QLineEdit(self)
        self.search_input.setObjectName("component_tree_search")
        self.search_input.setPlaceholderText("Search components")
        self.search_input.setClearButtonEnabled(True)

        self.model = ComponentTreeModel(self)
        self.proxy_model = ComponentTreeFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.tree = ComponentTreeView(self)
        self.tree.setModel(self.proxy_model)

        self.empty_state = PyEmptyState(
            "No project",
            "Create or open a project to inspect its Components.",
            parent=self,
        )
        self.content_stack = QStackedWidget(self)
        self.content_stack.addWidget(self.empty_state)
        self.content_stack.addWidget(self.tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.search_input)
        layout.addWidget(self.content_stack, 1)

        self.search_input.textChanged.connect(self._filter_changed)
        self.tree.componentSelected.connect(self._tree_selected)
        self.tree.componentContextMenuRequested.connect(
            self._show_context_menu
        )
        self.model.aboutToRefresh.connect(self._before_model_refresh)
        self.model.refreshed.connect(self._after_model_refresh)

    @property
    def canvas(self):
        return self._canvas

    def set_canvas(self, canvas) -> None:
        """Bind the active Canvas and restore only its UI expansion state."""

        if canvas is self._canvas:
            self._restore_current_session()
            return
        self._save_current_session()
        self._disconnect_canvas()
        self._canvas = canvas
        self._project_id = str(canvas.project_id) if canvas is not None else None
        blocked = self.search_input.blockSignals(True)
        try:
            self.search_input.clear()
        finally:
            self.search_input.blockSignals(blocked)
        self.proxy_model.set_query("")
        self.model.set_registry(
            canvas.component_registry if canvas is not None else None,
            canvas.editor_registry if canvas is not None else None,
        )
        if canvas is None:
            self.content_stack.setCurrentWidget(self.empty_state)
            return
        self.content_stack.setCurrentWidget(self.tree)
        signal = getattr(canvas, "componentSelectionChanged", None)
        if signal is not None:
            signal.connect(self._canvas_selected)
            self._canvas_selection_connection = signal
        session = self._sessions.setdefault(self._project_id, _TreeSession())
        registry = canvas.component_registry
        component_id = (
            canvas.current_component_id
            if canvas.current_component_id in registry
            else canvas.current_axes_component_id
            if canvas.current_axes_component_id in registry
            else canvas.root_component_id
        )
        self._select_and_show(component_id)
        self.tree.restore_expanded(session.expanded_keys)
        self.tree.expand_component_path(component_id)

    def forget_project(self, project_id: str) -> None:
        self._sessions.pop(str(project_id), None)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._save_current_session()
        self._disconnect_canvas()
        self._canvas = None
        self._project_id = None
        self.model.dispose()

    def _disconnect_canvas(self) -> None:
        signal = self._canvas_selection_connection
        if signal is not None:
            try:
                signal.disconnect(self._canvas_selected)
            except (RuntimeError, TypeError):
                pass
        self._canvas_selection_connection = None

    def _save_current_session(self) -> None:
        if self._project_id is None or self._canvas is None:
            return
        session = self._sessions.setdefault(self._project_id, _TreeSession())
        if not self.proxy_model.query:
            session.expanded_keys = self.tree.expanded_node_keys()

    def _restore_current_session(self) -> None:
        if self._project_id is None or self._canvas is None:
            return
        session = self._sessions.setdefault(self._project_id, _TreeSession())
        registry = self._canvas.component_registry
        selected = (
            self._canvas.current_component_id
            if self._canvas.current_component_id in registry
            else self._canvas.current_axes_component_id
            if self._canvas.current_axes_component_id in registry
            else self._canvas.root_component_id
        )
        self.tree.restore_expanded(session.expanded_keys)
        self._select_and_show(selected)

    def _before_model_refresh(self) -> None:
        self._refresh_state = (
            self._canvas.current_component_id if self._canvas is not None else None,
            self.tree.expanded_node_keys(),
        )

    def _after_model_refresh(self) -> None:
        if self._refresh_state is None:
            return
        selected, expanded = self._refresh_state
        self._refresh_state = None
        self.tree.restore_expanded(expanded)
        if (
            selected
            and self._canvas is not None
            and selected in self._canvas.component_registry
        ):
            self._select_tree_only(selected)
            self.tree.expand_component_path(selected)

    def _filter_changed(self, text: str) -> None:
        if text and not self.proxy_model.query:
            self._save_current_session()
        self._syncing_selection = True
        try:
            self.proxy_model.set_query(text)
        finally:
            self._syncing_selection = False
        if text:
            self.tree.expandAll()
            current = (
                self._canvas.current_component_id
                if self._canvas is not None
                else None
            )
            if current and not self._select_tree_only(current):
                self._syncing_selection = True
                try:
                    self.tree.clearSelection()
                    self.tree.setCurrentIndex(QModelIndex())
                finally:
                    self._syncing_selection = False
            return
        if self._project_id is not None:
            session = self._sessions.get(self._project_id)
            if session is not None:
                self.tree.collapseAll()
                self.tree.restore_expanded(session.expanded_keys)
        if self._canvas is not None:
            current = self._canvas.current_component_id
            if current in self._canvas.component_registry:
                self._select_tree_only(current)
                self.tree.expand_component_path(current)

    def _tree_selected(self, component_id: str) -> None:
        if self._syncing_selection or self._canvas is None:
            return
        if component_id not in self._canvas.component_registry:
            return
        previous = self._canvas.current_component_id
        if not self._canvas.select_component(component_id) and previous:
            self._select_tree_only(previous)

    def _canvas_selected(self, component_id: str) -> None:
        if self._canvas is None:
            return
        if component_id not in self._canvas.component_registry:
            return
        if self.proxy_model.query and not self._select_tree_only(component_id):
            self.search_input.clear()
        else:
            self._select_tree_only(component_id)
        self.tree.expand_component_path(component_id)

    def _select_tree_only(self, component_id: str) -> bool:
        self._syncing_selection = True
        try:
            return self.tree.select_component(component_id)
        finally:
            self._syncing_selection = False

    def _select_and_show(self, component_id: str) -> None:
        if self._canvas.select_component(component_id):
            self._select_tree_only(component_id)
            self.tree.expand_component_path(component_id)

    def _fallback_component(
        self,
        component_id: str,
        deleting: set[str] | None = None,
    ) -> str | None:
        if self._canvas is None:
            return None
        registry = self._canvas.component_registry
        if component_id not in registry:
            return self._canvas.root_component_id
        deleting = set(deleting or {component_id})
        state = registry.get(component_id).state
        siblings = list(self.model.children_ids(state.parent_id))
        try:
            index = siblings.index(component_id)
        except ValueError:
            index = -1
        for candidate in siblings[index + 1 :]:
            if candidate in registry and candidate not in deleting:
                return candidate
        for candidate in reversed(siblings[:index]):
            if candidate in registry and candidate not in deleting:
                return candidate
        parent_id = state.parent_id
        visited: set[str] = set()
        while parent_id is not None and parent_id in deleting:
            if parent_id in visited or parent_id not in registry:
                parent_id = None
                break
            visited.add(parent_id)
            parent_id = registry.get(parent_id).state.parent_id
        return parent_id or self._canvas.root_component_id

    def _show_context_menu(
        self, component_id: str, global_position: QPoint
    ) -> None:
        canvas = self._canvas
        if canvas is None or component_id not in canvas.component_registry:
            return
        controller = canvas.component_registry.get(component_id)
        state = controller.state
        menu = QMenu(self)
        delete_action = None
        batch_action = None
        if state.kind is ComponentKind.AXES:
            delete_action = menu.addAction("Delete Axes")
        elif controller.DELETION_POLICY is DeletionPolicy.REMOVE:
            delete_action = menu.addAction("Delete Component")
            if len(self._batch_candidates(state)) > 1:
                batch_action = menu.addAction("Batch Delete Same Type...")
        if menu.isEmpty():
            return
        action = menu.exec(global_position)
        if action is None:
            return
        if action is delete_action:
            fallback = self._fallback_component(component_id, {component_id})
            succeeded = (
                canvas.request_delete_axes(component_id)
                if state.kind is ComponentKind.AXES
                else canvas.delete_component_group(
                    (component_id,), state.role.value.replace("_", " ")
                )
            )
            if succeeded:
                self._select_after_delete(fallback)
            return
        if action is batch_action:
            self._run_batch_delete(state)

    def _batch_candidates(
        self, state: ComponentState
    ) -> list[tuple[str, str]]:
        registry = self._canvas.component_registry
        candidates = []
        for controller in registry.children(state.parent_id):
            candidate = controller.state
            if (
                candidate.kind is state.kind
                and candidate.role is state.role
                and controller.DELETION_POLICY is DeletionPolicy.REMOVE
            ):
                candidates.append(
                    (
                        candidate.id,
                        self.model.component_display_label(candidate),
                    )
                )
        return candidates

    def _run_batch_delete(self, state: ComponentState) -> None:
        dialog = ComponentBatchDeleteDialog(
            self._batch_candidates(state),
            role_label=state.role.value.replace("_", " "),
            parent=self,
        )
        accepted = dialog.exec() == QDialog.Accepted
        selected = dialog.selected_component_ids() if accepted else []
        dialog.deleteLater()
        if not selected:
            return
        fallback = self._fallback_component(state.id, set(selected))
        succeeded = self._canvas.delete_component_group(
            selected, state.role.value.replace("_", " ")
        )
        if succeeded and state.id in selected:
            self._select_after_delete(fallback)

    def _select_after_delete(self, fallback: str | None) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        registry = canvas.component_registry
        target = fallback if fallback in registry else canvas.root_component_id
        if target in registry:
            canvas.select_component(target)

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)
