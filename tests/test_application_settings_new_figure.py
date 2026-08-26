"""New Figure defaults for Style creation and first-time import.

Project restore/open must keep schema-v15 figure size and document DPI.
"""

from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import openpyxl
from PySide6.QtWidgets import QApplication

from mygui.application_settings import (
    APPEARANCE_THEME_MODE,
    APPEARANCE_UI_FONT_POINT_SIZE,
    ApplicationSettingsService,
    FixedNewFigureDefaults,
    MemorySettingsDocumentPort,
    NEW_FIGURE_DOCUMENT_DPI,
    NEW_FIGURE_HEIGHT_IN,
    NEW_FIGURE_WIDTH_IN,
    NewFigureSettings,
    ThemeMode,
    format_new_figure_field,
    resolve_new_figure_defaults,
)
from mygui.excel_io import import_excel_into_workspace
from mygui.project_io import (
    project_fingerprint,
    project_snapshot,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.text_io import import_text_into_workspace
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyStyleDialog
from main import MainWindow

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_DEFAULTS = NewFigureSettings(
    width_in=10.0,
    height_in=8.0,
    document_dpi=150.0,
)
PROJECT_SIZE = (4.0, 3.0, 100.0)


class CountingNewFigureDefaults:
    """Test double that records each ``current()`` call."""

    def __init__(self, settings: NewFigureSettings) -> None:
        self._settings = settings
        self.calls = 0

    def current(self) -> NewFigureSettings:
        self.calls += 1
        return self._settings


def _canvas_size(canvas) -> tuple[float, float, float]:
    width, height = (float(value) for value in canvas.fig.get_size_inches())
    return (width, height, float(canvas.document_dpi))


def _snapshot_size(canvas) -> tuple[float, float, float]:
    snapshot = canvas.component_snapshot()
    root = next(
        component
        for component in snapshot["components"]
        if component["id"] == snapshot["root_component_id"]
    )
    size_inches = root["properties"]["size_inches"]
    return (
        float(size_inches[0]),
        float(size_inches[1]),
        float(root["properties"]["dpi"]),
    )


class NewFigureDefaultsResolverTests(unittest.TestCase):
    def test_precedence_is_explicit_then_provider_then_builtin(self):
        self.assertEqual(
            resolve_new_figure_defaults(),
            NewFigureSettings(6.4, 4.8, 100.0),
        )
        provider = FixedNewFigureDefaults(CUSTOM_DEFAULTS)
        self.assertEqual(resolve_new_figure_defaults(provider), CUSTOM_DEFAULTS)
        overlay = resolve_new_figure_defaults(
            provider,
            width=5.0,
            dpi=72.0,
        )
        self.assertEqual(overlay.width_in, 5.0)
        self.assertEqual(overlay.height_in, 8.0)
        self.assertEqual(overlay.document_dpi, 72.0)

    def test_style_fields_keep_builtin_display_text(self):
        self.assertEqual(format_new_figure_field(6.4), "6.4")
        self.assertEqual(format_new_figure_field(4.8), "4.8")
        self.assertEqual(format_new_figure_field(100.0), "100")


class NewFigureCreationIsolationTests(unittest.TestCase):
    def test_restore_helpers_do_not_read_new_figure_defaults(self):
        window_source = (
            ROOT / "mygui/widgets/figure_canvas/py_figure_window.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(window_source)
        restore_fn = next(
            item
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PyFigureWindow"
            for item in node.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "load_project_figure_snapshot"
        )
        names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(restore_fn)
            if isinstance(node, (ast.Name, ast.Attribute))
        }
        self.assertNotIn("creation_figure_size", names)
        self.assertNotIn("resolve_new_figure_defaults", names)
        self.assertNotIn("new_figure_defaults_provider", names)
        self.assertNotIn("_new_figure_defaults", names)

        forbidden_hosts = (
            ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
            ROOT / "mygui/widgets/figure_canvas/canvas_materialize_handlers.py",
            ROOT / "mygui/widgets/figure_canvas/canvas_snapshot.py",
            ROOT / "mygui/project_io.py",
        )
        for path in forbidden_hosts:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "application_settings",
                text,
                f"{path.name} must not read application settings",
            )


class NewFigureCreationPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def _inject(self, settings: NewFigureSettings = CUSTOM_DEFAULTS):
        provider = CountingNewFigureDefaults(settings)
        self.window.figure_window.set_new_figure_defaults_provider(provider)
        return provider

    def test_provider_is_read_live_and_not_cached(self):
        service = ApplicationSettingsService(
            document=MemorySettingsDocumentPort(),
        )
        self.window.figure_window.set_new_figure_defaults_provider(
            service.new_figure_defaults_provider()
        )
        self.assertEqual(
            self.window.figure_window.creation_figure_size(),
            (6.4, 4.8, 100.0),
        )
        service.commit_patch(
            service.begin_session(),
            {
                NEW_FIGURE_WIDTH_IN: 9.1,
                NEW_FIGURE_HEIGHT_IN: 7.2,
                NEW_FIGURE_DOCUMENT_DPI: 175.0,
            },
        )
        self.assertEqual(
            self.window.figure_window.creation_figure_size(),
            (9.1, 7.2, 175.0),
        )

    def test_style_dialog_prefills_provider_and_explicit_input_wins(self):
        self._inject()
        dialog = PyStyleDialog("default", self.window.figure_window)
        try:
            self.assertEqual(dialog.width_line.text(), "10")
            self.assertEqual(dialog.height_line.text(), "8")
            self.assertEqual(dialog.dpi_line.text(), "150")
            dialog.width_line.setText("5")
            dialog.height_line.setText("4")
            dialog.dpi_line.setText("72")
            dialog.canva_name_line.setText("ExplicitStyle")
            dialog.accept()
        finally:
            dialog.close()
        canvas = self.window.figure_window.current_canva
        self.assertIsNotNone(canvas)
        self.assertEqual(_canvas_size(canvas), (5.0, 4.0, 72.0))
        self.assertEqual(_snapshot_size(canvas), (5.0, 4.0, 72.0))

    def test_reused_style_dialog_rereads_provider_on_show(self):
        first = FixedNewFigureDefaults(CUSTOM_DEFAULTS)
        self.window.figure_window.set_new_figure_defaults_provider(first)
        dialog = PyStyleDialog("default", self.window.figure_window)
        try:
            self.assertEqual(dialog.width_line.text(), "10")
            self.window.figure_window.set_new_figure_defaults_provider(
                FixedNewFigureDefaults(
                    NewFigureSettings(11.0, 9.0, 200.0),
                )
            )
            dialog.show()
            self.app.processEvents()
            self.assertEqual(dialog.width_line.text(), "11")
            self.assertEqual(dialog.height_line.text(), "9")
            self.assertEqual(dialog.dpi_line.text(), "200")
        finally:
            dialog.close()

    def test_style_dialog_accepts_fractional_document_dpi(self):
        self._inject(NewFigureSettings(10.0, 8.0, 150.5))
        dialog = PyStyleDialog("default", self.window.figure_window)
        try:
            self.assertEqual(dialog.dpi_line.text(), "150.5")
            dialog.canva_name_line.setText("FractionalDpi")
            dialog.accept()
        finally:
            dialog.close()
        canvas = self.window.figure_window.current_canva
        self.assertIsNotNone(canvas)
        self.assertEqual(_canvas_size(canvas), (10.0, 8.0, 150.5))
        self.assertEqual(_snapshot_size(canvas), (10.0, 8.0, 150.5))

    def test_text_import_uses_application_defaults(self):
        self._inject()
        path = Path(self.directory.name) / "points.txt"
        path.write_text("X Y\n1 2\n3 4\n", encoding="utf-8")
        import_text_into_workspace(
            str(path),
            self.window.table,
            figure_window=self.window.figure_window,
            show_preview=False,
        )
        canvas = self.window.figure_window.current_canva
        self.assertEqual(_canvas_size(canvas), (10.0, 8.0, 150.0))
        self.assertEqual(_snapshot_size(canvas), (10.0, 8.0, 150.0))

    def test_excel_import_uses_application_defaults(self):
        self._inject()
        path = Path(self.directory.name) / "points.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Raw"
        sheet.append(["X", "Y"])
        sheet.append([1, 2])
        workbook.save(path)
        workbook.close()
        import_excel_into_workspace(
            str(path),
            self.window.table,
            figure_window=self.window.figure_window,
            show_preview=False,
        )
        canvas = self.window.figure_window.current_canva
        self.assertEqual(_canvas_size(canvas), (10.0, 8.0, 150.0))
        self.assertEqual(_snapshot_size(canvas), (10.0, 8.0, 150.0))

    def test_restore_keeps_v15_size_when_application_defaults_change(self):
        self.window.figure_window.add_figure(
            width=PROJECT_SIZE[0],
            height=PROJECT_SIZE[1],
            dpi=PROJECT_SIZE[2],
            style="default",
            canva_name="PersistedSize",
        )
        path = Path(self.directory.name) / "persisted.mygui.json"
        save_project_snapshot(path, self.window.figure_window)

        loaded = MainWindow()
        provider = CountingNewFigureDefaults(CUSTOM_DEFAULTS)
        loaded.figure_window.set_new_figure_defaults_provider(provider)
        try:
            restore_project_snapshot(path, loaded.table, loaded.figure_window)
            canvas = loaded.figure_window.current_canva
            self.assertEqual(provider.calls, 0)
            self.assertEqual(_canvas_size(canvas), PROJECT_SIZE)
            self.assertEqual(_snapshot_size(canvas), PROJECT_SIZE)
            self.assertEqual(
                loaded.figure_window.creation_figure_size(),
                (10.0, 8.0, 150.0),
            )
        finally:
            loaded.close()
            self.app.processEvents()

    def test_settings_commit_is_absent_from_project_undo_fingerprint_and_state(self):
        self.window.close()
        service = ApplicationSettingsService(document=MemorySettingsDocumentPort())
        self.window = MainWindow(settings_service=service)
        canvas = self.window.figure_window.add_figure(
            width=PROJECT_SIZE[0],
            height=PROJECT_SIZE[1],
            dpi=PROJECT_SIZE[2],
            style="default",
            canva_name="SettingsIsolation",
        )
        stack = canvas.repository.undo_stack(canvas.project_id)
        selected = canvas.current_component_id
        before_snapshot = project_snapshot(self.window.figure_window, canvas=canvas)
        before_json = json.dumps(before_snapshot, sort_keys=True)
        before_fingerprint = project_fingerprint(before_snapshot)
        before_tree = canvas.component_snapshot()
        undo_index = stack.index()
        undo_count = stack.count()

        result = service.commit_patch(
            service.begin_session(),
            {
                APPEARANCE_THEME_MODE: ThemeMode.DARK,
                APPEARANCE_UI_FONT_POINT_SIZE: 16,
                NEW_FIGURE_WIDTH_IN: 10.0,
            },
        )
        self.assertTrue(result.success)
        self.assertEqual(service.snapshot().appearance.theme_mode, ThemeMode.DARK)
        self.assertEqual(service.snapshot().new_figure.width_in, 10.0)

        after_snapshot = project_snapshot(self.window.figure_window, canvas=canvas)
        after_json = json.dumps(after_snapshot, sort_keys=True)
        self.assertEqual(after_json, before_json)
        self.assertEqual(project_fingerprint(after_snapshot), before_fingerprint)
        self.assertEqual(canvas.component_snapshot(), before_tree)
        self.assertEqual(canvas.current_component_id, selected)
        self.assertEqual(stack.index(), undo_index)
        self.assertEqual(stack.count(), undo_count)
        self.assertEqual(after_snapshot["schema_version"], 15)
        self.assertNotIn("ui_font_point_size", after_json)
        self.assertNotIn("applicationSettings", after_json)
        self.assertNotIn("remember_layout", after_json)
        for component in after_snapshot["figure"]["components"]:
            self.assertNotIn("theme_mode", component.get("properties", {}))
            self.assertNotIn("ui_font_point_size", component.get("properties", {}))


if __name__ == "__main__":
    unittest.main()
