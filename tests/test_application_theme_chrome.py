"""Chrome palette, density metrics, icon DPR cache, and cached-window updates."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from mygui.application_settings.models import Density, ThemeMode
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
    compose_theme_snapshot,
    contrast_ratio,
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
        host_sheet = host.styleSheet().lower()
        self.assertIn(text, host_sheet)
        labels = [
            label
            for label in host.findChildren(QLabel)
            if str(label.text() or "").strip()
            and label.objectName() not in {"empty_state_title", "empty_state_detail"}
        ]
        self.assertTrue(labels)
        ancestor_sheets = [
            widget.styleSheet().lower()
            for widget in (host, *host.findChildren(QWidget))
            if widget.styleSheet()
        ]
        self.assertTrue(any(text in sheet for sheet in ancestor_sheets))
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

        figure_sheet = self.window.figure_window.styleSheet().lower()
        self.assertIn(content, figure_sheet)
        self.assertNotIn("#0f172a", figure_sheet)
        viewport = canvas.scroArea.viewport()
        self.assertEqual(
            viewport.palette().color(QPalette.ColorRole.Window).name().lower(),
            content,
        )

        right_sheet = self.window.right_column.styleSheet().lower()
        self.assertIn(surface_alt, right_sheet)
        self.assertNotIn("#0b1220", right_sheet)
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


if __name__ == "__main__":
    unittest.main()
