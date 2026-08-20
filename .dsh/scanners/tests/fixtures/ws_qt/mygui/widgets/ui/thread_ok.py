from PySide6.QtCore import QThread


class ShutdownThreadOwner:
    """Started thread with full shutdown path; no finding expected."""

    def __init__(self):
        self._thread = QThread()
        self._thread.finished.connect(self._thread.deleteLater)

    def start(self):
        self._thread.start()

    def shutdown(self):
        self._thread.quit()
        self._thread.wait()
