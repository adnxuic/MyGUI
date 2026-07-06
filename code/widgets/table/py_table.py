from Qt_core import *

from code.widgets import qss_func
from code.widgets.table.py_subtable import PySubTable

from code.database.py_database import PyDatabase, databases, validate_project_component_name

import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class TableTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            clicked_tab_index = self.tabBar().tabAt(event.position().toPoint())
            if clicked_tab_index != -1:
                self.show_context_menu(event.globalPosition().toPoint(), clicked_tab_index)
        super().mousePressEvent(event)

    def show_context_menu(self, position, tab_index):
        menu = QMenu()
        delete_action = menu.addAction("Delete")
        action = menu.exec(position)  # 显示菜单

        if action == delete_action:
            if self.count() > 1 and tab_index != self.count() - 1:  # 确保至少有一个标签页，且不是"+"标签
                response = QMessageBox.question(self, "Confirm Delete",
                                                "Are you sure you want to delete this Table?",
                                                QMessageBox.Yes | QMessageBox.No)
                if response == QMessageBox.Yes:
                    table_name = self.tabText(tab_index)
                    widget = self.widget(tab_index)
                    self.removeTab(tab_index)
                    PyDatabase.unregister_table(table_name)
                    widget.deleteLater()

class LegacyPyTable(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("table")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setMouseTracking(True)

        PyDatabase.clear()
        PyDatabase.register_table('Table1')

        self.tabWidget = TableTabWidget(self)

        database = PyDatabase()
        subtable = PySubTable('Table1', database)
        self.tabWidget.addTab(subtable, "Table1")


        # 创建"+"按钮，并添加为一个标签页，但设为不可选择
        self.plusButton = QPushButton("+")
        self.plusButton.clicked.connect(self.add_new_table)
        self.tabWidget.addTab(QWidget(), "")
        self.tabWidget.setTabEnabled(self.tabWidget.count() - 1, False)  # 设为不可选择
        self.tabWidget.tabBar().setTabButton(self.tabWidget.count() - 1, QTabBar.ButtonPosition.RightSide,
                                             self.plusButton)

        # 将tabWidget添加到布局中
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 10, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def add_new_table(self, is_open=False, table_name: str | None = None, first_sheet_name: str = "Sheet1"):
        # 添加新标签页
        index = self.tabWidget.count() - 1
        new_table_name = table_name or PyDatabase.next_table_name()
        PyDatabase.register_table(new_table_name)

        pydatabase = PyDatabase()
        subtable = PySubTable(new_table_name, pydatabase, first_sheet_name=first_sheet_name)

        self.tabWidget.insertTab(index, subtable, new_table_name)
        self.tabWidget.setCurrentIndex(index)

        if is_open:
            return subtable

    def clear_tables(self):
        for index in reversed(range(self.tabWidget.count() - 1)):
            widget = self.tabWidget.widget(index)
            self.tabWidget.removeTab(index)
            if widget is not None:
                widget.deleteLater()
        PyDatabase.clear()

    def load_database_snapshot(self, tables: dict):
        self.clear_tables()

        if not tables:
            self.add_new_table(table_name="Table1")
            return

        for table_name, sheets in tables.items():
            sheet_items = list(sheets.items()) or [("Sheet1", {})]
            first_sheet_name, first_columns = sheet_items[0]
            subtable = self.add_new_table(
                is_open=True,
                table_name=table_name,
                first_sheet_name=first_sheet_name,
            )

            first_table_view = subtable.get_table(0)
            first_table_view.load_columns(first_columns)
            first_table_view.model.save_data_to_database()

            for sheet_name, columns in sheet_items[1:]:
                table_view = subtable.add_new_sheet(sheet_name=sheet_name)
                table_view.load_columns(columns)
                table_view.model.save_data_to_database()


class PyTable(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("table")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)
        self.setMouseTracking(True)

        PyDatabase.clear()

        self._subtables: dict[str, PySubTable] = {}
        self._current_table_name: str | None = None
        self._figure_window = None

        self.stack = QStackedWidget(self)
        self.empty_label = QLabel("Create or open a project to edit table data.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setObjectName("empty_table_placeholder")
        self.stack.addWidget(self.empty_label)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 10, 0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

    @property
    def current_table_name(self) -> str | None:
        return self._current_table_name

    def set_figure_window(self, figure_window):
        self._figure_window = figure_window

    def _sheet_renamed(self, table_name: str, old_name: str, new_name: str):
        if self._figure_window is not None and hasattr(self._figure_window, "rename_sheet_references"):
            self._figure_window.rename_sheet_references(table_name, old_name, new_name)

    def has_table(self, table_name: str) -> bool:
        return table_name in self._subtables or table_name in databases

    def table_names(self) -> list[str]:
        return list(self._subtables.keys())

    def current_subtable(self) -> PySubTable | None:
        if self._current_table_name is None:
            return None
        return self._subtables.get(self._current_table_name)

    def create_project_table(self, table_name: str, first_sheet_name: str = "Sheet1",
                             switch: bool = True) -> PySubTable:
        table_name = validate_project_component_name(table_name, "Project name")
        first_sheet_name = validate_project_component_name(first_sheet_name, "Sheet name")
        if self.has_table(table_name):
            raise ValueError(f"Project already exists: {table_name}")

        subtable = PySubTable(
            table_name,
            PyDatabase(),
            first_sheet_name=first_sheet_name,
            sheet_renamed_callback=self._sheet_renamed,
        )
        self._subtables[table_name] = subtable
        self.stack.addWidget(subtable)
        if switch:
            self.switch_to_table(table_name)
        return subtable

    def add_new_table(self, is_open=False, table_name: str | None = None,
                      first_sheet_name: str = "Sheet1"):
        new_table_name = table_name or PyDatabase.next_table_name()
        return self.create_project_table(new_table_name, first_sheet_name=first_sheet_name)

    def switch_to_table(self, table_name: str | None):
        if table_name is None:
            self._current_table_name = None
            self.stack.setCurrentWidget(self.empty_label)
            return
        if table_name not in self._subtables:
            raise KeyError(f"Unknown project table: {table_name}")
        self._current_table_name = table_name
        self.stack.setCurrentWidget(self._subtables[table_name])

    def rename_project_table(self, old_name: str, new_name: str):
        new_name = validate_project_component_name(new_name, "Project name")
        if old_name == new_name:
            return
        if old_name not in self._subtables:
            raise KeyError(f"Unknown project table: {old_name}")
        if self.has_table(new_name):
            raise ValueError(f"Project already exists: {new_name}")

        PyDatabase.rename_table(old_name, new_name)
        subtable = self._subtables.pop(old_name)
        subtable.set_table_name(new_name)
        self._subtables[new_name] = subtable
        if self._current_table_name == old_name:
            self._current_table_name = new_name
            self.stack.setCurrentWidget(subtable)

    def remove_project_table(self, table_name: str):
        subtable = self._subtables.pop(table_name, None)
        if subtable is not None:
            self.stack.removeWidget(subtable)
            subtable.deleteLater()
        PyDatabase.unregister_table(table_name)
        if self._current_table_name == table_name:
            self.switch_to_table(next(iter(self._subtables), None))

    def clear_tables(self):
        for table_name in list(self._subtables):
            subtable = self._subtables.pop(table_name)
            self.stack.removeWidget(subtable)
            subtable.deleteLater()
        PyDatabase.clear()
        self.switch_to_table(None)

    def save_table_to_database(self, table_name: str):
        subtable = self._subtables.get(table_name)
        if subtable is None:
            raise KeyError(f"Unknown project table: {table_name}")
        subtable.save_all_sheets_to_database()

    def save_current_table_to_database(self):
        if self._current_table_name is None:
            return
        self.save_table_to_database(self._current_table_name)

    def save_all_tables_to_database(self):
        for table_name in list(self._subtables):
            self.save_table_to_database(table_name)

    def load_project_table_snapshot(self, table_snapshot: dict) -> PySubTable:
        table_name = validate_project_component_name(table_snapshot.get("name", ""), "Project name")
        sheets = table_snapshot.get("sheets") or {}
        if not isinstance(sheets, dict):
            raise ValueError("Invalid project table sheets")
        sheet_items = list(sheets.items()) or [("Sheet1", {})]
        first_sheet_name, first_columns = sheet_items[0]
        subtable = self.create_project_table(table_name, first_sheet_name=first_sheet_name)

        first_table_view = subtable.get_table(0)
        first_table_view.load_columns(first_columns)
        first_table_view.model.save_data_to_database()

        for sheet_name, columns in sheet_items[1:]:
            table_view = subtable.add_new_sheet(sheet_name=sheet_name)
            table_view.load_columns(columns)
            table_view.model.save_data_to_database()
        return subtable

    def load_database_snapshot(self, tables: dict):
        self.clear_tables()
        for table_name, sheets in tables.items():
            self.load_project_table_snapshot({
                "name": table_name,
                "sheets": sheets,
            })



