"""Fixture: container classes owning private layout state."""
from PySide6.QtWidgets import QFrame, QStackedWidget


class _BaseStack(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._toolboxes = {}


class ChartStack(_BaseStack):
    def ensure_toolbox(self, key):
        toolbox = self._toolboxes.get(key)  # legal: subclass of owner
        if toolbox is None:
            toolbox = QStackedWidget(self)
            self._toolboxes[key] = toolbox
        return toolbox


class _FigureStack(QFrame):
    def __init__(self):
        super().__init__()
        self._figure_stack = QStackedWidget(self)


class OtherPanel(QFrame):
    def __init__(self, host):
        super().__init__()
        self._other = host
        # violation: accessing a container's private stack
        count = host._figure_stack.count()

    def bad(self, stack):
        return stack._toolboxes  # violation: non-owner access
