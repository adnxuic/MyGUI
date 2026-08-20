"""Fixture: controller-bypass + alias-resolved artist mutation."""
from PySide6.QtWidgets import QFrame


class BypassPanel(QFrame):
    def replace_state(self, controller):
        controller.state = None  # violation: whole-state replacement

    def update_data(self, controller):
        controller.state.data.update({"subplot": {}})  # violation: dict mutation

    def setdefault_props(self, controller):
        controller.state.properties.setdefault("visible", True)  # violation

    def read_ok(self, controller):
        return controller.state.data.get("subplot")  # legal: read-only


class AliasPanel(QFrame):
    def hide_line(self, fig):
        artist = fig.axes[0].lines[0]
        artist.set_visible(False)  # violation: alias-resolved artist
