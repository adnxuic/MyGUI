from typing import Union

from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.style import use


class PyAxesModify:
    def __init__(self, fig: Figure, axe: Axes, style=None):
        self.style = style
        self.fig = fig

        self.axe = axe

        self.legend = None


    def redraw(self):
        self.fig.canvas.draw()

    def set_legend_position(self, position: Union[str, tuple]):
        self.legend = self.axe.legend(loc=position)
        self.redraw()

    def change_axes(self, axes, **kwargs):
        axes.set(**kwargs)
        return axes
