import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import openpyxl

from Qt_core import QApplication, QMimeData, QUrl

from code.database import ColumnType
from code.excel_io import (
    ExcelColumnSpec,
    ExcelSheetPreview,
    ExcelSheetSpec,
    import_excel_into_table,
    read_excel_workbook,
)
from main import MainWindow


class DropEventStub:
    def __init__(self, paths):
        self._mime_data = QMimeData()
        self._mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime_data

    def acceptProposedAction(self):
        self.accepted = True
        self.ignored = False

    def ignore(self):
        self.ignored = True
        self.accepted = False


class ExcelImportV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "WorkbookProject.xlsx"
        workbook = openpyxl.Workbook()
        raw = workbook.active
        raw.title = "Raw"
        raw.append(["X", "Enabled", "When"])
        raw.append([1, True, "2026-07-10"])
        raw.append([None, False, "2026-07-11"])
        formula = workbook.create_sheet("Formula")
        formula.append(["Value"])
        formula.append(["=1+1"])
        workbook.save(self.path)
        workbook.close()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def test_import_uses_headers_locks_types_and_is_one_undo_step(self):
        subtable = import_excel_into_table(str(self.path), self.window.table, show_preview=False)
        project = subtable.project
        imported = list(project.sheets.values())[0]

        self.assertEqual([column.name for column in imported.columns], ["X", "Enabled", "When"])
        self.assertEqual(
            [column.type for column in imported.columns],
            [ColumnType.NUMBER, ColumnType.BOOLEAN, ColumnType.DATETIME],
        )
        self.assertTrue(imported.frame[imported.columns[0].id].isna().iloc[1])

        self.window.repository.undo_stack(project.id).undo()
        self.assertEqual([sheet.name for sheet in project.sheets.values()], ["Sheet1"])
        self.window.repository.undo_stack(project.id).redo()
        self.assertIn("Raw", [sheet.name for sheet in project.sheets.values()])

    def test_import_never_evaluates_formulas(self):
        workbook = read_excel_workbook(str(self.path))
        formula = next(sheet for sheet in workbook if sheet.name == "Formula")
        self.assertIsNone(formula.rows[1][0])

    def test_sheet_name_collision_creates_unique_sheet(self):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="Project"
        )
        project = self.window.repository.project_by_name("Project")
        project.add_sheet("Raw")

        import_excel_into_table(str(self.path), self.window.table, show_preview=False)

        names = [sheet.name for sheet in project.sheets.values()]
        self.assertIn("Raw 2", names)

    def test_preview_allows_header_and_type_override(self):
        sheet = read_excel_workbook(str(self.path))[0]
        preview = ExcelSheetPreview(sheet)
        try:
            self.assertEqual(preview.column_name_editor(0).text(), "X")
            type_combo = preview.column_type_editor(0)
            type_combo.setCurrentText("text")
            spec = preview.spec()
            self.assertEqual(spec.columns[0].type, ColumnType.TEXT)
            preview.header.setChecked(False)
            self.assertEqual(preview.column_name_editor(0).text(), "X")
        finally:
            preview.deleteLater()

    def test_preview_displays_fields_as_columns_with_row_aligned_samples(self):
        sheet = read_excel_workbook(str(self.path))[0]
        preview = ExcelSheetPreview(sheet)
        try:
            self.assertEqual(preview.columns.columnCount(), 3)
            self.assertEqual(preview.columns.horizontalHeaderItem(0).text(), "X")
            self.assertEqual(preview.columns.horizontalHeaderItem(1).text(), "Enabled")
            self.assertEqual(preview.columns.horizontalHeaderItem(2).text(), "When")
            self.assertEqual(preview.columns.verticalHeaderItem(0).text(), "Import")
            self.assertEqual(preview.columns.verticalHeaderItem(1).text(), "Column Name")
            self.assertEqual(preview.columns.verticalHeaderItem(2).text(), "Type")
            self.assertEqual(preview.columns.item(3, 0).text(), "1")
            self.assertEqual(preview.columns.item(3, 1).text(), "True")
            self.assertEqual(preview.columns.item(4, 0).text(), "")
            self.assertEqual(preview.columns.item(4, 1).text(), "False")
        finally:
            preview.deleteLater()

    def test_preview_can_exclude_columns_and_preserves_selection_on_rebuild(self):
        sheet = read_excel_workbook(str(self.path))[0]
        preview = ExcelSheetPreview(sheet)
        try:
            preview.column_include_checkbox(1).setChecked(False)
            self.assertFalse(preview.column_name_editor(1).isEnabled())
            self.assertFalse(preview.column_type_editor(1).isEnabled())

            spec = preview.spec()
            self.assertEqual([column.name for column in spec.columns], ["X", "When"])

            preview.header.setChecked(False)
            self.assertFalse(preview.column_include_checkbox(1).isChecked())
            self.assertEqual(
                [column.name for column in preview.spec().columns],
                ["X", "When"],
            )
        finally:
            preview.deleteLater()

    def test_preview_rejects_included_sheet_without_selected_columns(self):
        sheet = read_excel_workbook(str(self.path))[0]
        preview = ExcelSheetPreview(sheet)
        try:
            for column in range(preview.columns.columnCount()):
                preview.column_include_checkbox(column).setChecked(False)
            with self.assertRaisesRegex(ValueError, "at least one column"):
                preview.spec()
        finally:
            preview.deleteLater()

    def test_failed_type_preflight_does_not_create_project(self):
        invalid = [ExcelSheetSpec("Raw", "Raw", [
            ExcelColumnSpec("X", ColumnType.NUMBER, ["not-a-number"])
        ])]
        with patch("code.excel_io._default_specs", return_value=invalid):
            with self.assertRaisesRegex(ValueError, "valid number"):
                import_excel_into_table(str(self.path), self.window.table, show_preview=False)
        self.assertEqual(self.window.table.table_names(), [])

    def test_excel_drag_is_accepted_and_routes_to_import(self):
        enter_event = DropEventStub([self.path])
        self.window.dragEnterEvent(enter_event)
        self.assertTrue(enter_event.accepted)

        drop_event = DropEventStub([self.path])
        with patch.object(self.window, "import_excel_file") as importer:
            self.window.dropEvent(drop_event)
        self.assertTrue(drop_event.accepted)
        importer.assert_called_once_with(str(self.path))

    def test_drag_import_creates_project_canvas_and_success_message(self):
        subtable = self.window.import_excel_file(str(self.path), show_preview=False)

        self.assertIsNotNone(subtable)
        self.assertEqual(self.window.figure_window.tabwindow.count(), 1)
        self.assertEqual(
            self.window.figure_window.current_canva.project_id,
            subtable.project.id,
        )
        self.assertIn("Excel imported", self.window.bottom_bar.message_bar.message_label.text())

    def test_multiple_file_drops_are_rejected(self):
        multiple_event = DropEventStub([self.path, self.path])
        self.window.dragEnterEvent(multiple_event)
        self.assertTrue(multiple_event.ignored)


if __name__ == "__main__":
    unittest.main()
