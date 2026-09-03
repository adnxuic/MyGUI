"""Factories that return native Qt widgets with semantic chrome properties."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTableView,
    QTreeView,
    QWidget,
)

from mygui.widgets.common_widget.py_empty_state import PyEmptyState

from .apply import annotate_section, apply_ui_style, combo_is_protected
from .models import UiRole, UiSize, UiTone, UiVariant


def _name(widget: QWidget, object_name: str | None) -> QWidget:
    if object_name:
        widget.setObjectName(object_name)
    return widget


def create_button(
    text: str = "",
    *,
    variant: UiVariant | str = UiVariant.OUTLINE,
    size: UiSize | str = UiSize.DEFAULT,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QPushButton:
    """Return a native push button annotated as ``button``."""

    button = QPushButton(text, parent)
    if text:
        button.setAccessibleName(text)
    _name(button, object_name)
    apply_ui_style(button, role=UiRole.BUTTON, variant=variant, size=size)
    return button


def create_icon_button(
    *,
    variant: UiVariant | str = UiVariant.GHOST,
    parent: QWidget | None = None,
    object_name: str | None = None,
    accessible_name: str = "",
) -> QPushButton:
    """Return a square icon tool button."""

    button = QPushButton(parent)
    if accessible_name:
        button.setAccessibleName(accessible_name)
        button.setToolTip(accessible_name)
    _name(button, object_name)
    apply_ui_style(
        button,
        role=UiRole.ICON_BUTTON,
        variant=variant,
        size=UiSize.ICON,
    )
    return button


def create_line_edit(
    text: str = "",
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
    invalid: bool = False,
) -> QLineEdit:
    """Return a native line edit annotated as ``input``."""

    editor = QLineEdit(text, parent)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.INPUT, invalid=invalid)
    return editor


def create_plain_text_edit(
    text: str = "",
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
    invalid: bool = False,
) -> QPlainTextEdit:
    """Return a native text area annotated as ``textarea``."""

    editor = QPlainTextEdit(text, parent)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.TEXTAREA, invalid=invalid)
    return editor


def create_combo_box(
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QComboBox:
    """Return a native combo box annotated as ``select``."""

    editor = QComboBox(parent)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.SELECT)
    return editor


def create_spin_box(
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QSpinBox:
    """Return a native integer spin box annotated as ``number``."""

    editor = QSpinBox(parent)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.NUMBER)
    return editor


def create_double_spin_box(
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QDoubleSpinBox:
    """Return a native float spin box annotated as ``number``."""

    editor = QDoubleSpinBox(parent)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.NUMBER)
    return editor


def create_check_box(
    text: str = "",
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QCheckBox:
    """Return a native checkbox."""

    editor = QCheckBox(text, parent)
    if text:
        editor.setAccessibleName(text)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.CHECKBOX)
    return editor


def create_radio_button(
    text: str = "",
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QRadioButton:
    """Return a native radio button."""

    editor = QRadioButton(text, parent)
    if text:
        editor.setAccessibleName(text)
    _name(editor, object_name)
    apply_ui_style(editor, role=UiRole.RADIO)
    return editor


def create_tabs(
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QTabWidget:
    """Return a native tab widget annotated as ``tabs``."""

    tabs = QTabWidget(parent)
    _name(tabs, object_name)
    apply_ui_style(tabs, role=UiRole.TABS)
    return tabs


def create_card(
    *,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QFrame:
    """Return a native frame annotated as ``card``."""

    frame = QFrame(parent)
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    _name(frame, object_name)
    apply_ui_style(frame, role=UiRole.CARD)
    return frame


def create_alert(
    text: str = "",
    *,
    tone: UiTone | str = UiTone.NEUTRAL,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QLabel:
    """Return a status/alert label."""

    label = QLabel(text, parent)
    label.setWordWrap(True)
    if text:
        label.setAccessibleName(text)
    _name(label, object_name)
    apply_ui_style(label, role=UiRole.ALERT, tone=tone)
    return label


def create_badge(
    text: str = "",
    *,
    tone: UiTone | str = UiTone.NEUTRAL,
    parent: QWidget | None = None,
    object_name: str | None = None,
) -> QLabel:
    """Return a compact status badge."""

    label = QLabel(text, parent)
    if text:
        label.setAccessibleName(text)
    _name(label, object_name)
    apply_ui_style(label, role=UiRole.BADGE, size=UiSize.SMALL, tone=tone)
    return label


def create_empty_state(
    title: str,
    detail: str,
    primary_text: str | None = None,
    parent: QWidget | None = None,
) -> PyEmptyState:
    """Return the existing empty-state widget with semantic annotation."""

    panel = PyEmptyState(title, detail, primary_text, parent)
    apply_ui_style(panel, role=UiRole.EMPTY_STATE, variant=UiVariant.OUTLINE)
    if panel.primary_button is not None:
        apply_ui_style(
            panel.primary_button,
            role=UiRole.BUTTON,
            variant=UiVariant.PRIMARY,
        )
    return panel


def style_accept_cancel(
    ok: QPushButton,
    cancel: QPushButton,
    *,
    ok_variant: UiVariant | str = UiVariant.PRIMARY,
) -> None:
    """Annotate a dialog accept/cancel pair without changing layout."""

    apply_ui_style(ok, role=UiRole.BUTTON, variant=ok_variant)
    apply_ui_style(cancel, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
    if ok.text() and not ok.accessibleName():
        ok.setAccessibleName(ok.text())
    if cancel.text() and not cancel.accessibleName():
        cancel.setAccessibleName(cancel.text())


def style_button(
    widget: QAbstractButton,
    *,
    variant: UiVariant | str,
    role: UiRole | str = UiRole.BUTTON,
    size: UiSize | str = UiSize.DEFAULT,
) -> QAbstractButton:
    """Annotate one button with an explicit variant. Never infer from text."""

    resolved_role = role if isinstance(role, UiRole) else UiRole(str(role))
    apply_ui_style(widget, role=resolved_role, variant=variant, size=size)
    if not widget.accessibleName():
        label = widget.text() or widget.toolTip()
        if label:
            widget.setAccessibleName(label)
    if resolved_role is UiRole.ICON_BUTTON and not widget.toolTip() and widget.accessibleName():
        widget.setToolTip(widget.accessibleName())
    return widget


def annotate_sections(root: QWidget) -> None:
    """Mark existing group boxes as sections without changing layout."""

    groups = [root] if isinstance(root, QGroupBox) else []
    groups.extend(root.findChildren(QGroupBox))
    for group in groups:
        if group.property("uiRole"):
            continue
        annotate_section(group)


def annotate_form_fields(root: QWidget) -> None:
    """Annotate native fields under ``root`` without restyling push buttons."""

    for widget in root.findChildren(QWidget):
        if widget.property("uiRole"):
            continue
        if isinstance(widget, QAbstractButton) and not isinstance(
            widget, (QCheckBox, QRadioButton)
        ):
            continue
        annotate_inspector_control(widget)


def style_dialog_button_box(box: QDialogButtonBox) -> QDialogButtonBox:
    """Annotate standard OK/Cancel/Apply/Save roles on a button box."""

    mapping = {
        QDialogButtonBox.StandardButton.Ok: UiVariant.PRIMARY,
        QDialogButtonBox.StandardButton.Save: UiVariant.PRIMARY,
        QDialogButtonBox.StandardButton.Apply: UiVariant.PRIMARY,
        QDialogButtonBox.StandardButton.Cancel: UiVariant.OUTLINE,
        QDialogButtonBox.StandardButton.Close: UiVariant.OUTLINE,
        QDialogButtonBox.StandardButton.No: UiVariant.OUTLINE,
        QDialogButtonBox.StandardButton.Yes: UiVariant.PRIMARY,
        QDialogButtonBox.StandardButton.Discard: UiVariant.DESTRUCTIVE,
        QDialogButtonBox.StandardButton.Reset: UiVariant.GHOST,
        QDialogButtonBox.StandardButton.RestoreDefaults: UiVariant.GHOST,
    }
    for role, variant in mapping.items():
        button = box.button(role)
        if button is not None:
            apply_ui_style(button, role=UiRole.BUTTON, variant=variant)
    return box


def annotate_inspector_control(widget: QWidget) -> QWidget:
    """Map a native Inspector primitive onto a closed component role."""

    if widget.property("uiRole"):
        return widget
    if isinstance(widget, QComboBox):
        if combo_is_protected(widget):
            return widget
        return apply_ui_style(widget, role=UiRole.SELECT)
    if isinstance(widget, QAbstractSpinBox):
        return apply_ui_style(widget, role=UiRole.NUMBER)
    if isinstance(widget, QPlainTextEdit):
        return apply_ui_style(widget, role=UiRole.TEXTAREA)
    if isinstance(widget, QLineEdit):
        return apply_ui_style(widget, role=UiRole.INPUT)
    if isinstance(widget, QCheckBox):
        return apply_ui_style(widget, role=UiRole.CHECKBOX)
    if isinstance(widget, QRadioButton):
        return apply_ui_style(widget, role=UiRole.RADIO)
    if isinstance(widget, QAbstractButton):
        return apply_ui_style(widget, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
    if isinstance(widget, QTabWidget):
        return apply_ui_style(widget, role=UiRole.TABS)
    if isinstance(widget, QListWidget):
        return apply_ui_style(widget, role=UiRole.TREE)
    if isinstance(widget, QTreeView):
        return apply_ui_style(widget, role=UiRole.TREE)
    if isinstance(widget, QTableView):
        return apply_ui_style(widget, role=UiRole.TABLE)
    return widget
