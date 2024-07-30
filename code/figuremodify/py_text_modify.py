from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure

from matplotlib.text import Text
from matplotlib.style import use


class PyTextModify:
    def __init__(self, fig, style=None, text: Text=None):
        self.style = style
        self.fig = fig

        self.text = text

    def redraw(self):
        self.fig.canvas.draw()

    def set_text_font(self, font):
        size = self.text.get_fontsize()
        self.text.set_fontproperties(font)
        self.text.set_fontsize(size)
        self.redraw()

    def set_text_fontsize(self, size):
        self.text.set_fontsize(size)
        self.redraw()

    def set_text_content(self, content):
        current_text = self.text.get_text()
        try:
            self.text.set_text(content)
            self.redraw()
        except ValueError:
            self.text.set_text(current_text)
            self.redraw()

    def set_xy_position(self, x, y):
        self.text.set_position((x, y))
        self.redraw()
