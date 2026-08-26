"""Closed health states and storage result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentHealth(StrEnum):
    """Closed set of dual-slot document health states."""

    NORMAL = "normal"
    DEGRADED = "degraded"
    READ_ONLY_FUTURE = "read_only_future"
    RECOVERY_REQUIRED = "recovery_required"
    WRITE_UNCERTAIN = "write_uncertain"


DOCUMENT_HEALTH_LABELS = {
    DocumentHealth.NORMAL: "Normal",
    DocumentHealth.DEGRADED: "Degraded",
    DocumentHealth.READ_ONLY_FUTURE: "Read-only future",
    DocumentHealth.RECOVERY_REQUIRED: "Recovery required",
    DocumentHealth.WRITE_UNCERTAIN: "Write uncertain",
}

DRAFT_RESET_HEALTH = frozenset({DocumentHealth.NORMAL, DocumentHealth.DEGRADED})
IMMEDIATE_RESET_HEALTH = frozenset(
    {
        DocumentHealth.READ_ONLY_FUTURE,
        DocumentHealth.RECOVERY_REQUIRED,
        DocumentHealth.WRITE_UNCERTAIN,
    }
)


def document_health_label(health: DocumentHealth | str) -> str:
    """Return the Settings Maintenance English label for a dual-slot health state."""

    if isinstance(health, DocumentHealth):
        return DOCUMENT_HEALTH_LABELS[health]
    try:
        return DOCUMENT_HEALTH_LABELS[DocumentHealth(str(health))]
    except ValueError:
        return str(health)


def allows_draft_preference_reset(health: DocumentHealth | str) -> bool:
    """Return whether Reset-all may stage a Settings Apply draft."""

    resolved = health if isinstance(health, DocumentHealth) else DocumentHealth(str(health))
    return resolved in DRAFT_RESET_HEALTH


def requires_immediate_storage_reset(health: DocumentHealth | str) -> bool:
    """Return whether storage must be reset now instead of through Apply."""

    resolved = health if isinstance(health, DocumentHealth) else DocumentHealth(str(health))
    return resolved in IMMEDIATE_RESET_HEALTH


class SlotPresence(StrEnum):
    """Distinguish a slot that was never written from one that exists."""

    MISSING = "missing"
    PRESENT = "present"


@dataclass(frozen=True, slots=True)
class SlotDiagnostic:
    """Inspection result for one document slot."""

    slot: str
    presence: SlotPresence
    status: str
    revision: int | None = None
    schema_version: int | None = None
    error: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentLoadResult:
    """Authoritative load snapshot for one dual-slot document."""

    health: DocumentHealth
    revision: int | None
    payload: dict[str, Any] | None
    source_slot: str | None
    diagnostics: tuple[str, ...]
    slot_states: tuple[SlotDiagnostic, ...] = ()
    snapshot_bytes: bytes | None = None
    migrated_from_legacy: bool = False

    @property
    def writable(self) -> bool:
        """Return whether a later commit may attempt a new revision."""

        return self.health in {DocumentHealth.NORMAL, DocumentHealth.DEGRADED}


@dataclass(frozen=True, slots=True)
class StorageCommitResult:
    """Outcome of a dual-slot commit after fresh-reader verification."""

    ok: bool
    health: DocumentHealth
    revision: int | None
    warning: str | None = None
    error: str | None = None
    slot: str | None = field(default=None)
