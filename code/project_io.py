import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from code.database.py_database import databases
from code.database.py_database import PyDatabase
from code.database.py_database import validate_project_component_name
from code.database.interpolate_func import (
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    interpolate_dict,
)


PROJECT_SCHEMA_NAME = "mygui-project"
PROJECT_SCHEMA_VERSION = 3
PROJECT_OBJECT_COLLECTIONS = ("curves", "plots", "scatters", "interpolates", "fits", "texts")
DATA_SOURCE_OBJECT_COLLECTIONS = ("plots", "scatters", "interpolates", "fits")


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


def export_database_snapshot(filename: str | Path) -> None:
    path = Path(filename)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serialize_databases(), handle, ensure_ascii=False, indent=2)


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


def _coerce_bool(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"Invalid project field {path}: expected boolean, got {value!r}")


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
    if collection == "texts":
        _validate_text_record(record, path, axes_count)
        return

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
            k = _coerce_int(record["k"], f"{path}.k")
            if k < 1 or k > 5:
                raise ValueError(f"Invalid project field {path}.k: must be between 1 and 5")
        if "samples" in record:
            samples = _coerce_int(record["samples"], f"{path}.samples")
            if samples < MIN_INTERPOLATION_SAMPLES or samples > MAX_INTERPOLATION_SAMPLES:
                raise ValueError(
                    f"Invalid project field {path}.samples: must be between "
                    f"{MIN_INTERPOLATION_SAMPLES} and {MAX_INTERPOLATION_SAMPLES}"
                )
        if "lam_auto" in record:
            _coerce_bool(record["lam_auto"], f"{path}.lam_auto")
        if record.get("lam") is not None:
            lam = _coerce_float(record["lam"], f"{path}.lam")
            if not np.isfinite(lam) or lam < 0:
                raise ValueError(f"Invalid project field {path}.lam: must be finite and non-negative")

    if collection == "fits":
        engine = record.get("engine", "Python")
        if engine not in {"Python", "Matlab"}:
            raise ValueError(f"Invalid project field {path}.engine: {engine!r}")
        if record.get("fit_type") is not None and not isinstance(record.get("fit_type"), str):
            raise ValueError(f"Invalid project field {path}.fit_type: expected string or null")
        if record.get("fit_options") is not None:
            _expect_dict(record.get("fit_options"), f"{path}.fit_options")
        if record.get("fit_result") is not None:
            _validate_fit_result(record.get("fit_result"), f"{path}.fit_result")
        if "expression" in record and not isinstance(record.get("expression"), str):
            raise ValueError(f"Invalid project field {path}.expression: expected string")
        for field_name in ("x_start", "x_stop"):
            value = _coerce_float(_require_field(record, field_name, path), f"{path}.{field_name}")
            if not np.isfinite(value):
                raise ValueError(f"Invalid project field {path}.{field_name}: must be finite")


def _validate_fit_result(value: Any, path: str) -> None:
    result = _expect_dict(value, path)
    for field_name in ("value_expression", "show_expression", "formula", "fit_type"):
        if field_name in result and not isinstance(result[field_name], str):
            raise ValueError(f"Invalid project field {path}.{field_name}: expected string")
    coefficients = _expect_list(result.get("coefficients", []), f"{path}.coefficients")
    for index, coefficient in enumerate(coefficients):
        coefficient_path = f"{path}.coefficients[{index}]"
        coefficient = _expect_dict(coefficient, coefficient_path)
        if "name" in coefficient and not isinstance(coefficient["name"], str):
            raise ValueError(f"Invalid project field {coefficient_path}.name: expected string")
        for field_name in ("value", "lower", "upper"):
            if coefficient.get(field_name) is not None:
                _coerce_float(coefficient[field_name], f"{coefficient_path}.{field_name}")
    goodness = result.get("goodness", {})
    if goodness is not None:
        goodness = _expect_dict(goodness, f"{path}.goodness")
        for field_name, field_value in goodness.items():
            if field_value is not None:
                _coerce_float(field_value, f"{path}.goodness.{field_name}")
    if result.get("confidence_level") is not None:
        _coerce_float(result["confidence_level"], f"{path}.confidence_level")


def _validate_number_pair(value: Any, path: str, *, allow_equal: bool = False) -> None:
    pair = _expect_list(value, path)
    if len(pair) != 2:
        raise ValueError(f"Invalid project field {path}: expected two numbers")
    first = _coerce_float(pair[0], f"{path}[0]")
    second = _coerce_float(pair[1], f"{path}[1]")
    if not np.isfinite(first) or not np.isfinite(second):
        raise ValueError(f"Invalid project field {path}: values must be finite")
    if not allow_equal and first == second:
        raise ValueError(f"Invalid project field {path}: values must be different")


