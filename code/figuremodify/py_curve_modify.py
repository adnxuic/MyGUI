from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.style import use


class PyCurveModify:
    def __init__(self, fig, style=None, line=None):
        self.style = style
        self.fig = fig

        self.line = line


    def redraw(self):
        self.fig.canvas.draw()



