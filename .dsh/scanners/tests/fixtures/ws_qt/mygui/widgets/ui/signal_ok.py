class SafeConnector:
    """Class-level disconnect contract and init-time binds; no finding expected."""

    def __init__(self, canvas):
        self._canvas = canvas

    def switch_canvas(self, canvas):
        self._disconnect_canvas()
        canvas.selectionChanged.connect(self._on_selected)

    def _disconnect_canvas(self):
        signal = getattr(self._canvas, "selectionChanged", None)
        if signal is not None:
            signal.disconnect(self._on_selected)
        self._canvas = None

    def _on_selected(self):
        pass


class InitLambdaBinder:
    """__init__-time lambda bindings are one-shot; no finding expected."""

    def __init__(self, button):
        button.clicked.connect(lambda: self.press())

    def press(self):
        pass
