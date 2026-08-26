"""Dual-slot QSettings document port with load arbitration and verified commit."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QSettings

from mygui.application_settings.storage.envelope import (
    DecodedEnvelope,
    EnvelopeCodec,
    EnvelopeError,
    canonical_json_bytes,
)
from mygui.application_settings.storage.keys import (
    MAX_REVISION,
    SLOT_A,
    SLOT_B,
    SLOTS,
    slot_key,
)
from mygui.application_settings.storage.types import (
    DocumentHealth,
    DocumentLoadResult,
    SlotDiagnostic,
    SlotPresence,
    StorageCommitResult,
)

Migrator = Callable[[Any], tuple[dict[str, Any], tuple[str, ...]]]


def _status_is_ok(status: object) -> bool:
    if status == QSettings.Status.NoError:
        return True
    return status in (0, "NoError")


class DualSlotDocumentPort:
    """Load and commit one document stored as two isolated JSON envelopes."""

    def __init__(
        self,
        store: Any,
        *,
        open_reader: Callable[[], Any],
        group: str,
        schema: str,
        migrator: Migrator | None = None,
        is_writes_forbidden: Callable[[], bool] | None = None,
        mark_writes_forbidden: Callable[[], None] | None = None,
        codec: EnvelopeCodec | None = None,
    ) -> None:
        self._store = store
        self._open_reader = open_reader
        self._group = group
        self._schema = schema
        self._migrator = migrator
        self._is_writes_forbidden = is_writes_forbidden
        self._mark_writes_forbidden = mark_writes_forbidden
        self._codec = codec or EnvelopeCodec()

    def load(self) -> DocumentLoadResult:
        """Validate both slots and return the arbitrated snapshot."""

        inspections = self._inspect_slots()
        return self._arbitrate(inspections)

    def clear_slots(self) -> None:
        """Remove both slot keys. Recovery use only; not a legacy migrator."""

        for slot in SLOTS:
            self._store.remove(slot_key(self._group, slot))
        if callable(getattr(self._store, "sync", None)):
            self._store.sync()

    def commit(self, payload: Mapping[str, Any]) -> StorageCommitResult:
        """Write the older slot, then confirm the result with a fresh reader."""

        if self._writes_are_forbidden():
            return StorageCommitResult(
                ok=False,
                health=DocumentHealth.WRITE_UNCERTAIN,
                revision=None,
                error="writes are forbidden after an uncertain store operation",
            )
        inspections = self._inspect_slots()
        load = self._arbitrate(inspections, allow_migrate=False)
        if load.health in {
            DocumentHealth.READ_ONLY_FUTURE,
            DocumentHealth.RECOVERY_REQUIRED,
            DocumentHealth.WRITE_UNCERTAIN,
        }:
            return StorageCommitResult(
                ok=False,
                health=load.health,
                revision=load.revision,
                error=f"commit refused because document health is {load.health}",
            )
        if _has_future_slot(inspections):
            return StorageCommitResult(
                ok=False,
                health=DocumentHealth.READ_ONLY_FUTURE,
                revision=load.revision,
                error="commit refused because a future schema slot is present",
            )
        try:
            next_revision = _next_revision(load.revision)
            encoded = self._codec.encode(
                schema=self._schema,
                payload=payload,
                revision=next_revision,
            )
        except EnvelopeError as exc:
            return StorageCommitResult(
                ok=False,
                health=load.health,
                revision=load.revision,
                error=str(exc),
            )
        target = _target_slot(load.source_slot, inspections)
        if _slot_is_future(inspections, target):
            return StorageCommitResult(
                ok=False,
                health=DocumentHealth.READ_ONLY_FUTURE,
                revision=load.revision,
                error="commit refused because the target slot has a future schema",
            )
        key = slot_key(self._group, target)
        warning = (
            "repaired a corrupt companion slot"
            if load.health is DocumentHealth.DEGRADED
            else None
        )
        try:
            self._store.setValue(key, encoded)
            set_status = getattr(self._store, "status", None)
            if callable(set_status) and not _status_is_ok(set_status()):
                return self._uncertain("QSettings.status() failed after setValue")
            self._store.sync()
            sync_status = getattr(self._store, "status", None)
            if callable(sync_status) and not _status_is_ok(sync_status()):
                return self._uncertain("QSettings.status() failed after sync")
        except Exception as exc:  # noqa: BLE001 - write uncertainty
            return self._uncertain(f"store write failed: {exc}")
        try:
            reader = self._open_reader()
        except Exception as exc:  # noqa: BLE001 - write uncertainty
            return self._uncertain(f"fresh reader could not be created: {exc}")
        try:
            if callable(getattr(reader, "sync", None)):
                reader.sync()
            raw = reader.value(key)
        except Exception as exc:  # noqa: BLE001 - write uncertainty
            return self._uncertain(f"fresh-reader readback failed: {exc}")
        try:
            decoded = self._codec.decode(raw, expected_schema=self._schema)
        except EnvelopeError as exc:
            return self._uncertain(f"fresh-reader envelope is invalid: {exc}")
        expected = self._codec.decode(encoded, expected_schema=self._schema)
        if not _typed_equal(expected, decoded):
            return self._uncertain("fresh-reader readback does not match the written envelope")
        return StorageCommitResult(
            ok=True,
            health=DocumentHealth.NORMAL,
            revision=next_revision,
            warning=warning,
            slot=target,
        )

    def _writes_are_forbidden(self) -> bool:
        if self._is_writes_forbidden is None:
            return False
        return bool(self._is_writes_forbidden())

    def _forbid_writes(self) -> None:
        if self._mark_writes_forbidden is not None:
            self._mark_writes_forbidden()

    def _uncertain(self, message: str) -> StorageCommitResult:
        self._forbid_writes()
        return StorageCommitResult(
            ok=False,
            health=DocumentHealth.WRITE_UNCERTAIN,
            revision=None,
            error=message,
        )

    def _inspect_slots(self) -> dict[str, SlotDiagnostic]:
        try:
            reader = self._open_reader()
        except Exception as exc:  # noqa: BLE001 - treat as unreadable store
            return {
                slot: SlotDiagnostic(
                    slot=slot,
                    presence=SlotPresence.PRESENT,
                    status="corrupt",
                    error=f"store unreadable: {exc}",
                )
                for slot in SLOTS
            }
        if callable(getattr(reader, "sync", None)):
            try:
                reader.sync()
            except Exception:
                pass
        return {slot: self._inspect_slot(reader, slot) for slot in SLOTS}

    def _inspect_slot(self, reader: Any, slot: str) -> SlotDiagnostic:
        key = slot_key(self._group, slot)
        try:
            present = bool(reader.contains(key))
        except Exception as exc:
            return SlotDiagnostic(
                slot=slot,
                presence=SlotPresence.PRESENT,
                status="corrupt",
                error=f"contains() failed: {exc}",
            )
        if not present:
            return SlotDiagnostic(
                slot=slot,
                presence=SlotPresence.MISSING,
                status="missing",
            )
        try:
            raw = reader.value(key)
            decoded = self._codec.decode(raw, expected_schema=self._schema)
        except EnvelopeError as exc:
            return SlotDiagnostic(
                slot=slot,
                presence=SlotPresence.PRESENT,
                status="corrupt",
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - slot isolation
            return SlotDiagnostic(
                slot=slot,
                presence=SlotPresence.PRESENT,
                status="corrupt",
                error=str(exc),
            )
        status = "valid_future" if decoded.is_future else "valid_current"
        return SlotDiagnostic(
            slot=slot,
            presence=SlotPresence.PRESENT,
            status=status,
            revision=decoded.revision,
            schema_version=decoded.schema_version,
            sha256=decoded.sha256,
        )

    def _decode_slot(self, slot: str) -> DecodedEnvelope | None:
        reader = self._open_reader()
        if callable(getattr(reader, "sync", None)):
            try:
                reader.sync()
            except Exception:
                pass
        key = slot_key(self._group, slot)
        if not reader.contains(key):
            return None
        return self._codec.decode(reader.value(key), expected_schema=self._schema)

    def _arbitrate(
        self,
        inspections: dict[str, SlotDiagnostic],
        *,
        allow_migrate: bool = True,
    ) -> DocumentLoadResult:
        states = tuple(inspections[slot] for slot in SLOTS)
        diagnostics = [_describe(item) for item in states]
        current = [
            item for item in states if item.status == "valid_current"
        ]
        future = [
            item for item in states if item.status == "valid_future"
        ]
        corrupt = [item for item in states if item.status == "corrupt"]
        missing = [item for item in states if item.status == "missing"]

        split = _split_brain(self, current + future)
        if split is not None:
            left, right = split
            diagnostics.append(
                f"split-brain at revision {left.revision}: "
                f"{left.slot} and {right.slot} differ"
            )
            return DocumentLoadResult(
                health=DocumentHealth.RECOVERY_REQUIRED,
                revision=left.revision,
                payload=None,
                source_slot=None,
                diagnostics=tuple(diagnostics),
                slot_states=states,
            )

        if future:
            current_snapshot = _highest(current)
            payload = None
            revision = None
            source = None
            snapshot_bytes = None
            if current_snapshot is not None:
                decoded = self._decode_slot(current_snapshot.slot)
                if decoded is not None:
                    payload = copy.deepcopy(decoded.payload)
                    revision = decoded.revision
                    source = current_snapshot.slot
                    snapshot_bytes = decoded.encoded_bytes
            elif future:
                decoded = self._decode_slot(_highest(future).slot)
                if decoded is not None:
                    snapshot_bytes = decoded.encoded_bytes
                    revision = decoded.revision
            diagnostics.append("future schema_version present; writes are forbidden")
            return DocumentLoadResult(
                health=DocumentHealth.READ_ONLY_FUTURE,
                revision=revision,
                payload=payload,
                source_slot=source,
                diagnostics=tuple(diagnostics),
                slot_states=states,
                snapshot_bytes=snapshot_bytes,
            )

        if len(missing) == 2:
            if not allow_migrate:
                return DocumentLoadResult(
                    health=DocumentHealth.NORMAL,
                    revision=None,
                    payload=None,
                    source_slot=None,
                    diagnostics=tuple(diagnostics),
                    slot_states=states,
                )
            payload, migrate_notes = self._migrate()
            diagnostics.extend(migrate_notes)
            return DocumentLoadResult(
                health=DocumentHealth.NORMAL,
                revision=None,
                payload=payload,
                source_slot=None,
                diagnostics=tuple(diagnostics),
                slot_states=states,
                migrated_from_legacy="bootstrap: migrated_from_legacy" in migrate_notes,
            )

        if not current:
            diagnostics.append(
                "slots were written but none are usable; legacy will not be re-imported"
            )
            return DocumentLoadResult(
                health=DocumentHealth.RECOVERY_REQUIRED,
                revision=None,
                payload=None,
                source_slot=None,
                diagnostics=tuple(diagnostics),
                slot_states=states,
            )

        selected = _highest(current)
        decoded = self._decode_slot(selected.slot)
        if decoded is None:
            diagnostics.append(f"{selected.slot} became unreadable during decode")
            return DocumentLoadResult(
                health=DocumentHealth.RECOVERY_REQUIRED,
                revision=None,
                payload=None,
                source_slot=None,
                diagnostics=tuple(diagnostics),
                slot_states=states,
            )
        health = DocumentHealth.DEGRADED if corrupt else DocumentHealth.NORMAL
        if corrupt:
            diagnostics.append(
                f"using {selected.slot}; the next successful commit will repair "
                f"the corrupt companion slot"
            )
        return DocumentLoadResult(
            health=health,
            revision=decoded.revision,
            payload=copy.deepcopy(decoded.payload),
            source_slot=selected.slot,
            diagnostics=tuple(diagnostics),
            slot_states=states,
            snapshot_bytes=decoded.encoded_bytes,
        )

    def _migrate(self) -> tuple[dict[str, Any], tuple[str, ...]]:
        if self._migrator is None:
            return {}, ("no migrator configured; using an empty payload",)
        try:
            reader = self._open_reader()
        except Exception as exc:  # noqa: BLE001 - isolated fallback
            return {}, (f"migrator could not open settings: {exc}",)
        try:
            payload, notes = self._migrator(reader)
        except Exception as exc:  # noqa: BLE001 - isolated fallback
            return {}, (f"migrator failed: {exc}",)
        if not isinstance(payload, dict):
            return {}, ("migrator did not return a JSON object",)
        return copy.deepcopy(payload), notes


def _describe(item: SlotDiagnostic) -> str:
    if item.status == "missing":
        return f"{item.slot}: missing"
    if item.error:
        return f"{item.slot}: {item.status} ({item.error})"
    if item.revision is None:
        return f"{item.slot}: {item.status}"
    return (
        f"{item.slot}: {item.status} revision={item.revision} "
        f"schema_version={item.schema_version}"
    )


def _highest(items: list[SlotDiagnostic]) -> SlotDiagnostic | None:
    if not items:
        return None
    return max(items, key=lambda item: (item.revision or 0, 0 if item.slot == SLOT_A else 1))


def _split_brain(
    port: DualSlotDocumentPort,
    items: list[SlotDiagnostic],
) -> tuple[SlotDiagnostic, SlotDiagnostic] | None:
    by_key: dict[tuple[int | None, int], list[SlotDiagnostic]] = {}
    for item in items:
        if item.revision is None:
            continue
        by_key.setdefault((item.schema_version, item.revision), []).append(item)
    for group in by_key.values():
        if len(group) < 2:
            continue
        hashes = {item.sha256 for item in group}
        if len(hashes) > 1:
            return group[0], group[1]
        payloads: list[bytes] = []
        for item in group:
            decoded = port._decode_slot(item.slot)
            if decoded is None:
                return group[0], group[1]
            payloads.append(canonical_json_bytes(decoded.payload))
        if len(set(payloads)) > 1:
            return group[0], group[1]
    return None


def _next_revision(current: int | None) -> int:
    nxt = 1 if current is None else current + 1
    if nxt > MAX_REVISION:
        raise EnvelopeError("revision would exceed the signed 64-bit maximum")
    return nxt


def _target_slot(
    source_slot: str | None,
    inspections: dict[str, SlotDiagnostic],
) -> str:
    if source_slot == SLOT_A:
        return SLOT_B
    if source_slot == SLOT_B:
        return SLOT_A
    if inspections[SLOT_A].status == "missing":
        return SLOT_A
    return SLOT_B


def _has_future_slot(inspections: dict[str, SlotDiagnostic]) -> bool:
    return any(item.status == "valid_future" for item in inspections.values())


def _slot_is_future(inspections: dict[str, SlotDiagnostic], slot: str) -> bool:
    return inspections[slot].status == "valid_future"


def _typed_equal(left: DecodedEnvelope, right: DecodedEnvelope) -> bool:
    return (
        left.schema == right.schema
        and left.schema_version == right.schema_version
        and left.revision == right.revision
        and left.sha256 == right.sha256
        and canonical_json_bytes(left.payload) == canonical_json_bytes(right.payload)
    )
