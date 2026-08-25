"""Sheet table view and south-tab host widget."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pandas as pd

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QInputDialog,
    QMenu,
    QTabWidget,
    QTableView,
)

from mygui import status_messages
from mygui.database import (
    ColumnRef,
    ColumnType,
    TableChangeSet,
    TableMutationCommand,
    TableRepository,
)
from mygui.database.table_document import (
    DEFAULT_COLUMN_WIDTH,
    coerce_series,
    infer_column_type,
    new_id,
)
from .table_model import DependencyHandler, TableModel, TypedItemDelegate

if TYPE_CHECKING:
    from .py_subtable import PySubTable

class TableView(QTableView):
    """Provide the table view Qt widget."""

    def __init__(self, repository: TableRepository, project_id: str, sheet_id: str,
                 dependency_handler: DependencyHandler | None = None):
        super().__init__()
        self.repository = repository
        self.project_id = project_id
        self.sheet_id = sheet_id
        self.dependency_handler = dependency_handler
        self.table_model = TableModel(repository, project_id, sheet_id, self)
        self.setModel(self.table_model)
        self.setItemDelegate(TypedItemDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setSortingEnabled(False)
        self._disposed = False

        horizontal = self.horizontalHeader()
        horizontal.setMinimumSectionSize(60)
        horizontal.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        horizontal.setSectionResizeMode(QHeaderView.Interactive)
        horizontal.setSectionsMovable(False)
        horizontal.setFixedHeight(44)
        horizontal.setContextMenuPolicy(Qt.CustomContextMenu)
        horizontal.customContextMenuRequested.connect(self.header_context_menu)
        horizontal.sectionResized.connect(self._column_resized)

        vertical = self.verticalHeader()
        vertical.setSectionResizeMode(QHeaderView.Fixed)
        vertical.setDefaultSectionSize(24)
        vertical.setContextMenuPolicy(Qt.CustomContextMenu)
        vertical.customContextMenuRequested.connect(self.row_context_menu)

        self._applying_widths = False
        self._apply_column_widths()
        self.repository.transaction_committed.connect(self._repository_changed)
        self._init_actions()

    @property
    def sheet(self):
        """Return the sheet."""

        return self.repository.sheet(self.project_id, self.sheet_id)

    def _init_actions(self):
        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.copy_items)
        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.paste_items)
        delete_action = QAction("Clear", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self.delete_items)
        self.addActions([copy_action, paste_action, delete_action])

    def _repository_changed(self, changes: TableChangeSet):
        if changes.project_id == self.project_id and (changes.structure_changed or changes.metadata_changed):
            QTimer.singleShot(0, self._apply_column_widths)

    def _apply_column_widths(self):
        if self._disposed or self.project_id not in self.repository.projects:
            return
        self._applying_widths = True
        try:
            for index, column in enumerate(self.sheet.columns):
                self.setColumnWidth(index, column.width)
        finally:
            self._applying_widths = False

    def _column_resized(self, logical_index: int, _old_size: int, new_size: int):
        if self._applying_widths or not 0 <= logical_index < len(self.sheet.columns):
            return
        column = self.sheet.columns[logical_index]
        if column.width == new_size:
            return
        column.width = max(60, int(new_size))

    def copy_items(self):
        """Copy items."""

        selection = self.selectedIndexes()
        if not selection:
            return
        top = min(index.row() for index in selection)
        bottom = max(index.row() for index in selection)
        left = min(index.column() for index in selection)
        right = max(index.column() for index in selection)
        lines = []
        for row in range(top, bottom + 1):
            lines.append("\t".join(
                str(self.table_model.data(self.table_model.index(row, column), Qt.DisplayRole) or "")
                for column in range(left, right + 1)
            ))
        QGuiApplication.clipboard().setText("\n".join(lines))

    def paste_items(self):
        """Paste items."""

        start = self.currentIndex()
        if not start.isValid():
            status_messages.show_warning("Select a starting cell before pasting.")
            return
        text = QGuiApplication.clipboard().text()
        if not text:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized.endswith("\n"):
            normalized = normalized[:-1]
        rows = [line.split("\t") for line in normalized.split("\n")]
        if self.table_model.paste_block(start.row(), start.column(), rows):
            status_messages.show_success(f"Pasted {len(rows)} rows × {max(map(len, rows))} columns.")

    def delete_items(self):
        """Delete items."""

        self.table_model.clear_indexes(self.selectedIndexes())

    def insert_row(self):
        """Insert row."""

        row = self.currentIndex().row() if self.currentIndex().isValid() else self.sheet.row_count

        def redo():
            self.sheet.insert_rows(row, 1)

        def undo():
            self.sheet.remove_rows(row, 1)

        refs = {ColumnRef(self.project_id, self.sheet_id, column.id) for column in self.sheet.columns}
        self.repository.push(self.project_id, TableMutationCommand(
            "Insert row", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, refs, structure_changed=True, reason="insert-row"),
        ))

    def delete_row(self):
        """Delete row."""

        if self.sheet.row_count == 0:
            return
        row = self.currentIndex().row() if self.currentIndex().isValid() else self.sheet.row_count - 1
        removed: dict[str, pd.DataFrame] = {}

        def redo():
            removed["rows"] = self.sheet.remove_rows(row, 1)

        def undo():
            self.sheet.restore_rows(row, removed["rows"])

        refs = {ColumnRef(self.project_id, self.sheet_id, column.id) for column in self.sheet.columns}
        self.repository.push(self.project_id, TableMutationCommand(
            "Delete row", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, refs, structure_changed=True, reason="delete-row"),
        ))

    def move_row(self, delta: int):
        """Move row."""

        current = self.currentIndex()
        if not current.isValid():
            return
        source = current.row()
        destination = max(0, min(source + delta, self.sheet.row_count - 1))
        if source == destination:
            return

        def redo():
            self.sheet.move_row(source, destination)

        def undo():
            self.sheet.move_row(destination, source)

        refs = {ColumnRef(self.project_id, self.sheet_id, column.id) for column in self.sheet.columns}
        self.repository.push(self.project_id, TableMutationCommand(
            "Move row", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, refs, reason="move-row"),
        ))
        self.setCurrentIndex(self.table_model.index(destination, current.column()))

    def add_column(self):
        """Add column."""

        index = self.currentIndex().column() + 1 if self.currentIndex().isValid() else len(self.sheet.columns)
        column_id = new_id()
        name = self.sheet.unique_column_name(f"Column {index + 1}")

        def redo():
            self.sheet.add_column(name=name, index=index, column_id=column_id)

        def undo():
            self.sheet.remove_column(column_id)

        ref = ColumnRef(self.project_id, self.sheet_id, column_id)
        self.repository.push(self.project_id, TableMutationCommand(
            "Add column", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, {ref}, metadata_changed=True,
                           structure_changed=True, reason="add-column"),
        ))

    def delete_column(self):
        """Delete column."""

        current = self.currentIndex()
        if not current.isValid() or len(self.sheet.columns) <= 1:
            status_messages.show_warning("A sheet must contain at least one column.")
            return
        index = current.column()
        schema = deepcopy(self.sheet.columns[index])
        values = self.sheet.frame[schema.id].copy(deep=True)
        ref = ColumnRef(self.project_id, self.sheet_id, schema.id)
        dependency_actions = self.dependency_handler([ref], "delete") if self.dependency_handler else None
        if dependency_actions is False:
            return
        if dependency_actions is None:
            dependency_actions = (lambda: None, lambda: None)
        dependency_redo, dependency_undo = dependency_actions

        def redo():
            if dependency_redo() is False:
                return False
            self.sheet.remove_column(schema.id)
            return True

        def undo():
            self.sheet.restore_column(index, deepcopy(schema), values.copy(deep=True))
            if dependency_undo() is False:
                return False
            return True

        self.repository.push(self.project_id, TableMutationCommand(
            "Delete column", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, {ref}, metadata_changed=True,
                           structure_changed=True, reason="delete-column"),
            rollback_on_error=True,
        ))

    def move_column(self, delta: int):
        """Move column."""

        current = self.currentIndex()
        if not current.isValid():
            return
        source = current.column()
        destination = max(0, min(source + delta, len(self.sheet.columns) - 1))
        if source == destination:
            return

        def redo():
            self.sheet.move_column(source, destination)

        def undo():
            self.sheet.move_column(destination, source)

        self.repository.push(self.project_id, TableMutationCommand(
            "Move column", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, metadata_changed=True,
                           structure_changed=True, reason="move-column"),
        ))
        self.setCurrentIndex(self.table_model.index(current.row(), destination))

    def rename_column(self):
        """Rename column."""

        current = self.currentIndex()
        if not current.isValid():
            return
        schema = self.sheet.columns[current.column()]
        name, ok = QInputDialog.getText(self, "Rename Column", "Column name:", text=schema.name)
        if not ok:
            return
        try:
            new_name = self.sheet.validate_column_name(name, exclude_id=schema.id)
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return
        old_name = schema.name
        if old_name == new_name:
            return

        def redo():
            schema.name = new_name

        def undo():
            schema.name = old_name

        ref = ColumnRef(self.project_id, self.sheet_id, schema.id)
        self.repository.push(self.project_id, TableMutationCommand(
            "Rename column", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, {ref}, metadata_changed=True, reason="rename-column"),
        ))

    def change_column_type(self):
        """Change column type."""

        current = self.currentIndex()
        if not current.isValid():
            return
        schema = self.sheet.columns[current.column()]
        choices = [column_type.value for column_type in ColumnType]
        selected, ok = QInputDialog.getItem(
            self, "Column Type", "Type:", choices, choices.index(schema.type.value), False
        )
        if not ok:
            return
        target = ColumnType(selected)
        if target == schema.type:
            return
        try:
            converted = coerce_series(self.sheet.frame[schema.id], target)
            resolved = infer_column_type(self.sheet.frame[schema.id]) if target == ColumnType.AUTO else target
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return
        ref = ColumnRef(self.project_id, self.sheet_id, schema.id)
        dependency_actions = None
        if resolved in {
            ColumnType.TEXT,
            ColumnType.BOOLEAN,
            ColumnType.DATETIME,
            ColumnType.AUTO,
        } and self.dependency_handler:
            dependency_actions = self.dependency_handler([ref], "type")
        if dependency_actions is False:
            return
        if dependency_actions is None:
            dependency_actions = (lambda: None, lambda: None)
        dependency_redo, dependency_undo = dependency_actions
        old_type = schema.type
        old_values = self.sheet.frame[schema.id].copy(deep=True)

        def redo():
            if dependency_redo() is False:
                return False
            schema.type = resolved
            self.sheet.frame[schema.id] = converted.copy(deep=True)
            return True

        def undo():
            schema.type = old_type
            self.sheet.frame[schema.id] = old_values.copy(deep=True)
            if dependency_undo() is False:
                return False
            return True

        self.repository.push(self.project_id, TableMutationCommand(
            "Change column type", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, {ref}, metadata_changed=True, reason="column-type"),
            rollback_on_error=True,
        ))

    def header_context_menu(self, position):
        """Open the column-header context menu."""

        column = self.horizontalHeader().logicalIndexAt(position)
        if column < 0:
            return
        self.setCurrentIndex(self.table_model.index(max(0, self.currentIndex().row()), column))
        menu = QMenu(self)
        rename = menu.addAction("Rename Column")
        change_type = menu.addAction("Change Type")
        menu.addSeparator()
        add = menu.addAction("Add Column Right")
        delete = menu.addAction("Delete Column")
        left = menu.addAction("Move Left")
        right = menu.addAction("Move Right")
        menu.addSeparator()
        ascending = menu.addAction("Sort Rows Ascending")
        descending = menu.addAction("Sort Rows Descending")
        action = menu.exec(self.horizontalHeader().mapToGlobal(position))
        if action == rename:
            self.rename_column()
        elif action == change_type:
            self.change_column_type()
        elif action == add:
            self.add_column()
        elif action == delete:
            self.delete_column()
        elif action == left:
            self.move_column(-1)
        elif action == right:
            self.move_column(1)
        elif action == ascending:
            self.table_model.sort_by_column(column, True)
        elif action == descending:
            self.table_model.sort_by_column(column, False)

    def row_context_menu(self, position):
        """Open the row-header context menu."""

        row = self.verticalHeader().logicalIndexAt(position)
        if row < 0:
            return
        column = max(0, self.currentIndex().column())
        self.setCurrentIndex(self.table_model.index(row, column))
        menu = QMenu(self)
        insert = menu.addAction("Insert Row Above")
        delete = menu.addAction("Delete Row")
        up = menu.addAction("Move Up")
        down = menu.addAction("Move Down")
        action = menu.exec(self.verticalHeader().mapToGlobal(position))
        if action == insert:
            self.insert_row()
        elif action == delete:
            self.delete_row()
        elif action == up:
            self.move_row(-1)
        elif action == down:
            self.move_row(1)

    def dispose(self) -> None:
        """Detach repository callbacks and ignore queued UI refreshes."""

        if self._disposed:
            return
        self._disposed = True
        try:
            self.repository.transaction_committed.disconnect(
                self._repository_changed
            )
        except (RuntimeError, TypeError):
            pass
        self.setModel(None)


class SheetTabWidget(QTabWidget):
    """Provide the sheet tab widget Qt widget."""

    def __init__(self, subtable: "PySubTable"):
        super().__init__(subtable)
        self.subtable = subtable
        self.setTabsClosable(False)
        tab_bar = self.tabBar()
        tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._context_menu)
        self.tabBarDoubleClicked.connect(self.subtable.rename_sheet)

    def _context_menu(self, position):
        index = self.tabBar().tabAt(position)
        if index < 0 or index >= self.count() - 1:
            return
        menu = QMenu(self)
        rename = menu.addAction("Rename Sheet")
        delete = menu.addAction("Delete Sheet")
        action = menu.exec(self.tabBar().mapToGlobal(position))
        if action == rename:
            self.subtable.rename_sheet(index)
        elif action == delete:
            self.subtable.delete_sheet(index)
