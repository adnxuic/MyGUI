import sys
from typing import cast

from PySide6.QtWidgets import QWidget

from Qt_core import *
import numpy as np

from code.database.py_database import databases
from code.database.py_database import PyDatabase
from code.database.py_database import validate_project_component_name


class TableModel(QAbstractTableModel):
    def __init__(self, database: PyDatabase):
        super().__init__()

        self.database = database

        data = [["" for _ in range(5)] for _ in range(20)]
        self._data = np.array(data, dtype=object)
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(0)
        self._sync_timer.timeout.connect(self._sync_to_database)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            value = self._data[index.row(), index.column()]
            return str(value) if value is not None else ""

    def rowCount(self, index=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, index=QModelIndex()):
        return self._data.shape[1]

    def flags(self, index):
        return super().flags(index) | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            self._data[index.row(), index.column()] = value
            self.dataChanged.emit(index, index)
            self.schedule_database_sync()
            # print('setData:', value)
            # print(self._data)
            return True
        return False

    def addRow(self):
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        new_row = np.array([[""] * self._data.shape[1]], dtype=object)
        self._data = np.vstack([self._data, new_row])
        self.endInsertRows()

    def addColumn(self):
        self.beginInsertColumns(QModelIndex(), self.columnCount(), self.columnCount())
        new_col = np.array([[""] * self._data.shape[0]], dtype=object).T
        self._data = np.hstack([self._data, new_col])
        self.endInsertColumns()

    def clearData(self, indexes):
        for index in indexes:
            if index.isValid():
                self.setData(index, "", Qt.EditRole)

    def Individual_sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        # Extract column data
        col_data = self._data[:, column]
        # Split non-empty and empty values
        non_null_data = col_data[col_data != '']
        null_data = col_data[col_data == '']

        try:
            non_null_data = non_null_data.astype(float)
            non_null_data = np.sort(non_null_data, kind='mergesort')
        except ValueError:
            non_null_data = np.sort(non_null_data, kind='mergesort')

        if order == Qt.DescendingOrder:
            non_null_data = non_null_data[::-1]

        # Rebuild the column with sorted non-empty values followed by empty cells
        sorted_data = np.concatenate((non_null_data, null_data))
        self._data[:, column] = sorted_data
        self.layoutChanged.emit()
        self.schedule_database_sync()

    def sort(self, column, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        # Extract column data
        col_data = self._data[:, column]
        # Split non-empty values and their row indices
        valid_indices = np.where(col_data != '')[0]
        valid_data = col_data[valid_indices]

        null_data_indices = np.where(col_data == '')[0]

        try:
            valid_data = valid_data.astype(float)
            sorted_indices = np.argsort(valid_data, kind='mergesort')
        except ValueError:
            sorted_indices = np.argsort(valid_data, kind='mergesort')

        if order == Qt.DescendingOrder:
            sorted_indices = sorted_indices[::-1]

        # Merge index arrays to get the final full-row sort order
        final_indices = np.concatenate((valid_indices[sorted_indices], null_data_indices))

        # Reorder the full table array
        self._data = self._data[final_indices]
        self.layoutChanged.emit()
        self.schedule_database_sync()

    # Database-related operations
    def schedule_database_sync(self):
        self._sync_timer.start()

    def flush_database_sync(self):
        if self._sync_timer.isActive():
            self._sync_timer.stop()
        self._sync_to_database()

    @staticmethod
    def _cell_has_value(value) -> bool:
        return value is not None and value != ""

    def _column_data(self, column: int) -> np.ndarray:
        col_data = self._data[:, column]
        non_null_data = col_data[[self._cell_has_value(value) for value in col_data]]
        try:
            return non_null_data.astype(float)
        except ValueError:
            return non_null_data.astype(str)

    def _sync_to_database(self):
        # Extract each column's data
        model_column_names = {str(i + 1) for i in range(self.columnCount())}
        for i in range(self.columnCount()):
            non_null_data = self._column_data(i)
            column_name = str(i + 1)
            # Check whether the column has data
            if len(non_null_data) > 0:
                # Convert and save to the database
                self.database.update_data(i + 1, non_null_data)
            elif self.database.has_connections(column_name):
                self.database.update_data(i + 1, np.array([], dtype=float))
            elif column_name in self.database.data:
                self.database.remove_data(column_name)

        for column_name in list(self.database.data.keys()):
            if column_name not in model_column_names:
                if self.database.has_connections(column_name):
                    self.database.update_data(column_name, np.array([], dtype=float))
                else:
                    self.database.remove_data(column_name)

    def load_columns(self, columns: dict):
        numeric_columns = {}
        for column_name, values in columns.items():
            try:
                column_index = int(column_name)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid column name in project: {column_name}") from exc
            if column_index < 1:
                raise ValueError(f"Invalid column index in project: {column_name}")
            numeric_columns[column_index] = list(values)

        row_count = max([20] + [len(values) for values in numeric_columns.values()])
        column_count = max([5] + list(numeric_columns.keys()))
        loaded = np.array([["" for _ in range(column_count)] for _ in range(row_count)], dtype=object)

        for column_index, values in numeric_columns.items():
            for row_index, value in enumerate(values):
                loaded[row_index, column_index - 1] = "" if value is None else value

        self.beginResetModel()
        self._data = loaded
        self.endResetModel()
        self.schedule_database_sync()


class TableView(QTableView):
    def __init__(self, database: PyDatabase):
        super().__init__()

        model = TableModel(database)
        self.setModel(model)
        self.model = cast(TableModel, self.model())

        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.selectionModel().currentChanged.connect(self.check_need_more_cells)
        self.initActions()

        # Header right-click context menu
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.headerContextMenu)

    def check_need_more_cells(self, current, previous):
        if current.row() == self.model.rowCount() - 1:
            self.model.addRow()
        if current.column() == self.model.columnCount() - 1:
            self.model.addColumn()

    def initActions(self):
        copyAction = QAction("Copy", self)
        copyAction.setShortcut("Ctrl+C")
        copyAction.triggered.connect(self.copyItems)

        pasteAction = QAction("Paste", self)
        pasteAction.setShortcut("Ctrl+V")
        pasteAction.triggered.connect(self.pasteItems)

        deleteAction = QAction("Delete", self)
        deleteAction.setShortcut("Delete")
        deleteAction.triggered.connect(self.deleteItems)

        self.addAction(copyAction)
        self.addAction(pasteAction)
        self.addAction(deleteAction)

    def copyItems(self):
        selection = self.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            cols = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = cols[-1] - cols[0] + 1
            table_contents = ''
            for r in range(rowcount):
                if r > 0:
                    table_contents += '\n'
                for c in range(colcount):
                    if c > 0:
                        table_contents += '\t'
                    index = self.model.index(rows[0] + r, cols[0] + c)
                    item = self.model.data(index, Qt.DisplayRole)
                    if item:
                        table_contents += item
            QGuiApplication.clipboard().setText(table_contents)

    def pasteItems(self):
        clipboard = QGuiApplication.clipboard().text()
        if clipboard:
            startPosition = self.currentIndex()
            rows = clipboard.split('\n')
            for i, row in enumerate(rows):
                columns = row.split('\t')
                for j, column in enumerate(columns):
                    rowPosition = startPosition.row() + i
                    colPosition = startPosition.column() + j
                    if rowPosition >= self.model.rowCount():
                        self.model.addRow()
                    if colPosition >= self.model.columnCount():
                        self.model.addColumn()
                    index = self.model.index(rowPosition, colPosition)
                    self.model.setData(index, column, Qt.EditRole)

    def deleteItems(self):
        selection = self.selectedIndexes()
        self.model.clearData(selection)

    def flush_database_sync(self):
        self.model.flush_database_sync()

    def headerContextMenu(self, pos):
        menu = QMenu()

        Individual_sortAscAction = menu.addAction("单独升序")
        Individual_sortDescAction = menu.addAction("单独逆序")
        sortAscAction = menu.addAction("升序")
        sortDescAction = menu.addAction("逆序")

        action = menu.exec(self.horizontalHeader().mapToGlobal(pos))
        column = self.horizontalHeader().logicalIndexAt(pos)
        if action == Individual_sortAscAction:
            self.model.Individual_sort(column, Qt.AscendingOrder)
        elif action == Individual_sortDescAction:
            self.model.Individual_sort(column, Qt.DescendingOrder)
        elif action == sortAscAction:
            self.model.sort(column, Qt.AscendingOrder)
        elif action == sortDescAction:
            self.model.sort(column, Qt.DescendingOrder)

    def add_excel_data(self, col_data: list, index):
        """
        Append a column of data to the table view at the given position.
        :param col_data: List of values for the column.
        :param index: Column index where data should be inserted.
        """
        # Ensure the model has enough columns for the new data
        if index >= self.model.columnCount():
            for i in range(index - self.model.columnCount() + 1):
                self.model.addColumn()

        # Add each value to the new column
        for row, data in enumerate(col_data):
            # Add a row when data exceeds current row count
            if row >= self.model.rowCount():
                self.model.addRow()
            # Resolve the model index for this cell
            model_index = self.model.index(row, index)
            # Set the cell value
            self.model.setData(model_index, data, Qt.EditRole)

    def load_columns(self, columns: dict):
        self.model.load_columns(columns)


