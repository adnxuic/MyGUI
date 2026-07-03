import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from code.database.py_database import databases
from code.database.py_database import PyDatabase
from code.database.interpolate_func import interpolate_dict


PROJECT_SCHEMA_NAME = "mygui-project"
PROJECT_SCHEMA_VERSION = 2
SUPPORTED_PROJECT_SCHEMA_VERSIONS = {1, PROJECT_SCHEMA_VERSION}
PROJECT_OBJECT_COLLECTIONS = ("curves", "plots", "scatters", "interpolates", "texts")
DATA_SOURCE_OBJECT_COLLECTIONS = ("plots", "scatters", "interpolates")


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
            "plots": [],
            "scatters": [],
            "interpolates": [],
            "texts": [],
        })
    return canvases


def project_snapshot(figure_window=None) -> dict[str, Any]:
    return {
        "schema": PROJECT_SCHEMA_NAME,
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

    return migrate_project_snapshot(snapshot)


def migrate_project_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("Unsupported project file")

    if snapshot.get("schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file")

    raw_version = snapshot.get("schema_version")
    try:
        schema_version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported project schema version: {raw_version}") from exc

    if schema_version not in SUPPORTED_PROJECT_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported project schema version: {raw_version}")

    migrated = deepcopy(snapshot)
    migrated["schema_version"] = PROJECT_SCHEMA_VERSION
    migrated.setdefault("tables", {})
    figures = migrated.setdefault("figures", [])
    if not isinstance(figures, list):
        raise ValueError("Invalid project figures")

    for figure in figures:
        if not isinstance(figure, dict):
            raise ValueError("Invalid project figure")
        figure.setdefault("axes_layouts", [])
        for collection in PROJECT_OBJECT_COLLECTIONS:
            figure.setdefault(collection, [])

    validate_project_snapshot(migrated)
    return migrated


def validate_project_snapshot(snapshot: dict[str, Any]) -> None:
    tables = _expect_dict(snapshot.get("tables", {}), "tables")
    data_names = _validate_tables(tables)
    figures = _expect_list(snapshot.get("figures", []), "figures")

    for figure_index, figure in enumerate(figures):
        figure_path = f"figures[{figure_index}]"
        _expect_dict(figure, figure_path)
        axes_count = _figure_axes_count(figure, figure_path)
        for collection in PROJECT_OBJECT_COLLECTIONS:
            records = _expect_list(figure.get(collection, []), f"{figure_path}.{collection}")
            for record_index, record in enumerate(records):
                record_path = f"{figure_path}.{collection}[{record_index}]"
                _validate_project_object(collection, record, record_path, axes_count, data_names)


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected list")
    return value


def _require_field(record: dict[str, Any], field_name: str, path: str) -> Any:
    if field_name not in record:
        raise ValueError(f"Missing project field {path}.{field_name}")
    return record[field_name]


def _coerce_int(value: Any, path: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected integer, got {value!r}") from exc


def _coerce_float(value: Any, path: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected number, got {value!r}") from exc


def _validate_tables(tables: dict[str, Any]) -> set[str]:
    data_names: set[str] = set()
    for table_name, sheets in tables.items():
        table_path = f"tables.{table_name}"
        sheets = _expect_dict(sheets, table_path)
        for sheet_name, columns in sheets.items():
            sheet_path = f"{table_path}.{sheet_name}"
            columns = _expect_dict(columns, sheet_path)
            for column_name, values in columns.items():
                column_path = f"{sheet_path}.{column_name}"
                column_index = _coerce_int(column_name, column_path)
                if column_index < 1:
                    raise ValueError(f"Invalid project field {column_path}: column index must be positive")
                _expect_list(values, column_path)
                data_names.add(f"{table_name}/{sheet_name}/{column_name}")
    return data_names


def _figure_axes_count(figure: dict[str, Any], path: str) -> int:
    axes_count = _coerce_int(figure.get("axes_count", 0), f"{path}.axes_count")
    if axes_count < 0:
        raise ValueError(f"Invalid project field {path}.axes_count: must be non-negative")

    axes_layouts = _expect_list(figure.get("axes_layouts", []), f"{path}.axes_layouts")
    for layout_index, layout in enumerate(axes_layouts):
        layout_path = f"{path}.axes_layouts[{layout_index}]"
        layout = _expect_dict(layout, layout_path)
        nrows = _coerce_int(layout.get("nrows", 1), f"{layout_path}.nrows")
        ncols = _coerce_int(layout.get("ncols", 1), f"{layout_path}.ncols")
        if nrows < 1 or ncols < 1:
            raise ValueError(f"Invalid project field {layout_path}: nrows and ncols must be positive")

    return axes_count


def _validate_axes_index(record: dict[str, Any], path: str, axes_count: int) -> None:
    axes_index = _coerce_int(_require_field(record, "axes_index", path), f"{path}.axes_index")
    if axes_index < 0 or axes_index >= axes_count:
        raise ValueError(
            f"Invalid project field {path}.axes_index: {axes_index} outside axes_count {axes_count}"
        )


def _validate_data_source(data_name: Any, path: str, data_names: set[str]) -> None:
    if not isinstance(data_name, str):
        raise ValueError(f"Invalid project field {path}: expected data source string")
    if data_name not in data_names:
        raise ValueError(f"Missing data source for {path}: {data_name}")


def _validate_project_object(collection: str, record: Any, path: str,
                             axes_count: int, data_names: set[str]) -> None:
    record = _expect_dict(record, path)
    _validate_axes_index(record, path, axes_count)

    if collection == "curves":
        _require_field(record, "expression", path)
        _coerce_float(_require_field(record, "x_start", path), f"{path}.x_start")
        _coerce_float(_require_field(record, "x_stop", path), f"{path}.x_stop")

    if collection in DATA_SOURCE_OBJECT_COLLECTIONS:
        _validate_data_source(_require_field(record, "x_data_name", path), f"{path}.x_data_name", data_names)
        _validate_data_source(_require_field(record, "y_data_name", path), f"{path}.y_data_name", data_names)

    if collection == "interpolates":
        method = _require_field(record, "method", path)
        if method not in interpolate_dict:
            raise ValueError(f"Unknown interpolation method at {path}.method: {method}")
        if "k" in record:
            _coerce_int(record["k"], f"{path}.k")

    if collection == "texts":
        _require_field(record, "text", path)
        _coerce_float(_require_field(record, "x", path), f"{path}.x")
        _coerce_float(_require_field(record, "y", path), f"{path}.y")


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
