from Qt_core import *
from code.widgets import qss_func
from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWindow
from code.widgets.fig_control_window.py_tex_window import PyTexWindow
from code.widgets.fig_control_window.py_matlab_window import PyMatlabWindow

import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class PyFigControlWindow(QFrame):
    def __init__(self):
        super().__init__()


        self.setObjectName("fig_control_window")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setMouseTracking(True)

        self.figmod_window = PyFigModWindow()
        self.tex_window = PyTexWindow()
        self.matlab_window = PyMatlabWindow()

        self.layout = QStackedLayout()

        self.layout.addWidget(self.figmod_window)
        self.layout.addWidget(self.tex_window)
        self.layout.addWidget(self.matlab_window)

        self.layout.setCurrentIndex(0)

        self.setLayout(self.layout)


