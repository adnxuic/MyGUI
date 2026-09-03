"""Chart mark, error, scatter-mapping, and Zoom connector spec editors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.widgets.english_buttons import english_ok_cancel
from mygui.widgets.ui_components import UiRole, apply_ui_style

from mygui.figuremodify.matplotlib_adapter import available_colormap_names
from mygui.figuremodify.components.errors import ComponentValidationError
from mygui.figuremodify.components.property_values import (
    normalize_connector,
    normalize_error_every,
    normalize_markevery,
    normalize_scatter_color_map,
    normalize_scatter_size_map,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import FocusAwareDoubleSpinBox, NumericTupleEditor
from .inline_spec_editors import LinePatternEditor, OptionalColorEditor
from .inspector_layout import add_labeled_form_row

from .spec_editor_base import (
    CONNECTOR_LABELS,
    _ERROR_EVERY_FIELDS,
    _MARKEVERY_FIELDS,
    _StructuredValueEditor,
    _TaggedSpecDialog,
    _bind_spec_dialog,
    _chrome_error_label,
)
from .spec_editors_field import NormSpecEditor

class MarkEveryEditor(_StructuredValueEditor):
    """Edit which data points receive a marker."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="marked points",
            normalizer=normalize_markevery,
            parent=parent,
        )

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog(
            "Marked points",
            self.value(),
            _MARKEVERY_FIELDS,
            normalize_markevery,
            self,
            flat=True,
        )

    def _summary_text(self, value: Any) -> str:
        kind = str(value["kind"])
        if kind == "all":
            return "Every point"
        if kind == "stride":
            start = value["start"]
            step = value["step"]
            return (
                f"Every {step} points"
                if start is None
                else f"Every {step} points from {start}"
            )
        if kind == "slice":
            return (
                f"Slice {value['start']}:{value['stop']}:{value['step']}".replace(
                    "None", ""
                )
            )
        if kind == "indices":
            return f"{len(value['values'])} selected points"
        return f"Every {float(value['distance']):g} of display width"


class ErrorEveryEditor(_StructuredValueEditor):
    """Edit the closed all/stride Error Bar sampling specification."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="error points",
            normalizer=normalize_error_every,
            parent=parent,
        )

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog(
            "Error points",
            self.value(),
            _ERROR_EVERY_FIELDS,
            normalize_error_every,
            self,
            flat=True,
        )

    def _summary_text(self, value: Any) -> str:
        if value["kind"] == "all":
            return "Every point"
        return f"Every {value['step']} points from {value['start']}"




class _ScatterColorMapDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Color mapping")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_scatter_color_map(value)

        layout = QVBoxLayout(self)
        self.enabled_input = QCheckBox("Map a numeric column to color", self)
        self.enabled_input.setChecked(bool(spec["enabled"]))
        layout.addWidget(self.enabled_input)

        self.details = QWidget(self)
        form = QFormLayout(self.details)
        form.setContentsMargins(0, 6, 0, 0)
        self.cmap_input = QComboBox(self.details)
        self.cmap_input.addItems(available_colormap_names())
        self.cmap_input.setCurrentText(str(spec["cmap"]))
        self.norm_input = NormSpecEditor(spec["norm"], parent=self.details)
        self.bad_input = ColorChoiceWidget(
            spec["bad"], color_library=color_library, parent=self.details
        )
        self.under_input = OptionalColorEditor(
            spec["under"], color_library=color_library, parent=self.details
        )
        self.over_input = OptionalColorEditor(
            spec["over"], color_library=color_library, parent=self.details
        )
        self.nonfinite_input = QComboBox(self.details)
        self.nonfinite_input.addItem("Drop non-finite rows", "drop")
        self.nonfinite_input.addItem("Use the bad color", "bad")
        self.nonfinite_input.setCurrentIndex(
            max(0, self.nonfinite_input.findData(spec["nonfinite"]))
        )
        add_labeled_form_row(form, "Colormap", self.cmap_input)
        add_labeled_form_row(form, "Normalization", self.norm_input)
        add_labeled_form_row(form, "Bad color", self.bad_input)
        add_labeled_form_row(form, "Under color", self.under_input)
        add_labeled_form_row(form, "Over color", self.over_input)
        add_labeled_form_row(form, "Non-finite values", self.nonfinite_input)
        layout.addWidget(self.details)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = english_ok_cancel(self)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.enabled_input.toggled.connect(self.details.setEnabled)
        self.details.setEnabled(self.enabled_input.isChecked())

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_scatter_color_map(
                {
                    "enabled": self.enabled_input.isChecked(),
                    "cmap": self.cmap_input.currentText(),
                    "norm": self.norm_input.value(),
                    "bad": self.bad_input.color(),
                    "under": self.under_input.value(),
                    "over": self.over_input.value(),
                    "nonfinite": self.nonfinite_input.currentData(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The color mapping editor has not been accepted.")
        return deepcopy(self._value)


class ScatterColorMapEditor(_StructuredValueEditor):
    """Edit the optional Scatter colormap specification."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError(
                "ScatterColorMapEditor requires the application ColorLibrary."
            )
        self.color_library = color_library
        super().__init__(
            value,
            title="color mapping",
            normalizer=normalize_scatter_color_map,
            parent=parent,
        )

    def _dialog(self) -> _ScatterColorMapDialog:
        return _ScatterColorMapDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        if not value["enabled"]:
            return "Uniform color"
        return f"{value['cmap']} \u00b7 {str(value['norm']['kind']).title()}"


