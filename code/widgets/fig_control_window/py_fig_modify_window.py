from Qt_core import *

from code.widgets.fig_control_window.py_all_mod_widget import (
    PyAxesModWidget, PyCurveModWindow, PyElementModWindow)

from code.widgets.qss_func import qss_loader

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyAllModWidget(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.setObjectName('all_mod_widget')

        self.setMouseTracking(True)

        self.layout = QVBoxLayout()

        self.btn_bars = []
        self.curve_btn_bar = QFrame()
        self.element_btn_bar = QFrame()
        self.btn_bars.append(self.curve_btn_bar)
        self.btn_bars.append(self.element_btn_bar)
        # 黑色边框
        self.curve_btn_bar.setStyleSheet("border: 1px solid black;")
        self.element_btn_bar.setStyleSheet("border: 1px solid black;")
        self.curve_btn_bar_layout = QHBoxLayout()
        self.element_btn_bar_layout = QHBoxLayout()

        self.axes_mod_widget = PyAxesModWidget(axe)
        self.curve_mod_window = PyCurveModWindow(axe)
        self.element_mod_window = PyElementModWindow(axe)

        self.stackwidget = QStackedWidget()

        self.stackwidget.addWidget(self.axes_mod_widget)
        self.stackwidget.addWidget(self.curve_mod_window)
        self.stackwidget.addWidget(self.element_mod_window)

        self.curve_btn_bar.setLayout(self.curve_btn_bar_layout)
        self.element_btn_bar.setLayout(self.element_btn_bar_layout)

        self.layout.addWidget(self.stackwidget)
        self.layout.addWidget(self.curve_btn_bar)
        self.layout.addWidget(self.element_btn_bar)

        self.setLayout(self.layout)

    def updateLayout(self, active_index):
        # 清空当前布局
        for i in reversed(range(self.layout.count())):
            self.layout.itemAt(i).widget().setParent(None)

        # 重新添加布局
        for i, btn_bar in enumerate(self.btn_bars):
            if i == active_index:
                self.layout.addWidget(self.stackwidget)

            self.layout.addWidget(btn_bar)

        if active_index == len(self.btn_bars):
            self.layout.addWidget(self.stackwidget)

    def add_curve_btn(self, btn_name, btn_func):
        btn = QPushButton(btn_name)
        btn.clicked.connect(btn_func)
        self.curve_btn_bar_layout.addWidget(btn)

    def add_element_btn(self, btn_name, btn_func):
        btn = QPushButton(btn_name)
        btn.clicked.connect(btn_func)
        self.element_btn_bar_layout.addWidget(btn)


class PyFigModWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_Widget')

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.axes_btn_bar = QFrame()
        self.axes_btn_bar_layout = QHBoxLayout()

        self.stacklayout = QStackedLayout()

        self.axes_btn_bar.setLayout(self.axes_btn_bar_layout)

        self.layout.addWidget(self.axes_btn_bar)
        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)

    def add_all_mod_widget(self, axe):
        all_mod_widget = PyAllModWidget(axe)
        self.stacklayout.addWidget(all_mod_widget)
        self.stacklayout.setCurrentIndex(self.stacklayout.count() - 1)

        btn_name = 'axe' + str(self.stacklayout.count())
        btn = QPushButton(btn_name)
        btn.clicked.connect(lambda: self.change_all_mod_widget(all_mod_widget))
        self.axes_btn_bar_layout.addWidget(btn)

    def change_all_mod_widget(self, all_mod_widget):
        self.stacklayout.setCurrentWidget(all_mod_widget)


class PyFigModWindow(QFrame):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_window')

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        # 堆叠窗口
        self.stacklayout = QStackedLayout()
        self.stacklayout.setSpacing(0)
        self.stacklayout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(self.stacklayout)

    def add_figmod_widget(self):
        figmod_widget = PyFigModWidget()
        self.stacklayout.addWidget(figmod_widget)
        self.stacklayout.setCurrentIndex(self.stacklayout.count() - 1)

        return figmod_widget
