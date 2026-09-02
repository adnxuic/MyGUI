"""Text and Annotation structured spec editors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from mygui.figuremodify.components.property_values import (
    normalize_annotation_box,
    normalize_font,
    normalize_text_box,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import FocusAwareDoubleSpinBox, NullableDoubleEditor
from .spec_editor_base import (
    TEXT_BOX_STYLES,
    _StructuredValueEditor,
    _bind_spec_dialog,
    _chrome_error_label,
)
from .inline_spec_editors import LinePatternEditor

_DEFAULT_TEXT_BOX = {
    "enabled": True,
    "boxstyle": "round",
    "facecolor": "#FFFFFF",
    "edgecolor": "#000000",
    "linewidth": 1.0,
    "line_pattern": {"kind": "preset", "value": "-"},
    "alpha": None,
    "fill": True,
    "hatch": None,
    "pad": 0.3,
}

class _FontSpecDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Offset font")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_font(value)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.family_input = QLineEdit(", ".join(spec["family"]), self)
        self.family_input.setAccessibleName("Font families")
        self.size_input = FocusAwareDoubleSpinBox(self)
        self.size_input.setRange(0.01, 1e6)
        self.size_input.setDecimals(3)
        self.size_input.setValue(float(spec["size"]))
        self.weight_input = QLineEdit(str(spec["weight"]), self)
        self.style_input = QComboBox(self)
        self.style_input.addItems(("normal", "italic", "oblique"))
        self.style_input.setCurrentText(str(spec["style"]))
        self.stretch_input = QLineEdit(str(spec["stretch"]), self)
        self.variant_input = QComboBox(self)
        self.variant_input.addItems(("normal", "small-caps"))
        self.variant_input.setCurrentText(str(spec["variant"]))
        self.color_input = ColorChoiceWidget(
            spec["color"], color_library=color_library, parent=self
        )
        form.addRow("Families", self.family_input)
        form.addRow("Size (pt)", self.size_input)
        form.addRow("Weight", self.weight_input)
        form.addRow("Style", self.style_input)
        form.addRow("Stretch", self.stretch_input)
        form.addRow("Variant", self.variant_input)
        form.addRow("Color", self.color_input)
        layout.addLayout(form)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _number_or_text(text: str) -> Any:
        candidate = text.strip()
        try:
            number = float(candidate)
        except ValueError:
            return candidate
        return int(number) if number.is_integer() else number

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_font(
                {
                    "family": [item.strip() for item in self.family_input.text().split(",") if item.strip()],
                    "size": self.size_input.value(),
                    "weight": self._number_or_text(self.weight_input.text()),
                    "style": self.style_input.currentText(),
                    "stretch": self._number_or_text(self.stretch_input.text()),
                    "variant": self.variant_input.currentText(),
                    "color": self.color_input.color(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The font editor has not been accepted.")
        return deepcopy(self._value)


class FontSpecEditor(_StructuredValueEditor):
    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError("FontSpecEditor requires the application ColorLibrary.")
        self.color_library = color_library
        super().__init__(value, title="offset font", normalizer=normalize_font, parent=parent)

    def _dialog(self) -> _FontSpecDialog:
        return _FontSpecDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        family = value["family"][0]
        return f"{family} · {float(value['size']):g} pt · {value['weight']}"




class _TextBoxDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Text box")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_text_box(value)
        if not spec["enabled"]:
            spec = deepcopy(_DEFAULT_TEXT_BOX)
            spec["enabled"] = False

        layout = QVBoxLayout(self)
        self.enabled_input = QCheckBox("Draw a box behind this text", self)
        self.enabled_input.setChecked(bool(spec["enabled"]))
        layout.addWidget(self.enabled_input)

        self.details = QWidget(self)
        form = QFormLayout(self.details)
        form.setContentsMargins(0, 6, 0, 0)
        self.boxstyle_input = QComboBox(self.details)
        self.boxstyle_input.addItems(TEXT_BOX_STYLES)
        if self.boxstyle_input.findText(str(spec["boxstyle"])) < 0:
            self.boxstyle_input.addItem(str(spec["boxstyle"]))
        self.boxstyle_input.setCurrentText(str(spec["boxstyle"]))
        self.facecolor_input = ColorChoiceWidget(
            spec["facecolor"], color_library=color_library, parent=self.details
        )
        self.edgecolor_input = ColorChoiceWidget(
            spec["edgecolor"], color_library=color_library, parent=self.details
        )
        self.linewidth_input = FocusAwareDoubleSpinBox(self.details)
        self.linewidth_input.setRange(0.0, 1e6)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setValue(float(spec["linewidth"]))
        self.line_pattern_input = LinePatternEditor(
            spec["line_pattern"], parent=self.details
        )
        self.alpha_input = NullableDoubleEditor(
            spec["alpha"],
            fallback=1.0,
            bounds=(0.0, 1.0),
            decimals=3,
            step=0.05,
            parent=self.details,
        )
        self.fill_input = QCheckBox(self.details)
        self.fill_input.setChecked(bool(spec["fill"]))
        self.hatch_input = QLineEdit(
            "" if spec["hatch"] is None else str(spec["hatch"]), self.details
        )
        self.hatch_input.setPlaceholderText("Matplotlib hatch, for example ///")
        self.pad_input = FocusAwareDoubleSpinBox(self.details)
        self.pad_input.setRange(0.0, 1e6)
        self.pad_input.setDecimals(3)
        self.pad_input.setValue(float(spec["pad"]))
        form.addRow("Box style", self.boxstyle_input)
        form.addRow("Background", self.facecolor_input)
        form.addRow("Border", self.edgecolor_input)
        form.addRow("Border width", self.linewidth_input)
        form.addRow("Border pattern", self.line_pattern_input)
        form.addRow("Opacity", self.alpha_input)
        form.addRow("Filled", self.fill_input)
        form.addRow("Hatch", self.hatch_input)
        form.addRow("Pad", self.pad_input)
        layout.addWidget(self.details)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
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
        if not self.enabled_input.isChecked():
            self._value = {"enabled": False}
            self.accept()
            return
        hatch = self.hatch_input.text().strip()
        try:
            self._value = normalize_text_box(
                {
                    "enabled": True,
                    "boxstyle": self.boxstyle_input.currentText(),
                    "facecolor": self.facecolor_input.color(),
                    "edgecolor": self.edgecolor_input.color(),
                    "linewidth": self.linewidth_input.value(),
                    "line_pattern": self.line_pattern_input.value(),
                    "alpha": self.alpha_input.value(),
                    "fill": self.fill_input.isChecked(),
                    "hatch": hatch or None,
                    "pad": self.pad_input.value(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The text box editor has not been accepted.")
        return deepcopy(self._value)


class TextBoxEditor(_StructuredValueEditor):
    """Edit the optional box drawn behind one text component."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError("TextBoxEditor requires the application ColorLibrary.")
        self.color_library = color_library
        super().__init__(
            value,
            title="text box",
            normalizer=normalize_text_box,
            parent=parent,
        )

    def _dialog(self) -> _TextBoxDialog:
        return _TextBoxDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        if not value["enabled"]:
            return "No box"
        return f"{str(value['boxstyle']).title()} \u00b7 {value['facecolor']}"