# Custom QTabWidget
class SheetTabWidget(QTabWidget):
    def __init__(self, table_name: str, parent=None):
        super().__init__(parent)
        self.table_name = table_name

        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            pos = event.position().toPoint()
            pos.setY(pos.y() - self.tabBar().y())
            clicked_tab_index = self.tabBar().tabAt(pos)
            if clicked_tab_index != -1:
                self.show_context_menu(event.globalPosition().toPoint(), clicked_tab_index)
        super().mousePressEvent(event)

    def show_context_menu(self, position, tab_index):
        if tab_index < 0 or tab_index == self.count() - 1:
            return

        menu = QMenu()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec(position)

        if action == rename_action:
            old_name = self.tabText(tab_index)
            new_name, ok = QInputDialog.getText(self, "Rename Sheet", "Sheet name:", text=old_name)
            if not ok:
                return
            try:
                subtable = self.parent()
                if subtable is not None and hasattr(subtable, "rename_sheet"):
                    subtable.rename_sheet(old_name, new_name)
            except Exception as exc:
                QMessageBox.warning(self, "Rename Sheet", str(exc))
            return

        if action == delete_action:
            if self.count() > 2:
                response = QMessageBox.question(
                    self,
                    "Confirm Delete",
                    "Are you sure you want to delete this sheet?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if response == QMessageBox.Yes:
                    sheet_name = self.tabText(tab_index)
                    widget = self.widget(tab_index)
                    self.removeTab(tab_index)
                    PyDatabase.unregister_sheet(self.table_name, sheet_name)
                    widget.deleteLater()
            return


class PySubTable(QFrame):
    def __init__(self, table_name: str, pydatabase: PyDatabase, first_sheet_name: str = "Sheet1",
                 sheet_renamed_callback=None):
        super().__init__()

        self.table_name = validate_project_component_name(table_name, "Project name")
        self.sheet_renamed_callback = sheet_renamed_callback

        self.setMouseTracking(True)

        first_sheet_name = validate_project_component_name(first_sheet_name, "Sheet name")
        PyDatabase.register_sheet(self.table_name, first_sheet_name, pydatabase)

        # Use the custom QTabWidget
        self.tabWidget = SheetTabWidget(self.table_name, self)
        self.tabWidget.setTabPosition(QTabWidget.South)
        self.tabWidget.addTab(TableView(databases[self.table_name][first_sheet_name]), first_sheet_name)

        # Create "+" button tab; keep it non-selectable
        self.plusButton = QPushButton("+")
        self.plusButton.clicked.connect(self.add_new_sheet)
        self.tabWidget.addTab(QWidget(), "")
        self.tabWidget.setTabEnabled(self.tabWidget.count() - 1, False)  # Disable selection for the "+" tab
        self.tabWidget.tabBar().setTabButton(self.tabWidget.count() - 1, QTabBar.ButtonPosition.RightSide,
                                             self.plusButton)

        # Connect tab-change signal
        self.currentSheet = self.tabWidget.currentWidget()
        self.tabWidget.currentChanged.connect(self.updateCurrentSheet)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def get_table(self, index) -> TableView:
        tableview = cast(TableView, self.tabWidget.widget(index))
        return tableview

    def updateCurrentSheet(self):
        pass

    def _legacy_add_new_sheet(self, sheet_name: str | None = None):
        # Add a new sheet tab
        index = self.tabWidget.count() - 1
        new_sheet_name = sheet_name or PyDatabase.next_sheet_name(self.table_name)
        PyDatabase.register_sheet(self.table_name, new_sheet_name, PyDatabase())
        table_view = TableView(databases[self.table_name][new_sheet_name])
        self.tabWidget.insertTab(index, table_view, new_sheet_name)
        self.tabWidget.setCurrentIndex(index)
        return table_view

    def set_table_name(self, table_name: str):
        self.table_name = validate_project_component_name(table_name, "Project name")
        self.tabWidget.table_name = self.table_name

    def add_new_sheet(self, sheet_name: str | None = None):
        index = self.tabWidget.count() - 1
        new_sheet_name = validate_project_component_name(
            sheet_name or PyDatabase.next_sheet_name(self.table_name),
            "Sheet name",
        )
        if new_sheet_name in databases.get(self.table_name, {}):
            raise ValueError(f"Sheet already exists: {new_sheet_name}")
        PyDatabase.register_sheet(self.table_name, new_sheet_name, PyDatabase())
        table_view = TableView(databases[self.table_name][new_sheet_name])
        self.tabWidget.insertTab(index, table_view, new_sheet_name)
        self.tabWidget.setCurrentIndex(index)
        return table_view

    def rename_sheet(self, old_name: str, new_name: str):
        new_name = validate_project_component_name(new_name, "Sheet name")
        if old_name == new_name:
            return
        PyDatabase.rename_sheet(self.table_name, old_name, new_name)
        for index in range(self.tabWidget.count() - 1):
            if self.tabWidget.tabText(index) == old_name:
                self.tabWidget.setTabText(index, new_name)
                break
        if self.sheet_renamed_callback is not None:
            self.sheet_renamed_callback(self.table_name, old_name, new_name)

    def save_all_sheets_to_database(self):
        for index in range(self.tabWidget.count() - 1):
            self.get_table(index).flush_database_sync()
