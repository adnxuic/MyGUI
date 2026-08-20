"""Fixture: UI code mutates a Matplotlib artist directly (ARCH-UI-ARTIST-MUTATION)."""

from PySide6.QtWidgets import QWidget


class InspectorBad(QWidget):
    """A widget whose refresh path mutates an artist without a Controller."""

    def __init__(self, axes, parent=None):
        super().__init__(parent)
        self.axes = axes
        self.line = self.axes.lines[0]

    def refresh(self):
        self.line.set_color("red")
