import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from mygui.application_settings import (
    APPEARANCE_UI_FONT_POINT_SIZE,
    ApplicationSettingsService,
    ThemeMode,
)
from mygui.application_settings.storage import (
    APPLICATION_SETTINGS_GROUP,
    COLOR_LIBRARY_SETTINGS_GROUP,
    CURRENT_SCHEMA_VERSION,
    DocumentHealth,
    DualSlotDocumentPort,
    EnvelopeCodec,
    EnvelopeError,
    LEGACY_COLOR_GROUP,
    LEGACY_EXPORT_GROUP,
    LEGACY_WORKSPACE_GROUP,
    SCHEMA_APPLICATION_SETTINGS,
    SCHEMA_COLOR_LIBRARY_SETTINGS,
    SLOT_A,
    SLOT_B,
    canonical_json_bytes,
    clear_legacy_keys,
    create_settings_backend,
    default_application_settings_payload,
    default_color_library_payload,
    envelope_sha256,
    migrate_application_settings,
    migrate_color_library_settings,
    slot_key,
)
from mygui.application_settings.storage.keys import MAX_ENVELOPE_BYTES, MAX_REVISION


def _encode(
    payload,
    *,
    revision=1,
    schema=SCHEMA_APPLICATION_SETTINGS,
    schema_version=CURRENT_SCHEMA_VERSION,
):
    return EnvelopeCodec().encode(
        schema=schema,
        payload=payload,
        revision=revision,
        schema_version=schema_version,
    )


class _StatusStub:
    def __init__(self, inner, *, after_set=None, after_sync=None, sync_error=None):
        self._inner = inner
        self._after_set = after_set
        self._after_sync = after_sync
        self._sync_error = sync_error
        self._forced = None

    def setValue(self, key, value):
        self._inner.setValue(key, value)
        if self._after_set is not None:
            self._forced = self._after_set

    def sync(self):
        if self._sync_error is not None:
            raise self._sync_error
        self._inner.sync()
        if self._after_sync is not None:
            self._forced = self._after_sync

    def status(self):
        if self._forced is not None:
            return self._forced
        return QSettings.Status.NoError

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _WritePhaseStore:
    def __init__(self, inner, on_write):
        self._inner = inner
        self._on_write = on_write

    def setValue(self, key, value):
        self._inner.setValue(key, value)
        self._on_write()

    def __getattr__(self, name):
        return getattr(self._inner, name)


