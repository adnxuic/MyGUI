from Qt_core import *

from code.widgets.fig_control_window.py_all_mod_widget import (
    PyAxesModWidget, PyCurveModWidget, PyElementModWidget)

from code.widgets.qss_func import qss_loader

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyAllModWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName('all_mod_widget')

        self.setMouseTracking(True)

        self.layout = QVBoxLayout()

        self.curve_btn_bar = QHBoxLayout()
        self.element_btn_bar = QHBoxLayout()

        self.axes_mod_widget = PyAxesModWidget()
        self.curve_mod_widget = PyCurveModWidget()
        self.element_mod_widget = PyElementModWidget()

        self.stacklayout = QStackedLayout()

        self.stacklayout.addWidget(self.axes_mod_widget)
        self.stacklayout.addWidget(self.curve_mod_widget)
        self.stacklayout.addWidget(self.element_mod_widget)

        self.layout.addLayout(self.curve_btn_bar)
        self.layout.addLayout(self.element_btn_bar)
        self.layout.addLayout(self.stacklayout)

        self.setLayout(self.layout)


    def change_layout(self, layout):
        self.layout = layout
        self.setLayout(self.layout)

    def add_curve_btn(self, btn_name, btn_func):
        btn = QPushButton(btn_name)
        btn.clicked.connect(btn_func)
        self.curve_btn_bar.addWidget(btn)

    def add_element_btn(self, btn_name, btn_func):
        btn = QPushButton(btn_name)
        btn.clicked.connect(btn_func)
        self.element_btn_bar.addWidget(btn)




class PyFigModWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_Widget')

        self.axe = None


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
        self.axe = axe
        all_mod_widget = PyAllModWidget()
        self.stacklayout.addWidget(all_mod_widget)
        self.stacklayout.setCurrentIndex(self.stacklayout.count() - 1)

        btn_name = 'axe' + str(self.stacklayout.count())
        btn = QPushButton(btn_name)
        btn.clicked.connect(self.change_all_mod_widget)
        self.axes_btn_bar_layout.addWidget(btn)


    def change_all_mod_widget(self, axesmod_widget):
        pass



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
