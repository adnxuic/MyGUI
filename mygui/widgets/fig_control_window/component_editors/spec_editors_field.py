"""Field mapping, colormap, grid-edge, and contour spec editors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mygui.figuremodify.matplotlib_adapter import (
    CONTOUR_LABEL_FORMAT_CHOICES,
    available_colormap_names,
)
from mygui.figuremodify.components.property_values import (
    normalize_color_map_spec,
    normalize_contour_label_spec,
    normalize_contour_levels_spec,
    normalize_grid_edge_spec,
    normalize_norm,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    format_number_sequence,
    parse_number_sequence,
)
from .inline_spec_editors import OptionalColorEditor
from .spec_editor_base import (
    _NORM_FIELDS,
    _StructuredValueEditor,
    _TaggedSpecDialog,
    _bind_spec_dialog,
    _chrome_error_label,
)

class NormSpecEditor(_StructuredValueEditor):
    """Edit the tagged, callable-free colormap normalization."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="color normalization",
            normalizer=normalize_norm,
            parent=parent,
        )

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog(
            "Color normalization",
            self.value(),
            _NORM_FIELDS,
            normalize_norm,
            self,
        )

    def _summary_text(self, value: Any) -> str:
        names = {"two_slope": "Two slope", "none": "No normalization"}
        kind = str(value["kind"])
        return names.get(kind, kind.replace("_", " ").title())



