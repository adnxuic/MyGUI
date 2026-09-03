"""Force English labels on Qt standard dialog buttons."""

from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QWidget


_DIALOG_BUTTON_TEXT = {
    QDialogButtonBox.StandardButton.Ok: "OK",
    QDialogButtonBox.StandardButton.Cancel: "Cancel",
    QDialogButtonBox.StandardButton.Apply: "Apply",
    QDialogButtonBox.StandardButton.Save: "Save",
    QDialogButtonBox.StandardButton.Close: "Close",
    QDialogButtonBox.StandardButton.Yes: "Yes",
    QDialogButtonBox.StandardButton.No: "No",
}

_MESSAGE_BUTTON_TEXT = {
    QMessageBox.StandardButton.Ok: "OK",
    QMessageBox.StandardButton.Cancel: "Cancel",
    QMessageBox.StandardButton.Yes: "Yes",
    QMessageBox.StandardButton.No: "No",
    QMessageBox.StandardButton.Apply: "Apply",
    QMessageBox.StandardButton.Save: "Save",
    QMessageBox.StandardButton.Close: "Close",
}


def apply_english_dialog_buttons(box: QDialogButtonBox) -> QDialogButtonBox:
    """Set OK/Cancel and related standard buttons to English."""

    for role, text in _DIALOG_BUTTON_TEXT.items():
        button = box.button(role)
        if button is not None:
            button.setText(text)
    from mygui.widgets.ui_components import style_dialog_button_box

    return style_dialog_button_box(box)


def english_ok_cancel(parent: QWidget | None = None) -> QDialogButtonBox:
    """Return an OK/Cancel button box with English labels."""

    return apply_english_dialog_buttons(
        QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent,
        )
    )


def apply_english_message_buttons(box: QMessageBox) -> QMessageBox:
    """Set Yes/No/OK/Cancel on a message box to English."""

    for role, text in _MESSAGE_BUTTON_TEXT.items():
        button = box.button(role)
        if button is not None:
            button.setText(text)
    return box


def ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    """Forward Yes/No questions to the shared confirmation facade."""

    from mygui.widgets.ui_components import ask_confirmation

    return ask_confirmation(
        parent,
        title,
        text,
        confirm_text="Yes",
        cancel_text="No",
    )
