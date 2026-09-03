"""Axes limits and layout Inspector sections."""

from __future__ import annotations


from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.widgets.ui_components import UiVariant, style_button

from ..common import FocusAwareDoubleSpinBox
from ..context import perform_editor_action
from ..inspector import EditorSection
from ..inspector_layout import (
    add_labeled_form_row,
    apply_expanding_field,
    configure_inspector_form,
)
from .property import PropertySection

class AxesLimitsSection(QWidget, EditorSection):
    """Edit ordered Axes limits and expose inversion as non-persistent proxies."""

    PROPERTY_KEYS = (
        "xlim",
        "ylim",
        "autoscalex_on",
        "autoscaley_on",
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
        layout.addWidget(self.properties)
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
        return self.properties.editor(key)

    def editors(self):
        """Return all persistent and proxy controls."""

        return {
            **self.properties.editors(),
            "x_inverted": self.x_inverted,
            "y_inverted": self.y_inverted,
        }

    def sync_from_controller(self) -> None:
        """Synchronize limits and derived inversion without recursion."""

        self.properties.sync_from_controller()
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


class AxesLayoutSection(QWidget, EditorSection):
    """Show immutable Axes relationships and edit GridSpec vs manual geometry."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.geometry_label = QLabel(self)
        self.geometry_label.setWordWrap(True)
        layout.addWidget(self.geometry_label)

        self.twin_label = QLabel(
            "Linked with twin peer: geometry changes apply to both Axes.",
            self,
        )
        self.twin_label.setObjectName("axes_twin_hint")
        self.twin_label.setWordWrap(True)
        layout.addWidget(self.twin_label)

        # --- Grid Mode Controls ---
        self.grid_container = QWidget(self)
        grid_layout = QVBoxLayout(self.grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        self.edit_button = QPushButton("Edit Layout Geometry…", self.grid_container)
        style_button(self.edit_button, variant=UiVariant.OUTLINE)
        self.edit_button.clicked.connect(self.edit_layout)
        apply_expanding_field(self.edit_button)
        grid_layout.addWidget(self.edit_button)

        self.switch_manual_button = QPushButton(
            "Switch to Manual Position…", self.grid_container
        )
        style_button(self.switch_manual_button, variant=UiVariant.OUTLINE)
        self.switch_manual_button.clicked.connect(self.switch_to_manual)
        apply_expanding_field(self.switch_manual_button)
        grid_layout.addWidget(self.switch_manual_button)

        layout.addWidget(self.grid_container)

        # --- Manual Mode Controls ---
        self.manual_container = QWidget(self)
        manual_layout = QVBoxLayout(self.manual_container)
        manual_layout.setContentsMargins(0, 0, 0, 0)

        form_layout = QFormLayout()
        configure_inspector_form(form_layout)

        self.left_spin = FocusAwareDoubleSpinBox(self.manual_container)
        self.left_spin.setRange(0.0, 1.0)
        self.left_spin.setDecimals(6)
        self.left_spin.setSingleStep(0.01)
        apply_expanding_field(self.left_spin)
        add_labeled_form_row(form_layout, "Left", self.left_spin)

        self.bottom_spin = FocusAwareDoubleSpinBox(self.manual_container)
        self.bottom_spin.setRange(0.0, 1.0)
        self.bottom_spin.setDecimals(6)
        self.bottom_spin.setSingleStep(0.01)
        apply_expanding_field(self.bottom_spin)
        add_labeled_form_row(form_layout, "Bottom", self.bottom_spin)

        self.width_spin = FocusAwareDoubleSpinBox(self.manual_container)
        self.width_spin.setRange(0.000001, 1.0)
        self.width_spin.setDecimals(6)
        self.width_spin.setSingleStep(0.01)
        apply_expanding_field(self.width_spin)
        add_labeled_form_row(form_layout, "Width", self.width_spin)

        self.height_spin = FocusAwareDoubleSpinBox(self.manual_container)
        self.height_spin.setRange(0.000001, 1.0)
        self.height_spin.setDecimals(6)
        self.height_spin.setSingleStep(0.01)
        apply_expanding_field(self.height_spin)
        add_labeled_form_row(form_layout, "Height", self.height_spin)

        self.right_label = QLabel("0.000000", self.manual_container)
        self.right_label.setWordWrap(True)
        add_labeled_form_row(form_layout, "Right (computed)", self.right_label)

        self.top_label = QLabel("0.000000", self.manual_container)
        self.top_label.setWordWrap(True)
        add_labeled_form_row(form_layout, "Top (computed)", self.top_label)

        manual_layout.addLayout(form_layout)

        for spin in (self.left_spin, self.bottom_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._apply_manual_bounds)

        self.return_grid_button = QPushButton(
            "Return to Grid Layout", self.manual_container
        )
        style_button(self.return_grid_button, variant=UiVariant.OUTLINE)
        self.return_grid_button.clicked.connect(self.return_to_grid)
        apply_expanding_field(self.return_grid_button)
        manual_layout.addWidget(self.return_grid_button)

        self.reset_button = QPushButton(
            "Reset Position", self.manual_container
        )
        style_button(self.reset_button, variant=UiVariant.DESTRUCTIVE)
        self.reset_button.clicked.connect(self.reset_position)
        apply_expanding_field(self.reset_button)
        manual_layout.addWidget(self.reset_button)

        layout.addWidget(self.manual_container)

        self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Refresh the relationship summary and grid/manual state."""

        state = self.controller.read_state()
        subplot = state.data.get("subplot", {})
        layer = "Right Y" if subplot.get("layer") == "right_y" else "Primary"
        shared = []
        if subplot.get("share_x_group"):
            shared.append("shared X")
        if subplot.get("share_y_group"):
            shared.append("shared Y")
        relationship = ", ".join(shared) if shared else "independent axes"

        # Check twin status
        has_twin = False
        axes_geometry = getattr(self.context, "axes_geometry", None)
        if axes_geometry is not None:
            twin_group = axes_geometry.twin_group(self.controller.component_id)
            has_twin = len(twin_group) > 1
        self.twin_label.setVisible(has_twin)

        geom = state.data.get("geometry", {})
        mode = geom.get("mode", "grid")
        mode_label = "Grid controlled" if mode == "grid" else "Manual position"
        self.geometry_label.setText(f"Geometry: {mode_label}")

        self.summary_label.setText(
            f"Cell {int(subplot.get('row', 0)) + 1}, "
            f"{int(subplot.get('column', 0)) + 1} · {layer} · {relationship}.\n"
            "Cell occupancy, sharing, and twin relationships are fixed after creation."
        )

        if mode == "manual":
            self.grid_container.setVisible(False)
            self.manual_container.setVisible(True)
            bounds = geom.get("bounds", [0.0, 0.0, 1.0, 1.0])
            left, bottom, width, height = (float(v) for v in bounds)
            blockers = (
                QSignalBlocker(self.left_spin),
                QSignalBlocker(self.bottom_spin),
                QSignalBlocker(self.width_spin),
                QSignalBlocker(self.height_spin),
            )
            self.left_spin.setValue(left)
            self.bottom_spin.setValue(bottom)
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
            del blockers
            self.right_label.setText(f"{left + width:.6f}")
            self.top_label.setText(f"{bottom + height:.6f}")
        else:
            self.grid_container.setVisible(True)
            self.manual_container.setVisible(False)

    def _apply_manual_bounds(self) -> None:
        left = float(self.left_spin.value())
        bottom = float(self.bottom_spin.value())
        width = float(self.width_spin.value())
        height = float(self.height_spin.value())
        if left + width > 1.0:
            width = max(0.000001, 1.0 - left)
            with QSignalBlocker(self.width_spin):
                self.width_spin.setValue(width)
        if bottom + height > 1.0:
            height = max(0.000001, 1.0 - bottom)
            with QSignalBlocker(self.height_spin):
                self.height_spin.setValue(height)

        bounds = (left, bottom, width, height)
        axes_geometry = getattr(self.context, "axes_geometry", None)
        if axes_geometry is None:
            return
        result = perform_editor_action(
            self.context,
            "Change Axes Position",
            lambda: axes_geometry.set_manual_bounds(
                self.controller.component_id, bounds
            ),
            merge_key=("axes_geometry", self.controller.component_id),
            scan_all=True,
        )
        if not self.context.messages.present(
            result,
            success="Axes position updated.",
        ):
            self.sync_from_controller()
            return
        self.right_label.setText(f"{left + width:.6f}")
        self.top_label.setText(f"{bottom + height:.6f}")

    def switch_to_manual(self) -> None:
        """Switch this Axes from GridSpec to manual bounds."""

        axes_geometry = getattr(self.context, "axes_geometry", None)
        if axes_geometry is None:
            return
        result = perform_editor_action(
            self.context,
            "Switch Axes to Manual Position",
            lambda: axes_geometry.switch_to_manual(
                self.controller.component_id
            ),
            scan_all=True,
        )
        if not self.context.messages.present(
            result,
            success="Switched to manual position.",
        ):
            self.sync_from_controller()
            return
        self.sync_from_controller()

    def return_to_grid(self) -> None:
        """Return this Axes to GridSpec layout projection."""

        axes_geometry = getattr(self.context, "axes_geometry", None)
        if axes_geometry is None:
            return
        result = perform_editor_action(
            self.context,
            "Return Axes to Grid Layout",
            lambda: axes_geometry.return_to_grid(
                self.controller.component_id
            ),
            scan_all=True,
        )
        if not self.context.messages.present(
            result,
            success="Returned to grid layout.",
        ):
            self.sync_from_controller()
            return
        self.sync_from_controller()

    def reset_position(self) -> None:
        """Reset manual bounds to the latest GridSpec cell allocation rectangle."""

        axes_geometry = getattr(self.context, "axes_geometry", None)
        if axes_geometry is None:
            return
        result = perform_editor_action(
            self.context,
            "Reset Axes Manual Position",
            lambda: axes_geometry.reset_to_grid_bounds(
                self.controller.component_id
            ),
            scan_all=True,
        )
        if not self.context.messages.present(
            result,
            success="Reset position to grid cell.",
        ):
            self.sync_from_controller()
            return
        self.sync_from_controller()

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

    def editor(self, key: str):
        """Return a persistent or geometry editor control."""

        editors = self.editors()
        if key in editors:
            return editors[key]
        raise KeyError(key)

    def editors(self):
        """Return all geometry and layout controls."""

        return {
            "edit_button": self.edit_button,
            "switch_manual_button": self.switch_manual_button,
            "left": self.left_spin,
            "bottom": self.bottom_spin,
            "width": self.width_spin,
            "height": self.height_spin,
            "right": self.right_label,
            "top": self.top_label,
            "return_grid_button": self.return_grid_button,
            "reset_button": self.reset_button,
        }

    def dispose(self) -> None:
        """Disconnect all signals."""

        try:
            self.edit_button.clicked.disconnect()
            self.switch_manual_button.clicked.disconnect()
            self.return_grid_button.clicked.disconnect()
            self.reset_button.clicked.disconnect()
            for spin in (
                self.left_spin,
                self.bottom_spin,
                self.width_spin,
                self.height_spin,
            ):
                spin.valueChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
