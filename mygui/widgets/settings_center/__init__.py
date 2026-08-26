"""Settings Center shell: cached modal window, page registry, and session glue.

Integrator holds :class:`SettingsCenterHost`, registers B/C pages with
:meth:`SettingsCenterHost.register_page`, and opens the window from the gear
or Settings ``QAction``. Appearance/Workspace/New Figure forms belong to B;
Export/Integrations/Maintenance belong to C.
"""

from .geometry import (
    INITIAL_HEIGHT,
    INITIAL_WIDTH,
    MINIMUM_HEIGHT,
    MINIMUM_WIDTH,
    NAV_PANE_WIDTH,
    SCREEN_FRACTION,
    constrain_to_available,
)
from .host import SettingsCenterHost
from .pages import (
    PAGE_INTEGRATIONS,
    PAGE_MAINTENANCE,
    SHELL_PAGE_METADATA,
    SHELL_PAGE_ORDER,
    SettingsCenterPageSpec,
    SettingsPageHost,
    SettingsPageRegistry,
    standard_page_spec,
)
from .export_page import EXPORT_DPI_STRATEGY_HINT, ExportSettingsPage
from .integrations_page import IntegrationsSettingsPage
from .integrations_status import (
    IntegrationStatus,
    matlab_integration_status,
    tex_integration_status,
)
from .maintenance_page import MaintenanceSettingsPage
from .compose import compose_settings_center, register_all_pages
from .register import register_c_pages
from .specs import (
    export_page_spec,
    integrations_page_spec,
    maintenance_page_spec,
    page_specs,
)
from .session_glue import SettingsCenterSession
from .window import SETTINGS_CENTER_QSS_RESOURCE, SettingsCenterWindow

NAV_WIDTH = NAV_PANE_WIDTH

__all__ = [
    "INITIAL_HEIGHT",
    "INITIAL_WIDTH",
    "MINIMUM_HEIGHT",
    "MINIMUM_WIDTH",
    "NAV_PANE_WIDTH",
    "NAV_WIDTH",
    "PAGE_INTEGRATIONS",
    "PAGE_MAINTENANCE",
    "SCREEN_FRACTION",
    "SETTINGS_CENTER_QSS_RESOURCE",
    "SHELL_PAGE_METADATA",
    "SHELL_PAGE_ORDER",
    "SettingsCenterHost",
    "SettingsCenterPageSpec",
    "SettingsCenterSession",
    "SettingsCenterWindow",
    "SettingsPageHost",
    "SettingsPageRegistry",
    "constrain_to_available",
    "export_page_spec",
    "integrations_page_spec",
    "maintenance_page_spec",
    "matlab_integration_status",
    "page_specs",
    "compose_settings_center",
    "register_all_pages",
    "register_c_pages",
    "standard_page_spec",
    "tex_integration_status",
    "EXPORT_DPI_STRATEGY_HINT",
    "ExportSettingsPage",
    "IntegrationStatus",
    "IntegrationsSettingsPage",
    "MaintenanceSettingsPage",
]
