from Qt_core import *
from code.widgets import qss_func

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

