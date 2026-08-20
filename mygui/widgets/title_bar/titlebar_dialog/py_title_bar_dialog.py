"""Provide shared title-bar dialogs for Figure and Axes creation."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mygui import status_messages
from mygui.resources import icon_path, load_qss_resource
from mygui.widgets.figure_canvas.py_figure_window import PyFigureWindow
from mygui.widgets.theme import COLORS
from mygui.widgets.title_bar.titlebar_dialog.axes_layout_input import (
    AxesLayoutInput,
    axes_layout_preset,
    normalized_layout_icon,
)


class PyStyleDialog(QDialog):
    """Collect the basic values used to create one Figure project."""

    def __init__(self, dialog_name=None, figure_window=None, parent=None):
        super().__init__(parent)
        self.style = dialog_name
        self.setObjectName("style_dialog")
        self.setStyleSheet(
            load_qss_resource(
                "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
            )
        )
        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("style.svg")))
        self.figure_window = figure_window

        self.layout = QVBoxLayout()
        self.width_line = QLineEdit("6.4")
        self.height_line = QLineEdit("4.8")
        self.dpi_line = QLineEdit("100")
        self.canva_name_line = QLineEdit(str(dialog_name or "Figure"))
        for label, control in (
            ("Width", self.width_line),
            ("Height", self.height_line),
            ("DPI", self.dpi_line),
            ("Figure name", self.canva_name_line),
        ):
            self.layout.addWidget(QLabel(label))
            self.layout.addWidget(control)

        self.ok_button = QPushButton("Create")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        self.layout.addLayout(buttons)
        self.setLayout(self.layout)

    def accept(self):
        """Validate the inputs and create the Figure."""

        try:
            self.figure_window.add_figure(
                width=float(self.width_line.text()),
                height=float(self.height_line.text()),
                dpi=int(self.dpi_line.text()),
                style=self.style,
                canva_name=self.canva_name_line.text(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Create Project", str(exc))
            return
        super().accept()


class PyLayoutDialog(QDialog):
    """Create or safely edit one persisted scientific Axes layout."""

    def __init__(
        self,
        dialog_name=None,
        figure_window=None,
        preset_key: str | None = None,
        parent=None,
        *,
        layout_id: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("layout_dialog")
        self.setStyleSheet(
            load_qss_resource(
                "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
            )
        )
        self.figure_window: PyFigureWindow = figure_window
        self.layout_id = str(layout_id) if layout_id is not None else None
        self.preset_key = None if self.layout_id else str(preset_key or "single")
        preset = None if self.layout_id else axes_layout_preset(self.preset_key)
        self.setWindowTitle(
            "Edit Axes layout"
            if self.layout_id
            else str(dialog_name or preset.label)
        )
        self.setWindowIcon(
            normalized_layout_icon(
                icon_path("layout.svg"),
                canvas_size=64,
                tint=COLORS["text_primary"],
            )
            if preset is None
            else normalized_layout_icon(preset.icon_path, canvas_size=64)
        )

        canvas = getattr(figure_window, "current_canva", None)
        definition = None
        occupied = None
        twins = None
        relationship_summary = None
        if self.layout_id is not None:
            if canvas is None:
                raise ValueError("No Figure is available for layout editing.")
            definition = canvas.axes_layout_service.layout_definition(self.layout_id)
            occupied = set()
            twins = set()
            shared_x = False
            shared_y = False
            controllers = canvas.axes_layout_service.axes_for_layout(self.layout_id)
            for controller in controllers:
                subplot = controller.state.data["subplot"]
                cell = (int(subplot["row"]), int(subplot["column"]))
                if subplot["layer"] == "primary":
                    occupied.add(cell)
                    shared_x = shared_x or bool(subplot.get("share_x_group"))
                    shared_y = shared_y or bool(subplot.get("share_y_group"))
                elif subplot["layer"] == "right_y":
                    twins.add(cell)
            relationships = []
            if shared_x:
                relationships.append("shared X")
            if shared_y:
                relationships.append("shared Y")
            if twins:
                relationships.append(f"{len(twins)} right-Y Axes")
            if not relationships:
                relationships.append("independent Axes")
            relationship_summary = (
                f'{int(definition["nrows"])} × {int(definition["ncols"])} · '
                f'{len(occupied)} primary Axes · {" · ".join(relationships)}'
            )

        self.layout = QVBoxLayout()
        self.input = AxesLayoutInput(
            color_library=figure_window.color_library,
            preset_key=self.preset_key,
            default_view=(
                canvas.axes_layout_service.creation_view_defaults()
                if canvas is not None
                else None
            ),
            edit_definition=definition,
            occupied_cells=occupied,
            twin_cells=twins,
            relationship_summary=relationship_summary,
            parent=self,
        )
        if canvas is not None:
            self.input.constrained_input.setChecked(
                canvas.axes_layout_service.constrained_layout_enabled()
            )
        self.layout.addWidget(self.input)

        self.ok_button = QPushButton("Apply" if self.layout_id else "Create")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.input.validity_changed.connect(self._sync_accept_enabled)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)
        self.setLayout(self.layout)
        self.resize(720, 620)
        self._sync_accept_enabled(*self.input.refresh_validation())

    def _sync_accept_enabled(self, valid: bool, _message: str) -> None:
        """Keep submission unavailable while inline validation fails."""

        self.ok_button.setEnabled(bool(valid))

    def accept(self):
        """Submit the controller-free request to the Canvas layout service."""

        canvas = self.figure_window.current_canva
        if canvas is None:
            status_messages.show_error("Create a Figure before adding a layout.")
            return
        try:
            spec = self.input.spec()
            if self.layout_id is None:
                component_ids = canvas.create_axes_layout(spec)
                message = f"Created layout with {len(component_ids)} Axes."
            else:
                component_ids = canvas.update_axes_layout(spec)
                message = f"Updated layout for {len(component_ids)} Axes."
        except Exception as exc:
            status_messages.show_error(str(exc))
            return
        if self.input.records_recent_color:
            self.figure_window.color_library.record_recent(
                self.input.selected_color
            )
        status_messages.show_success(message)
        super().accept()
