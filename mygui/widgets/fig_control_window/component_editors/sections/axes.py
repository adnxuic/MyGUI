"""Axes limits and layout Inspector sections."""

from __future__ import annotations


from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages

from ..context import perform_editor_action
from ..inspector import EditorSection
from .property import PropertySection

class AxesLimitsSection(QWidget, EditorSection):
    """Edit ordered Axes limits and expose inversion as non-persistent proxies."""

    PROPERTY_KEYS = (
        "xlim",
        "ylim",
        "autoscalex_on",
        "autoscaley_on",
        "y_lower_reserve",
    )
    LIMIT_KEYS = ("xlim", "ylim", "autoscalex_on", "autoscaley_on")
    PROXY_KEYS = ("x_inverted", "y_inverted")

    def __init__(self, controller, *, context, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def apply(properties):
            key, value = next(iter(properties.items()))
            dimension = {
                "xlim": "x",
                "ylim": "y",
                "autoscalex_on": "x",
                "autoscaley_on": "y",
            }[key]
            kwargs = (
                {"limits": value}
                if key in {"xlim", "ylim"}
                else {"autoscale": value}
            )
            return perform_editor_action(
                context,
                f"Change Axes {key}",
                lambda: context.axes_layout.apply_linked_axis(
                    controller.component_id,
                    dimension,
                    **kwargs,
                ),
                merge_key=("property", controller.component_id, key),
                scan_all=True,
            )

        self.properties = PropertySection(
            controller,
            context=context,
            property_keys=self.LIMIT_KEYS,
            apply_properties=apply,
            parent=self,
        )
        self.reserve = PropertySection(
            controller,
            context=context,
            property_keys=("y_lower_reserve",),
            parent=self,
        )
        layout.addWidget(self.properties)
        layout.addWidget(self.reserve)
        proxy_row = QHBoxLayout()
        self.x_inverted = QCheckBox("Invert X", self)
        self.y_inverted = QCheckBox("Invert Y", self)
        proxy_row.addWidget(self.x_inverted)
        proxy_row.addWidget(self.y_inverted)
        layout.addLayout(proxy_row)
        self.x_inverted.toggled.connect(
            lambda checked: self._apply_inversion("x", checked)
        )
        self.y_inverted.toggled.connect(
            lambda checked: self._apply_inversion("y", checked)
        )
        self.sync_from_controller()

    def _apply_inversion(self, dimension: str, inverted: bool) -> bool:
        key = f"{dimension}lim"
        limits = tuple(self.controller.read_state().properties[key])
        if (limits[0] > limits[1]) == bool(inverted):
            return True
        result = perform_editor_action(self.context,
            f"Change {dimension.upper()} Axis Inversion",
            lambda: self.context.axes_layout.apply_linked_axis(
                self.controller.component_id,
                dimension,
                limits=tuple(reversed(limits)),
            ),
        )
        if not self.context.messages.present(
            result,
            success=f"{dimension.upper()} axis inversion updated.",
        ):
            self.sync_from_controller()
            return False
        self.properties.sync_from_controller()
        return True

    def editor(self, key: str):
        """Return a persistent editor or inversion proxy."""

        if key in self.PROXY_KEYS:
            return getattr(self, key)
        if key == "y_lower_reserve":
            return self.reserve.editor(key)
        return self.properties.editor(key)

    def editors(self):
        """Return all persistent and proxy controls."""

        return {
            **self.properties.editors(),
            **self.reserve.editors(),
            "x_inverted": self.x_inverted,
            "y_inverted": self.y_inverted,
        }

    def sync_from_controller(self) -> None:
        """Synchronize limits and derived inversion without recursion."""

        self.properties.sync_from_controller()
        self.reserve.sync_from_controller()
        state = self.controller.read_state().properties
        blockers = (
            QSignalBlocker(self.x_inverted),
            QSignalBlocker(self.y_inverted),
        )
        self.x_inverted.setChecked(state["xlim"][0] > state["xlim"][1])
        self.y_inverted.setChecked(state["ylim"][0] > state["ylim"][1])
        del blockers

    def dispose(self) -> None:
        """Disconnect proxy controls and dispose the nested property section."""

        try:
            self.x_inverted.toggled.disconnect()
            self.y_inverted.toggled.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.properties.dispose()
        self.reserve.dispose()
class AxesLayoutSection(QWidget, EditorSection):
    """Show immutable Axes relationships and open safe geometry editing."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.edit_button = QPushButton("Edit layout geometry…", self)
        self.edit_button.clicked.connect(self.edit_layout)
        layout.addWidget(self.edit_button)
        self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Refresh the persisted relationship summary."""

        subplot = self.controller.state.data.get("subplot", {})
        layer = "Right Y" if subplot.get("layer") == "right_y" else "Primary"
        shared = []
        if subplot.get("share_x_group"):
            shared.append("shared X")
        if subplot.get("share_y_group"):
            shared.append("shared Y")
        relationship = ", ".join(shared) if shared else "independent axes"
        self.summary_label.setText(
            f"Cell {int(subplot.get('row', 0)) + 1}, "
            f"{int(subplot.get('column', 0)) + 1} · {layer} · {relationship}.\n"
            "Cell occupancy, sharing, and twin relationships are fixed after creation."
        )

    def edit_layout(self) -> None:
        """Open the shared layout dialog for this Axes' stable layout id."""

        subplot = self.controller.state.data.get("subplot", {})
        layout_id = subplot.get("layout_id")
        if not layout_id:
            status_messages.show_error("This Axes has no editable layout record.")
            return
        try:
            from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
                PyLayoutDialog,
            )

            canvas = self.context.axes_layout.canvas
            figure_window = canvas.figure_window
            if figure_window is None:
                raise ValueError("The Figure window is unavailable.")
            dialog = PyLayoutDialog(
                "Edit Axes layout",
                figure_window,
                parent=self,
                layout_id=str(layout_id),
            )
            dialog.exec()
        except Exception as exc:
            status_messages.show_error(str(exc))
