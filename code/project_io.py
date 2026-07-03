import json
from pathlib import Path
from typing import Any

import numpy as np

from code.database.py_database import databases
from code.database.py_database import PyDatabase


PROJECT_SCHEMA_VERSION = 1


def serialize_databases() -> dict[str, dict[str, dict[str, list[Any]]]]:
    tables: dict[str, dict[str, dict[str, list[Any]]]] = {}
    for table_name, sheets in databases.items():
        tables[table_name] = {}
        for sheet_name, database in sheets.items():
            tables[table_name][sheet_name] = {
                column_name: values[0].tolist()
                for column_name, values in database.data.items()
            }
    return tables


def serialize_figure_window(figure_window) -> list[dict[str, Any]]:
    if figure_window is None:
        return []

    if hasattr(figure_window, "project_snapshot"):
        return figure_window.project_snapshot()

    canvases: list[dict[str, Any]] = []
    tabwindow = getattr(figure_window, "tabwindow", None)
    if tabwindow is None:
        return canvases

    for index in range(tabwindow.count()):
        canvas = tabwindow.widget(index)
        fig = getattr(canvas, "fig", None)
        if fig is None:
            continue

        canvases.append({
            "name": tabwindow.tabText(index),
            "style": getattr(canvas, "style", None),
            "dpi": float(fig.dpi),
            "size_inches": [float(value) for value in fig.get_size_inches()],
            "axes_count": len(fig.axes),
            "axes_layouts": [],
            "curves": [],
        })
    return canvases


def project_snapshot(figure_window=None) -> dict[str, Any]:
    return {
        "schema": "mygui-project",
        "schema_version": PROJECT_SCHEMA_VERSION,
        "tables": serialize_databases(),
        "figures": serialize_figure_window(figure_window),
    }


def save_project_snapshot(filename: str | Path, figure_window=None) -> None:
    path = Path(filename)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(project_snapshot(figure_window), handle, ensure_ascii=False, indent=2)


def export_database_snapshot(filename: str | Path) -> None:
    path = Path(filename)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serialize_databases(), handle, ensure_ascii=False, indent=2)


def load_project_file(filename: str | Path) -> dict[str, Any]:
    path = Path(filename)
    with path.open("r", encoding="utf-8") as handle:
        snapshot = json.load(handle)

    if snapshot.get("schema") != "mygui-project":
        raise ValueError("Unsupported project file")
    if snapshot.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {snapshot.get('schema_version')}")
    return snapshot


def restore_databases(tables: dict[str, dict[str, dict[str, list[Any]]]]) -> None:
    PyDatabase.clear()
    for table_name, sheets in tables.items():
        PyDatabase.register_table(table_name)
        for sheet_name, columns in sheets.items():
            database = PyDatabase()
            PyDatabase.register_sheet(table_name, sheet_name, database)
            for column_name, values in columns.items():
                try:
                    column_index = int(column_name)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid column name in project: {column_name}") from exc
                database.update_data(column_index, _project_values_to_array(values))


def _project_values_to_array(values: list[Any]) -> np.ndarray:
    data = np.array(values)
    try:
        return data.astype(float)
    except (TypeError, ValueError):
        return data.astype(str)


def restore_project_snapshot(filename: str | Path, table=None, figure_window=None) -> dict[str, Any]:
    snapshot = load_project_file(filename)
    tables = snapshot.get("tables", {})

    if table is not None and hasattr(table, "load_database_snapshot"):
        table.load_database_snapshot(tables)
    else:
        restore_databases(tables)

    if figure_window is not None and hasattr(figure_window, "load_figure_snapshot"):
        figure_window.load_figure_snapshot(snapshot.get("figures", []))

    return snapshot
