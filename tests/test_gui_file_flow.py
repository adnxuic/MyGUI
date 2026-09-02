import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
)
from mygui.widgets.title_bar.py_title_menu import (
    ControlBar,
    MenuBar,
    load_excel_into_table,
    load_text_into_table,
)
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

    def test_file_menu_cancels_and_reports_missing_targets_without_writing(self):
        from mygui import status_messages

        empty = MainWindow()
        try:
            menu = empty.title_bar.menu_bar
            with patch.object(QMessageBox, "warning") as warning:
                with patch.object(status_messages, "show_error"):
                    self.assertFalse(menu.save_file())
                    self.assertFalse(menu.save_file_as())
            self.assertGreaterEqual(warning.call_count, 2)
            self.assertFalse(menu.save_canvas(None))
            self.assertTrue(
                menu._project_save_path("plain").endswith(".mygui.json")
            )
            with patch(
                "mygui.widgets.title_bar.py_title_menu.QFileDialog.getSaveFileName",
                return_value=("", ""),
            ):
                self.assertFalse(menu.export_data())
                self.assertFalse(
                    self.menu.save_canvas(
                        self.window.figure_window.current_canva,
                        save_as=True,
                    )
                )
            with patch(
                "mygui.widgets.title_bar.py_title_menu.QFileDialog.getOpenFileName",
                return_value=("missing-file.xlsx", ""),
            ):
                menu.open_file()
                menu.open_project()
                menu.open_text_file()
            from types import SimpleNamespace

            with patch.object(self.menu, "figure_window", None):
                with patch.object(QMessageBox, "warning") as library_warning:
                    self.menu.export_canvas(
                        SimpleNamespace(color_library=None)
                    )
            library_warning.assert_called_once()
            self.assertIn(
                "color library",
                library_warning.call_args[0][2].casefold(),
            )
        finally:
            empty.close()
            self.app.processEvents()

    def test_selector_menu_toggles_and_file_helpers(self):
        from mygui.application_theme import current_density_metrics

        host = QMainWindow()
        bar = ControlBar(host)
        bar.close()
        host.close()
        selector = self.window.title_bar.selector_menu_bar
        selector.apply_theme_metrics(current_density_metrics())
        with patch("mygui.widgets.title_bar.py_title_menu.QMessageBox.warning"):
            selector.the_button_was_toggled(False)
            selector.chart_button.setChecked(True)
            selector.element_button.setChecked(True)
            selector.layout_button.setChecked(True)
            selector.style_button.setChecked(True)
        with patch(
            "mygui.widgets.title_bar.py_title_menu.import_excel_into_workspace",
            return_value=True,
        ) as excel:
            self.assertTrue(load_excel_into_table("book.xlsx", self.window.table))
        excel.assert_called_once()
        with patch(
            "mygui.widgets.title_bar.py_title_menu.import_text_into_workspace",
            return_value=True,
        ) as text:
            self.assertTrue(load_text_into_table("data.csv", self.window.table))
        text.assert_called_once()
        menu = self.window.title_bar.menu_bar
        menu._sync_edit_actions()
        with patch.object(menu.template_workflow, "open_extract") as extract:
            menu._change_to_template()
        extract.assert_called_once()
        with patch(
            "mygui.widgets.title_bar.py_title_menu.export_database_snapshot"
        ) as export_data, patch(
            "mygui.widgets.title_bar.py_title_menu.QFileDialog.getSaveFileName",
            return_value=("out.json", ""),
        ):
            self.assertIsNone(menu.export_data())
        export_data.assert_called_once()
        with patch.object(menu, "export_canvas", return_value=True) as export_canvas:
            menu.export_current_figure()
        export_canvas.assert_called_once()
        with patch(
            "mygui.widgets.title_bar.py_title_menu.QFileDialog.getOpenFileName",
            return_value=("book.xlsx", ""),
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.os.path.exists",
            return_value=True,
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.load_excel_into_table",
            return_value=True,
        ) as load_excel:
            menu.open_file()
        load_excel.assert_called_once()
        with patch(
            "mygui.widgets.title_bar.py_title_menu.QFileDialog.getOpenFileName",
            return_value=("notes.txt", ""),
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.os.path.isfile",
            return_value=True,
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.load_text_into_table",
            return_value=True,
        ) as load_text:
            menu.open_text_file()
        load_text.assert_called_once()
        with patch(
            "mygui.widgets.title_bar.py_title_menu.QFileDialog.getOpenFileName",
            return_value=("project.mygui.json", ""),
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.os.path.exists",
            return_value=True,
        ), patch(
            "mygui.widgets.title_bar.py_title_menu.restore_project_snapshot",
            return_value=True,
        ) as restore:
            menu.open_project()
        restore.assert_called_once()
        with patch.object(menu, "save_canvas", return_value=True) as save:
            self.assertTrue(menu.save_file())
            self.assertTrue(menu.save_file_as())
        self.assertEqual(save.call_count, 2)
        with patch.object(menu.file_menu, "exec"):
            menu.show_menu(menu.file_menu, menu.file_button)


if __name__ == "__main__":
    unittest.main()
