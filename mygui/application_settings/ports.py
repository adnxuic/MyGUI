"""Narrow ports for settings storage and later-phase consumers.

Storage implementations live in ``mygui.application_settings.storage`` (SubAgent
A / Integrator). This module only declares the protocol the service depends on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .keys import WORKSPACE_LAYOUT
from .models import (
    DEFAULT_WORKSPACE_LAYOUT,
    ComponentDefaultsSettings,
    ExportSettings,
    NewFigureSettings,
    SettingsCommitResult,
    SettingsHealth,
    WorkspaceLayoutPayload,
)


@dataclass(frozen=True, slots=True)
class ServiceDocumentLoadResult:
    """In-memory load result used by tests. Not the dual-slot storage type."""

    payload: Mapping[str, Any] | None = None
    missing: bool = False
    recovered: bool = False
    warning: str | None = None
    error: str | None = None
    health: SettingsHealth = SettingsHealth.OK


@dataclass(frozen=True, slots=True)
class ServiceStorageCommitResult:
    """Normalized commit result used by the service. Not the dual-slot type."""

    success: bool
    error: str | None = None
    warning: str | None = None


@runtime_checkable
class SettingsDocumentPort(Protocol):
    """Load and commit the application-settings document.

    Implementations may return this module's service result types or the
    dual-slot types in ``mygui.application_settings.storage``. The service
    duck-types ``payload`` / ``revision`` on load and ``ok`` or ``success``
    on commit. This module does not implement QSettings dual-slot storage.
    """

    def load(self) -> Any:
        """Return the stored payload, or a missing/empty document for a fresh install."""

    def commit(self, payload: Mapping[str, Any]) -> Any:
        """Replace the stored document with a JSON-safe nested payload."""


@runtime_checkable
class NewFigureDefaultsProvider(Protocol):
    """Narrow read port for Style creation/import. Not the full settings service."""

    def current(self) -> NewFigureSettings:
        """Return the application New Figure defaults."""


@runtime_checkable
class ComponentDefaultsProvider(Protocol):
    """Narrow read port for component creation defaults. Not the settings service."""

    def current(self) -> ComponentDefaultsSettings:
        """Return the application Components defaults."""


@runtime_checkable
class ExportPreferencesPort(Protocol):
    """Narrow export-preference port. Not the full settings service."""

    def current(self) -> ExportSettings:
        """Return the application export preferences."""

    def commit(self, settings: ExportSettings) -> Any:
        """Persist export preferences after a successful export or Settings Apply."""


@runtime_checkable
class WorkspaceLayoutPort(Protocol):
    """Narrow workspace port for MainWindow. Not the Settings Center Apply path."""

    def remember_layout(self) -> bool:
        """Return whether close-save may persist the live layout."""

    def layout_to_restore(self) -> WorkspaceLayoutPayload | None:
        """Return a stored layout to restore, or ``None`` for computed defaults."""

    def save_layout(self, layout: WorkspaceLayoutPayload) -> Any:
        """Persist layout now. Failures leave the previous document slot intact."""


class MemorySettingsDocumentPort:
    """In-memory document port for service tests. Not a QSettings dual-slot store."""

    def __init__(self, payload: Mapping[str, Any] | None = None) -> None:
        self.payload: dict[str, Any] | None = (
            None if payload is None else dict(payload)
        )
        self.fail_commit = False
        self.raise_on_commit: BaseException | None = None
        self.commit_calls = 0
        self.load_calls = 0

    def load(self) -> ServiceDocumentLoadResult:
        self.load_calls += 1
        if self.payload is None:
            return ServiceDocumentLoadResult(payload=None, missing=True)
        return ServiceDocumentLoadResult(payload=dict(self.payload), missing=False)

    def commit(self, payload: Mapping[str, Any]) -> ServiceStorageCommitResult:
        self.commit_calls += 1
        if self.raise_on_commit is not None:
            raise self.raise_on_commit
        if self.fail_commit:
            return ServiceStorageCommitResult(
                success=False,
                error="storage commit failed",
            )
        self.payload = dict(payload)
        return ServiceStorageCommitResult(success=True)


class SnapshotNewFigureDefaults:
    """Adapter that exposes only New Figure defaults from a getter."""

    def __init__(self, getter: Any) -> None:
        self._getter = getter

    def current(self) -> NewFigureSettings:
        return self._getter()


class SnapshotComponentDefaults:
    """Adapter that exposes only Components defaults from a getter."""

    def __init__(self, getter: Any) -> None:
        self._getter = getter

    def current(self) -> ComponentDefaultsSettings:
        return self._getter()


class FixedComponentDefaults:
    """Narrow adapter that always returns one ``ComponentDefaultsSettings``."""

    def __init__(self, settings: ComponentDefaultsSettings) -> None:
        self._settings = settings

    def current(self) -> ComponentDefaultsSettings:
        return self._settings


class SnapshotExportPreferences:
    """Adapter that exposes only export preferences from a getter."""

    def __init__(self, getter: Any, committer: Any | None = None) -> None:
        self._getter = getter
        self._committer = committer

    def current(self) -> ExportSettings:
        return self._getter()

    def commit(self, settings: ExportSettings) -> Any:
        if self._committer is None:
            return ServiceStorageCommitResult(success=True)
        return self._committer(settings)


class MemoryExportPreferences:
    """In-memory export port for dialog tests. Not a QSettings store."""

    def __init__(self, settings: ExportSettings | None = None) -> None:
        self._settings = settings if settings is not None else ExportSettings()
        self.fail_commit = False
        self.raise_on_commit: BaseException | None = None
        self.commit_calls = 0
        self.committed: list[ExportSettings] = []

    def current(self) -> ExportSettings:
        return self._settings

    def commit(self, settings: ExportSettings) -> ServiceStorageCommitResult:
        self.commit_calls += 1
        self.committed.append(settings)
        if self.raise_on_commit is not None:
            raise self.raise_on_commit
        if self.fail_commit:
            return ServiceStorageCommitResult(
                success=False,
                error="export preference commit failed",
            )
        self._settings = settings
        return ServiceStorageCommitResult(success=True)


class ServiceWorkspaceLayoutPort:
    """Adapter that exposes only workspace layout from a settings service."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def remember_layout(self) -> bool:
        workspace = self._service.snapshot().workspace
        return bool(workspace.remember_layout)

    def layout_to_restore(self) -> WorkspaceLayoutPayload | None:
        workspace = self._service.snapshot().workspace
        if not workspace.remember_layout:
            return None
        layout = workspace.layout
        if layout == DEFAULT_WORKSPACE_LAYOUT:
            return None
        return layout

    def save_layout(self, layout: WorkspaceLayoutPayload) -> SettingsCommitResult:
        session = self._service.begin_session()
        return self._service.commit_patch(session, {WORKSPACE_LAYOUT: layout})
