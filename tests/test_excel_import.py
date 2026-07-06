import os
import tempfile
import unittest
import zipfile
from pathlib import Path

_TEST_TMP_DIR = Path(__file__).with_name("_tmp")
_TEST_TMP_DIR.mkdir(exist_ok=True)
os.environ["TEMP"] = str(_TEST_TMP_DIR)
os.environ["TMP"] = str(_TEST_TMP_DIR)
tempfile.tempdir = str(_TEST_TMP_DIR)

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


@unittest.skip("legacy Excel import tests expected a new table per import")
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


class FakeTableViewV3:
    def __init__(self):
        self.model = FakeModel()
        self.columns = {}

    def load_columns(self, columns):
        self.columns = dict(columns)


class FakeSubTableV3:
    def __init__(self):
        self.tables = [FakeTableViewV3()]
        self.tabWidget = type("FakeTabs", (), {"count": lambda _self: len(self.tables) + 1})()

    def add_new_sheet(self):
        table = FakeTableViewV3()
        self.tables.append(table)
        return table

    def get_table(self, index):
        return self.tables[index]


class FakeTableV3:
    def __init__(self, has_current=True):
        self.subtable = FakeSubTableV3() if has_current else None
        self.created_name = None

    def current_subtable(self):
        return self.subtable

    def create_project_table(self, table_name):
        self.created_name = table_name
        self.subtable = FakeSubTableV3()
        return self.subtable


class ExcelImportV3Tests(unittest.TestCase):
    def make_workbook_file(self, filename="input.xlsx"):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        path = temp_dir / filename
        with zipfile.ZipFile(path, "w") as workbook:
            workbook.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
            )
            workbook.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            workbook.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
            )
            workbook.writestr(
                "xl/workbook.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="First" sheetId="1" r:id="rId1"/>
    <sheet name="Second" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""",
            )
            workbook.writestr(
                "xl/styles.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>""",
            )
            workbook.writestr(
                "xl/worksheets/sheet1.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>10</v></c></row>
    <row r="2"><c r="A2"><v>2</v></c><c r="B2"><v>20</v></c></row>
  </sheetData>
</worksheet>""",
            )
            workbook.writestr(
                "xl/worksheets/sheet2.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><v>3</v></c><c r="B1"><v>30</v></c></row>
    <row r="2"><c r="A2"><v>4</v></c><c r="B2"><v>40</v></c></row>
  </sheetData>
</worksheet>""",
            )
        return path

    def test_import_excel_into_current_project_table(self):
        filename = self.make_workbook_file()
        table = FakeTableV3(has_current=True)

        subtable = import_excel_into_table(str(filename), table)

        self.assertIs(subtable, table.subtable)
        self.assertIsNone(table.created_name)
        self.assertEqual(subtable.tables[0].columns, {"1": [1, 2], "2": [10, 20]})
        self.assertEqual(subtable.tables[1].columns, {"1": [3, 4], "2": [30, 40]})
        self.assertEqual(subtable.tables[0].model.save_count, 1)
        self.assertEqual(subtable.tables[1].model.save_count, 1)

    def test_import_without_current_table_creates_project_table_from_filename(self):
        filename = self.make_workbook_file("WorkbookProject.xlsx")
        table = FakeTableV3(has_current=False)

        import_excel_into_table(str(filename), table)

        self.assertEqual(table.created_name, "WorkbookProject")
