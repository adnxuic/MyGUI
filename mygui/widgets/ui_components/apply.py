"""Apply and refresh semantic chrome properties on native Qt widgets."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QComboBox, QWidget

from .models import (
    PROPERTY_INVALID,
    PROPERTY_ROLE,
    PROPERTY_SIZE,
    PROPERTY_TEXT_ROLE,
    PROPERTY_TONE,
    PROPERTY_VARIANT,
    UiComponentSpec,
    UiRole,
    UiSize,
    UiTextRole,
    UiTone,
    UiVariant,
)


def _enum(value, enum_type):
    if isinstance(value, enum_type):
        return value
    return enum_type(str(value))


def component_spec(
    spec: UiComponentSpec | None = None,
    *,
    role: UiRole | str | None = None,
    variant: UiVariant | str | None = None,
    size: UiSize | str | None = None,
    tone: UiTone | str | None = None,
    invalid: bool | None = None,
) -> UiComponentSpec:
    """Return a validated spec from an instance or keyword overrides."""

    base = spec if spec is not None else UiComponentSpec(role=UiRole.BUTTON)
    resolved_role = _enum(role, UiRole) if role is not None else base.role
    return UiComponentSpec(
        role=resolved_role,
        variant=_enum(variant, UiVariant) if variant is not None else base.variant,
        size=_enum(size, UiSize) if size is not None else base.size,
        tone=_enum(tone, UiTone) if tone is not None else base.tone,
        invalid=base.invalid if invalid is None else bool(invalid),
    )


def _combo_check_states(combo: QComboBox) -> tuple[object, ...]:
    model = combo.model()
    if model is None:
        return ()
    column = combo.modelColumn()
    return tuple(
        model.data(model.index(row, column), Qt.ItemDataRole.CheckStateRole)
        for row in range(model.rowCount())
    )


def combo_is_protected(combo: QComboBox) -> bool:
    """Return True for editable or check-model combos that must not become select."""

    if combo.isEditable():
        return True
    return any(state is not None for state in _combo_check_states(combo))


def _restore_combo(
    combo: QComboBox,
    index: int,
    checks: tuple[object, ...],
) -> None:
    try:
        combo.objectName()
    except RuntimeError:
        return
    blocker = QSignalBlocker(combo)
    model = combo.model()
    if model is not None and checks:
        model_blocker = QSignalBlocker(model)
        column = combo.modelColumn()
        for row, check in enumerate(checks):
            if check is not None:
                model.setData(
                    model.index(row, column),
                    check,
                    Qt.ItemDataRole.CheckStateRole,
                )
        del model_blocker
    if combo.currentIndex() != index:
        combo.setCurrentIndex(index)
    del blocker


def _set_property_if_changed(widget: QWidget, name: str, value) -> bool:
    if widget.property(name) == value:
        return False
    widget.setProperty(name, value)
    return True


def refresh_ui_style(widget: QWidget) -> QWidget:
    """Repolish ``widget`` after dynamic-property changes."""

    if not widget.testAttribute(Qt.WidgetAttribute.WA_WState_Polished):
        QWidget.update(widget)
        return widget
    combo = widget if isinstance(widget, QComboBox) else None
    index = combo.currentIndex() if combo is not None else None
    checks = _combo_check_states(combo) if combo is not None else ()
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    # QAbstractItemView.update(QModelIndex) shadows QWidget.update().
    QWidget.update(widget)
    if combo is not None and index is not None:
        _restore_combo(combo, index, checks)
    return widget


def apply_ui_style(
    widget: QWidget,
    spec: UiComponentSpec | None = None,
    *,
    role: UiRole | str | None = None,
    variant: UiVariant | str | None = None,
    size: UiSize | str | None = None,
    tone: UiTone | str | None = None,
    invalid: bool | None = None,
) -> QWidget:
    """Annotate a native widget with validated component properties."""

    resolved = component_spec(
        spec,
        role=role,
        variant=variant,
        size=size,
        tone=tone,
        invalid=invalid,
    )
    changed = False
    changed |= _set_property_if_changed(widget, PROPERTY_ROLE, resolved.role.value)
    changed |= _set_property_if_changed(
        widget, PROPERTY_VARIANT, resolved.variant.value
    )
    changed |= _set_property_if_changed(widget, PROPERTY_SIZE, resolved.size.value)
    changed |= _set_property_if_changed(widget, PROPERTY_TONE, resolved.tone.value)
    changed |= _set_property_if_changed(
        widget,
        PROPERTY_INVALID,
        "true" if resolved.invalid else "false",
    )
    if changed:
        refresh_ui_style(widget)
    return widget


def apply_text_style(
    label: QWidget,
    role: UiTextRole | str,
    *,
    tone: UiTone | str = UiTone.NEUTRAL,
) -> QWidget:
    """Annotate a label with a closed typography role. Does not change layout."""

    resolved = role if isinstance(role, UiTextRole) else UiTextRole(str(role))
    resolved_tone = tone if isinstance(tone, UiTone) else UiTone(str(tone))
    changed = False
    changed |= _set_property_if_changed(label, PROPERTY_TEXT_ROLE, resolved.value)
    changed |= _set_property_if_changed(label, PROPERTY_TONE, resolved_tone.value)
    if changed:
        refresh_ui_style(label)
    return label


def annotate_section(group: QWidget) -> QWidget:
    """Apply section chrome without changing expand/collapse or child enablement."""

    checkable = bool(getattr(group, "isCheckable", lambda: False)())
    checked = bool(getattr(group, "isChecked", lambda: True)()) if checkable else True
    child_enabled = [
        (child, child.isEnabled())
        for child in group.children()
        if isinstance(child, QWidget)
    ]
    apply_ui_style(group, role=UiRole.SECTION)
    if checkable:
        if not group.isCheckable():
            group.setCheckable(True)
        if group.isChecked() != checked:
            group.setChecked(checked)
        restore = getattr(group, "_keep_children_enabled", None)
        if callable(restore):
            restore()
        for child, enabled in child_enabled:
            try:
                child.setEnabled(enabled)
            except RuntimeError:
                continue
    return group


_ELIDE_CACHE_ATTR = "_ui_elide_cache"


def apply_elided_text(
    widget: QWidget,
    text: str,
    *,
    padding: int = 12,
    mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
) -> str:
    """Set elided visible text and keep the full string as tooltip.

    Does not change parent layouts. ``padding`` is subtracted from the current
    widget width before measuring. Repeat calls with the same full text,
    effective width, and font skip ``setText`` and tooltip writes.
    """

    full = str(text)
    width = max(1, widget.width() - max(0, int(padding)))
    font_key = widget.font().toString()
    cached = getattr(widget, _ELIDE_CACHE_ATTR, None)
    if (
        isinstance(cached, tuple)
        and len(cached) == 4
        and cached[0] == full
        and cached[1] == width
        and cached[2] == font_key
    ):
        return cached[3]
    metrics = QFontMetrics(widget.font())
    elided = metrics.elidedText(full, mode, width)
    setter = getattr(widget, "setText", None)
    if callable(setter):
        setter(elided)
    if full and (elided != full or not widget.toolTip()):
        widget.setToolTip(full)
    try:
        setattr(widget, _ELIDE_CACHE_ATTR, (full, width, font_key, elided))
    except RuntimeError:
        pass
    return elided
