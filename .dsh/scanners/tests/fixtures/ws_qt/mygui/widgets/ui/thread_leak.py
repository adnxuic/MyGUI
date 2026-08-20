from PySide6.QtCore import QThread


class LeakyThreadOwner:
    """Starts a member QThread and never shuts it down."""

    def __init__(self):
        self._thread = QThread()
        self._thread.start()

    def run(self):
        pass
