"""Colorbar and reference-mark/guide creation inputs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
)
from mygui.database import (
    ColumnRef,
    ColumnType,
    TableRepository,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import (
    FocusAwareDoubleSpinBox,
    parse_number_sequence,
)

class ColorbarInput(QFrame):
    """Controller-free source and placement input for Colorbar creation."""

    def __init__(self, sources, *, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source_input = QComboBox(self)
        for component_id, label in sources:
            self.source_input.addItem(str(label), str(component_id))
        layout.addRow("Source:", self.source_input)

        self.location_input = QComboBox(self)
        self.location_input.addItems(("right", "left", "top", "bottom"))
        layout.addRow("Location:", self.location_input)
        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)

        self.fraction_input = FocusAwareDoubleSpinBox(self)
        self.fraction_input.setRange(0.001, 1.0)
        self.fraction_input.setDecimals(3)
        self.fraction_input.setSingleStep(0.01)
        self.fraction_input.setValue(0.15)
        layout.addRow("Fraction:", self.fraction_input)

        self.shrink_input = FocusAwareDoubleSpinBox(self)
        self.shrink_input.setRange(0.001, 1.0)
        self.shrink_input.setDecimals(3)
        self.shrink_input.setSingleStep(0.05)
        self.shrink_input.setValue(1.0)
        layout.addRow("Shrink:", self.shrink_input)

        self.aspect_input = FocusAwareDoubleSpinBox(self)
        self.aspect_input.setRange(0.001, 10000.0)
        self.aspect_input.setDecimals(3)
        self.aspect_input.setValue(20.0)
        layout.addRow("Aspect:", self.aspect_input)

        self.pad_input = FocusAwareDoubleSpinBox(self)
        self.pad_input.setRange(0.0, 1.0)
        self.pad_input.setDecimals(3)
        self.pad_input.setSingleStep(0.01)
        self.pad_input.setValue(0.05)
        layout.addRow("Pad:", self.pad_input)

    def has_source(self) -> bool:
        """Return whether creation has one eligible stable source id."""

        return self.source_input.count() > 0

    def source_component_id(self) -> str | None:
        """Return the selected stable source component id."""

        value = self.source_input.currentData(Qt.UserRole)
        return str(value) if value is not None else None

    def properties(self) -> dict[str, object]:
        """Return the complete user-selected Colorbar creation patch."""

        return {
            "location": self.location_input.currentText(),
            "label": self.label_input.text(),
            "fraction": float(self.fraction_input.value()),
            "shrink": float(self.shrink_input.value()),
            "aspect": float(self.aspect_input.value()),
            "pad": float(self.pad_input.value()),
        }


class ReferenceMarksInput(QFrame):
    """Controller-free typed input for Reflection Positions creation."""

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        defaults,
        parent=None,
        repository: TableRepository | None = None,
        project_id: str | None = None,
        max_baseline_plus_height: float | None = None,
        appearance_only: bool = False,
        automatic_baseline: bool = False,
    ):
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "ReferenceMarksInput requires the application ColorLibrary."
            )
        self.repository = repository
        self.project_id = project_id
        self.max_baseline_plus_height = max_baseline_plus_height
        self.automatic_baseline = bool(automatic_baseline)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)

        self.positions_input = QLineEdit(self)
        self.positions_input.setPlaceholderText(
            "Comma or space separated values, e.g. 15.1876, 15.2256"
        )
        if not appearance_only:
            layout.addRow("Positions:", self.positions_input)

        self.position_ref_input = QComboBox(self)
        self.position_ref_input.addItem("(None)", None)
        if repository is not None and project_id is not None:
            for ref in repository.iter_column_refs(
                project_id, {ColumnType.NUMBER}
            ):
                self.position_ref_input.addItem(repository.ref_label(ref), ref)
        if not appearance_only:
            layout.addRow("Table column:", self.position_ref_input)

        self.baseline_input = FocusAwareDoubleSpinBox(self)
        self.baseline_input.setRange(0.0, 1.0)
        self.baseline_input.setDecimals(4)
        self.baseline_input.setSingleStep(0.005)
        self.baseline_input.setValue(0.08)
        if self.automatic_baseline:
            self.baseline_input.setEnabled(False)
            layout.addRow("Baseline:", QLabel("Automatic", self))
            self.baseline_input.hide()
        else:
            layout.addRow("Baseline:", self.baseline_input)

        self.height_input = FocusAwareDoubleSpinBox(self)
        self.height_input.setRange(0.000000001, 1.0)
        self.height_input.setDecimals(9)
        self.height_input.setSingleStep(0.005)
        self.height_input.setValue(0.025)
        layout.addRow("Height:", self.height_input)

        self.color_input = ColorChoiceWidget(
            defaults.color,
            color_library=color_library,
            auto_record_recent=not appearance_only,
            parent=self,
        )
        layout.addRow("Color:", self.color_input)

        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1000.0)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setSingleStep(0.1)
        self.linewidth_input.setValue(float(defaults.linewidth))
        layout.addRow("Line width:", self.linewidth_input)

    def positions(self) -> list[float]:
        """Return the typed ordered numeric sequence."""

        return [
            float(value)
            for value in parse_number_sequence(self.positions_input.text())
        ]

    def properties(self) -> dict[str, object]:
        """Return the Controller-free creation property patch."""

        return {
            "label": self.label_input.text(),
            "baseline": float(self.baseline_input.value()),
            "height": float(self.height_input.value()),
            "color": self.color_input.color(),
            "linewidth": float(self.linewidth_input.value()),
        }

    def position_ref(self) -> ColumnRef | None:
        """Return the selected nullable Number-column reference."""

        value = self.position_ref_input.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    def set_position_ref(self, ref: ColumnRef | None) -> None:
        """Select the Number-column reference or None."""

        target = 0
        if ref is not None:
            for index in range(self.position_ref_input.count()):
                if self.position_ref_input.itemData(index, Qt.UserRole) == ref:
                    target = index
                    break
        self.position_ref_input.setCurrentIndex(target)

    def validate_geometry(self) -> None:
        """Reject XRD pre-creation geometry that leaves the reserved band."""

        if self.automatic_baseline or self.max_baseline_plus_height is None:
            return
        total = float(self.baseline_input.value()) + float(self.height_input.value())
        if total > float(self.max_baseline_plus_height) + 1e-12:
            raise ValueError(
                "Baseline plus height must not exceed the reserved Y-axis band."
            )


def _guide_number_input(value: float, parent) -> FocusAwareDoubleSpinBox:
    editor = FocusAwareDoubleSpinBox(parent)
    editor.setRange(-1.0e100, 1.0e100)
    editor.setDecimals(6)
    editor.setSingleStep(0.1)
    editor.setValue(float(value))
    return editor


def _guide_span_input(value: float, parent) -> FocusAwareDoubleSpinBox:
    editor = FocusAwareDoubleSpinBox(parent)
    editor.setRange(0.0, 1.0)
    editor.setDecimals(4)
    editor.setSingleStep(0.05)
    editor.setValue(float(value))
    return editor


class ReferenceLineInput(QFrame):
    """Controller-free typed input for constant Reference Line creation."""

    def __init__(self, *, color_library: ColorLibrary, defaults, parent=None):
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "ReferenceLineInput requires the application ColorLibrary."
            )
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)
        self.orientation_input = QComboBox(self)
        self.orientation_input.addItem("Vertical (x = value)", "vertical")
        self.orientation_input.addItem("Horizontal (y = value)", "horizontal")
        layout.addRow("Orientation:", self.orientation_input)
        self.value_input = _guide_number_input(0.0, self)
        layout.addRow("Value:", self.value_input)
        self.span_start_input = _guide_span_input(0.0, self)
        self.span_end_input = _guide_span_input(1.0, self)
        layout.addRow("Span start:", self.span_start_input)
        layout.addRow("Span end:", self.span_end_input)
        self.color_input = ColorChoiceWidget(
            defaults.color,
            color_library=color_library,
            parent=self,
        )
        layout.addRow("Color:", self.color_input)
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1000.0)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setSingleStep(0.1)
        self.linewidth_input.setValue(float(defaults.linewidth))
        layout.addRow("Line width:", self.linewidth_input)

    def properties(self) -> dict[str, object]:
        return {
            "label": self.label_input.text(),
            "orientation": str(self.orientation_input.currentData(Qt.UserRole)),
            "value": float(self.value_input.value()),
            "span_start": float(self.span_start_input.value()),
            "span_end": float(self.span_end_input.value()),
            "color": self.color_input.color(),
            "linewidth": float(self.linewidth_input.value()),
        }


class ReferenceBandInput(QFrame):
    """Controller-free typed input for constant Reference Band creation."""

    def __init__(self, *, color_library: ColorLibrary, defaults, parent=None):
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "ReferenceBandInput requires the application ColorLibrary."
            )
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)
        self.orientation_input = QComboBox(self)
        self.orientation_input.addItem("Vertical (x bounds)", "vertical")
        self.orientation_input.addItem("Horizontal (y bounds)", "horizontal")
        layout.addRow("Orientation:", self.orientation_input)
        self.lower_input = _guide_number_input(0.0, self)
        self.upper_input = _guide_number_input(1.0, self)
        layout.addRow("Lower:", self.lower_input)
        layout.addRow("Upper:", self.upper_input)
        self.span_start_input = _guide_span_input(0.0, self)
        self.span_end_input = _guide_span_input(1.0, self)
        layout.addRow("Span start:", self.span_start_input)
        layout.addRow("Span end:", self.span_end_input)
        self.facecolor_input = ColorChoiceWidget(
            defaults.color,
            color_library=color_library,
            parent=self,
        )
        self.edgecolor_input = ColorChoiceWidget(
            defaults.color,
            color_library=color_library,
            parent=self,
        )
        layout.addRow("Face color:", self.facecolor_input)
        layout.addRow("Edge color:", self.edgecolor_input)
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1000.0)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setSingleStep(0.1)
        self.linewidth_input.setValue(float(defaults.linewidth))
        layout.addRow("Line width:", self.linewidth_input)

    def properties(self) -> dict[str, object]:
        return {
            "label": self.label_input.text(),
            "orientation": str(self.orientation_input.currentData(Qt.UserRole)),
            "lower": float(self.lower_input.value()),
            "upper": float(self.upper_input.value()),
            "span_start": float(self.span_start_input.value()),
            "span_end": float(self.span_end_input.value()),
            "facecolor": self.facecolor_input.color(),
            "edgecolor": self.edgecolor_input.color(),
            "linewidth": float(self.linewidth_input.value()),
        }
