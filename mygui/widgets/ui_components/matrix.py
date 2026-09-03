"""Test-only component matrix. Not mounted in production windows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .apply import annotate_section, apply_text_style, apply_ui_style
from .feedback import style_progress_bar
from .factories import (
    create_alert,
    create_badge,
    create_button,
    create_card,
    create_check_box,
    create_combo_box,
    create_double_spin_box,
    create_empty_state,
    create_icon_button,
    create_line_edit,
    create_plain_text_edit,
    create_radio_button,
    create_spin_box,
    create_tabs,
)
from .models import UiRole, UiSize, UiTextRole, UiTone, UiVariant


def build_component_matrix(parent: QWidget | None = None) -> QWidget:
    """Return a hidden matrix of every role/variant/size for tests.

    Production UI must not add this widget to MainWindow or Settings.
    """

    host = QWidget(parent)
    host.setObjectName("ui_component_matrix")
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    root = QVBoxLayout(host)
    root.setContentsMargins(8, 8, 8, 8)

    buttons = QGroupBox("Buttons", host)
    grid = QGridLayout(buttons)
    row = 0
    for variant in UiVariant:
        for size in (UiSize.SMALL, UiSize.DEFAULT, UiSize.LARGE):
            button = create_button(
                f"{variant.value}/{size.value}",
                variant=variant,
                size=size,
                parent=buttons,
            )
            grid.addWidget(button, row, 0)
            disabled = create_button(
                "disabled",
                variant=variant,
                size=size,
                parent=buttons,
            )
            disabled.setEnabled(False)
            grid.addWidget(disabled, row, 1)
            pressed = create_button(
                "pressed",
                variant=variant,
                size=size,
                parent=buttons,
            )
            pressed.setDown(True)
            grid.addWidget(pressed, row, 2)
            row += 1
    icon = create_icon_button(parent=buttons, accessible_name="Icon tool")
    grid.addWidget(icon, row, 0)
    checked = create_button("checked", variant=UiVariant.GHOST, parent=buttons)
    checked.setCheckable(True)
    checked.setChecked(True)
    grid.addWidget(checked, row, 1)
    root.addWidget(buttons)

    forms = QGroupBox("Fields", host)
    form_grid = QGridLayout(forms)
    line = create_line_edit("enabled", parent=forms)
    invalid = create_line_edit("invalid", parent=forms, invalid=True)
    readonly = create_line_edit("readonly", parent=forms)
    readonly.setReadOnly(True)
    area = create_plain_text_edit("notes", parent=forms)
    combo = create_combo_box(parent=forms)
    combo.addItem("Choice")
    spin = create_spin_box(parent=forms)
    dspin = create_double_spin_box(parent=forms)
    check = create_check_box("Checked", parent=forms)
    check.setChecked(True)
    indeterminate = QCheckBox("Indeterminate", forms)
    apply_ui_style(indeterminate, role=UiRole.CHECKBOX)
    indeterminate.setTristate(True)
    indeterminate.setCheckState(Qt.CheckState.PartiallyChecked)
    radio = create_radio_button("Radio", parent=forms)
    radio.setChecked(True)
    for index, widget in enumerate(
        (line, invalid, readonly, area, combo, spin, dspin, check, indeterminate, radio)
    ):
        form_grid.addWidget(widget, index // 2, index % 2)
    root.addWidget(forms)

    chrome = QGroupBox("Chrome", host)
    chrome_layout = QVBoxLayout(chrome)
    chrome_layout.addWidget(create_card(parent=chrome))
    chrome_layout.addWidget(create_alert("Alert", tone=UiTone.WARNING, parent=chrome))
    chrome_layout.addWidget(create_badge("Badge", tone=UiTone.INFO, parent=chrome))
    tabs = create_tabs(parent=chrome)
    tabs.addTab(QLabel("One", tabs), "One")
    tabs.addTab(QLabel("Two", tabs), "Two")
    chrome_layout.addWidget(tabs)
    chrome_layout.addWidget(
        create_empty_state("Empty", "No items", "Create", parent=chrome)
    )
    status = QLabel("Status", chrome)
    apply_ui_style(status, role=UiRole.STATUS, tone=UiTone.INFO)
    chrome_layout.addWidget(status)
    progress = QProgressBar(chrome)
    progress.setRange(0, 0)
    style_progress_bar(progress, tone=UiTone.INFO)
    chrome_layout.addWidget(progress)
    root.addWidget(chrome)

    type_box = QGroupBox("Typography", host)
    annotate_section(type_box)
    type_layout = QVBoxLayout(type_box)
    for role in UiTextRole:
        label = QLabel(role.value, type_box)
        apply_text_style(label, role)
        type_layout.addWidget(label)
    root.addWidget(type_box)
    return host