def _validate_spine_state(value: Any, path: str) -> None:
    state = _expect_dict(value, path)
    if "visible" in state:
        _coerce_bool(state["visible"], f"{path}.visible")
    if "position" not in state:
        return
    position = _expect_list(state["position"], f"{path}.position")
    if len(position) != 2:
        raise ValueError(f"Invalid project field {path}.position: expected [mode, value]")
    if not isinstance(position[0], str):
        raise ValueError(f"Invalid project field {path}.position[0]: expected string")
    number = _coerce_float(position[1], f"{path}.position[1]")
    if not np.isfinite(number):
        raise ValueError(f"Invalid project field {path}.position[1]: must be finite")


def _validate_legend_state(value: Any, path: str) -> None:
    if value is None:
        return
    legend = _expect_dict(value, path)
    if "visible" in legend:
        _coerce_bool(legend["visible"], f"{path}.visible")
    if "loc" in legend and isinstance(legend["loc"], list):
        _validate_number_pair(legend["loc"], f"{path}.loc", allow_equal=True)


def _validate_axes_state_record(record: Any, path: str, axes_count: int) -> None:
    record = _expect_dict(record, path)
    axes_index = _coerce_int(_require_field(record, "index", path), f"{path}.index")
    if axes_index < 0 or axes_index >= axes_count:
        raise ValueError(
            f"Invalid project field {path}.index: {axes_index} outside axes_count {axes_count}"
        )
    if "xlim" in record:
        _validate_number_pair(record["xlim"], f"{path}.xlim")
    if "ylim" in record:
        _validate_number_pair(record["ylim"], f"{path}.ylim")
    for field_name in ("xlabel", "ylabel", "label_fontfamily"):
        if field_name in record and not isinstance(record[field_name], str):
            raise ValueError(f"Invalid project field {path}.{field_name}: expected string")
    if "label_fontsize" in record:
        fontsize = _coerce_float(record["label_fontsize"], f"{path}.label_fontsize")
        if not np.isfinite(fontsize) or fontsize <= 0:
            raise ValueError(f"Invalid project field {path}.label_fontsize: must be positive")
    for field_name in ("x_label_position", "y_label_position"):
        if field_name in record:
            _validate_number_pair(record[field_name], f"{path}.{field_name}", allow_equal=True)
    for field_name in ("xaxis_visible", "yaxis_visible"):
        if field_name in record:
            _coerce_bool(record[field_name], f"{path}.{field_name}")
    spines = record.get("spines", {})
    if spines is not None:
        spines = _expect_dict(spines, f"{path}.spines")
        for spine_name, spine_state in spines.items():
            if not isinstance(spine_name, str):
                raise ValueError(f"Invalid project field {path}.spines: spine name must be string")
            _validate_spine_state(spine_state, f"{path}.spines.{spine_name}")
    _validate_legend_state(record.get("legend"), f"{path}.legend")


def _validate_text_record(record: dict[str, Any], path: str, axes_count: int) -> None:
    scope = record.get("scope", "axes")
    if scope not in {"axes", "figure"}:
        raise ValueError(f"Invalid project field {path}.scope: {scope!r}")
    if scope == "axes":
        _validate_axes_index(record, path, axes_count)

    _require_field(record, "text", path)
    _coerce_float(_require_field(record, "x", path), f"{path}.x")
    _coerce_float(_require_field(record, "y", path), f"{path}.y")
    if "usetex" in record:
        _coerce_bool(record["usetex"], f"{path}.usetex")


def _project_values_to_array(values: list[Any]) -> np.ndarray:
    data = np.array(values)
    try:
        return data.astype(float)
    except (TypeError, ValueError):
        return data.astype(str)

def serialize_project_table(table_name: str) -> dict[str, Any]:
    if table_name not in databases:
        raise ValueError(f"Missing project table: {table_name}")
    return {
        "name": table_name,
        "sheets": {
            sheet_name: {
                column_name: values[0].tolist()
                for column_name, values in database.data.items()
            }
            for sheet_name, database in databases[table_name].items()
        },
    }


def project_snapshot(figure_window=None) -> dict[str, Any]:
    if figure_window is None or getattr(figure_window, "current_canva", None) is None:
        raise ValueError("No current project canvas to save.")
    canvas = figure_window.current_canva
    project_name = validate_project_component_name(canvas.project_name, "Project name")
    figure = canvas.project_snapshot()
    figure["name"] = project_name
    snapshot = {
        "schema": PROJECT_SCHEMA_NAME,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": project_name,
        "table": serialize_project_table(canvas.project_table_name),
        "figure": figure,
    }
    validate_project_snapshot(snapshot)
    return snapshot


