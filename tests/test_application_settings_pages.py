"""Appearance, Workspace, and New Figure Settings Center pages."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QWidget,
)

from mygui.application_settings import (
    APPEARANCE_DENSITY,
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    ApplicationSettingsService,
    MemorySettingsDocumentPort,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    PAGE_APPEARANCE,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
    SettingsValidationError,
    WORKSPACE_LAYOUT,
    WORKSPACE_REMEMBER_LAYOUT,
    production_settings_registry,
)
from mygui.application_settings.models import Density, ThemeMode
from mygui.application_settings.values import (
    MAX_DOCUMENT_DPI,
    MAX_FIGURE_INCHES,
    MAX_UI_FONT_PT,
    MIN_DOCUMENT_DPI,
    MIN_FIGURE_INCHES,
    MIN_UI_FONT_PT,
)
from mygui.application_theme import (
    AppearancePreferences,
    EffectiveScheme,
    FakeStyleHints,
    ThemeService,
)
from mygui.widgets.settings_center.pages import page_matches
from mygui.widgets.settings_pages import (
    AppearanceSettingsPage,
    NewFigureSettingsPage,
    WorkspaceSettingsPage,
    builtin_page_specs,
    register_pages,
    try_register_with_shell,
)
from mygui.widgets.settings_pages.appearance import APPEARANCE_INTRO, page_spec
from mygui.widgets.settings_pages.new_figure import (
    NEW_FIGURE_PRECEDENCE,
)
from mygui.widgets.settings_pages.workspace import (
    RESET_BUTTON_TEXT,
    RESET_DIALOG_TEXT,
    RESET_DIALOG_TITLE,
)

ROOT = Path(__file__).resolve().parents[1]
PAGES_ROOT = ROOT / "mygui" / "widgets" / "settings_pages"
QSS_PATH = PAGES_ROOT / "style.qss"
FOOTER_TEXTS = frozenset(
    {"Apply", "OK", "Cancel", "Restore page defaults", "Restore Page Defaults"}
)


class RecordingTheme:
    """Test double for ThemeService.preview."""

    def __init__(self, scheme: EffectiveScheme = EffectiveScheme.LIGHT) -> None:
        self.scheme = scheme
        self.preview_calls: list[AppearancePreferences] = []

    def resolve_effective_scheme(self, mode=None):
        return self.scheme

    def preview(self, preferences: AppearancePreferences) -> None:
        self.preview_calls.append(preferences)


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class SettingsPagesCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qapp()

    def setUp(self) -> None:
        self.widgets: list[QWidget] = []

    def tearDown(self) -> None:
        while self.widgets:
            widget = self.widgets.pop()
            widget.hide()
            widget.deleteLater()
        self.app.processEvents()

    def _track(self, widget: QWidget) -> QWidget:
        self.widgets.append(widget)
        return widget


class PageSpecAndRegistrationTests(SettingsPagesCase):
    def test_page_spec_matches_registry_keys_and_editors(self) -> None:
        registry = production_settings_registry()
        specs = builtin_page_specs()
        self.assertEqual(
            [spec.page_id for spec in specs],
            [PAGE_APPEARANCE, PAGE_WORKSPACE, PAGE_NEW_FIGURE],
        )
        for spec in specs:
            page = registry.page(spec.page_id)
            self.assertEqual(spec.title, page.title)
            for key in page.setting_keys:
                setting = registry.spec(key)
                self.assertTrue(page_matches(spec, setting.key, registry))
                if setting.label:
                    self.assertTrue(page_matches(spec, setting.label, registry))
                if setting.choices:
                    choice = setting.choices[0]
                    self.assertTrue(
                        page_matches(
                            spec,
                            str(getattr(choice, "value", choice)),
                            registry,
                        )
                    )
            widget = self._track(spec.factory(None))
            self.assertEqual(widget.page_id(), spec.page_id)
            self.assertTrue(callable(spec.factory))

    def test_module_page_spec_matches_class(self) -> None:
        spec = page_spec()
        self.assertEqual(spec.page_id, PAGE_APPEARANCE)
        self.assertEqual(spec.description, APPEARANCE_INTRO)

    def test_register_pages_invokes_shell_hook(self) -> None:
        recorded: list[object] = []
        specs = register_pages(recorded.append)
        self.assertEqual(recorded, list(specs))
        self.assertEqual(len(specs), 3)

    def test_try_register_with_shell_is_safe_when_absent(self) -> None:
        result = try_register_with_shell()
        self.assertIsInstance(result, bool)

    def test_pages_have_no_window_footer(self) -> None:
        pages = (
            self._track(AppearanceSettingsPage()),
            self._track(WorkspaceSettingsPage()),
            self._track(NewFigureSettingsPage()),
        )
        for page in pages:
            self.assertEqual(page.findChildren(QDialogButtonBox), [])
            texts = {button.text() for button in page.findChildren(QPushButton)}
            self.assertTrue(texts.isdisjoint(FOOTER_TEXTS), texts)


class AppearancePageTests(SettingsPagesCase):
    def test_defaults_and_system_effective_caption(self) -> None:
        theme = RecordingTheme(EffectiveScheme.LIGHT)
        page = self._track(AppearanceSettingsPage(theme=theme))
        values = page.draft_values()
        self.assertEqual(values[APPEARANCE_THEME_MODE], ThemeMode.SYSTEM)
        self.assertEqual(values[APPEARANCE_UI_FONT_POINT_SIZE], 9)
        self.assertEqual(values[APPEARANCE_DENSITY], Density.STANDARD)
        self.assertEqual(page.system_radio.text(), "System (Light)")
        self.assertTrue(page.system_radio.isChecked())
        self.assertEqual(theme.preview_calls, [])

        theme.scheme = EffectiveScheme.DARK
        page._refresh_system_caption()
        self.assertEqual(page.system_radio.text(), "System (Dark)")

    def test_change_stages_draft_and_calls_preview(self) -> None:
        theme = RecordingTheme()
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(AppearanceSettingsPage(session=session, theme=theme))
        page.dark_radio.click()
        self.assertEqual(page.draft_values()[APPEARANCE_THEME_MODE], ThemeMode.DARK)
        self.assertEqual(session.dirty_patch()[APPEARANCE_THEME_MODE], ThemeMode.DARK)
        self.assertEqual(theme.preview_calls[-1].mode, ThemeMode.DARK)

        page.font_spin.setValue(16)
        self.assertEqual(page.draft_values()[APPEARANCE_UI_FONT_POINT_SIZE], 16)
        self.assertEqual(theme.preview_calls[-1].font_pt, 16)

        page.comfortable_radio.click()
        self.assertEqual(page.draft_values()[APPEARANCE_DENSITY], Density.COMFORTABLE)
        self.assertEqual(theme.preview_calls[-1].density, Density.COMFORTABLE)

    def test_restore_page_defaults_previews_registry_defaults(self) -> None:
        theme = RecordingTheme()
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(AppearanceSettingsPage(session=session, theme=theme))
        page.dark_radio.click()
        page.font_spin.setValue(12)
        page.apply_page_defaults()
        values = page.draft_values()
        self.assertEqual(values[APPEARANCE_THEME_MODE], ThemeMode.SYSTEM)
        self.assertEqual(values[APPEARANCE_UI_FONT_POINT_SIZE], 9)
        self.assertEqual(values[APPEARANCE_DENSITY], Density.STANDARD)
        self.assertEqual(theme.preview_calls[-1].mode, ThemeMode.SYSTEM)
        self.assertEqual(
            session.dirty_patch()[APPEARANCE_THEME_MODE], ThemeMode.SYSTEM
        )

    def test_invalid_font_size_uses_registry_validator(self) -> None:
        theme = RecordingTheme()
        page = self._track(AppearanceSettingsPage(theme=theme))
        registry = production_settings_registry()
        with self.assertRaises(SettingsValidationError):
            registry.spec(APPEARANCE_UI_FONT_POINT_SIZE).normalize(MIN_UI_FONT_PT - 1)
        with self.assertRaises(SettingsValidationError):
            page.set_draft_value(APPEARANCE_UI_FONT_POINT_SIZE, MAX_UI_FONT_PT + 1)
        self.assertEqual(page.draft_values()[APPEARANCE_UI_FONT_POINT_SIZE], 9)
        self.assertEqual(theme.preview_calls, [])

    def test_real_theme_service_preview_does_not_mutate_matplotlib(self) -> None:
        import matplotlib as mpl

        hints = FakeStyleHints(Qt.ColorScheme.Light)
        theme = ThemeService(self.app, style_hints=hints)
        origin_font = self.app.font()
        origin_palette = self.app.palette()
        origin_sheet = self.app.styleSheet()
        before = dict(mpl.rcParams)
        page = self._track(AppearanceSettingsPage(theme=theme))
        try:
            page.dark_radio.click()
            self.assertEqual(theme.snapshot().preferences.mode, ThemeMode.DARK)
            self.assertEqual(dict(mpl.rcParams), before)
        finally:
            theme.cancel_preview()
            theme.shutdown()
            self.app.setFont(origin_font)
            self.app.setPalette(origin_palette)
            self.app.setStyleSheet(origin_sheet)


class WorkspacePageTests(SettingsPagesCase):
    def test_remember_layout_default_and_draft(self) -> None:
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(WorkspaceSettingsPage(session=session))
        self.assertTrue(page.draft_values()[WORKSPACE_REMEMBER_LAYOUT])
        self.assertIn("splitter", page.findChildren(QLabel)[0].text().lower())
        page.remember_box.setChecked(False)
        self.assertFalse(session.dirty_patch()[WORKSPACE_REMEMBER_LAYOUT])

    def test_remember_checkbox_text_toggles_on_click(self) -> None:
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(WorkspaceSettingsPage(session=session))
        page.show()
        page.remember_box.adjustSize()
        self.app.processEvents()
        self.assertEqual(page.remember_box.text(), "Remember workspace layout")
        self.assertTrue(page.remember_box.isChecked())
        QTest.mouseClick(page.remember_box, Qt.LeftButton)
        self.app.processEvents()
        self.assertFalse(page.remember_box.isChecked())
        self.assertFalse(session.dirty_patch()[WORKSPACE_REMEMBER_LAYOUT])

    def test_reset_confirm_yes_runs_immediate_command(self) -> None:
        reset_now = Mock()
        port = Mock()
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(
            WorkspaceSettingsPage(
                session=session,
                reset_layout_now=reset_now,
                layout_port=port,
            )
        )
        with patch("mygui.widgets.settings_pages.workspace.ask_confirmation", return_value=True) as ask:
            page.reset_button.click()
        reset_now.assert_called_once_with()
        port.save_layout.assert_not_called()
        self.assertNotIn(WORKSPACE_LAYOUT, session.dirty_patch())
        ask.assert_called_once()
        self.assertIn(RESET_DIALOG_TITLE, str(ask.call_args))
        self.assertIn("immediately", RESET_DIALOG_TEXT)

    def test_restore_defaults_does_not_stage_workspace_layout(self) -> None:
        from mygui.application_settings.models import DEFAULT_WORKSPACE_LAYOUT

        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        committed = service.commit_patch(
            service.begin_session(),
            {
                WORKSPACE_REMEMBER_LAYOUT: False,
                WORKSPACE_LAYOUT: DEFAULT_WORKSPACE_LAYOUT,
            },
        )
        self.assertTrue(committed.success)
        session = service.begin_session()
        result = service.reset_section(session, PAGE_WORKSPACE)
        self.assertTrue(result.success)
        dirty = dict(session.dirty_patch())
        self.assertNotIn(WORKSPACE_LAYOUT, dirty)
        self.assertEqual(dirty[WORKSPACE_REMEMBER_LAYOUT], True)
        page = self._track(WorkspaceSettingsPage(session=session))
        page.remember_box.setChecked(False)
        self.assertNotIn(WORKSPACE_LAYOUT, session.dirty_patch())

    def test_reset_confirm_no_does_not_reset(self) -> None:
        reset_now = Mock()
        page = self._track(WorkspaceSettingsPage(reset_layout_now=reset_now))
        with patch("mygui.widgets.settings_pages.workspace.ask_confirmation", return_value=False):
            self.assertFalse(page.reset_workspace_layout_now())
        reset_now.assert_not_called()

    def test_reset_button_text_and_layout_port_fallback(self) -> None:
        port = Mock()
        page = self._track(WorkspaceSettingsPage(layout_port=port))
        self.assertEqual(page.reset_button.text(), RESET_BUTTON_TEXT)
        with patch("mygui.widgets.settings_pages.workspace.ask_confirmation", return_value=True):
            self.assertTrue(page.reset_workspace_layout_now())
        port.save_layout.assert_called_once()


class NewFigurePageTests(SettingsPagesCase):
    def test_defaults_and_explanatory_copy(self) -> None:
        page = self._track(NewFigureSettingsPage())
        values = page.draft_values()
        self.assertEqual(values[NEW_FIGURE_WIDTH_IN], 6.4)
        self.assertEqual(values[NEW_FIGURE_HEIGHT_IN], 4.8)
        self.assertEqual(values[NEW_FIGURE_DOCUMENT_DPI], 100.0)
        copy_text = " ".join(label.text() for label in page.findChildren(QLabel))
        self.assertIn("Style creation", copy_text)
        self.assertIn("text or Excel", copy_text)
        self.assertIn(NEW_FIGURE_PRECEDENCE.split(":")[0], copy_text)
        self.assertIn("explicit input", copy_text)
        self.assertIn("schema-v23", copy_text)
        self.assertIn("do not overwrite", copy_text.lower())
        self.assertIn("built-in defaults", copy_text)

    def test_draft_stages_session_without_footer_commit(self) -> None:
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        session = service.begin_session()
        page = self._track(NewFigureSettingsPage(session=session))
        page.width_spin.setValue(8.0)
        self.assertEqual(session.dirty_patch()[NEW_FIGURE_WIDTH_IN], 8.0)
        self.assertEqual(service.snapshot().new_figure.width_in, 6.4)

    def test_range_validation_uses_registry(self) -> None:
        page = self._track(NewFigureSettingsPage())
        registry = production_settings_registry()
        cases = (
            (NEW_FIGURE_WIDTH_IN, MIN_FIGURE_INCHES - 0.01),
            (NEW_FIGURE_HEIGHT_IN, MAX_FIGURE_INCHES + 1),
            (NEW_FIGURE_DOCUMENT_DPI, MIN_DOCUMENT_DPI - 1),
            (NEW_FIGURE_DOCUMENT_DPI, MAX_DOCUMENT_DPI + 1),
        )
        for key, raw in cases:
            with self.subTest(key=key, raw=raw):
                with self.assertRaises(SettingsValidationError):
                    registry.spec(key).normalize(raw)
                before = page.draft_values()[key]
                with self.assertRaises(SettingsValidationError):
                    page.set_draft_value(key, raw)
                self.assertEqual(page.draft_values()[key], before)


class AccessibilityTests(SettingsPagesCase):
    def test_editors_have_accessible_names_buddies_and_tab_focus(self) -> None:
        pages = (
            self._track(AppearanceSettingsPage(theme=RecordingTheme())),
            self._track(WorkspaceSettingsPage()),
            self._track(NewFigureSettingsPage()),
        )
        for page in pages:
            with self.subTest(page=page.page_id()):
                for editor in page.keyboard_editors():
                    name = editor.accessibleName()
                    self.assertTrue(str(name).strip(), editor.objectName())
                    self.assertTrue(
                        int(editor.focusPolicy()) & int(Qt.TabFocus),
                        editor.objectName(),
                    )
                for key, label in page.buddy_labels().items():
                    self.assertIsNotNone(label.buddy(), key)
                    self.assertTrue(str(label.text()).strip(), key)

    def test_hint_contrast_uses_theme_tokens_not_hardcoded_gray(self) -> None:
        source = QSS_PATH.read_text(encoding="utf-8")
        self.assertIn("{{COLOR_TEXT_MUTED}}", source)
        self.assertIn("{{COLOR_TEXT_PRIMARY}}", source)
        self.assertNotIn("gray", source.casefold())
        self.assertNotRegex(source, r"color:\s*#[89a-fA-F][0-9a-fA-F]{5}")

    def test_package_does_not_import_matplotlib_or_figure_domain(self) -> None:
        forbidden = ("matplotlib", "mygui.figuremodify", "mygui.database")
        for path in PAGES_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            any(alias.name.startswith(name) for name in forbidden),
                            f"{path.name} imports {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(
                        any(node.module.startswith(name) for name in forbidden),
                        f"{path.name} imports {node.module}",
                    )


if __name__ == "__main__":
    unittest.main()
