"""Error Bar data-source Inspector section."""

from __future__ import annotations

from mygui.database import ColumnRef

from ..context import perform_editor_action
from ..errorbar_inputs import ErrorBarDataInput
from ..inspector import EditorSection

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ErrorBarDataSection(QWidget, EditorSection):
    """Hold a full data draft and submit it atomically via Apply.

    Mode switches and column edits only update the draft; nothing reaches
    ``ErrorBarDataService`` until Apply commits all five data fields as one
    transaction (one Undo record). Reset restores the last committed state
    without history or messages.
    """

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context

        data = controller.read_state().data
        x_ref = ColumnRef.from_dict(data["x_ref"])
        y_ref = ColumnRef.from_dict(data["y_ref"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.data_input = ErrorBarDataInput(
            context.repository,
            x_ref.project_id,
            parent=self,
        )
        self.data_input.set_refs(x_ref, y_ref)
        self.data_input.set_error_specs(
            data.get("xerr"),
            data.get("yerr"),
        )
        self.data_input.set_preprocess(data["preprocess"])
        layout.addWidget(self.data_input)
        self.x_data_input = self.data_input.x_data_input
        self.y_data_input = self.data_input.y_data_input

        self.hint_label = QLabel("", self)
        self.hint_label.setObjectName("errorbar_data_hint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        button_layout = QHBoxLayout()
        self.apply_button = QPushButton("Apply", self)
        self.apply_button.setObjectName("errorbar_data_apply")
        self.reset_button = QPushButton("Reset", self)
        self.reset_button.setObjectName("errorbar_data_reset")
        button_layout.addStretch(1)
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.reset_button)
        layout.addLayout(button_layout)

        self.apply_button.clicked.connect(self.apply_clicked)
        self.reset_button.clicked.connect(self.reset_clicked)
        self.data_input.refs_connect(
            self._draft_changed,
            self._draft_changed,
        )
        self.data_input.expressions_connect(
            self._draft_changed,
            self._draft_changed,
        )
        self.data_input.x_error_input.connect_changed(
            self._draft_changed
        )
        self.data_input.y_error_input.connect_changed(
            self._draft_changed
        )
        self._refresh_apply_state()

    def _draft_changed(self, *_args) -> None:
        """Refresh the Apply gate after any draft control edit."""

        self._refresh_apply_state()

    def _refresh_apply_state(self) -> None:
        error = self.data_input.spec_error()
        self.apply_button.setEnabled(error is None)
        self.hint_label.setText(error or "")
        if error is not None:
            self.hint_label.setStyleSheet("color: #b3660a;")
        else:
            self.hint_label.setStyleSheet("")

    def apply_clicked(self) -> bool:
        """Commit the complete draft as one atomic data change."""

        error = self.data_input.spec_error()
        if error is not None:
            self.hint_label.setText(error)
            return False
        data = self.controller.read_state().data
        x_ref = (
            self.data_input.get_x_ref()
            or ColumnRef.from_dict(data["x_ref"])
        )
        y_ref = (
            self.data_input.get_y_ref()
            or ColumnRef.from_dict(data["y_ref"])
        )
        result = perform_editor_action(
            self.context,
            "Change Error Bar Data Source",
            lambda: self.context.errorbars.configure(
                self.controller,
                x_ref=x_ref,
                y_ref=y_ref,
                xerr=self.data_input.xerr_spec(),
                yerr=self.data_input.yerr_spec(),
                preprocess=self.data_input.preprocess_values(),
            ),
        )
        if not self.context.messages.present(
            result,
            success="Error Bar data source updated.",
        ):
            self.sync_from_controller()
            return False
        self._refresh_apply_state()
        return True

    def reset_clicked(self) -> None:
        """Restore the last committed state without history or messages."""

        self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        data = self.controller.read_state().data
        self.data_input.set_refs(
            ColumnRef.from_dict(data["x_ref"]),
            ColumnRef.from_dict(data["y_ref"]),
        )
        self.data_input.set_error_specs(
            data.get("xerr"),
            data.get("yerr"),
        )
        self.data_input.set_preprocess(data["preprocess"])
        self._refresh_apply_state()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self.data_input.dispose()
