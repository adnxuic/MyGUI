"""ThemeService resolution, density, contrast, System listening, and settings wiring."""

from __future__ import annotations

import ast
import math
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from mygui.application_settings import (
    APPEARANCE_THEME_MODE,
    ApplicationSettingsService,
    MemorySettingsDocumentPort,
    RecordingRuntimeBinder,
    SettingsHealth,
    SettingsRuntimeApplier,
    ThemeMode as SettingsThemeMode,
)
from mygui.application_settings.models import Density as SettingsDensity
from mygui.application_theme import (
    APPLY_STEPS,
    AppearancePreferences,
    CONTRAST_PAIRS_BODY,
    CONTRAST_PAIRS_FOCUS,
    DARK_CORE_TOKENS,
    DENSITY_BANDS,
    Density,
    EffectiveScheme,
    FakeStyleHints,
    LIGHT_COLOR_TOKENS,
    ThemeMode,
    ThemeService,
    ThemeSettingsBinder,
    ThemeValidationError,
    apply_committed_appearance,
    compose_theme_runtime_applier,
    compose_theme_service,
    contrast_ratio,
)
from mygui.application_theme.tokens import ICON_ROLES
from mygui.widgets.theme import QSS_TOKENS

ROOT = Path(__file__).resolve().parents[1]
THEME_PACKAGE = ROOT / "mygui" / "application_theme"
FORBIDDEN_IMPORT_PREFIXES = (
    "matplotlib",
    "mygui.figuremodify",
    "mygui.database",
)
FORBIDDEN_NAMES = frozenset(
    {
        "ComponentRegistry",
        "ComponentState",
        "TableRepository",
        "DeletionCoordinator",
    }
)


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _ThemeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()
        cls._origin_font = cls.app.font()
        cls._origin_palette = QPalette(cls.app.palette())
        cls._origin_stylesheet = cls.app.styleSheet()

    def setUp(self) -> None:
        self.hints = FakeStyleHints(Qt.ColorScheme.Light)
        self.theme = ThemeService(self.app, style_hints=self.hints)
        self.events: list[tuple[object, object]] = []
        self.theme.subscribe(lambda old, new: self.events.append((old, new)))

    def tearDown(self) -> None:
        self.theme.shutdown()
        self.app.setFont(self._origin_font)
        self.app.setPalette(self._origin_palette)
        self.app.setStyleSheet(self._origin_stylesheet)

    def _prefs(self, **kwargs) -> AppearancePreferences:
        values = {"mode": ThemeMode.LIGHT, "font_pt": 9, "density": Density.STANDARD}
        values.update(kwargs)
        return AppearancePreferences(**values)


