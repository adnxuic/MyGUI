import sys
from typing import Optional
from Qt_core import *

from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget
from code.widgets.fig_control_window.all_mod_widgets.py_all_mod_widget import PyModBox
from code.widgets.fig_control_window.all_mod_widgets.py_curve_mod_widgets import PyCurveModWidget

from code.figuremodify.py_axes_modify import PyAxesModify
from code.figuremodify.py_curve_modify import PyCurveModify

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.style import use

import numpy as np

mpl.use("QtAgg")


class PyFigureCanvas(QWidget):
    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None):
        super().__init__()
        self.style = style
        with mpl.style.context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)

        self.fig_modify_widget: Optional[PyFigModWidget] = None

        self.current_axes: Optional[Axes] = None
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

    def setFigModifyWidget(self, fig_modify_widget):
        self.fig_modify_widget = fig_modify_widget

    def update_current_axes(self, axe):
        self.current_axes = axe

    def redraw(self):
        self.fig.canvas.draw()

    def add_axes(self, nrows=1, ncols=1):
        with mpl.style.context(self.style):
            for i in range(nrows * ncols):
                axe = self.fig.add_subplot(nrows, ncols, 1 + i)
                btn = self.fig_modify_widget.add_all_mod_widget(axe)
                btn.clicked.connect(lambda _, axe1=axe: self.update_current_axes(axe1))
                if i == 0:
                    self.update_current_axes(axe)

        self.redraw()

    def add_curve(self, func_test: str, style, color, label: str):

        x = np.linspace(0, 10, 1000)
        y = eval(func_test)
        with mpl.style.context(self.style):
            line, = self.current_axes.plot(x, y, ls=style, color=color, label=label)

        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)

        # 如果all_mod_widget中没有curve_box，则添加一个
        if all_mod_widget.curve_mod_window.boxs.get('curve_box') is None:
            all_mod_widget.add_chart_box('curve_box')

        # 添加曲线调整窗口
        curve_mod_widget = PyCurveModWidget(PyCurveModify(self.fig, self.style, line))

        curve_box: PyModBox = all_mod_widget.curve_mod_window.boxs['curve_box']
        curve_box.add_widget(curve_mod_widget, 'cuvre')

        self.redraw()

    def save(self, filename, dpi=None):
        if dpi is None:
            save_dpi = self.fig.dpi
        else:
            save_dpi = dpi
        with mpl.style.context(self.style):
            self.fig.savefig(filename, dpi=save_dpi)
