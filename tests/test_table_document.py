import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

from mygui.database import (
    ColumnRef,
    ColumnType,
    ProjectTableDocument,
    SheetDocument,
    TableChangeSet,
    TableMutationCommand,
    TableRepository,
)
from PySide6.QtWidgets import QApplication


class TableDocumentTests(unittest.TestCase):
    def test_auto_columns_infer_and_lock_supported_types(self):
        sheet = SheetDocument.create("Data", column_count=0)
        numeric = sheet.add_column("Numeric", values=["1.5", "", 3])
        boolean = sheet.add_column("Boolean", values=[True, "false", "yes"])
        dates = sheet.add_column("Dates", values=["2026-07-10", None, "2026-07-12"])
        text = sheet.add_column("Text", values=["1", "word", "3"])

        self.assertEqual(numeric.type, ColumnType.NUMBER)
        self.assertEqual(boolean.type, ColumnType.BOOLEAN)
        self.assertEqual(dates.type, ColumnType.DATETIME)
        self.assertEqual(text.type, ColumnType.TEXT)
        self.assertEqual(str(sheet.frame[numeric.id].dtype), "Float64")
        self.assertTrue(pd.isna(sheet.frame.at[1, numeric.id]))

    def test_internal_missing_rows_survive_snapshot_roundtrip(self):
        project = ProjectTableDocument.create("Project")
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        sheet.set_block(0, 0, [[1], [""], [3]])

        restored = ProjectTableDocument.from_snapshot(project.to_snapshot())
        restored_sheet = next(iter(restored.sheets.values()))
        restored_values = restored_sheet.frame[column.id]

        self.assertEqual(len(restored_values), sheet.row_count)
        self.assertEqual(float(restored_values.iloc[0]), 1.0)
        self.assertTrue(pd.isna(restored_values.iloc[1]))
        self.assertEqual(float(restored_values.iloc[2]), 3.0)

    def test_invalid_locked_edit_is_atomic(self):
        sheet = SheetDocument.create("Data", column_count=0)
        column = sheet.add_column("Numeric", ColumnType.NUMBER, values=[1, 2, 3])
        before = sheet.frame[column.id].copy(deep=True)

        with self.assertRaisesRegex(ValueError, "valid number"):
            sheet.set_block(0, 0, [[4], ["not-a-number"]])

        pd.testing.assert_series_equal(sheet.frame[column.id], before)

    def test_number_columns_reject_nonfinite_values_atomically(self):
        sheet = SheetDocument.create("Data", column_count=0)
        column = sheet.add_column("Numeric", ColumnType.NUMBER, values=[1, 2, 3])
        before = sheet.frame[column.id].copy(deep=True)

        for value in (float("nan"), float("inf"), float("-inf"), "Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite"):
                    sheet.set_cell(0, column.id, value)
                pd.testing.assert_series_equal(sheet.frame[column.id], before)

    def test_row_and_column_moves_keep_values_aligned(self):
        sheet = SheetDocument.create("Data", column_count=0)
        x = sheet.add_column("X", values=[1, 2, 3])
        y = sheet.add_column("Y", values=[10, 20, 30])
        sheet.move_row(0, 2)
        sheet.move_column(1, 0)

        self.assertEqual(sheet.column_ids, [y.id, x.id])
        np.testing.assert_allclose(sheet.frame[x.id].iloc[:3].to_numpy(dtype=float), [2, 3, 1])
        np.testing.assert_allclose(sheet.frame[y.id].iloc[:3].to_numpy(dtype=float), [20, 30, 10])

    def test_rows_can_be_recreated_after_sheet_is_emptied(self):
        sheet = SheetDocument.create("Data")
        sheet.truncate_rows(0)
        sheet.insert_rows(0, 2)
        self.assertEqual(sheet.row_count, 2)
        self.assertEqual(len(sheet.frame), 2)
        self.assertTrue(sheet.frame.isna().all().all())

    def test_column_names_are_case_insensitively_unique(self):
        sheet = SheetDocument.create("Data", column_count=0)
        sheet.add_column("Temperature")
        with self.assertRaisesRegex(ValueError, "already exists"):
            sheet.validate_column_name("temperature")


class TableRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_refs_survive_column_rename_and_move(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        ref = ColumnRef(project.id, sheet.id, column.id)

        column.name = "Renamed"
        sheet.move_column(0, 2)

        self.assertTrue(repository.has_ref(ref))
        self.assertEqual(repository.ref_label(ref), "Project/Sheet1/Renamed")

    def test_pair_access_preserves_line_gaps_and_filters_calculations(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        sheet = next(iter(project.sheets.values()))
        x, y = sheet.columns[:2]
        sheet.set_block(0, 0, [[1, 10], ["", 20], [3, 30]])
        x_ref = ColumnRef(project.id, sheet.id, x.id)
        y_ref = ColumnRef(project.id, sheet.id, y.id)

        line = repository.line_pair(x_ref, y_ref)
        filtered = repository.valid_pair(x_ref, y_ref)

        self.assertEqual(line.missing_count, 1)
        self.assertTrue(np.isnan(line.x[1]))
        np.testing.assert_allclose(filtered.x, [1, 3])
        np.testing.assert_allclose(filtered.y, [10, 30])

    def test_command_emits_one_transaction_for_redo_and_undo(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        ref = ColumnRef(project.id, sheet.id, column.id)
        observed = []
        repository.transaction_committed.connect(observed.append)
        changes = TableChangeSet(project.id, {ref})

        command = TableMutationCommand(
            "Edit cell",
            repository,
            project.id,
            lambda: sheet.set_cell(0, column.id, "5"),
            lambda: sheet.set_cell(0, column.id, ""),
            changes,
        )
        repository.push(project.id, command)
        repository.undo_stack(project.id).undo()

        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0].changed_columns, {ref})
        self.assertEqual(observed[1].changed_columns, {ref})

    def test_failed_transaction_restores_document_identity_and_emits_nothing(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        before = project.to_snapshot()
        observed = []
        repository.transaction_committed.connect(observed.append)

        with self.assertRaisesRegex(RuntimeError, "injected"):
            with repository.transaction(project.id):
                sheet.name = "Mutated"
                sheet.remove_column(column.id)
                repository.record_change(
                    TableChangeSet(
                        project.id,
                        structure_changed=True,
                        reason="failed",
                    )
                )
                raise RuntimeError("injected failure")

        self.assertIs(repository.project(project.id), project)
        self.assertIs(repository.sheet(project.id, sheet.id), sheet)
        self.assertIs(sheet.column(column.id), column)
        self.assertEqual(project.to_snapshot(), before)
        self.assertEqual(observed, [])

    def test_caught_nested_failure_poisoned_outer_transaction(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        original_name = project.name

        with self.assertRaisesRegex(RuntimeError, "rolled back"):
            with repository.transaction(project.id):
                try:
                    with repository.transaction(project.id):
                        project.name = "Mutated"
                        raise ValueError("nested failure")
                except ValueError:
                    pass

        self.assertEqual(project.name, original_name)

    def test_project_mapping_and_series_do_not_expose_mutation_paths(self):
        repository = TableRepository()
        project = repository.create_project("Project")
        sheet = next(iter(project.sheets.values()))
        column = sheet.columns[0]
        sheet.set_cell(0, column.id, "3")
        ref = ColumnRef(project.id, sheet.id, column.id)

        with self.assertRaises(TypeError):
            repository.projects["other"] = project
        detached = repository.series(ref)
        detached.iloc[0] = 99
        self.assertEqual(float(repository.series(ref).iloc[0]), 3.0)


if __name__ == "__main__":
    unittest.main()
