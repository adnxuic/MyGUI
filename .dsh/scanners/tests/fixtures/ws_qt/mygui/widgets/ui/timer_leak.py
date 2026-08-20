from PySide6.QtCore import QTimer


class LeakyTimerOwner:
    """Owns a parentless timer and never stops it."""

    def __init__(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self.tick)

    def tick(self):
        pass
