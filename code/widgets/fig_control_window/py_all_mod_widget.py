from Qt_core import *
from code.widgets.qss_func import qss_loader

import os

# 调整坐标系
class PyAxesModWidget(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)

# 调整曲线
class PyCurveModWindow(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedLayout()

        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)

    def add_curve_widget(self, curve_widget):
        self.stacklayout.addWidget(curve_widget)

    def change_curve_widget(self, index):
        self.stacklayout.setCurrentIndex(index)

class PyCurveModBox(QToolBox):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)

    def add_curve_widget(self, curve_widget):
        self.addItem(curve_widget, '曲线')

    def change_curve_widget(self, index):
        self.setCurrentIndex(index)

class PyCurveModWidget(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)

# 调整元素
class PyElementModWindow(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedLayout()

        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)


class PyElementModBox(QToolBox):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)

    def add_element_widget(self, element_widget):
        self.addItem(element_widget, '元素')

    def change_element_widget(self, index):
        self.setCurrentIndex(index)

class PyElementModWidget(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)