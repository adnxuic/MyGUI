"""Single QSettings backend that exposes two isolated document ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

from mygui.application_settings.storage.dual_slot import DualSlotDocumentPort
from mygui.application_settings.storage.keys import (
    APPLICATION_SETTINGS_GROUP,
    COLOR_LIBRARY_SETTINGS_GROUP,
    SCHEMA_APPLICATION_SETTINGS,
    SCHEMA_COLOR_LIBRARY_SETTINGS,
)
from mygui.application_settings.storage.migrators import (
    clear_legacy_keys,
    default_application_settings_payload,
    default_color_library_payload,
    migrate_application_settings,
    migrate_color_library_settings,
)
from mygui.application_settings.storage.types import StorageCommitResult


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    """Identity used to open a fresh QSettings reader for the same store."""

    file_name: str
    format: QSettings.Format
    scope: QSettings.Scope
    organization: str
    application: str

    def open(self) -> QSettings:
        """Open a new QSettings object that is not the writer cache."""

        if self.format == QSettings.Format.IniFormat and self.file_name:
            return QSettings(self.file_name, QSettings.Format.IniFormat)
        if self.organization and self.application:
            return QSettings(
                self.format,
                self.scope,
                self.organization,
                self.application,
            )
        raise RuntimeError(
            "Settings backend is missing a file path or organization identity"
        )


class SettingsBackend:
    """Own one QSettings instance and the two dual-slot document ports."""

    def __init__(
        self,
        store: QSettings,
        *,
        identity: BackendIdentity | None = None,
        reader_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._store = store
        self._identity = identity or _identity_from_settings(store)
        self._reader_factory = reader_factory
        self._writes_forbidden = False
        self._application_port: DualSlotDocumentPort | None = None
        self._color_port: DualSlotDocumentPort | None = None

    @property
    def store(self) -> QSettings:
        """Return the injected writer QSettings."""

        return self._store

    @property
    def writes_forbidden(self) -> bool:
        """Return whether this process must not write this backend again."""

        return self._writes_forbidden

    def mark_writes_forbidden(self) -> None:
        """Forbid further commits after an uncertain write."""

        self._writes_forbidden = True

    def create_fresh_reader(self) -> QSettings:
        """Create a new QSettings reader for the same organization/file."""

        if self._reader_factory is not None:
            return self._reader_factory()
        return self._identity.open()

    def application_settings_port(self) -> DualSlotDocumentPort:
        """Return the application-settings dual-slot port."""

        if self._application_port is None:
            self._application_port = DualSlotDocumentPort(
                self._store,
                open_reader=self.create_fresh_reader,
                group=APPLICATION_SETTINGS_GROUP,
                schema=SCHEMA_APPLICATION_SETTINGS,
                migrator=migrate_application_settings,
                is_writes_forbidden=lambda: self._writes_forbidden,
                mark_writes_forbidden=self.mark_writes_forbidden,
            )
        return self._application_port

    def clear_writes_forbidden(self) -> None:
        """Allow commits again after an explicit incompatible-storage reset."""

        self._writes_forbidden = False

    def reset_incompatible_documents(self) -> StorageCommitResult:
        """Clear application dual-slot keys and legacy groups, then restore writes.

        Color-library dual-slot data is left intact. This is an immediate
        recovery command, not a Settings Apply draft.
        """

        application = self.application_settings_port()
        application.clear_slots()
        clear_legacy_keys(self._store)
        self.clear_writes_forbidden()
        payload = default_application_settings_payload(migrated=False)
        return application.commit(payload)

    def reset_color_library_document(self) -> StorageCommitResult:
        """Clear only the color dual-slot document, then restore writable defaults.

        Application settings slots are left intact. Recovery use only.
        """

        color = self.color_library_settings_port()
        color.clear_slots()
        return color.commit(default_color_library_payload())

    def color_library_settings_port(self) -> DualSlotDocumentPort:
        """Return the color-library dual-slot port."""

        if self._color_port is None:
            self._color_port = DualSlotDocumentPort(
                self._store,
                open_reader=self.create_fresh_reader,
                group=COLOR_LIBRARY_SETTINGS_GROUP,
                schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
                migrator=migrate_color_library_settings,
                is_writes_forbidden=lambda: self._writes_forbidden,
                mark_writes_forbidden=self.mark_writes_forbidden,
            )
        return self._color_port


def create_settings_backend(
    settings: QSettings | None = None,
    *,
    file_path: str | Path | None = None,
    organization: str | None = None,
    application: str | None = None,
    format: QSettings.Format | None = None,
    scope: QSettings.Scope | None = None,
    reader_factory: Callable[[], Any] | None = None,
) -> SettingsBackend:
    """Create one QSettings backend. Never constructs a no-argument QSettings()."""

    store: QSettings
    if settings is not None:
        store = settings
    elif file_path is not None:
        chosen_format = format if format is not None else QSettings.Format.IniFormat
        store = QSettings(str(file_path), chosen_format)
    elif organization and application:
        if format is not None:
            chosen_scope = scope if scope is not None else QSettings.Scope.UserScope
            store = QSettings(format, chosen_scope, organization, application)
        else:
            store = QSettings(organization, application)
    else:
        raise ValueError(
            "create_settings_backend requires an injected QSettings, a file_path, "
            "or organization and application names"
        )
    identity = _identity_from_settings(
        store,
        organization=organization,
        application=application,
        format=format,
        scope=scope,
        file_path=file_path,
    )
    return SettingsBackend(
        store,
        identity=identity,
        reader_factory=reader_factory,
    )


def _identity_from_settings(
    store: QSettings,
    *,
    organization: str | None = None,
    application: str | None = None,
    format: QSettings.Format | None = None,
    scope: QSettings.Scope | None = None,
    file_path: str | Path | None = None,
) -> BackendIdentity:
    file_name = str(file_path) if file_path is not None else ""
    if not file_name:
        try:
            file_name = str(store.fileName() or "")
        except Exception:
            file_name = ""
    try:
        chosen_format = format if format is not None else store.format()
    except Exception:
        chosen_format = QSettings.Format.IniFormat
    try:
        chosen_scope = scope if scope is not None else store.scope()
    except Exception:
        chosen_scope = QSettings.Scope.UserScope
    try:
        org = organization if organization is not None else str(store.organizationName() or "")
    except Exception:
        org = organization or ""
    try:
        app = application if application is not None else str(store.applicationName() or "")
    except Exception:
        app = application or ""
    return BackendIdentity(
        file_name=file_name,
        format=chosen_format,
        scope=chosen_scope,
        organization=org,
        application=app,
    )
