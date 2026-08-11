"""Provide the title bar's style pull-down menu."""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QVBoxLayout, QWidgetAction
from mygui.widgets import qss_func
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")
qss_file = qss_func.qss_loader(qss_path)

class StyleMenu(QMenu):
    """Provide the style menu Qt widget."""

    def __init__(self, connect_button, button_dict=None):
        super().__init__()

        self.connect_button = connect_button
        self.button_dict = button_dict

        #
        self.style_menu = QFrame()
        self.style_menu.setObjectName("style_menu")
        self.style_menu.setStyleSheet(qss_file)
        self.layout = QVBoxLayout()
        self.layout_list = []
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 每8个按钮为一行,并在每一行中间添加一条横线
        i = 0
        for index, (key, value) in enumerate(self.button_dict.items()):
            if index >= 8:  # Start from the 9th element
                if i%8 == 0:
                    self.layout_list.append(QHBoxLayout())
                    self.layout_list[-1].setContentsMargins(0, 10, 0, 0)
                i += 1
                self.layout_list[-1].addWidget(value)

        # 如果最后一行有不足8个按钮，则在后面补充弹性空间
        if i%8 != 0:
            for j in range(8 - i%8):
                self.layout_list[-1].addStretch()

        for layout in self.layout_list:
            self.layout.addLayout(layout)
            # 在每一行中间添加一条横线
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            self.layout.addWidget(line)


        self.style_menu.setLayout(self.layout)

        # 添加动作
        style_menu_action = QWidgetAction(self)
        style_menu_action.setDefaultWidget(self.style_menu)
        self.addAction(style_menu_action)

        # 连接菜单的隐藏信号
        self.aboutToHide.connect(self.menu_about_to_hide)


    def menu_about_to_hide(self):
        """Restore button state when the attached menu closes."""

        self.connect_button.setChecked(False)