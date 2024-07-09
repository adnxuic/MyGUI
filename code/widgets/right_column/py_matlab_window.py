from Qt_core import *


class PyMatlabWindow(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("matlab_window")

        self.layout = QVBoxLayout(self)

