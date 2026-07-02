from typing import Any

import openpyxl as xl


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
    subtable = table.add_new_table(is_open=True)
    for sheet_index, columns in enumerate(read_excel_columns(file_name)):
        if sheet_index > 0:
            subtable.add_new_sheet()

        tableview = subtable.get_table(sheet_index)
        for column_index, data_list in enumerate(columns):
            tableview.add_excel_data(data_list, column_index)
        tableview.model.save_data_to_database()

    return subtable
