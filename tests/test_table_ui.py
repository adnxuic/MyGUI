import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from mygui import status_messages
from mygui.database import ColumnType, TableRepository
from mygui.widgets.table.py_subtable import PySubTable


class TableUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.repository = TableRepository()
        self.project = self.repository.create_project("Project")
        self.subtable = PySubTable(self.repository, self.project.id)
        self.view = self.subtable.get_table(0)
        self.model = self.view.table_model
        self.messages = []
        status_messages.set_status_handler(lambda message, level: self.messages.append((message, level)))

    def tearDown(self):
        status_messages.clear_status_handler()
        self.subtable.deleteLater()
        self.app.processEvents()

    def test_header_roles_alignment_and_missing_background(self):
        self.model.setData(self.model.index(0, 0), "1.5", Qt.EditRole)
        numeric = self.model.index(0, 0)
        missing = self.model.index(1, 0)

        self.assertEqual(self.model.headerData(0, Qt.Horizontal), "Column 1\nnumber")
        self.assertEqual(self.model.data(numeric, Qt.TextAlignmentRole), Qt.AlignRight | Qt.AlignVCenter)
        self.assertIsNotNone(self.model.data(missing, Qt.BackgroundRole))
        self.assertEqual(self.model.data(numeric, Qt.EditRole), "1.5")

    def test_invalid_locked_value_is_rejected_and_reported(self):
        self.model.setData(self.model.index(0, 0), "1", Qt.EditRole)
        accepted = self.model.setData(self.model.index(0, 0), "invalid", Qt.EditRole)

        self.assertFalse(accepted)
        self.assertEqual(self.model.data(self.model.index(0, 0)), "1")
        self.assertTrue(any(level == "error" and "valid number" in message for message, level in self.messages))

    def test_row_sort_is_stable_and_undoable(self):
        self.model.paste_block(0, 0, [[2, "b"], [1, "a"], [2, "c"]])
        self.model.sort_by_column(0, True)
        self.assertEqual([self.model.data(self.model.index(row, 1)) for row in range(3)], ["a", "b", "c"])

        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual([self.model.data(self.model.index(row, 1)) for row in range(3)], ["b", "a", "c"])

    def test_row_and_column_commands_are_undoable(self):
        original_rows = self.model.rowCount()
        original_columns = self.model.columnCount()
        self.view.insert_row()
        self.view.add_column()
        self.assertEqual(self.model.rowCount(), original_rows + 1)
        self.assertEqual(self.model.columnCount(), original_columns + 1)

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        stack.undo()
        self.assertEqual(self.model.rowCount(), original_rows)
        self.assertEqual(self.model.columnCount(), original_columns)

    def test_undo_stack_is_limited_to_fifty_commands(self):
        for value in range(55):
            self.model.setData(self.model.index(0, 0), str(value), Qt.EditRole)
        self.assertEqual(self.repository.undo_stack(self.project.id).count(), 50)

    def test_fifty_thousand_by_twenty_single_edit_keeps_frame_identity(self):
        sheet = self.model.sheet
        sheet.truncate_rows(0)
        sheet.ensure_rows(50_000)
        while len(sheet.columns) < 20:
            sheet.add_column()
        values = list(range(50_000))
        for column in sheet.columns:
            column.type = ColumnType.NUMBER
            sheet.frame[column.id] = values
            sheet.frame[column.id] = sheet.frame[column.id].astype("Float64")
        frame_id = id(sheet.frame)
        observed = []
        self.repository.transaction_committed.connect(observed.append)

        self.model.setData(self.model.index(0, 0), "42", Qt.EditRole)

        self.assertEqual(id(sheet.frame), frame_id)
        self.assertEqual(len(observed[-1].changed_columns), 1)
        self.assertEqual(float(sheet.frame.iat[0, 0]), 42.0)

    def test_sheet_rename_is_available_and_undoable(self):
        second_view = self.subtable.add_new_sheet("Second")
        second_sheet_id = second_view.sheet_id

        with patch.object(QInputDialog, "getText", return_value=("Renamed", True)):
            self.subtable.rename_sheet(1)

        self.assertEqual(self.project.sheets[second_sheet_id].name, "Renamed")
        self.assertEqual(self.subtable.tabWidget.tabText(1), "Renamed")

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        self.assertEqual(self.project.sheets[second_sheet_id].name, "Second")
        self.assertEqual(self.subtable.tabWidget.tabText(1), "Second")
        stack.redo()
        self.assertEqual(self.subtable.tabWidget.tabText(1), "Renamed")

    def test_sheet_delete_and_dependency_cascade_are_undoable(self):
        second_view = self.subtable.add_new_sheet("Second")
        second_sheet_id = second_view.sheet_id
        events = []

        def dependency_handler(refs, reason):
            self.assertEqual(reason, "delete-sheet")
            self.assertTrue(refs)
            return (
                lambda: events.append("dependency-redo"),
                lambda: events.append("dependency-undo"),
            )

        self.subtable.dependency_handler = dependency_handler
        self.subtable.delete_sheet(1)
        self.assertNotIn(second_sheet_id, self.project.sheets)
        self.assertEqual(events, ["dependency-redo"])

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        self.assertEqual(list(self.project.sheets)[1], second_sheet_id)
        self.assertEqual(self.subtable.tabWidget.tabText(1), "Second")
        self.assertEqual(events[-1], "dependency-undo")

        stack.redo()
        self.assertNotIn(second_sheet_id, self.project.sheets)
        self.assertEqual(events[-1], "dependency-redo")

    def test_sheet_context_menu_is_attached_to_the_tab_bar(self):
        self.assertEqual(
            self.subtable.tabWidget.tabBar().contextMenuPolicy(),
            Qt.CustomContextMenu,
        )


if __name__ == "__main__":
    unittest.main()
