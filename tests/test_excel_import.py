import os
import tempfile
import unittest
from pathlib import Path

import openpyxl

from code.excel_io import import_excel_into_table, read_excel_columns


class FakeModel:
    def __init__(self):
        self.save_count = 0

    def save_data_to_database(self):
        self.save_count += 1


class FakeTableView:
    def __init__(self):
        self.model = FakeModel()
        self.columns = {}

    def add_excel_data(self, data_list, index):
        self.columns[index] = data_list


class FakeSubTable:
    def __init__(self):
        self.tables = [FakeTableView()]

    def add_new_sheet(self):
        self.tables.append(FakeTableView())

    def get_table(self, index):
        return self.tables[index]


class FakeTable:
    def __init__(self):
        self.subtable = FakeSubTable()

    def add_new_table(self, is_open=False):
        self.is_open = is_open
        return self.subtable


class ExcelImportTests(unittest.TestCase):
    def make_workbook_file(self):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        tempfile.tempdir = str(temp_dir)
        os.environ["TMP"] = str(temp_dir)
        os.environ["TEMP"] = str(temp_dir)

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "First"
        ws1.append([1, 10])
        ws1.append([2, 20])
        ws2 = wb.create_sheet("Second")
        ws2.append([3, 30])
        ws2.append([4, 40])

        filename = Path(__file__).with_name("_excel_import_tmp.xlsx")
        wb.save(filename)
        wb.close()
        return filename

    def test_read_excel_columns_reads_all_sheets(self):
        filename = self.make_workbook_file()
        try:
            sheets = read_excel_columns(filename)

            self.assertEqual(sheets, [
                [[1, 2], [10, 20]],
                [[3, 4], [30, 40]],
            ])
        finally:
            os.remove(filename)

    def test_import_excel_into_table_applies_columns_and_saves_each_sheet(self):
        filename = self.make_workbook_file()
        try:
            table = FakeTable()
            subtable = import_excel_into_table(filename, table)

            self.assertTrue(table.is_open)
            self.assertEqual(subtable.tables[0].columns, {0: [1, 2], 1: [10, 20]})
            self.assertEqual(subtable.tables[1].columns, {0: [3, 4], 1: [30, 40]})
            self.assertEqual(subtable.tables[0].model.save_count, 1)
            self.assertEqual(subtable.tables[1].model.save_count, 1)
        finally:
            os.remove(filename)


if __name__ == "__main__":
    unittest.main()