class _ScatterSizeMapDialog(QDialog):
    def __init__(self, value: Any, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Size mapping")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: dict[str, Any] | None = None
        spec = normalize_scatter_size_map(value)

        layout = QVBoxLayout(self)
        self.enabled_input = QCheckBox("Map a numeric column to size", self)
        self.enabled_input.setChecked(bool(spec["enabled"]))
        layout.addWidget(self.enabled_input)

        self.details = QWidget(self)
        form = QFormLayout(self.details)
        form.setContentsMargins(0, 6, 0, 0)
        self.input_range_input = NumericTupleEditor(
            spec["input"],
            length=2,
            nullable=True,
            fallback=(0.0, 1.0),
            decimals=6,
            parent=self.details,
        )
        self.output_range_input = NumericTupleEditor(
            spec["output"],
            length=2,
            fallback=(12.0, 120.0),
            bounds=(0.0, 1e6),
            decimals=3,
            parent=self.details,
        )
        self.clamp_input = QCheckBox(self.details)
        self.clamp_input.setChecked(bool(spec["clamp"]))
        add_labeled_form_row(form, "Data range", self.input_range_input)
        add_labeled_form_row(form, "Point area (pt\u00b2)", self.output_range_input)
        add_labeled_form_row(form, "Clamp to range", self.clamp_input)
        layout.addWidget(self.details)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = english_ok_cancel(self)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.enabled_input.toggled.connect(self.details.setEnabled)
        self.details.setEnabled(self.enabled_input.isChecked())

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_scatter_size_map(
                {
                    "enabled": self.enabled_input.isChecked(),
                    "input": self.input_range_input.value(),
                    "output": self.output_range_input.value(),
                    "clamp": self.clamp_input.isChecked(),
                }
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The size mapping editor has not been accepted.")
        return deepcopy(self._value)


class ScatterSizeMapEditor(_StructuredValueEditor):
    """Edit the optional Scatter points-squared size mapping."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="size mapping",
            normalizer=normalize_scatter_size_map,
            parent=parent,
        )

    def _dialog(self) -> _ScatterSizeMapDialog:
        return _ScatterSizeMapDialog(self.value(), self)

    def _summary_text(self, value: Any) -> str:
        if not value["enabled"]:
            return "Uniform size"
        low, high = value["output"]
        return f"{float(low):g}\u2013{float(high):g} pt\u00b2"


def normalize_connectors(value: Any) -> tuple[dict[str, Any], ...]:
    """Normalize the four Zoom inset connector records."""

    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ComponentValidationError("Zoom inset requires four connector specs.")
    if len(value) != 4:
        raise ComponentValidationError("Zoom inset requires four connector specs.")
    return tuple(normalize_connector(item) for item in value)


class _ConnectorPage(QWidget):
    def __init__(self, spec: dict[str, Any], color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.visible_input = QCheckBox(self)
        self.visible_input.setChecked(bool(spec["visible"]))
        self.color_input = ColorChoiceWidget(
            spec["color"], color_library=color_library, parent=self
        )
        self.line_pattern_input = LinePatternEditor(spec["line_pattern"], parent=self)
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1e6)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setValue(float(spec["linewidth"]))
        self.alpha_input = FocusAwareDoubleSpinBox(self)
        self.alpha_input.setRange(0.0, 1.0)
        self.alpha_input.setDecimals(3)
        self.alpha_input.setSingleStep(0.05)
        self.alpha_input.setValue(float(spec["alpha"]))
        self.zorder_input = FocusAwareDoubleSpinBox(self)
        self.zorder_input.setRange(-1e6, 1e6)
        self.zorder_input.setDecimals(3)
        self.zorder_input.setValue(float(spec["zorder"]))
        add_labeled_form_row(form, "Visible", self.visible_input)
        add_labeled_form_row(form, "Color", self.color_input)
        add_labeled_form_row(form, "Pattern", self.line_pattern_input)
        add_labeled_form_row(form, "Width", self.linewidth_input)
        add_labeled_form_row(form, "Opacity", self.alpha_input)
        add_labeled_form_row(form, "Z order", self.zorder_input)
    def values(self) -> dict[str, Any]:
        """Return this connector's complete record."""

        return {
            "visible": self.visible_input.isChecked(),
            "color": self.color_input.color(),
            "line_pattern": self.line_pattern_input.value(),
            "linewidth": self.linewidth_input.value(),
            "alpha": self.alpha_input.value(),
            "zorder": self.zorder_input.value(),
        }


class _ZoomConnectorsDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
        _bind_spec_dialog(self)
        self.setWindowTitle("Zoom connectors")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: tuple[dict[str, Any], ...] | None = None
        specs = normalize_connectors(value)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        apply_ui_style(self.tabs, role=UiRole.TABS)
        self.pages: list[_ConnectorPage] = []
        for label, spec in zip(CONNECTOR_LABELS, specs, strict=True):
            page = _ConnectorPage(spec, color_library, self.tabs)
            self.pages.append(page)
            self.tabs.addTab(page, label)
        layout.addWidget(self.tabs)

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = english_ok_cancel(self)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        try:
            self._value = normalize_connectors(
                [page.values() for page in self.pages]
            )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> tuple[dict[str, Any], ...]:
        if self._value is None:
            raise RuntimeError("The connector editor has not been accepted.")
        return deepcopy(self._value)


class ZoomConnectorsEditor(_StructuredValueEditor):
    """Edit the four Zoom inset connector lines as one value."""

    def __init__(self, value: Any, *, color_library: ColorLibrary, parent=None):
        if color_library is None:
            raise ValueError(
                "ZoomConnectorsEditor requires the application ColorLibrary."
            )
        self.color_library = color_library
        super().__init__(
            value,
            title="zoom connectors",
            normalizer=normalize_connectors,
            parent=parent,
        )

    def _dialog(self) -> _ZoomConnectorsDialog:
        return _ZoomConnectorsDialog(self.value(), self.color_library, self)

    def _summary_text(self, value: Any) -> str:
        visible = sum(1 for item in value if item["visible"])
        return f"{visible} of {len(value)} connectors visible"

