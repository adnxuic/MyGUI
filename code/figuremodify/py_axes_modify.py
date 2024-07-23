from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.style import use


class PyAxesModify:
    def __init__(self, fig, style=None):
        self.style = style
        self.fig = fig

        self.axes = []

    def redraw(self):
        self.fig.canvas.draw()

    def add_axes(self):
        with mpl.style.context(self.style):
            axes = self.fig.add_subplot(111)
        self.axes.append(axes)
        self.redraw()

        return axes

    def change_axes(self, axes, **kwargs):
        axes.set(**kwargs)
        return axes

