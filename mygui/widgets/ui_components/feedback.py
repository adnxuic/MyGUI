"""Feedback facade: validation, busy, progress, Message Box, and confirmation.

Production UI must present warnings and questions through this module rather
than ``QMessageBox.warning`` / ``QMessageBox.question``. Native file and color
dialogs stay unchanged. This module is not a second theme owner.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QMessageBox,
    QProgressBar,
    QWidget,
)

from .apply import apply_ui_style, refresh_ui_style
from .factories import style_button
from .models import (
    PROPERTY_BUSY,
    PROPERTY_INVALID,
    UiRole,
    UiTone,
    UiVariant,
)

_VALIDATION_BACKUP = "_ui_validation_origin"
_BUSY_BACKUP = "_ui_busy_origin"


def _widget_alive(widget: QWidget | None) -> bool:
    if widget is None:
        return False
    try:
        from shiboken6 import isValid

        if not isValid(widget):
            return False
    except Exception:
        pass
    try:
        widget.objectName()
    except RuntimeError:
        return False
    return True


def _flag_is_true(value) -> bool:
    return value in (True, "true", "1")


def set_validation_state(widget: QWidget, *, invalid: bool, message: str = "") -> QWidget:
    """Mark or clear a field error without adding layout nodes.

    Clearing restores the tooltip and accessible description captured on the
    first invalid assignment. Message-only updates skip repolish.
    """

    if not _widget_alive(widget):
        return widget
    was_invalid = _flag_is_true(widget.property(PROPERTY_INVALID))
    if invalid:
        if getattr(widget, _VALIDATION_BACKUP, None) is None:
            setattr(
                widget,
                _VALIDATION_BACKUP,
                (widget.toolTip() or "", widget.accessibleDescription() or ""),
            )
        text = str(message)
        if text:
            widget.setToolTip(text)
            widget.setAccessibleDescription(text)
        if was_invalid:
            return widget
        widget.setProperty(PROPERTY_INVALID, "true")
        return refresh_ui_style(widget)
    backup = getattr(widget, _VALIDATION_BACKUP, None)
    if not was_invalid:
        return widget
    widget.setProperty(PROPERTY_INVALID, "false")
    if backup is not None:
        tooltip, description = backup
        widget.setToolTip(tooltip)
        widget.setAccessibleDescription(description)
        delattr(widget, _VALIDATION_BACKUP)
    return refresh_ui_style(widget)


def set_busy_state(
    widget: QWidget,
    busy: bool,
    *,
    busy_text: str | None = None,
) -> QWidget:
    """Idempotently disable a trigger and restore its original text/enabled."""

    if not _widget_alive(widget):
        return widget
    was_busy = _flag_is_true(widget.property(PROPERTY_BUSY))
    if busy:
        if was_busy:
            return widget
        if getattr(widget, _BUSY_BACKUP, None) is None:
            current_text = widget.text() if hasattr(widget, "text") else None
            setattr(widget, _BUSY_BACKUP, (current_text, widget.isEnabled()))
        widget.setProperty(PROPERTY_BUSY, "true")
        if busy_text is not None and hasattr(widget, "setText"):
            widget.setText(str(busy_text))
        widget.setEnabled(False)
        return refresh_ui_style(widget)
    if not was_busy:
        return widget
    widget.setProperty(PROPERTY_BUSY, "false")
    backup = getattr(widget, _BUSY_BACKUP, None)
    if backup is not None:
        original_text, enabled = backup
        if original_text is not None and hasattr(widget, "setText"):
            widget.setText(original_text)
        widget.setEnabled(bool(enabled))
        delattr(widget, _BUSY_BACKUP)
    return refresh_ui_style(widget)


def style_progress_bar(
    bar: QProgressBar,
    *,
    tone: UiTone | str = UiTone.INFO,
) -> QProgressBar:
    """Annotate an existing native progress bar. Does not add a new bar."""

    if not _widget_alive(bar):
        return bar
    apply_ui_style(bar, role=UiRole.PROGRESS, tone=tone)
    return bar


def style_message_box(
    box: QMessageBox,
    *,
    tone: UiTone | str,
    primary: QAbstractButton | None = None,
    destructive: QAbstractButton | None = None,
) -> QMessageBox:
    """Apply tone and explicit button variants to a native QMessageBox."""

    resolved = tone if isinstance(tone, UiTone) else UiTone(str(tone))
    apply_ui_style(box, role=UiRole.STATUS, tone=resolved)
    styled = {id(primary), id(destructive)}
    if primary is not None:
        style_button(primary, variant=UiVariant.PRIMARY)
    if destructive is not None:
        style_button(destructive, variant=UiVariant.DESTRUCTIVE)
    for button in box.buttons():
        if id(button) in styled:
            continue
        style_button(button, variant=UiVariant.OUTLINE)
    return box


def ask_confirmation(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    destructive: bool = False,
    confirm_text: str = "Continue",
    cancel_text: str = "Cancel",
) -> bool:
    """Ask a styled Yes-style question. Esc and the window close cancel.

    Ordinary confirms default-focus the primary Continue button. Destructive
    confirms default-focus Cancel so close/Esc do not run the action.
    """

    box = QMessageBox(parent)
    box.setIcon(
        QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question
    )
    box.setWindowTitle(str(title))
    box.setText(str(text))
    box.setStandardButtons(
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    )
    confirm = box.button(QMessageBox.StandardButton.Ok)
    cancel = box.button(QMessageBox.StandardButton.Cancel)
    if confirm is not None:
        confirm.setText(str(confirm_text))
    if cancel is not None:
        cancel.setText(str(cancel_text))
    box.setEscapeButton(cancel)
    if destructive:
        box.setDefaultButton(cancel)
        style_message_box(box, tone=UiTone.WARNING, destructive=confirm)
    else:
        box.setDefaultButton(confirm)
        style_message_box(box, tone=UiTone.INFO, primary=confirm)
    box.exec()
    if not _widget_alive(box):
        return False
    return box.clickedButton() is confirm


def present_warning(parent: QWidget | None, title: str, text: str) -> None:
    """Show a modal recoverable warning. Do not also write the Message Bar."""

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(str(title))
    box.setText(str(text))
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    ok_button = box.button(QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("OK")
    style_message_box(box, tone=UiTone.WARNING, primary=ok_button)
    box.exec()


def present_error(parent: QWidget | None, title: str, text: str) -> None:
    """Show a modal unrecoverable/external error. Do not also write the Message Bar."""

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(str(title))
    box.setText(str(text))
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    ok_button = box.button(QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("OK")
    style_message_box(box, tone=UiTone.ERROR, primary=ok_button)
    box.exec()