def save_project_snapshot(filename: str | Path, figure_window=None) -> None:
    path = Path(filename)
    snapshot = project_snapshot(figure_window)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        try:
            os.replace(temp_name, path)
            temp_name = None
        except PermissionError:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, ensure_ascii=False, indent=2)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except PermissionError:
                pass


def load_project_file(filename: str | Path) -> dict[str, Any]:
    path = Path(filename)
    with path.open("r", encoding="utf-8-sig") as handle:
        snapshot = json.load(handle)
    validate_project_snapshot(snapshot)
    return snapshot


def validate_project_snapshot(snapshot: dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("Unsupported project file")
    if snapshot.get("schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file")
    raw_version = snapshot.get("schema_version")
    try:
        schema_version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported project schema version: {raw_version}") from exc
    if schema_version != PROJECT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {raw_version}")

    project_name = validate_project_component_name(snapshot.get("name", ""), "Project name")
    table = _expect_dict(snapshot.get("table"), "table")
    figure = _expect_dict(snapshot.get("figure"), "figure")
    if table.get("name") != project_name:
        raise ValueError("Project table name must match project name")
    if figure.get("name") != project_name:
        raise ValueError("Project figure name must match project name")

    data_names = _validate_project_table(table, project_name)
    axes_count = _figure_axes_count(figure, "figure")
    axes_records = _expect_list(figure.get("axes", []), "figure.axes")
    for axes_record_index, axes_record in enumerate(axes_records):
        _validate_axes_state_record(
            axes_record,
            f"figure.axes[{axes_record_index}]",
            axes_count,
        )
    for collection in PROJECT_OBJECT_COLLECTIONS:
        records = _expect_list(figure.get(collection, []), f"figure.{collection}")
        for record_index, record in enumerate(records):
            _validate_project_object(
                collection,
                record,
                f"figure.{collection}[{record_index}]",
                axes_count,
                data_names,
            )


def _validate_project_table(table: dict[str, Any], project_name: str) -> set[str]:
    table_name = validate_project_component_name(table.get("name", ""), "Project name")
    if table_name != project_name:
        raise ValueError("Project table name must match project name")
    sheets = _expect_dict(table.get("sheets", {}), "table.sheets")
    data_names: set[str] = set()
    for sheet_name, columns in sheets.items():
        sheet_name = validate_project_component_name(sheet_name, "Sheet name")
        columns = _expect_dict(columns, f"table.sheets.{sheet_name}")
        for column_name, values in columns.items():
            column_path = f"table.sheets.{sheet_name}.{column_name}"
            column_index = _coerce_int(column_name, column_path)
            if column_index < 1:
                raise ValueError(f"Invalid project field {column_path}: column index must be positive")
            _expect_list(values, column_path)
            data_names.add(f"{table_name}/{sheet_name}/{column_name}")
    return data_names


def _restore_project_table_to_database(table_snapshot: dict[str, Any]) -> None:
    table_name = validate_project_component_name(table_snapshot.get("name", ""), "Project name")
    if table_name in databases:
        raise ValueError(f"Project already exists: {table_name}")
    PyDatabase.register_table(table_name)
    for sheet_name, columns in (table_snapshot.get("sheets") or {}).items():
        database = PyDatabase()
        PyDatabase.register_sheet(table_name, sheet_name, database)
        for column_name, values in columns.items():
            database.update_data(int(column_name), _project_values_to_array(values))


def restore_project_snapshot(filename: str | Path, table=None, figure_window=None) -> dict[str, Any]:
    snapshot = load_project_file(filename)
    project_name = snapshot["name"]

    if table is not None and hasattr(table, "has_table") and table.has_table(project_name):
        raise ValueError(f"Project already exists: {project_name}")
    if figure_window is not None and hasattr(figure_window, "has_project_name"):
        if figure_window.has_project_name(project_name):
            raise ValueError(f"Project already exists: {project_name}")
    elif project_name in databases:
        raise ValueError(f"Project already exists: {project_name}")

    table_loaded = False
    try:
        if table is not None and hasattr(table, "load_project_table_snapshot"):
            table.load_project_table_snapshot(snapshot["table"])
        else:
            _restore_project_table_to_database(snapshot["table"])
        table_loaded = True

        if figure_window is not None and hasattr(figure_window, "load_project_figure_snapshot"):
            figure_window.load_project_figure_snapshot(
                snapshot["figure"],
                project_name,
                project_path=str(Path(filename)),
            )
        return snapshot
    except Exception:
        if figure_window is not None and hasattr(figure_window, "remove_project"):
            figure_window.remove_project(project_name)
        if table_loaded:
            if table is not None and hasattr(table, "remove_project_table"):
                table.remove_project_table(project_name)
            else:
                PyDatabase.unregister_table(project_name)
        raise
