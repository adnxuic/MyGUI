"""Present a typed table document through Qt's model/view widgets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Sequence, cast

import numpy as np
import pandas as pd

from PySide6.QtCore import QAbstractTableModel, QDateTime, QModelIndex, QTimer, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QDoubleValidator, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QStyledItemDelegate,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.database import (
    ColumnRef,
    ColumnType,
    TableChangeSet,
    TableMutationCommand,
    TableRepository,
    validate_component_name,
)
from mygui.database.table_document import (
    DEFAULT_COLUMN_WIDTH,
    PANDAS_DTYPES,
    coerce_series,
    display_value,
    infer_column_type,
    is_missing,
    new_id,
)


DependencyHandler = Callable[
    [list[ColumnRef], str],
    tuple[Callable[[], None], Callable[[], None]] | bool | None,
]


def _same_value(left: Any, right: Any) -> bool:
    if is_missing(left) and is_missing(right):
        return True
    try:
        return bool(left == right)
    except (TypeError, ValueError):
        return False


class TableModel(QAbstractTableModel):
    """Expose table data through Qt's model API."""

    def __init__(self, repository: TableRepository, project_id: str, sheet_id: str, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.project_id = project_id
        self.sheet_id = sheet_id
        self._error_cells: set[tuple[int, int]] = set()
        self.repository.transaction_committed.connect(self._repository_changed)

    @property
    def sheet(self):
        """Return the sheet."""

        return self.repository.sheet(self.project_id, self.sheet_id)

    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows exposed by the Qt model."""

        return 0 if parent.isValid() else self.sheet.row_count

    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns exposed by the Qt model."""

        return 0 if parent.isValid() else len(self.sheet.columns)

    def data(self, index, role=Qt.DisplayRole):
        """Return data for the requested Qt model role."""

        if not index.isValid() or not 0 <= index.row() < self.rowCount() or not 0 <= index.column() < self.columnCount():
            return None
        column = self.sheet.columns[index.column()]
        value = self.sheet.frame.at[index.row(), column.id]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return display_value(value, column.type)
        if role == Qt.CheckStateRole and column.type == ColumnType.BOOLEAN:
            if is_missing(value):
                return Qt.PartiallyChecked
            return Qt.Checked if bool(value) else Qt.Unchecked
        if role == Qt.TextAlignmentRole:
            if column.type == ColumnType.NUMBER:
                return Qt.AlignRight | Qt.AlignVCenter
            if column.type == ColumnType.BOOLEAN:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter
        if role == Qt.ToolTipRole:
            return display_value(value, column.type) or "Missing value"
        if role == Qt.BackgroundRole:
            if (index.row(), index.column()) in self._error_cells:
                return QBrush(QColor("#fecaca"))
            if is_missing(value):
                return QBrush(QColor("#f3f4f6"))
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Return display data for a Qt table header."""

        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and 0 <= section < self.columnCount():
                column = self.sheet.columns[section]
                return f"{column.name}\n{column.type.value}"
            if orientation == Qt.Vertical and 0 <= section < self.rowCount():
                return str(section + 1)
        if role == Qt.ToolTipRole and orientation == Qt.Horizontal and 0 <= section < self.columnCount():
            column = self.sheet.columns[section]
            return f"{column.name} ({column.type.value})\nID: {column.id}"
        return None

    def flags(self, index):
        """Return the Qt item flags for the requested model index."""

        if not index.isValid():
            return Qt.NoItemFlags
        result = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        if self.sheet.columns[index.column()].type == ColumnType.BOOLEAN:
            result |= Qt.ItemIsUserCheckable
        return result

    def _column_ref(self, column: int) -> ColumnRef:
        return ColumnRef(self.project_id, self.sheet_id, self.sheet.columns[column].id)

    def _mark_error(self, index: QModelIndex, message: str) -> None:
        key = (index.row(), index.column())
        self._error_cells.add(key)
        self.dataChanged.emit(index, index, [Qt.BackgroundRole])
        status_messages.show_error(message)

        def clear_error():
            self._error_cells.discard(key)
            try:
                current = self.index(*key)
                if current.isValid():
                    self.dataChanged.emit(current, current, [Qt.BackgroundRole])
            except RuntimeError:
                return

        QTimer.singleShot(1500, clear_error)

    def setData(self, index, value, role=Qt.EditRole):
        """Apply an edit from Qt's model/view API."""

        if not index.isValid() or role not in (Qt.EditRole, Qt.CheckStateRole):
            return False
        column = self.sheet.columns[index.column()]
        if role == Qt.CheckStateRole:
            value = value == Qt.Checked
        old_value = self.sheet.frame.at[index.row(), column.id]
        old_type = column.type
        try:
            resolved, converted = self.sheet.resolved_edit(column.id, [value])
        except ValueError as exc:
            self._mark_error(index, str(exc))
            return False
        new_value = converted[0]
        if _same_value(old_value, new_value) and old_type == resolved:
            return False

        ref = self._column_ref(index.column())

        def redo():
            self.sheet.set_cell(index.row(), column.id, value)

        def undo():
            if old_type == ColumnType.AUTO:
                self.sheet.frame[column.id] = self.sheet.frame[column.id].astype("object")
            else:
                self.sheet.frame[column.id] = self.sheet.frame[column.id].astype(PANDAS_DTYPES[old_type])
            column.type = old_type
            self.sheet.frame.at[index.row(), column.id] = old_value

        self.repository.push(self.project_id, TableMutationCommand(
            "Edit cell",
            self.repository,
            self.project_id,
            redo,
            undo,
            TableChangeSet(
                self.project_id,
                {ref},
                metadata_changed=old_type != resolved,
                reason="cell-edit",
            ),
        ))
        return True

    def _repository_changed(self, changes: TableChangeSet) -> None:
        if changes.project_id != self.project_id:
            return
        if changes.structure_changed:
            self.beginResetModel()
            self.endResetModel()
            return
        changed_columns = [
            self.sheet.column_index(ref.column_id)
            for ref in changes.changed_columns
            if ref.sheet_id == self.sheet_id and self.repository.has_ref(ref)
        ]
        if changed_columns and self.rowCount():
            first = self.index(0, min(changed_columns))
            last = self.index(self.rowCount() - 1, max(changed_columns))
            self.dataChanged.emit(first, last)
        if changes.metadata_changed:
            self.headerDataChanged.emit(Qt.Horizontal, 0, max(0, self.columnCount() - 1))

    def clear_indexes(self, indexes: Sequence[QModelIndex]) -> bool:
        """Clear indexes."""

        cells = sorted({(index.row(), index.column()) for index in indexes if index.isValid()})
        if not cells:
            return False
        old_values = {
            (row, self.sheet.columns[column].id): self.sheet.frame.iat[row, column]
            for row, column in cells
        }
        refs = {self._column_ref(column) for _, column in cells}

        def redo():
            for row, column in cells:
                schema = self.sheet.columns[column]
                self.sheet.frame.at[row, schema.id] = pd.NaT if schema.type == ColumnType.DATETIME else pd.NA

        def undo():
            for (row, column_id), old_value in old_values.items():
                self.sheet.frame.at[row, column_id] = old_value

        self.repository.push(self.project_id, TableMutationCommand(
            "Clear cells", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, refs, reason="clear-cells"),
        ))
        return True

    def paste_block(self, start_row: int, start_column: int, rows: Sequence[Sequence[Any]]) -> bool:
        """Paste block."""

        block = [list(row) for row in rows]
        if not block:
            return False
        width = max((len(row) for row in block), default=0)
        if width == 0:
            return False
        for row in block:
            row.extend([""] * (width - len(row)))

        old_row_count = self.sheet.row_count
        existing_count = max(0, min(width, len(self.sheet.columns) - start_column))
        existing_ids = self.sheet.column_ids[start_column:start_column + existing_count]
        old_types = {column_id: self.sheet.column(column_id).type for column_id in existing_ids}
        old_values = self.sheet.frame.loc[
            start_row:min(start_row + len(block) - 1, old_row_count - 1), existing_ids
        ].copy(deep=True) if existing_ids and start_row < old_row_count else pd.DataFrame(columns=existing_ids)

        try:
            for offset, column_id in enumerate(existing_ids):
                self.sheet.resolved_edit(column_id, [row[offset] for row in block])
        except ValueError as exc:
            self._mark_error(self.index(start_row, start_column + offset), str(exc))
            return False

        new_specs: list[tuple[str, str]] = []
        for offset in range(existing_count, width):
            new_specs.append((new_id(), self.sheet.unique_column_name(f"Column {start_column + offset + 1}")))

        def redo():
            self.sheet.ensure_rows(start_row + len(block))
            for column_id, name in new_specs:
                if column_id not in self.sheet.column_ids:
                    self.sheet.add_column(name=name, column_id=column_id)
            self.sheet.set_block(start_row, start_column, block)

        def undo():
            for column_id, old_type in old_types.items():
                schema = self.sheet.column(column_id)
                schema.type = old_type
                self.sheet.frame[column_id] = self.sheet.frame[column_id].astype(
                    PANDAS_DTYPES.get(old_type, "object")
                )
            if not old_values.empty:
                stop = start_row + len(old_values) - 1
                self.sheet.frame.loc[start_row:stop, existing_ids] = old_values.to_numpy()
            for column_id, _name in reversed(new_specs):
                if column_id in self.sheet.column_ids:
                    self.sheet.remove_column(column_id)
            self.sheet.truncate_rows(old_row_count)

        def changes():
            refs = {
                ColumnRef(self.project_id, self.sheet_id, column_id)
                for column_id in existing_ids + [column_id for column_id, _ in new_specs]
            }
            return TableChangeSet(
                self.project_id,
                refs,
                metadata_changed=bool(new_specs) or any(
                    self.repository.has_ref(ref) and self.sheet.column(ref.column_id).type != old_types.get(ref.column_id)
                    for ref in refs
                ),
                structure_changed=bool(new_specs) or start_row + len(block) > old_row_count,
                reason="paste",
            )

        self.repository.push(self.project_id, TableMutationCommand(
            "Paste cells", self.repository, self.project_id, redo, undo, changes,
        ))
        return True

    def sort_by_column(self, column: int, ascending: bool) -> None:
        """Sort by column."""

        if not 0 <= column < self.columnCount():
            return
        column_id = self.sheet.columns[column].id
        original_order: list[int] = []

        def redo():
            nonlocal original_order
            original_order = self.sheet.sort_rows(column_id, ascending)

        def undo():
            inverse = np.argsort(np.asarray(original_order))
            self.sheet.frame = self.sheet.frame.iloc[inverse].reset_index(drop=True)

        refs = {
            ColumnRef(self.project_id, self.sheet_id, schema.id)
            for schema in self.sheet.columns
        }
        self.repository.push(self.project_id, TableMutationCommand(
            "Sort rows", self.repository, self.project_id, redo, undo,
            TableChangeSet(self.project_id, refs, reason="sort-rows"),
        ))


