from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Any

from Qt_core import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFont,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSignalBlocker,
    QSpinBox,
    QWidget,
    Signal,
)

from code import status_messages
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget

from .common import (
    DebouncedTextBinding,
    NullableDoubleEditor,
    NumericTupleEditor,
    SpinePositionEditor,
    modification_message,
    modification_status,
    modification_succeeded,
)


def _metadata(spec: Any, *names: str, default=None):
    if isinstance(spec, Mapping):
        for name in names:
            if name in spec:
                return spec[name]
        return default
    for name in names:
        if hasattr(spec, name):
            return getattr(spec, name)
    return default


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


class ComponentEditorBase(QWidget):
    """Schema-driven Qt editor for a component controller.

    A controller is expected to expose ``set_property(key, value)`` and either
    ``read_state()`` or ``state``.  Property metadata may be mappings or
    dataclass-like objects, which keeps this UI package independent from the
    controller implementation.
    """

    propertyChanged = Signal(str, object)
    propertyRejected = Signal(str, object)

    def __init__(
        self,
        controller,
        *,
        context=None,
        color_library: ColorLibrary | None = None,
        property_specs: Iterable[Any] | Mapping[str, Any] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.color_library = color_library
        self.form_layout = QFormLayout(self)
        self._specs: dict[str, Any] = {}
        self._editors: dict[str, QWidget] = {}
        self._text_bindings: dict[str, DebouncedTextBinding] = {}
        self._text_formatters: dict[str, Any] = {}
        self._position_inputs: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}
        self._tuple_editors: dict[str, NumericTupleEditor] = {}
        self._nullable_number_editors: dict[str, NullableDoubleEditor] = {}
        self._spine_position_editors: dict[str, SpinePositionEditor] = {}
        self.build(property_specs)

    def _controller_specs(self):
        specs = getattr(self.controller, "property_specs", None)
        if specs is None:
            specs = getattr(type(self.controller), "PROPERTY_SPECS", ())
        return specs() if callable(specs) else specs

    @staticmethod
    def _normalize_specs(specs) -> list[tuple[str, Any]]:
        if specs is None:
            return []
        if isinstance(specs, Mapping):
            return [(str(key), value) for key, value in specs.items()]
        result = []
        for spec in specs:
            key = _metadata(spec, "key", "name")
            if key is None:
                raise ValueError("Property metadata requires a key or name.")
            result.append((str(key), spec))
        return result

    def _state_properties(self) -> Mapping[str, Any]:
        reader = getattr(self.controller, "read_state", None)
        state = reader() if callable(reader) else getattr(self.controller, "state", None)
        if isinstance(state, Mapping):
            properties = state.get("properties", state)
        else:
            properties = getattr(state, "properties", {})
        return properties if isinstance(properties, Mapping) else {}

    def build(self, property_specs=None) -> None:
        specs = self._normalize_specs(
            self._controller_specs() if property_specs is None else property_specs
        )
        properties = self._state_properties()
        for key, spec in specs:
            self._specs[key] = spec
            value = properties.get(key, _metadata(spec, "default", default=None))
            editor = self._create_editor(key, spec, value)
            self._editors[key] = editor
            label = str(_metadata(spec, "label", "title", default=key.replace("_", " ").title()))
            self.form_layout.addRow(label, editor)

    def editor(self, key: str) -> QWidget:
        return self._editors[key]

    def editors(self) -> Mapping[str, QWidget]:
        return dict(self._editors)

    @staticmethod
    def _editor_kind(spec: Any, value: Any, *, key: str = "") -> str:
        raw_kind = _metadata(spec, "editor", "editor_type", "widget", default="")
        kind = _enum_text(raw_kind).casefold().replace("-", "_")
        aliases = {
            "check": "bool",
            "checkbox": "bool",
            "check_box": "bool",
            "boolean": "bool",
            "spin": "int",
            "spinbox": "int",
            "integer": "int",
            "double": "number",
            "float": "number",
            "double_spin": "number",
            "double_spinbox": "number",
            "combo": "enum",
            "combobox": "enum",
            "choice": "enum",
            "line_edit": "text",
            "string": "text",
            "colour": "color",
            "font_family": "font",
            "point": "position",
            "xy": "position",
            "size": "position",
            "range": "position",
            "rotation": "number",
            "line_style": "enum",
            "font_weight": "enum",
            "legend_position": "enum",
            "marker": "enum",
        }
        kind = aliases.get(kind, kind)
        if kind == "auto":
            kind = ""
        if kind:
            return kind
        property_key = str(
            key or _metadata(spec, "key", "name", default="")
        ).casefold()
        if "color" in property_key or "colour" in property_key:
            return "color"
        if "fontfamily" in property_key or property_key in {"font", "font_family"}:
            return "font"
        if property_key in {"position", "xy", "coords", "coordinates"}:
            return "position"
        value_type = _metadata(spec, "value_type", "type", "python_type")
        if value_type is bool or isinstance(value, bool):
            return "bool"
        if value_type is int or (isinstance(value, int) and not isinstance(value, bool)):
            return "int"
        if value_type is float or isinstance(value, float):
            return "number"
        choices = _metadata(spec, "choices", "options", "values")
        if choices:
            return "enum"
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return "position"
        return "text"

    @staticmethod
    def _bounds(spec: Any, *, integer: bool) -> tuple[float, float]:
        minimum = _metadata(spec, "minimum", "min_value", "minimum_value", "min")
        maximum = _metadata(spec, "maximum", "max_value", "maximum_value", "max")
        if integer:
            return (
                -2_147_483_647 if minimum is None else int(minimum),
                2_147_483_647 if maximum is None else int(maximum),
            )
        return (
            -1e300 if minimum is None else float(minimum),
            1e300 if maximum is None else float(maximum),
        )

    def _create_editor(self, key: str, spec: Any, value: Any) -> QWidget:
        kind = self._editor_kind(spec, value, key=key)
        allow_none = bool(_metadata(spec, "allow_none", default=False))
        if kind == "bool":
            editor = QCheckBox(self)
            editor.setChecked(bool(value))
            editor.toggled.connect(lambda candidate, k=key: self.apply_property(k, candidate))
            return editor
        if kind == "int":
            editor = QSpinBox(self)
            minimum, maximum = self._bounds(spec, integer=True)
            editor.setRange(int(minimum), int(maximum))
            editor.setSingleStep(int(_metadata(spec, "step", "single_step", default=1)))
            editor.setValue(int(value or 0))
            editor.valueChanged.connect(lambda candidate, k=key: self.apply_property(k, candidate))
            return editor
        if kind == "number":
            minimum, maximum = self._bounds(spec, integer=False)
            if allow_none:
                fallback = _metadata(spec, "default", default=None)
                if fallback is None:
                    fallback = 1.0
                editor = NullableDoubleEditor(
                    value,
                    fallback=float(fallback),
                    bounds=(minimum, maximum),
                    decimals=int(_metadata(spec, "decimals", default=6)),
                    step=float(
                        _metadata(spec, "step", "single_step", default=0.1)
                    ),
                    parent=self,
                )
                editor.valueChanged.connect(
                    lambda candidate, k=key: self.apply_property(k, candidate)
                )
                self._nullable_number_editors[key] = editor
                return editor
            editor = QDoubleSpinBox(self)
            editor.setRange(minimum, maximum)
            editor.setDecimals(int(_metadata(spec, "decimals", default=6)))
            editor.setSingleStep(float(_metadata(spec, "step", "single_step", default=0.1)))
            editor.setValue(float(value or 0.0))
            editor.valueChanged.connect(lambda candidate, k=key: self.apply_property(k, candidate))
            return editor
        if kind == "enum":
            editor = QComboBox(self)
            choices = _metadata(
                spec, "choices", "options", "values", default=()
            ) or ()
            raw_editor = _enum_text(
                _metadata(spec, "editor", "editor_type", "widget", default="")
            ).casefold()
            if not choices and raw_editor == "line_style":
                choices = {
                    "Solid": "-",
                    "Dashed": "--",
                    "Dash-dot": "-.",
                    "Dotted": ":",
                    "None": "None",
                }
            elif not choices and raw_editor == "marker":
                choices = (
                    "None",
                    "o",
                    "s",
                    "D",
                    "^",
                    "v",
                    "<",
                    ">",
                    "x",
                    "+",
                    "*",
                    "P",
                    "X",
                )
            elif not choices and raw_editor == "font_weight":
                choices = ("normal", "light", "medium", "semibold", "bold", "heavy")
            elif not choices and raw_editor == "legend_position":
                choices = (
                    "best",
                    "upper right",
                    "upper left",
                    "lower left",
                    "lower right",
                    "right",
                    "center left",
                    "center right",
                    "lower center",
                    "upper center",
                    "center",
                )
            iterable = choices.items() if isinstance(choices, Mapping) else ((item, item) for item in choices)
            for label, choice in iterable:
                editor.addItem(str(label), choice)
            index = editor.findData(value)
            if index < 0:
                index = editor.findData(_enum_text(value))
            editor.setCurrentIndex(max(0, index))
            editor.currentIndexChanged.connect(
                lambda _index, combo=editor, k=key: self.apply_property(k, combo.currentData())
            )
            return editor
        if kind == "color":
            if self.color_library is None:
                raise ValueError(
                    f"Property '{key}' requires the application ColorLibrary to be injected."
                )
            initial_color = value
            if initial_color is None:
                initial_color = _metadata(spec, "default", default=None)
            if initial_color is None:
                initial_color = "#000000"
            editor = ColorChoiceWidget(
                initial_color,
                color_library=self.color_library,
                parent=self,
            )
            editor.colorChanged.connect(lambda candidate, k=key: self.apply_property(k, candidate))
            return editor
        if kind == "font":
            editor = QFontComboBox(self)
            if value:
                editor.setCurrentFont(QFont(str(value)))
            editor.currentFontChanged.connect(
                lambda font, k=key: self.apply_property(k, font.family())
            )
            return editor
        if kind == "position":
            fallback = _metadata(spec, "default", default=None)
            editor = NumericTupleEditor(
                value,
                length=2,
                nullable=allow_none,
                fallback=fallback,
                decimals=int(_metadata(spec, "decimals", default=6)),
                step=float(_metadata(spec, "step", default=0.1)),
                parent=self,
            )
            editor.valueChanged.connect(
                lambda candidate, k=key: self.apply_property(k, candidate)
            )
            self._tuple_editors[key] = editor
            self._position_inputs[key] = tuple(editor.inputs)
            return editor
        if kind == "rectangle":
            editor = NumericTupleEditor(
                value,
                length=4,
                nullable=allow_none,
                fallback=_metadata(spec, "default", default=None),
                decimals=int(_metadata(spec, "decimals", default=6)),
                step=float(_metadata(spec, "step", default=0.1)),
                parent=self,
            )
            editor.valueChanged.connect(
                lambda candidate, k=key: self.apply_property(k, candidate)
            )
            self._tuple_editors[key] = editor
            return editor
        if kind == "spine_position":
            editor = SpinePositionEditor(value, parent=self)
            editor.valueChanged.connect(
                lambda candidate, k=key: self.apply_property(k, candidate)
            )
            self._spine_position_editors[key] = editor
            return editor
        if kind == "aspect":
            return self._create_text_editor(
                key,
                spec,
                value,
                parser=self._parse_aspect,
                formatter=lambda candidate: str(candidate),
            )

        value_type = _metadata(spec, "value_type", "type", "python_type")
        if value_type is dict:
            return self._create_text_editor(
                key,
                spec,
                value,
                parser=lambda candidate, nullable=allow_none: (
                    None
                    if nullable and not candidate.strip()
                    else json.loads(candidate)
                ),
                formatter=lambda candidate: (
                    ""
                    if candidate is None
                    else json.dumps(
                        candidate,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
            )
        return self._create_text_editor(
            key,
            spec,
            value,
            parser=lambda candidate, nullable=allow_none: (
                None if nullable and not candidate else candidate
            ),
            formatter=lambda candidate: "" if candidate is None else str(candidate),
        )

    @staticmethod
    def _parse_aspect(candidate: str):
        text = str(candidate).strip()
        lowered = text.casefold()
        if lowered in {"auto", "equal"}:
            return lowered
        return float(text)

    def _create_text_editor(
        self,
        key: str,
        spec: Any,
        value: Any,
        *,
        parser,
        formatter,
    ) -> QLineEdit:
        editor = QLineEdit(formatter(value), self)
        result_presenter = None
        messages = getattr(self.context, "messages", None)
        if callable(getattr(messages, "present", None)):
            label = str(
                _metadata(
                    spec,
                    "label",
                    "title",
                    default=key.replace("_", " ").title(),
                )
            )
            result_presenter = (
                lambda result, presenter=messages, text=label, k=key:
                presenter.present(
                    result,
                    success=self._success_message(k, text),
                )
            )
        binding = DebouncedTextBinding(
            editor,
            lambda candidate, k=key, convert=parser: self._set_controller_property(
                k, convert(candidate)
            ),
            delay_ms=int(_metadata(spec, "debounce_ms", "delay_ms", default=250)),
            result_presenter=result_presenter,
            parent=self,
        )
        binding.applied.connect(
            lambda candidate, k=key, convert=parser: self.propertyChanged.emit(
                k, convert(candidate)
            )
        )
        binding.rejected.connect(lambda candidate, k=key: self.propertyRejected.emit(k, candidate))
        self._text_bindings[key] = binding
        self._text_formatters[key] = formatter
        return editor

    def _set_controller_property(self, key: str, value: Any):
        setter = getattr(self.controller, "set_property", None)
        if not callable(setter):
            raise AttributeError("Component controller does not provide set_property().")
        return setter(key, value)

    def _success_message(self, key: str, label: str) -> str:
        return f"{label} updated."

    def apply_property(self, key: str, value: Any) -> bool:
        old_value = self._state_properties().get(key)
        try:
            result = self._set_controller_property(key, value)
        except Exception as exc:
            self._set_editor_value(key, old_value)
            status_messages.show_error(str(exc))
            self.propertyRejected.emit(key, value)
            return False
        label = str(
            _metadata(
                self._specs.get(key, {}),
                "label",
                "title",
                default=key.replace("_", " ").title(),
            )
        )
        messages = getattr(self.context, "messages", None)
        if callable(getattr(messages, "present", None)):
            succeeded = messages.present(
                result,
                success=self._success_message(key, label),
            )
        else:
            succeeded = modification_succeeded(result)
            if succeeded:
                message = modification_message(result)
                status = modification_status(result)
                if status == "empty" and message:
                    status_messages.show_warning(message)
                elif status != "noop":
                    status_messages.show_success(
                        message or self._success_message(key, label)
                    )
            else:
                message = modification_message(result)
                if message:
                    status_messages.show_error(message)
        if not succeeded:
            self._set_editor_value(key, old_value)
            self.propertyRejected.emit(key, value)
            return False
        actual_value = self._state_properties().get(key, value)
        self._set_editor_value(key, actual_value)
        self.propertyChanged.emit(key, actual_value)
        return True

    def _set_editor_value(self, key: str, value: Any) -> None:
        editor = self._editors.get(key)
        if editor is None:
            return
        kind = self._editor_kind(self._specs[key], value, key=key)
        if isinstance(editor, NullableDoubleEditor):
            editor.set_value(value)
            return
        if isinstance(editor, NumericTupleEditor):
            editor.set_value(value)
            return
        if isinstance(editor, SpinePositionEditor):
            editor.set_value(value)
            return
        if key in self._text_bindings:
            formatter = self._text_formatters.get(
                key,
                lambda candidate: "" if candidate is None else str(candidate),
            )
            self._text_bindings[key].set_text(formatter(value))
            return
        if kind == "color":
            if value is not None:
                editor.set_color(value, emit=False)
            return
        if kind == "font":
            blocker = QSignalBlocker(editor)
            editor.setCurrentFont(QFont(str(value)))
            del blocker
            return
        blocker = QSignalBlocker(editor)
        if kind == "bool":
            editor.setChecked(bool(value))
        elif kind == "int":
            editor.setValue(int(value or 0))
        elif kind == "number":
            editor.setValue(float(value or 0.0))
        elif kind == "enum":
            index = editor.findData(value)
            if index >= 0:
                editor.setCurrentIndex(index)
        del blocker

    def sync_from_controller(self) -> None:
        properties = self._state_properties()
        for key in self._editors:
            if key in properties:
                self._set_editor_value(key, properties[key])
