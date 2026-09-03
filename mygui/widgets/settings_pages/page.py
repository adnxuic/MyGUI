"""Shared Settings Center page contract. Pages have no window footer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSpinBox,
    QWidget,
)

from mygui.application_settings.registry import (
    SettingSpec,
    SettingsPageSpec,
    SettingsRegistry,
    production_settings_registry,
)
from mygui.widgets.ui_components import UiRole, UiTextRole, apply_text_style, apply_ui_style

QSS_RESOURCE = "mygui/widgets/settings_pages/style.qss"

SettingsPageFactory = Callable[..., QWidget]


@dataclass(frozen=True, slots=True)
class SettingsUiPageSpec:
    """UI page descriptor for the Settings Center shell ``register_page`` hook.

    ``factory`` is lazy: the shell should call it only when the page is first
    shown. Pages do not own Apply / OK / Cancel / Restore page defaults.
    """

    page_id: str
    title: str
    description: str
    keywords: tuple[str, ...]
    setting_keys: tuple[str, ...]
    widget_class: type
    factory: SettingsPageFactory
    registry_page: SettingsPageSpec


def keywords_for_page(
    page_id: str,
    registry: SettingsRegistry | None = None,
) -> tuple[str, ...]:
    """Collect search terms from SettingsRegistry specs. Not a second catalog."""

    catalog = registry or production_settings_registry()
    page = catalog.page(page_id)
    words: list[str] = [page.title, page.page_id]
    for key in page.setting_keys:
        spec = catalog.spec(key)
        words.append(spec.key)
        if spec.label:
            words.append(spec.label)
        if spec.choices:
            for choice in spec.choices:
                words.append(str(getattr(choice, "value", choice)))
                name = getattr(choice, "name", None)
                if name:
                    words.append(str(name))
    seen: dict[str, None] = {}
    for word in words:
        text = str(word).strip()
        if text:
            seen.setdefault(text, None)
    return tuple(seen)


def build_ui_page_spec(
    widget_class: type,
    *,
    description: str,
    extra_keywords: tuple[str, ...] = (),
    registry: SettingsRegistry | None = None,
) -> SettingsUiPageSpec:
    """Compose a shell page spec from the typed SettingsRegistry page."""

    catalog = registry or production_settings_registry()
    page_id = str(widget_class.PAGE_ID)
    page = catalog.page(page_id)
    keywords = keywords_for_page(page_id, catalog)
    if extra_keywords:
        merged = dict.fromkeys((*keywords, *extra_keywords))
        keywords = tuple(merged)

    def factory(parent: QWidget | None = None, **kwargs: Any) -> QWidget:
        return widget_class(parent, **kwargs)

    return SettingsUiPageSpec(
        page_id=page.page_id,
        title=page.title,
        description=description,
        keywords=keywords,
        setting_keys=page.setting_keys,
        widget_class=widget_class,
        factory=factory,
        registry_page=page,
    )


def make_hint_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Muted helper copy. Color comes from theme tokens, not hardcoded gray."""

    label = QLabel(text, parent)
    label.setObjectName("settings_page_hint")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setFocusPolicy(Qt.NoFocus)
    label.setAccessibleName(text.split(".", 1)[0] if text else "Hint")
    apply_text_style(label, UiTextRole.MUTED)
    return label


