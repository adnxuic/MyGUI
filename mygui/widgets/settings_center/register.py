"""Register Export, Integrations, and Maintenance with Agent A's Settings Center.

Call ``register_c_pages(settings_host, color_library=...)``. Factories receive
``SettingsPageHost``. Integrator must pass ``on_open_tex_panel`` /
``on_open_matlab_panel`` (or connect the page signals) so MainWindow opens the
existing right-rail panels without remounting those widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mygui.application_settings.service import ApplicationSettingsService
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center.export_page import ExportSettingsPage
from mygui.widgets.settings_center.integrations_page import IntegrationsSettingsPage
from mygui.widgets.settings_center.integrations_status import IntegrationStatus
from mygui.widgets.settings_center.maintenance_page import MaintenanceSettingsPage
from mygui.widgets.settings_center.pages import SettingsPageHost
from mygui.widgets.settings_center.specs import page_specs


def make_export_factory(
    color_library: ColorLibrary,
    *,
    service: ApplicationSettingsService | None = None,
    document_dpi: float = 100.0,
    width_inches: float = 6.4,
    height_inches: float = 4.8,
) -> Callable[[SettingsPageHost], ExportSettingsPage]:
    """Return a ``SettingsPageHost`` factory for the Export page."""

    def factory(host: SettingsPageHost) -> ExportSettingsPage:
        width = width_inches
        height = height_inches
        dpi = document_dpi
        if service is not None:
            new_figure = service.snapshot().new_figure
            width = float(new_figure.width_in)
            height = float(new_figure.height_in)
            dpi = float(new_figure.document_dpi)
        return ExportSettingsPage(
            color_library,
            host=host,
            document_dpi=dpi,
            width_inches=width,
            height_inches=height,
        )

    return factory


def make_integrations_factory(
    *,
    tex_status: Callable[[], IntegrationStatus] | IntegrationStatus | None = None,
    matlab_status: Callable[[], IntegrationStatus] | IntegrationStatus | None = None,
    on_open_tex_panel: Callable[[], None] | None = None,
    on_open_matlab_panel: Callable[[], None] | None = None,
) -> Callable[[SettingsPageHost], IntegrationsSettingsPage]:
    """Return a factory that never remounts TeX/MATLAB widgets."""

    def factory(host: SettingsPageHost) -> IntegrationsSettingsPage:
        page = IntegrationsSettingsPage(
            host=host,
            tex_status=tex_status,
            matlab_status=matlab_status,
        )
        if on_open_tex_panel is not None:
            page.openTexPanelRequested.connect(on_open_tex_panel)
        if on_open_matlab_panel is not None:
            page.openMatlabPanelRequested.connect(on_open_matlab_panel)
        return page

    return factory


def make_maintenance_factory(
    *,
    service: ApplicationSettingsService | None = None,
    backend: Any | None = None,
    color_library: ColorLibrary | None = None,
    confirm: Callable[[str, str], bool] | None = None,
) -> Callable[[SettingsPageHost], MaintenanceSettingsPage]:
    """Return a factory for dual-slot health and confirmed commands."""

    def factory(host: SettingsPageHost) -> MaintenanceSettingsPage:
        return MaintenanceSettingsPage(
            host=host,
            service=service,
            backend=backend,
            color_library=color_library,
            confirm=confirm,
        )

    return factory


def register_c_pages(
    center: Any,
    *,
    color_library: ColorLibrary,
    service: ApplicationSettingsService | None = None,
    backend: Any | None = None,
    document_dpi: float = 100.0,
    width_inches: float = 6.4,
    height_inches: float = 4.8,
    tex_status: Callable[[], IntegrationStatus] | IntegrationStatus | None = None,
    matlab_status: Callable[[], IntegrationStatus] | IntegrationStatus | None = None,
    on_open_tex_panel: Callable[[], None] | None = None,
    on_open_matlab_panel: Callable[[], None] | None = None,
    confirm: Callable[[str, str], bool] | None = None,
) -> list[Any]:
    """Register the three C pages when ``center.register_page`` exists.

    Returns the specs passed to the shell. Returns an empty list when the
    shell has not published ``register_page``.
    """

    register = getattr(center, "register_page", None)
    if not callable(register):
        return []
    specs = page_specs(
        export_factory=make_export_factory(
            color_library,
            service=service,
            document_dpi=document_dpi,
            width_inches=width_inches,
            height_inches=height_inches,
        ),
        integrations_factory=make_integrations_factory(
            tex_status=tex_status,
            matlab_status=matlab_status,
            on_open_tex_panel=on_open_tex_panel,
            on_open_matlab_panel=on_open_matlab_panel,
        ),
        maintenance_factory=make_maintenance_factory(
            service=service,
            backend=backend,
            color_library=color_library,
            confirm=confirm,
        ),
    )
    for spec in specs:
        register(spec)
    return list(specs)
