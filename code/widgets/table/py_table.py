from Qt_core import *

from code.widgets import qss_func
from code.widgets.table.py_subtable import PySubTable

from code.database.py_database import PyDatabase

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

class PyTable(QFrame):
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

    def add_new_table(self, is_open=False):
        # 添加新标签页
        index = self.tabWidget.count() - 1
        new_table_name = PyDatabase.next_table_name()
        PyDatabase.register_table(new_table_name)

        pydatabase = PyDatabase()
        subtable = PySubTable(new_table_name, pydatabase)

        self.tabWidget.insertTab(index, subtable, new_table_name)
        self.tabWidget.setCurrentIndex(index)

        if is_open:
            return subtable



