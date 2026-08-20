from PySide6.QtCore import QTimer


class ParentedTimerOwner:
    """Parented timer: Qt owns the lifecycle; no finding expected."""

    def __init__(self, parent=None):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)

    def tick(self):
        pass
