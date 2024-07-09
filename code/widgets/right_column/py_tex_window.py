from Qt_core import *


class PyTexWindow(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("tex_window")

        self.layout = QVBoxLayout(self)
