"""Application settings service: snapshot, session, rebase, and commit."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .document import (
    apply_patch_values,
    export_settings_to_patch,
    flatten_snapshot,
    payload_has_unknown_current_fields,
    snapshot_from_values,
    snapshot_to_payload,
    values_from_payload,
)
from .errors import (
    RuntimeBindingRollbackError,
    SettingsValidationError,
)
from .keys import PAGE_IDS, PERSISTENT_KEYS
from .models import (
    ApplicationSettingsSnapshot,
    ExportSettings,
    NewFigureSettings,
    SettingEffect,
    SettingsCommitResult,
    SettingsDraftResult,
    SettingsHealth,
)
from .ports import (
    ExportPreferencesPort,
    MemorySettingsDocumentPort,
    NewFigureDefaultsProvider,
    ServiceStorageCommitResult,
    ServiceWorkspaceLayoutPort,
    SettingsDocumentPort,
    SnapshotExportPreferences,
    SnapshotNewFigureDefaults,
    WorkspaceLayoutPort,
)
from .registry import SettingsRegistry, iter_live_keys, production_settings_registry
from .runtime import RuntimeBindingTransaction, SettingsRuntimeApplier
from .session import SettingsSession

SettingsListener = Callable[[ApplicationSettingsSnapshot], None]


class ApplicationSettingsService:
    """Authoritative in-memory settings snapshot with document-backed commits."""

    def __init__(
        self,
        document: SettingsDocumentPort | None = None,
        *,
        registry: SettingsRegistry | None = None,
        runtime_applier: SettingsRuntimeApplier | None = None,
    ) -> None:
        self._registry = registry or production_settings_registry()
        self._document = document if document is not None else MemorySettingsDocumentPort()
        self._applier = runtime_applier or SettingsRuntimeApplier()
        self._listeners: dict[int, SettingsListener] = {}
        self._listener_seq = 0
        self._commit_log: list[frozenset[str]] = []
        self._health = SettingsHealth.OK
        self._snapshot, load_warning = self._load_snapshot()
        self._load_warning = load_warning

    def _load_snapshot(self) -> tuple[ApplicationSettingsSnapshot, str | None]:
        try:
            loaded = self._document.load()
        except Exception as exc:  # noqa: BLE001
            defaults = snapshot_from_values(
                self._registry.defaults(),
                revision=0,
            )
            self._health = SettingsHealth.DEGRADED
            return defaults, f"settings load failed: {exc}"
        payload = getattr(loaded, "payload", None)
        missing = bool(getattr(loaded, "missing", payload is None))
        values, payload_revision = values_from_payload(payload, self._registry)
        envelope_revision = getattr(loaded, "revision", None)
        revision = payload_revision
        if envelope_revision is not None:
            try:
                revision = int(envelope_revision)
            except (TypeError, ValueError, OverflowError):
                revision = payload_revision
        if revision < 0:
            revision = 0
        self._health = _health_from_document(loaded)
        warning = getattr(loaded, "warning", None)
        diagnostics = getattr(loaded, "diagnostics", ())
        if warning is None and diagnostics:
            warning = "; ".join(str(item) for item in diagnostics if item)
        error = getattr(loaded, "error", None)
        if error and not missing:
            warning = str(error)
            if self._health is SettingsHealth.OK:
                self._health = SettingsHealth.DEGRADED
        if getattr(loaded, "recovered", False) or getattr(
            loaded, "migrated_from_legacy", False
        ):
            if self._health is SettingsHealth.OK:
                self._health = SettingsHealth.DEGRADED
        if payload_has_unknown_current_fields(
            payload if isinstance(payload, Mapping) else None
        ):
            if self._health in {SettingsHealth.OK, SettingsHealth.DEGRADED}:
                self._health = SettingsHealth.READ_ONLY_FUTURE
            extra = "unknown same-version fields; storage is read-only"
            warning = extra if not warning else f"{warning}; {extra}"
        return snapshot_from_values(values, revision=revision), warning

    def snapshot(self) -> ApplicationSettingsSnapshot:
        """Return the current immutable snapshot."""

        return self._snapshot

    def health(self) -> SettingsHealth:
        """Return whether runtime/storage still matches the snapshot."""

        return self._health

    def writable(self) -> bool:
        """Return whether ``commit_patch`` may persist a new revision."""

        return self._health in {SettingsHealth.OK, SettingsHealth.DEGRADED}

    def begin_session(self) -> SettingsSession:
        """Open a draft that stores only dirty keys and a base revision."""

        return SettingsSession(
            base_revision=self._snapshot.revision,
            service_id=id(self),
        )

    def subscribe(self, callback: SettingsListener) -> Callable[[], None]:
        """Register a listener. Successful commits emit exactly once."""

        token = self._listener_seq
        self._listener_seq += 1
        self._listeners[token] = callback

        def unsubscribe() -> None:
            self._listeners.pop(token, None)

        return unsubscribe

    def commit_patch(
        self,
        session: SettingsSession,
        patch: Mapping[str, Any] | None = None,
    ) -> SettingsCommitResult:
        """Validate, rebase, preview LIVE keys, then persist the document."""

        self._check_session(session)
        incoming = {**session.dirty_patch(), **dict(patch or {})}
        if incoming and not self.writable():
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error="Settings storage is not writable.",
                health=self._health,
            )
        if not incoming:
            return SettingsCommitResult(
                success=True,
                snapshot=self._snapshot,
                warning=self._load_warning,
                health=self._health,
            )
        try:
            normalized = apply_patch_values(
                flatten_snapshot(self._snapshot),
                incoming,
                self._registry,
            )
            incoming_normalized = {
                key: normalized[key] for key in incoming
            }
        except SettingsValidationError as exc:
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=str(exc),
                health=self._health,
            )

        conflicts = self._conflicts(session.base_revision, set(incoming_normalized))
        if conflicts:
            self._resync_session(session, incoming_normalized, conflicts)
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=(
                    "Settings patch conflicts with external changes: "
                    + ", ".join(sorted(conflicts))
                ),
                conflicts=tuple(sorted(conflicts)),
                health=self._health,
            )

        current_values = flatten_snapshot(self._snapshot)
        changed = {
            key: value
            for key, value in incoming_normalized.items()
            if current_values[key] != value
        }
        if not changed:
            session.base_revision = self._snapshot.revision
            session._clear_dirty()
            return SettingsCommitResult(
                success=True,
                snapshot=self._snapshot,
                health=self._health,
            )

        candidate_values = dict(current_values)
        candidate_values.update(changed)
        candidate = snapshot_from_values(
            candidate_values,
            revision=self._snapshot.revision,
        )
        live_keys = iter_live_keys(self._registry, changed)
        transaction = self._applier.transaction()
        preview_error = self._preview_live(transaction, candidate, live_keys)
        if preview_error is not None:
            return preview_error
        previewed = bool(live_keys)

        payload = snapshot_to_payload(
            snapshot_from_values(
                candidate_values,
                revision=self._snapshot.revision + 1,
            ),
            self._registry,
        )
        stored = self._commit_document(payload)
        if not stored.success:
            if previewed:
                rollback_error = self._rollback_preview(transaction)
                if rollback_error is not None:
                    return rollback_error
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=stored.error or "storage commit failed",
                warning=stored.warning,
                health=self._health,
            )

        confirm_warning = stored.warning
        if previewed:
            try:
                transaction.confirm()
            except Exception as exc:
                self._health = SettingsHealth.UNCERTAIN
                confirm_warning = str(exc)

        new_snapshot = snapshot_from_values(
            candidate_values,
            revision=self._snapshot.revision + 1,
        )
        self._snapshot = new_snapshot
        self._commit_log.append(frozenset(changed))
        if self._health is not SettingsHealth.UNCERTAIN:
            self._health = SettingsHealth.OK
        session.base_revision = new_snapshot.revision
        session._clear_dirty()
        self._emit(new_snapshot)
        return SettingsCommitResult(
            success=True,
            snapshot=new_snapshot,
            warning=confirm_warning,
            health=self._health,
            event_emitted=True,
        )

    def reset_section(
        self,
        session: SettingsSession,
        section_id: str,
    ) -> SettingsDraftResult:
        """Stage page defaults on the session. Does not write the document."""

        self._check_session(session)
        if section_id not in PAGE_IDS:
            raise SettingsValidationError(
                f"Unknown settings page {section_id!r}."
            )
        defaults = self._registry.restore_defaults_for_page(section_id)
        current = flatten_snapshot(self._snapshot)
        dirty = dict(session.dirty_patch())
        for key, default in defaults.items():
            if current[key] != default:
                dirty[key] = default
            else:
                dirty.pop(key, None)
        session._replace_dirty(dirty)
        return SettingsDraftResult(
            success=True,
            session_revision=session.base_revision,
            dirty=session.dirty_patch(),
        )

    def reset_all_preferences(self, session: SettingsSession) -> SettingsDraftResult:
        """Stage built-in defaults for every persisted page. Color library is excluded."""

        self._check_session(session)
        defaults = self._registry.reset_all_defaults()
        current = flatten_snapshot(self._snapshot)
        dirty = dict(session.dirty_patch())
        for key, default in defaults.items():
            if current[key] != default:
                dirty[key] = default
            else:
                dirty.pop(key, None)
        session._replace_dirty(dirty)
        return SettingsDraftResult(
            success=True,
            session_revision=session.base_revision,
            dirty=session.dirty_patch(),
        )

    def reload(self) -> ApplicationSettingsSnapshot:
        """Reload the in-memory snapshot from the document. Does not emit."""

        self._snapshot, self._load_warning = self._load_snapshot()
        return self._snapshot

    def new_figure_defaults_provider(self) -> NewFigureDefaultsProvider:
        """Narrow port for Style creation/import. Do not pass this service."""

        return SnapshotNewFigureDefaults(lambda: self.snapshot().new_figure)

    def export_preferences_port(self) -> ExportPreferencesPort:
        """Narrow port for export defaults. Do not pass this service."""

        return SnapshotExportPreferences(
            lambda: self.snapshot().export,
            committer=self._commit_export_settings,
        )

    def _commit_export_settings(self, settings: ExportSettings) -> SettingsCommitResult:
        return self.commit_patch(
            self.begin_session(),
            export_settings_to_patch(settings),
        )

    def workspace_layout_port(self) -> WorkspaceLayoutPort:
        """Narrow port for MainWindow remember/reset/close-save. Not Apply."""

        return ServiceWorkspaceLayoutPort(self)

    def new_figure_defaults(self) -> NewFigureSettings:
        return self._snapshot.new_figure

    def export_preferences(self) -> ExportSettings:
        return self._snapshot.export

    def document_payload(self) -> dict[str, Any]:
        """Return the JSON-safe payload for the current snapshot."""

        return snapshot_to_payload(self._snapshot, self._registry)

    def _preview_live(
        self,
        transaction: RuntimeBindingTransaction,
        candidate: ApplicationSettingsSnapshot,
        live_keys: frozenset[str],
    ) -> SettingsCommitResult | None:
        if not live_keys:
            return None
        try:
            transaction.apply_preview(candidate, live_keys)
        except RuntimeBindingRollbackError as exc:
            self._health = SettingsHealth.UNCERTAIN
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=str(exc),
                health=SettingsHealth.UNCERTAIN,
            )
        except Exception as exc:
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=str(exc),
                health=self._health,
            )
        return None

    def _rollback_preview(
        self,
        transaction: RuntimeBindingTransaction,
    ) -> SettingsCommitResult | None:
        try:
            transaction.rollback()
        except RuntimeBindingRollbackError as exc:
            self._health = SettingsHealth.UNCERTAIN
            return SettingsCommitResult(
                success=False,
                snapshot=self._snapshot,
                error=str(exc),
                health=SettingsHealth.UNCERTAIN,
            )
        return None

    def _check_session(self, session: SettingsSession) -> None:
        if session.service_id != id(self):
            raise SettingsValidationError(
                "Settings session does not belong to this service."
            )

    def _conflicts(self, base_revision: int, keys: set[str]) -> tuple[str, ...]:
        if base_revision > self._snapshot.revision:
            return tuple(sorted(keys))
        changed: set[str] = set()
        for index, committed in enumerate(self._commit_log, start=1):
            # log[0] produced revision 1 if we started at 0 with one commit.
            produced_revision = (
                self._snapshot.revision - len(self._commit_log) + index
            )
            if produced_revision <= base_revision:
                continue
            changed |= set(committed)
        return tuple(sorted(keys & changed))

    def _resync_session(
        self,
        session: SettingsSession,
        incoming: Mapping[str, Any],
        conflicts: tuple[str, ...],
    ) -> None:
        session.base_revision = self._snapshot.revision
        kept = {
            key: value
            for key, value in incoming.items()
            if key not in conflicts
        }
        session._replace_dirty(kept)

    def _commit_document(self, payload: Mapping[str, Any]) -> ServiceStorageCommitResult:
        try:
            result = self._document.commit(payload)
        except Exception as exc:  # noqa: BLE001
            return ServiceStorageCommitResult(success=False, error=str(exc))
        if result is None:
            return ServiceStorageCommitResult(
                success=False, error="storage commit failed"
            )
        ok = getattr(result, "ok", None)
        if ok is None:
            ok = bool(getattr(result, "success", False))
        error = getattr(result, "error", None)
        warning = getattr(result, "warning", None)
        return ServiceStorageCommitResult(
            success=bool(ok),
            error=None if error is None else str(error),
            warning=None if warning is None else str(warning),
        )

    def _emit(self, snapshot: ApplicationSettingsSnapshot) -> None:
        for callback in list(self._listeners.values()):
            try:
                callback(snapshot)
            except Exception:
                continue


def _health_from_document(loaded: Any) -> SettingsHealth:
    """Map storage health onto service health without collapsing future/recovery."""

    health = getattr(loaded, "health", None)
    if health is None:
        return SettingsHealth.OK
    if isinstance(health, SettingsHealth):
        return health
    text = str(getattr(health, "value", health)).casefold()
    if "uncertain" in text:
        return SettingsHealth.UNCERTAIN
    if text in {"read_only_future", SettingsHealth.READ_ONLY_FUTURE.value}:
        return SettingsHealth.READ_ONLY_FUTURE
    if text in {"recovery_required", SettingsHealth.RECOVERY_REQUIRED.value}:
        return SettingsHealth.RECOVERY_REQUIRED
    if text in {"degraded", SettingsHealth.DEGRADED.value}:
        return SettingsHealth.DEGRADED
    return SettingsHealth.OK


def default_effect_for_key(key: str) -> SettingEffect:
    """Return the production effect for a persisted key."""

    if key not in PERSISTENT_KEYS:
        raise SettingsValidationError(f"Unknown setting {key!r}.")
    return production_settings_registry().spec(key).effect
