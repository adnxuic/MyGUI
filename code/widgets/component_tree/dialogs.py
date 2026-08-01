"""Controller-free dialogs owned by Components tree navigation."""

from __future__ import annotations

from collections.abc import Iterable

from Qt_core import *


class ComponentBatchDeleteDialog(QDialog):
    """Select one or more visible component instances for batch deletion."""

    def __init__(
        self,
        entries: Iterable[tuple[str, str]],
        *,
        role_label: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Delete {role_label.title()} Components")
        self.setModal(True)
        self._checkboxes: list[QCheckBox] = []

        layout = QVBoxLayout(self)
        description = QLabel(
            f"Select the {role_label} components to delete.", self
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        selection_bar = QHBoxLayout()
        select_all_button = QPushButton("Select All", self)
        clear_all_button = QPushButton("Clear All", self)
        selection_bar.addWidget(select_all_button)
        selection_bar.addWidget(clear_all_button)
        selection_bar.addStretch()
        layout.addLayout(selection_bar)

        list_frame = QFrame(self)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        for component_id, label in entries:
            checkbox = QCheckBox(str(label), list_frame)
            checkbox.setProperty("component_id", str(component_id))
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._selection_changed)
            self._checkboxes.append(checkbox)
            list_layout.addWidget(checkbox)
        list_layout.addStretch()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(list_frame)
        layout.addWidget(scroll)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self.delete_button = self.buttons.addButton(
            "Delete", QDialogButtonBox.AcceptRole
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        select_all_button.clicked.connect(
            lambda: self._set_all_checked(True)
        )
        clear_all_button.clicked.connect(
            lambda: self._set_all_checked(False)
        )
        self._selection_changed()

    def _set_all_checked(self, checked: bool) -> None:
        for checkbox in self._checkboxes:
            checkbox.setChecked(checked)
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        count = len(self.selected_component_ids())
        self.delete_button.setEnabled(count > 0)
        self.delete_button.setText(f"Delete ({count})")

    def selected_component_ids(self) -> list[str]:
        """Return checked component IDs in their displayed order."""

        return [
            str(checkbox.property("component_id"))
            for checkbox in self._checkboxes
            if checkbox.isChecked()
        ]
