import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from mygui import status_messages
from mygui.database import ColumnType, TableRepository
from mygui.widgets.table.py_subtable import (
    PySubTable,
    TypedItemDelegate,
    _same_value,
)



class TableUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _menu_type(selected_text: str | None):
        class Action:
            def __init__(self, text):
                self._text = text

            def text(self):
                return self._text

        class Menu:
            def __init__(self, *_args, **_kwargs):
                self._actions = []

            def addAction(self, text):
                action = Action(text)
                self._actions.append(action)
                return action

            def addSeparator(self):
                pass

            def isEmpty(self):
                return not self._actions

            def actions(self):
                return list(self._actions)

            def exec(self, _position=None):
                return next(
                    (
                        action
                        for action in self._actions
                        if action.text() == selected_text
                    ),
                    None,
                )

        return Menu

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

    def test_same_value_helper(self):
        self.assertTrue(_same_value(pd.NA, None))
        self.assertTrue(_same_value(np.nan, pd.NA))
        self.assertTrue(_same_value(42, 42))
        self.assertFalse(_same_value(42, 43))

        class BadCompare:
            def __eq__(self, _other):
                raise TypeError("injected compare failure")

        self.assertFalse(_same_value(BadCompare(), 1))

    def test_header_roles_alignment_and_missing_background(self):
        self.model.setData(self.model.index(0, 0), "1.5", Qt.EditRole)
        numeric = self.model.index(0, 0)
        missing = self.model.index(1, 0)

        self.assertEqual(self.model.headerData(0, Qt.Horizontal), "Column 1\nnumber")
        self.assertEqual(self.model.data(numeric, Qt.TextAlignmentRole), Qt.AlignRight | Qt.AlignVCenter)
        self.assertIsNotNone(self.model.data(missing, Qt.BackgroundRole))
        self.assertEqual(self.model.data(numeric, Qt.EditRole), "1.5")
        self.assertIsNone(self.model.headerData(999, Qt.Horizontal))
        self.assertIsNone(self.model.headerData(999, Qt.Vertical))
        self.assertIsNone(self.model.headerData(0, Qt.Horizontal, Qt.UserRole))
        self.assertEqual(self.model.headerData(0, Qt.Vertical), "1")
        self.assertIn("Column 1 (number)", self.model.headerData(0, Qt.Horizontal, Qt.ToolTipRole))

    def test_model_flags_and_out_of_bounds_data(self):
        self.assertEqual(self.model.flags(QModelIndex()), Qt.NoItemFlags)
        self.assertEqual(
            self.model.flags(self.model.index(0, 0)),
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable,
        )

        sheet = self.model.sheet
        sheet.columns[0].type = ColumnType.BOOLEAN
        self.assertTrue(bool(self.model.flags(self.model.index(0, 0)) & Qt.ItemIsUserCheckable))

        self.assertIsNone(self.model.data(QModelIndex()))
        self.assertIsNone(self.model.data(self.model.index(999, 999)))
        self.assertIsNone(self.model.data(self.model.index(0, 0), Qt.UserRole))

    def test_model_data_boolean_roles_and_tooltips(self):
        sheet = self.model.sheet
        sheet.columns[0].type = ColumnType.BOOLEAN
        sheet.ensure_rows(3)
        sheet.set_cell(0, sheet.columns[0].id, True)
        sheet.set_cell(1, sheet.columns[0].id, False)
        sheet.set_cell(2, sheet.columns[0].id, None)

        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.CheckStateRole), Qt.Checked)
        self.assertEqual(self.model.data(self.model.index(1, 0), Qt.CheckStateRole), Qt.Unchecked)
        self.assertEqual(self.model.data(self.model.index(2, 0), Qt.CheckStateRole), Qt.PartiallyChecked)

        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.TextAlignmentRole), Qt.AlignCenter)
        self.assertEqual(self.model.data(self.model.index(2, 0), Qt.ToolTipRole), "Missing value")

        sheet.columns[0].type = ColumnType.TEXT
        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.TextAlignmentRole), Qt.AlignLeft | Qt.AlignVCenter)

    def test_model_set_data_branches_and_noop(self):
        sheet = self.model.sheet
        sheet.columns[0].type = ColumnType.BOOLEAN
        accepted = self.model.setData(self.model.index(0, 0), Qt.Checked, Qt.CheckStateRole)
        self.assertTrue(accepted)
        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.CheckStateRole), Qt.Checked)

        # No-op set data
        no_op = self.model.setData(self.model.index(0, 0), "true", Qt.EditRole)
        self.assertFalse(no_op)

        # Invalid index or unsupported role
        self.assertFalse(self.model.setData(QModelIndex(), "true", Qt.EditRole))
        self.assertFalse(self.model.setData(self.model.index(0, 0), "true", Qt.ToolTipRole))

    def test_model_set_data_auto_column_undo_redo(self):
        sheet = self.model.sheet
        sheet.columns[0].type = ColumnType.AUTO
        sheet.frame[sheet.columns[0].id] = sheet.frame[sheet.columns[0].id].astype("object")

        self.model.setData(self.model.index(0, 0), "123", Qt.EditRole)
        self.assertEqual(sheet.columns[0].type, ColumnType.NUMBER)

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        self.assertEqual(sheet.columns[0].type, ColumnType.AUTO)
        stack.redo()
        self.assertEqual(sheet.columns[0].type, ColumnType.NUMBER)

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

        # Out of bounds sort column is safe no-op
        self.model.sort_by_column(999, True)

    def test_model_clear_indexes(self):
        self.assertFalse(self.model.clear_indexes([]))

        self.view.add_column()
        sheet = self.model.sheet
        sheet.columns[1].type = ColumnType.DATETIME
        sheet.frame[sheet.columns[1].id] = pd.to_datetime(["2025-01-01 00:00:00"] * sheet.row_count)
        self.model.setData(self.model.index(0, 0), "10.0", Qt.EditRole)

        cleared = self.model.clear_indexes([self.model.index(0, 0), self.model.index(0, 1)])
        self.assertTrue(cleared)
        self.assertTrue(pd.isna(sheet.frame.at[0, sheet.columns[0].id]))
        self.assertTrue(pd.isna(sheet.frame.at[0, sheet.columns[1].id]))

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        self.assertEqual(float(sheet.frame.at[0, sheet.columns[0].id]), 10.0)

    def test_model_paste_block_expansion_and_rollback(self):
        self.assertFalse(self.model.paste_block(0, 0, []))
        self.assertFalse(self.model.paste_block(0, 0, [[]]))

        initial_cols = self.model.columnCount()
        pasted = self.model.paste_block(0, 0, [
            ["1.0", "alpha", "2025-01-01", "4.0", "5.0", "extra_col"],
            ["2.0", "beta", "2025-01-02", "8.0", "10.0", "extra_val"],
        ])
        self.assertTrue(pasted)
        self.assertGreater(self.model.columnCount(), initial_cols)
        self.assertGreaterEqual(self.model.rowCount(), 2)

        stack = self.repository.undo_stack(self.project.id)
        stack.undo()
        self.assertEqual(self.model.columnCount(), initial_cols)

        # Invalid value paste fails and reports error
        sheet = self.model.sheet
        sheet.columns[0].type = ColumnType.NUMBER
        bad_paste = self.model.paste_block(0, 0, [["not-a-number"]])
        self.assertFalse(bad_paste)


    def test_typed_item_delegate_lifecycle(self):
        delegate = TypedItemDelegate(self.view)
        sheet = self.model.sheet

        # Boolean column editor
        sheet.columns[0].type = ColumnType.BOOLEAN
        combo = delegate.createEditor(self.view, None, self.model.index(0, 0))
        self.assertIsInstance(combo, QComboBox)
        delegate.setEditorData(combo, self.model.index(0, 0))
        combo.setCurrentText("true")
        delegate.setModelData(combo, self.model, self.model.index(0, 0))
        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.CheckStateRole), Qt.Checked)

        # DateTime column editor
        sheet.columns[0].type = ColumnType.DATETIME
        dt_edit = delegate.createEditor(self.view, None, self.model.index(0, 0))
        self.assertIsInstance(dt_edit, QDateTimeEdit)
        self.model.setData(self.model.index(0, 0), "2025-05-10T14:30:00", Qt.EditRole)
        delegate.setEditorData(dt_edit, self.model.index(0, 0))
        delegate.setModelData(dt_edit, self.model, self.model.index(0, 0))

        # Number column editor
        sheet.columns[0].type = ColumnType.NUMBER
        num_edit = delegate.createEditor(self.view, None, self.model.index(0, 0))
        self.assertIsInstance(num_edit, QLineEdit)
        self.assertIsNotNone(num_edit.validator())
        num_edit.setText("99.5")
        delegate.setModelData(num_edit, self.model, self.model.index(0, 0))
        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.EditRole), "99.5")

        # Text column editor
        sheet.columns[0].type = ColumnType.TEXT
        txt_edit = delegate.createEditor(self.view, None, self.model.index(0, 0))
        self.assertIsInstance(txt_edit, QLineEdit)
        self.assertIsNone(txt_edit.validator())
        txt_edit.setText("Hello Text")
        delegate.setModelData(txt_edit, self.model, self.model.index(0, 0))
        self.assertEqual(self.model.data(self.model.index(0, 0), Qt.EditRole), "Hello Text")

    def test_table_view_copy_and_paste_items(self):
        self.view.paste_items()  # no selection / start
        self.model.setData(self.model.index(0, 0), "123", Qt.EditRole)

        # Copy selection
        self.view.setCurrentIndex(self.model.index(0, 0))
        self.view.copy_items()
        clipboard_text = QGuiApplication.clipboard().text()
        self.assertIn("123", clipboard_text)

        # Paste items
        QGuiApplication.clipboard().setText("456\t789\n100\t200")
        self.view.paste_items()
        self.assertTrue(any("Pasted" in msg for msg, _ in self.messages))

        # Clear items
        self.view.delete_items()

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

    def test_table_view_row_and_column_move_operations(self):
        self.model.paste_block(0, 0, [["1"], ["2"], ["3"]])
        self.view.setCurrentIndex(self.model.index(0, 0))

        # Move row down
        self.view.move_row(1)
        self.assertEqual(self.model.data(self.model.index(1, 0)), "1")
        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual(self.model.data(self.model.index(0, 0)), "1")

        # Move row clamped no-op
        self.view.setCurrentIndex(self.model.index(0, 0))
        self.view.move_row(-1)
        self.assertEqual(self.model.data(self.model.index(0, 0)), "1")

        # Delete row
        current_rows = self.model.rowCount()
        self.view.delete_row()
        self.assertEqual(self.model.rowCount(), current_rows - 1)
        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual(self.model.rowCount(), current_rows)

        # Column move operations
        initial_cols = self.model.columnCount()
        self.view.add_column()
        self.view.setCurrentIndex(self.model.index(0, 0))
        self.view.move_column(1)
        self.repository.undo_stack(self.project.id).undo()

        # Delete column when multiple columns exist
        self.view.setCurrentIndex(self.model.index(0, 1))
        self.view.delete_column()
        self.assertEqual(self.model.columnCount(), initial_cols)
        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual(self.model.columnCount(), initial_cols + 1)

        # Delete column single column warning
        while self.model.columnCount() > 1:
            self.view.setCurrentIndex(self.model.index(0, 0))
            self.view.delete_column()
        self.view.setCurrentIndex(self.model.index(0, 0))
        self.view.delete_column()
        self.assertTrue(any("at least one column" in msg for msg, _ in self.messages))

    def test_table_view_column_rename_and_type_change(self):
        self.view.setCurrentIndex(self.model.index(0, 0))

        # Rename column dialog cancel
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            self.view.rename_column()

        # Rename column error
        with patch.object(QInputDialog, "getText", return_value=("", True)):
            self.view.rename_column()
        self.assertTrue(any("empty" in msg.lower() for msg, _ in self.messages))

        # Rename column success & undo
        with patch.object(QInputDialog, "getText", return_value=("RenamedCol", True)):
            self.view.rename_column()
        self.assertEqual(self.model.sheet.columns[0].name, "RenamedCol")
        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual(self.model.sheet.columns[0].name, "Column 1")

        # Change column type dialog cancel
        with patch.object(QInputDialog, "getItem", return_value=("text", False)):
            self.view.change_column_type()

        # Change column type success & undo
        with patch.object(QInputDialog, "getItem", return_value=("text", True)):
            self.view.change_column_type()
        self.assertEqual(self.model.sheet.columns[0].type, ColumnType.TEXT)
        self.repository.undo_stack(self.project.id).undo()
        self.assertEqual(self.model.sheet.columns[0].type, ColumnType.AUTO)

    def test_table_view_context_menu_actions_and_subtable_context_menu(self):
        # Header context menu actions
        self.view.add_column()
        self.model.paste_block(0, 0, [["2", "b"], ["1", "a"]])

        with patch.object(self.view.horizontalHeader(), "logicalIndexAt", return_value=0), \
             patch.object(self.view.verticalHeader(), "logicalIndexAt", return_value=0):

            # Header menu: test rename action
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Rename Column")), \
                 patch.object(QInputDialog, "getText", return_value=("ColRenamed", True)):
                self.view.header_context_menu(QPoint(10, 10))
            self.assertEqual(self.model.sheet.columns[0].name, "ColRenamed")

            # Header menu: test change type action
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Change Type")), \
                 patch.object(QInputDialog, "getItem", return_value=("text", True)):
                self.view.header_context_menu(QPoint(10, 10))
            self.assertEqual(self.model.sheet.columns[0].type, ColumnType.TEXT)

            # Header menu: test Add Column Right
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Add Column Right")):
                self.view.header_context_menu(QPoint(10, 10))

            # Header menu: test Move Left & Move Right
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Move Right")):
                self.view.header_context_menu(QPoint(10, 10))
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Move Left")):
                self.view.header_context_menu(QPoint(10, 10))

            # Header menu: test Sort Rows Ascending & Descending
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Sort Rows Ascending")):
                self.view.header_context_menu(QPoint(10, 10))
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Sort Rows Descending")):
                self.view.header_context_menu(QPoint(10, 10))

            # Header menu: test Delete Column
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Delete Column")):
                self.view.header_context_menu(QPoint(10, 10))

            # Row menu actions: Insert Row, Delete Row, Move Up, Move Down
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Move Down")):
                self.view.row_context_menu(QPoint(10, 10))
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Move Up")):
                self.view.row_context_menu(QPoint(10, 10))
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Insert Row Above")):
                self.view.row_context_menu(QPoint(10, 10))
            with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Delete Row")):
                self.view.row_context_menu(QPoint(10, 10))

        # Sheet TabBar context menu actions
        self.subtable.add_new_sheet("Tab2")
        with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Rename Sheet")), \
             patch.object(QInputDialog, "getText", return_value=("Tab2Renamed", True)):
            with patch.object(self.subtable.tabWidget.tabBar(), "tabAt", return_value=1):
                self.subtable.tabWidget._context_menu(QPoint(50, 10))
        self.assertEqual(self.subtable.tabWidget.tabText(1), "Tab2Renamed")

        with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type("Delete Sheet")):
            with patch.object(self.subtable.tabWidget.tabBar(), "tabAt", return_value=1):
                self.subtable.tabWidget._context_menu(QPoint(50, 10))
        self.assertEqual(self.subtable.tabWidget.count(), 2)  # Sheet1 + plus

    def test_dependency_handler_aborts_and_error_cells(self):
        # Error cell styling and clear error
        self.model._mark_error(self.model.index(0, 0), "Custom error")
        self.assertIsNotNone(self.model.data(self.model.index(0, 0), Qt.BackgroundRole))
        self.assertTrue((0, 0) in self.model._error_cells)

        # Dependency handler abort on column delete
        self.view.add_column()
        self.subtable.dependency_handler = lambda refs, reason: False
        self.view.dependency_handler = self.subtable.dependency_handler
        self.view.setCurrentIndex(self.model.index(0, 1))
        self.view.delete_column()
        self.assertEqual(self.model.columnCount(), 6)

        # Dependency handler abort on column type change
        with patch.object(QInputDialog, "getItem", return_value=("text", True)):
            self.view.change_column_type()

        # Dependency handler returning functions
        undo_called = []
        redo_called = []
        def handler_funcs(refs, reason):
            return (lambda: redo_called.append(True), lambda: undo_called.append(True))
        self.view.dependency_handler = handler_funcs
        with patch.object(QInputDialog, "getItem", return_value=("text", True)):
            self.view.change_column_type()
        self.assertTrue(redo_called)

        # Dependency redo failing
        def handler_failing_redo(refs, reason):
            return (lambda: False, lambda: None)
        self.view.dependency_handler = handler_failing_redo
        self.view.delete_column()

        # Dependency undo failing
        def handler_failing_undo(refs, reason):
            return (lambda: True, lambda: False)
        self.view.dependency_handler = handler_failing_undo
        self.view.delete_column()
        self.repository.undo_stack(self.project.id).undo()


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

    def test_sheet_rename_validation_errors_and_cancel(self):
        self.subtable.add_new_sheet("Second")

        # Dialog cancel
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            self.subtable.rename_sheet(1)

        # Empty name error
        with patch.object(QInputDialog, "getText", return_value=("", True)):
            self.subtable.rename_sheet(1)
        self.assertTrue(any("empty" in msg.lower() for msg, _ in self.messages))

        # Duplicate name error
        with patch.object(QInputDialog, "getText", return_value=("Sheet1", True)):
            self.subtable.rename_sheet(1)
        self.assertTrue(any("already exists" in msg for msg, _ in self.messages))

        # Same name no-op
        with patch.object(QInputDialog, "getText", return_value=("Second", True)):
            self.subtable.rename_sheet(1)

    def test_subtable_sheet_tab_and_toolbar_operations(self):
        self.assertEqual(self.subtable.current_view(), self.view)
        self.assertEqual(self.subtable.get_table(0), self.view)
        with self.assertRaises(IndexError):
            self.subtable.get_table(999)

        # Toolbar button triggers
        self.subtable.undo()
        self.subtable.redo()
        with patch.object(QInputDialog, "getText", return_value=("RenamedCurrent", True)):
            self.subtable.rename_current_sheet()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.subtable.delete_current_sheet()

        # Context menu on sheet tab bar
        with patch("mygui.widgets.table.py_subtable.QMenu", self._menu_type(None)):
            self.subtable.tabWidget._context_menu(QPoint(10, 10))

        # Sync sheets
        self.subtable.sync_sheets_from_repository()
        self.assertEqual(self.subtable.tabWidget.count(), 2)  # Sheet1 + plus tab

        # Single sheet deletion warning
        self.subtable.delete_sheet(0)
        self.assertTrue(any("at least one sheet" in msg for msg, _ in self.messages))

    def test_sheet_view_construction_failure_rolls_back_without_event(self):
        before = self.project.to_snapshot()
        before_views = dict(self.subtable._views)
        before_tabs = self.subtable.tabWidget.count()
        before_index = self.subtable.tabWidget.currentIndex()
        observed = []
        self.repository.transaction_committed.connect(observed.append)

        with patch(
            "mygui.widgets.table.py_subtable.TableView",
            side_effect=RuntimeError("injected TableView failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "TableView"):
                self.subtable.add_new_sheet("Broken")

        self.assertEqual(self.project.to_snapshot(), before)
        self.assertEqual(self.subtable._views, before_views)
        self.assertEqual(self.subtable.tabWidget.count(), before_tabs)
        self.assertEqual(self.subtable.tabWidget.currentIndex(), before_index)
        self.assertEqual(observed, [])

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

