"""Project-scoped host for Components tree navigation and actions."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLineEdit,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
)

from mygui.figuremodify.components import (
    ComponentState,
    DeletionPolicy,
)
from mygui import status_messages
from mygui.widgets.common_widget.py_empty_state import PyEmptyState

from .dialogs import ComponentBatchDeleteDialog, DeleteCandidate
from .model import ComponentTreeFilterProxyModel, ComponentTreeModel
from .nodes import ComponentNodeKey, TreeNodeKey
from .view import ComponentTreeView
from mygui.application_theme import (
    bind_widget_qss,
    current_density_metrics,
    subscribe_theme_window,
)


@dataclass(slots=True)
class _TreeSession:
    expanded_keys: set[TreeNodeKey] = field(default_factory=set)


class ComponentTreeHost(QFrame):
    """Bind the Components tree to the active project's authoritative Canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("component_tree_host")
        bind_widget_qss(self, "mygui/widgets/component_tree/style.qss")
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
        subscribe_theme_window(self)
        self.apply_theme_metrics(current_density_metrics())
        self.tree.componentSelected.connect(self._tree_selected)
        self.tree.componentContextMenuRequested.connect(
            self._show_context_menu
        )
        self.model.aboutToRefresh.connect(self._before_model_refresh)
        self.model.refreshed.connect(self._after_model_refresh)

    def apply_theme_metrics(self, metrics) -> None:
        """Apply tree-host padding and search-field height from density metrics."""

        layout = self.layout()
        if layout is not None:
            pad = metrics.spacing_sm
            layout.setContentsMargins(pad, pad, pad, pad)
            layout.setSpacing(pad)
        self.search_input.setMinimumHeight(metrics.control)
        self.search_input.setMaximumHeight(metrics.control)

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

    def _show_context_menu(
        self, node_key: TreeNodeKey, global_position: QPoint
    ) -> None:
        canvas = self._canvas
        if not isinstance(node_key, ComponentNodeKey):
            return
        component_id = node_key.component_id
        if canvas is None or component_id not in canvas.component_registry:
            return
        previous = canvas.current_component_id
        if not canvas.select_component(component_id):
            if previous is not None:
                self._select_tree_only(previous)
            return
        controller = canvas.component_registry.get(component_id)
        state = controller.state
        menu = QMenu(self)
        delete_action = None
        batch_action = None
        duplicate_action = None
        delete_label = self.model.presentation.delete_label(state)
        if controller.DELETION_POLICY is DeletionPolicy.REMOVE:
            delete_action = menu.addAction(f"Delete {delete_label}")
            if len(self._batch_candidates(state)) > 1:
                batch_action = menu.addAction("Batch Delete Same Type...")
        duplicate_label = self.model.presentation.duplicate_label(state)
        if duplicate_label:
            duplicate_action = menu.addAction(duplicate_label)
        if menu.isEmpty():
            return
        action = menu.exec(global_position)
        if action is None:
            return
        if action is duplicate_action:
            try:
                new_id = canvas.duplicate_component(component_id)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    duplicate_label or "Duplicate Component",
                    f"Could not duplicate component: {exc}",
                )
                return
            if new_id is not None:
                self._select_and_show(new_id)
            return
        if action is delete_action:
            if not self._confirm_single_delete(component_id):
                return
            canvas.delete_components(
                (component_id,),
                anchor_id=component_id,
                reason="single",
                role_label=delete_label,
            )
            return
        if action is batch_action:
            self._run_batch_delete(state)

    def _source_label(self, component_id: str) -> str:
        index = self.model.index_for_component(component_id)
        return str(self.model.data(index, Qt.DisplayRole) or component_id)

    def _confirm_single_delete(self, component_id: str) -> bool:
        canvas = self._canvas
        label = self._source_label(component_id)
        detail = ""
        descendants = canvas.component_registry.descendants(component_id)
        if descendants:
            detail = f" and its {len(descendants)} child components"
        message = QMessageBox(self)
        message.setWindowTitle("Delete Component")
        message.setIcon(QMessageBox.Warning)
        message.setText(f"Delete {label}{detail}?")
        message.setInformativeText(
            f"Stable ID: {component_id}\nThis action cannot be undone."
        )
        delete_button = message.addButton(
            "Delete", QMessageBox.DestructiveRole
        )
        cancel_button = message.addButton(QMessageBox.Cancel)
        message.setDefaultButton(cancel_button)
        message.exec()
        return message.clickedButton() is delete_button

    def _batch_candidates(
        self, state: ComponentState
    ) -> list[DeleteCandidate]:
        registry = self._canvas.component_registry
        candidates = []
        parent_label = (
            self._source_label(state.parent_id)
            if state.parent_id is not None
            else "Figure"
        )
        cohort_key = (
            state.parent_id,
            state.kind.value,
            state.role.value,
            DeletionPolicy.REMOVE.value,
        )
        for component_id in self.model.children_ids(state.parent_id):
            controller = registry.get(component_id)
            candidate = controller.state
            if (
                candidate.kind is state.kind
                and candidate.role is state.role
                and controller.DELETION_POLICY is DeletionPolicy.REMOVE
            ):
                candidates.append(
                    DeleteCandidate(
                        candidate.id,
                        self._source_label(candidate.id),
                        parent_label,
                        cohort_key,
                    )
                )
        return candidates

    def _run_batch_delete(self, state: ComponentState) -> None:
        original_candidates = self._batch_candidates(state)
        dialog = ComponentBatchDeleteDialog(
            original_candidates,
            role_label=self.model.presentation.delete_label(state),
            parent=self,
        )
        accepted = dialog.exec() == QDialog.Accepted
        selected = dialog.selected_component_ids() if accepted else []
        dialog.deleteLater()
        if not selected:
            return
        try:
            current_candidates = self._batch_candidates(state)
        except Exception:
            current_candidates = []
        if current_candidates != original_candidates:
            status_messages.show_error(
                "The component group changed while the deletion dialog was "
                "open. Nothing was deleted."
            )
            return
        self._canvas.delete_components(
            selected,
            anchor_id=state.id,
            reason="batch",
            role_label=self.model.presentation.delete_label(state),
        )

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)