class ThemeContractTests(_ThemeCase):
    def test_theme_mode_and_density_are_settings_owned(self) -> None:
        self.assertIs(ThemeMode, SettingsThemeMode)
        self.assertIs(Density, SettingsDensity)
        self.assertEqual(set(ThemeMode), {ThemeMode.SYSTEM, ThemeMode.LIGHT, ThemeMode.DARK})
        self.assertEqual(
            set(Density),
            {Density.COMPACT, Density.STANDARD, Density.COMFORTABLE},
        )

    def test_light_tokens_match_current_widget_theme(self) -> None:
        for key, value in QSS_TOKENS.items():
            if key.startswith("COLOR_"):
                self.assertEqual(LIGHT_COLOR_TOKENS[key], value, key)

    def test_dark_core_tokens_are_closed(self) -> None:
        expected = {
            "content": "#0F172A",
            "surface": "#1F2937",
            "surface-alt": "#273449",
            "command": "#0B1220",
            "text": "#F8FAFC",
            "muted": "#CBD5E1",
            "accent": "#2563EB",
            "focus": "#60A5FA",
            "border": "#475569",
            "error": "#FCA5A5",
        }
        self.assertEqual(dict(DARK_CORE_TOKENS), expected)

    def test_resolves_light_dark_and_system(self) -> None:
        self.theme.apply_committed(self._prefs(mode=ThemeMode.LIGHT))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)
        self.theme.apply_committed(self._prefs(mode=ThemeMode.DARK))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertEqual(self.theme.snapshot().tokens["content"], "#0F172A")
        self.hints.set_color_scheme(Qt.ColorScheme.Dark)
        self.theme.apply_committed(self._prefs(mode=ThemeMode.SYSTEM))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.hints.set_color_scheme(Qt.ColorScheme.Light)
        self.theme.apply_committed(self._prefs(mode=ThemeMode.SYSTEM))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)

    def test_unknown_system_uses_startup_native_luminance(self) -> None:
        light_palette = QPalette()
        light_palette.setColor(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.Window,
            QColor("#ffffff"),
        )
        dark_palette = QPalette()
        dark_palette.setColor(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.Window,
            QColor("#000000"),
        )
        unknown = FakeStyleHints(Qt.ColorScheme.Unknown)
        light_service = ThemeService(
            self.app,
            style_hints=unknown,
            native_palette=light_palette,
        )
        self.assertEqual(
            light_service.resolve_effective_scheme(ThemeMode.SYSTEM),
            EffectiveScheme.LIGHT,
        )
        light_service.shutdown()
        dark_unknown = FakeStyleHints(Qt.ColorScheme.Unknown)
        dark_service = ThemeService(
            self.app,
            style_hints=dark_unknown,
            native_palette=dark_palette,
        )
        self.assertEqual(
            dark_service.resolve_effective_scheme(ThemeMode.SYSTEM),
            EffectiveScheme.DARK,
        )
        dark_service.shutdown()

    def test_system_signal_reapplies_only_in_system_mode(self) -> None:
        self.theme.apply_committed(self._prefs(mode=ThemeMode.LIGHT))
        self.events.clear()
        self.hints.set_color_scheme(Qt.ColorScheme.Dark)
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)
        self.assertEqual(self.events, [])

        self.hints.set_color_scheme(Qt.ColorScheme.Light)
        self.theme.apply_committed(self._prefs(mode=ThemeMode.SYSTEM))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.LIGHT)
        self.events.clear()
        self.hints.set_color_scheme(Qt.ColorScheme.Dark)
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertEqual(len(self.events), 1)
        old, new = self.events[0]
        self.assertEqual(old.scheme, EffectiveScheme.LIGHT)
        self.assertEqual(new.scheme, EffectiveScheme.DARK)

    def test_font_bounds_and_three_density_metrics(self) -> None:
        with self.assertRaises(ThemeValidationError):
            AppearancePreferences(font_pt=7)
        with self.assertRaises(ThemeValidationError):
            AppearancePreferences(font_pt=17)
        for point_size in (8, 16):
            for density in Density:
                self.theme.apply_committed(
                    self._prefs(font_pt=point_size, density=density)
                )
                snapshot = self.theme.snapshot()
                band = DENSITY_BANDS[density]
                font_height = QFontMetrics(snapshot.font).height()
                floor = int(math.ceil(font_height)) + band.vertical_padding
                self.assertEqual(snapshot.preferences.font_pt, point_size)
                self.assertEqual(snapshot.metrics.vertical_padding, band.vertical_padding)
                self.assertEqual(snapshot.metrics.spacing_xs, band.spacing_xs)
                self.assertEqual(snapshot.metrics.spacing_xl, band.spacing_xl)
                self.assertEqual(snapshot.metrics.rail, max(band.rail, floor))
                self.assertEqual(snapshot.metrics.button, max(band.button, floor))
                self.assertEqual(snapshot.metrics.bottom, max(band.bottom, floor))
                self.assertEqual(snapshot.metrics.command, max(band.command, floor))
                self.assertEqual(snapshot.metrics.gallery, max(band.gallery, floor))
                self.assertEqual(
                    snapshot.metrics.gallery_icon,
                    max(band.gallery_icon, int(math.ceil(font_height))),
                )
                self.assertEqual(snapshot.metrics.table_row, max(band.table_row, floor))
                self.assertEqual(
                    snapshot.metrics.table_header, max(band.table_header, floor)
                )
                self.assertEqual(snapshot.metrics.tree, max(band.tree, floor))
                self.assertEqual(snapshot.metrics.control, max(band.control, floor))
                self.assertEqual(snapshot.font.pointSize(), point_size)

    def test_apply_success_emits_exactly_once(self) -> None:
        self.theme.apply_committed(self._prefs(mode=ThemeMode.DARK))
        self.assertEqual(len(self.events), 1)
        old, new = self.events[0]
        self.assertIsNot(old, new)
        self.assertEqual(new.scheme, EffectiveScheme.DARK)
        self.assertIn("mygui-theme-app", self.app.styleSheet())
        self.assertEqual(self.app.font().pointSize(), 9)
        self.assertEqual(dict(new.icon_roles), dict(ICON_ROLES))

        self.events.clear()
        self.theme.preview(self._prefs(mode=ThemeMode.LIGHT, font_pt=11))
        self.assertEqual(self.events, [])
        self.theme.apply_committed(self._prefs(mode=ThemeMode.LIGHT, font_pt=11))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][1].preferences.font_pt, 11)

    def test_body_and_focus_contrast_pairs(self) -> None:
        for scheme, foreground, background in CONTRAST_PAIRS_BODY:
            mode = ThemeMode.LIGHT if scheme == "light" else ThemeMode.DARK
            self.theme.apply_committed(self._prefs(mode=mode))
            tokens = self.theme.snapshot().tokens
            ratio = contrast_ratio(tokens[foreground], tokens[background])
            self.assertGreaterEqual(
                ratio,
                4.5,
                f"{scheme} {foreground} on {background} = {ratio:.2f}",
            )
        for scheme, foreground, background in CONTRAST_PAIRS_FOCUS:
            mode = ThemeMode.LIGHT if scheme == "light" else ThemeMode.DARK
            self.theme.apply_committed(self._prefs(mode=mode))
            tokens = self.theme.snapshot().tokens
            ratio = contrast_ratio(tokens[foreground], tokens[background])
            self.assertGreaterEqual(
                ratio,
                3.0,
                f"{scheme} {foreground} on {background} = {ratio:.2f}",
            )

    def test_does_not_force_fusion_style(self) -> None:
        before_type = type(self.app.style())
        self.theme.apply_committed(self._prefs(mode=ThemeMode.DARK))
        self.assertEqual(type(self.app.style()), before_type)
        for path in THEME_PACKAGE.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn('setStyle("Fusion")', source, path.name)
            self.assertNotIn("setStyle('Fusion')", source, path.name)

    def test_hidden_widget_bind_and_destroyed_detach(self) -> None:
        hidden = QWidget()
        hidden.hide()
        self.theme.bindings.bind_qss(hidden, "mygui/widgets/hidden.qss")
        self.theme.apply_committed(self._prefs(mode=ThemeMode.DARK))
        self.assertIn("mygui-theme-resource:mygui/widgets/hidden.qss:dark", hidden.styleSheet())
        hidden.deleteLater()
        self.app.processEvents()
        self.theme.apply_committed(self._prefs(mode=ThemeMode.LIGHT))

    def test_preview_cancel_restores_pre_session_snapshot(self) -> None:
        self.theme.apply_committed(self._prefs(mode=ThemeMode.LIGHT, font_pt=9))
        origin = self.theme.snapshot()
        self.events.clear()
        self.theme.preview(self._prefs(mode=ThemeMode.DARK, font_pt=16))
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertEqual(self.events, [])
        self.theme.cancel_preview()
        self.assertIs(self.theme.snapshot(), origin)
        self.assertEqual(self.app.font().pointSize(), 9)
        self.assertIn("mygui-theme-app", self.app.styleSheet())

    def test_settings_live_commit_goes_through_theme_service(self) -> None:
        extra = RecordingRuntimeBinder("extra")
        port = MemorySettingsDocumentPort()
        settings = ApplicationSettingsService(
            document=port,
            runtime_applier=SettingsRuntimeApplier(
                [ThemeSettingsBinder(self.theme), extra]
            ),
        )
        result = settings.commit_patch(
            settings.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.DARK},
        )
        self.assertTrue(result.success)
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertEqual([action[0] for action in extra.actions], ["apply", "confirm"])
        self.assertEqual(len(self.events), 1)

        extra.actions.clear()
        self.events.clear()
        origin = self.theme.snapshot()
        port.fail_commit = True
        failed = settings.commit_patch(
            settings.begin_session(),
            {APPEARANCE_THEME_MODE: ThemeMode.LIGHT},
        )
        self.assertFalse(failed.success)
        self.assertEqual(failed.health, SettingsHealth.OK)
        self.assertIs(self.theme.snapshot(), origin)
        self.assertEqual(self.theme.snapshot().scheme, EffectiveScheme.DARK)
        self.assertEqual([action[0] for action in extra.actions], ["apply", "rollback"])
        self.assertEqual(self.events, [])

    def test_theme_package_does_not_import_figure_or_registry(self) -> None:
        for path in sorted(THEME_PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                names: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        modules.append(node.module)
                    names.extend(alias.name for alias in node.names)
                for module in modules:
                    for prefix in FORBIDDEN_IMPORT_PREFIXES:
                        self.assertFalse(
                            module == prefix or module.startswith(prefix + "."),
                            f"{path.name} imports {module}",
                        )
                for name in names:
                    self.assertNotIn(name, FORBIDDEN_NAMES, path.name)

    def test_apply_steps_are_locked(self) -> None:
        self.assertEqual(APPLY_STEPS, ("font", "palette", "qss", "metrics", "icons"))


class ThemeStartupIntegrationTests(_ThemeCase):
    def test_compose_theme_service_shares_default_runtime_ports(self) -> None:
        from mygui.application_theme.qss import BundledQssRenderer
        from mygui.application_theme.runtime import (
            default_theme_runtime,
            reset_theme_runtime_for_tests,
        )

        reset_theme_runtime_for_tests()
        runtime = default_theme_runtime()
        theme = compose_theme_service(self.app, style_hints=self.hints)
        try:
            self.assertIs(theme._icons, runtime.icon_provider)
            self.assertIs(theme._metrics_port, runtime.metrics_applier)
            self.assertIs(runtime.binding_port, theme.bindings)
            self.assertIsInstance(theme._qss, BundledQssRenderer)
        finally:
            theme.shutdown()

    def test_settings_applier_uses_the_same_theme_service(self) -> None:
        extra = RecordingRuntimeBinder("extra")
        applier = compose_theme_runtime_applier(self.theme, extra=(extra,))
        self.assertIs(applier._binders[0]._theme, self.theme)
        self.assertIs(applier._binders[1], extra)

    def test_apply_committed_appearance_maps_settings_snapshot(self) -> None:
        port = MemorySettingsDocumentPort()
        settings = ApplicationSettingsService(document=port)
        apply_committed_appearance(self.theme, settings.snapshot())
        appearance = settings.snapshot().appearance
        published = self.theme.snapshot().preferences
        self.assertEqual(published.mode, appearance.theme_mode)
        self.assertEqual(published.font_pt, appearance.ui_font_point_size)
        self.assertEqual(published.density, appearance.density)

    def test_main_startup_order_applies_theme_before_widgets(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        helper = source[
            source.index("def compose_application_settings_and_theme") : source.index(
                "def _is_qsettings"
            )
        ]
        helper_markers = [
            "create_settings_backend",
            "compose_theme_service",
            "settings_service = ApplicationSettingsService",
            "compose_theme_runtime_applier(theme)",
            "apply_committed_appearance",
        ]
        helper_indexes = [helper.index(marker) for marker in helper_markers]
        self.assertEqual(helper_indexes, sorted(helper_indexes))

        startup = source[source.index('if __name__ == "__main__":') :]
        startup_markers = [
            "app = QApplication(sys.argv)",
            "install_font_diagnostic_bridge()",
            "setOrganizationName",
            "setApplicationName",
            "compose_application_settings_and_theme(app)",
            "window = MainWindow",
        ]
        startup_indexes = [startup.index(marker) for marker in startup_markers]
        self.assertEqual(startup_indexes, sorted(startup_indexes))
        self.assertNotIn("configure_application_font", startup)
        self.assertNotIn("setStyleSheet", startup)
        self.assertNotIn("load_qss_resource", startup)
        self.assertNotIn('setStyle("Fusion")', source)
        self.assertNotIn("setStyle('Fusion')", source)

    def test_mainwindow_binds_qss_instead_of_import_time_light_sheet(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        setup = source[source.index("def setup_ui") : source.index("def _valid_splitter_sizes")]
        self.assertIn("bind_widget_qss(self, MAINWINDOW_QSS_RESOURCE)", setup)
        self.assertIn("subscribe_theme_window(self)", setup)
        self.assertNotIn("mainwindow_qss", source)
        self.assertNotIn("setStyleSheet(mainwindow_qss)", source)
        basic = (
            ROOT / "mygui" / "widgets" / "mainwindow_init" / "basic_setting.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def render_mainwindow_stylesheet", basic)
        self.assertNotIn("mainwindow_qss = load_qss_resource", basic)

    def test_figure_canvas_isolates_matplotlib_through_theme_owner(self) -> None:
        source = (
            ROOT / "mygui" / "widgets" / "figure_canvas" / "py_figure_canves.py"
        ).read_text(encoding="utf-8")
        self.assertIn("isolate_matplotlib_canvas(self.canva)", source)
        self.assertNotIn("self.canva.setStyleSheet", source)


if __name__ == "__main__":
    unittest.main()
