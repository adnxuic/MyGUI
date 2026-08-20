"""Fixture: UI artist mutation + second state candidates."""
from mygui.figuremodify.components.models import ComponentState


class LinePanel(QFrame):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self._text_binding = None

    def refresh(self, line):
        # violation: UI mutates a Matplotlib artist directly
        line.set_visible(True)
        line.set_linewidth(2.0)

    def refresh_ok(self, controller):
        # legal: routed through the controller
        controller.set_property("visible", True)

    def binding_ok(self):
        # legal: this is a Qt label binding, not an artist
        self._text_binding.set_text("hello")


class SecondStatePanel(QFrame):
    def __init__(self):
        super().__init__()
        self.current_component_id = None  # violation: second selection model
        self.states = {}

    def create(self):
        state = ComponentState(id="x")  # violation: UI-owned ComponentState
        self.states["x"] = state

    def mutate(self, controller):
        # violation: direct state mutation bypasses Controllers
        controller.state.properties["visible"] = True

    def read_ok(self, controller):
        # legal: read-only synchronization
        return controller.state.properties.get("visible")
