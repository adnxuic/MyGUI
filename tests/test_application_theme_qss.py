"""Bundled QSS token expansion, bind replay, and chrome-hex contracts."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

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
