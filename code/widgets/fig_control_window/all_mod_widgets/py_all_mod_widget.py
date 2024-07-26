from Qt_core import *
from code.widgets.qss_func import qss_loader
from code.widgets.fig_control_window.all_mod_widgets.py_curve_mod_widgets import PyCurveModWidget

import os


# 调整坐标系
class PyAxesModWindow(QFrame):
    """
    坐标系调整窗口
    一个坐标系对应一个
    """

    def __init__(self, axe):
        super().__init__()

        self.axe = axe
        # 设置边框
        self.setStyleSheet("border: 1px solid black;")

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)


# 调整曲线
class PyCurveModWindow(QFrame):
    """
    曲线调整窗口
    一个坐标系对应一个
    用来容纳不同类的曲线调整箱
    """

    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedWidget()

        self.layout.addWidget(self.stacklayout)
        self.setLayout(self.layout)

    def add_box(self, box_name: str, btn: QPushButton):
        widget = PyModBox()
        self.boxs[box_name] = widget
        self.stacklayout.addWidget(widget)

        btn.clicked.connect(lambda: self.change_widget(widget))
        self.change_widget(widget)

    def change_widget(self, widget):
        self.stacklayout.setCurrentWidget(widget)


# 调整元素
class PyElementModWindow(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedLayout()

        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)

    def add_box(self, box_name: str, btn: QPushButton):
        widget = PyModBox()
        self.boxs[box_name] = widget
        self.stacklayout.addWidget(widget)

        btn.clicked.connect(lambda: self.change_widget(widget))
        self.change_widget(widget)

    def change_widget(self, widget):
        self.stacklayout.setCurrentWidget(widget)


class PyModBox(QToolBox):
    """
    调整箱
    用来容纳同类的多条调整窗口
    """

    def __init__(self):
        super().__init__()

        self.item_num = 0

    def add_widget(self, widget, widget_name: str):
        self.addItem(widget, widget_name + str(self.item_num))
        self.item_num += 1