class TypedItemDelegate(QStyledItemDelegate):
    """Render and edit typed item values in Qt item views."""

    def createEditor(self, parent, option, index):
        """Create the typed Qt editor for a table cell."""

        model = cast(TableModel, index.model())
        column_type = model.sheet.columns[index.column()].type
        if column_type == ColumnType.BOOLEAN:
            editor = QComboBox(parent)
            editor.addItems(["true", "false", ""])
            return editor
        if column_type == ColumnType.DATETIME:
            editor = QDateTimeEdit(parent)
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            return editor
        editor = QLineEdit(parent)
        if column_type == ColumnType.NUMBER:
            validator = QDoubleValidator(editor)
            validator.setNotation(QDoubleValidator.ScientificNotation)
            editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):
        """Set editor data."""

        text = str(index.data(Qt.EditRole) or "")
        if isinstance(editor, QComboBox):
            editor.setCurrentText(text)
        elif isinstance(editor, QDateTimeEdit):
            value = QDateTime.fromString(text, Qt.ISODate)
            if value.isValid():
                editor.setDateTime(value)
        elif isinstance(editor, QLineEdit):
            editor.setText(text)

    def setModelData(self, editor, model, index):
        """Set model data."""

        if isinstance(editor, QComboBox):
            value = editor.currentText()
        elif isinstance(editor, QDateTimeEdit):
            value = editor.dateTime().toString(Qt.ISODate)
        else:
            value = editor.text()
        model.setData(index, value, Qt.EditRole)


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


