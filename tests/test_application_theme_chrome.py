"""Chrome palette, density metrics, icon DPR cache, and cached-window updates."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QScrollArea, QWidget

from mygui.application_settings import APPEARANCE_THEME_MODE, ApplicationSettingsService
from mygui.application_settings.models import Density, ThemeMode
from mygui.application_settings.storage import create_settings_backend
from mygui.application_theme import (
    AppearancePreferences,
    CachingThemeIconProvider,
    CONTRAST_PAIRS_BODY,
    DENSITY_BANDS,
    EffectiveScheme,
    FakeStyleHints,
    IconCacheKey,
    IconRole,
    LIGHT_QSS_TOKENS,
    SIZE_PARTICIPANTS,
    ThemeService,
    ThemeSnapshot,
    compose_theme_snapshot,
    contrast_ratio,
    current_density_metrics,
    current_qss_tokens,
    subscribe_theme_window,
)
from mygui.application_theme.icons import classify_icon_source
from mygui.application_theme.runtime import reset_theme_runtime_for_tests
from mygui.application_theme.qss import reset_qss_bindings_for_tests
from mygui.application_theme.windows import default_window_registry
from mygui.project_io import project_snapshot
from mygui.resources import icon_path
from mygui.widgets.figure_canvas.canvas_popout import CanvasPopoutWindow
from mygui.widgets.left_column.py_setting_dialog import PySettingDialog
from tests.axes_helpers import create_regular_axes

ROOT = Path(__file__).resolve().parents[1]
THEME_PACKAGE = ROOT / "mygui" / "application_theme"


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ThemeMetricsFormulaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_size_participant_inventory_covers_chrome_bands(self) -> None:
        names = {item["object_name"] for item in SIZE_PARTICIPANTS}
        self.assertTrue(
            {
                "left_column",
                "right_column",
                "bottom_bar",
                "selector_menu_bar",
                "selector_menu",
                "sheet_table_view",
                "component_tree_view",
                "figure_popout_window",
            }.issubset(names)
        )

    def test_compact_8pt_and_comfortable_16pt_use_font_floor(self) -> None:
        cases = (
            (8, Density.COMPACT),
            (16, Density.COMFORTABLE),
        )
        for font_pt, density in cases:
            with self.subTest(font_pt=font_pt, density=density.value):
                snapshot = compose_theme_snapshot(
                    EffectiveScheme.LIGHT,
                    AppearancePreferences(
                        mode=ThemeMode.LIGHT,
                        font_pt=font_pt,
                        density=density,
                    ),
                )
                band = DENSITY_BANDS[density]
                font_height = int(math.ceil(QFontMetrics(snapshot.font).height()))
                floor = font_height + band.vertical_padding
                metrics = snapshot.metrics
                self.assertEqual(metrics.font_height, font_height)
                self.assertEqual(metrics.vertical_padding, band.vertical_padding)
                self.assertEqual(metrics.table_row, max(band.table_row, floor))
                self.assertEqual(metrics.table_header, max(band.table_header, floor))
                self.assertEqual(metrics.tree, max(band.tree, floor))
                self.assertEqual(metrics.control, max(band.control, floor))
                self.assertEqual(metrics.rail, max(band.rail, floor))
                self.assertEqual(metrics.button, max(band.button, floor))
                self.assertGreaterEqual(metrics.control, font_height + metrics.vertical_padding)

                edit = QLineEdit("Agypq")
                edit.setFont(snapshot.font)
                edit.setFixedHeight(metrics.control)
                self.app.processEvents()
                glyph = QFontMetrics(snapshot.font).boundingRect("Agypq").height()
                self.assertLessEqual(glyph, edit.height())
                edit.deleteLater()


class ThemePaletteContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def test_palette_text_contrasts_with_content_and_surface(self) -> None:
        for scheme in (EffectiveScheme.LIGHT, EffectiveScheme.DARK):
            with self.subTest(scheme=scheme.value):
                mode = ThemeMode.LIGHT if scheme is EffectiveScheme.LIGHT else ThemeMode.DARK
                snapshot = compose_theme_snapshot(
                    scheme,
                    AppearancePreferences(mode=mode, font_pt=9, density=Density.STANDARD),
                )
                palette = snapshot.palette
                text = palette.color(QPalette.ColorRole.WindowText).name()
                content = palette.color(QPalette.ColorRole.Window).name()
                surface = palette.color(QPalette.ColorRole.Base).name()
                self.assertGreaterEqual(contrast_ratio(text, content), 4.5)
                self.assertGreaterEqual(contrast_ratio(text, surface), 4.5)
                tokens = snapshot.tokens
                for token_scheme, foreground, background in CONTRAST_PAIRS_BODY:
                    if token_scheme != scheme.value:
                        continue
                    self.assertGreaterEqual(
                        contrast_ratio(tokens[foreground], tokens[background]),
                        4.5,
                    )


class ThemeIconCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        self.provider = CachingThemeIconProvider()
        self.light = compose_theme_snapshot(
            EffectiveScheme.LIGHT,
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=9, density=Density.STANDARD),
        )
        self.dark = compose_theme_snapshot(
            EffectiveScheme.DARK,
            AppearancePreferences(mode=ThemeMode.DARK, font_pt=9, density=Density.STANDARD),
        )
        self.source = icon_path("setting.svg")

    def test_same_key_does_not_recolor_twice_and_scheme_invalidates(self) -> None:
        first = self.provider.icon(self.source, snapshot=self.light, dpr=1.0, logical_size=24)
        self.assertEqual(self.provider.recolor_calls, 1)
        self.assertEqual(self.provider.misses, 1)
        second = self.provider.icon(self.source, snapshot=self.light, dpr=1.0, logical_size=24)
        self.assertEqual(self.provider.recolor_calls, 1)
        self.assertEqual(self.provider.hits, 1)
        self.assertIs(first, second)

        key = self.provider.cache_key(
            self.source,
            IconRole.CHROME,
            24,
            EffectiveScheme.LIGHT,
            Density.STANDARD,
            1.0,
        )
        self.assertIsInstance(key, IconCacheKey)
        self.assertEqual(key.scheme, EffectiveScheme.LIGHT)

        rendered = self.provider.prerender(self.dark)
        self.provider.apply(rendered)
        self.assertNotIn(key, self.provider._cache)
        dark_icon = self.provider.icon(
            self.source, snapshot=self.dark, dpr=1.0, logical_size=24
        )
        self.assertGreaterEqual(self.provider.recolor_calls, 2)
        self.assertFalse(dark_icon.isNull())

        hi_dpr = self.provider.icon(
            self.source, snapshot=self.dark, dpr=2.0, logical_size=24
        )
        self.assertFalse(hi_dpr.isNull())
        again = self.provider.icon(
            self.source, snapshot=self.dark, dpr=2.0, logical_size=24
        )
        self.assertIs(hi_dpr, again)

    def test_brand_and_preview_are_not_recolored(self) -> None:
        self.assertEqual(classify_icon_source(icon_path("matlab.svg")), IconRole.BRAND)
        self.assertEqual(
            classify_icon_source(icon_path("chart_images/plot.svg")),
            IconRole.PREVIEW,
        )
        before = self.provider.recolor_calls
        brand = self.provider.icon(
            icon_path("matlab.svg"),
            snapshot=self.light,
            role=IconRole.BRAND,
            dpr=1.0,
            logical_size=24,
        )
        preview = self.provider.icon(
            icon_path("style_images/default.svg"),
            snapshot=self.light,
            role=IconRole.PREVIEW,
            dpr=1.0,
            logical_size=24,
        )
        self.assertEqual(self.provider.recolor_calls, before)
        self.assertFalse(brand.isNull())
        self.assertFalse(preview.isNull())

    def test_restore_replays_icons_to_live_subscribed_windows(self) -> None:
        class _TestIconSubscriber(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.applied_snapshots: list[ThemeSnapshot] = []

            def apply_theme_icons(self, snapshot: ThemeSnapshot, _provider) -> None:
                self.applied_snapshots.append(snapshot)

        subscriber = _TestIconSubscriber()
        subscribe_theme_window(subscriber)
        rendered_light = self.provider.prerender(self.light)
        self.provider.apply(rendered_light)
        memento = self.provider.capture()

        rendered_dark = self.provider.prerender(self.dark)
        self.provider.apply(rendered_dark)
        self.assertEqual(subscriber.applied_snapshots[-1].scheme, EffectiveScheme.DARK)

        self.provider.restore(memento)
        self.assertEqual(subscriber.applied_snapshots[-1].scheme, EffectiveScheme.LIGHT)
        subscriber.deleteLater()

    def test_restore_without_snapshot_degrades_safely(self) -> None:
        self.provider.restore({"cache": {}})
        self.assertEqual(self.provider._cache, {})

    def test_restore_propagates_exception_when_widget_fails(self) -> None:
        class _FaultySubscriber(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.fail_now = False

            def apply_theme_icons(self, _snapshot, _provider) -> None:
                if self.fail_now:
                    raise RuntimeError("custom icon fail")

        faulty = _FaultySubscriber()
        subscribe_theme_window(faulty)
        rendered = self.provider.prerender(self.light)
        self.provider.apply(rendered)
        memento = self.provider.capture()
        faulty.fail_now = True
        with self.assertRaises(RuntimeError):
            self.provider.restore(memento)
        faulty.deleteLater()


class ThemeWindowSubscriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        self.hints = FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=self.hints)

    def tearDown(self) -> None:
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def test_hidden_settings_and_parentless_popout_update(self) -> None:
        dialog = PySettingDialog()
        dialog.hide()
        self.assertTrue(default_window_registry().contains(dialog))

        class _Owner:
            def _restore_canvas_from_popout(self, _window) -> None:
                return None

        popout = CanvasPopoutWindow(_Owner())
        self.assertIsNone(popout.parentWidget())
        self.assertTrue(default_window_registry().contains(popout))
        marker = QLabel("theme-probe", popout)
        marker.setObjectName("theme_probe")

        light_content = self.theme.snapshot().palette.color(QPalette.ColorRole.Window)
        self.theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.DARK, font_pt=9, density=Density.STANDARD)
        )
        self.app.processEvents()
        window_role = QPalette.ColorRole.Window
        tokens = self.theme.snapshot().tokens
        content = str(tokens["COLOR_CONTENT_BACKGROUND"]).lower()
        surface = str(tokens["COLOR_SURFACE"]).lower()
        dialog_window = dialog.palette().color(window_role).name().lower()
        self.assertNotEqual(dialog_window, light_content.name().lower())
        self.assertIn(dialog_window, {content, surface})
        self.assertIn(surface, dialog.styleSheet().lower())
        self.assertEqual(
            popout.palette().color(window_role).name().lower(),
            self.theme.snapshot().palette.color(window_role).name().lower(),
        )
        self.assertFalse(popout.isVisible())
        self.assertFalse(dialog.isVisible())

        popout.deleteLater()
        dialog.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        live = list(default_window_registry().live_widgets())
        self.assertNotIn(dialog, live)
        self.assertNotIn(popout, live)

    def test_subscribe_applies_current_snapshot_to_late_window(self) -> None:
        self.theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.DARK, font_pt=9, density=Density.STANDARD)
        )
        widget = QWidget()
        widget.hide()
        subscribe_theme_window(widget)
        self.assertEqual(
            widget.palette().color(QPalette.ColorRole.Window).name().lower(),
            self.theme.snapshot().palette.color(QPalette.ColorRole.Window).name().lower(),
        )
        widget.deleteLater()
        self.app.processEvents()


class ThemeDoesNotMutateFigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def tearDown(self) -> None:
        theme = getattr(self, "theme", None)
        if theme is not None:
            theme.shutdown()
        window = getattr(self, "window", None)
        if window is not None:
            window.close_without_prompt()
            window.deleteLater()
        self.app.processEvents()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def test_theme_switch_leaves_selection_history_and_project_json(self) -> None:
        from main import MainWindow

        reset_theme_runtime_for_tests()
        self.hints = FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=self.hints)
        self.window = MainWindow()
        self.window.resize(1280, 720)
        canvas = self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ThemeChrome"
        )
        create_regular_axes(canvas)
        axes_id = canvas.current_axes_component_id
        self.assertTrue(canvas.select_component(axes_id))
        self.app.processEvents()

        selected = canvas.current_component_id
        stack = canvas.repository.undo_stack(canvas.project_id)
        undo_index = stack.index()
        undo_count = stack.count()
        before_json = json.dumps(project_snapshot(self.window.figure_window, canvas=canvas), sort_keys=True)
        before_tree = canvas.component_snapshot()

        self.theme.apply_committed(
            AppearancePreferences(
                mode=ThemeMode.DARK,
                font_pt=16,
                density=Density.COMFORTABLE,
            )
        )
        self.app.processEvents()

        self.assertEqual(canvas.current_component_id, selected)
        self.assertEqual(stack.index(), undo_index)
        self.assertEqual(stack.count(), undo_count)
        after_json = json.dumps(project_snapshot(self.window.figure_window, canvas=canvas), sort_keys=True)
        self.assertEqual(after_json, before_json)
        self.assertEqual(canvas.component_snapshot(), before_tree)

    def test_theme_package_does_not_call_private_dwm_apis(self) -> None:
        for path in sorted(THEME_PACKAGE.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            self.assertNotIn("dwmapi", lowered, path.name)
            self.assertNotIn("dwmsetwindowattribute", lowered, path.name)
            self.assertNotIn("dwnextendframeintoclientarea", lowered, path.name)


def _opaque_icon_value(icon, size: int = 24) -> float:
    image = icon.pixmap(size, size).toImage()
    values = [
        image.pixelColor(x, y).value()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 127
    ]
    if not values:
        return 0.0
    return sum(values) / len(values)


class ThemeDarkToLightChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def tearDown(self) -> None:
        theme = getattr(self, "theme", None)
        if theme is not None:
            theme.shutdown()
        window = getattr(self, "window", None)
        if window is not None:
            window.close_without_prompt()
            window.deleteLater()
        self.app.processEvents()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def _apply(self, mode: ThemeMode) -> None:
        self.theme.apply_committed(
            AppearancePreferences(mode=mode, font_pt=9, density=Density.STANDARD)
        )
        self.app.processEvents()

    def test_dark_to_light_refreshes_inspector_canvas_rail_and_toolbar(self) -> None:
        from main import MainWindow

        reset_theme_runtime_for_tests()
        self.hints = FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=self.hints)
        self._apply(ThemeMode.DARK)
        self.window = MainWindow()
        self.window.resize(1280, 720)
        canvas = self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ThemeSwitch"
        )
        create_regular_axes(canvas)
        self.assertTrue(canvas.select_component(canvas.current_axes_component_id))
        self.app.processEvents()

        home_action = canvas.navigation_toolbar._actions.get("home")
        self.assertIsNotNone(home_action)
        dark_home = _opaque_icon_value(home_action.icon())
        dark_toolbar_value = canvas.navigation_toolbar.palette().color(
            canvas.navigation_toolbar.backgroundRole()
        ).value()

        self._apply(ThemeMode.LIGHT)
        tokens = self.theme.snapshot().tokens
        text = str(tokens["COLOR_TEXT_PRIMARY"]).lower()
        surface = str(tokens["COLOR_SURFACE"]).lower()
        content = str(tokens["COLOR_CONTENT_BACKGROUND"]).lower()
        surface_alt = str(tokens["COLOR_SURFACE_ALT"]).lower()
        self.assertEqual(content, LIGHT_QSS_TOKENS["COLOR_CONTENT_BACKGROUND"].lower())
        self.assertEqual(
            current_qss_tokens()["COLOR_CONTENT_BACKGROUND"].lower(),
            content,
        )
        self.assertNotEqual(content, "#0f172a")

        host = self.window.fig_control_window.figure_inspector_host
        workbench_sheet = self.window.styleSheet().lower()
        self.assertIn(text, workbench_sheet)
        self.assertIn(content, workbench_sheet)
        self.assertIn(surface_alt, workbench_sheet)
        self.assertEqual(host.styleSheet(), "")
        labels = [
            label
            for label in host.findChildren(QLabel)
            if str(label.text() or "").strip()
            and label.objectName() not in {"empty_state_title", "empty_state_detail"}
        ]
        self.assertTrue(labels)
        for label in labels:
            window_text = label.palette().color(QPalette.ColorRole.WindowText).name().lower()
            if contrast_ratio(window_text, surface) < 4.5:
                current = label
                sheets: list[str] = []
                while current is not None:
                    if current.styleSheet():
                        sheets.append(current.styleSheet().lower())
                    current = current.parentWidget()
                self.assertTrue(any(text in sheet for sheet in sheets), label.text())
            else:
                self.assertGreaterEqual(contrast_ratio(window_text, surface), 4.5)

        self.assertEqual(self.window.figure_window.styleSheet(), "")
        self.assertNotIn("#0f172a", workbench_sheet)
        viewport = canvas.scroArea.viewport()
        self.assertEqual(
            viewport.palette().color(QPalette.ColorRole.Window).name().lower(),
            content,
        )

        self.assertEqual(self.window.right_column.styleSheet(), "")
        self.assertNotIn("#0b1220", workbench_sheet)
        self.assertLess(
            _opaque_icon_value(self.window.right_column.tex_button.icon()),
            120,
        )

        light_home = _opaque_icon_value(home_action.icon())
        self.assertGreaterEqual(
            canvas.navigation_toolbar.palette().color(
                canvas.navigation_toolbar.backgroundRole()
            ).value(),
            128,
        )
        self.assertLess(light_home, 160)
        if dark_toolbar_value < 128:
            self.assertLess(light_home, dark_home)


class ThemeDarkPreviewRevertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.hints = FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=self.hints)
        self.theme.apply_committed(
            AppearancePreferences(mode=ThemeMode.LIGHT, font_pt=9, density=Density.STANDARD)
        )
        self.backend = create_settings_backend(
            organization="MyGUI",
            application="MyGUITest",
        )
        self.service = ApplicationSettingsService(
            document=self.backend.application_settings_port(),
        )
        self.service.commit_patch(
            self.service.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.LIGHT},
        )
        from main import MainWindow

        self.window = MainWindow(
            settings_backend=self.backend,
            settings_service=self.service,
            theme_service=self.theme,
        )
        self.window.resize(1280, 720)
        self.canvas = self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="PreviewRevert"
        )
        create_regular_axes(self.canvas)
        self.assertTrue(self.canvas.select_component(self.canvas.current_axes_component_id))
        self.app.processEvents()

    def tearDown(self) -> None:
        if hasattr(self, "theme"):
            self.theme.shutdown()
        if hasattr(self, "window") and self.window is not None:
            self.window.close_without_prompt()
            self.window.deleteLater()
        self.app.processEvents()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def _assert_light_icons(self) -> None:
        for name, action in self.canvas.navigation_toolbar._actions.items():
            self.assertLess(
                _opaque_icon_value(action.icon()), 120,
                f"Figure toolbar {name} should be dark on the restored Light surface",
            )
        self.assertLess(
            _opaque_icon_value(self.window.left_column.setting_button.icon()),
            120,
            "setting_button should be dark",
        )
        self.assertLess(
            _opaque_icon_value(self.window.left_column.components_button.icon()),
            120,
            "components_button should be dark",
        )
        self.assertGreater(
            _opaque_icon_value(self.window.left_column.table_button.icon()),
            200,
            "checked table_button on blue accent should be bright",
        )
        self.assertLess(
            _opaque_icon_value(self.window.title_bar.selector_menu_bar.style_button.icon()),
            120,
            "checked style_button on light surface should be dark",
        )
        self.assertGreater(
            _opaque_icon_value(self.window.title_bar.selector_menu_bar.layout_button.icon()),
            200,
            "unchecked layout_button on dark command bar should be bright",
        )
        self.assertLess(
            _opaque_icon_value(self.window.right_column.tex_button.icon()),
            120,
            "tex_button should be dark",
        )
        self.assertLess(
            QColor(str(self.theme.snapshot().tokens["COLOR_STATUS_BACKGROUND"])).value(),
            128,
            "bottom_bar background should remain dark",
        )

    def _assert_dark_preview_icons(self) -> None:
        for name, action in self.canvas.navigation_toolbar._actions.items():
            self.assertGreater(
                _opaque_icon_value(action.icon()), 200,
                f"Figure toolbar {name} should be bright on the Dark surface",
            )
        self.assertGreater(
            _opaque_icon_value(self.window.left_column.setting_button.icon()),
            200,
            "setting_button should be bright in Dark preview",
        )
        self.assertGreater(
            _opaque_icon_value(self.window.left_column.components_button.icon()),
            200,
            "components_button should be bright in Dark preview",
        )
        self.assertGreater(
            _opaque_icon_value(self.window.right_column.tex_button.icon()),
            200,
            "tex_button should be bright in Dark preview",
        )

    def test_dark_preview_reselect_light_restores_all_window_icons(self) -> None:
        self._assert_light_icons()
        dialog = self.window.settings_center.present()
        self.app.processEvents()
        self.assertIsNotNone(dialog)

        dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self.app.processEvents()
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertTrue(dialog.glue.is_dirty())
        self._assert_dark_preview_icons()

        dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.LIGHT)
        self.app.processEvents()
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)
        self.assertFalse(dialog.glue.is_dirty())
        self._assert_light_icons()

        dialog.reject()
        self.app.processEvents()
        self._assert_light_icons()

    def test_dark_preview_cancel_esc_and_close_restore_all_window_icons(self) -> None:
        paths = ("cancel", "escape", "close")
        for path in paths:
            with self.subTest(path=path):
                self._assert_light_icons()
                dialog = self.window.settings_center.present()
                self.app.processEvents()
                self.assertIsNotNone(dialog)

                dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
                self.app.processEvents()
                self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
                self._assert_dark_preview_icons()

                if path == "cancel":
                    dialog.cancel_button.click()
                elif path == "escape":
                    QTest.keyClick(dialog, Qt.Key_Escape)
                elif path == "close":
                    dialog.close()
                self.app.processEvents()

                self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)
                self.assertEqual(self.theme.snapshot().preferences.mode, ThemeMode.LIGHT)
                self._assert_light_icons()

    def test_cached_hidden_window_and_dialog_created_during_preview(self) -> None:
        cached_dialog = PySettingDialog()
        cached_dialog.hide()
        self.assertTrue(default_window_registry().contains(cached_dialog))

        settings_win = self.window.settings_center.present()
        self.app.processEvents()
        settings_win.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self.app.processEvents()

        late_widget = QWidget()
        late_widget.setProperty("themeChromeWindowIcon", icon_path("setting.svg"))
        subscribe_theme_window(late_widget)
        self.assertTrue(default_window_registry().contains(late_widget))

        settings_win.cancel_button.click()
        self.app.processEvents()

        self._assert_light_icons()
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)

        cached_dialog.deleteLater()
        late_widget.deleteLater()
        self.app.processEvents()

    def test_toolbar_both_scheme_roundtrips_in_popout_preserve_project_state(self) -> None:
        self.window.show()
        self.canvas.popout_action.trigger()
        self.app.processEvents()
        toolbar = self.canvas.navigation_toolbar
        state = self.canvas.component_snapshot()
        selected = self.canvas.current_component_id
        stack = self.canvas.repository.undo_stack(self.canvas.project_id)
        history = (stack.index(), stack.count())
        checked = {name: action.isChecked() for name, action in toolbar._actions.items()}
        try:
            for origin, preview in ((ThemeMode.LIGHT, ThemeMode.DARK), (ThemeMode.DARK, ThemeMode.LIGHT)):
                self.service.commit_patch(
                    self.service.begin_session(), {APPEARANCE_THEME_MODE: origin},
                )
                self.theme.apply_committed(AppearancePreferences(mode=origin))
                dialog = self.window.settings_center.present()
                self.app.processEvents()
                for _ in range(2):
                    dialog.stage_value(APPEARANCE_THEME_MODE, preview)
                    self.app.processEvents()
                    dialog.stage_value(APPEARANCE_THEME_MODE, origin)
                    self.app.processEvents()
                    for name, action in toolbar._actions.items():
                        brightness = _opaque_icon_value(action.icon())
                        if origin is ThemeMode.LIGHT:
                            self.assertLess(brightness, 120, name)
                        else:
                            self.assertGreater(brightness, 200, name)
                dialog.reject()
            self.assertEqual(self.canvas.component_snapshot(), state)
            self.assertEqual(self.canvas.current_component_id, selected)
            self.assertEqual((stack.index(), stack.count()), history)
            self.assertEqual({name: action.isChecked() for name, action in toolbar._actions.items()}, checked)
        finally:
            self.canvas._canvas_popout_window.close()
            self.app.processEvents()


class ThemeSettingsPaletteRestoreTests(unittest.TestCase):
    """Real cached pages must restore painted colors, not just theme tokens."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        from mygui.application_settings import MemorySettingsDocumentPort
        from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
        from mygui.widgets.settings_center import compose_settings_center

        self.original = (self.app.font(), self.app.palette(), self.app.styleSheet())
        reset_theme_runtime_for_tests()
        reset_qss_bindings_for_tests()
        self.theme = ThemeService(self.app, style_hints=FakeStyleHints(Qt.ColorScheme.Light))
        self.theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
        self.port = MemorySettingsDocumentPort()
        self.service = ApplicationSettingsService(document=self.port)
        self.service.commit_patch(
            self.service.begin_session(), {APPEARANCE_THEME_MODE: ThemeMode.LIGHT},
        )
        self.messages = []
        self.host = compose_settings_center(
            None, settings_service=self.service, theme_service=self.theme,
            color_library=ColorLibrary(), reset_layout_now=lambda: None,
            on_message=lambda *args: self.messages.append(args),
        )
        self.dialog = self.host.present("new_figure")
        self.app.processEvents()

    def tearDown(self) -> None:
        self.theme._fault_hooks = None
        self.dialog.reject()
        self.dialog.deleteLater()
        self.theme.shutdown()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.app.setFont(self.original[0])
        self.app.setPalette(self.original[1])
        self.app.setStyleSheet(self.original[2])
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def _select_page(self, page_id: str) -> None:
        from mygui.widgets.settings_center import SHELL_PAGE_ORDER

        self.dialog.nav_list.setCurrentRow(list(SHELL_PAGE_ORDER).index(page_id))
        self.app.processEvents()

    def _page_colors(self):
        page = self.dialog.findChild(QWidget, "settings_page_new_figure")
        scroll = self.dialog.findChild(QScrollArea, "settings_page_scroll_new_figure")
        label = page.findChild(QLabel, "settings_page_field_label")
        self.assertIsNotNone(label)
        roles = (QPalette.Window, QPalette.WindowText, QPalette.Base, QPalette.Text)
        return tuple(
            tuple(widget.palette().color(role).rgba() for role in roles)
            for widget in (self.dialog, scroll, scroll.viewport(), page, label)
        )

    def _assert_surface(self) -> None:
        page = self.dialog.findChild(QWidget, "settings_page_new_figure")
        image = page.grab().toImage()
        background = image.pixelColor(image.width() - 4, image.height() - 4)
        self.assertEqual(background.name(), self.theme.snapshot().tokens["COLOR_SURFACE"].lower())
        label = page.findChild(QLabel, "settings_page_field_label")
        self.assertGreaterEqual(
            contrast_ratio(label.palette().color(QPalette.WindowText).name(), background.name()),
            4.5,
        )

    def test_cached_page_reselect_roundtrip_in_both_schemes(self) -> None:
        for origin, preview in ((ThemeMode.LIGHT, ThemeMode.DARK), (ThemeMode.DARK, ThemeMode.LIGHT)):
            with self.subTest(origin=origin):
                self.dialog.reject()
                self.service.commit_patch(
                    self.service.begin_session(), {APPEARANCE_THEME_MODE: origin},
                )
                self.theme.apply_committed(AppearancePreferences(mode=origin))
                self.dialog = self.host.present("new_figure")
                self.app.processEvents()
                before = self._page_colors()
                for _ in range(3):
                    self._select_page("appearance")
                    self.dialog.stage_value(APPEARANCE_THEME_MODE, preview)
                    self.app.processEvents()
                    self.dialog.stage_value(APPEARANCE_THEME_MODE, origin)
                    self.app.processEvents()
                    self._select_page("new_figure")
                    self.assertEqual(self._page_colors(), before)
                    self._assert_surface()

    def test_cancel_escape_close_and_storage_failure_restore_cached_page(self) -> None:
        before = self._page_colors()
        for action in ("cancel", "escape", "close", "storage"):
            with self.subTest(action=action):
                self._select_page("appearance")
                self.dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
                self.app.processEvents()
                if action == "cancel":
                    self.dialog.cancel_button.click()
                elif action == "escape":
                    QTest.keyClick(self.dialog, Qt.Key_Escape)
                elif action == "close":
                    self.dialog.close()
                else:
                    self.port.fail_commit = True
                    self.dialog.apply_button.click()
                    self.port.fail_commit = False
                    self.assertEqual(len(self.messages), 1)
                self.app.processEvents()
                self.dialog = self.host.present("new_figure")
                self.app.processEvents()
                self.assertEqual(self._page_colors(), before)
                self._assert_surface()

    def test_fault_before_qss_and_after_partial_qss_restore_actual_palettes(self) -> None:
        from mygui.application_theme import ThemeApplyError, ThemeFaultHooks
        from mygui.application_theme import service as service_module
        from mygui.application_theme.qss import apply_widget_stylesheet

        before = self._page_colors()
        snapshot = self.theme.snapshot()
        events = []
        self.theme.subscribe(lambda *args: events.append(args))
        for step in ("qss", "icons"):
            with self.subTest(step=step):
                self.theme._fault_hooks = ThemeFaultHooks(fail_apply_step=step)
                with self.assertRaises(ThemeApplyError):
                    self.theme.preview(AppearancePreferences(mode=ThemeMode.DARK))
                self.app.processEvents()
                self.assertEqual(self._page_colors(), before)
                self.assertIs(self.theme.snapshot(), snapshot)
        self.theme._fault_hooks = None

        def partial_apply(port, rendered):
            widget, resource = next(port.iter_bindings())
            apply_widget_stylesheet(widget, rendered[resource])
            raise RuntimeError("QSS participant failed after first write")

        with mock.patch.object(service_module, "binding_apply", partial_apply):
            with self.assertRaises(ThemeApplyError):
                self.theme.preview(AppearancePreferences(mode=ThemeMode.DARK))
        self.app.processEvents()
        self.assertEqual(self._page_colors(), before)
        self.assertIs(self.theme.snapshot(), snapshot)
        self.assertEqual(events, [])
        self._assert_surface()

    def test_late_page_and_independent_root_restore_once(self) -> None:
        from mygui.application_theme import bind_widget_qss
        from mygui.application_theme import qss

        before = self._page_colors()
        self._select_page("appearance")
        self.dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.DARK)
        self._select_page("workspace")
        late = QWidget()
        late.setObjectName("fig_control_window")
        bind_widget_qss(late, "mygui/widgets/fig_control_window/style.qss")
        subscribe_theme_window(late)
        late.hide()
        writes = []
        original_write = QWidget.setStyleSheet

        def record(widget, sheet):
            writes.append(id(widget))
            return original_write(widget, sheet)

        with (
            mock.patch.object(QWidget, "setStyleSheet", record),
            mock.patch.object(QApplication, "setStyleSheet", wraps=self.app.setStyleSheet) as app_write,
            mock.patch("mygui.application_theme.windows._polish_widget_tree") as polish,
        ):
            self.dialog.stage_value(APPEARANCE_THEME_MODE, ThemeMode.LIGHT)
        self.app.processEvents()
        app_write.assert_not_called()
        polish.assert_not_called()
        self.assertEqual(len(writes), len(set(writes)))
        self.assertIn(id(late), writes)
        self.assertEqual(late.styleSheet(), qss.render_resource_stylesheet(
            "mygui/widgets/fig_control_window/style.qss", self.theme.snapshot(),
        ))
        self._select_page("new_figure")
        self.assertEqual(self._page_colors(), before)
        self._assert_surface()
        self._select_page("workspace")
        workspace = self.dialog.findChild(QWidget, "settings_page_workspace")
        self.assertEqual(workspace.palette().color(QPalette.Window).name(), "#ffffff")
        late.deleteLater()


class ThemePropagateLinearizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        reset_theme_runtime_for_tests()
        from mygui.application_theme.windows import reset_window_registry_for_tests

        reset_window_registry_for_tests()

    def tearDown(self) -> None:
        reset_qss_bindings_for_tests()
        reset_theme_runtime_for_tests()

    def test_overlapping_registered_roots_visit_each_widget_once(self) -> None:
        from mygui.application_theme.windows import default_window_registry, subscribe_theme_window

        parent = QWidget()
        child = QWidget(parent)
        grandchild = QWidget(child)
        subscribe_theme_window(parent)
        subscribe_theme_window(child)
        registry = default_window_registry()
        registry.apply_palette(self.app.palette())
        self.assertEqual(registry.max_visits("palette"), 1)
        self.assertEqual(registry.last_stage_visits["palette"].get(id(parent), 0), 1)
        self.assertEqual(registry.last_stage_visits["palette"].get(id(child), 0), 0)
        self.assertEqual(registry.last_stage_visits["palette"].get(id(grandchild), 0), 0)
        registry.apply_metrics(current_density_metrics())
        self.assertEqual(registry.max_visits("metrics"), 1)
        self.assertEqual(registry.last_stage_visits["metrics"].get(id(grandchild), 0), 0)
        self.assertGreaterEqual(registry.last_stage_visits["metrics"].get(id(parent), 0), 1)
        self.assertGreaterEqual(registry.last_stage_visits["metrics"].get(id(child), 0), 1)
        parent.deleteLater()
        self.app.processEvents()

    def test_construction_batch_defers_sync_until_exit(self) -> None:
        from mygui.application_theme import (
            AppearancePreferences,
            ThemeMode,
            compose_theme_service,
            theme_construction_batch,
        )
        from mygui.application_theme.windows import subscribe_theme_window

        theme = compose_theme_service(self.app)
        theme.apply_committed(AppearancePreferences(mode=ThemeMode.DARK))
        expected = theme.snapshot().palette.color(QPalette.ColorRole.Window).name().lower()
        widget = QWidget()
        origin = widget.palette().color(QPalette.ColorRole.Window).name().lower()
        with theme_construction_batch():
            subscribe_theme_window(widget)
            self.assertEqual(
                widget.palette().color(QPalette.ColorRole.Window).name().lower(),
                origin,
            )
        self.assertEqual(
            widget.palette().color(QPalette.ColorRole.Window).name().lower(),
            expected,
        )
        widget.deleteLater()
        theme.shutdown()
        self.app.processEvents()

    def test_dynamic_participant_can_defer_initial_sync(self) -> None:
        from mygui.application_theme import windows

        parent = QWidget()
        participant = QWidget(parent)
        with mock.patch.object(windows, "_sync_widget") as sync_widget:
            windows.subscribe_theme_window(
                participant,
                sync_initial=False,
            )
        sync_widget.assert_not_called()
        self.assertIn(id(participant), windows.default_window_registry()._metrics)
        parent.deleteLater()
        self.app.processEvents()

    def test_palette_memento_restores_viewport_flags_and_skips_departed_widgets(self) -> None:
        from mygui.application_theme.windows import ThemeWindowRegistry

        registry = ThemeWindowRegistry()
        scroll = QScrollArea()
        departed = QWidget()
        destroyed = QWidget()
        registry.register(scroll)
        registry.register(departed)
        registry.register(destroyed)
        viewport = scroll.viewport()
        original = QPalette(viewport.palette())
        flag = viewport.testAttribute(Qt.WA_SetPalette)
        captured = registry.capture_palettes()
        self.assertEqual(len(captured), 4)
        registry.unregister(departed)
        departed_palette = QPalette(departed.palette())
        departed_palette.setColor(QPalette.Window, QColor("magenta"))
        departed.setPalette(departed_palette)
        destroyed.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        changed = QPalette(original)
        changed.setColor(QPalette.Window, QColor("cyan"))
        registry.apply_palette(changed)
        registry.restore_palettes(captured, original)
        self.assertEqual(viewport.palette(), original)
        self.assertEqual(viewport.testAttribute(Qt.WA_SetPalette), flag)
        self.assertEqual(departed.palette(), departed_palette)
        scroll.deleteLater()
        departed.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_classify_icon_source_caches_absolute_user_paths(self) -> None:
        from mygui.application_theme.icons import (
            classify_icon_source,
            clear_icon_classify_cache_for_tests,
        )

        clear_icon_classify_cache_for_tests()
        user = "E:/not-bundled/custom.svg"
        first = classify_icon_source(user)
        second = classify_icon_source(user)
        self.assertEqual(first, IconRole.USER_DATA)
        self.assertEqual(second, IconRole.USER_DATA)
        bundled = icon_path("setting.svg")
        self.assertEqual(classify_icon_source(bundled), IconRole.CHROME)
        self.assertEqual(classify_icon_source(bundled), IconRole.CHROME)


if __name__ == "__main__":
    unittest.main()
