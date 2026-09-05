"""Bundled QSS token expansion, bind replay, and chrome-hex contracts."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from mygui.application_theme import (
    DIALOG_QSS_RESOURCE,
    CONTRAST_PAIRS_BODY,
    CONTRAST_PAIRS_FOCUS,
    DARK_QSS_TOKENS,
    EffectiveScheme,
    LIGHT_QSS_TOKENS,
    MAINWINDOW_QSS_RESOURCE,
    ThemeBindingRegistry,
    bind_qss,
    bind_widget_qss,
    binding_count,
    contrast_ratio,
    current_qss_tokens,
    qss_tokens_for_scheme,
    rebind_qss_bindings,
    reset_qss_bindings_for_tests,
)
from mygui.widgets.mainwindow_init.basic_setting import render_mainwindow_stylesheet
from mygui.resources import expand_qss_tokens, load_qss_resource
from mygui.widgets.left_column.py_setting_dialog import PySettingDialog
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyStyleDialog

ROOT = Path(__file__).resolve().parents[1]
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
# Brand / example data colors that may remain in bundled QSS. Chrome hex must
# come from snapshot tokens; this set is the explicit exception list.
CHROME_HEX_WHITELIST = frozenset()


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _bundled_qss_paths() -> list[Path]:
    return sorted(ROOT.joinpath("mygui").rglob("*.qss"))


def _color_token_values(tokens: dict[str, str]) -> set[str]:
    return {
        str(value).lower()
        for name, value in tokens.items()
        if str(name).startswith("COLOR_") and str(value).startswith("#")
    }


class QssTokenExpansionTests(unittest.TestCase):
    def test_all_bundled_qss_expand_for_light_and_dark(self) -> None:
        for path in _bundled_qss_paths():
            relative = path.relative_to(ROOT).as_posix()
            source = path.read_text(encoding="utf-8")
            for scheme, tokens in (
                (EffectiveScheme.LIGHT, LIGHT_QSS_TOKENS),
                (EffectiveScheme.DARK, DARK_QSS_TOKENS),
            ):
                with self.subTest(resource=relative, scheme=scheme.value):
                    rendered = load_qss_resource(relative, tokens=tokens)
                    self.assertNotIn("{{", rendered)
                    self.assertNotIn("}}", rendered)
                    again = expand_qss_tokens(source, tokens)
                    self.assertEqual(rendered, again)

    def test_same_snapshot_is_deterministic(self) -> None:
        resource = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        first = load_qss_resource(resource, tokens=DARK_QSS_TOKENS)
        second = load_qss_resource(resource, tokens=dict(DARK_QSS_TOKENS))
        self.assertEqual(first, second)

    def test_expanded_hex_is_snapshot_chrome_or_whitelist(self) -> None:
        for path in _bundled_qss_paths():
            relative = path.relative_to(ROOT).as_posix()
            for tokens in (LIGHT_QSS_TOKENS, DARK_QSS_TOKENS):
                rendered = load_qss_resource(relative, tokens=tokens)
                allowed = _color_token_values(dict(tokens)) | {
                    value.lower() for value in CHROME_HEX_WHITELIST
                }
                leftovers = [
                    match
                    for match in _HEX.findall(rendered)
                    if match.lower() not in allowed
                ]
                with self.subTest(resource=relative):
                    self.assertEqual(leftovers, [])

    def test_qss_tokens_for_scheme_matches_tables(self) -> None:
        self.assertEqual(
            dict(qss_tokens_for_scheme(EffectiveScheme.LIGHT)),
            dict(LIGHT_QSS_TOKENS),
        )
        self.assertEqual(
            dict(qss_tokens_for_scheme("dark")),
            dict(DARK_QSS_TOKENS),
        )


class QssContrastContractTests(unittest.TestCase):
    def test_light_body_text_meets_4_5(self) -> None:
        tokens = LIGHT_QSS_TOKENS
        for scheme, foreground, background in CONTRAST_PAIRS_BODY:
            if scheme != "light":
                continue
            with self.subTest(pair=f"{foreground}/{background}"):
                self.assertGreaterEqual(
                    contrast_ratio(tokens[foreground], tokens[background]),
                    4.5,
                )

    def test_light_focus_and_strong_border_meet_3(self) -> None:
        tokens = LIGHT_QSS_TOKENS
        for scheme, foreground, background in CONTRAST_PAIRS_FOCUS:
            if scheme != "light":
                continue
            with self.subTest(pair=f"{foreground}/{background}"):
                self.assertGreaterEqual(
                    contrast_ratio(tokens[foreground], tokens[background]),
                    3.0,
                )

    def test_dark_body_text_meets_4_5(self) -> None:
        tokens = DARK_QSS_TOKENS
        pairs = (
            ("COLOR_TEXT_PRIMARY", "COLOR_CONTENT_BACKGROUND"),
            ("COLOR_TEXT_PRIMARY", "COLOR_SURFACE"),
            ("COLOR_TEXT_MUTED", "COLOR_SURFACE"),
            ("COLOR_TEXT_ON_DARK", "COLOR_COMMAND_BACKGROUND"),
        )
        for foreground, background in pairs:
            with self.subTest(pair=f"{foreground}/{background}"):
                self.assertGreaterEqual(
                    contrast_ratio(tokens[foreground], tokens[background]),
                    4.5,
                )

    def test_dark_focus_and_strong_border_meet_3(self) -> None:
        tokens = DARK_QSS_TOKENS
        pairs = (
            ("COLOR_FOCUS", "COLOR_SURFACE"),
            ("COLOR_FOCUS", "COLOR_CONTENT_BACKGROUND"),
            ("COLOR_BORDER_STRONG", "COLOR_SURFACE"),
        )
        for foreground, background in pairs:
            with self.subTest(pair=f"{foreground}/{background}"):
                self.assertGreaterEqual(
                    contrast_ratio(tokens[foreground], tokens[background]),
                    3.0,
                )

    def test_light_status_text_keeps_historical_contrast(self) -> None:
        tokens = LIGHT_QSS_TOKENS
        background = tokens["COLOR_STATUS_BACKGROUND"]
        for name in (
            "COLOR_TEXT_ON_DARK",
            "COLOR_TEXT_MUTED_ON_DARK",
            "COLOR_SUCCESS",
            "COLOR_WARNING",
            "COLOR_ERROR",
        ):
            with self.subTest(token=name):
                self.assertGreaterEqual(
                    contrast_ratio(tokens[name], background),
                    4.5,
                )


class QssBindReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        reset_qss_bindings_for_tests()

    def tearDown(self) -> None:
        reset_qss_bindings_for_tests()

    def test_bind_widget_qss_sets_stylesheet(self) -> None:
        widget = QWidget()
        bind_widget_qss(widget, DIALOG_QSS_RESOURCE)
        stylesheet = widget.styleSheet()
        self.assertTrue(stylesheet)
        self.assertNotIn("{{", stylesheet)
        self.assertIn(LIGHT_QSS_TOKENS["COLOR_SURFACE"], stylesheet)
        widget.deleteLater()
        self.app.processEvents()

    def test_rebind_updates_hidden_widget_without_cached_string(self) -> None:
        hidden = QWidget()
        hidden.hide()
        bind_qss(hidden, DIALOG_QSS_RESOURCE, LIGHT_QSS_TOKENS)
        self.assertIn(LIGHT_QSS_TOKENS["COLOR_SURFACE"], hidden.styleSheet())
        rebind_qss_bindings(DARK_QSS_TOKENS)
        self.assertIn(DARK_QSS_TOKENS["COLOR_SURFACE"], hidden.styleSheet())
        self.assertNotIn(LIGHT_QSS_TOKENS["COLOR_SURFACE"], hidden.styleSheet())
        hidden.deleteLater()
        self.app.processEvents()

    def test_destroyed_widget_leaves_the_registry(self) -> None:
        widget = QWidget()
        bind_widget_qss(widget, DIALOG_QSS_RESOURCE)
        self.assertGreaterEqual(binding_count(), 1)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(binding_count(), 0)

    def test_theme_binding_registry_applies_existing_resource(self) -> None:
        registry = ThemeBindingRegistry()
        widget = QWidget()
        registry.bind_qss(widget, DIALOG_QSS_RESOURCE)
        self.assertTrue(widget.styleSheet())
        registry.apply_stylesheets(
            {
                DIALOG_QSS_RESOURCE: load_qss_resource(
                    DIALOG_QSS_RESOURCE,
                    tokens=DARK_QSS_TOKENS,
                )
            }
        )
        self.assertIn(DARK_QSS_TOKENS["COLOR_SURFACE"], widget.styleSheet())
        widget.deleteLater()
        self.app.processEvents()

    def test_setting_dialog_bind_has_stylesheet(self) -> None:
        dialog = PySettingDialog()
        self.assertTrue(dialog.styleSheet())
        self.assertNotIn("{{", dialog.styleSheet())
        dialog.deleteLater()
        self.app.processEvents()

    def test_style_dialog_bind_has_stylesheet(self) -> None:
        dialog = PyStyleDialog("style")
        self.assertTrue(dialog.styleSheet())
        self.assertNotIn("{{", dialog.styleSheet())
        dialog.deleteLater()
        self.app.processEvents()

    def test_fit_dialog_object_accepts_dialog_qss(self) -> None:
        dialog = QDialog()
        dialog.setObjectName("fit_dialog")
        bind_widget_qss(dialog, DIALOG_QSS_RESOURCE)
        self.assertTrue(dialog.styleSheet())
        dialog.deleteLater()
        self.app.processEvents()

    def test_current_qss_tokens_are_explicit_snapshot_values(self) -> None:
        tokens = current_qss_tokens()
        self.assertIn("COLOR_SURFACE", tokens)
        self.assertEqual(tokens["COLOR_SURFACE"], LIGHT_QSS_TOKENS["COLOR_SURFACE"])

    def test_mainwindow_stylesheet_expands_from_tokens_not_import_time(self) -> None:
        light = render_mainwindow_stylesheet(tokens=LIGHT_QSS_TOKENS)
        dark = render_mainwindow_stylesheet(tokens=DARK_QSS_TOKENS)
        self.assertNotIn("{{", light)
        self.assertNotIn("{{", dark)
        self.assertIn(LIGHT_QSS_TOKENS["COLOR_CONTENT_BACKGROUND"], light)
        self.assertIn(DARK_QSS_TOKENS["COLOR_CONTENT_BACKGROUND"], dark)
        self.assertNotEqual(light, dark)
        self.assertEqual(
            MAINWINDOW_QSS_RESOURCE,
            "mygui/widgets/mainwindow_init/style.qss",
        )


class QssSingleChannelPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        reset_qss_bindings_for_tests()
        from mygui.application_theme.runtime import reset_theme_runtime_for_tests

        reset_theme_runtime_for_tests()

    def tearDown(self) -> None:
        reset_qss_bindings_for_tests()
        from mygui.application_theme.runtime import reset_theme_runtime_for_tests

        reset_theme_runtime_for_tests()
        self.app.setStyleSheet("")

    def test_bind_widget_qss_uses_theme_registry_only(self) -> None:
        from mygui.application_theme import AppearancePreferences, ThemeMode, compose_theme_service

        theme = compose_theme_service(self.app)
        theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
        widget = QWidget()
        bind_widget_qss(widget, DIALOG_QSS_RESOURCE)
        self.assertEqual(binding_count(), 0)
        bound = list(theme.bindings.iter_bindings())
        self.assertEqual(len(bound), 1)
        self.assertIs(bound[0][0], widget)
        widget.deleteLater()
        self.app.processEvents()

    def test_theme_switch_is_one_app_sheet_and_changed_roots(self) -> None:
        from mygui.application_theme import AppearancePreferences, ThemeMode, compose_theme_service
        from mygui.application_theme.qss import rebind_qss_bindings

        theme = compose_theme_service(self.app)
        theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
        roots = [QWidget() for _ in range(3)]
        for widget in roots:
            bind_widget_qss(widget, DIALOG_QSS_RESOURCE)

        app_calls: list[object] = []
        widget_calls: list[object] = []
        origin_app = type(self.app).setStyleSheet
        origin_widget = QWidget.setStyleSheet

        def _app_sheet(app, sheet):
            app_calls.append(app)
            return origin_app(app, sheet)

        def _widget_sheet(widget, sheet):
            widget_calls.append(widget)
            return origin_widget(widget, sheet)

        with (
            patch.object(type(self.app), "setStyleSheet", _app_sheet),
            patch.object(QWidget, "setStyleSheet", _widget_sheet),
            patch(
                "mygui.application_theme.windows.refresh_chrome_style",
            ) as polish,
            patch(
                "mygui.application_theme.qss.rebind_qss_bindings",
                wraps=rebind_qss_bindings,
            ) as rebind,
        ):
            theme.apply_committed(AppearancePreferences(mode=ThemeMode.DARK))
        self.assertEqual(len(app_calls), 0)
        self.assertEqual(len(widget_calls), 3)
        self.assertEqual(set(widget_calls), set(roots))
        polish.assert_not_called()
        rebind.assert_not_called()
        for widget in roots:
            widget.deleteLater()
        self.app.processEvents()

    def test_identical_stylesheet_skips_setstylesheet(self) -> None:
        widget = QWidget()
        bind_widget_qss(widget, DIALOG_QSS_RESOURCE)
        origin = QWidget.setStyleSheet
        calls: list[object] = []

        def _sheet(target, stylesheet):
            calls.append(target)
            return origin(target, stylesheet)

        with patch.object(QWidget, "setStyleSheet", _sheet):
            bind_widget_qss(widget, DIALOG_QSS_RESOURCE)
        self.assertEqual(calls, [])
        widget.deleteLater()
        self.app.processEvents()

    def test_isolate_matplotlib_canvas_is_token_free_and_idempotent(self) -> None:
        from mygui.application_theme import isolate_matplotlib_canvas
        from mygui.application_theme.qss import MATPLOTLIB_CANVAS_ISOLATION_QSS

        widget = QWidget()
        isolate_matplotlib_canvas(widget)
        self.assertEqual(widget.styleSheet(), MATPLOTLIB_CANVAS_ISOLATION_QSS)
        origin = QWidget.setStyleSheet
        calls: list[object] = []

        def _sheet(target, stylesheet):
            calls.append(target)
            return origin(target, stylesheet)

        with patch.object(QWidget, "setStyleSheet", _sheet):
            isolate_matplotlib_canvas(widget)
        self.assertEqual(calls, [])
        widget.deleteLater()
        self.app.processEvents()

    def test_theme_rollback_restores_combo_without_tree_polish(self) -> None:
        from mygui.application_theme import AppearancePreferences, ThemeMode, compose_theme_service
        from PySide6.QtWidgets import QComboBox

        theme = compose_theme_service(self.app)
        theme.apply_committed(AppearancePreferences(mode=ThemeMode.LIGHT))
        host = QWidget()
        combo = QComboBox(host)
        combo.addItem("one")
        combo.addItem("two")
        combo.addItem("three")
        combo.setCurrentIndex(1)
        bind_widget_qss(host, DIALOG_QSS_RESOURCE)
        with patch("mygui.application_theme.windows.refresh_chrome_style") as polish:
            theme.preview(AppearancePreferences(mode=ThemeMode.DARK))
            self.assertEqual(combo.currentIndex(), 1)
            theme.cancel_preview()
        polish.assert_not_called()
        self.assertEqual(combo.currentIndex(), 1)
        host.deleteLater()
        self.app.processEvents()

    def test_qss_cache_does_not_depend_on_cwd(self) -> None:
        import os
        import tempfile

        from mygui.application_theme.qss import compose_component_stylesheet

        first = compose_component_stylesheet(DIALOG_QSS_RESOURCE, LIGHT_QSS_TOKENS)
        with tempfile.TemporaryDirectory() as folder:
            previous = os.getcwd()
            os.chdir(folder)
            try:
                second = compose_component_stylesheet(
                    DIALOG_QSS_RESOURCE, LIGHT_QSS_TOKENS
                )
            finally:
                os.chdir(previous)
        self.assertEqual(first, second)
        self.assertTrue(first)


class QssResourceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        reset_qss_bindings_for_tests()

    def tearDown(self) -> None:
        reset_qss_bindings_for_tests()

    def test_bundle_composes_ordered_resources_once(self) -> None:
        from mygui.application_theme import QssResourceBundle
        from mygui.application_theme.qss import compose_component_stylesheet

        bundle = QssResourceBundle(
            (
                "mygui/widgets/settings_center/style.qss",
                "mygui/widgets/settings_pages/style.qss",
            )
        )
        rendered = compose_component_stylesheet(bundle.key, LIGHT_QSS_TOKENS)
        self.assertIn("setting_dialog", rendered)
        self.assertIn("settings_page_appearance", rendered)
        widget = QWidget()
        bind_widget_qss(widget, bundle)
        self.assertIn("setting_dialog", widget.styleSheet())
        widget.deleteLater()
        self.app.processEvents()

    def test_workbench_scope_suppresses_covered_descendant_bindings(self) -> None:
        from mygui.application_theme import (
            WORKBENCH_QSS_BUNDLE,
            workbench_qss_scope,
        )

        root = QWidget()
        with workbench_qss_scope(root):
            child = QWidget(root)
            bind_widget_qss(child, "mygui/widgets/fig_control_window/style.qss")
        late_child = QWidget(root)
        bind_widget_qss(
            late_child,
            "mygui/widgets/fig_control_window/all_mod_widgets/style.qss",
        )

        self.assertTrue(root.styleSheet())
        self.assertEqual(root.property("myguiWorkbenchQssResources"), WORKBENCH_QSS_BUNDLE.key)
        self.assertEqual(child.styleSheet(), "")
        self.assertEqual(late_child.styleSheet(), "")
        self.assertEqual(binding_count(), 1)
        root.deleteLater()
        self.app.processEvents()