class PySubTable(QFrame):
    """Provide the py sub table Qt widget."""

    def __init__(self, repository: TableRepository, project_id: str,
                 dependency_handler: DependencyHandler | None = None):
        super().__init__()
        self.repository = repository
        self.project_id = project_id
        self.dependency_handler = dependency_handler
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("table_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.tabWidget = SheetTabWidget(self)
        self.tabWidget.setTabPosition(QTabWidget.South)
        self.tabWidget.tabBarClicked.connect(self._plus_clicked)
        self._views: dict[str, TableView] = {}
        self._build_tabs()
        self._build_toolbar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.tabWidget)

    @property
    def project(self):
        """Return the project."""

        return self.repository.project(self.project_id)

    def _build_tabs(self):
        self._dispose_tabs()
        self._views.clear()
        for sheet in self.project.sheets.values():
            view = TableView(self.repository, self.project_id, sheet.id, self.dependency_handler)
            self._views[sheet.id] = view
            self.tabWidget.addTab(view, sheet.name)
        plus = QWidget()
        self.tabWidget.addTab(plus, "+")

    def sync_sheets_from_repository(self) -> None:
        """Rebuild the sheet projection from authoritative Repository state."""

        self._build_tabs()

    def _dispose_tabs(self):
        while self.tabWidget.count():
            widget = self.tabWidget.widget(0)
            if isinstance(widget, TableView):
                widget.dispose()
            self.tabWidget.removeTab(0)
            if widget is not None:
                widget.deleteLater()

    def dispose(self) -> None:
        """Detach repository listeners before the project is removed."""

        self._dispose_tabs()
        self._views.clear()

    def _build_toolbar(self):
        groups = (
            (("Undo", self.undo), ("Redo", self.redo)),
            (
                ("Rename Sheet", self.rename_current_sheet),
                ("Delete Sheet", self.delete_current_sheet),
            ),
            (
                ("Add Row", lambda: self.current_view().insert_row()),
                ("Delete Row", lambda: self.current_view().delete_row()),
                ("Move Row Up", lambda: self.current_view().move_row(-1)),
                ("Move Row Down", lambda: self.current_view().move_row(1)),
            ),
            (
                ("Add Column", lambda: self.current_view().add_column()),
                ("Delete Column", lambda: self.current_view().delete_column()),
            ),
        )
        for group_index, actions in enumerate(groups):
            if group_index:
                self.toolbar.addSeparator()
            for text, callback in actions:
                action = self.toolbar.addAction(text)
                action.setToolTip(text)
                action.setStatusTip(text)
                action.triggered.connect(callback)

    def current_view(self) -> TableView:
        """Return the current view."""

        widget = self.tabWidget.currentWidget()
        if not isinstance(widget, TableView):
            if not self._views:
                raise RuntimeError("Project has no sheets.")
            return next(iter(self._views.values()))
        return widget

    def get_table(self, index: int) -> TableView:
        """Return table."""

        widget = self.tabWidget.widget(index)
        if not isinstance(widget, TableView):
            raise IndexError("Sheet index does not refer to a table.")
        return widget

    def undo(self):
        """Reverse this table mutation."""

        self.repository.undo_stack(self.project_id).undo()

    def redo(self):
        """Reapply this table mutation."""

        self.repository.undo_stack(self.project_id).redo()

    def current_sheet_index(self) -> int:
        """Return the current sheet index."""

        index = self.tabWidget.currentIndex()
        if 0 <= index < self.tabWidget.count() - 1:
            return index
        return 0

    def rename_current_sheet(self):
        """Rename current sheet."""

        self.rename_sheet(self.current_sheet_index())

    def delete_current_sheet(self):
        """Delete current sheet."""

        self.delete_sheet(self.current_sheet_index())

    def _plus_clicked(self, index: int):
        if index == self.tabWidget.count() - 1:
            self.add_new_sheet()

    def add_new_sheet(self, sheet_name: str | None = None, sheet=None) -> TableView:
        """Add new sheet."""

        previous_index = self.tabWidget.currentIndex()
        view = None
        added_sheet = None
        changes = TableChangeSet(
            self.project_id,
            metadata_changed=True,
            structure_changed=True,
            reason="add-sheet",
        )
        try:
            with self.repository.mutate(changes):
                added_sheet = (
                    self.project.add_sheet(sheet_name)
                    if sheet is None
                    else self.project.add_sheet(sheet=sheet)
                )
                view = TableView(
                    self.repository,
                    self.project_id,
                    added_sheet.id,
                    self.dependency_handler,
                )
                index = self.tabWidget.count() - 1
                inserted = self.tabWidget.insertTab(
                    index,
                    view,
                    added_sheet.name,
                )
                if inserted < 0:
                    raise RuntimeError("Could not add the sheet tab.")
                self._views[added_sheet.id] = view
                self.tabWidget.setCurrentIndex(inserted)
        except Exception:
            if added_sheet is not None:
                self._views.pop(added_sheet.id, None)
            if view is not None:
                index = self.tabWidget.indexOf(view)
                if index >= 0:
                    self.tabWidget.removeTab(index)
                view.dispose()
                view.setParent(None)
                view.deleteLater()
            if self.tabWidget.count():
                self.tabWidget.setCurrentIndex(
                    max(0, min(previous_index, self.tabWidget.count() - 1))
                )
            raise
        return view

    def rename_sheet(self, index: int):
        """Rename sheet."""

        if index < 0 or index >= self.tabWidget.count() - 1:
            return
        view = self.get_table(index)
        sheet = self.repository.sheet(self.project_id, view.sheet_id)
        name, ok = QInputDialog.getText(self, "Rename Sheet", "Sheet name:", text=sheet.name)
        if not ok:
            return
        try:
            cleaned = validate_component_name(name, "Sheet name")
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return
        if any(other.id != sheet.id and other.name.casefold() == cleaned.casefold()
               for other in self.project.sheets.values()):
            status_messages.show_error(f"Sheet name already exists: {cleaned}")
            return
        old_name = sheet.name
        if old_name == cleaned:
            return

        def set_name(value: str):
            sheet.name = value
            for tab_index in range(self.tabWidget.count() - 1):
                tab_view = self.tabWidget.widget(tab_index)
                if isinstance(tab_view, TableView) and tab_view.sheet_id == sheet.id:
                    self.tabWidget.setTabText(tab_index, value)
                    break

        self.repository.push(self.project_id, TableMutationCommand(
            "Rename sheet", self.repository, self.project_id,
            lambda: set_name(cleaned), lambda: set_name(old_name),
            TableChangeSet(self.project_id, metadata_changed=True, reason="rename-sheet"),
        ))
        status_messages.show_success(f"Sheet renamed to {cleaned}.")

    def delete_sheet(self, index: int):
        """Delete sheet."""

        if index < 0 or index >= self.tabWidget.count() - 1:
            return
        if len(self.project.sheets) <= 1:
            status_messages.show_warning("A project must contain at least one sheet.")
            return
        view = self.get_table(index)
        sheet = self.repository.sheet(self.project_id, view.sheet_id)
        refs = [ColumnRef(self.project_id, sheet.id, column.id) for column in sheet.columns]
        dependency_actions = self.dependency_handler(refs, "delete-sheet") if self.dependency_handler else None
        if dependency_actions is False:
            return
        if dependency_actions is None:
            dependency_actions = (lambda: None, lambda: None)
        dependency_redo, dependency_undo = dependency_actions
        original_index = list(self.project.sheets).index(sheet.id)

        def select_nearest_sheet(preferred: int):
            if self.project.sheets:
                self.tabWidget.setCurrentIndex(min(preferred, len(self.project.sheets) - 1))

        def redo():
            if dependency_redo() is False:
                return False
            self.project.sheets.pop(sheet.id, None)
            self._build_tabs()
            select_nearest_sheet(original_index)
            return True

        def undo():
            items = list(self.project.sheets.items())
            items.insert(original_index, (sheet.id, sheet))
            self.project.sheets.clear()
            self.project.sheets.update(items)
            self._build_tabs()
            self.tabWidget.setCurrentIndex(original_index)
            if dependency_undo() is False:
                return False
            return True

        committed = self.repository.push(self.project_id, TableMutationCommand(
            "Delete sheet", self.repository, self.project_id, redo, undo,
            TableChangeSet(
                self.project_id, set(refs), metadata_changed=True,
                structure_changed=True, reason="delete-sheet",
            ),
            rollback_on_error=True,
        ))
        if committed:
            status_messages.show_success(f"Sheet deleted: {sheet.name}.")
