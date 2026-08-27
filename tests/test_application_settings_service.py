"""Service-level application settings tests.

Session rebase coverage lives in ``test_application_settings_session.py``.
This module focuses on commit transactions, runtime binders, and the document.
"""

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mygui.application_settings import (
    APPEARANCE_THEME_MODE,
    ApplicationSettingsService,
    EXPORT_CUSTOM_DPI,
    EXPORT_FORMAT,
    EXPORT_METADATA,
    EXPORT_PAD_INCHES,
    EXPORT_USE_PROJECT_DPI,
    ExportBBoxInches,
    ExportFormatPreference,
    MemorySettingsDocumentPort,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_EXPORT,
    PadInchesKind,
    RecordingRuntimeBinder,
    SettingEditorKind,
    SettingsHealth,
    SettingsRuntimeApplier,
    ThemeMode,
    WORKSPACE_REMEMBER_LAYOUT,
    WorkspaceExplorerMode,
    WorkspaceLayoutPayload,
    bind_workspace_layout_port,
    production_settings_registry,
)
from mygui.application_settings.document import snapshot_to_payload
from mygui.application_settings.keys import PERSISTENT_KEYS
from mygui.application_settings.values import (
    METADATA_KEYS,
    normalize_export_metadata,
    normalize_pad_inches,
)


def _service(**kwargs) -> ApplicationSettingsService:
    kwargs.setdefault("document", MemorySettingsDocumentPort())
    return ApplicationSettingsService(**kwargs)


