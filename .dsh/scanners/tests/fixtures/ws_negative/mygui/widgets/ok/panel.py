"""Negative fixture: legal UI paths must not be reported."""
from mygui.figuremodify.components.models import ComponentState


class SafePanel(QFrame):
    def __init__(self, canvas):
        self.canvas = canvas
        self._text_binding = None
        self.label = None

    def via_controller(self, controller):
        controller.apply_property("visible", True)

    def read_only(self, controller):
        return controller.state.properties.get("visible")

    def canvas_selection(self, canvas):
        canvas.current_component_id = "fig-1"

    def widget_binding(self):
        self._text_binding.set_text("ok")
        self.label.setVisible(True)

    def local_font_ok(self, title, font):
        title.setFont(font)

    def qsettings_annotation_ok(self, settings: QSettings | None = None):
        return settings

    def axes_command(self, ax):
        ax.set_xlabel("x")


class StateUsingPanel(QFrame):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.registry = canvas.component_registry

    def refresh(self, component_id):
        state = self.registry.get(component_id).state
        return state
