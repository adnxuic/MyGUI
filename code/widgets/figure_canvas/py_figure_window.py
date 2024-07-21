import sys

from Qt_core import *
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from code.widgets import qss_func
import matplotlib

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

matplotlib.use("QtAgg")


class PyFigureWindow(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.canvas = {}

        self.layout = QVBoxLayout()
        self.tabwindow = QTabWidget()

        # self.sc1 = PyFigureCanvas(self, width=10, height=5, dpi=100, style='dark_background')
        # axes = self.sc1.add_axes()
        # axes.plot([0, 1, 2, 3, 4], [10, 1, 20, 3, 40])
        # self.tabwindow.addTab(self.sc1, 'dark_background')
        #
        # self.sc2 = PyFigureCanvas(self, width=10, height=3, dpi=100, style='ggplot')
        # axes = self.sc2.add_axes()
        # axes.plot([0, 1, 2, 3, 4], [10, 1, 20, 3, 40])
        # self.tabwindow.addTab(self.sc2, 'ggplot')

        self.layout.addWidget(self.tabwindow)
        self.setLayout(self.layout)

    def add_figure(self, width=None, height=None, dpi=None, style=None, canva_name=None):
        canva = PyFigureCanvas(self, width=width, height=height, dpi=dpi, style=style)
        self.canvas['canva' + str(len(self.canvas) + 1)] = canva

        if canva_name is not None:
            self.tabwindow.addTab(canva, canva_name)
        elif canva_name == '':
            self.tabwindow.addTab(canva, 'canva' + str(len(self.canvas) + 1))
        else:
            self.tabwindow.addTab(canva, 'canva' + str(len(self.canvas) + 1))

        self.tabwindow.setCurrentWidget(canva)
