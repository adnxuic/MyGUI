from Qt_core import *

from code.figuremodify.py_curve_modify import PyCurveModify


class PyCurveModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify):
        super().__init__()

        self.curve_modify = curve_modify

        self.layout = QVBoxLayout()

        self.setLayout(self.layout)
