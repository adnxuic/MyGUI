"""Compose the production Settings Center host and register all six pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QWidget

from mygui.application_settings.service import ApplicationSettingsService
from mygui.application_theme.service import ThemeService
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.host import SettingsCenterHost
from mygui.widgets.settings_center.register import register_c_pages
from mygui.widgets.settings_center.session_glue import MessageCallback
from mygui.widgets.settings_pages import register_b_pages


def register_all_pages(
    center: Any,
    *,
    color_library: ColorLibrary,
    service: ApplicationSettingsService | None = None,
    backend: Any | None = None,
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
    tex_status: Any | None = None,
    matlab_status: Any | None = None,
    on_open_tex_panel: Callable[[], None] | None = None,
    on_open_matlab_panel: Callable[[], None] | None = None,
    confirm: Callable[[str, str], bool] | None = None,
) -> list[Any]:
    """Register Appearance through Maintenance in navigation order."""

    specs: list[Any] = []
    specs.extend(
        register_b_pages(
            center,
            reset_layout_now=reset_layout_now,
            layout_port=layout_port,
        )
    )
    specs.extend(
        register_c_pages(
            center,
            color_library=color_library,
            service=service,
            backend=backend,
            tex_status=tex_status,
            matlab_status=matlab_status,
            on_open_tex_panel=on_open_tex_panel,
            on_open_matlab_panel=on_open_matlab_panel,
            confirm=confirm,
        )
    )
    return specs


def compose_settings_center(
    parent: QWidget | None,
    *,
    settings_service: ApplicationSettingsService,
    theme_service: ThemeService,
    color_library: ColorLibrary,
    backend: Any | None = None,
    reset_layout_now: Callable[[], Any] | None = None,
    layout_port: Any | None = None,
    on_message: MessageCallback | None = None,
    on_open_tex_panel: Callable[[], None] | None = None,
    on_open_matlab_panel: Callable[[], None] | None = None,
) -> SettingsCenterHost:
    """Build the lazy Settings Center host with all six production pages."""

    host = SettingsCenterHost(
        parent,
        settings_service,
        theme_service,
        on_message=on_message,
    )
    register_all_pages(
        host,
        color_library=color_library,
        service=settings_service,
        backend=backend,
        reset_layout_now=reset_layout_now,
        layout_port=layout_port,
        on_open_tex_panel=on_open_tex_panel,
        on_open_matlab_panel=on_open_matlab_panel,
    )
    return host