class ApplicationSettingsServiceModuleTests(unittest.TestCase):
    def test_load_ignores_invalid_fields_and_keeps_defaults(self):
        port = MemorySettingsDocumentPort(
            {
                "appearance": {
                    "theme_mode": "not-a-theme",
                    "ui_font_point_size": 9,
                    "density": "standard",
                },
                "revision": 4,
            }
        )
        service = _service(document=port)
        snapshot = service.snapshot()
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(snapshot.appearance.ui_font_point_size, 9)
        self.assertEqual(snapshot.revision, 4)

    def test_export_tagged_values_round_trip_through_payload(self):
        service = _service()
        result = service.commit_patch(
            service.begin_session(),
            {
                EXPORT_FORMAT: ExportFormatPreference.PDF,
                EXPORT_PAD_INCHES: "layout",
                EXPORT_METADATA: {"Title": "Paper", "Subject": "XRD"},
                "export.bbox_inches": "tight",
            },
        )
        self.assertTrue(result.success)
        export = service.snapshot().export
        self.assertEqual(export.format, ExportFormatPreference.PDF)
        self.assertEqual(export.bbox_inches, ExportBBoxInches.TIGHT)
        self.assertEqual(export.pad_inches.kind, PadInchesKind.LAYOUT)
        self.assertEqual(export.pad_inches.to_savefig(), "layout")
        self.assertEqual(export.metadata.fields["Title"], "Paper")
        payload = json.loads(json.dumps(service.document_payload()))
        restored = MemorySettingsDocumentPort(payload)
        loaded = ApplicationSettingsService(document=restored).snapshot()
        self.assertEqual(loaded.export.format, ExportFormatPreference.PDF)
        self.assertEqual(loaded.export.pad_inches.kind, PadInchesKind.LAYOUT)
        self.assertEqual(dict(loaded.export.metadata.fields), dict(export.metadata.fields))

    def test_metadata_rejects_unknown_keys(self):
        with self.assertRaisesRegex(Exception, "metadata"):
            normalize_export_metadata({"kind": "export_metadata", "fields": {"Foo": "x"}})
        with self.assertRaisesRegex(Exception, "pad_inches"):
            normalize_pad_inches({"kind": "numeric", "inches": 9})
        self.assertTrue(METADATA_KEYS >= {"Title", "Creator", "Rights"})

    def test_registry_has_every_persistent_key_once(self):
        registry = production_settings_registry()
        self.assertEqual(registry.keys(), PERSISTENT_KEYS)
        self.assertEqual(len(registry.keys()), len(set(registry.keys())))
        for spec in registry.persistent_specs():
            self.assertNotEqual(getattr(SettingEditorKind, "JSON", None), spec.editor)
            self.assertNotEqual(spec.editor.value, "json")

    def test_dpi_strategy_survives_reload(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        service.commit_patch(
            service.begin_session(),
            {EXPORT_USE_PROJECT_DPI: False, EXPORT_CUSTOM_DPI: 96.0},
        )
        reloaded = ApplicationSettingsService(
            document=MemorySettingsDocumentPort(port.payload)
        )
        self.assertFalse(reloaded.snapshot().export.use_project_dpi)
        self.assertEqual(reloaded.snapshot().export.custom_dpi, 96.0)

    def test_apply_then_storage_failure_rolls_preview_back(self):
        port = MemorySettingsDocumentPort()
        binder = RecordingRuntimeBinder("live")
        service = _service(
            document=port,
            runtime_applier=SettingsRuntimeApplier([binder]),
        )
        port.fail_commit = True
        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertFalse(result.success)
        self.assertEqual([action[0] for action in binder.actions], ["apply", "rollback"])
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(result.health, SettingsHealth.OK)

    def test_new_figure_defaults_are_application_not_project_state(self):
        service = _service()
        service.commit_patch(
            service.begin_session(),
            {
                NEW_FIGURE_WIDTH_IN: 10.0,
                NEW_FIGURE_HEIGHT_IN: 7.5,
                NEW_FIGURE_DOCUMENT_DPI: 150,
            },
        )
        payload = snapshot_to_payload(
            service.snapshot(),
            production_settings_registry(),
        )
        self.assertNotIn("id", payload)
        self.assertIn("components", payload)
        self.assertNotIn("id", payload["components"])
        self.assertEqual(
            payload["components"]["line"]["color"],
            {"kind": "inherit", "value": "#1F77B4"},
        )
        self.assertEqual(payload["new_figure"]["width_in"], 10.0)
        self.assertEqual(
            service.new_figure_defaults().document_dpi,
            150.0,
        )

    def test_same_version_unknown_fields_are_read_only(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        committed = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.LIGHT},
        )
        self.assertTrue(committed.success)
        stored = dict(port.payload)
        appearance = dict(stored["appearance"])
        appearance["future_only_field"] = True
        stored["appearance"] = appearance
        port.payload = stored
        commits = port.commit_calls
        service.reload()
        self.assertEqual(service.health(), SettingsHealth.READ_ONLY_FUTURE)
        self.assertFalse(service.writable())
        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertFalse(result.success)
        self.assertIn("not writable", (result.error or "").casefold())
        self.assertEqual(port.commit_calls, commits)
        self.assertEqual(port.payload["appearance"]["future_only_field"], True)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.LIGHT)

    def test_storage_migrator_camelcase_layout_is_accepted(self):
        port = MemorySettingsDocumentPort(
            {
                "appearance": {
                    "theme_mode": "light",
                    "ui_font_point_size": 9,
                    "density": "standard",
                },
                "workspace": {
                    "remember_layout": True,
                    "layout": {
                        "version": 2,
                        "outerSplitterSizes": [640, 640],
                        "innerSplitterSizes": [330, 260],
                        "explorerMode": "components",
                        "explorerVisible": False,
                    },
                },
                "export": {
                    "pad_inches": 0.1,
                    "metadata": {"Title": "Legacy"},
                },
            }
        )
        snapshot = _service(document=port).snapshot()
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.LIGHT)
        self.assertEqual(snapshot.workspace.layout.outer_splitter_sizes, (640, 640))
        self.assertEqual(snapshot.workspace.layout.explorer_mode.value, "components")
        self.assertFalse(snapshot.workspace.layout.explorer_visible)
        self.assertEqual(snapshot.export.pad_inches.kind, PadInchesKind.NUMERIC)
        self.assertEqual(snapshot.export.metadata.fields["Title"], "Legacy")

    def test_dual_slot_result_shapes_are_duck_typed(self):
        class _Load:
            payload = {"appearance": {"theme_mode": "dark"}}
            revision = 5
            health = "normal"
            diagnostics = ()
            migrated_from_legacy = False

        class _Commit:
            def __init__(self):
                self.payloads = []
                self.fail = False

            def load(self):
                return _Load()

            def commit(self, payload):
                self.payloads.append(payload)
                if self.fail:
                    return type("R", (), {"ok": False, "error": "slot busy"})()
                return type("R", (), {"ok": True, "revision": 6, "warning": None})()

        port = _Commit()
        service = ApplicationSettingsService(document=port)
        self.assertEqual(service.snapshot().revision, 5)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.DARK)

        port.fail = True
        blocked = service.commit_patch(
            service.begin_session(),
            {EXPORT_FORMAT: "pdf"},
        )
        self.assertFalse(blocked.success)
        self.assertIn("slot busy", blocked.error or "")
        self.assertEqual(service.snapshot().revision, 5)
        self.assertEqual(
            service.snapshot().export.format,
            ExportFormatPreference.PNG,
        )

        port.fail = False
        ok = service.commit_patch(
            service.begin_session(),
            {EXPORT_FORMAT: "svg"},
        )
        self.assertTrue(ok.success)
        self.assertEqual(service.snapshot().revision, 6)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.SVG)

    def test_reset_export_does_not_write_until_commit(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        service.commit_patch(
            service.begin_session(),
            {EXPORT_FORMAT: "jpeg", EXPORT_CUSTOM_DPI: 180.0},
        )
        session = service.begin_session()
        draft = service.reset_section(session, PAGE_EXPORT)
        self.assertTrue(draft.success)
        self.assertEqual(port.commit_calls, 1)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.JPEG)
        self.assertEqual(session.dirty_patch()[EXPORT_FORMAT], ExportFormatPreference.PNG)
        committed = service.commit_patch(session, {})
        self.assertTrue(committed.success)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.PNG)
        self.assertEqual(service.snapshot().export.custom_dpi, 100.0)

    def test_reset_all_preferences_is_draft_only_and_covers_every_page(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        service.commit_patch(
            service.begin_session(),
            {
                APPEARANCE_THEME_MODE: ThemeMode.DARK,
                EXPORT_FORMAT: "jpeg",
                NEW_FIGURE_WIDTH_IN: 8.0,
            },
        )
        session = service.begin_session()
        session.stage(EXPORT_CUSTOM_DPI, 180.0)
        draft = service.reset_all_preferences(session)
        self.assertTrue(draft.success)
        self.assertEqual(port.commit_calls, 1)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(
            session.dirty_patch()[APPEARANCE_THEME_MODE],
            ThemeMode.SYSTEM,
        )
        self.assertEqual(session.dirty_patch()[EXPORT_FORMAT], ExportFormatPreference.PNG)
        self.assertEqual(session.dirty_patch()[NEW_FIGURE_WIDTH_IN], 6.4)
        self.assertNotIn(EXPORT_CUSTOM_DPI, session.dirty_patch())
        committed = service.commit_patch(session, {})
        self.assertTrue(committed.success)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.PNG)
        self.assertEqual(service.snapshot().new_figure.width_in, 6.4)


