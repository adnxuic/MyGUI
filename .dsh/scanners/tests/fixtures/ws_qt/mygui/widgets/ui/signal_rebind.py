class RebindConnector:
    """Repeatable method appends lambda connections without disconnects."""

    def __init__(self, button):
        self._button = button

    def sync(self):
        self._button.clicked.connect(lambda: self._on_click())

    def _on_click(self):
        pass
