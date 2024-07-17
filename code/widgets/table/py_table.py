from Qt_core import *
from code.widgets import qss_func
from code.widgets.table.py_subtable import CustomTabWidget, PySubTable


import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class PyTable(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("table")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.tabWidget = CustomTabWidget(self)
        self.tabWidget.addTab(PySubTable(), "Table1")

        # 创建"+"按钮，并添加为一个标签页，但设为不可选择
        self.plusButton = QPushButton("+")
        self.plusButton.clicked.connect(self.add_new_table)
        self.tabWidget.addTab(QWidget(), "")
        self.tabWidget.setTabEnabled(self.tabWidget.count() - 1, False)  # 设为不可选择
        self.tabWidget.tabBar().setTabButton(self.tabWidget.count() - 1, QTabBar.ButtonPosition.RightSide,
                                             self.plusButton)

        # 将tabWidget添加到布局中
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabWidget)
        self.setLayout(layout)

    def add_new_table(self):
        # 添加新标签页
        index = self.tabWidget.count() - 1
        new_table_name = f"Table{index + 1}"
        self.tabWidget.insertTab(index, PySubTable(), new_table_name)
        self.tabWidget.setCurrentIndex(index)