class WorkspaceLayoutPortTests(unittest.TestCase):
    def test_bind_wraps_memory_document_and_skips_default_restore(self):
        document = MemorySettingsDocumentPort()
        service, port = bind_workspace_layout_port(settings_service=document)
        self.assertIsInstance(service, ApplicationSettingsService)
        self.assertTrue(port.remember_layout())
        self.assertIsNone(port.layout_to_restore())

    def test_save_layout_round_trips_and_remember_false_hides_restore(self):
        service = _service()
        port = service.workspace_layout_port()
        layout = WorkspaceLayoutPayload(
            version=2,
            outer_splitter_sizes=(640, 640),
            inner_splitter_sizes=(330, 260),
            explorer_mode=WorkspaceExplorerMode.COMPONENTS,
            explorer_visible=False,
        )
        result = port.save_layout(layout)
        self.assertTrue(result.success)
        self.assertEqual(port.layout_to_restore(), layout)

        disabled = service.commit_patch(
            service.begin_session(),
            {WORKSPACE_REMEMBER_LAYOUT: False},
        )
        self.assertTrue(disabled.success)
        self.assertFalse(port.remember_layout())
        self.assertIsNone(port.layout_to_restore())
        self.assertEqual(service.snapshot().workspace.layout, layout)

    def test_save_layout_failure_leaves_snapshot_unchanged(self):
        document = MemorySettingsDocumentPort()
        service = _service(document=document)
        port = service.workspace_layout_port()
        layout = WorkspaceLayoutPayload(
            version=2,
            outer_splitter_sizes=(640, 640),
            inner_splitter_sizes=(330, 260),
            explorer_mode=WorkspaceExplorerMode.COMPONENTS,
            explorer_visible=False,
        )
        self.assertTrue(port.save_layout(layout).success)
        revision = service.snapshot().revision
        document.fail_commit = True
        failed = port.save_layout(
            WorkspaceLayoutPayload(
                version=2,
                outer_splitter_sizes=(500, 500),
                inner_splitter_sizes=(200, 200),
                explorer_mode=WorkspaceExplorerMode.TABLE,
                explorer_visible=True,
            )
        )
        self.assertFalse(failed.success)
        self.assertEqual(service.snapshot().revision, revision)
        self.assertEqual(service.snapshot().workspace.layout, layout)

    def test_normal_dual_slot_diagnostics_do_not_produce_load_warning(self):
        class _HealthyDualSlotDocument:
            def load(self):
                from mygui.application_settings.storage.types import DocumentHealth, DocumentLoadResult
                return DocumentLoadResult(
                    health=DocumentHealth.NORMAL,
                    revision=9,
                    payload={},
                    source_slot="slotA",
                    diagnostics=(
                        "slotA: valid_current revision=9 schema_version=1",
                        "slotB: valid_current revision=8 schema_version=1",
                    ),
                )

        service = ApplicationSettingsService(document=_HealthyDualSlotDocument())
        self.assertEqual(service.health(), SettingsHealth.OK)
        self.assertIsNone(service._load_warning)
        result = service.commit_patch(service.begin_session())
        self.assertTrue(result.success)
        self.assertIsNone(result.warning)

    def test_degraded_dual_slot_diagnostics_produce_load_warning(self):
        class _DegradedDualSlotDocument:
            def load(self):
                from mygui.application_settings.storage.types import DocumentHealth, DocumentLoadResult
                return DocumentLoadResult(
                    health=DocumentHealth.DEGRADED,
                    revision=9,
                    payload={},
                    source_slot="slotA",
                    diagnostics=(
                        "slotA: valid_current revision=9 schema_version=1",
                        "slotB: corrupt (sha256 mismatch)",
                        "using slotA; the next successful commit will repair the corrupt companion slot",
                    ),
                )

        service = ApplicationSettingsService(document=_DegradedDualSlotDocument())
        self.assertEqual(service.health(), SettingsHealth.DEGRADED)
        self.assertIsNotNone(service._load_warning)
        self.assertIn("corrupt", service._load_warning)


if __name__ == "__main__":
    unittest.main()
