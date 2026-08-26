"""Bind export consumers to ``ExportPreferencesPort`` without the full service.

The composition root should inject
``ApplicationSettingsService.export_preferences_port()``. Wrapping an injected
``QSettings`` here is a transition helper for callers that still pass the
shared store; it must not ``setValue`` ``figureExport``.
"""

from __future__ import annotations

from typing import Any

from .ports import (
    ExportPreferencesPort,
    MemoryExportPreferences,
    SettingsDocumentPort,
)
from .service import ApplicationSettingsService


def bind_export_preferences_port(
    *,
    settings: Any = None,
    settings_service: Any = None,
    export_preferences: ExportPreferencesPort | None = None,
) -> ExportPreferencesPort:
    """Resolve the export port from an explicit port, service, document, or QSettings."""

    if export_preferences is not None:
        return export_preferences
    service = _as_settings_service(settings_service)
    if service is None:
        service = _as_settings_service(settings)
    if service is not None:
        return service.export_preferences_port()
    if _is_qsettings(settings):
        from mygui.application_settings.storage import create_settings_backend

        backend = create_settings_backend(settings=settings)
        service = ApplicationSettingsService(
            document=backend.application_settings_port()
        )
        return service.export_preferences_port()
    return MemoryExportPreferences()


def _as_settings_service(value: Any) -> ApplicationSettingsService | None:
    if value is None:
        return None
    if isinstance(value, ApplicationSettingsService):
        return value
    if (
        hasattr(value, "snapshot")
        and hasattr(value, "begin_session")
        and hasattr(value, "commit_patch")
        and hasattr(value, "export_preferences_port")
    ):
        return value
    if _is_document_port(value):
        return ApplicationSettingsService(document=value)
    return None


def _is_document_port(value: Any) -> bool:
    if isinstance(value, SettingsDocumentPort):
        return True
    return hasattr(value, "load") and hasattr(value, "commit")


def _is_qsettings(value: Any) -> bool:
    return (
        value is not None
        and hasattr(value, "setValue")
        and hasattr(value, "value")
        and hasattr(value, "sync")
        and hasattr(value, "beginGroup")
    )
