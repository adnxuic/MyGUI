"""Stable-ID Qt view for Components tree navigation."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeView

from .nodes import COMPONENT_ID_ROLE, NODE_KEY_ROLE, TreeNodeKey
from mygui.application_theme import current_density_metrics, subscribe_theme_window


class ComponentTreeView(QTreeView):
    """Single-selection tree that emits requests for real Components only."""

    componentSelected = Signal(str)
    componentContextMenuRequested = Signal(object, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("component_tree_view")
        self.setHeaderHidden(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu_requested)
        self._theme_row_height = current_density_metrics().tree
        subscribe_theme_window(self)

    def sizeHintForRow(self, row: int) -> int:
        """Honor the density tree-row floor so large UI fonts are not clipped."""

        return max(super().sizeHintForRow(row), int(self._theme_row_height))

    def apply_theme_metrics(self, metrics) -> None:
        """Apply Components-tree row height from the published density metrics."""

        self._theme_row_height = metrics.tree
        self.doItemsLayout()

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        indexes = selected.indexes()
        if not indexes:
            return
        component_id = indexes[0].data(COMPONENT_ID_ROLE)
        if component_id:
            self.componentSelected.emit(str(component_id))

    def _context_menu_requested(self, position: QPoint) -> None:
        index = self.indexAt(position)
        if not index.isValid():
            return
        node_key = index.data(NODE_KEY_ROLE)
        if node_key is not None:
            self.componentContextMenuRequested.emit(
                node_key, self.viewport().mapToGlobal(position)
            )

    def selected_component_id(self) -> str | None:
        index = self.currentIndex()
        value = index.data(COMPONENT_ID_ROLE) if index.isValid() else None
        return str(value) if value else None

    def select_component(self, component_id: str) -> bool:
        proxy = self.model()
        source_index = proxy.sourceModel().index_for_component(
            str(component_id)
        )
        proxy_index = proxy.mapFromSource(source_index)
        if not proxy_index.isValid():
            return False
        self.setCurrentIndex(proxy_index)
        self.scrollTo(proxy_index, QAbstractItemView.EnsureVisible)
        return True

    def expanded_node_keys(self) -> set[TreeNodeKey]:
        result: set[TreeNodeKey] = set()
        proxy = self.model()

        def visit(parent=QModelIndex()):
            for row in range(proxy.rowCount(parent)):
                index = proxy.index(row, 0, parent)
                node_key = index.data(NODE_KEY_ROLE)
                if node_key is not None and self.isExpanded(index):
                    result.add(node_key)
                visit(index)

        visit()
        return result

    def restore_expanded(self, node_keys: set[TreeNodeKey]) -> None:
        proxy = self.model()
        source = proxy.sourceModel()
        for node_key in node_keys:
            index = proxy.mapFromSource(source.index_for_node(node_key))
            if index.isValid():
                self.setExpanded(index, True)

    def expand_component_path(self, component_id: str) -> None:
        proxy = self.model()
        source = proxy.sourceModel()
        source_index = source.index_for_component(component_id)
        while source_index.isValid():
            proxy_index = proxy.mapFromSource(source_index)
            if proxy_index.isValid():
                self.setExpanded(proxy_index, True)
            source_index = source.parent(source_index)
