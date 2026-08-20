"""Negative fixture: owners and subclasses access private state legally."""
from PySide6.QtWidgets import QFrame


class Host(QFrame):
    def __init__(self):
        super().__init__()
        self._figure_stack = None
        self._inspector_stack = None

    def swap(self):
        self._figure_stack.setCurrentIndex(1)
        return self._inspector_stack


class Panel(Host):
    def current(self):
        return self._figure_stack
