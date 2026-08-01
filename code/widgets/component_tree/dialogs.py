"""Controller-free dialogs owned by Components tree navigation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from Qt_core import *


@dataclass(frozen=True, slots=True)
class DeleteCandidate:
    """UI-only identity and presentation for one batch deletion candidate."""

    component_id: str
    instance_label: str
    parent_label: str
    cohort_key: tuple[str | None, str, str, str]

    def __iter__(self):
        """Retain convenient two-value unpacking for UI callers."""

        yield self.component_id
        yield self.instance_label


class ComponentBatchDeleteDialog(QDialog):
    """Select one or more visible component instances for batch deletion."""

    def __init__(
        self,
        entries: Iterable[DeleteCandidate | tuple[str, str]],
        *,
        role_label: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Delete {role_label.title()} Components")
        self.setModal(True)
        self._checkboxes: list[QCheckBox] = []
        self._id_labels: list[QLabel] = []
        self.candidates = tuple(
            entry
            if isinstance(entry, DeleteCandidate)
            else DeleteCandidate(
                str(entry[0]),
                str(entry[1]),
                "",
                (None, "", "", "remove"),
            )
            for entry in entries
        )

        layout = QVBoxLayout(self)
        parent_labels = {
            candidate.parent_label
            for candidate in self.candidates
            if candidate.parent_label
        }
        scope = (
            f" under {next(iter(parent_labels))}"
            if len(parent_labels) == 1
            else ""
        )
        description = QLabel(
            f"All {len(self.candidates)} matching {role_label} components"
            f"{scope} are listed, including items hidden by tree search. "
            "Select the instances to delete; the operation is all-or-none.",
            self,
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
        for candidate in self.candidates:
            row = QHBoxLayout()
            checkbox = QCheckBox(candidate.instance_label, list_frame)
            checkbox.setProperty("component_id", candidate.component_id)
            checkbox.setToolTip(
                f"{candidate.parent_label}\nStable ID: {candidate.component_id}"
            )
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._selection_changed)
            self._checkboxes.append(checkbox)
            stable_id = QLabel(candidate.component_id, list_frame)
            stable_id.setObjectName("delete_candidate_id")
            stable_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._id_labels.append(stable_id)
            row.addWidget(checkbox, 1)
            row.addWidget(stable_id)
            list_layout.addLayout(row)
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
