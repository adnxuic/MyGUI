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


class AmbiguousStoppedTimerOwner:
    """Cleanup vocabulary exists but is not tied to the constructed timer."""

    def __init__(self):
        self._secondary_timer = QTimer()

    def close(self):
        self._other_timer.stop()
