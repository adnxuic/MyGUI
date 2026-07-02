import json
from pathlib import Path
from typing import Any

from code.database.py_database import databases


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
            "dpi": float(fig.dpi),
            "size_inches": [float(value) for value in fig.get_size_inches()],
            "axes_count": len(fig.axes),
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
