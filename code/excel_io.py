from typing import Any
from pathlib import Path

import openpyxl as xl

from code.database.py_database import validate_project_component_name


def read_excel_columns(file_name: str) -> list[list[list[Any]]]:
    wb = xl.load_workbook(file_name)
    try:
        sheets: list[list[list[Any]]] = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheets.append([[cell.value for cell in col] for col in sheet.iter_cols()])
        return sheets
    finally:
        wb.close()


def import_excel_into_table(file_name: str, table):
    subtable = table.current_subtable() if hasattr(table, "current_subtable") else None
    if subtable is None:
        project_name = validate_project_component_name(Path(file_name).stem, "Project name")
        subtable = table.create_project_table(project_name)
    for sheet_index, columns in enumerate(read_excel_columns(file_name)):
        if sheet_index < subtable.tabWidget.count() - 1:
            tableview = subtable.get_table(sheet_index)
        else:
            tableview = subtable.add_new_sheet()
        tableview.load_columns({
            str(column_index + 1): data_list
            for column_index, data_list in enumerate(columns)
        })
        tableview.model.save_data_to_database()

    return subtable