def make_intro_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Primary intro copy for a settings page."""

    label = QLabel(text, parent)
    label.setObjectName("settings_page_intro")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setFocusPolicy(Qt.NoFocus)
    label.setAccessibleName("Page description")
    apply_text_style(label, UiTextRole.BODY)
    return label


def make_tab_scroll(
    page: QWidget,
    object_name: str,
    parent: QWidget | None = None,
) -> QScrollArea:
    """Scrollable tab body so long groups do not grow the Settings shell."""

    scroll = QScrollArea(parent)
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll


def add_buddy_row(
    form: QFormLayout,
    text: str,
    editor: QWidget,
    *,
    field: QWidget | None = None,
) -> QLabel:
    """Add a labeled editor row with buddy + accessibleName."""

    label = QLabel(text)
    label.setObjectName("settings_page_field_label")
    label.setBuddy(editor)
    apply_text_style(label, UiTextRole.LABEL)
    if not editor.accessibleName():
        editor.setAccessibleName(text)
    editor.setFocusPolicy(Qt.StrongFocus)
    form.addRow(label, field if field is not None else editor)
    return label


class FocusSpinBox(QSpinBox):
    """Integer editor that ignores wheel events until it has focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setKeyboardTracking(False)
        apply_ui_style(self, role=UiRole.NUMBER)

    def wheelEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FocusDoubleSpinBox(QDoubleSpinBox):
    """Number editor that ignores wheel events until it has focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setKeyboardTracking(False)
        apply_ui_style(self, role=UiRole.NUMBER)

    def wheelEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


def configure_int_editor(editor: QSpinBox, spec: SettingSpec) -> None:
    if spec.minimum is not None:
        editor.setMinimum(int(spec.minimum))
    if spec.maximum is not None:
        editor.setMaximum(int(spec.maximum))
    editor.setValue(int(spec.default))


def configure_number_editor(
    editor: QDoubleSpinBox,
    spec: SettingSpec,
    *,
    decimals: int,
    step: float,
    suffix: str,
) -> None:
    editor.setDecimals(decimals)
    editor.setSingleStep(step)
    if spec.minimum is not None:
        editor.setMinimum(float(spec.minimum))
    if spec.maximum is not None:
        editor.setMaximum(float(spec.maximum))
    editor.setValue(float(spec.default))
    if suffix:
        editor.setSuffix(suffix)


class SettingsPageWidget(QWidget):
    """Base page: draft values only. Shell owns session submit and footer."""

    valuesChanged = Signal(object)
    PAGE_ID = ""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session: Any | None = None,
        registry: SettingsRegistry | None = None,
        host: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._host = host
        self._registry = registry or production_settings_registry()
        self._loading = False
        self._staging = False
        self._buddy_labels: dict[str, QLabel] = {}
        self.setObjectName(f"settings_page_{self.PAGE_ID}")

    @classmethod
    def page_spec(cls) -> SettingsUiPageSpec:
        raise NotImplementedError

    def page_id(self) -> str:
        return str(self.PAGE_ID)

    def bind_session(self, session: Any | None) -> None:
        """Attach the shell's SettingsSession. Pages stage; they do not commit."""

        self._session = session

    def bind_host(self, host: Any | None) -> None:
        """Attach Agent A's SettingsPageHost when the shell constructs the page."""

        self._host = host
        if host is not None:
            bind = getattr(host, "bind_draft_reloaded", None)
            if callable(bind):
                bind(self._reload_from_host)

    def hosted_draft_keys(self) -> tuple[str, ...]:
        """Persisted keys this page reads from ``host.draft_values``."""

        return tuple(self.editors())

    def _reload_from_host(self, values: Mapping[str, Any] | None = None) -> None:
        host = self._host
        if host is None:
            return
        keys = self.hosted_draft_keys()
        payload = self._hosted_values(host, keys, values)
        self.load_values(payload, preview=False)

    def _hosted_values(
        self,
        host: Any,
        keys: tuple[str, ...],
        values: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if values is not None:
            return {key: values[key] for key in keys if key in values}
        draft_values = getattr(host, "draft_values", None)
        if callable(draft_values):
            try:
                return dict(draft_values(keys))
            except TypeError:
                pass
        return {key: host.draft_value(key) for key in keys}

    def _initial_values(self) -> Mapping[str, Any]:
        if self._host is not None:
            return self._hosted_values(self._host, self.hosted_draft_keys())
        return self._registry.defaults_for_page(self.PAGE_ID)

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
    ) -> None:
        raise NotImplementedError

    def apply_page_defaults(
        self,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        """Update editors from page defaults. Shell Restore uses this."""

        payload = (
            dict(defaults)
            if defaults is not None
            else dict(self._registry.defaults_for_page(self.PAGE_ID))
        )
        self.load_values(payload, preview=True)

    def draft_values(self) -> dict[str, Any]:
        raise NotImplementedError

    def editors(self) -> dict[str, QWidget]:
        raise NotImplementedError

    def buddy_labels(self) -> dict[str, QLabel]:
        return dict(self._buddy_labels)

    def keyboard_editors(self) -> tuple[QWidget, ...]:
        """Return every interactive editor that must be Tab-reachable."""

        return tuple(self.editors().values())

    def set_draft_value(self, key: str, raw: Any) -> Any:
        """Validate ``raw`` through the registry, then update the editor."""

        normalized = self._registry.spec(key).normalize(raw)
        self.load_values({**self.draft_values(), key: normalized}, preview=True)
        return normalized

    def _stage_and_emit(self, values: Mapping[str, Any]) -> None:
        if self._loading or self._staging:
            return
        self._staging = True
        try:
            if self._host is not None:
                stage_values = getattr(self._host, "stage_values", None)
                if callable(stage_values):
                    stage_values(values)
                else:
                    for key, value in values.items():
                        current = self._host.draft_value(key)
                        if current != value:
                            self._host.stage_value(key, value)
                self.valuesChanged.emit(dict(values))
                return
            if self._session is not None:
                stage_many = getattr(self._session, "stage_many", None)
                if callable(stage_many):
                    stage_many(values)
                else:
                    for key, value in values.items():
                        self._session.stage(key, value)
            self.valuesChanged.emit(dict(values))
        finally:
            self._staging = False
