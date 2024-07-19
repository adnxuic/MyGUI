from Qt_core import *
from code.widgets.qss_func import qss_loader

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class PyFigModWindow(QFrame):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_window')

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))