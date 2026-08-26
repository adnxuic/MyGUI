import json
import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mygui.application_settings import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    EXPORT_CUSTOM_DPI,
    EXPORT_FORMAT,
    EXPORT_METADATA,
    EXPORT_PAD_INCHES,
    EXPORT_USE_PROJECT_DPI,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_APPEARANCE,
    PAGE_AXES_COMPONENTS,
    PAGE_COMPONENTS,
    PAGE_EXPORT,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
    ApplicationSettingsService,
    ApplicationSettingsSnapshot,
    Density,
    ExportFormatPreference,
    MemorySettingsDocumentPort,
    PadInchesKind,
    RecordingRuntimeBinder,
    SettingEditorKind,
    SettingEffect,
    SettingsHealth,
    SettingsRuntimeApplier,
    SettingsSession,
    SettingsValidationError,
    ThemeMode,
    WORKSPACE_LAYOUT,
    WORKSPACE_REMEMBER_LAYOUT,
    production_settings_registry,
)
from mygui.application_settings.document import (
    FORBIDDEN_PAYLOAD_KEYS,
    snapshot_to_payload,
)
from mygui.application_settings.values import workspace_layout_to_wire


def _service(**kwargs) -> ApplicationSettingsService:
    if "document" not in kwargs:
        kwargs["document"] = MemorySettingsDocumentPort()
    return ApplicationSettingsService(**kwargs)


