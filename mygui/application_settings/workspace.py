"""Bind MainWindow to the workspace-layout port without a second preference store.

Immediate reset and close-save go through ``WorkspaceLayoutPort.save_layout``.
They are not Settings Center Apply drafts. Figure Controllers do not receive
this port or ``ApplicationSettingsService``.
"""

from __future__ import annotations

from typing import Any

from .ports import (
    ServiceWorkspaceLayoutPort,
    SettingsDocumentPort,
    WorkspaceLayoutPort,
)
from .service import ApplicationSettingsService


def commit_succeeded(result: Any) -> bool:
    """Return whether a settings or storage commit proved durable."""

    if result is None:
        return False
    ok = getattr(result, "ok", None)
    if ok is None:
        ok = getattr(result, "success", False)
    return bool(ok)


def bind_workspace_layout_port(
    *,
    settings: Any = None,
    settings_service: Any = None,
    workspace_layout_port: WorkspaceLayoutPort | None = None,
) -> tuple[ApplicationSettingsService | None, WorkspaceLayoutPort | None]:
    """Resolve the workspace port from an injected service, document, or QSettings.

    Preference order: explicit port, ``ApplicationSettingsService``, document
    port (``load`` / ``commit``), then an injected ``QSettings`` wrapped with
    ``create_settings_backend``. Callers must not ``setValue`` ``workspaceLayout``.
    """

    service = _as_settings_service(settings_service)
    if workspace_layout_port is not None:
        return service, workspace_layout_port
    if service is not None:
        return service, ServiceWorkspaceLayoutPort(service)
    if _is_qsettings(settings):
        from mygui.application_settings.storage import create_settings_backend

        backend = create_settings_backend(settings=settings)
        service = ApplicationSettingsService(
            document=backend.application_settings_port()
        )
        return service, ServiceWorkspaceLayoutPort(service)
    return None, None


def _as_settings_service(value: Any) -> ApplicationSettingsService | None:
    if value is None:
        return None
    if isinstance(value, ApplicationSettingsService):
        return value
    if _is_settings_service(value):
        return value
    if _is_document_port(value):
        return ApplicationSettingsService(document=value)
    return None


def _is_settings_service(value: Any) -> bool:
    return (
        hasattr(value, "snapshot")
        and hasattr(value, "begin_session")
        and hasattr(value, "commit_patch")
    )


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
