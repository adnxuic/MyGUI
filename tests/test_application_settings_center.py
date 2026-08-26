"""Settings Center shell: session, preview, geometry, search, and lifecycle."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QRadioButton, QSpinBox, QWidget

from mygui.application_settings import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    ApplicationSettingsService,
    Density,
    MemorySettingsDocumentPort,
    SettingsHealth,
    ThemeMode,
)
from mygui.application_theme import (
    AppearancePreferences,
    FakeStyleHints,
    ThemeService,
    reset_qss_bindings_for_tests,
    subscribe_theme_window,
)
from mygui.application_theme.runtime import reset_theme_runtime_for_tests
from mygui.application_theme.windows import default_window_registry
from mygui.widgets.settings_center import (
    INITIAL_HEIGHT,
    INITIAL_WIDTH,
    MINIMUM_HEIGHT,
    MINIMUM_WIDTH,
    NAV_PANE_WIDTH,
    SHELL_PAGE_ORDER,
    SettingsCenterHost,
    SettingsCenterWindow,
    compose_settings_center,
    constrain_to_available,
    standard_page_spec,
)
from mygui.widgets.settings_center.geometry import SCREEN_FRACTION
from mygui.widgets.settings_center.pages import page_matches
from mygui.application_settings.registry import production_settings_registry

ROOT = Path(__file__).resolve().parents[1]
CENTER_PACKAGE = ROOT / "mygui" / "widgets" / "settings_center"


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _fake_factory(name: str, calls: list[str]):
    def factory(_host) -> QWidget:
        calls.append(name)
        widget = QWidget()
        widget.setObjectName(f"fake_page_{name}")
        label = QLabel(name, widget)
        label.setObjectName(f"fake_label_{name}")
        return widget

    return factory


class SettingsCenterGeometryTests(unittest.TestCase):
    def test_small_screen_scales_to_ninety_percent(self) -> None:
        available = QRect(10, 20, 400, 300)
        geo = constrain_to_available(available)
        self.assertEqual(geo.width(), int(400 * SCREEN_FRACTION))
        self.assertEqual(geo.height(), int(300 * SCREEN_FRACTION))
        self.assertLess(geo.width(), MINIMUM_WIDTH)
        self.assertLess(geo.height(), MINIMUM_HEIGHT)
        self.assertEqual(geo.x(), 10 + (400 - geo.width()) // 2)
        self.assertEqual(geo.y(), 20 + (300 - geo.height()) // 2)

    def test_large_screen_uses_initial_size_and_honors_minimum(self) -> None:
        available = QRect(0, 0, 1920, 1080)
        geo = constrain_to_available(available)
        self.assertEqual(geo.width(), INITIAL_WIDTH)
        self.assertEqual(geo.height(), INITIAL_HEIGHT)
        self.assertGreaterEqual(geo.width(), MINIMUM_WIDTH)
        self.assertGreaterEqual(geo.height(), MINIMUM_HEIGHT)
        self.assertEqual(geo.x(), (1920 - INITIAL_WIDTH) // 2)
        self.assertEqual(geo.y(), (1080 - INITIAL_HEIGHT) // 2)


class SettingsCenterShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.messages: list[tuple[str, str]] = []
        self.factory_calls: list[str] = []
        self.port = MemorySettingsDocumentPort()
        self.service = ApplicationSettingsService(document=self.port)
        self.theme = ThemeService(
            self.app,
            style_hints=FakeStyleHints(Qt.ColorScheme.Light),
        )
        self.theme.apply_committed(AppearancePreferences())
        self.host = SettingsCenterHost(
            None,
            self.service,
            self.theme,
            on_message=self._on_message,
            confirm_immediate=lambda _title, _text: True,
        )
        self.host.register_page(
            standard_page_spec(
                "appearance",
                _fake_factory("appearance", self.factory_calls),
            )
        )
        self.host.register_page(
            standard_page_spec(
                "new_figure",
                _fake_factory("new_figure", self.factory_calls),
            )
        )
        self.host.register_page(
            standard_page_spec(
                "integrations",
                _fake_factory("integrations", self.factory_calls),
                keywords=("TeX", "MATLAB"),
            )
        )

    def tearDown(self) -> None:
        window = self.host.window
        if window is not None:
            window.close()
            window.deleteLater()
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()
        self.app.processEvents()

    def _on_message(self, text: str, level: str) -> None:
        self.messages.append((str(level), str(text)))

    def _present(self, page_id: str | None = "appearance"):
        window = self.host.present(page_id)
        self.app.processEvents()
        return window

    def test_nav_pane_is_one_hundred_ninety_logical_pixels(self) -> None:
        window = self._present()
        pane = window.findChild(QWidget, "settings_nav_pane")
        self.assertIsNotNone(pane)
        self.assertEqual(pane.width(), NAV_PANE_WIDTH)

    def test_pages_are_created_lazily(self) -> None:
        window = self._present("appearance")
        self.assertEqual(self.factory_calls, ["appearance"])
        self.assertEqual(window.created_page_ids(), frozenset({"appearance"}))
        window.nav_list.setCurrentRow(1)
        self.app.processEvents()
        self.assertIn("new_figure", window.created_page_ids())
        self.assertNotIn("integrations", window.created_page_ids())

    def test_search_filters_pages_and_registry_field_keywords(self) -> None:
        window = self._present()
        registry = production_settings_registry()
        appearance = standard_page_spec("appearance")
        self.assertTrue(page_matches(appearance, "theme", registry))
        self.assertTrue(page_matches(appearance, "UI font size", registry))
        self.assertTrue(page_matches(appearance, "comfortable", registry))
        self.assertTrue(page_matches(appearance, "COMFORTABLE", registry))
        window.search_edit.setText("MATLAB")
        self.app.processEvents()
        hidden = {
            window.nav_list.item(index).text(): window.nav_list.item(index).isHidden()
            for index in range(window.nav_list.count())
        }
        self.assertTrue(hidden["Appearance"])
        self.assertFalse(hidden["Integrations"])
        window.search_edit.setText("DPI")
        self.app.processEvents()
        hidden = {
            window.nav_list.item(index).text(): window.nav_list.item(index).isHidden()
            for index in range(window.nav_list.count())
        }
        self.assertTrue(hidden["Appearance"])
        self.assertFalse(hidden["New Figure"])

    def test_focus_lands_on_search_or_nav(self) -> None:
        window = self._present()
        focused = window.focusWidget()
        self.assertIn(focused, {window.search_edit, window.nav_list, window})

    def test_preview_apply_ok_cancel_esc_and_close_restore(self) -> None:
        origin = self.theme.snapshot()
        window = self._present()
        window.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self.assertEqual(self.theme.snapshot().preferences.mode, ThemeMode.DARK)
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertTrue(window.glue.is_dirty())

        window.apply_button.click()
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(self.theme.snapshot().preferences.mode, ThemeMode.DARK)
        self.assertIn(("success", "Settings applied."), self.messages)
        self.assertFalse(window.glue.is_dirty())

        window.stage_value(APPEARANCE_UI_FONT_POINT_SIZE, 16)
        self.assertEqual(self.theme.snapshot().preferences.font_pt, 16)
        window.cancel_button.click()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(self.theme.snapshot().preferences.font_pt, 9)

        window = self._present()
        origin = self.theme.snapshot()
        window.stage_value(APPEARANCE_UI_FONT_POINT_SIZE, 14)
        QTest.keyClick(window, Qt.Key_Escape)
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertEqual(self.theme.snapshot().preferences.font_pt, origin.preferences.font_pt)
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 9)

        window = self._present()
        window.stage_value(APPEARANCE_UI_FONT_POINT_SIZE, 12)
        window.close()
        self.app.processEvents()
        self.assertEqual(self.theme.snapshot().preferences.font_pt, 9)
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 9)

        window = self._present()
        window.stage_value(APPEARANCE_UI_FONT_POINT_SIZE, 11)
        window.ok_button.click()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 11)
        self.assertEqual(self.theme.snapshot().preferences.font_pt, 11)

    def test_restore_page_defaults_only_changes_draft(self) -> None:
        committed = self.service.commit_patch(
            self.service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertTrue(committed.success)
        commits_before = self.port.commit_calls
        window = self._present("appearance")
        window.restore_defaults_button.click()
        self.app.processEvents()
        self.assertEqual(self.port.commit_calls, commits_before)
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(
            dict(window.glue.session.dirty_patch()),
            {APPEARANCE_THEME_MODE: ThemeMode.SYSTEM},
        )
        self.assertIn("draft", window.status_label.text().casefold())

    def test_immediate_command_is_confirmed_and_separated_from_apply(self) -> None:
        ran: list[str] = []
        window = self._present()
        commits_before = self.port.commit_calls
        window.request_immediate_command(
            "reset_workspace_layout_now",
            title="Reset workspace layout now?",
            text="This command is not part of Apply.",
            handler=lambda: ran.append("reset"),
        )
        self.assertEqual(ran, ["reset"])
        self.assertEqual(self.port.commit_calls, commits_before)
        self.assertFalse(window.glue.is_dirty())

    def test_storage_failure_restores_persisted_values_and_pre_window_appearance(
        self,
    ) -> None:
        origin = self.theme.snapshot()
        window = self._present()
        window.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self.port.fail_commit = True
        self.messages.clear()
        window.apply_button.click()
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertFalse(self.service.snapshot().appearance.theme_mode is ThemeMode.DARK)
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(self.theme.snapshot().preferences.mode, origin.preferences.mode)
        self.assertEqual(self.messages[0][0], "error")
        self.assertTrue(window.glue.is_dirty())

    def test_repeated_open_reuses_window_without_rebinding(self) -> None:
        with (
            patch(
                "mygui.widgets.settings_center.window.bind_widget_qss",
                wraps=__import__(
                    "mygui.widgets.settings_center.window", fromlist=["bind_widget_qss"]
                ).bind_widget_qss,
            ) as bind,
            patch(
                "mygui.widgets.settings_center.window.subscribe_theme_window",
                wraps=subscribe_theme_window,
            ) as subscribe,
        ):
            first = self.host.present("appearance")
            self.app.processEvents()
            self.assertEqual(bind.call_count, 1)
            self.assertEqual(subscribe.call_count, 1)
            first.close()
            self.app.processEvents()
            second = self.host.present("appearance")
            self.app.processEvents()
            self.assertIs(first, second)
            self.assertEqual(bind.call_count, 1)
            self.assertEqual(subscribe.call_count, 1)

    def test_open_centers_on_stub_screen_and_does_not_persist_geometry(self) -> None:
        self.host._geometry_provider = lambda: QRect(80, 40, 400, 300)
        window = self._present()
        self.assertEqual(window.width(), 360)
        self.assertEqual(window.height(), 270)
        self.assertLessEqual(abs(window.x() - (80 + 20)), 4)
        self.assertLessEqual(abs(window.y() - (40 + 15)), 4)
        window.move(0, 0)
        window.close()
        self.app.processEvents()
        window = self._present()
        self.assertLessEqual(abs(window.x() - 100), 4)
        self.assertLessEqual(abs(window.y() - 55), 4)

    def test_host_open_uses_exec_on_the_cached_dialog(self) -> None:
        window = self.host.ensure_window()
        with patch.object(window, "exec", return_value=0) as exec_dialog:
            result = self.host.open("appearance")
        self.assertEqual(result, 0)
        exec_dialog.assert_called_once_with()
        self.assertIs(self.host.window, window)

    def test_hidden_window_is_theme_subscribed(self) -> None:
        window = self._present()
        window.hide()
        self.assertTrue(default_window_registry().contains(window))
        self.assertTrue(window.styleSheet())
        self.assertNotIn("{{", window.styleSheet())

    def test_package_does_not_write_or_import_qsettings_geometry(self) -> None:
        forbidden = {"QSettings", "saveGeometry", "restoreGeometry"}
        for path in sorted(CENTER_PACKAGE.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                    imported.update(alias.name for alias in node.names)
            self.assertNotIn("QSettings", imported, path.name)
            for token in forbidden:
                self.assertNotIn(token, source, path.name)

    def test_one_message_bar_result_per_apply(self) -> None:
        window = self._present()
        window.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        window.stage_value(APPEARANCE_UI_FONT_POINT_SIZE, 13)
        self.messages.clear()
        window.apply_button.click()
        self.app.processEvents()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0][0], "success")

    def test_search_return_does_not_ok_or_commit(self) -> None:
        commits_before = self.port.commit_calls
        window = self._present()
        self.assertFalse(window.ok_button.isDefault())
        self.assertFalse(window.ok_button.autoDefault())
        window.search_edit.setFocus(Qt.OtherFocusReason)
        QTest.keyClick(window.search_edit, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertEqual(self.port.commit_calls, commits_before)
        QTest.keyClick(window.search_edit, Qt.Key_Enter)
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertEqual(self.port.commit_calls, commits_before)

    def test_search_without_matches_hides_the_page_stack(self) -> None:
        window = self._present()
        window.search_edit.setText("zzznomatch")
        self.app.processEvents()
        self.assertFalse(window._stack.isVisible())
        self.assertFalse(window.restore_defaults_button.isEnabled())
        self.assertEqual(window._title.text(), "No matching settings")


class SettingsCenterProductionPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.messages: list[tuple[str, str]] = []
        self.port = MemorySettingsDocumentPort()
        self.service = ApplicationSettingsService(document=self.port)
        self.theme = ThemeService(
            self.app,
            style_hints=FakeStyleHints(Qt.ColorScheme.Light),
        )
        self.theme.apply_committed(AppearancePreferences())
        from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary

        self.host = compose_settings_center(
            None,
            settings_service=self.service,
            theme_service=self.theme,
            color_library=ColorLibrary(),
            reset_layout_now=lambda: None,
            on_message=self._on_message,
        )

    def tearDown(self) -> None:
        window = self.host.window
        if window is not None:
            window.close()
            window.deleteLater()
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()
        self.app.processEvents()

    def _on_message(self, text: str, level: str) -> None:
        self.messages.append((str(level), str(text)))

    def test_six_pages_are_registered_in_shell_order(self) -> None:
        self.assertEqual(list(self.host.pages.page_ids()), list(SHELL_PAGE_ORDER))
        self.assertIsNone(self.host.window)
        window = self.host.present("appearance")
        self.app.processEvents()
        self.assertEqual(window.objectName(), "setting_dialog")
        self.assertIn("appearance", window.created_page_ids())
        self.assertNotIn("export", window.created_page_ids())
        window.nav_list.setCurrentRow(list(SHELL_PAGE_ORDER).index("workspace"))
        self.app.processEvents()
        self.assertIn("workspace", window.created_page_ids())

    def test_tab_reaches_appearance_editors(self) -> None:
        window = self.host.present("appearance")
        self.app.processEvents()
        page = window.findChild(QWidget, "settings_page_appearance")
        self.assertIsNotNone(page)
        editors = [
            child
            for child in page.findChildren(QWidget)
            if int(child.focusPolicy()) & int(Qt.TabFocus) and child.isEnabled()
        ]
        self.assertTrue(editors)
        window.search_edit.setFocus(Qt.OtherFocusReason)
        QTest.keyClick(window, Qt.Key_Tab)
        self.app.processEvents()
        focused = window.focusWidget()
        self.assertIsNotNone(focused)

    def test_cancel_reopen_reloads_real_pages_and_density_does_not_stage_stale_font(
        self,
    ) -> None:
        window = self.host.present("appearance")
        self.app.processEvents()
        spin = window.findChild(QSpinBox, "appearance_font_spin")
        self.assertIsNotNone(spin)
        spin.setValue(14)
        self.app.processEvents()
        self.assertEqual(window.glue.session.dirty_patch()[APPEARANCE_UI_FONT_POINT_SIZE], 14)
        window.cancel_button.click()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 9)

        window = self.host.present("appearance")
        self.app.processEvents()
        spin = window.findChild(QSpinBox, "appearance_font_spin")
        self.assertEqual(spin.value(), 9)
        comfortable = window.findChild(QRadioButton, "appearance_density_comfortable")
        comfortable.click()
        self.app.processEvents()
        dirty = dict(window.glue.session.dirty_patch())
        self.assertNotIn(APPEARANCE_UI_FONT_POINT_SIZE, dirty)
        self.assertEqual(dirty[APPEARANCE_DENSITY], Density.COMFORTABLE)

    def test_restore_workspace_defaults_does_not_stage_layout(self) -> None:
        from mygui.application_settings import WORKSPACE_LAYOUT, WORKSPACE_REMEMBER_LAYOUT
        from mygui.application_settings.models import DEFAULT_WORKSPACE_LAYOUT

        committed = self.service.commit_patch(
            self.service.begin_session(),
            {
                WORKSPACE_REMEMBER_LAYOUT: False,
                WORKSPACE_LAYOUT: DEFAULT_WORKSPACE_LAYOUT,
            },
        )
        self.assertTrue(committed.success)
        window = self.host.present("workspace")
        self.app.processEvents()
        window.restore_defaults_button.click()
        self.app.processEvents()
        dirty = dict(window.glue.session.dirty_patch())
        self.assertNotIn(WORKSPACE_LAYOUT, dirty)
        self.assertEqual(dirty.get(WORKSPACE_REMEMBER_LAYOUT), True)


class SettingsCenterFutureSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        import tempfile

        from mygui.application_settings.storage import (
            APPLICATION_SETTINGS_GROUP,
            SLOT_A,
            SLOT_B,
            create_settings_backend,
            default_application_settings_payload,
            slot_key,
        )
        from mygui.application_settings.storage.envelope import EnvelopeCodec
        from mygui.application_settings.storage.keys import SCHEMA_APPLICATION_SETTINGS
        from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary

        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.messages: list[tuple[str, str]] = []
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "settings.ini"
        self.backend = create_settings_backend(file_path=path)
        current = default_application_settings_payload(migrated=False)
        store = self.backend.store
        store.setValue(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_A),
            EnvelopeCodec().encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload=current,
                revision=3,
                schema_version=1,
            ),
        )
        store.setValue(
            slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B),
            EnvelopeCodec().encode(
                schema=SCHEMA_APPLICATION_SETTINGS,
                payload={"future_field": True},
                revision=9,
                schema_version=2,
            ),
        )
        store.sync()
        self.future_raw = store.value(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B))
        self.service = ApplicationSettingsService(
            document=self.backend.application_settings_port()
        )
        self.theme = ThemeService(
            self.app,
            style_hints=FakeStyleHints(Qt.ColorScheme.Light),
        )
        self.theme.apply_committed(AppearancePreferences())
        self.host = compose_settings_center(
            None,
            settings_service=self.service,
            theme_service=self.theme,
            color_library=ColorLibrary(
                document=self.backend.color_library_settings_port()
            ),
            backend=self.backend,
            reset_layout_now=lambda: None,
            on_message=self._on_message,
        )

    def tearDown(self) -> None:
        window = self.host.window
        if window is not None:
            window.close()
            window.deleteLater()
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        self.directory.cleanup()
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()
        self.app.processEvents()

    def _on_message(self, text: str, level: str) -> None:
        self.messages.append((str(level), str(text)))

    def test_future_schema_disables_apply_and_does_not_overwrite(self) -> None:
        from mygui.application_settings.storage import (
            APPLICATION_SETTINGS_GROUP,
            SLOT_B,
            slot_key,
        )

        self.assertEqual(self.service.health(), SettingsHealth.READ_ONLY_FUTURE)
        self.assertFalse(self.service.writable())
        window = self.host.present("appearance")
        self.app.processEvents()
        self.assertFalse(window.apply_button.isEnabled())
        self.assertFalse(window.ok_button.isEnabled())
        self.assertIn("read-only", window.status_label.text().casefold())
        origin = self.theme.snapshot()
        spin = window.findChild(QSpinBox, "appearance_font_spin")
        spin.setValue(14)
        self.app.processEvents()
        self.assertTrue(window.glue.is_dirty())
        self.assertFalse(window.apply_button.isEnabled())
        self.messages.clear()
        window._on_apply()
        self.app.processEvents()
        self.assertEqual(self.messages[0][0], "error")
        self.assertIn("not writable", self.messages[0][1].casefold())
        self.assertEqual(self.theme.snapshot().preferences.font_pt, origin.preferences.font_pt)
        self.assertEqual(
            self.backend.store.value(slot_key(APPLICATION_SETTINGS_GROUP, SLOT_B)),
            self.future_raw,
        )
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 9)


class SettingsCenterIncompatibleResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        import tempfile

        from mygui.application_settings.storage import create_settings_backend
        from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary

        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.messages: list[tuple[str, str]] = []
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "settings.ini"
        self.backend = create_settings_backend(file_path=path)
        self.service = ApplicationSettingsService(
            document=self.backend.application_settings_port()
        )
        self.theme = ThemeService(
            self.app,
            style_hints=FakeStyleHints(Qt.ColorScheme.Light),
        )
        self.theme.apply_committed(AppearancePreferences())
        self.host = compose_settings_center(
            None,
            settings_service=self.service,
            theme_service=self.theme,
            color_library=ColorLibrary(
                document=self.backend.color_library_settings_port()
            ),
            backend=self.backend,
            reset_layout_now=lambda: None,
            on_message=self._on_message,
        )

    def tearDown(self) -> None:
        window = self.host.window
        if window is not None:
            window.close()
            window.deleteLater()
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        self.directory.cleanup()
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()
        self.app.processEvents()

    def _on_message(self, text: str, level: str) -> None:
        self.messages.append((str(level), str(text)))

    def test_incompatible_reset_applies_committed_appearance_and_reloads_pages(
        self,
    ) -> None:
        from unittest.mock import patch

        from PySide6.QtWidgets import QMessageBox

        from mygui.application_settings.storage import (
            APPLICATION_SETTINGS_GROUP,
            SLOT_A,
            SLOT_B,
            DocumentHealth,
            slot_key,
        )
        from mygui.application_settings.storage.envelope import EnvelopeCodec
        from mygui.application_settings.storage.keys import SCHEMA_APPLICATION_SETTINGS

        from mygui.application_theme.binder import apply_committed_appearance

        committed = self.service.commit_patch(
            self.service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK, APPEARANCE_UI_FONT_POINT_SIZE: 14},
        )
        self.assertTrue(committed.success)
        apply_committed_appearance(self.theme, self.service.snapshot())
        window = self.host.present("appearance")
        self.app.processEvents()
        dark = window.findChild(QRadioButton, "appearance_theme_dark")
        self.assertTrue(dark.isChecked())
        self.assertEqual(self.theme.snapshot().preferences.mode, ThemeMode.DARK)

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
        window.nav_list.setCurrentRow(list(SHELL_PAGE_ORDER).index("maintenance"))
        self.app.processEvents()
        page = window.findChild(QWidget, "maintenance_settings_page")
        self.assertIsNotNone(page)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.assertTrue(page.reset_incompatible_storage())
        self.app.processEvents()
        self.assertEqual(
            self.backend.application_settings_port().load().health,
            DocumentHealth.NORMAL,
        )
        self.assertEqual(self.service.snapshot().appearance.theme_mode, ThemeMode.SYSTEM)
        self.assertEqual(self.service.snapshot().appearance.ui_font_point_size, 9)
        self.assertEqual(self.theme.snapshot().preferences.mode, ThemeMode.SYSTEM)
        self.assertEqual(self.theme.snapshot().preferences.font_pt, 9)
        window.nav_list.setCurrentRow(list(SHELL_PAGE_ORDER).index("appearance"))
        self.app.processEvents()
        system = window.findChild(QRadioButton, "appearance_theme_system")
        spin = window.findChild(QSpinBox, "appearance_font_spin")
        self.assertTrue(system.isChecked())
        self.assertEqual(spin.value(), 9)


class SettingsCenterWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.theme = ThemeService(
            self.app,
            style_hints=FakeStyleHints(Qt.ColorScheme.Light),
        )
        self.theme.apply_committed(AppearancePreferences())

    def tearDown(self) -> None:
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()
        self.app.processEvents()

    def test_gear_menu_and_shortcut_share_lazy_host(self) -> None:
        from main import MainWindow

        window = MainWindow(
            settings_service=MemorySettingsDocumentPort(),
            theme_service=self.theme,
        )
        try:
            self.assertIsNotNone(window.settings_center)
            self.assertIsNone(window.settings_center.window)
            self.assertEqual(
                list(window.settings_center.pages.page_ids()),
                list(SHELL_PAGE_ORDER),
            )
            self.assertEqual(
                window.settings_action.shortcut(),
                QKeySequence("Ctrl+,"),
            )
            self.assertIn(
                window.settings_action,
                window.title_bar.menu_bar.edit_menu.actions(),
            )
            with patch.object(SettingsCenterWindow, "exec", return_value=0):
                window.left_column.setting_button.click()
                first = window.settings_center.window
                self.assertIsNotNone(first)
                self.assertEqual(first.objectName(), "setting_dialog")
                window.settings_action.trigger()
                self.assertIs(window.settings_center.window, first)
                window.open_settings_center()
                self.assertIs(window.settings_center.window, first)
            self.assertIsNone(window.left_column.setting_dialog)
        finally:
            cached = window.settings_center.window
            if cached is not None:
                cached.close()
                cached.deleteLater()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
