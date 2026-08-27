"""Controller-free Annotation creation input."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLineEdit,
)

from .common import FocusAwareDoubleSpinBox

_ANNOTATION_TEXT_COORDS = (
    ("Offset points", "offset_points"),
    ("Data", "data"),
    ("Axes fraction", "axes_fraction"),
)
_ANNOTATION_TARGET_COORDS = (
    ("Data", "data"),
    ("Axes fraction", "axes_fraction"),
)


class AnnotationInput(QFrame):
    """Controller-free values for one new Annotation."""

    def __init__(
        self,
        *,
        default_xy: tuple[float, float] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_input = QLineEdit(self)
        self.text_input.setPlaceholderText("Annotation text")
        self.text_input.setText("New Annotation")
        layout.addRow("Text:", self.text_input)

        self.xycoords_input = QComboBox(self)
        for label, value in _ANNOTATION_TARGET_COORDS:
            self.xycoords_input.addItem(label, value)
        layout.addRow("Target coordinates:", self.xycoords_input)

        self.x_input = FocusAwareDoubleSpinBox(self)
        self.x_input.setRange(-1e12, 1e12)
        self.x_input.setDecimals(6)
        self.x_input.setSingleStep(0.1)
        self.y_input = FocusAwareDoubleSpinBox(self)
        self.y_input.setRange(-1e12, 1e12)
        self.y_input.setDecimals(6)
        self.y_input.setSingleStep(0.1)
        if default_xy is not None:
            self.x_input.setValue(float(default_xy[0]))
            self.y_input.setValue(float(default_xy[1]))
        layout.addRow("Target x:", self.x_input)
        layout.addRow("Target y:", self.y_input)

        self.textcoords_input = QComboBox(self)
        for label, value in _ANNOTATION_TEXT_COORDS:
            self.textcoords_input.addItem(label, value)
        layout.addRow("Text placement:", self.textcoords_input)

        self.xytext_x_input = FocusAwareDoubleSpinBox(self)
        self.xytext_x_input.setRange(-1e9, 1e9)
        self.xytext_x_input.setDecimals(3)
        self.xytext_x_input.setSingleStep(1.0)
        self.xytext_x_input.setValue(20.0)
        self.xytext_y_input = FocusAwareDoubleSpinBox(self)
        self.xytext_y_input.setRange(-1e9, 1e9)
        self.xytext_y_input.setDecimals(3)
        self.xytext_y_input.setSingleStep(1.0)
        self.xytext_y_input.setValue(20.0)
        layout.addRow("Text x:", self.xytext_x_input)
        layout.addRow("Text y:", self.xytext_y_input)

        self.arrow_input = QCheckBox("Show arrow", self)
        self.arrow_input.setChecked(True)
        layout.addRow("Arrow:", self.arrow_input)

        self.xycoords_input.currentIndexChanged.connect(
            self._target_coords_changed
        )
        self.textcoords_input.currentIndexChanged.connect(
            self._text_coords_changed
        )

    def _target_coords_changed(self, _index: int) -> None:
        if self.xycoords_input.currentData() == "axes_fraction":
            self.x_input.setRange(0.0, 1.0)
            self.y_input.setRange(0.0, 1.0)
        else:
            self.x_input.setRange(-1e12, 1e12)
            self.y_input.setRange(-1e12, 1e12)

    def _text_coords_changed(self, _index: int) -> None:
        if self.textcoords_input.currentData() == "axes_fraction":
            self.xytext_x_input.setRange(0.0, 1.0)
            self.xytext_y_input.setRange(0.0, 1.0)
        else:
            self.xytext_x_input.setRange(-1e12, 1e12)
            self.xytext_y_input.setRange(-1e12, 1e12)

    def properties(self) -> dict:
        """Return the creation properties collected by this input."""

        return {
            "text": self.text_input.text(),
            "xy": [self.x_input.value(), self.y_input.value()],
            "xycoords": self.xycoords_input.currentData(),
            "xytext": [
                self.xytext_x_input.value(),
                self.xytext_y_input.value(),
            ],
            "textcoords": self.textcoords_input.currentData(),
            "arrow_enabled": self.arrow_input.isChecked(),
        }
