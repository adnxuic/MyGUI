from Qt_core import *
from code.widgets import qss_func

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyLeftColumn(QFrame):
    def __init__(self, table, fig_control_window):
        super().__init__()
        self.table = table
        self.fig_control_window = fig_control_window

        self.setObjectName("left_column")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 44)

        # 图表按钮
        self.table_button = QPushButton(QIcon("pictures/icons/tables.svg"), "")
        self.table_button.setObjectName("table_button")
        self.table_button.setCheckable(True)
        self.table_button.setChecked(True)
        self.table_button.toggled.connect(self.the_button_was_toggled)
        self.layout.addWidget(self.table_button)

        # 添加弹性空间
        self.layout.addStretch(1)


        # 设置按钮
        self.setting_button = QPushButton(QIcon("pictures/icons/setting.svg"), "")
        self.setting_button.setObjectName("setting_button")
        self.setting_button.setCheckable(True)
        self.setting_button.setChecked(False)
        self.layout.addWidget(self.setting_button)



    def the_button_was_toggled(self, checked):
        # 获取当前窗口的宽度
        current_width = self.fig_control_window.width()
        current_height = self.fig_control_window.height()
        if checked:
            new_width = current_width // 2
            self.table.setVisible(True)
            self.fig_control_window.setFixedSize(new_width, current_height)
        else:
            new_width = current_width * 2
            self.table.setVisible(False)
            self.fig_control_window.setFixedSize(new_width, current_height)
