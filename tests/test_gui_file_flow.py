import os
import tempfile
import unittest
from pathlib import Path

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
)
from mygui.widgets.title_bar.py_title_menu import MenuBar
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


if __name__ == "__main__":
    unittest.main()
