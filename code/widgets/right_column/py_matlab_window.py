from Qt_core import *
from code.widgets.qss_func import qss_loader

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyMatlabWindow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("matlab_window")

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        self.move(0, 0)
        self.hide()

        self.layout = QVBoxLayout(self)

