"""Structured dialog editors for the closed schema-v14 value contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.figuremodify.matplotlib_adapter import available_colormap_names

from mygui.figuremodify.components.errors import ComponentValidationError
from mygui.figuremodify.components.property_values import (
    normalize_connector,
    normalize_figure_layout,
    normalize_font,
    normalize_formatter,
    normalize_locator,
    normalize_markevery,
    normalize_norm,
    normalize_scale,
    normalize_scatter_color_map,
    normalize_scatter_size_map,
    normalize_text_box,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    NullableDoubleEditor,
    NumericTupleEditor,
    format_number_sequence,
    parse_number_sequence,
)
from .inline_spec_editors import LinePatternEditor, OptionalColorEditor


@dataclass(frozen=True)
class _Field:
    path: str
    label: str
    kind: str
    default: Any
    choices: tuple[tuple[str, Any], ...] = ()
    tooltip: str = ""


def _choice(*values: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(("Automatic" if value is None else str(value), value) for value in values)


_SCALE_FIELDS = {
    "linear": (),
    "log": (
        _Field("base", "Base", "number", 10.0),
        _Field("subs", "Sub-ticks", "optional_numbers", None),
        _Field("nonpositive", "Non-positive values", "enum", "clip", _choice("clip", "mask")),
    ),
    "symlog": (
        _Field("base", "Base", "number", 10.0),
        _Field("linthresh", "Linear threshold", "number", 2.0),
        _Field("linscale", "Linear scale", "number", 1.0),
        _Field("subs", "Sub-ticks", "optional_numbers", None),
    ),
    "logit": (
        _Field("nonpositive", "Non-positive values", "enum", "mask", _choice("clip", "mask")),
        _Field("one_half", "One-half label", "text", r"\frac{1}{2}"),
        _Field("use_overline", "Use overline", "bool", False),
    ),
    "asinh": (
        _Field("linear_width", "Linear width", "number", 1.0),
        _Field("base", "Base", "number", 10.0),
        _Field("subs", "Sub-ticks", "numbers", [2.0, 5.0]),
    ),
}

_LOCATOR_FIELDS = {
    "auto": (),
    "auto_minor": (
        _Field("n", "Intervals", "enum", None, _choice(None, 4, 5)),
    ),
    "max_n": (
        _Field("nbins", "Maximum bins", "auto_int", "auto"),
        _Field("steps", "Allowed steps", "optional_numbers", None),
        _Field("integer", "Integers only", "bool", False),
        _Field("symmetric", "Symmetric about zero", "bool", False),
        _Field("prune", "Prune edge tick", "enum", None, _choice(None, "lower", "upper", "both")),
        _Field("min_n_ticks", "Minimum ticks", "int", 2),
    ),
    "multiple": (
        _Field("base", "Interval", "number", 1.0),
        _Field("offset", "Offset", "number", 0.0),
    ),
    "linear": (
        _Field("numticks", "Number of ticks", "int", 11),
    ),
    "fixed": (
        _Field("locations", "Locations", "numbers", [0.0, 1.0]),
        _Field("nbins", "Maximum bins", "optional_int", None),
    ),
    "log": (
        _Field("base", "Base", "number", 10.0),
        _Field("subs", "Sub-ticks", "optional_numbers", None),
        _Field("numticks", "Maximum ticks", "optional_int", None),
    ),
    "symlog": (
        _Field("transform.base", "Base", "number", 10.0),
        _Field("transform.linthresh", "Linear threshold", "number", 2.0),
        _Field("transform.linscale", "Linear scale", "number", 1.0),
        _Field("subs", "Sub-ticks", "optional_numbers", None),
    ),
    "asinh": (
        _Field("linear_width", "Linear width", "number", 1.0),
        _Field("numticks", "Number of ticks", "int", 11),
        _Field("symthresh", "Symmetry threshold", "number", 0.2),
        _Field("base", "Base", "number", 10.0),
        _Field("subs", "Sub-ticks", "numbers", [2.0, 5.0]),
    ),
    "logit": (
        _Field("minor", "Minor ticks", "bool", False),
        _Field("nbins", "Number of bins", "auto_int", "auto"),
    ),
    "null": (),
}

_FORMATTER_FIELDS = {
    "scalar": (
        _Field("use_offset", "Use offset", "bool", True),
        _Field("use_math_text", "Use math text", "bool", False),
        _Field("use_locale", "Use locale", "bool", False),
        _Field("scientific", "Scientific notation", "bool", True),
        _Field("powerlimits", "Scientific limits", "ints", [-5, 6]),
    ),
    "engineering": (
        _Field("unit", "Unit", "text", ""),
        _Field("places", "Decimal places", "optional_int", None),
        _Field("sep", "Separator", "text", " "),
        _Field("usetex", "Use TeX", "bool", False),
        _Field("use_math_text", "Use math text", "bool", False),
    ),
    "percent": (
        _Field("xmax", "100% value", "number", 100.0),
        _Field("decimals", "Decimal places", "optional_int", None),
        _Field("symbol", "Symbol", "text", "%"),
        _Field("is_latex", "Symbol is TeX", "bool", False),
    ),
    "str_method": (
        _Field("format", "Format", "text", "{x:g}"),
    ),
    "fixed": (
        _Field("labels", "Labels (one per line)", "text_lines", [""]),
    ),
    "log": (),
    "log_exponent": (),
    "log_mathtext": (),
    "log_sci": (),
    "logit": (
        _Field("use_overline", "Use overline", "bool", False),
        _Field("one_half", "One-half label", "text", r"\frac{1}{2}"),
        _Field("minor", "Minor labels", "bool", False),
        _Field("minor_threshold", "Minor threshold", "int", 25),
    ),
    "null": (),
}

_LOG_FORMATTER_FIELDS = (
    _Field("base", "Base", "number", 10.0),
    _Field("label_only_base", "Label base powers only", "bool", False),
    _Field("minor_thresholds", "Minor thresholds", "optional_numbers", [1.0, 0.4]),
    _Field("linthresh", "Linear threshold", "optional_number", None),
)
for _formatter_kind in ("log", "log_exponent", "log_mathtext", "log_sci"):
    _FORMATTER_FIELDS[_formatter_kind] = _LOG_FORMATTER_FIELDS

_LAYOUT_FIELDS = {
    "none": (),
    "tight": (
        _Field("pad", "Pad", "optional_number", 1.08),
        _Field("w_pad", "Width pad", "optional_number", None),
        _Field("h_pad", "Height pad", "optional_number", None),
        _Field("rect", "Rectangle", "optional_numbers", None),
    ),
    "constrained": (
        _Field("w_pad", "Width pad", "optional_number", None),
        _Field("h_pad", "Height pad", "optional_number", None),
        _Field("wspace", "Width spacing", "optional_number", None),
        _Field("hspace", "Height spacing", "optional_number", None),
        _Field("rect", "Rectangle", "optional_numbers", None),
    ),
}
_LAYOUT_FIELDS["compressed"] = _LAYOUT_FIELDS["constrained"]

_MARKEVERY_FIELDS = {
    "all": (),
    "stride": (
        _Field("start", "First marked point", "optional_int", None),
        _Field("step", "Every N points", "int", 1),
    ),
    "slice": (
        _Field("start", "Start index", "optional_int", None),
        _Field("stop", "Stop index", "optional_int", None),
        _Field("step", "Step", "optional_int", None),
    ),
    "indices": (
        _Field("values", "Point indices", "ints", [0]),
    ),
    "spacing": (
        _Field("start", "Start offset", "number", 0.0),
        _Field("distance", "Display distance", "number", 0.1),
    ),
}

_NORM_FIELDS = {
    "linear": (
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
    ),
    "log": (
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
    ),
    "symlog": (
        _Field("linthresh", "Linear threshold", "number", 1.0),
        _Field("linscale", "Linear scale", "number", 1.0),
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
        _Field("base", "Base", "number", 10.0),
    ),
    "power": (
        _Field("gamma", "Gamma", "number", 1.0),
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
    ),
    "two_slope": (
        _Field("vcenter", "Center", "number", 0.0),
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
    ),
    "centered": (
        _Field("vcenter", "Center", "number", 0.0),
        _Field("halfrange", "Half range", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
    ),
    "boundary": (
        _Field("boundaries", "Boundaries", "numbers", [0.0, 1.0]),
        _Field("ncolors", "Color count", "int", 256),
        _Field("clip", "Clip out-of-range", "bool", False),
        _Field(
            "extend",
            "Extend",
            "enum",
            "neither",
            _choice("neither", "both", "min", "max"),
        ),
    ),
    "asinh": (
        _Field("linear_width", "Linear width", "number", 1.0),
        _Field("vmin", "Minimum", "optional_number", None),
        _Field("vmax", "Maximum", "optional_number", None),
        _Field("clip", "Clip out-of-range", "bool", False),
    ),
    "none": (),
}

TEXT_BOX_STYLES = (
    "round",
    "round4",
    "circle",
    "square",
    "sawtooth",
    "roundtooth",
    "larrow",
    "rarrow",
    "darrow",
)

CONNECTOR_LABELS = (
    "Lower left",
    "Upper left",
    "Lower right",
    "Upper right",
)


def _get_path(mapping: dict[str, Any], path: str, default: Any) -> Any:
    value: Any = mapping
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return deepcopy(default)
        value = value[part]
    return deepcopy(value)


def _set_path(mapping: dict[str, Any], path: str, value: Any) -> None:
    target = mapping
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


class _OptionalIntEditor(QWidget):
    def __init__(self, value: int | None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled_input = QCheckBox("Set", self)
        self.value_input = FocusAwareSpinBox(self)
        self.value_input.setRange(-2_147_483_647, 2_147_483_647)
        layout.addWidget(self.enabled_input)
        layout.addWidget(self.value_input, 1)
        self.enabled_input.toggled.connect(self.value_input.setEnabled)
        self.set_value(value)

    def value(self) -> int | None:
        return int(self.value_input.value()) if self.enabled_input.isChecked() else None

    def set_value(self, value: int | None) -> None:
        blocker = QSignalBlocker(self.enabled_input)
        self.enabled_input.setChecked(value is not None)
        del blocker
        if value is not None:
            self.value_input.setValue(int(value))
        self.value_input.setEnabled(value is not None)


class _ParameterForm(QWidget):
    def __init__(self, fields: tuple[_Field, ...], values: dict[str, Any], parent=None):
        super().__init__(parent)
        self._fields = fields
        self._inputs: dict[str, QWidget] = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        if not fields:
            note = QLabel("This type has no additional parameters.", self)
            note.setWordWrap(True)
            layout.addRow(note)
        for field in fields:
            value = _get_path(values, field.path, field.default)
            editor = self._create_input(field, value)
            editor.setAccessibleName(field.label)
            if field.tooltip:
                editor.setToolTip(field.tooltip)
                editor.setAccessibleDescription(field.tooltip)
            self._inputs[field.path] = editor
            layout.addRow(field.label, editor)

    def _create_input(self, field: _Field, value: Any) -> QWidget:
        if field.kind == "bool":
            editor = QCheckBox(self)
            editor.setChecked(bool(value))
            return editor
        if field.kind == "enum":
            editor = QComboBox(self)
            for label, item in field.choices:
                editor.addItem(label, item)
            index = editor.findData(value)
            editor.setCurrentIndex(max(0, index))
            return editor
        if field.kind == "number":
            editor = FocusAwareDoubleSpinBox(self)
            editor.setRange(-1e300, 1e300)
            editor.setDecimals(8)
            editor.setSingleStep(0.1)
            editor.setValue(float(value))
            return editor
        if field.kind == "int":
            editor = FocusAwareSpinBox(self)
            editor.setRange(-2_147_483_647, 2_147_483_647)
            editor.setValue(int(value))
            return editor
        if field.kind == "optional_number":
            return NullableDoubleEditor(
                value,
                fallback=1.0,
                bounds=(-1e300, 1e300),
                decimals=8,
                step=0.1,
                parent=self,
            )
        if field.kind == "optional_int":
            return _OptionalIntEditor(value, self)
        if field.kind in {"numbers", "optional_numbers", "ints"}:
            editor = QLineEdit(format_number_sequence(value), self)
            editor.setPlaceholderText("Comma-separated values")
            return editor
        if field.kind == "text_lines":
            editor = QPlainTextEdit(self)
            editor.setPlainText("\n".join(str(item) for item in value))
            editor.setMaximumHeight(88)
            return editor
        editor = QLineEdit("" if value is None else str(value), self)
        if field.kind == "auto_int":
            editor.setPlaceholderText("auto or a positive integer")
        return editor

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in self._fields:
            editor = self._inputs[field.path]
            if field.kind == "bool":
                value = editor.isChecked()
            elif field.kind == "enum":
                value = editor.currentData()
            elif field.kind == "number":
                value = float(editor.value())
            elif field.kind == "int":
                value = int(editor.value())
            elif field.kind == "optional_number":
                value = editor.value()
            elif field.kind == "optional_int":
                value = editor.value()
            elif field.kind in {"numbers", "optional_numbers", "ints"}:
                text = editor.text()
                value = parse_number_sequence(
                    text,
                    integer=field.kind == "ints",
                )
                if field.kind == "optional_numbers" and not text.strip():
                    value = None
            elif field.kind == "text_lines":
                value = editor.toPlainText().splitlines()
            elif field.kind == "auto_int":
                text = editor.text().strip()
                value = "auto" if text.casefold() == "auto" else int(text)
            else:
                value = editor.text()
            _set_path(result, field.path, value)
        return result


class _TaggedSpecDialog(QDialog):
    def __init__(
        self,
        title: str,
        value: dict[str, Any],
        fields_by_kind: dict[str, tuple[_Field, ...]],
        normalizer: Callable[[Any], dict[str, Any]],
        parent=None,
        *,
        flat: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(430)
        self._normalizer = normalizer
        self._flat = bool(flat)
        self._value: dict[str, Any] | None = None
        self._forms: dict[str, _ParameterForm] = {}

        layout = QVBoxLayout(self)
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type", self))
        self.kind_input = QComboBox(self)
        self.kind_input.setAccessibleName(f"{title} type")
        type_row.addWidget(self.kind_input, 1)
        layout.addLayout(type_row)

        self.form_stack = QStackedWidget(self)
        current_kind = str(value.get("kind", ""))
        current_params = value if self._flat else value.get("params", {})
        for index, (kind, fields) in enumerate(fields_by_kind.items()):
            self.kind_input.addItem(kind.replace("_", " ").title(), kind)
            params = current_params if kind == current_kind else {}
            form = _ParameterForm(fields, params, self)
            self._forms[kind] = form
            self.form_stack.addWidget(form)
            if kind == current_kind:
                self.kind_input.setCurrentIndex(index)
        self.form_stack.setCurrentIndex(self.kind_input.currentIndex())
        layout.addWidget(self.form_stack)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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
        self.kind_input.currentIndexChanged.connect(self.form_stack.setCurrentIndex)

    def _validate_and_accept(self) -> None:
        kind = str(self.kind_input.currentData())
        params = self._forms[kind].values()
        candidate = (
            {"kind": kind, **params}
            if self._flat
            else {"kind": kind, "params": params}
        )
        try:
            self._value = self._normalizer(candidate)
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def value(self) -> dict[str, Any]:
        if self._value is None:
            raise RuntimeError("The structured editor has not been accepted.")
        return deepcopy(self._value)


class _StructuredValueEditor(QWidget):
    valueChanged = Signal(object)

    def __init__(self, value: Any, *, title: str, normalizer, parent=None):
        super().__init__(parent)
        self._title = title
        self._normalizer = normalizer
        self._value: Any = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel(self)
        self.summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.edit_button = QPushButton("Configure…", self)
        self.edit_button.setAccessibleName(f"Configure {title}")
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.edit_button)
        self.setFocusProxy(self.edit_button)
        self.edit_button.clicked.connect(self._open_dialog)
        self.set_value(value)

    def _dialog(self) -> QDialog:
        raise NotImplementedError

    def _summary_text(self, value: Any) -> str:
        return str(value)

    def _open_dialog(self) -> None:
        dialog = self._dialog()
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.set_value(dialog.value(), emit=True)
        finally:
            dialog.deleteLater()

    def value(self) -> Any:
        return deepcopy(self._value)

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        normalized = self._normalizer(value)
        self._value = deepcopy(normalized)
        text = self._summary_text(normalized)
        self.summary.setText(text)
        self.summary.setToolTip(text)
        self.summary.setAccessibleName(text)
        if emit:
            self.valueChanged.emit(deepcopy(normalized))


class AxisScaleEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="axis scale", normalizer=normalize_scale, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Axis scale", self.value(), _SCALE_FIELDS, normalize_scale, self)

    def _summary_text(self, value: Any) -> str:
        return str(value["kind"]).replace("_", " ").title()


class AxisLocatorEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="tick locator", normalizer=normalize_locator, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Tick locator", self.value(), _LOCATOR_FIELDS, normalize_locator, self)

    def _summary_text(self, value: Any) -> str:
        names = {"max_n": "Maximum N", "auto_minor": "Automatic minor", "null": "None"}
        return names.get(value["kind"], str(value["kind"]).replace("_", " ").title())


class AxisFormatterEditor(_StructuredValueEditor):
    def __init__(self, value: Any, parent=None):
        super().__init__(value, title="tick formatter", normalizer=normalize_formatter, parent=parent)

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog("Tick formatter", self.value(), _FORMATTER_FIELDS, normalize_formatter, self)

    def _summary_text(self, value: Any) -> str:
        names = {
            "str_method": "String format",
            "log_exponent": "Log exponent",
            "log_mathtext": "Log math text",
            "log_sci": "Log scientific",
            "null": "None",
        }
        return names.get(value["kind"], str(value["kind"]).replace("_", " ").title())


class _FontSpecDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
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

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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


class FigureLayoutEditor(_StructuredValueEditor):
    """Edit the tagged Figure layout engine and its parameters."""

    def __init__(self, value: Any, parent=None):
        super().__init__(
            value,
            title="layout engine",
            normalizer=normalize_figure_layout,
            parent=parent,
        )

    def _dialog(self) -> _TaggedSpecDialog:
        return _TaggedSpecDialog(
            "Layout engine",
            self.value(),
            _LAYOUT_FIELDS,
            normalize_figure_layout,
            self,
        )

    def _summary_text(self, value: Any) -> str:
        names = {"none": "None"}
        kind = str(value["kind"])
        return names.get(kind, kind.title())


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


class _TextBoxDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
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

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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


class _ScatterColorMapDialog(QDialog):
    def __init__(self, value: Any, color_library: ColorLibrary, parent=None):
        super().__init__(parent)
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
        form.addRow("Colormap", self.cmap_input)
        form.addRow("Normalization", self.norm_input)
        form.addRow("Bad color", self.bad_input)
        form.addRow("Under color", self.under_input)
        form.addRow("Over color", self.over_input)
        form.addRow("Non-finite values", self.nonfinite_input)
        layout.addWidget(self.details)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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
        form.addRow("Data range", self.input_range_input)
        form.addRow("Point area (pt\u00b2)", self.output_range_input)
        form.addRow("Clamp to range", self.clamp_input)
        layout.addWidget(self.details)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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
        form.addRow("Visible", self.visible_input)
        form.addRow("Color", self.color_input)
        form.addRow("Pattern", self.line_pattern_input)
        form.addRow("Width", self.linewidth_input)
        form.addRow("Opacity", self.alpha_input)
        form.addRow("Z order", self.zorder_input)

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
        self.setWindowTitle("Zoom connectors")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._value: tuple[dict[str, Any], ...] | None = None
        specs = normalize_connectors(value)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.pages: list[_ConnectorPage] = []
        for label, spec in zip(CONNECTOR_LABELS, specs):
            page = _ConnectorPage(spec, color_library, self.tabs)
            self.pages.append(page)
            self.tabs.addTab(page, label)
        layout.addWidget(self.tabs)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B00020;")
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


StructuredValueEditor = _StructuredValueEditor


__all__ = [
    "AxisFormatterEditor",
    "AxisLocatorEditor",
    "AxisScaleEditor",
    "CONNECTOR_LABELS",
    "FigureLayoutEditor",
    "FontSpecEditor",
    "MarkEveryEditor",
    "NormSpecEditor",
    "ScatterColorMapEditor",
    "ScatterSizeMapEditor",
    "StructuredValueEditor",
    "TEXT_BOX_STYLES",
    "TextBoxEditor",
    "ZoomConnectorsEditor",
    "normalize_connectors",
]
