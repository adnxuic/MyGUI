"""Define reusable property controls and editor-section foundations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QWidget,
)

from mygui import status_messages
from mygui.figuremodify.components import (
    ComponentValidationError,
    EditorKind,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary

from .common import (
    DebouncedTextBinding,
    NullableDoubleEditor,
    NumericTupleEditor,
    SpinePositionEditor,
    modification_message,
    modification_status,
    modification_succeeded,
)
from .editor_factories import create_editor_widget
from .inline_spec_editors import InlineValueEditor
from .spec_editors import StructuredValueEditor


_VALUE_EDITORS = (
    InlineValueEditor,
    NullableDoubleEditor,
    NumericTupleEditor,
    SpinePositionEditor,
    StructuredValueEditor,
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


def _metadata_default(spec: Any, *names: str, default):
    """Return metadata while treating an explicit ``None`` as unspecified."""

    value = _metadata(spec, *names, default=default)
    return default if value is None else value


def _display_label(spec: Any, key: str) -> str:
    """Return one non-empty user-facing property label."""

    fallback = str(key).replace("_", " ").title()
    value = _metadata(spec, "label", "title", default=None)
    if value is None or not str(value).strip():
        return fallback
    return str(value).strip()


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
        """Build and lay out this editor section's controls."""

        specs = self._normalize_specs(
            self._controller_specs() if property_specs is None else property_specs
        )
        properties = self._state_properties()
        for key, spec in specs:
            self._specs[key] = spec
            value = properties.get(key, _metadata(spec, "default", default=None))
            editor = self._create_editor(key, spec, value)
            self._editors[key] = editor
            label = _display_label(spec, key)
            tooltip = str(_metadata(spec, "tooltip", default="") or "")
            editor.setAccessibleName(label)
            if tooltip:
                editor.setToolTip(tooltip)
                editor.setAccessibleDescription(tooltip)
            self.form_layout.addRow(label, editor)

    def editor(self, key: str) -> QWidget:
        """Return the editor widget used for the property."""

        return self._editors[key]

    def editors(self) -> Mapping[str, QWidget]:
        """Return the available editors."""

        return dict(self._editors)

    @staticmethod
    def _editor_kind(spec: Any, _value: Any, *, key: str = "") -> EditorKind:
        raw_kind = _metadata(
            spec,
            "editor",
            "editor_type",
            "widget",
            default=EditorKind.AUTO,
        )
        try:
            kind = raw_kind if isinstance(raw_kind, EditorKind) else EditorKind(raw_kind)
        except (TypeError, ValueError) as exc:
            raise ComponentValidationError(
                f"Property {key!r} declares unknown editor {raw_kind!r}."
            ) from exc
        if kind is not EditorKind.AUTO:
            return kind

        choices = _metadata(spec, "choices", "options", "values")
        if choices:
            return EditorKind.ENUM
        value_type = _metadata(spec, "value_type", "type", "python_type")
        inferred = {
            bool: EditorKind.BOOL,
            int: EditorKind.INT,
            float: EditorKind.NUMBER,
            str: EditorKind.TEXT,
            dict: EditorKind.JSON,
        }.get(value_type)
        if inferred is None:
            raise ComponentValidationError(
                f"Property {key!r} cannot infer an editor from value_type "
                f"{value_type!r}; declare EditorKind explicitly."
            )
        return inferred

    @staticmethod
    def _tuple_fallback(spec: Any, length: int) -> tuple[float, ...]:
        """Return a valid starting tuple for an optional numeric group."""

        default = _metadata(spec, "default", default=None)
        if isinstance(default, (tuple, list)) and len(default) == length:
            return tuple(float(item) for item in default)
        if length == 3:
            return (1.0, 1.0, 1.0)
        return tuple(
            0.0 if index % 2 == 0 else 1.0 for index in range(length)
        )

    def _require_color_library(self, key: str) -> ColorLibrary:
        if self.color_library is None:
            raise ValueError(
                f"Property '{key}' requires the application ColorLibrary to be injected."
            )
        return self.color_library

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
        return create_editor_widget(self, key, spec, value)

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
            label = _display_label(spec, key)
            def result_presenter(
                result,
                presenter=messages,
                text=label,
                property_key=key,
            ):
                return presenter.present(
                    result,
                    success=self._success_message(property_key, text),
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
        def operation():
            return setter(key, value)

        perform = getattr(self.context, "perform", None)
        if not callable(perform):
            return operation()
        state = self.controller.state
        role = str(getattr(state.role, "value", state.role)).replace("_", " ").title()
        label = _display_label(self._specs.get(key, {}), key)
        return perform(
            f"Change {role} {label}",
            operation,
            merge_key=("property", self.controller.component_id, key),
        )

    def _success_message(self, key: str, label: str) -> str:
        return f"{label} updated."

    def apply_property(self, key: str, value: Any) -> bool:
        """Apply property."""

        old_value = self._state_properties().get(key)
        try:
            result = self._set_controller_property(key, value)
        except Exception as exc:
            self._set_editor_value(key, old_value)
            status_messages.show_error(str(exc))
            self.propertyRejected.emit(key, value)
            return False
        label = _display_label(self._specs.get(key, {}), key)
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
        if isinstance(editor, _VALUE_EDITORS):
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
        """Refresh controls from authoritative Controller state."""

        properties = self._state_properties()
        for key in self._editors:
            if key in properties:
                self._set_editor_value(key, properties[key])
