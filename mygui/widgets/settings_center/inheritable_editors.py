"""Reusable inherit-source switch plus a retained value editor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QWidget,
)

from mygui.application_settings.models import (
    DefaultValueMode,
    InheritSource,
    InheritableValue,
    SettingEditorKind,
)
from mygui.application_settings.registry import SettingSpec
from mygui.figuremodify.matplotlib_adapter import (
    available_font_families,
    available_marker_definitions,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.widgets.settings_pages.page import FocusDoubleSpinBox

GENERIC_FONT_FAMILIES = (
    "sans-serif",
    "serif",
    "monospace",
    "cursive",
    "fantasy",
)
_FONT_FAMILY_CHOICES: tuple[str, ...] | None = None
_FONT_FAMILY_MODEL: QStringListModel | None = None


class FocusComboBox(QComboBox):
    """Combo that ignores wheel events until it has focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FontFamilyComboBox(FocusComboBox):
    """Editable font combo that attaches the shared catalog on first use."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(16)
        self._catalog_attached = False

    def attach_catalog(self) -> None:
        if self._catalog_attached:
            return
        current = self.currentText()
        self.setModel(font_family_item_model())
        self._catalog_attached = True
        _set_font_combo_value(self, current)

    def showPopup(self) -> None:  # noqa: N802 — Qt override
        self.attach_catalog()
        super().showPopup()

    def focusInEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.attach_catalog()
        super().focusInEvent(event)


def inherit_checkbox_label(spec: SettingSpec) -> str:
    if spec.inherit_source is InheritSource.AXES_PALETTE:
        return "Use Axes palette"
    return "Use Figure style"


def enum_choice_label(value: Any) -> str:
    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "None"
    return str(value)


def marker_choice_label(value: str) -> str:
    needle = str(value)
    for key, description in available_marker_definitions():
        if str(key) == needle:
            return f"{needle} ({description})"
    if needle == "None":
        return "None (no marker)"
    return needle


def font_family_choices() -> tuple[str, ...]:
    global _FONT_FAMILY_CHOICES
    cached = _FONT_FAMILY_CHOICES
    if cached is not None:
        return cached
    seen: dict[str, None] = {}
    for name in (*GENERIC_FONT_FAMILIES, *available_font_families()):
        text = str(name).strip()
        if text:
            seen.setdefault(text, None)
    catalog = tuple(seen)
    _FONT_FAMILY_CHOICES = catalog
    return catalog


def font_family_item_model() -> QStringListModel:
    """Return the process-level font-family combo model.

    Combos share this catalog so Axes Components does not insert hundreds of
    items four times. The model is parented to ``QApplication`` so individual
    combos do not take ownership.
    """

    global _FONT_FAMILY_MODEL
    model = _FONT_FAMILY_MODEL
    if model is not None:
        try:
            model.rowCount()
        except RuntimeError:
            model = None
            _FONT_FAMILY_MODEL = None
        else:
            return model
    owner = QApplication.instance()
    model = QStringListModel(list(font_family_choices()), owner)
    _FONT_FAMILY_MODEL = model
    return model


class InheritableSettingRow(QWidget):
    """One Components field: inherit switch plus a retained typed editor."""

    valueChanged = Signal()

    def __init__(
        self,
        spec: SettingSpec,
        *,
        color_library: ColorLibrary,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self._loading = False
        self.inherit_box = QCheckBox(inherit_checkbox_label(spec), self)
        self.inherit_box.setObjectName(f"settings_inherit_{spec.key}")
        self.inherit_box.setAccessibleName(inherit_checkbox_label(spec))
        self.inherit_box.setFocusPolicy(Qt.StrongFocus)
        self._read_inner: Callable[[], Any]
        self._write_inner: Callable[[Any], None]
        self.value_editor = self._make_editor(spec, color_library)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.inherit_box, 0)
        layout.addWidget(self.value_editor, 1)
        self.inherit_box.toggled.connect(self._on_inherit_toggled)
        self.setObjectName(f"settings_inheritable_{spec.key}")

    def _make_editor(self, spec: SettingSpec, color_library: ColorLibrary) -> QWidget:
        kind = spec.editor
        if kind is SettingEditorKind.INHERITABLE_COLOR:
            editor = ColorChoiceWidget(
                color=str(spec.default.value),
                color_library=color_library,
                auto_record_recent=False,
                allow_favorite=False,
                parent=self,
            )
            editor.setAccessibleName(spec.label or spec.key)
            editor.colorChanged.connect(self._on_value_edited)
            self._read_inner = editor.color
            self._write_inner = lambda value: editor.set_color(
                value, emit=False, record_recent=False
            )
            return editor
        if kind is SettingEditorKind.INHERITABLE_BOOL:
            editor = QCheckBox(spec.label or "Enabled", self)
            editor.setObjectName(f"settings_value_{spec.key}")
            editor.setAccessibleName(spec.label or spec.key)
            editor.setFocusPolicy(Qt.StrongFocus)
            editor.setChecked(bool(spec.default.value))
            editor.toggled.connect(self._on_value_edited)
            self._read_inner = lambda: bool(editor.isChecked())
            self._write_inner = lambda value: editor.setChecked(bool(value))
            return editor
        if kind is SettingEditorKind.INHERITABLE_OPTIONAL_NUMBER:
            return self._make_optional_number(spec)
        if kind is SettingEditorKind.INHERITABLE_NUMBER:
            editor = FocusDoubleSpinBox(self)
            editor.setObjectName(f"settings_value_{spec.key}")
            editor.setAccessibleName(spec.label or spec.key)
            editor.setDecimals(2)
            editor.setSingleStep(0.1)
            if spec.minimum is not None:
                editor.setMinimum(float(spec.minimum))
            if spec.maximum is not None:
                editor.setMaximum(float(spec.maximum))
            editor.setValue(float(spec.default.value))
            editor.valueChanged.connect(self._on_value_edited)
            self._read_inner = lambda: float(editor.value())
            self._write_inner = lambda value: editor.setValue(float(value))
            return editor
        if kind is SettingEditorKind.INHERITABLE_TEXT:
            editor = FontFamilyComboBox(self)
            editor.setObjectName(f"settings_value_{spec.key}")
            editor.setAccessibleName(spec.label or spec.key)
            editor.currentIndexChanged.connect(self._on_value_edited)
            editor.editTextChanged.connect(self._on_value_edited)
            self._read_inner = lambda: str(editor.currentText())
            self._write_inner = lambda value: _set_font_combo_value(editor, value)
            return editor
        editor = FocusComboBox(self)
        editor.setObjectName(f"settings_value_{spec.key}")
        editor.setAccessibleName(spec.label or spec.key)
        choices = spec.choices or ()
        for choice in choices:
            if spec.key.endswith(".marker"):
                editor.addItem(marker_choice_label(str(choice)), str(choice))
            else:
                editor.addItem(enum_choice_label(choice), choice)
        editor.currentIndexChanged.connect(self._on_value_edited)
        self._read_inner = lambda: (
            editor.currentData()
            if editor.currentData() is not None
            else editor.currentText()
        )
        self._write_inner = lambda value: _set_combo_value(editor, value)
        return editor

    def extra_focus_widgets(self) -> tuple[QWidget, ...]:
        none_box = getattr(self, "_optional_none", None)
        if none_box is None:
            return ()
        return (none_box,)

    def _make_optional_number(self, spec: SettingSpec) -> QWidget:
        host = QWidget(self)
        host.setObjectName(f"settings_value_{spec.key}")
        host.setAccessibleName(spec.label or spec.key)
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        none_box = QCheckBox("None", host)
        none_box.setObjectName(f"settings_none_{spec.key}")
        none_box.setAccessibleName("None")
        none_box.setFocusPolicy(Qt.StrongFocus)
        spin = FocusDoubleSpinBox(host)
        spin.setObjectName(f"settings_number_{spec.key}")
        spin.setAccessibleName(spec.label or spec.key)
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        if spec.minimum is not None:
            spin.setMinimum(float(spec.minimum))
        if spec.maximum is not None:
            spin.setMaximum(float(spec.maximum))
        default = spec.default.value
        last_number = [
            float(default)
            if default is not None
            else float(spec.maximum if spec.maximum is not None else 1.0)
        ]
        if default is None:
            none_box.setChecked(True)
            spin.setValue(last_number[0])
            spin.setEnabled(False)
        else:
            spin.setValue(float(default))
        self._optional_none = none_box
        self._optional_spin = spin
        self._optional_last = last_number

        def read_inner() -> float | None:
            if none_box.isChecked():
                return None
            return float(spin.value())

        def write_inner(value: Any) -> None:
            if value is None:
                none_box.setChecked(True)
                spin.setEnabled(False)
                return
            last_number[0] = float(value)
            none_box.setChecked(False)
            spin.setValue(float(value))
            spin.setEnabled(not self.inherit_box.isChecked())

        def on_none_toggled(checked: bool) -> None:
            if checked:
                last_number[0] = float(spin.value())
                spin.setEnabled(False)
            else:
                spin.setValue(last_number[0])
                spin.setEnabled(not self.inherit_box.isChecked())
            self._emit_if_ready()

        none_box.toggled.connect(on_none_toggled)
        spin.valueChanged.connect(self._on_value_edited)
        self._read_inner = read_inner
        self._write_inner = write_inner
        row.addWidget(none_box, 0)
        row.addWidget(spin, 1)
        return host

    def value(self) -> InheritableValue:
        mode = (
            DefaultValueMode.INHERIT
            if self.inherit_box.isChecked()
            else DefaultValueMode.OVERRIDE
        )
        return InheritableValue(mode=mode, value=self._read_inner())

    def set_value(self, value: InheritableValue) -> None:
        self._loading = True
        try:
            normalized = self.spec.normalize(value)
            self.inherit_box.setChecked(normalized.mode is DefaultValueMode.INHERIT)
            self._write_inner(normalized.value)
            self.value_editor.setEnabled(normalized.mode is DefaultValueMode.OVERRIDE)
        finally:
            self._loading = False

    def _on_inherit_toggled(self, checked: bool) -> None:
        self.value_editor.setEnabled(not checked)
        if (
            self.spec.editor is SettingEditorKind.INHERITABLE_OPTIONAL_NUMBER
            and getattr(self, "_optional_none", None) is not None
            and self._optional_none.isChecked()
        ):
            self._optional_spin.setEnabled(False)
        self._emit_if_ready()

    def _on_value_edited(self, *_args: object) -> None:
        self._emit_if_ready()

    def _emit_if_ready(self) -> None:
        if self._loading:
            return
        self.valueChanged.emit()


def _set_font_combo_value(editor: QComboBox, value: Any) -> None:
    text = str(value)
    index = editor.findText(text)
    if index >= 0:
        editor.setCurrentIndex(index)
    if editor.isEditable():
        editor.setCurrentText(text)


def _set_combo_value(editor: QComboBox, value: Any) -> None:
    index = editor.findData(value)
    if index < 0:
        index = editor.findData(str(value))
    if index < 0:
        index = editor.findText(str(value))
    if index < 0:
        editor.addItem(enum_choice_label(value), value)
        index = editor.findData(value)
    editor.setCurrentIndex(index)
    if editor.isEditable():
        editor.setCurrentText(str(value))
