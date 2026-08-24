import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
)
from mygui.widgets.title_bar.py_title_menu import MenuBar
from mygui.widgets.title_bar.titlebar_dialog.figure_export_dialog import (
    FigureExportDialog,
)
from main import MainWindow


class GuiFileFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ProjectA"
        )
        create_regular_axes(self.window.figure_window.current_canva)
        model = self.window.table.current_subtable().get_table(0).table_model
        model.setData(model.index(0, 0), "1", Qt.EditRole)
        self.menu = MenuBar(self.window.table, self.window.figure_window)

    def tearDown(self):
        self.menu.deleteLater()
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def test_save_menu_writes_current_schema_without_database_flush(self):
        target = Path(self.directory.name) / "saved"
        self.menu._save_project_to(str(target))
        saved = Path(str(target) + ".mygui.json")

        self.assertTrue(saved.exists())
        self.assertEqual(
            load_project_file(saved)["schema_version"],
            PROJECT_SCHEMA_VERSION,
        )
        self.assertEqual(self.window.figure_window.current_canva.project_path, str(saved))

    def test_restored_project_is_added_to_table_and_figure(self):
        target = Path(self.directory.name) / "saved.mygui.json"
        self.menu._save_project_to(str(target))
        loaded = MainWindow()
        try:
            restore_project_snapshot(target, loaded.table, loaded.figure_window)
            self.assertEqual(loaded.table.table_names(), ["ProjectA"])
            self.assertEqual(loaded.figure_window.tabwindow.count(), 1)
            self.assertEqual(loaded.table.current_project_id, loaded.figure_window.current_canva.project_id)
            self.assertFalse(
                loaded.figure_window.is_canvas_dirty(
                    loaded.figure_window.current_canva
                )
            )
        finally:
            loaded.close()
            self.app.processEvents()

    def test_menu_and_toolbar_open_the_same_export_window_for_an_explicit_canvas(self):
        first = self.window.figure_window.current_canva
        second = self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ProjectB",
        )
        self.app.processEvents()
        self.assertIs(self.window.figure_window.current_canva, second)
        opened = []

        class RecordingDialog:
            def __init__(self, **kwargs):
                opened.append(kwargs)
                self.context = kwargs["context"]

            def exec(self):
                return QDialog.DialogCode.Rejected

        menu = self.window.title_bar.menu_bar
        with patch(
            "mygui.widgets.title_bar.py_title_menu.FigureExportDialog",
            RecordingDialog,
        ):
            menu.export_current_figure()
            first.navigation_toolbar.save_figure()
        self.assertEqual(len(opened), 2)
        self.assertIs(opened[0]["export_callable"].__self__, second)
        self.assertEqual(opened[0]["context"].project_name, "ProjectB")
        self.assertIs(opened[1]["export_callable"].__self__, first)
        self.assertEqual(opened[1]["context"].project_name, "ProjectA")
        self.assertFalse((Path(self.directory.name) / "ghost.png").exists())

    def test_missing_project_cancel_and_declined_overwrite_do_not_write(self):
        target = Path(self.directory.name) / "skip.png"
        empty = MainWindow()
        try:
            with patch.object(QMessageBox, "warning") as warning:
                empty.title_bar.menu_bar.export_current_figure()
            warning.assert_called_once()
            self.assertFalse(target.exists())
        finally:
            empty.close()
            self.app.processEvents()

        opened = []

        class CancelDialog:
            def __init__(self, **kwargs):
                opened.append(kwargs)

            def exec(self):
                return QDialog.DialogCode.Rejected

        with patch(
            "mygui.widgets.title_bar.py_title_menu.FigureExportDialog",
            CancelDialog,
        ):
            self.window.title_bar.menu_bar.export_current_figure()
        self.assertEqual(len(opened), 1)
        self.assertFalse(target.exists())

        target.write_bytes(b"keep")
        canvas = self.window.figure_window.current_canva
        dialog = FigureExportDialog(
            context=canvas.export_context(),
            color_library=canvas.color_library,
            export_callable=canvas.export_figure,
        )
        try:
            dialog.path_edit.setText(str(target))
            with patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.No,
            ):
                dialog._export()
        finally:
            dialog.close()
            dialog.deleteLater()
        self.assertEqual(target.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
