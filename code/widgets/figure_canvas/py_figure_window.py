import sys
from typing import Optional

from Qt_core import *
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget

from code.widgets import qss_func
import matplotlib

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

matplotlib.use("QtAgg")


class PyFigureWindow(QFrame):
    def __init__(self, fig_modify_window=None):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.fig_modify_window = fig_modify_window
        self.current_canva : Optional[PyFigureCanvas] = None
        self.canvas = {}

        self.current_fig_modify_widget = PyFigModWidget()

        self.layout = QVBoxLayout()
        self.tabwindow = QTabWidget()
        self.tabwindow.currentChanged.connect(self.change_current_canvas)

        self.layout.addWidget(self.tabwindow)
        self.setLayout(self.layout)

    def add_figure(self, width=None, height=None, dpi=None, style=None, canva_name=None):
        canva = PyFigureCanvas(self, width=width, height=height, dpi=dpi, style=style)
        self.canvas['canva' + str(len(self.canvas) + 1)] = canva

        figmod_widget = self.fig_modify_window.add_figmod_widget()

        canva.setFigModifyWidget(figmod_widget)

        if canva_name != '':
            self.tabwindow.addTab(canva, canva_name)
        else:
            self.tabwindow.addTab(canva, 'canva' + str(len(self.canvas) + 1))

        self.tabwindow.setCurrentWidget(canva)


    def change_current_canvas(self):
        self.current_canva = self.tabwindow.currentWidget()
        self.fig_modify_window.stacklayout.setCurrentIndex(self.tabwindow.currentIndex())
        self.current_fig_modify_widget = self.fig_modify_window.stacklayout.currentWidget()
