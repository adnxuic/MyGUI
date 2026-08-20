"""Fixture: parentless member QTimer with no stop path (QT-TIMER-OWNERSHIP)."""

from PySide6.QtCore import QTimer


class TimerBad:
    """Owner that never stops its timer."""

    def __init__(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self.tick)

    def tick(self):
        pass
