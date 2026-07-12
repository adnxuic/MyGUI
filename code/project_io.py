from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from code.database import ColumnRef, ColumnType, ProjectTableDocument, TableRepository, validate_component_name
from code.database.interpolate_func import interpolate_dict


PROJECT_SCHEMA_NAME = "mygui-project"
PROJECT_SCHEMA_VERSION = 4
DATA_SOURCE_COLLECTIONS = ("plots", "scatters", "interpolates", "fits")
FIGURE_COLLECTIONS = ("curves", *DATA_SOURCE_COLLECTIONS, "texts")


def export_database_snapshot(filename: str | Path, repository: TableRepository,
                             project_id: str | None = None) -> None:
    if project_id is None:
        payload = [project.to_snapshot() for project in repository.projects.values()]
    else:
        payload = repository.snapshot(project_id)
    Path(filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected array.")
    return value


def _coerce_int(value: Any, path: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected integer.") from exc


def _coerce_float(value: Any, path: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected number.") from exc


def _validate_table(table_snapshot: Any, project_id: str,
                    project_name: str) -> dict[ColumnRef, ColumnType]:
    table = _expect_dict(table_snapshot, "table")
    document = ProjectTableDocument.from_snapshot(table)
    if document.id != project_id:
        raise ValueError("Project and table identifiers must match.")
    if document.name != project_name:
        raise ValueError("Project and table names must match.")
    refs = {}
    sheet_names = set()
    for sheet in document.sheets.values():
        validate_component_name(sheet.name, "Sheet name")
        normalized = sheet.name.casefold()
        if normalized in sheet_names:
            raise ValueError(f"Duplicate sheet name: {sheet.name}")
        sheet_names.add(normalized)
        column_names = set()
        for column in sheet.columns:
            normalized_column = column.name.casefold()
            if normalized_column in column_names:
                raise ValueError(f"Duplicate column name in {sheet.name}: {column.name}")
            column_names.add(normalized_column)
            refs[ColumnRef(project_id, sheet.id, column.id)] = column.type
    return refs


def _validate_axes(figure: dict[str, Any]) -> int:
    axes_count = _coerce_int(figure.get("axes_count", 0), "figure.axes_count")
    if axes_count < 0:
        raise ValueError("figure.axes_count must not be negative.")
    size = _expect_list(figure.get("size_inches", []), "figure.size_inches")
    if len(size) != 2 or any(_coerce_float(value, "figure.size_inches") <= 0 for value in size):
        raise ValueError("figure.size_inches must contain two positive numbers.")
    _coerce_float(figure.get("dpi", 100), "figure.dpi")
    for record in _expect_list(figure.get("axes", []), "figure.axes"):
        axes_record = _expect_dict(record, "figure.axes[]")
        index = _coerce_int(axes_record.get("index", -1), "figure.axes[].index")
        if not 0 <= index < axes_count:
            raise ValueError(f"Invalid axes index: {index}")
    return axes_count


def _validate_figure(figure_snapshot: Any, available_refs: dict[ColumnRef, ColumnType],
                     project_id: str) -> None:
    figure = _expect_dict(figure_snapshot, "figure")
    axes_count = _validate_axes(figure)
    object_ids = set()
    for collection in FIGURE_COLLECTIONS:
        records = _expect_list(figure.get(collection, []), f"figure.{collection}")
        for index, raw_record in enumerate(records):
            path = f"figure.{collection}[{index}]"
            record = _expect_dict(raw_record, path)
            if collection != "texts" or record.get("scope", "axes") != "figure":
                axes_index = _coerce_int(record.get("axes_index", 0), f"{path}.axes_index")
                if not 0 <= axes_index < axes_count:
                    raise ValueError(f"Invalid project field {path}.axes_index: {axes_index}")
            if collection in DATA_SOURCE_COLLECTIONS:
                object_id = str(record.get("object_id", "")).strip()
                if not object_id or object_id in object_ids:
                    raise ValueError(f"Invalid or duplicate object id at {path}.")
                object_ids.add(object_id)
                for field in ("x_ref", "y_ref"):
                    ref = ColumnRef.from_dict(record.get(field))
                    if ref.project_id != project_id or ref not in available_refs:
                        raise ValueError(f"Invalid data reference at {path}.{field}.")
                    allowed = {ColumnType.NUMBER, ColumnType.DATETIME} if field == "x_ref" else {ColumnType.NUMBER}
                    if available_refs[ref] not in allowed:
                        raise ValueError(f"Incompatible column type at {path}.{field}.")
            if collection == "interpolates" and record.get("method") not in interpolate_dict:
                raise ValueError(f"Unknown interpolation method at {path}.")
            if collection == "fits" and record.get("engine", "Python") not in {"Python", "Matlab"}:
                raise ValueError(f"Unknown fitting engine at {path}.")


def validate_project_snapshot(snapshot: dict[str, Any]) -> None:
    root = _expect_dict(snapshot, "project")
    if root.get("schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file.")
    version = root.get("schema_version")
    if version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {version!r}; only schema v{PROJECT_SCHEMA_VERSION} is supported."
        )
    project = _expect_dict(root.get("project"), "project")
    project_id = str(project.get("id", "")).strip()
    if not project_id:
        raise ValueError("Project id must not be empty.")
    project_name = validate_component_name(project.get("name", ""), "Project name")
    refs = _validate_table(root.get("table"), project_id, project_name)
    _validate_figure(root.get("figure"), refs, project_id)


def project_snapshot(figure_window=None) -> dict[str, Any]:
    if figure_window is None or getattr(figure_window, "current_canva", None) is None:
        raise ValueError("No current project canvas to save.")
    canvas = figure_window.current_canva
    project = figure_window.repository.project(canvas.project_id)
    snapshot = {
        "schema": PROJECT_SCHEMA_NAME,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {"id": project.id, "name": project.name},
        "table": project.to_snapshot(),
        "figure": canvas.project_snapshot(),
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
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            temp_name = handle.name
        try:
            os.replace(temp_name, path)
            temp_name = None
        except PermissionError:
            path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except PermissionError:
                pass


def load_project_file(filename: str | Path) -> dict[str, Any]:
    with Path(filename).open("r", encoding="utf-8-sig") as handle:
        snapshot = json.load(handle)
    validate_project_snapshot(snapshot)
    return snapshot


def restore_project_snapshot(filename: str | Path, table=None, figure_window=None) -> dict[str, Any]:
    snapshot = load_project_file(filename)
    project_meta = snapshot["project"]
    project_id = project_meta["id"]
    project_name = project_meta["name"]
    repository = getattr(table, "repository", None) or getattr(figure_window, "repository", None)
    if repository is None:
        raise ValueError("Project restore requires a TableRepository-backed window.")
    if project_id in repository.projects or repository.project_by_name(project_name, required=False) is not None:
        raise ValueError(f"Project already exists: {project_name}")

    table_loaded = False
    try:
        if table is None:
            raise ValueError("Project restore requires the Table widget.")
        table.load_project_table_snapshot(snapshot["table"])
        table_loaded = True
        if figure_window is not None:
            figure_window.load_project_figure_snapshot(
                snapshot["figure"], project_name, project_path=str(Path(filename))
            )
        return snapshot
    except Exception:
        if figure_window is not None:
            figure_window.remove_project(project_name)
        if table_loaded:
            table.remove_project_table(project_id)
        raise
