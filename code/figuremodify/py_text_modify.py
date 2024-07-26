from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.style import use


class PyTextModify:
    def __init__(self, fig, style=None, text=None):
        self.style = style
        self.fig = fig

        self.text = text

    def redraw(self):
        self.fig.canvas.draw()
