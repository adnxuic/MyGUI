"""Export, Integrations, and Maintenance Settings Center page tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mygui.application_settings import (
    APPEARANCE_THEME_MODE,
    ApplicationSettingsService,
    COMPONENTS_LINE_LINEWIDTH,
    DefaultValueMode,
    EXPORT_CUSTOM_DPI,
    EXPORT_FORMAT,
    EXPORT_USE_PROJECT_DPI,
    ExportBBoxInches,
    ExportFormatPreference,
    ExportMetadata,
    ExportSettings,
    InheritableValue,
    JpegSubsampling,
    PadInchesKind,
    PadInchesValue,
    ThemeMode,
    TiffCompression,
)
from mygui.application_settings.document import flatten_snapshot
from mygui.application_settings.keys import PAGE_EXPORT, PAGE_INTEGRATIONS, PAGE_MAINTENANCE
from mygui.application_settings.storage import (
    APPLICATION_SETTINGS_GROUP,
    SLOT_A,
    SLOT_B,
    DocumentHealth,
    create_settings_backend,
    document_health_label,
    slot_key,
)
from mygui.application_settings.storage.envelope import EnvelopeCodec
from mygui.application_settings.storage.keys import SCHEMA_APPLICATION_SETTINGS
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.settings_center import (
    ExportSettingsPage,
    IntegrationStatus,
    IntegrationsSettingsPage,
    MaintenanceSettingsPage,
    SHELL_PAGE_ORDER,
    SettingsPageRegistry,
    page_specs,
    register_all_pages,
    register_c_pages,
)
from mygui.widgets.settings_center.maintenance_page import (
    CLEAR_RECENT_TITLE,
    IMMEDIATE_RESET_TITLE,
    RESET_ALL_TITLE,
    RESET_COLOR_STORAGE_TITLE,
    RESET_LIBRARY_TITLE,
)
from mygui.widgets.settings_center.pages import SettingsCenterPageSpec


UNAVAILABLE = IntegrationStatus(
    available=False,
    session_state="Disabled this session",
    diagnostic_summary="mocked unavailable",
)


class _Confirm:
    def __init__(self, allowed=()):
        self.allowed = set(allowed)
        self.calls: list[str] = []

    def __call__(self, title: str, text: str) -> bool:
        self.calls.append(title)
        return title in self.allowed


class _FakeHost:
    def __init__(self, service, session, confirm=None):
        self.service = service
        self.session = session
        self.confirm = confirm
        self.messages: list[tuple[str, str]] = []
        self.reload_hooks: list = []
        self.commands: list[str] = []
        self.stage_batches: list[dict] = []

    def draft_value(self, key: str):
        return self.draft_values((key,))[key]

    def draft_values(self, keys=None):
        values = flatten_snapshot(self.service.snapshot())
        values.update(self.session.dirty_patch())
        if keys is None:
            return values
        return {key: values[key] for key in keys}

    def stage_value(self, key: str, value) -> None:
        self.stage_values({key: value})

    def stage_values(self, mapping) -> None:
        self.stage_batches.append(dict(mapping))
        for key, value in mapping.items():
            self.session.stage(key, value)

    def request_immediate_command(
        self,
        command_id: str,
        *,
        title: str,
        text: str,
        handler,
        confirm: bool = True,
    ) -> None:
        self.commands.append(command_id)
        if confirm and self.confirm is not None and not self.confirm(title, text):
            return
        handler()

    def emit_message(self, text: str, level: str = "info") -> None:
        self.messages.append((str(text), str(level)))

    def bind_draft_reloaded(self, callback) -> None:
        self.reload_hooks.append(callback)

    def reset_all_preferences(self) -> None:
        self.service.reset_all_preferences(self.session)
        for hook in self.reload_hooks:
            hook()

    def apply_storage_reset(self) -> None:
        self.session._clear_dirty()
        self.session.base_revision = self.service.snapshot().revision
        for hook in self.reload_hooks:
            hook()


class DocumentHealthLabelTests(unittest.TestCase):
    def test_closed_health_states_map_to_settings_copy(self):
        expected = {
            DocumentHealth.NORMAL: "Normal",
            DocumentHealth.DEGRADED: "Degraded",
            DocumentHealth.READ_ONLY_FUTURE: "Read-only future",
            DocumentHealth.RECOVERY_REQUIRED: "Recovery required",
            DocumentHealth.WRITE_UNCERTAIN: "Write uncertain",
        }
        self.assertEqual(set(expected), set(DocumentHealth))
        for health, label in expected.items():
            self.assertEqual(document_health_label(health), label)
            self.assertEqual(document_health_label(health.value), label)


class ExportSettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_export_page_round_trips_export_settings(self):
        service = ApplicationSettingsService()
        session = service.begin_session()
        host = _FakeHost(service, session)
        original = ExportSettings(
            format=ExportFormatPreference.PDF,
            last_directory=str(Path.cwd()),
            use_project_dpi=True,
            custom_dpi=220.0,
            transparent=True,
            facecolor="#112233",
            edgecolor="auto",
            bbox_inches=ExportBBoxInches.TIGHT,
            pad_inches=PadInchesValue(kind=PadInchesKind.LAYOUT, inches=None),
            png_compress_level=3,
            png_optimize=True,
            jpeg_quality=40,
            jpeg_optimize=True,
            jpeg_progressive=True,
            jpeg_subsampling=JpegSubsampling.FOUR_TWO_ZERO,
            tiff_compression=TiffCompression.LZW,
            webp_lossless=True,
            webp_quality=70,
            webp_alpha_quality=80,
            webp_method=2,
            webp_exact=True,
            metadata=ExportMetadata(fields={"Title": "Chart", "Creator": "MyGUI"}),
        )
        page = ExportSettingsPage(
            ColorLibrary(),
            host=host,
            session=session,
            export=original,
            document_dpi=150.0,
        )
        self.addCleanup(page.deleteLater)
        loaded = page.export_settings()
        self.assertEqual(loaded.format, original.format)
        self.assertEqual(loaded.last_directory, original.last_directory)
        self.assertTrue(loaded.use_project_dpi)
        self.assertEqual(loaded.custom_dpi, 220.0)
        self.assertTrue(loaded.transparent)
        self.assertEqual(loaded.facecolor, "#112233")
        self.assertEqual(loaded.bbox_inches, ExportBBoxInches.TIGHT)
        self.assertEqual(loaded.pad_inches.kind, PadInchesKind.LAYOUT)
        self.assertEqual(loaded.metadata.fields["Title"], "Chart")
        self.assertIn("strategy only", page.dpi_strategy_hint.text())
        self.assertTrue(page.panel.use_project_dpi.isChecked())
        self.assertFalse(page.panel.dpi_spin.isEnabled())

        page.panel.custom_dpi.setChecked(True)
        self.assertEqual(len(host.stage_batches), 1)
        self.assertIn(EXPORT_USE_PROJECT_DPI, host.stage_batches[0])
        page.panel.format_combo.setCurrentIndex(
            page.panel.format_combo.findData("png")
        )
        patch = dict(session.dirty_patch())
        self.assertEqual(patch[EXPORT_FORMAT], ExportFormatPreference.PNG)
        self.assertFalse(patch[EXPORT_USE_PROJECT_DPI])
        self.assertEqual(patch[EXPORT_CUSTOM_DPI], 220.0)
        self.assertEqual(page.page_spec().page_id, PAGE_EXPORT)


class IntegrationsSettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unavailable_tex_and_matlab_still_open_the_page(self):
        with patch("mygui.tex_config.validate_tex_runtime") as tex_probe, patch(
            "mygui.database.matlab_adapter.ensure_matlab_available_isolated"
        ) as matlab_probe, patch(
            "mygui.database.matlab_adapter.ensure_matlab_available"
        ) as matlab_import:
            page = IntegrationsSettingsPage(
                tex_status=UNAVAILABLE,
                matlab_status=UNAVAILABLE,
            )
            self.addCleanup(page.deleteLater)
            tex_probe.assert_not_called()
            matlab_probe.assert_not_called()
            matlab_import.assert_not_called()
        self.assertEqual(page.tex_availability.text(), "Unavailable")
        self.assertEqual(page.matlab_availability.text(), "Unavailable")
        self.assertTrue(page.open_tex_panel_button.isEnabled())
        self.assertTrue(page.open_matlab_panel_button.isEnabled())
        opened = []
        page.openTexPanelRequested.connect(lambda: opened.append("tex"))
        page.openMatlabPanelRequested.connect(lambda: opened.append("matlab"))
        page.open_tex_panel_button.click()
        page.open_matlab_panel_button.click()
        self.assertEqual(opened, ["tex", "matlab"])
        self.assertEqual(page.page_spec().page_id, PAGE_INTEGRATIONS)
        text = Path(__file__).resolve().parents[1].joinpath(
            "mygui/widgets/settings_center/integrations_page.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("PyTexWindow", text)
        self.assertNotIn("PyMatlabWindow", text)
        self.assertNotIn("fig_control_window", text)

    def test_default_probes_do_not_start_runtimes_when_unavailable(self):
        with patch(
            "mygui.tex_config.validate_tex_runtime",
            side_effect=AssertionError("started TeX"),
        ), patch(
            "mygui.database.matlab_adapter.ensure_matlab_available_isolated",
            side_effect=AssertionError("started MATLAB"),
        ), patch(
            "mygui.tex_config.has_tex_engine",
            return_value=False,
        ), patch(
            "mygui.tex_config.is_tex_enabled",
            return_value=False,
        ), patch(
            "mygui.database.matlab_adapter.is_matlab_enabled",
            return_value=False,
        ), patch(
            "mygui.widgets.settings_center.integrations_status._matlab_runtime_importable",
            return_value=(False, "MATLAB Python runtime is not available."),
        ):
            page = IntegrationsSettingsPage()
            self.addCleanup(page.deleteLater)
        self.assertEqual(page.tex_availability.text(), "Unavailable")
        self.assertEqual(page.matlab_availability.text(), "Unavailable")
        self.assertTrue(page.open_tex_panel_button.isEnabled())


class MaintenanceSettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.ini"
        self.backend = create_settings_backend(file_path=self.path)
        self.service = ApplicationSettingsService(
            document=self.backend.application_settings_port()
        )
        self.library = ColorLibrary(
            document=self.backend.color_library_settings_port()
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_health_labels_follow_document_health(self):
        confirm = _Confirm()
        page = MaintenanceSettingsPage(
            service=self.service,
            session=self.service.begin_session(),
            backend=self.backend,
            color_library=self.library,
            application_health=DocumentHealth.DEGRADED,
            color_health=DocumentHealth.WRITE_UNCERTAIN,
            confirm=confirm,
        )
        self.addCleanup(page.deleteLater)
        self.assertIn("Degraded", page.application_health_label.text())
        self.assertIn("Write uncertain", page.color_health_label.text())
        self.assertFalse(page.reset_all_button.isHidden())
        self.assertTrue(page.reset_incompatible_button.isHidden())
        self.assertFalse(page.clear_recent_button.isEnabled())
        self.assertFalse(page.reset_library_button.isEnabled())
        self.assertTrue(page.reset_color_storage_button.isHidden())
        self.assertIn("Normal or Degraded", page.color_diagnostics_label.text())

        page._application_health = DocumentHealth.RECOVERY_REQUIRED
        page.refresh()
        self.assertIn("Recovery required", page.application_health_label.text())
        self.assertTrue(page.reset_all_button.isHidden())
        self.assertFalse(page.reset_incompatible_button.isHidden())

    def test_reset_all_excludes_color_library_and_is_draft_only(self):
        self.library.record_recent("#FF0000")
        self.library.toggle_favorite_color("#00FF00")
        self.service.commit_patch(
            self.service.begin_session(),
            {
                APPEARANCE_THEME_MODE: ThemeMode.DARK,
                EXPORT_FORMAT: "jpeg",
                COMPONENTS_LINE_LINEWIDTH: InheritableValue(
                    DefaultValueMode.OVERRIDE, 4.0
                ),
            },
        )
        session = self.service.begin_session()
        confirm = _Confirm(allowed=(RESET_ALL_TITLE,))
        page = MaintenanceSettingsPage(
            service=self.service,
            session=session,
            backend=self.backend,
            color_library=self.library,
            confirm=confirm,
        )
        self.addCleanup(page.deleteLater)
        revision = self.service.snapshot().revision
        self.assertTrue(page.reset_all_preferences())
        self.assertEqual(self.library.recent_colors, ["#FF0000"])
        self.assertEqual(self.library.favorite_colors, ["#00FF00"])
        self.assertEqual(self.service.snapshot().revision, revision)
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(
            session.dirty_patch()[APPEARANCE_THEME_MODE],
            ThemeMode.SYSTEM,
        )
        self.assertEqual(session.dirty_patch()[EXPORT_FORMAT], ExportFormatPreference.PNG)
        self.assertEqual(
            session.dirty_patch()[COMPONENTS_LINE_LINEWIDTH].mode,
            DefaultValueMode.INHERIT,
        )

    def test_color_library_commands_require_independent_confirmation(self):
        self.library.record_recent("#ABCDEF")
        palette = self.library.create_custom_palette("Keep", ["red", "blue"])
        confirm = _Confirm()
        page = MaintenanceSettingsPage(
            service=self.service,
            session=self.service.begin_session(),
            backend=self.backend,
            color_library=self.library,
            confirm=confirm,
        )
        self.addCleanup(page.deleteLater)
        self.assertIn("Recent colors: 1", page.color_counts_label.text())
        self.assertFalse(page.clear_recent_colors())
        self.assertEqual(self.library.recent_colors, ["#ABCDEF"])
        self.assertEqual(confirm.calls, [CLEAR_RECENT_TITLE])

        confirm.allowed.add(CLEAR_RECENT_TITLE)
        self.assertTrue(page.clear_recent_colors())
        self.assertEqual(self.library.recent_colors, [])
        self.assertIn(palette.id, self.library.custom_palettes)

        confirm.allowed.clear()
        self.assertFalse(page.reset_color_library())
        self.assertIn(palette.id, self.library.custom_palettes)
        confirm.allowed.add(RESET_LIBRARY_TITLE)
        self.assertTrue(page.reset_color_library())
        self.assertEqual(self.library.custom_palettes, {})
        self.assertIn(CLEAR_RECENT_TITLE, confirm.calls)
        self.assertIn(RESET_LIBRARY_TITLE, confirm.calls)
        self.assertNotIn(RESET_ALL_TITLE, confirm.calls)

    def test_incompatible_reset_is_immediate_and_separate_from_apply(self):
        self.library.record_recent("#123456")
        self.service.commit_patch(
            self.service.begin_session(),
            {EXPORT_FORMAT: "svg"},
        )
        store = self.backend.store
        store.setValue(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_A),
            EnvelopeCodec().encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"side": "a"},
                revision=8,
            ),
        )
        store.setValue(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B),
            EnvelopeCodec().encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"side": "b"},
                revision=8,
            ),
        )
        store.sync()
        self.service.reload()
        session = self.service.begin_session()
        session.stage(EXPORT_FORMAT, ExportFormatPreference.JPEG)
        confirm = _Confirm(allowed=(IMMEDIATE_RESET_TITLE,))
        page = MaintenanceSettingsPage(
            service=self.service,
            session=session,
            backend=self.backend,
            color_library=self.library,
            confirm=confirm,
        )
        self.addCleanup(page.deleteLater)
        self.assertFalse(page.reset_incompatible_button.isHidden())
        self.assertTrue(page.reset_all_button.isHidden())
        self.assertFalse(page.reset_all_preferences())
        self.assertEqual(session.dirty_patch()[EXPORT_FORMAT], ExportFormatPreference.JPEG)
        self.assertTrue(page.reset_incompatible_storage())
        self.assertEqual(dict(session.dirty_patch()), {})
        self.assertEqual(
            self.backend.application_settings_port().load().health,
            DocumentHealth.NORMAL,
        )
        self.assertEqual(
            self.service.snapshot().export.format,
            ExportFormatPreference.PNG,
        )
        self.assertEqual(self.library.recent_colors, ["#123456"])
        self.assertNotIn(RESET_ALL_TITLE, confirm.calls)
        self.assertEqual(page.page_spec().page_id, PAGE_MAINTENANCE)

    def test_color_recovery_does_not_pretend_the_library_is_empty(self):
        from mygui.application_settings.storage import (
            COLOR_LIBRARY_SETTINGS_GROUP,
            SCHEMA_COLOR_LIBRARY_SETTINGS,
        )

        store = self.backend.store
        store.setValue(
            slot_key(COLOR_LIBRARY_SETTINGS_GROUP, SLOT_A),
            EnvelopeCodec().encode(
                schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
                payload={"side": "a"},
                revision=4,
            ),
        )
        store.setValue(
            slot_key(COLOR_LIBRARY_SETTINGS_GROUP, SLOT_B),
            EnvelopeCodec().encode(
                schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
                payload={"side": "b"},
                revision=4,
            ),
        )
        store.sync()
        library = ColorLibrary(document=self.backend.color_library_settings_port())
        self.assertFalse(library.payload_applied())
        self.assertTrue(library.consume_load_warning())
        self.assertEqual(library.document_health(), DocumentHealth.RECOVERY_REQUIRED)
        self.assertFalse(library.writable())
        confirm = _Confirm(allowed=(RESET_COLOR_STORAGE_TITLE,))
        page = MaintenanceSettingsPage(
            service=self.service,
            session=self.service.begin_session(),
            backend=self.backend,
            color_library=library,
            confirm=confirm,
        )
        self.addCleanup(page.deleteLater)
        self.assertIn("not loaded", page.color_counts_label.text().casefold())
        self.assertFalse(page.clear_recent_button.isEnabled())
        self.assertFalse(page.reset_library_button.isEnabled())
        self.assertFalse(page.reset_color_storage_button.isHidden())
        self.assertTrue(page.reset_color_storage_button.isEnabled())
        self.assertFalse(page.reset_color_library())
        self.assertTrue(page.reset_color_library_storage())
        self.assertTrue(library.payload_applied())
        self.assertEqual(library.document_health(), DocumentHealth.NORMAL)
        self.assertIn("Recent colors: 0", page.color_counts_label.text())

    def test_future_only_color_library_is_read_only_with_diagnostics(self):
        from mygui.application_settings.storage import (
            COLOR_LIBRARY_SETTINGS_GROUP,
            SCHEMA_COLOR_LIBRARY_SETTINGS,
        )

        store = self.backend.store
        store.setValue(
            slot_key(COLOR_LIBRARY_SETTINGS_GROUP, SLOT_A),
            EnvelopeCodec().encode(
                schema=SCHEMA_COLOR_LIBRARY_SETTINGS,
                payload={"next": True},
                revision=5,
                schema_version=2,
            ),
        )
        store.sync()
        library = ColorLibrary(document=self.backend.color_library_settings_port())
        self.assertFalse(library.payload_applied())
        self.assertEqual(library.document_health(), DocumentHealth.READ_ONLY_FUTURE)
        page = MaintenanceSettingsPage(
            service=self.service,
            session=self.service.begin_session(),
            backend=self.backend,
            color_library=library,
            confirm=_Confirm(),
        )
        self.addCleanup(page.deleteLater)
        self.assertFalse(page.clear_recent_button.isEnabled())
        self.assertFalse(page.reset_library_button.isEnabled())
        self.assertTrue(page.reset_color_storage_button.isHidden())
        self.assertIn("read-only", page.color_diagnostics_label.text().casefold())
        self.assertFalse(page.reset_color_library())

    def test_export_settings_page_does_not_write_the_color_library(self):
        from mygui.figuremodify.style_base.color_models import ColorSelection

        library = ColorLibrary(document=self.backend.color_library_settings_port())
        session = self.service.begin_session()
        host = _FakeHost(self.service, session)
        page = ExportSettingsPage(library, host=host, session=session)
        self.addCleanup(page.deleteLater)
        self.assertFalse(page.panel.face_color.auto_record_recent)
        self.assertFalse(page.panel.face_color.allow_favorite)
        self.assertTrue(page.panel.face_color.favorite_button.isHidden())
        self.assertEqual(page.panel.use_project_dpi.text(), "Use project DPI")
        page.panel.face_color.set_selection(
            ColorSelection("#FF0000"),
            emit=True,
            record_recent=page.panel.face_color.auto_record_recent,
        )
        page.panel.face_color._toggle_favorite()
        self.assertEqual(library.recent_colors, [])
        self.assertEqual(library.favorite_colors, [])


class SettingsPageRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_specs_and_register_page_hook(self):
        specs = page_specs()
        self.assertEqual(
            [item.page_id for item in specs],
            [PAGE_EXPORT, PAGE_INTEGRATIONS, PAGE_MAINTENANCE],
        )
        self.assertIsInstance(specs[0], SettingsCenterPageSpec)
        self.assertEqual(specs[1].keywords, ("TeX", "MATLAB"))

        service = ApplicationSettingsService()
        opened: list[str] = []
        registry = SettingsPageRegistry()
        returned = register_c_pages(
            registry,
            color_library=ColorLibrary(),
            service=service,
            tex_status=UNAVAILABLE,
            matlab_status=UNAVAILABLE,
            on_open_tex_panel=lambda: opened.append("tex"),
            on_open_matlab_panel=lambda: opened.append("matlab"),
            confirm=_Confirm(),
        )
        self.assertEqual(len(returned), 3)
        self.assertEqual(
            list(registry.page_ids()),
            [PAGE_EXPORT, PAGE_INTEGRATIONS, PAGE_MAINTENANCE],
        )
        self.assertIsNotNone(registry.get(PAGE_EXPORT).factory)
        self.assertEqual(register_c_pages(object(), color_library=ColorLibrary()), [])

    def test_register_all_pages_uses_shell_order(self):
        service = ApplicationSettingsService()
        host_pages = SettingsPageRegistry()

        class _Center:
            def register_page(self, spec):
                host_pages.register_page(spec)

        returned = register_all_pages(
            _Center(),
            color_library=ColorLibrary(),
            service=service,
            tex_status=UNAVAILABLE,
            matlab_status=UNAVAILABLE,
        )
        self.assertEqual(len(returned), 9)
        self.assertEqual(list(host_pages.page_ids()), list(SHELL_PAGE_ORDER))

    def test_c_page_controls_are_keyboard_reachable(self):
        page = IntegrationsSettingsPage(
            tex_status=UNAVAILABLE,
            matlab_status=UNAVAILABLE,
        )
        self.addCleanup(page.deleteLater)
        for button in (page.open_tex_panel_button, page.open_matlab_panel_button):
            self.assertTrue(str(button.accessibleName()).strip())
            self.assertTrue(int(button.focusPolicy()) & int(Qt.TabFocus))

        export = ExportSettingsPage(ColorLibrary())
        self.addCleanup(export.deleteLater)
        self.assertTrue(export.panel.isEnabled())

        maintenance = MaintenanceSettingsPage(confirm=_Confirm())
        self.addCleanup(maintenance.deleteLater)
        for button in (
            maintenance.reset_all_button,
            maintenance.clear_recent_button,
            maintenance.reset_library_button,
        ):
            self.assertTrue(str(button.accessibleName()).strip())
            self.assertTrue(int(button.focusPolicy()) & int(Qt.TabFocus))
