"""Qt table model and cell delegate for one sheet."""

from __future__ import annotations

from typing import Any, Callable, Sequence, cast

import numpy as np
import pandas as pd

from PySide6.QtCore import QAbstractTableModel, QDateTime, QModelIndex, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QLineEdit,
    QStyledItemDelegate,
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
    PANDAS_DTYPES,
    display_value,
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
