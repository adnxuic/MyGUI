from Qt_core import *


class PyElementModWidget(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)