"""Fixture: legal accesses inside owning container classes."""
from PySide6.QtWidgets import QFrame


class _Stack(QFrame):
    def __init__(self):
        super().__init__()
        self._toolboxes = {}


class ChartStack(_Stack):
    def find(self, key):
        return self._toolboxes.get(key)