class _ColorMapSpecDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Colormap")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_color_map_spec(value)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.cmap_input = QComboBox(self)
        self.cmap_input.addItems(available_colormap_names())
        self.cmap_input.setCurrentText(str(spec["cmap"]))
        self.norm_input = NormSpecEditor(spec["norm"], parent=self)
        self.bad_input = ColorChoiceWidget(
            spec["bad"], color_library=color_library, parent=self
        )
        self.under_input = OptionalColorEditor(
            spec["under"], color_library=color_library, parent=self
        )
        self.over_input = OptionalColorEditor(
            spec["over"], color_library=color_library, parent=self
        )
        form.addRow("Colormap", self.cmap_input)
        form.addRow("Normalization", self.norm_input)
        form.addRow("Bad color", self.bad_input)
        form.addRow("Under color", self.under_input)
        form.addRow("Over color", self.over_input)
        layout.addLayout(form)
        self.error_label = _chrome_error_label(self)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_color_map_spec(
                {
                    "cmap": self.cmap_input.currentText(),
                    "norm": self.norm_input.value(),
                    "bad": self.bad_input.color(),
                    "under": self.under_input.value(),
                    "over": self.over_input.value(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The colormap editor has not been accepted.")
        return deepcopy(self._value)


class ColorMapSpecEditor(_StructuredValueEditor):
    """Edit the closed FIELD_2D colormap, norm, and out-of-range colors."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError(
                "ColorMapSpecEditor requires the application ColorLibrary."
            )
        self.color_library = color_library
        super().__init__(
            value,
            title="colormap",
            normalizer=normalize_color_map_spec,
            parent=parent,
        )

    def _dialog(self) -> _ColorMapSpecDialog:
        return _ColorMapSpecDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        return f"{value['cmap']} \u00b7 {str(value['norm']['kind']).title()}"


class _GridEdgeSpecDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Grid edge")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._value: dict[str, Any] | None = None
        spec = normalize_grid_edge_spec(value)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind_input = QComboBox(self)
        self.kind_input.addItem("None", "none")
        self.kind_input.addItem("Face color", "face")
        self.kind_input.addItem("Custom color", "color")
        kind = str(spec["kind"])
        self.kind_input.setCurrentIndex(max(0, self.kind_input.findData(kind)))
        initial_color = spec["value"] if kind == "color" else "#000000"
        self.color_input = ColorChoiceWidget(
            initial_color, color_library=color_library, parent=self
        )
        form.addRow("Mode", self.kind_input)
        form.addRow("Color", self.color_input)
        layout.addLayout(form)
        self.error_label = _chrome_error_label(self)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind_input.currentIndexChanged.connect(self._sync_color)
        self._sync_color()

    def _sync_color(self) -> None:
        self.color_input.setEnabled(self.kind_input.currentData() == "color")

    def _validate_and_accept(self) -> None:
        kind = str(self.kind_input.currentData())
        payload: dict[str, Any] = {"kind": kind}
        if kind == "color":
            payload["value"] = self.color_input.color()
        try:
            self._value = normalize_grid_edge_spec(payload)
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The grid edge editor has not been accepted.")
        return deepcopy(self._value)


class GridEdgeSpecEditor(_StructuredValueEditor):
    """Edit pcolormesh edgecolor as none, face, or an explicit color."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError(
                "GridEdgeSpecEditor requires the application ColorLibrary."
            )
        self.color_library = color_library
        super().__init__(
            value,
            title="grid edge",
            normalizer=normalize_grid_edge_spec,
            parent=parent,
        )

    def _dialog(self) -> _GridEdgeSpecDialog:
        return _GridEdgeSpecDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        if value["kind"] == "color":
            return str(value["value"])
        return str(value["kind"]).title()


class _ContourLevelsSpecDialog(QDialog):
    def __init__(self, value: Any, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Contour levels")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._value: dict[str, Any] | None = None
        spec = normalize_contour_levels_spec(value)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind_input = QComboBox(self)
        self.kind_input.addItem("Automatic count", "count")
        self.kind_input.addItem("Explicit values", "values")
        self.kind_input.setCurrentIndex(
            max(0, self.kind_input.findData(str(spec["kind"])))
        )
        self.count_input = FocusAwareSpinBox(self)
        self.count_input.setRange(2, 256)
        self.count_input.setValue(int(spec.get("count", 8)))
        self.values_input = QPlainTextEdit(self)
        if spec["kind"] == "values":
            self.values_input.setPlainText(format_number_sequence(spec["values"]))
        form.addRow("Mode", self.kind_input)
        form.addRow("Count", self.count_input)
        form.addRow("Values", self.values_input)
        layout.addLayout(form)
        self.error_label = _chrome_error_label(self)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind_input.currentIndexChanged.connect(self._sync_mode)
        self._sync_mode()

    def _sync_mode(self) -> None:
        count_mode = self.kind_input.currentData() == "count"
        self.count_input.setEnabled(count_mode)
        self.values_input.setEnabled(not count_mode)

    def _validate_and_accept(self) -> None:
        kind = str(self.kind_input.currentData())
        if kind == "count":
            payload: dict[str, Any] = {
                "kind": "count",
                "count": int(self.count_input.value()),
            }
        else:
            payload = {
                "kind": "values",
                "values": parse_number_sequence(self.values_input.toPlainText()),
            }
        try:
            self._value = normalize_contour_levels_spec(payload)
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The contour levels editor has not been accepted.")
        return deepcopy(self._value)


class ContourLevelsSpecEditor(_StructuredValueEditor):
    """Edit automatic count or strictly increasing explicit contour levels."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="contour levels",
            normalizer=normalize_contour_levels_spec,
            parent=parent,
        )

    def _dialog(self) -> _ContourLevelsSpecDialog:
        return _ContourLevelsSpecDialog(self.value(), self)

    def _summary_text(self, value: Any) -> str:
        if value["kind"] == "count":
            return f"{value['count']} automatic levels"
        return f"{len(value['values'])} explicit levels"


class _ContourLabelSpecDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Contour labels")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._value: dict[str, Any] | None = None
        spec = normalize_contour_label_spec(value)
        layout = QVBoxLayout(self)
        self.enabled_input = QCheckBox("Show contour labels", self)
        self.enabled_input.setChecked(bool(spec["enabled"]))
        layout.addWidget(self.enabled_input)
        self.details = QWidget(self)
        form = QFormLayout(self.details)
        form.setContentsMargins(0, 6, 0, 0)
        self.fmt_input = QComboBox(self.details)
        self.fmt_input.addItems(CONTOUR_LABEL_FORMAT_CHOICES)
        self.fmt_input.setCurrentText(str(spec["fmt"]))
        self.fontsize_input = FocusAwareDoubleSpinBox(self.details)
        self.fontsize_input.setRange(1.0, 100.0)
        self.fontsize_input.setDecimals(1)
        self.fontsize_input.setValue(float(spec["fontsize"]))
        self.color_input = OptionalColorEditor(
            spec["color"], color_library=color_library, parent=self.details
        )
        self.inline_input = QCheckBox(self.details)
        self.inline_input.setChecked(bool(spec["inline"]))
        self.spacing_input = FocusAwareDoubleSpinBox(self.details)
        self.spacing_input.setRange(0.0, 100.0)
        self.spacing_input.setDecimals(1)
        self.spacing_input.setValue(float(spec["inline_spacing"]))
        form.addRow("Format", self.fmt_input)
        form.addRow("Font size", self.fontsize_input)
        form.addRow("Color", self.color_input)
        form.addRow("Inline", self.inline_input)
        form.addRow("Inline spacing", self.spacing_input)
        layout.addWidget(self.details)
        self.error_label = _chrome_error_label(self)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.enabled_input.toggled.connect(self.details.setEnabled)
        self.details.setEnabled(self.enabled_input.isChecked())

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_contour_label_spec(
                {
                    "enabled": self.enabled_input.isChecked(),
                    "fmt": self.fmt_input.currentText(),
                    "fontsize": self.fontsize_input.value(),
                    "color": self.color_input.value(),
                    "inline": self.inline_input.isChecked(),
                    "inline_spacing": self.spacing_input.value(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The contour label editor has not been accepted.")
        return deepcopy(self._value)


class ContourLabelSpecEditor(_StructuredValueEditor):
    """Edit closed contour-label formatting and placement."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError(
                "ContourLabelSpecEditor requires the application ColorLibrary."
            )
        self.color_library = color_library
        super().__init__(
            value,
            title="contour labels",
            normalizer=normalize_contour_label_spec,
            parent=parent,
        )

    def _dialog(self) -> _ContourLabelSpecDialog:
        return _ContourLabelSpecDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        if not value["enabled"]:
            return "Off"
        return f"{value['fmt']} \u00b7 {value['fontsize']:g} pt"

