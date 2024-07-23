import sys

from Qt_core import *

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.style import use

from code.figuremodify.py_axes_modify import PyAxesModify

mpl.use("QtAgg")


class PyFigureCanvas(QWidget):
    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None):
        super().__init__()
        self.style = style
        with mpl.style.context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)

        self.axes_modify = PyAxesModify(self.fig, style)

        self.canva = FigureCanvasQTAgg(self.fig)
        self.canva.setFixedSize(width * dpi, height * dpi)

        # 添加滚动条
        self.scroArea = QScrollArea()
        self.scroArea.setWidget(self.canva)
        self.scroArea.setAlignment(Qt.AlignCenter)
        self.scroArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 设置显示策略
        self.scroArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 设置显示策略

        layout = QVBoxLayout()

        toolbox = NavigationToolbar(self.canva, self)

        layout.addWidget(toolbox)
        layout.addWidget(self.scroArea)

        self.setLayout(layout)

    def add_axes(self):
        with mpl.style.context(self.style):
            axes = self.fig.add_subplot(111)
        return axes

    def save(self, filename, dpi=None):
        if dpi is None:
            save_dpi = self.fig.dpi
        else:
            save_dpi = dpi
        with mpl.style.context(self.style):
            self.fig.savefig(filename, dpi=save_dpi)
