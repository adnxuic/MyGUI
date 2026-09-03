"""Shared dialog chrome for structured Inspector spec editors."""

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
    QVBoxLayout,
    QWidget,
)


from mygui.application_theme import bind_widget_qss
from mygui.widgets.english_buttons import apply_english_dialog_buttons
from mygui.widgets.ui_components import (
    UiTextRole,
    UiVariant,
    apply_text_style,
    style_button,
)

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    NullableDoubleEditor,
    format_number_sequence,
    parse_number_sequence,
)
from .inspector_layout import (
    SAFE_MIN_WIDTH,
    add_labeled_form_row,
    apply_expanding_field,
    configure_inspector_form,
)

_DIALOG_QSS = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"


def _bind_spec_dialog(dialog: QDialog) -> None:
    bind_widget_qss(dialog, _DIALOG_QSS)


def _chrome_error_label(parent) -> QLabel:
    label = QLabel(parent)
    label.setObjectName("chrome_error_label")
    label.setWordWrap(True)
    label.hide()
    return label


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
    "index": (
        _Field(
            "base",
            "Index interval",
            "number",
            1.0,
            tooltip="Use for index-like data with a regular item interval.",
        ),
        _Field("offset", "Index offset", "number", 0.0),
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
    "format_str": (
        _Field(
            "format",
            "Percent format",
            "text",
            "%g",
            tooltip="One safe percent conversion; %% inserts a literal percent sign.",
        ),
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

_ERROR_EVERY_FIELDS = {
    "all": (),
    "stride": (
        _Field("start", "First error point", "int", 0),
        _Field("step", "Every N points", "int", 1),
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.enabled_input = QCheckBox("Set", self)
        self.value_input = FocusAwareSpinBox(self)
        self.value_input.setRange(-2_147_483_647, 2_147_483_647)
        apply_expanding_field(self.value_input)
        layout.addWidget(self.enabled_input)
        layout.addWidget(self.value_input)
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
        configure_inspector_form(layout)
        layout.setContentsMargins(0, 6, 0, 0)
        if not fields:
            note = QLabel("This type has no additional parameters.", self)
            note.setWordWrap(True)
            layout.addRow(note)
        for field in fields:
            value = _get_path(values, field.path, field.default)
            editor = self._create_input(field, value)
            editor.setAccessibleName(field.label)
            apply_expanding_field(editor)
            if field.tooltip:
                editor.setToolTip(field.tooltip)
                editor.setAccessibleDescription(field.tooltip)
            self._inputs[field.path] = editor
            add_labeled_form_row(layout, field.label, editor, tooltip=field.tooltip)

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
        _bind_spec_dialog(self)
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

        self.error_label = _chrome_error_label(self)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        apply_english_dialog_buttons(buttons)
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setMinimumWidth(1)
        apply_text_style(self.summary, UiTextRole.VALUE)
        self.summary.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.edit_button = QPushButton("Configure…", self)
        self.edit_button.setAccessibleName(f"Configure {title}")
        style_button(self.edit_button, variant=UiVariant.OUTLINE)
        apply_expanding_field(self.edit_button)
        layout.addWidget(self.summary)
        layout.addWidget(self.edit_button)
        self.setFocusProxy(self.edit_button)
        self.setMinimumWidth(SAFE_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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




StructuredValueEditor = _StructuredValueEditor
