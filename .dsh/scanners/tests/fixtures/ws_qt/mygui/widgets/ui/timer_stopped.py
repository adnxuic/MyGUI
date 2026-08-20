from PySide6.QtCore import QTimer


class StoppedTimerOwner:
    """Parentless timer but with an explicit stop path; no finding expected."""

    def __init__(self):
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    def close(self):
        self._timer.stop()
        self._pending = []

    def flush(self):
        pass