class ApplicationSettingsSessionTests(unittest.TestCase):
    def test_session_stores_only_dirty_patch_and_base_revision(self):
        service = _service()
        session = service.begin_session()
        self.assertIsInstance(session, SettingsSession)
        self.assertEqual(session.base_revision, 0)
        self.assertFalse(session.is_dirty())
        self.assertEqual(dict(session.dirty_patch()), {})
        self.assertFalse(hasattr(session, "snapshot"))
        self.assertFalse(hasattr(session, "_snapshot"))
        self.assertFalse(hasattr(session, "appearance"))
        self.assertIn("_dirty", SettingsSession.__slots__)
        self.assertIn("base_revision", SettingsSession.__slots__)
        self.assertNotIn("appearance", SettingsSession.__slots__)

        session.stage(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self.assertEqual(
            dict(session.dirty_patch()),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)

    def test_disjoint_external_changes_are_rebased_then_committed(self):
        service = _service()
        first = service.begin_session()
        second = service.begin_session()
        written = service.commit_patch(second, {EXPORT_FORMAT: "pdf"})
        self.assertTrue(written.success)
        self.assertEqual(service.snapshot().revision, 1)
        self.assertEqual(
            service.snapshot().export.format,
            ExportFormatPreference.PDF,
        )

        rebased = service.commit_patch(first, {APPEARANCE_THEME_MODE: "dark"})
        self.assertTrue(rebased.success)
        self.assertFalse(rebased.conflicts)
        snapshot = service.snapshot()
        self.assertEqual(snapshot.revision, 2)
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(snapshot.export.format, ExportFormatPreference.PDF)
        self.assertEqual(first.base_revision, 2)
        self.assertFalse(first.is_dirty())

    def test_same_key_conflict_rejects_and_resyncs_session(self):
        service = _service()
        first = service.begin_session()
        second = service.begin_session()
        first.stage(APPEARANCE_THEME_MODE, "dark")
        first.stage(EXPORT_FORMAT, "svg")
        committed = service.commit_patch(second, {APPEARANCE_THEME_MODE: "light"})
        self.assertTrue(committed.success)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.LIGHT)

        events: list[ApplicationSettingsSnapshot] = []
        service.subscribe(events.append)
        rejected = service.commit_patch(first, {APPEARANCE_THEME_MODE: "dark"})
        self.assertFalse(rejected.success)
        self.assertEqual(rejected.conflicts, (APPEARANCE_THEME_MODE,))
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.LIGHT)
        self.assertEqual(service.snapshot().revision, 1)
        self.assertEqual(len(events), 0)
        self.assertEqual(first.base_revision, 1)
        self.assertNotIn(APPEARANCE_THEME_MODE, first.dirty_patch())
        self.assertEqual(
            first.dirty_patch()[EXPORT_FORMAT],
            ExportFormatPreference.SVG,
        )

    def test_stale_session_from_another_service_is_rejected(self):
        owner = _service()
        other = _service()
        session = owner.begin_session()
        session.stage(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        with self.assertRaises(SettingsValidationError):
            other.commit_patch(session, {})
        self.assertEqual(owner.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(other.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)

    def test_future_base_revision_conflicts_and_resyncs(self):
        service = _service()
        session = service.begin_session()
        session.stage(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        session.base_revision = 99
        result = service.commit_patch(session, {})
        self.assertFalse(result.success)
        self.assertEqual(result.conflicts, (APPEARANCE_THEME_MODE,))
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(session.base_revision, 0)
        self.assertEqual(dict(session.dirty_patch()), {})

    def test_reset_section_only_changes_session_draft(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        session = service.begin_session()
        committed = service.commit_patch(
            session,
            {
                APPEARANCE_THEME_MODE: ThemeMode.DARK,
                APPEARANCE_UI_FONT_POINT_SIZE: 12,
                APPEARANCE_DENSITY: Density.COMPACT,
            },
        )
        self.assertTrue(committed.success)
        self.assertEqual(port.commit_calls, 1)
        payload_after_commit = dict(port.payload)

        draft = service.begin_session()
        draft.stage(NEW_FIGURE_WIDTH_IN, 8.0)
        result = service.reset_section(draft, PAGE_APPEARANCE)
        self.assertTrue(result.success)
        self.assertEqual(port.commit_calls, 1)
        self.assertEqual(port.payload, payload_after_commit)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(service.snapshot().appearance.ui_font_point_size, 12)
        self.assertEqual(
            dict(draft.dirty_patch())[APPEARANCE_THEME_MODE],
            ThemeMode.SYSTEM,
        )
        self.assertEqual(draft.dirty_patch()[APPEARANCE_UI_FONT_POINT_SIZE], 9)
        self.assertEqual(draft.dirty_patch()[APPEARANCE_DENSITY], Density.STANDARD)
        self.assertEqual(draft.dirty_patch()[NEW_FIGURE_WIDTH_IN], 8.0)
        self.assertEqual(service.snapshot().new_figure.width_in, 6.4)

        events: list[object] = []
        service.subscribe(lambda _snapshot: events.append(True))
        service.reset_section(draft, PAGE_NEW_FIGURE)
        self.assertEqual(len(events), 0)
        self.assertNotIn(NEW_FIGURE_WIDTH_IN, draft.dirty_patch())
        self.assertEqual(service.snapshot().revision, 1)


class ApplicationSettingsServiceTests(unittest.TestCase):
    def test_fresh_defaults_are_system_nine_standard_and_style_figure_sizes(self):
        snapshot = _service().snapshot()
        self.assertEqual(snapshot.appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(snapshot.appearance.ui_font_point_size, 9)
        self.assertEqual(snapshot.appearance.density, Density.STANDARD)
        self.assertTrue(snapshot.workspace.remember_layout)
        self.assertEqual(snapshot.workspace.layout.version, 2)
        self.assertEqual(snapshot.new_figure.width_in, 6.4)
        self.assertEqual(snapshot.new_figure.height_in, 4.8)
        self.assertEqual(snapshot.new_figure.document_dpi, 100.0)
        self.assertEqual(snapshot.export.format, ExportFormatPreference.PNG)
        self.assertTrue(snapshot.export.use_project_dpi)
        self.assertEqual(snapshot.export.custom_dpi, 100.0)
        self.assertEqual(snapshot.export.pad_inches.kind, PadInchesKind.NUMERIC)
        self.assertEqual(snapshot.export.pad_inches.inches, 0.1)

    def test_normalizer_rejects_illegal_font_density_and_theme(self):
        service = _service()
        session = service.begin_session()
        font = service.commit_patch(session, {APPEARANCE_UI_FONT_POINT_SIZE: 7})
        self.assertFalse(font.success)
        self.assertIn("font", (font.error or "").lower())

        too_big = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: 17},
        )
        self.assertFalse(too_big.success)

        bool_size = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: True},
        )
        self.assertFalse(bool_size.success)

        density = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_DENSITY: "huge"},
        )
        self.assertFalse(density.success)
        self.assertIn("Density", density.error or "")

        theme = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: "solarized"},
        )
        self.assertFalse(theme.success)
        self.assertIn("Theme", theme.error or "")
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(service.snapshot().revision, 0)

        registry = production_settings_registry()
        with self.assertRaises(SettingsValidationError):
            registry.spec(APPEARANCE_UI_FONT_POINT_SIZE).normalize(9.5)
        with self.assertRaises(SettingsValidationError):
            registry.spec(APPEARANCE_THEME_MODE).normalize("LIGHT")
        with self.assertRaises(SettingsValidationError):
            registry.spec(WORKSPACE_LAYOUT).normalize({"version": 2})

    def test_runtime_apply_success_then_document_commit(self):
        port = MemorySettingsDocumentPort()
        binder = RecordingRuntimeBinder("theme")
        service = _service(
            document=port,
            runtime_applier=SettingsRuntimeApplier([binder]),
        )
        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertTrue(result.success)
        self.assertEqual([action[0] for action in binder.actions], ["apply", "confirm"])
        self.assertEqual(binder.actions[0][1][1], frozenset({APPEARANCE_THEME_MODE}))
        self.assertEqual(port.commit_calls, 1)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.DARK)

        export_binder = RecordingRuntimeBinder("export")
        export_service = _service(
            document=MemorySettingsDocumentPort(),
            runtime_applier=SettingsRuntimeApplier([export_binder]),
        )
        next_use = export_service.commit_patch(
            export_service.begin_session(),
            {EXPORT_FORMAT: "tiff"},
        )
        self.assertTrue(next_use.success)
        self.assertEqual(export_binder.actions, [])

    def test_runtime_apply_failure_rolls_back_and_skips_disk(self):
        port = MemorySettingsDocumentPort()
        first = RecordingRuntimeBinder("first")
        second = RecordingRuntimeBinder("second", fail_apply=True)
        service = _service(
            document=port,
            runtime_applier=SettingsRuntimeApplier([first, second]),
        )
        events: list[object] = []
        service.subscribe(events.append)
        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_DENSITY: Density.COMFORTABLE},
        )
        self.assertFalse(result.success)
        self.assertIn("second apply failed", result.error or "")
        self.assertEqual(service.snapshot().appearance.density, Density.STANDARD)
        self.assertEqual(service.snapshot().revision, 0)
        self.assertEqual(port.commit_calls, 0)
        self.assertIsNone(port.payload)
        self.assertEqual(len(events), 0)
        self.assertEqual([action[0] for action in first.actions], ["apply", "rollback"])
        self.assertEqual([action[0] for action in second.actions], [])
        self.assertEqual(result.health, SettingsHealth.OK)

    def test_rollback_failure_is_uncertain_and_not_success(self):
        port = MemorySettingsDocumentPort()
        binder = RecordingRuntimeBinder("live", fail_rollback=True)
        service = _service(
            document=port,
            runtime_applier=SettingsRuntimeApplier([binder]),
        )
        port.fail_commit = True
        result = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_UI_FONT_POINT_SIZE: 11},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.health, SettingsHealth.UNCERTAIN)
        self.assertEqual(service.health(), SettingsHealth.UNCERTAIN)
        self.assertEqual(service.snapshot().appearance.ui_font_point_size, 9)
        self.assertEqual(service.snapshot().revision, 0)
        self.assertIsNone(port.payload)
        self.assertIn("rollback", (result.error or "").lower())

    def test_events_emit_exactly_once_on_success_never_on_failure(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        events: list[int] = []
        unsubscribe = service.subscribe(
            lambda snapshot: events.append(snapshot.revision)
        )

        failed = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: "nope"},
        )
        self.assertFalse(failed.success)
        self.assertEqual(events, [])

        port.fail_commit = True
        stored_fail = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertFalse(stored_fail.success)
        self.assertEqual(events, [])
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)

        port.fail_commit = False
        ok = service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertTrue(ok.success)
        self.assertTrue(ok.event_emitted)
        self.assertEqual(events, [1])

        unsubscribe()
        service.commit_patch(
            service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.LIGHT},
        )
        self.assertEqual(events, [1])

    def test_storage_failure_leaves_memory_snapshot_unchanged(self):
        port = MemorySettingsDocumentPort()
        service = _service(document=port)
        before = service.snapshot()
        port.fail_commit = True
        result = service.commit_patch(
            service.begin_session(),
            {
                NEW_FIGURE_WIDTH_IN: 8.0,
                NEW_FIGURE_HEIGHT_IN: 6.0,
                NEW_FIGURE_DOCUMENT_DPI: 120.0,
            },
        )
        self.assertFalse(result.success)
        self.assertEqual(service.snapshot(), before)
        self.assertEqual(service.snapshot().new_figure.width_in, 6.4)
        self.assertIsNone(port.payload)

        port.fail_commit = False
        port.raise_on_commit = RuntimeError("disk full")
        raised = service.commit_patch(
            service.begin_session(),
            {EXPORT_CUSTOM_DPI: 200.0},
        )
        self.assertFalse(raised.success)
        self.assertIn("disk full", raised.error or "")
        self.assertEqual(service.snapshot().export.custom_dpi, 100.0)
        self.assertTrue(service.snapshot().export.use_project_dpi)
        self.assertIsNone(port.payload)

    def test_serialized_payload_has_no_ui_widget_or_callback(self):
        service = _service()
        session = service.begin_session()
        layout = workspace_layout_to_wire(service.snapshot().workspace.layout)
        committed = service.commit_patch(
            session,
            {
                APPEARANCE_THEME_MODE: "dark",
                WORKSPACE_REMEMBER_LAYOUT: False,
                WORKSPACE_LAYOUT: layout,
                EXPORT_USE_PROJECT_DPI: False,
                EXPORT_CUSTOM_DPI: 150.0,
                EXPORT_PAD_INCHES: {"kind": "layout"},
                EXPORT_METADATA: {
                    "kind": "export_metadata",
                    "fields": {"Title": "Chart", "Author": "Ada"},
                },
            },
        )
        self.assertTrue(committed.success)
        payload = service.document_payload()
        encoded = json.dumps(payload)
        self.assertIsInstance(encoded, str)
        self.assertNotIn("callback", encoded)
        self.assertNotIn("QWidget", encoded)
        self.assertNotIn("normalizer", encoded)
        self.assertEqual(payload["appearance"]["theme_mode"], "dark")
        self.assertEqual(payload["export"]["use_project_dpi"], False)
        self.assertEqual(payload["export"]["custom_dpi"], 150.0)
        self.assertEqual(payload["export"]["pad_inches"], {"kind": "layout"})
        self.assertEqual(
            payload["export"]["metadata"],
            {"kind": "export_metadata", "fields": {"Title": "Chart", "Author": "Ada"}},
        )
        self.assertEqual(payload["workspace"]["layout"]["kind"], "workspace_layout_v2")
        self.assertEqual(payload["workspace"]["layout"]["version"], 2)
        self._assert_data_only(payload)

        registry = production_settings_registry()
        round_trip = snapshot_to_payload(service.snapshot(), registry)
        self.assertEqual(round_trip, payload)
        for spec in registry.persistent_specs():
            self.assertIsNot(spec.editor, SettingEditorKind.ACTION)
            self.assertNotEqual(spec.editor.value, "json")
            self.assertTrue(spec.persistent)
            self.assertIsNotNone(spec.normalizer)
            self.assertIsNotNone(spec.validator)
            self.assertTrue(spec.migration)

    def test_use_project_dpi_is_independent_of_custom_dpi(self):
        service = _service()
        result = service.commit_patch(
            service.begin_session(),
            {
                EXPORT_USE_PROJECT_DPI: True,
                EXPORT_CUSTOM_DPI: 220.0,
            },
        )
        self.assertTrue(result.success)
        export = service.snapshot().export
        self.assertTrue(export.use_project_dpi)
        self.assertEqual(export.custom_dpi, 220.0)
        payload = service.document_payload()
        self.assertTrue(payload["export"]["use_project_dpi"])
        self.assertEqual(payload["export"]["custom_dpi"], 220.0)

    def test_narrow_ports_do_not_expose_the_service(self):
        service = _service()
        service.commit_patch(
            service.begin_session(),
            {NEW_FIGURE_WIDTH_IN: 7.2, EXPORT_FORMAT: "svg"},
        )
        figure = service.new_figure_defaults_provider()
        components = service.component_defaults_provider()
        export = service.export_preferences_port()
        workspace = service.workspace_layout_port()
        self.assertEqual(figure.current().width_in, 7.2)
        self.assertEqual(components.current().line.color.mode.value, "inherit")
        self.assertEqual(export.current().format, ExportFormatPreference.SVG)
        self.assertTrue(workspace.remember_layout())
        self.assertFalse(hasattr(figure, "commit_patch"))
        self.assertFalse(hasattr(components, "commit_patch"))
        self.assertFalse(hasattr(components, "begin_session"))
        self.assertFalse(hasattr(export, "begin_session"))
        self.assertTrue(callable(getattr(export, "commit")))
        self.assertFalse(hasattr(workspace, "commit_patch"))
        self.assertFalse(hasattr(workspace, "begin_session"))

    def test_export_preferences_port_commit_updates_snapshot(self):
        service = _service()
        port = service.export_preferences_port()
        updated = replace(
            port.current(),
            format=ExportFormatPreference.PDF,
            custom_dpi=144.0,
            use_project_dpi=True,
        )
        result = port.commit(updated)
        self.assertTrue(result.success)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.PDF)
        self.assertEqual(port.current().custom_dpi, 144.0)
        self.assertTrue(port.current().use_project_dpi)
        self.assertFalse(hasattr(port, "commit_patch"))

    def test_export_preferences_port_commit_failure_leaves_snapshot(self):
        document = MemorySettingsDocumentPort()
        service = _service(document=document)
        service.commit_patch(
            service.begin_session(),
            {EXPORT_FORMAT: "svg"},
        )
        export = service.export_preferences_port()
        document.fail_commit = True
        result = export.commit(
            replace(export.current(), format=ExportFormatPreference.PDF)
        )
        self.assertFalse(result.success)
        self.assertEqual(export.current().format, ExportFormatPreference.SVG)
        self.assertEqual(service.snapshot().export.format, ExportFormatPreference.SVG)

    def test_production_registry_covers_persisted_pages(self):
        registry = production_settings_registry()
        self.assertEqual(
            [page.page_id for page in registry.pages],
            [
                PAGE_APPEARANCE,
                PAGE_WORKSPACE,
                PAGE_NEW_FIGURE,
                PAGE_COMPONENTS,
                PAGE_AXES_COMPONENTS,
                PAGE_EXPORT,
            ],
        )
        live = {
            spec.key
            for spec in registry.persistent_specs()
            if spec.effect is SettingEffect.LIVE_REVERSIBLE
        }
        next_use = {
            spec.key
            for spec in registry.persistent_specs()
            if spec.effect is SettingEffect.NEXT_USE
        }
        restart = {
            spec.key
            for spec in registry.persistent_specs()
            if spec.effect is SettingEffect.RESTART_REQUIRED
        }
        self.assertEqual(
            live,
            {
                APPEARANCE_THEME_MODE,
                APPEARANCE_UI_FONT_POINT_SIZE,
                APPEARANCE_DENSITY,
            },
        )
        self.assertIn(EXPORT_FORMAT, next_use)
        self.assertIn(NEW_FIGURE_WIDTH_IN, next_use)
        self.assertIn(WORKSPACE_LAYOUT, next_use)
        self.assertEqual(restart, set())
        self.assertEqual(live | next_use | restart, set(registry.keys()))

    def _assert_data_only(self, payload) -> None:
        stack = [payload]
        while stack:
            item = stack.pop()
            if callable(item) and not isinstance(item, (str, bytes)):
                self.fail(f"payload contains callable {item!r}")
            if isinstance(item, dict):
                for key, value in item.items():
                    self.assertNotIn(key, FORBIDDEN_PAYLOAD_KEYS)
                    stack.append(value)
            elif isinstance(item, (list, tuple)):
                stack.extend(item)


if __name__ == "__main__":
    unittest.main()
