"""Runtime chrome inspection for semantic roles and accessibility."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QHeaderView,
    QLineEdit,
    QListView,
    QListWidget,
    QPlainTextEdit,
    QSizeGrip,
    QTabBar,
    QTextEdit,
    QToolButton,
    QWidget,
)

from .models import PROPERTY_ROLE, PROPERTY_VARIANT, UiRole, UiVariant
from .apply import combo_is_protected

_INTERACTIVE = (
    QAbstractButton,
    QLineEdit,
    QAbstractSpinBox,
    QComboBox,
    QAbstractSlider,
    QAbstractItemView,
    QPlainTextEdit,
    QTextEdit,
    QTabBar,
)

_VALID_ROLES = {item.value for item in UiRole}
_VALID_VARIANTS = {item.value for item in UiVariant}


def _module_name(widget: QWidget) -> str:
    return type(widget).__module__ or ""


def is_inspection_exempt(widget: QWidget) -> bool:
    """Return True for Qt internals, Matplotlib chrome, and protected combos."""

    name = widget.objectName() or ""
    if name.startswith("qt_"):
        return True
    if name == "ui_component_matrix":
        return True
    module = _module_name(widget)
    if module.startswith("matplotlib"):
        return True
    if isinstance(widget, QComboBox) and combo_is_protected(widget):
        return True
    parent = widget.parentWidget()
    if isinstance(parent, QComboBox) and combo_is_protected(parent):
        return True
    if type(widget) is QAbstractButton:
        return True
    if isinstance(widget, (QAbstractSlider, QHeaderView, QSizeGrip, QTabBar)):
        return True
    if isinstance(widget, QToolButton) and (
        name in {"ScrollLeftButton", "ScrollRightButton"}
        or isinstance(parent, (QTabBar, QLineEdit))
    ):
        return True
    if isinstance(widget, QListView) and not isinstance(widget, QListWidget):
        return True
    return False


def inspect_chrome(root: QWidget) -> tuple[str, ...]:
    """Report missing uiRole, button variants, and icon-button names.

    Hidden stacked pages are included. Editable and checkable combos stay
    exempt. Does not infer button variants from label text.
    """

    problems: list[str] = []
    widgets: Iterable[QWidget] = (root, *root.findChildren(QWidget))
    for widget in widgets:
        if is_inspection_exempt(widget):
            continue
        if not isinstance(widget, _INTERACTIVE):
            continue
        role = widget.property(PROPERTY_ROLE)
        if not role:
            problems.append(
                f"{type(widget).__name__}#{widget.objectName() or '-'} missing uiRole"
            )
            continue
        if str(role) not in _VALID_ROLES:
            problems.append(
                f"{type(widget).__name__}#{widget.objectName() or '-'} invalid uiRole={role!r}"
            )
            continue
        if str(role) in {UiRole.BUTTON.value, UiRole.ICON_BUTTON.value}:
            variant = widget.property(PROPERTY_VARIANT)
            if str(variant or "") not in _VALID_VARIANTS:
                problems.append(
                    f"{type(widget).__name__}#{widget.objectName() or '-'} missing explicit uiVariant"
                )
        if str(role) == UiRole.ICON_BUTTON.value:
            if not (widget.toolTip() or "").strip():
                problems.append(
                    f"{type(widget).__name__}#{widget.objectName() or '-'} icon-button missing tooltip"
                )
            if not (widget.accessibleName() or "").strip():
                problems.append(
                    f"{type(widget).__name__}#{widget.objectName() or '-'} icon-button missing accessible name"
                )
    return tuple(problems)
