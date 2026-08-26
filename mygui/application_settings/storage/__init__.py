"""Dual-slot QSettings storage for application and color-library settings."""

from mygui.application_settings.storage.backend import (
    SettingsBackend,
    create_settings_backend,
)
from mygui.application_settings.storage.dual_slot import DualSlotDocumentPort
from mygui.application_settings.storage.envelope import (
    EnvelopeCodec,
    EnvelopeError,
    canonical_json_bytes,
    envelope_sha256,
)
from mygui.application_settings.storage.keys import (
    APPLICATION_SETTINGS_GROUP,
    COLOR_LIBRARY_SETTINGS_GROUP,
    CURRENT_SCHEMA_VERSION,
    LEGACY_COLOR_GROUP,
    LEGACY_EXPORT_GROUP,
    LEGACY_WORKSPACE_GROUP,
    SCHEMA_APPLICATION_SETTINGS,
    SCHEMA_COLOR_LIBRARY_SETTINGS,
    SLOT_A,
    SLOT_B,
    slot_key,
)
from mygui.application_settings.storage.migrators import (
    clear_legacy_keys,
    default_application_settings_payload,
    default_color_library_payload,
    migrate_application_settings,
    migrate_color_library_settings,
)
from mygui.application_settings.storage.types import (
    DOCUMENT_HEALTH_LABELS,
    DRAFT_RESET_HEALTH,
    IMMEDIATE_RESET_HEALTH,
    DocumentHealth,
    DocumentLoadResult,
    SlotDiagnostic,
    SlotPresence,
    StorageCommitResult,
    allows_draft_preference_reset,
    document_health_label,
    requires_immediate_storage_reset,
)

__all__ = [
    "APPLICATION_SETTINGS_GROUP",
    "COLOR_LIBRARY_SETTINGS_GROUP",
    "CURRENT_SCHEMA_VERSION",
    "DOCUMENT_HEALTH_LABELS",
    "DRAFT_RESET_HEALTH",
    "DocumentHealth",
    "DocumentLoadResult",
    "IMMEDIATE_RESET_HEALTH",
    "DualSlotDocumentPort",
    "EnvelopeCodec",
    "EnvelopeError",
    "LEGACY_COLOR_GROUP",
    "LEGACY_EXPORT_GROUP",
    "LEGACY_WORKSPACE_GROUP",
    "SCHEMA_APPLICATION_SETTINGS",
    "SCHEMA_COLOR_LIBRARY_SETTINGS",
    "SLOT_A",
    "SLOT_B",
    "SettingsBackend",
    "SlotDiagnostic",
    "SlotPresence",
    "StorageCommitResult",
    "allows_draft_preference_reset",
    "canonical_json_bytes",
    "clear_legacy_keys",
    "create_settings_backend",
    "document_health_label",
    "requires_immediate_storage_reset",
    "default_application_settings_payload",
    "default_color_library_payload",
    "envelope_sha256",
    "migrate_application_settings",
    "migrate_color_library_settings",
    "slot_key",
]
