"""Appearance settings page. LIVE_REVERSIBLE preview via ThemeService."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFormLayout,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.keys import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    PAGE_APPEARANCE,
)
from mygui.application_settings.models import Density, ThemeMode
from mygui.application_theme.models import AppearancePreferences, EffectiveScheme
from mygui.application_theme.system import (
    resolve_effective_scheme,
    scheme_from_palette,
)

from .page import (
    FocusSpinBox,
    SettingsPageWidget,
    add_buddy_row,
    configure_int_editor,
    make_hint_label,
    make_intro_label,
)

APPEARANCE_INTRO = (
    "Choose the workbench theme, UI font size, and density. Changes preview "
    "immediately. They do not change Matplotlib Figures, Artists, rcParams, "
    "or project colors."
)
APPEARANCE_THEME_HINT = (
    "System follows the operating-system color scheme. The label shows the "
    "effective Light or Dark result, for example System (Light)."
)

_THEME_CAPTIONS = {
    ThemeMode.LIGHT: "Light",
    ThemeMode.DARK: "Dark",
}
_DENSITY_CAPTIONS = {
    Density.COMPACT: "Compact",
    Density.STANDARD: "Standard",
    Density.COMFORTABLE: "Comfortable",
}


def _scheme_title(scheme: EffectiveScheme | str) -> str:
    value = getattr(scheme, "value", scheme)
    return str(value).capitalize()


def system_theme_caption(theme: Any | None = None) -> str:
    """Return ``System (Light)`` or ``System (Dark)`` from the effective scheme."""

    scheme: EffectiveScheme
    if theme is not None:
        scheme = theme.resolve_effective_scheme(ThemeMode.SYSTEM)
    else:
        app = QApplication.instance()
        if app is None:
            scheme = EffectiveScheme.LIGHT
        else:
            scheme = resolve_effective_scheme(
                ThemeMode.SYSTEM,
                app.styleHints().colorScheme(),
                scheme_from_palette(app.palette()),
            )
    return f"System ({_scheme_title(scheme)})"


class AppearanceSettingsPage(SettingsPageWidget):
    """Theme, UI font size, and density. Preview is live and reversible."""

    PAGE_ID = PAGE_APPEARANCE

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        session: Any | None = None,
        registry: Any | None = None,
        theme: Any | None = None,
        host: Any | None = None,
    ) -> None:
        super().__init__(parent, session=session, registry=registry, host=host)
        self._theme = theme
        self._scheme_connection = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if host is None:
            root.addWidget(make_intro_label(APPEARANCE_INTRO, self))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        theme_box = QWidget(self)
        theme_row = QHBoxLayout(theme_box)
        theme_row.setContentsMargins(0, 0, 0, 0)
        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self._theme_radios: dict[ThemeMode, QRadioButton] = {}
        self.system_radio = self._add_theme_radio(
            theme_row, ThemeMode.SYSTEM, system_theme_caption(theme)
        )
        self.light_radio = self._add_theme_radio(
            theme_row, ThemeMode.LIGHT, _THEME_CAPTIONS[ThemeMode.LIGHT]
        )
        self.dark_radio = self._add_theme_radio(
            theme_row, ThemeMode.DARK, _THEME_CAPTIONS[ThemeMode.DARK]
        )
        theme_label = add_buddy_row(
            form,
            self._registry.spec(APPEARANCE_THEME_MODE).label or "Theme",
            self.system_radio,
            field=theme_box,
        )
        self._buddy_labels[APPEARANCE_THEME_MODE] = theme_label

        font_spec = self._registry.spec(APPEARANCE_UI_FONT_POINT_SIZE)
        self.font_spin = FocusSpinBox(self)
        self.font_spin.setObjectName("appearance_font_spin")
        configure_int_editor(self.font_spin, font_spec)
        self.font_spin.setSuffix(" pt")
        font_label = add_buddy_row(
            form,
            font_spec.label or "UI font size",
            self.font_spin,
        )
        self._buddy_labels[APPEARANCE_UI_FONT_POINT_SIZE] = font_label

        density_box = QWidget(self)
        density_row = QHBoxLayout(density_box)
        density_row.setContentsMargins(0, 0, 0, 0)
        self.density_group = QButtonGroup(self)
        self.density_group.setExclusive(True)
        self._density_radios: dict[Density, QRadioButton] = {}
        self.compact_radio = self._add_density_radio(
            density_row, Density.COMPACT, _DENSITY_CAPTIONS[Density.COMPACT]
        )
        self.standard_radio = self._add_density_radio(
            density_row, Density.STANDARD, _DENSITY_CAPTIONS[Density.STANDARD]
        )
        self.comfortable_radio = self._add_density_radio(
            density_row, Density.COMFORTABLE, _DENSITY_CAPTIONS[Density.COMFORTABLE]
        )
        density_spec = self._registry.spec(APPEARANCE_DENSITY)
        density_label = add_buddy_row(
            form,
            density_spec.label or "Density",
            self.compact_radio,
            field=density_box,
        )
        self._buddy_labels[APPEARANCE_DENSITY] = density_label

        root.addLayout(form)
        root.addWidget(make_hint_label(APPEARANCE_THEME_HINT, self))
        root.addStretch(1)

        self.theme_group.buttonClicked.connect(self._on_appearance_changed)
        self.density_group.buttonClicked.connect(self._on_appearance_changed)
        self.font_spin.valueChanged.connect(self._on_appearance_changed)
        QWidget.setTabOrder(self.system_radio, self.light_radio)
        QWidget.setTabOrder(self.light_radio, self.dark_radio)
        QWidget.setTabOrder(self.dark_radio, self.font_spin)
        QWidget.setTabOrder(self.font_spin, self.compact_radio)
        QWidget.setTabOrder(self.compact_radio, self.standard_radio)
        QWidget.setTabOrder(self.standard_radio, self.comfortable_radio)

        self._connect_scheme_listener()
        self.bind_host(host)
        self.load_values(self._initial_values())

    @classmethod
    def page_spec(cls):
        return page_spec(cls.make_factory())

    @classmethod
    def make_factory(cls):
        def factory(host: Any) -> AppearanceSettingsPage:
            theme = getattr(host, "theme_service", None)
            return cls(host=host, theme=theme)

        return factory

    def bind_theme(self, theme: Any | None) -> None:
        """Inject ThemeService for live preview and System effective labels."""

        self._disconnect_scheme_listener()
        self._theme = theme
        self._connect_scheme_listener()
        self._refresh_system_caption()

    def editors(self) -> dict[str, QWidget]:
        return {
            APPEARANCE_THEME_MODE: self.system_radio,
            APPEARANCE_UI_FONT_POINT_SIZE: self.font_spin,
            APPEARANCE_DENSITY: self.compact_radio,
        }

    def keyboard_editors(self) -> tuple[QWidget, ...]:
        return (
            self.system_radio,
            self.light_radio,
            self.dark_radio,
            self.font_spin,
            self.compact_radio,
            self.standard_radio,
            self.comfortable_radio,
        )

    def draft_values(self) -> dict[str, Any]:
        return {
            APPEARANCE_THEME_MODE: self._current_theme_mode(),
            APPEARANCE_UI_FONT_POINT_SIZE: int(self.font_spin.value()),
            APPEARANCE_DENSITY: self._current_density(),
        }

    def load_values(
        self,
        values: Mapping[str, Any],
        *,
        preview: bool = False,
    ) -> None:
        self._loading = True
        try:
            if APPEARANCE_THEME_MODE in values:
                mode = self._registry.spec(APPEARANCE_THEME_MODE).normalize(
                    values[APPEARANCE_THEME_MODE]
                )
                self._theme_radios[mode].setChecked(True)
            if APPEARANCE_UI_FONT_POINT_SIZE in values:
                font_pt = self._registry.spec(APPEARANCE_UI_FONT_POINT_SIZE).normalize(
                    values[APPEARANCE_UI_FONT_POINT_SIZE]
                )
                self.font_spin.setValue(int(font_pt))
            if APPEARANCE_DENSITY in values:
                density = self._registry.spec(APPEARANCE_DENSITY).normalize(
                    values[APPEARANCE_DENSITY]
                )
                self._density_radios[density].setChecked(True)
            self._refresh_system_caption()
        finally:
            self._loading = False
        if preview:
            self._on_appearance_changed()

    def _add_theme_radio(
        self,
        layout: QHBoxLayout,
        mode: ThemeMode,
        caption: str,
    ) -> QRadioButton:
        radio = QRadioButton(caption)
        radio.setObjectName(f"appearance_theme_{mode.value}")
        radio.setFocusPolicy(Qt.StrongFocus)
        radio.setAccessibleName(caption)
        self.theme_group.addButton(radio)
        self._theme_radios[mode] = radio
        layout.addWidget(radio)
        return radio

    def _add_density_radio(
        self,
        layout: QHBoxLayout,
        density: Density,
        caption: str,
    ) -> QRadioButton:
        radio = QRadioButton(caption)
        radio.setObjectName(f"appearance_density_{density.value}")
        radio.setFocusPolicy(Qt.StrongFocus)
        radio.setAccessibleName(caption)
        self.density_group.addButton(radio)
        self._density_radios[density] = radio
        layout.addWidget(radio)
        return radio

    def _current_theme_mode(self) -> ThemeMode:
        for mode, radio in self._theme_radios.items():
            if radio.isChecked():
                return mode
        return ThemeMode.SYSTEM

    def _current_density(self) -> Density:
        for density, radio in self._density_radios.items():
            if radio.isChecked():
                return density
        return Density.STANDARD

    def _refresh_system_caption(self) -> None:
        caption = system_theme_caption(self._theme)
        self.system_radio.setText(caption)
        self.system_radio.setAccessibleName(caption)

    def _on_appearance_changed(self, *_args: object) -> None:
        if self._loading or self._staging:
            return
        values = self.draft_values()
        self._stage_and_emit(values)
        if self._host is None:
            self._preview_appearance(values)

    def _preview_appearance(self, values: Mapping[str, Any]) -> None:
        if self._theme is None:
            return
        preview = getattr(self._theme, "preview", None)
        if not callable(preview):
            return
        preview(
            AppearancePreferences(
                mode=values[APPEARANCE_THEME_MODE],
                font_pt=int(values[APPEARANCE_UI_FONT_POINT_SIZE]),
                density=values[APPEARANCE_DENSITY],
            )
        )

    def _connect_scheme_listener(self) -> None:
        hints = None
        if self._theme is not None:
            hints = getattr(self._theme, "_hints", None)
        if hints is None:
            app = QApplication.instance()
            if app is not None:
                hints = app.styleHints()
        changed = getattr(hints, "colorSchemeChanged", None) if hints is not None else None
        if changed is None:
            return
        self._scheme_connection = changed.connect(self._on_system_scheme_changed)

    def _disconnect_scheme_listener(self) -> None:
        connection = self._scheme_connection
        self._scheme_connection = None
        if connection is None or isinstance(connection, bool):
            return
        try:
            from PySide6.QtCore import QObject

            QObject.disconnect(connection)
        except (RuntimeError, TypeError):
            return

    def _on_system_scheme_changed(self, *_args: object) -> None:
        self._refresh_system_caption()


def make_appearance_factory():
    return AppearanceSettingsPage.make_factory()


def page_spec(factory=None):
    """Shell registration spec for the Appearance page."""

    from mygui.widgets.settings_center.pages import standard_page_spec

    return standard_page_spec(
        PAGE_APPEARANCE,
        factory if factory is not None else make_appearance_factory(),
        description=APPEARANCE_INTRO,
    )
