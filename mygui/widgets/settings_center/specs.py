"""Settings Center page specs for Export, Integrations, and Maintenance."""

from __future__ import annotations

from mygui.application_settings.keys import PAGE_EXPORT, PAGE_INTEGRATIONS, PAGE_MAINTENANCE
from mygui.widgets.settings_center.pages import (
    PageFactory,
    SettingsCenterPageSpec,
    standard_page_spec,
)


def export_page_spec(factory: PageFactory | None = None) -> SettingsCenterPageSpec:
    """Return the Export page spec for ``SettingsCenterHost.register_page``."""

    return standard_page_spec(PAGE_EXPORT, factory)


def integrations_page_spec(factory: PageFactory | None = None) -> SettingsCenterPageSpec:
    """Return the read-only Integrations page spec. No persisted keys."""

    return standard_page_spec(PAGE_INTEGRATIONS, factory)


def maintenance_page_spec(factory: PageFactory | None = None) -> SettingsCenterPageSpec:
    """Return the Maintenance page spec. Immediate commands are not Apply keys."""

    return standard_page_spec(
        PAGE_MAINTENANCE,
        factory,
        keywords=(
            "Reset all application preferences",
            "Reset incompatible storage",
            "Clear recent colors",
            "Reset color library",
            "Reset color library storage",
            "Recovery",
            "Write uncertain",
            "Read-only future",
        ),
    )


def page_specs(
    *,
    export_factory: PageFactory | None = None,
    integrations_factory: PageFactory | None = None,
    maintenance_factory: PageFactory | None = None,
) -> tuple[SettingsCenterPageSpec, ...]:
    """Return Export, Integrations, and Maintenance specs in display order."""

    return (
        export_page_spec(export_factory),
        integrations_page_spec(integrations_factory),
        maintenance_page_spec(maintenance_factory),
    )
