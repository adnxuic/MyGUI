from Qt_core import *

from code.widgets import qss_func
from code.widgets.title_bar.py_title_button import ChangeButton, SelectMenuButton, SelectButton
from code.widgets.title_bar.py_selector_bar import PySelectorBar
from code.widgets.title_bar.py_title_menu import MenuBar, SelectorMenuBar

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent

        # 样式设置
        self.setObjectName("title_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        # 设置布局
        self.layout = QVBoxLayout(self)
        self.sublayout = QHBoxLayout()
        self.sublayout.setSpacing(0)
        self.stacklayout_top = QStackedLayout()
        self.stacklayout_bottom = QStackedLayout()

        # 堆叠布局添加菜单栏
        self.stacklayout_top.addWidget(SelectorMenuBar())
        self.stacklayout_top.addWidget(MenuBar())

        # 添加布局元素
        # 选择更改按钮
        self.change_button = ChangeButton('change_button')
        self.change_button.toggled.connect(self.the_button_was_toggled)
        self.sublayout.addWidget(self.change_button)

        # 添加堆叠布局
        self.sublayout.addLayout(self.stacklayout_top)

        # 添加弹性空间
        sub_spacer = QSpacerItem(0, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.sublayout.addItem(sub_spacer)

        # 关闭按钮
        button_close = QPushButton(QIcon("pictures/icons/close.svg"), "")
        button_close.setObjectName("close_button")
        button_close.clicked.connect(self.parent.close)
        self.sublayout.addWidget(button_close)

        # 添加上方布局
        self.layout.addLayout(self.sublayout)

        # 添加弹性空间
        spacer = QSpacerItem(0, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout.addItem(spacer)

        # 下方选择栏
        selector_bar = PySelectorBar()
        self.layout.addWidget(selector_bar)

    def the_button_was_toggled(self, checked):
        if checked:
            self.stacklayout_top.setCurrentIndex(1)
        else:
            self.stacklayout_top.setCurrentIndex(0)

    # 移动窗口事件
    # def moveWindow(self, event):
    #     if self.parent.isMaximized():
    #         curso_x = self.parent.pos().x()
    #         curso_y = self.parent.pos().y() - QCursor.pos().y()
    #         self.parent.move(curso_x, curso_y)
    #
    #     if event.button() == Qt.LeftButton:
    #         self.parent.move(self.parent.pos() + event.globalPos() - self.parent.dragPos)
    #         self.parent.dragPos = event.globalPos()
    #         event.accept()