class AnnotationBoxEditor(_StructuredValueEditor):
    """Edit the closed box composite behind one Annotation."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError("AnnotationBoxEditor requires the application ColorLibrary.")
        self.color_library = color_library
        super().__init__(
            value,
            title="annotation box",
            normalizer=normalize_annotation_box,
            parent=parent,
        )

    def _dialog(self) -> _AnnotationBoxDialog:
        return _AnnotationBoxDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        if not value["enabled"]:
            return "No box"
        return f"{str(value['style']).title()} · {value['facecolor']}"


class _AnnotationBoxDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Annotation box")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_annotation_box(value)

        layout = QVBoxLayout(self)
        self.enabled_input = QCheckBox("Draw a box behind this annotation", self)
        self.enabled_input.setChecked(bool(spec["enabled"]))
        layout.addWidget(self.enabled_input)

        self.details = QWidget(self)
        form = QFormLayout(self.details)
        form.setContentsMargins(0, 6, 0, 0)
        self.style_input = QComboBox(self.details)
        self.style_input.addItem("Square", "square")
        self.style_input.addItem("Rounded", "rounded")
        self.style_input.setCurrentIndex(
            max(0, self.style_input.findData(str(spec["style"])))
        )
        self.facecolor_input = ColorChoiceWidget(
            spec["facecolor"], color_library=color_library, parent=self.details
        )
        self.edgecolor_input = ColorChoiceWidget(
            spec["edgecolor"], color_library=color_library, parent=self.details
        )
        self.linewidth_input = FocusAwareDoubleSpinBox(self.details)
        self.linewidth_input.setRange(0.0, 1e6)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setValue(float(spec["linewidth"]))
        self.alpha_input = NullableDoubleEditor(
            spec["alpha"],
            fallback=1.0,
            bounds=(0.0, 1.0),
            decimals=3,
            step=0.05,
            parent=self.details,
        )
        self.padding_input = FocusAwareDoubleSpinBox(self.details)
        self.padding_input.setRange(0.0, 1e6)
        self.padding_input.setDecimals(3)
        self.padding_input.setValue(float(spec["padding"]))
        form.addRow("Box style", self.style_input)
        form.addRow("Background", self.facecolor_input)
        form.addRow("Border", self.edgecolor_input)
        form.addRow("Border width", self.linewidth_input)
        form.addRow("Opacity", self.alpha_input)
        form.addRow("Padding", self.padding_input)
        layout.addWidget(self.details)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
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
            self._value = normalize_annotation_box(
                {
                    "enabled": self.enabled_input.isChecked(),
                    "style": self.style_input.currentData(),
                    "facecolor": self.facecolor_input.color(),
                    "edgecolor": self.edgecolor_input.color(),
                    "linewidth": self.linewidth_input.value(),
                    "alpha": self.alpha_input.value(),
                    "padding": self.padding_input.value(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The annotation box editor has not been accepted.")
        return deepcopy(self._value)

