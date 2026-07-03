from Qt_core import *

import matplotlib as mpl
from matplotlib.figure import Figure

from matplotlib.text import Text
from matplotlib.style import use
from typing import Any


class PyTextModify:
    def __init__(self, fig, style=None, text: Text=None, project_record: dict[str, Any] | None = None):
        self.style = style
        self.fig = fig

        self.text = text
        self.project_record = project_record

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw()

    def set_text_font(self, font):
        size = self.text.get_fontsize()
        self.text.set_fontproperties(font)
        self.text.set_fontsize(size)
        self.update_project_record(fontfamily=font)
        self.redraw()

    def set_text_fontsize(self, size):
        self.text.set_fontsize(size)
        self.update_project_record(fontsize=float(self.text.get_fontsize()))
        self.redraw()

    def set_text_content(self, content):
        current_text = self.text.get_text()
        try:
            self.text.set_text(content)
            self.update_project_record(text=content)
            self.redraw()
        except ValueError:
            self.text.set_text(current_text)
            self.redraw()

    def set_xy_position(self, x, y):
        self.text.set_position((x, y))
        self.update_project_record(x=float(x), y=float(y))
        self.redraw()
