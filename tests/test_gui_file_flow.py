import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEST_TMP_DIR = Path(__file__).with_name("_tmp")
_TEST_TMP_DIR.mkdir(exist_ok=True)
os.environ["TEMP"] = str(_TEST_TMP_DIR)
os.environ["TMP"] = str(_TEST_TMP_DIR)
tempfile.tempdir = str(_TEST_TMP_DIR)

import numpy as np
import openpyxl

from Qt_core import QApplication
from code.database.py_database import PyDatabase
from code.widgets.title_bar import py_title_menu as title_menu_module
from main import MainWindow


@unittest.skip("legacy workspace-level file flow tests; v3 uses one canvas and one table")
class GuiFileFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PyDatabase.clear()
        temp_root = Path(__file__).with_name("_tmp")
        temp_root.mkdir(exist_ok=True)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mygui-file-flow-", dir=temp_root))
        tempfile.tempdir = str(self.temp_dir)
        os.environ["TMP"] = str(self.temp_dir)
        os.environ["TEMP"] = str(self.temp_dir)
        self.window = MainWindow()
        self.menu_bar = self.window.title_bar.stacklayout_top.widget(1)

    def tearDown(self):
        self.window.close()
        PyDatabase.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_workbook_file(self):
        filename = self.temp_dir / "input.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append([1, 10])
        sheet.append([2, 20])
        sheet.append([3, 30])
        workbook.save(filename)
        workbook.close()
        return filename

    def add_canvas(self, with_axes=True):
        self.window.figure_window.add_figure(width=4, height=3, dpi=80, style="default", canva_name="file-flow")
        canvas = self.window.figure_window.current_canva
        if with_axes:
            canvas.add_axes(nrows=1, ncols=1)
        return canvas

    def open_excel_from_menu(self, filename: Path):
        with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=(str(filename), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.open_file()
        warning.assert_not_called()

    def test_real_menu_file_flow_open_save_open_export_image_and_data(self):
        workbook = self.make_workbook_file()
        self.open_excel_from_menu(workbook)
        self.add_canvas(with_axes=True)

        np.testing.assert_allclose(PyDatabase.get_data("Table2/Sheet1/1"), np.array([1.0, 2.0, 3.0]))
        np.testing.assert_allclose(PyDatabase.get_data("Table2/Sheet1/2"), np.array([10.0, 20.0, 30.0]))

        project_file = self.temp_dir / "flow.mygui.json"
        project_file.write_text("stale project", encoding="utf-8")
        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(project_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.save_file()
        warning.assert_not_called()

        saved_project = json.loads(project_file.read_text(encoding="utf-8"))
        self.assertEqual(saved_project["schema"], "mygui-project")
        self.assertEqual(len(saved_project["figures"]), 1)

        self.window.table.clear_tables()
        self.window.figure_window.clear_figures()
        PyDatabase.clear()
        self.app.processEvents()
        self.assertFalse(PyDatabase.has_data("Table2/Sheet1/1"))

        with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=(str(project_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.open_project()
        warning.assert_not_called()
        self.app.processEvents()

        np.testing.assert_allclose(PyDatabase.get_data("Table2/Sheet1/1"), np.array([1.0, 2.0, 3.0]))
        self.assertEqual(self.window.figure_window.tabwindow.count(), 1)

        image_file = self.temp_dir / "figure.png"
        image_file.write_bytes(b"stale image")
        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(image_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_current_figure()
        warning.assert_not_called()
        self.assertTrue(image_file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

        data_file = self.temp_dir / "data.json"
        data_file.write_text("stale data", encoding="utf-8")
        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(data_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_data()
        warning.assert_not_called()

        exported_data = json.loads(data_file.read_text(encoding="utf-8"))
        self.assertEqual(exported_data["Table2"]["Sheet1"]["1"], [1.0, 2.0, 3.0])
        self.assertEqual(exported_data["Table2"]["Sheet1"]["2"], [10.0, 20.0, 30.0])

    def test_file_dialog_cancel_paths_do_not_run_actions_or_warn(self):
        self.add_canvas(with_axes=True)

        with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=("", "")), \
                patch.object(title_menu_module, "load_excel_into_table") as load_excel, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.open_file()
        load_excel.assert_not_called()
        warning.assert_not_called()

        with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=("", "")), \
                patch.object(title_menu_module, "restore_project_snapshot") as restore_project, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.open_project()
        restore_project.assert_not_called()
        warning.assert_not_called()

        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=("", "")), \
                patch.object(title_menu_module, "save_project_snapshot") as save_project, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.save_file()
        save_project.assert_not_called()
        warning.assert_not_called()

        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=("", "")), \
                patch.object(self.window.figure_window.current_canva, "save") as save_figure, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_current_figure()
        save_figure.assert_not_called()
        warning.assert_not_called()

        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=("", "")), \
                patch.object(title_menu_module, "export_database_snapshot") as export_data, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_data()
        export_data.assert_not_called()
        warning.assert_not_called()

    def test_empty_canvas_exports_and_missing_canvas_warns(self):
        empty_canvas = self.add_canvas(with_axes=False)
        image_file = self.temp_dir / "empty_canvas.png"

        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(image_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_current_figure()
        warning.assert_not_called()
        self.assertTrue(image_file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIs(empty_canvas, self.window.figure_window.current_canva)

        self.window.figure_window.clear_figures()
        with patch.object(title_menu_module.QFileDialog, "getSaveFileName") as get_save_file_name, \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.export_current_figure()
        get_save_file_name.assert_not_called()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class GuiSingleProjectFileFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PyDatabase.clear()
        temp_root = Path(__file__).with_name("_tmp")
        temp_root.mkdir(exist_ok=True)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mygui-v3-file-flow-", dir=temp_root))
        self.window = MainWindow()
        self.menu_bar = self.window.title_bar.stacklayout_top.widget(1)

    def tearDown(self):
        self.window.close()
        PyDatabase.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def add_project_with_unsaved_table_data(self, name="ProjectA"):
        self.window.figure_window.add_figure(width=4, height=3, dpi=80, style="default", canva_name=name)
        canvas = self.window.figure_window.current_canva
        canvas.add_axes(nrows=1, ncols=1)
        table_view = self.window.table.current_subtable().get_table(0)
        table_view.model.setData(table_view.model.index(0, 0), "1")
        table_view.model.setData(table_view.model.index(1, 0), "2")
        table_view.model.setData(table_view.model.index(0, 1), "10")
        table_view.model.setData(table_view.model.index(1, 1), "20")
        return canvas

    def test_save_current_project_writes_v3_and_syncs_table_model(self):
        self.add_project_with_unsaved_table_data()
        project_file = self.temp_dir / "project_a.mygui.json"

        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(project_file), "")), \
                patch.object(title_menu_module.QMessageBox, "warning") as warning:
            self.menu_bar.save_file_as()

        warning.assert_not_called()
        saved_project = json.loads(project_file.read_text(encoding="utf-8"))
        self.assertEqual(saved_project["schema_version"], 3)
        self.assertEqual(saved_project["name"], "ProjectA")
        self.assertEqual(saved_project["table"]["name"], "ProjectA")
        self.assertEqual(saved_project["table"]["sheets"]["Sheet1"]["1"], [1.0, 2.0])
        self.assertEqual(self.window.figure_window.current_canva.project_path, str(project_file))

    def test_open_project_appends_and_duplicate_name_rejected(self):
        self.add_project_with_unsaved_table_data("ProjectA")
        project_file = self.temp_dir / "project_a.mygui.json"
        with patch.object(title_menu_module.QFileDialog, "getSaveFileName", return_value=(str(project_file), "")):
            self.menu_bar.save_file_as()

        loaded_window = MainWindow()
        try:
            loaded_menu = loaded_window.title_bar.stacklayout_top.widget(1)
            loaded_window.figure_window.add_figure(width=4, height=3, dpi=80, style="default", canva_name="Existing")

            with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=(str(project_file), "")), \
                    patch.object(title_menu_module.QMessageBox, "warning") as warning:
                loaded_menu.open_project()
            warning.assert_not_called()

            self.assertEqual(loaded_window.table.table_names(), ["Existing", "ProjectA"])
            self.assertEqual(loaded_window.figure_window.tabwindow.count(), 2)

            with patch.object(title_menu_module.QFileDialog, "getOpenFileName", return_value=(str(project_file), "")), \
                    patch.object(title_menu_module.QMessageBox, "warning") as warning:
                loaded_menu.open_project()
            warning.assert_called_once()
            self.assertEqual(loaded_window.table.table_names(), ["Existing", "ProjectA"])
            self.assertEqual(loaded_window.figure_window.tabwindow.count(), 2)
        finally:
            loaded_window.close()
