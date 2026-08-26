"""Lazy single-instance Settings Center cache for Integrator QAction wiring."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from mygui.application_settings.registry import SettingsRegistry, production_settings_registry
from mygui.application_settings.service import ApplicationSettingsService
from mygui.application_theme.service import ThemeService

from .geometry import AvailableGeometryProvider
from .pages import SettingsCenterPageSpec, SettingsPageRegistry
from .session_glue import MessageCallback
from .window import ImmediateConfirm, SettingsCenterWindow


class SettingsCenterHost:
    """Lazy-create and reuse one modal Settings Center window.

    Integrator holds this on MainWindow, registers B/C pages, and connects
    the gear / Settings QAction to :meth:`open`.
    """

    def __init__(
        self,
        parent: QWidget | None,
        settings_service: ApplicationSettingsService,
        theme_service: ThemeService,
        *,
        page_registry: SettingsPageRegistry | None = None,
        settings_registry: SettingsRegistry | None = None,
        on_message: MessageCallback | None = None,
        available_geometry: AvailableGeometryProvider | None = None,
        confirm_immediate: ImmediateConfirm | None = None,
    ) -> None:
        self._parent = parent
        self._settings_service = settings_service
        self._theme_service = theme_service
        self._pages = page_registry if page_registry is not None else SettingsPageRegistry()
        self._settings_registry = settings_registry or production_settings_registry()
        self._on_message = on_message
        self._geometry_provider = available_geometry
        self._confirm_immediate = confirm_immediate
        self._window: SettingsCenterWindow | None = None

    @property
    def pages(self) -> SettingsPageRegistry:
        return self._pages

    @property
    def window(self) -> SettingsCenterWindow | None:
        return self._alive_window()

    def register_page(self, spec: SettingsCenterPageSpec) -> None:
        """Register or replace a page. Safe to call before the first open."""

        self._pages.register_page(spec)
        window = self._alive_window()
        if window is not None:
            window.on_pages_changed()

    def ensure_window(self) -> SettingsCenterWindow:
        """Create the cached window on first use."""

        window = self._alive_window()
        if window is not None:
            return window
        window = SettingsCenterWindow(
            self._parent,
            settings_service=self._settings_service,
            theme_service=self._theme_service,
            page_registry=self._pages,
            settings_registry=self._settings_registry,
            on_message=self._on_message,
            available_geometry=self._geometry_provider,
            confirm_immediate=self._confirm_immediate,
        )
        self._window = window
        window.destroyed.connect(self._forget_window)
        return window

    def present(self, page_id: str | None = None) -> SettingsCenterWindow:
        """Non-blocking show. Tests use this instead of :meth:`open`."""

        window = self.ensure_window()
        window.prepare_session(page_id=page_id)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def open(self, page_id: str | None = None) -> int:
        """Blocking modal ``exec``. Wire Integrator QAction.triggered here."""

        window = self.ensure_window()
        if window.isVisible():
            window.prepare_session(page_id=page_id)
            window.raise_()
            window.activateWindow()
            return int(window.result())
        window.prepare_session(page_id=page_id)
        return int(window.exec())

    def _forget_window(self, *_args: object) -> None:
        self._window = None

    def _alive_window(self) -> SettingsCenterWindow | None:
        window = self._window
        if window is None:
            return None
        try:
            window.objectName()
        except RuntimeError:
            self._window = None
            return None
        return window
