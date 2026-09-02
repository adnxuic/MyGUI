"""Controller-free creation input for Secondary Axis Elements."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget

from mygui.figuremodify.component_services import SecondaryAxisCreateSpec

from .inline_spec_editors import (
    SecondaryAxisPlacementEditor,
    UnitTransformEditor,
)
from .inspector_layout import configure_inspector_form


class SecondaryAxisInput(QWidget):
    """Collect orientation, unit mapping, placement, and initial label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        configure_inspector_form(layout)
        self.orientation_input = QComboBox(self)
        self.orientation_input.addItem("X (top/bottom)", "x")
        self.orientation_input.addItem("Y (left/right)", "y")
        self.transform_input = UnitTransformEditor(parent=self)
        self.placement_input = SecondaryAxisPlacementEditor(parent=self)
        self.placement_input.set_orientation("x")
        self.label_input = QLineEdit(self)
        self.label_input.setPlaceholderText("Optional unit label")
        layout.addRow("Orientation", self.orientation_input)
        layout.addRow("Unit transform", self.transform_input)
        layout.addRow("Placement", self.placement_input)
        layout.addRow("Label", self.label_input)
        self.orientation_input.currentIndexChanged.connect(self._orientation_changed)

    def _orientation_changed(self, *_args) -> None:
        self.placement_input.set_orientation(self.orientation())

    def orientation(self) -> str:
        return str(self.orientation_input.currentData())

    def spec(self) -> SecondaryAxisCreateSpec:
        return SecondaryAxisCreateSpec(
            self.orientation(),
            unit_transform=self.transform_input.value(),
            placement=self.placement_input.value(),
            properties={"label": self.label_input.text()},
        )