class EnvelopeCodecTests(unittest.TestCase):
    def test_canonical_json_sorts_keys_and_rejects_nan(self):
        encoded = canonical_json_bytes({"b": 1, "a": 2})
        self.assertEqual(encoded, b'{"a":2,"b":1}')
        with self.assertRaises(EnvelopeError):
            canonical_json_bytes({"x": float("nan")})
        with self.assertRaises(EnvelopeError):
            canonical_json_bytes({"x": float("inf")})

    def test_sha256_excludes_digest_field(self):
        body = {
            "payload": {"k": True},
            "revision": 3,
            "schema": SCHEMA_APPLICATION_SETTINGS,
            "schema_version": 1,
        }
        digest = envelope_sha256({**body, "sha256": "should-be-ignored"})
        self.assertEqual(digest, envelope_sha256(body))
        self.assertEqual(len(digest), 64)

    def test_revision_bounds(self):
        codec = EnvelopeCodec()
        payload = {"ok": True}
        codec.encode(schema=SCHEMA_APPLICATION_SETTINGS, payload=payload, revision=1)
        codec.encode(
            schema=SCHEMA_APPLICATION_SETTINGS,
            payload=payload,
            revision=MAX_REVISION,
        )
        with self.assertRaises(EnvelopeError):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload=payload,
                revision=0,
            )
        with self.assertRaises(EnvelopeError):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload=payload,
                revision=MAX_REVISION + 1,
            )

    def test_one_mib_limit(self):
        codec = EnvelopeCodec()
        schema = SCHEMA_APPLICATION_SETTINGS

        def size_for(padding):
            text = codec.encode(
                schema=schema,
                payload={"padding": "x" * padding},
                revision=1,
            )
            return len(text.encode("utf-8"))

        low = 0
        high = MAX_ENVELOPE_BYTES
        while low < high:
            mid = (low + high + 1) // 2
            try:
                encoded_size = size_for(mid)
            except EnvelopeError:
                high = mid - 1
                continue
            if encoded_size <= MAX_ENVELOPE_BYTES:
                low = mid
            else:
                high = mid - 1
        self.assertLessEqual(size_for(low), MAX_ENVELOPE_BYTES)
        with self.assertRaises(EnvelopeError):
            codec.encode(
                schema=schema,
                payload={"padding": "x" * (low + 1)},
                revision=1,
            )

        oversized = codec.encode(
            schema=schema,
            payload={"padding": "x" * low},
            revision=1,
        )
        decoded = codec.decode(oversized, expected_schema=schema)
        self.assertEqual(decoded.payload["padding"], "x" * low)

    def test_hash_mismatch_is_rejected(self):
        codec = EnvelopeCodec()
        text = codec.encode(
            schema=SCHEMA_APPLICATION_SETTINGS,
            payload={"a": 1},
            revision=1,
        )
        data = json.loads(text)
        data["sha256"] = "ab" * 32
        broken = json.dumps(data, sort_keys=True, separators=(",", ":"))
        with self.assertRaisesRegex(EnvelopeError, "sha256 mismatch"):
            codec.decode(broken, expected_schema=SCHEMA_APPLICATION_SETTINGS)

    def test_encode_and_decode_reject_illegal_inputs_and_storage_shapes(self):
        codec = EnvelopeCodec()
        with self.assertRaisesRegex(EnvelopeError, "non-empty string"):
            codec.encode(schema="", payload={"a": 1}, revision=1)
        with self.assertRaisesRegex(EnvelopeError, "schema_version"):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"a": 1},
                revision=1,
                schema_version=0,
            )
        with self.assertRaisesRegex(EnvelopeError, "payload must be a JSON object"):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload=["not", "an", "object"],
                revision=1,
            )
        with self.assertRaisesRegex(EnvelopeError, "payload is not JSON-serializable"):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"bad": object()},
                revision=1,
            )
        with self.assertRaisesRegex(EnvelopeError, "empty"):
            codec.decode(None, expected_schema=SCHEMA_APPLICATION_SETTINGS)
        with self.assertRaisesRegex(EnvelopeError, "empty"):
            codec.decode("", expected_schema=SCHEMA_APPLICATION_SETTINGS)
        with self.assertRaisesRegex(EnvelopeError, "not UTF-8"):
            codec.decode(b"\xff\xfe", expected_schema=SCHEMA_APPLICATION_SETTINGS)
        with self.assertRaisesRegex(EnvelopeError, "not valid JSON"):
            codec.decode("{", expected_schema=SCHEMA_APPLICATION_SETTINGS)
        with self.assertRaisesRegex(EnvelopeError, "duplicate JSON key"):
            codec.decode(
                '{"schema":"x","schema":"y"}',
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        with self.assertRaisesRegex(EnvelopeError, "JSON object"):
            codec.decode("[]", expected_schema=SCHEMA_APPLICATION_SETTINGS)
        encoded = codec.encode(
            schema=SCHEMA_APPLICATION_SETTINGS,
            payload={"ok": True},
            revision=1,
        )
        with self.assertRaisesRegex(EnvelopeError, "does not match"):
            codec.decode(encoded, expected_schema=SCHEMA_COLOR_LIBRARY_SETTINGS)
        decoded = codec.decode(bytearray(encoded.encode("utf-8")), expected_schema=SCHEMA_APPLICATION_SETTINGS)
        self.assertEqual(decoded.payload, {"ok": True})
        self.assertFalse(decoded.is_future)
        self.assertEqual(decoded.encoded_bytes, encoded.encode("utf-8"))

        data = json.loads(encoded)
        data["sha256"] = "zzzz" + ("a" * 60)
        with self.assertRaisesRegex(EnvelopeError, "64-character hex"):
            codec.decode(
                json.dumps(data, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        data["sha256"] = "ab" * 32
        data["extra"] = True
        body = {key: data[key] for key in data if key != "sha256"}
        data["sha256"] = envelope_sha256(body)
        with self.assertRaisesRegex(EnvelopeError, "unknown fields"):
            codec.decode(
                json.dumps(data, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        data["schema_version"] = CURRENT_SCHEMA_VERSION + 1
        body = {key: data[key] for key in data if key != "sha256"}
        data["sha256"] = envelope_sha256(body)
        future = codec.decode(
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            expected_schema=SCHEMA_APPLICATION_SETTINGS,
        )
        self.assertTrue(future.is_future)

        with self.assertRaisesRegex(EnvelopeError, "non-finite"):
            codec.decode("Infinity", expected_schema=SCHEMA_APPLICATION_SETTINGS)
        with self.assertRaisesRegex(EnvelopeError, "must be an integer"):
            codec.encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"a": 1},
                revision=True,
            )
        encoded = codec.encode(
            schema=SCHEMA_APPLICATION_SETTINGS,
            payload={"ok": True},
            revision=1,
        )
        parsed = json.loads(encoded)
        parsed["schema_version"] = 0
        body = {key: parsed[key] for key in parsed if key != "sha256"}
        parsed["sha256"] = envelope_sha256(body)
        with self.assertRaisesRegex(EnvelopeError, "schema_version must be >= 1"):
            codec.decode(
                json.dumps(parsed, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        parsed = json.loads(encoded)
        parsed["revision"] = MAX_REVISION + 1
        body = {key: parsed[key] for key in parsed if key != "sha256"}
        parsed["sha256"] = envelope_sha256(body)
        with self.assertRaisesRegex(EnvelopeError, "revision must be in"):
            codec.decode(
                json.dumps(parsed, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        parsed = json.loads(encoded)
        parsed["payload"] = []
        body = {key: parsed[key] for key in parsed if key != "sha256"}
        parsed["sha256"] = envelope_sha256(body)
        with self.assertRaisesRegex(EnvelopeError, "payload must be a JSON object"):
            codec.decode(
                json.dumps(parsed, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        parsed = json.loads(encoded)
        parsed["sha256"] = 12
        with self.assertRaisesRegex(EnvelopeError, "64-character hex"):
            codec.decode(
                json.dumps(parsed, sort_keys=True, separators=(",", ":")),
                expected_schema=SCHEMA_APPLICATION_SETTINGS,
            )
        with patch(
            "mygui.application_settings.storage.envelope.MAX_ENVELOPE_BYTES",
            8,
        ):
            with self.assertRaisesRegex(EnvelopeError, "1 MiB"):
                codec.decode(encoded, expected_schema=SCHEMA_APPLICATION_SETTINGS)

        class _AsBytes:
            def __bytes__(self):
                return encoded.encode("utf-8")

        decoded_bytes_obj = codec.decode(
            _AsBytes(),
            expected_schema=SCHEMA_APPLICATION_SETTINGS,
        )
        self.assertEqual(decoded_bytes_obj.payload, {"ok": True})

        class _AsText:
            def __bytes__(self):
                raise TypeError("no bytes")

            def __str__(self):
                return encoded

        decoded_text_obj = codec.decode(
            _AsText(),
            expected_schema=SCHEMA_APPLICATION_SETTINGS,
        )
        self.assertEqual(decoded_text_obj.payload, {"ok": True})

        class _BadUtf8:
            def __bytes__(self):
                return b"\xff\xfe"

        with self.assertRaisesRegex(EnvelopeError, "not UTF-8"):
            codec.decode(_BadUtf8(), expected_schema=SCHEMA_APPLICATION_SETTINGS)

        class _EmptyBoth:
            def __bytes__(self):
                return b""

            def __str__(self):
                return ""

        with self.assertRaisesRegex(EnvelopeError, "empty"):
            codec.decode(_EmptyBoth(), expected_schema=SCHEMA_APPLICATION_SETTINGS)

    def test_canonical_json_rejects_non_serializable_values(self):
        with self.assertRaises(EnvelopeError):
            canonical_json_bytes({"x": {1, 2}})


class DualSlotStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.ini"
        self.backend = create_settings_backend(file_path=self.path)
        self.port = self.backend.application_settings_port()
        self.color = self.backend.color_library_settings_port()

    def tearDown(self):
        self.backend.store.sync()
        self.directory.cleanup()

    def _plant(self, slot, payload, revision, *, group=APPLICATION_SETTINGS_GROUP,
               schema=SCHEMA_APPLICATION_SETTINGS, schema_version=1, raw=None):
        key = slot_key(group, slot)
        if raw is None:
            raw = EnvelopeCodec().encode(
                schema=schema,
                payload=payload,
                revision=revision,
                schema_version=schema_version,
            )
        self.backend.store.setValue(key, raw)
        self.backend.store.sync()

    def _legacy_workspace(self, *, version=2):
        settings = self.backend.store
        settings.beginGroup(LEGACY_WORKSPACE_GROUP)
        settings.setValue("version", version)
        settings.setValue("outerSplitterSizes", [640, 640])
        settings.setValue("innerSplitterSizes", [330, 260])
        if version == 1:
            settings.setValue("tableVisible", False)
        else:
            settings.setValue("explorerMode", "components")
            settings.setValue("explorerVisible", False)
        settings.endGroup()
        settings.sync()

    def _legacy_export(self, *, version=1, fmt="pdf"):
        settings = self.backend.store
        settings.beginGroup(LEGACY_EXPORT_GROUP)
        settings.setValue("version", version)
        settings.setValue("format", fmt)
        settings.setValue("lastDirectory", str(self.directory.name))
        settings.setValue("dpi", 180)
        settings.setValue("useProjectDpi", False)
        settings.setValue("jpegQuality", 40)
        settings.beginGroup("metadata")
        settings.setValue("Title", "Kept")
        settings.endGroup()
        settings.endGroup()
        settings.sync()

    def _legacy_color(self, *, version=1, state=None):
        settings = self.backend.store
        settings.beginGroup(LEGACY_COLOR_GROUP)
        settings.setValue("version", version)
        if state is None:
            state = json.dumps(
                {
                    "recent_colors": ["#FF0000"],
                    "favorite_colors": [],
                    "favorite_palette_ids": ["tab10"],
                    "custom_palettes": [],
                }
            )
        settings.setValue("state", state)
        settings.endGroup()
        settings.sync()

    def test_create_settings_backend_requires_identity(self):
        with self.assertRaises(ValueError):
            create_settings_backend()

    def test_fresh_install_uses_system_appearance(self):
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.NORMAL)
        self.assertIsNone(loaded.revision)
        self.assertIsNone(loaded.source_slot)
        self.assertEqual(loaded.payload["appearance"]["theme_mode"], "system")
        self.assertEqual(loaded.payload["appearance"]["ui_font_point_size"], 9)
        self.assertEqual(loaded.payload["appearance"]["density"], "standard")
        self.assertTrue(loaded.writable)
        self.assertIn("bootstrap: fresh_defaults", loaded.diagnostics)
        color = self.color.load()
        self.assertEqual(color.payload, default_color_library_payload())

    def test_alternating_slot_writes(self):
        first_payload = default_application_settings_payload(migrated=False)
        first_payload["appearance"]["theme_mode"] = "light"
        first = self.port.commit(first_payload)
        self.assertTrue(first.ok)
        self.assertEqual(first.slot, SLOT_A)
        self.assertEqual(first.revision, 1)
        self.assertEqual(first.health, DocumentHealth.NORMAL)

        loaded = self.port.load()
        self.assertEqual(loaded.source_slot, SLOT_A)
        self.assertEqual(loaded.revision, 1)
        self.assertEqual(loaded.payload["appearance"]["theme_mode"], "light")

        second_payload = dict(loaded.payload)
        second_payload = json.loads(json.dumps(second_payload))
        second_payload["workspace"]["remember_layout"] = False
        second = self.port.commit(second_payload)
        self.assertTrue(second.ok)
        self.assertEqual(second.slot, SLOT_B)
        self.assertEqual(second.revision, 2)

        third_payload = json.loads(json.dumps(second_payload))
        third_payload["new_figure"]["width_in"] = 8.0
        third = self.port.commit(third_payload)
        self.assertTrue(third.ok)
        self.assertEqual(third.slot, SLOT_A)
        self.assertEqual(third.revision, 3)

        latest = self.port.load()
        self.assertEqual(latest.source_slot, SLOT_A)
        self.assertEqual(latest.revision, 3)
        self.assertEqual(latest.payload["new_figure"]["width_in"], 8.0)
        self.assertTrue(
            self.backend.store.contains(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B))
        )

    def test_single_slot_corrupt_is_degraded_and_repaired_on_commit(self):
        payload = default_application_settings_payload(migrated=False)
        self.assertTrue(self.port.commit(payload).ok)
        self._plant(SLOT_B, {"other": True}, revision=1)
        self.backend.store.setValue(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B),
            "{not-json",
        )
        self.backend.store.sync()

        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.DEGRADED)
        self.assertEqual(loaded.source_slot, SLOT_A)
        self.assertTrue(loaded.writable)
        repaired_payload = json.loads(json.dumps(loaded.payload))
        repaired_payload["appearance"]["density"] = "standard"
        committed = self.port.commit(repaired_payload)
        self.assertTrue(committed.ok)
        self.assertEqual(committed.slot, SLOT_B)
        self.assertEqual(committed.health, DocumentHealth.NORMAL)

        after = self.port.load()
        self.assertEqual(after.health, DocumentHealth.NORMAL)
        self.assertEqual(after.revision, 2)
        self.assertEqual(after.source_slot, SLOT_B)

    def test_both_slots_corrupt_do_not_reimport_legacy(self):
        self._legacy_workspace()
        self._legacy_export()
        self._plant(SLOT_A, {"a": 1}, 1, raw="broken-a")
        self._plant(SLOT_B, {"b": 1}, 1, raw="broken-b")
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.RECOVERY_REQUIRED)
        self.assertIsNone(loaded.payload)
        self.assertFalse(loaded.writable)
        self.assertFalse(self.port.commit({"x": 1}).ok)
        self.backend.store.beginGroup(LEGACY_WORKSPACE_GROUP)
        try:
            self.assertEqual(int(self.backend.store.value("version")), 2)
        finally:
            self.backend.store.endGroup()

    def test_one_corrupt_and_one_missing_is_recovery(self):
        self._legacy_export()
        self._plant(SLOT_A, {"a": 1}, 1, raw="not-an-envelope")
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.RECOVERY_REQUIRED)
        self.assertIsNone(loaded.payload)
        self.assertNotEqual(loaded.payload, default_application_settings_payload())

    def test_equal_revision_split_brain_is_read_only(self):
        self._plant(SLOT_A, {"side": "a"}, revision=4)
        self._plant(SLOT_B, {"side": "b"}, revision=4)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.RECOVERY_REQUIRED)
        self.assertIsNone(loaded.payload)
        self.assertFalse(loaded.writable)
        refused = self.port.commit({"side": "c"})
        self.assertFalse(refused.ok)
        self.assertEqual(refused.health, DocumentHealth.RECOVERY_REQUIRED)

    def test_future_and_current_are_read_only_and_do_not_overwrite_future(self):
        current_payload = default_application_settings_payload(migrated=False)
        future_payload = {"future_field": True, "nested": {"v": 2}}
        self._plant(SLOT_A, current_payload, revision=3, schema_version=1)
        self._plant(SLOT_B, future_payload, revision=9, schema_version=2)
        future_raw = self.backend.store.value(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B)
        )

        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.READ_ONLY_FUTURE)
        self.assertEqual(loaded.source_slot, SLOT_A)
        self.assertEqual(loaded.revision, 3)
        self.assertEqual(loaded.payload["appearance"]["theme_mode"], "system")
        self.assertFalse(loaded.writable)

        refused = self.port.commit(loaded.payload)
        self.assertFalse(refused.ok)
        self.assertEqual(refused.health, DocumentHealth.READ_ONLY_FUTURE)
        self.backend.store.sync()
        self.assertEqual(
            self.backend.store.value(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B)),
            future_raw,
        )

    def test_same_revision_future_and_current_is_not_split_brain(self):
        current_payload = default_application_settings_payload(migrated=False)
        self._plant(SLOT_A, current_payload, revision=4, schema_version=1)
        self._plant(SLOT_B, {"next": True}, revision=4, schema_version=2)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.READ_ONLY_FUTURE)
        self.assertEqual(loaded.source_slot, SLOT_A)
        self.assertEqual(loaded.payload["appearance"]["theme_mode"], "system")
        self.assertFalse(self.port.commit(loaded.payload).ok)

    def test_future_only_returns_snapshot_bytes_without_current_payload(self):
        self._plant(SLOT_A, {"next": True}, revision=5, schema_version=2)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.READ_ONLY_FUTURE)
        self.assertIsNone(loaded.payload)
        self.assertIsNotNone(loaded.snapshot_bytes)
        self.assertFalse(self.port.commit({"x": 1}).ok)

    def test_hash_error_marks_slot_corrupt(self):
        text = _encode({"a": 1}, revision=1)
        data = json.loads(text)
        data["sha256"] = "cd" * 32
        self._plant(SLOT_A, {"a": 1}, 1, raw=json.dumps(data))
        payload = default_application_settings_payload(migrated=False)
        self._plant(SLOT_B, payload, revision=2)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.DEGRADED)
        self.assertEqual(loaded.source_slot, SLOT_B)
        self.assertTrue(any("sha256" in note for note in loaded.diagnostics))

    def test_readback_mismatch_is_write_uncertain(self):
        empty = Path(self.directory.name) / "empty.ini"
        phase = {"after_write": False}

        def open_reader():
            if phase["after_write"]:
                return QSettings(str(empty), QSettings.IniFormat)
            return QSettings(str(self.path), QSettings.IniFormat)

        store = _WritePhaseStore(
            self.backend.store,
            on_write=lambda: phase.update(after_write=True),
        )
        port = DualSlotDocumentPort(
            store,
            open_reader=open_reader,
            group=APPLICATION_SETTINGS_GROUP,
            schema=SCHEMA_APPLICATION_SETTINGS,
            migrator=migrate_application_settings,
            is_writes_forbidden=lambda: self.backend.writes_forbidden,
            mark_writes_forbidden=self.backend.mark_writes_forbidden,
        )
        result = port.commit(default_application_settings_payload())
        self.assertFalse(result.ok)
        self.assertEqual(result.health, DocumentHealth.WRITE_UNCERTAIN)
        self.assertTrue(self.backend.writes_forbidden)
        second = port.commit(default_application_settings_payload())
        self.assertFalse(second.ok)
        self.assertEqual(second.health, DocumentHealth.WRITE_UNCERTAIN)

    def test_status_error_after_sync_is_write_uncertain(self):
        stub = _StatusStub(
            self.backend.store,
            after_sync=QSettings.Status.AccessError,
        )
        port = DualSlotDocumentPort(
            stub,
            open_reader=self.backend.create_fresh_reader,
            group=APPLICATION_SETTINGS_GROUP,
            schema=SCHEMA_APPLICATION_SETTINGS,
            migrator=migrate_application_settings,
            is_writes_forbidden=lambda: self.backend.writes_forbidden,
            mark_writes_forbidden=self.backend.mark_writes_forbidden,
        )
        result = port.commit({"appearance": {"theme_mode": "system"}})
        self.assertFalse(result.ok)
        self.assertEqual(result.health, DocumentHealth.WRITE_UNCERTAIN)
        self.assertIn("status()", result.error)

    def test_status_error_after_setvalue_is_write_uncertain(self):
        stub = _StatusStub(
            self.backend.store,
            after_set=QSettings.Status.FormatError,
        )
        port = DualSlotDocumentPort(
            stub,
            open_reader=self.backend.create_fresh_reader,
            group=APPLICATION_SETTINGS_GROUP,
            schema=SCHEMA_APPLICATION_SETTINGS,
            is_writes_forbidden=lambda: self.backend.writes_forbidden,
            mark_writes_forbidden=self.backend.mark_writes_forbidden,
        )
        result = port.commit({"k": 1})
        self.assertFalse(result.ok)
        self.assertEqual(result.health, DocumentHealth.WRITE_UNCERTAIN)

    def test_sync_exception_is_write_uncertain(self):
        stub = _StatusStub(
            self.backend.store,
            sync_error=OSError("disk full"),
        )
        port = DualSlotDocumentPort(
            stub,
            open_reader=self.backend.create_fresh_reader,
            group=APPLICATION_SETTINGS_GROUP,
            schema=SCHEMA_APPLICATION_SETTINGS,
            is_writes_forbidden=lambda: self.backend.writes_forbidden,
            mark_writes_forbidden=self.backend.mark_writes_forbidden,
        )
        result = port.commit({"k": 1})
        self.assertFalse(result.ok)
        self.assertEqual(result.health, DocumentHealth.WRITE_UNCERTAIN)
        self.assertIn("disk full", result.error)

    def test_commit_rejects_oversize_and_revision_overflow_without_forbidding(self):
        too_big = {"padding": "x" * (MAX_ENVELOPE_BYTES + 16)}
        result = self.port.commit(too_big)
        self.assertFalse(result.ok)
        self.assertIn("1 MiB", result.error)
        self.assertFalse(self.backend.writes_forbidden)

        self._plant(SLOT_A, {"ok": True}, revision=MAX_REVISION)
        overflow = self.port.commit({"ok": False})
        self.assertFalse(overflow.ok)
        self.assertIn("signed 64-bit", overflow.error)
        self.assertFalse(self.backend.writes_forbidden)

    def test_legacy_domains_are_isolated_and_unknown_versions_default_only_that_domain(self):
        self._legacy_workspace(version=2)
        self._legacy_export(version=99)
        self._legacy_color(version=1, state="not-json")

        app = self.port.load()
        self.assertEqual(app.health, DocumentHealth.NORMAL)
        self.assertTrue(app.migrated_from_legacy)
        self.assertEqual(app.payload["appearance"]["theme_mode"], "light")
        self.assertEqual(
            app.payload["workspace"]["layout"]["explorerMode"],
            "components",
        )
        self.assertEqual(
            app.payload["workspace"]["layout"]["innerSplitterSizes"],
            [330, 260],
        )
        self.assertEqual(
            app.payload["export"]["format"],
            default_application_settings_payload(migrated=True)["export"]["format"],
        )
        self.assertTrue(
            any("export: unknown version" in note for note in app.diagnostics)
        )

        color = self.color.load()
        self.assertEqual(color.payload, default_color_library_payload())
        self.assertTrue(
            any("invalid state" in note for note in color.diagnostics)
        )

    def test_mixed_good_legacy_export_and_bad_workspace(self):
        self._legacy_workspace(version=7)
        self._legacy_export(version=1, fmt="webp")
        app = self.port.load()
        self.assertEqual(app.payload["appearance"]["theme_mode"], "light")
        self.assertIsNone(app.payload["workspace"]["layout"])
        self.assertEqual(app.payload["export"]["format"], "webp")
        self.assertEqual(app.payload["export"]["custom_dpi"], 180.0)
        self.assertEqual(app.payload["export"]["jpeg_quality"], 40)
        self.assertEqual(app.payload["export"]["metadata"]["Title"], "Kept")

    def test_color_legacy_migrates_on_its_own_port(self):
        self._legacy_color()
        color = self.color.load()
        self.assertEqual(color.payload["recent_colors"], ["#FF0000"])
        self.assertEqual(color.payload["favorite_palette_ids"], ["tab10"])
        app = self.port.load()
        self.assertEqual(app.payload["appearance"]["theme_mode"], "system")
        self.assertNotIn("recent_colors", app.payload)

    def test_workspace_v1_migrates_table_visibility(self):
        self._legacy_workspace(version=1)
        app = self.port.load()
        layout = app.payload["workspace"]["layout"]
        self.assertEqual(layout["version"], 2)
        self.assertEqual(layout["explorerMode"], "table")
        self.assertFalse(layout["explorerVisible"])
        self.assertEqual(app.payload["appearance"]["theme_mode"], "light")

    def test_migrate_only_when_both_slots_missing(self):
        self._legacy_workspace()
        stored = default_application_settings_payload(migrated=False)
        stored["appearance"]["theme_mode"] = "system"
        stored["workspace"]["remember_layout"] = False
        self._plant(SLOT_A, stored, revision=1)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.NORMAL)
        self.assertEqual(loaded.source_slot, SLOT_A)
        self.assertFalse(loaded.payload["workspace"]["remember_layout"])
        self.assertIsNone(loaded.payload["workspace"]["layout"])
        self.assertEqual(loaded.payload["appearance"]["theme_mode"], "system")

    def test_successful_commit_leaves_legacy_inert_and_clear_is_opt_in(self):
        self._legacy_workspace()
        self._legacy_export()
        loaded = self.port.load()
        committed = self.port.commit(loaded.payload)
        self.assertTrue(committed.ok)
        settings = self.backend.store
        settings.beginGroup(LEGACY_WORKSPACE_GROUP)
        try:
            self.assertEqual(int(settings.value("version")), 2)
        finally:
            settings.endGroup()
        settings.beginGroup(LEGACY_EXPORT_GROUP)
        try:
            self.assertEqual(int(settings.value("version")), 1)
        finally:
            settings.endGroup()
        with patch.object(settings, "remove") as remove:
            self.port.load()
            self.port.commit(loaded.payload)
            remove.assert_not_called()
        clear_legacy_keys(settings)
        settings.beginGroup(LEGACY_WORKSPACE_GROUP)
        try:
            self.assertIsNone(settings.value("version"))
        finally:
            settings.endGroup()

    def test_color_and_application_slots_are_isolated(self):
        app_payload = default_application_settings_payload()
        color_payload = default_color_library_payload()
        color_payload["recent_colors"] = ["#00FF00"]
        self.assertTrue(self.port.commit(app_payload).ok)
        self.assertTrue(self.color.commit(color_payload).ok)
        self.assertTrue(
            self.backend.store.contains(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_A))
        )
        self.assertTrue(
            self.backend.store.contains(slot_key(COLOR_LIBRARY_SETTINGS_GROUP, SLOT_A))
        )
        self.assertNotEqual(
            self.backend.store.value(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_A)),
            self.backend.store.value(slot_key(COLOR_LIBRARY_SETTINGS_GROUP, SLOT_A)),
        )
        self.assertEqual(self.color.load().payload["recent_colors"], ["#00FF00"])
        self.assertNotIn("recent_colors", self.port.load().payload)

    def test_migration_write_failure_does_not_report_success(self):
        self._legacy_workspace()
        loaded = self.port.load()
        stub = _StatusStub(
            self.backend.store,
            after_sync=QSettings.Status.AccessError,
        )
        port = DualSlotDocumentPort(
            stub,
            open_reader=self.backend.create_fresh_reader,
            group=APPLICATION_SETTINGS_GROUP,
            schema=SCHEMA_APPLICATION_SETTINGS,
            migrator=migrate_application_settings,
            is_writes_forbidden=lambda: self.backend.writes_forbidden,
            mark_writes_forbidden=self.backend.mark_writes_forbidden,
        )
        result = port.commit(loaded.payload)
        self.assertFalse(result.ok)
        self.assertEqual(result.health, DocumentHealth.WRITE_UNCERTAIN)
        self.assertTrue(self.backend.writes_forbidden)

    def test_direct_migrators_do_not_write_legacy_keys(self):
        self._legacy_color()
        settings = self.backend.store
        with patch.object(settings, "setValue") as set_value:
            migrate_application_settings(settings)
            migrate_color_library_settings(settings)
            set_value.assert_not_called()

    def test_fresh_ini_backend_feeds_service_snapshot(self):
        service = ApplicationSettingsService(document=self.port)
        snapshot = service.snapshot()
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(snapshot.appearance.ui_font_point_size, 9)
        self.assertEqual(snapshot.new_figure.width_in, 6.4)
        self.assertEqual(snapshot.revision, 0)

    def test_migrator_camelcase_layout_round_trips_through_service(self):
        self._legacy_workspace(version=2)
        service = ApplicationSettingsService(document=self.port)
        snapshot = service.snapshot()
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.LIGHT)
        layout = snapshot.workspace.layout
        self.assertEqual(layout.outer_splitter_sizes, (640, 640))
        self.assertEqual(layout.inner_splitter_sizes, (330, 260))
        self.assertEqual(layout.explorer_mode.value, "components")
        self.assertFalse(layout.explorer_visible)

        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: 11},
        )
        self.assertTrue(result.success)

        reloaded = ApplicationSettingsService(document=self.port)
        self.assertEqual(reloaded.snapshot().appearance.ui_font_point_size, 11)
        self.assertEqual(
            reloaded.snapshot().workspace.layout.outer_splitter_sizes,
            (640, 640),
        )
        self.assertEqual(
            reloaded.snapshot().workspace.layout.explorer_mode.value,
            "components",
        )

        raw = self.backend.store.value(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_A)
        )
        if raw is None:
            raw = self.backend.store.value(
                slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B)
            )
        decoded = EnvelopeCodec().decode(
            raw, expected_schema=SCHEMA_APPLICATION_SETTINGS
        )
        wire_layout = decoded.payload["workspace"]["layout"]
        self.assertEqual(wire_layout["kind"], "workspace_layout_v2")
        self.assertEqual(wire_layout["outer_splitter_sizes"], [640, 640])

    def test_reset_incompatible_documents_restores_writable_defaults(self):
        color_payload = default_color_library_payload()
        color_payload["recent_colors"] = ["#00FF00"]
        self.assertTrue(self.color.commit(color_payload).ok)
        self._legacy_workspace()
        self._legacy_export()
        self._plant(SLOT_A, {"side": "a"}, revision=4)
        self._plant(SLOT_B, {"side": "b"}, revision=4)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.RECOVERY_REQUIRED)
        self.assertFalse(self.port.commit({"x": 1}).ok)

        result = self.backend.reset_incompatible_documents()
        self.assertTrue(result.ok)
        self.assertEqual(result.health, DocumentHealth.NORMAL)
        recovered = self.port.load()
        self.assertEqual(recovered.health, DocumentHealth.NORMAL)
        self.assertTrue(recovered.writable)
        self.assertEqual(recovered.payload["appearance"]["theme_mode"], "system")
        self.assertEqual(self.color.load().payload["recent_colors"], ["#00FF00"])
        self.backend.store.beginGroup(LEGACY_WORKSPACE_GROUP)
        try:
            self.assertIsNone(self.backend.store.value("version"))
        finally:
            self.backend.store.endGroup()
        follow = self.port.commit(recovered.payload)
        self.assertTrue(follow.ok)

    def test_reset_incompatible_documents_clears_write_uncertain(self):
        self.backend.mark_writes_forbidden()
        self.assertTrue(self.backend.writes_forbidden)
        self._plant(SLOT_A, {"broken": True}, revision=1, raw="not-json")
        result = self.backend.reset_incompatible_documents()
        self.assertTrue(result.ok)
        self.assertFalse(self.backend.writes_forbidden)
        loaded = self.port.load()
        self.assertEqual(loaded.health, DocumentHealth.NORMAL)
        self.assertTrue(loaded.writable)

    def test_color_alternating_slot_writes(self):
        first = default_color_library_payload()
        first["recent_colors"] = ["#FF0000"]
        committed = self.color.commit(first)
        self.assertTrue(committed.ok)
        self.assertEqual(committed.slot, SLOT_A)
        self.assertEqual(committed.revision, 1)

        second = json.loads(json.dumps(first))
        second["recent_colors"] = ["#00FF00"]
        follow = self.color.commit(second)
        self.assertTrue(follow.ok)
        self.assertEqual(follow.slot, SLOT_B)
        self.assertEqual(follow.revision, 2)
        self.assertEqual(self.color.load().payload["recent_colors"], ["#00FF00"])
        self.assertEqual(self.port.load().health, DocumentHealth.NORMAL)

    def test_color_single_slot_corrupt_is_degraded_and_split_brain_is_recovery(self):
        payload = default_color_library_payload()
        self.assertTrue(self.color.commit(payload).ok)
        self._plant(
            SLOT_B,
            {"recent_colors": ["#111111"]},
            revision=1,
            group=COLOR_LIBRARY_SETTINGS_GROUP,
            schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
            raw="{not-json",
        )
        degraded = self.color.load()
        self.assertEqual(degraded.health, DocumentHealth.DEGRADED)
        self.assertEqual(degraded.source_slot, SLOT_A)
        self.assertTrue(degraded.writable)

        self._plant(
            SLOT_A,
            {"recent_colors": ["#AA0000"]},
            revision=4,
            group=COLOR_LIBRARY_SETTINGS_GROUP,
            schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
        )
        self._plant(
            SLOT_B,
            {"recent_colors": ["#00BB00"]},
            revision=4,
            group=COLOR_LIBRARY_SETTINGS_GROUP,
            schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
        )
        split = self.color.load()
        self.assertEqual(split.health, DocumentHealth.RECOVERY_REQUIRED)
        self.assertIsNone(split.payload)
        self.assertFalse(self.color.commit(payload).ok)
        self.assertEqual(self.port.load().health, DocumentHealth.NORMAL)

    def test_unknown_legacy_versions_of_all_three_domains_are_independent(self):
        self._legacy_workspace(version=9)
        self._legacy_export(version=9)
        self._legacy_color(version=9)
        app = self.port.load()
        color = self.color.load()
        self.assertEqual(app.health, DocumentHealth.NORMAL)
        self.assertTrue(app.migrated_from_legacy)
        self.assertEqual(app.payload["appearance"]["theme_mode"], "light")
        self.assertIsNone(app.payload["workspace"]["layout"])
        self.assertEqual(
            app.payload["export"]["format"],
            default_application_settings_payload(migrated=True)["export"]["format"],
        )
        self.assertEqual(color.payload, default_color_library_payload())
        self.assertTrue(any("workspace: unknown version" in note for note in app.diagnostics))
        self.assertTrue(any("export: unknown version" in note for note in app.diagnostics))
        self.assertTrue(any("unknown version" in note for note in color.diagnostics))

    def test_service_cannot_write_after_write_uncertain(self):
        service = ApplicationSettingsService(document=self.port)
        first = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: 10},
        )
        self.assertTrue(first.success)
        self.backend.mark_writes_forbidden()
        refused = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: 12},
        )
        self.assertFalse(refused.success)
        self.assertEqual(service.snapshot().appearance.ui_font_point_size, 10)
        self.assertTrue(self.backend.writes_forbidden)
        self.assertFalse(self.color.commit(default_color_library_payload()).ok)


if __name__ == "__main__":
    unittest.main()
