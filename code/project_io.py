"""Validate, migrate, save, and load MyGUI project snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from code.database import ColumnRef, ColumnType, ProjectTableDocument, TableRepository, validate_component_name
from code.figuremodify.components.serialization import (
    legacy_figure_to_v6,
    normalize_v6_figure,
    normalize_v7_figure,
    normalize_v9_figure,
    migrate_v8_figure_to_v9,
    validate_v9_figure,
)


PROJECT_SCHEMA_NAME = "mygui-project"
PROJECT_SCHEMA_VERSION = 9


def export_database_snapshot(filename: str | Path, repository: TableRepository,
                             project_id: str | None = None) -> None:
    """Export database snapshot."""

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


def migrate_v4_to_v5(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate v4 to v5."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME or root.get("schema_version") != 4:
        raise ValueError("migrate_v4_to_v5 requires a schema v4 project.")
    figure = _expect_dict(root.get("figure"), "figure")
    for record in _expect_list(figure.get("axes", []), "figure.axes"):
        _expect_dict(record, "figure.axes[]").setdefault("color_cycle", None)
    color_order = 0
    for collection in ("curves", "plots", "scatters", "interpolates", "fits"):
        for record in _expect_list(figure.get(collection, []), f"figure.{collection}"):
            chart_record = _expect_dict(record, f"figure.{collection}[]")
            chart_record.setdefault("color_order", color_order)
            saved_order = _coerce_int(
                chart_record["color_order"], f"figure.{collection}[].color_order"
            )
            color_order = max(color_order + 1, saved_order + 1)
    root["schema_version"] = 5
    return root


def migrate_v5_to_v6(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate v5 to v6."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME or root.get("schema_version") != 5:
        raise ValueError("migrate_v5_to_v6 requires a schema v5 project.")
    project = _expect_dict(root.get("project"), "project")
    project_id = str(project.get("id", "")).strip()
    if not project_id:
        raise ValueError("Project id must not be empty.")
    root["figure"] = legacy_figure_to_v6(
        _expect_dict(root.get("figure"), "figure"),
        project_id,
    )
    root["schema_version"] = 6
    return root


def migrate_v6_to_v7(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate a schema-v6 project to the v7 component contract."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME or root.get("schema_version") != 6:
        raise ValueError("migrate_v6_to_v7 requires a schema v6 project.")
    root["figure"] = normalize_v6_figure(
        _expect_dict(root.get("figure"), "figure")
    )
    root["schema_version"] = 7
    return root


def migrate_v7_to_v8(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate schema v7 by adding identity preprocessing to data roles."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME or root.get("schema_version") != 7:
        raise ValueError("migrate_v7_to_v8 requires a schema v7 project.")
    figure = _expect_dict(root.get("figure"), "figure")
    for raw in _expect_list(figure.get("components"), "figure.components"):
        component = _expect_dict(raw, "figure.components[]")
        if component.get("role") in {
            "data_plot",
            "scatter",
            "interpolation",
            "fit_curve",
        }:
            data = _expect_dict(component.get("data"), "figure.components[].data")
            data["preprocess"] = {
                "x_expression": "x",
                "y_expression": "y",
            }
    root["figure"] = normalize_v7_figure(figure)
    root["schema_version"] = 8
    return root


def migrate_v8_to_v9(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate schema v8 to persisted Figure layout/link state."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME or root.get("schema_version") != 8:
        raise ValueError("migrate_v8_to_v9 requires a schema v8 project.")
    project = _expect_dict(root.get("project"), "project")
    project_id = str(project.get("id", "")).strip()
    if not project_id:
        raise ValueError("Project id must not be empty.")
    root["figure"] = migrate_v8_figure_to_v9(
        _expect_dict(root.get("figure"), "figure"),
        project_id,
    )
    root["schema_version"] = 9
    return root


def migrate_project_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Migrate project snapshot."""

    root = deepcopy(_expect_dict(snapshot, "project"))
    if root.get("schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file.")
    version = root.get("schema_version")
    if version == 4:
        root = migrate_v4_to_v5(root)
        version = 5
    if version == 5:
        root = migrate_v5_to_v6(root)
        version = 6
    if version == 6:
        root = migrate_v6_to_v7(root)
        version = 7
    if version == 7:
        root = migrate_v7_to_v8(root)
        version = 8
    if version == 8:
        root = migrate_v8_to_v9(root)
        version = 9
    if version == PROJECT_SCHEMA_VERSION:
        root["figure"] = normalize_v9_figure(
            _expect_dict(root.get("figure"), "figure")
        )
        return root
    raise ValueError(
        f"Unsupported project schema version {version!r}; "
        "supported versions are v4, v5, v6, v7, v8, and v9."
    )


def validate_project_snapshot(snapshot: dict[str, Any]) -> None:
    """Validate project snapshot."""

    root = _expect_dict(snapshot, "project")
    if root.get("schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file.")
    version = root.get("schema_version")
    if version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {version!r}; "
            f"only schema v{PROJECT_SCHEMA_VERSION} is valid after migration."
        )
    project = _expect_dict(root.get("project"), "project")
    project_id = str(project.get("id", "")).strip()
    if not project_id:
        raise ValueError("Project id must not be empty.")
    project_name = validate_component_name(project.get("name", ""), "Project name")
    refs = _validate_table(root.get("table"), project_id, project_name)
    validate_v9_figure(root.get("figure"), refs, project_id, project_name)


def project_snapshot(figure_window=None, *, canvas=None) -> dict[str, Any]:
    """Build the complete serializable project snapshot."""

    if figure_window is None:
        raise ValueError("No Figure window is available to save.")
    if canvas is None:
        canvas = getattr(figure_window, "current_canva", None)
    if canvas is None:
        raise ValueError("No current project canvas to save.")
    project = figure_window.repository.project(canvas.project_id)
    figure = normalize_v9_figure(canvas.component_snapshot())
    snapshot = {
        "schema": PROJECT_SCHEMA_NAME,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {"id": project.id, "name": project.name},
        "table": project.to_snapshot(),
        "figure": figure,
    }
    validate_project_snapshot(snapshot)
    return snapshot


def save_project_snapshot(
    filename: str | Path,
    figure_window=None,
    *,
    canvas=None,
) -> dict[str, Any]:
    """Save project snapshot."""

    path = Path(filename)
    if canvas is None and figure_window is not None:
        canvas = getattr(figure_window, "current_canva", None)
    snapshot = project_snapshot(figure_window, canvas=canvas)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            temp_name = handle.name
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except PermissionError:
                pass
    if canvas is not None:
        canvas.project_path = str(path)
    mark_clean = getattr(figure_window, "mark_canvas_clean", None)
    if callable(mark_clean) and canvas is not None:
        mark_clean(canvas, snapshot=snapshot)
    return snapshot


def load_project_file(filename: str | Path) -> dict[str, Any]:
    """Load project file."""

    with Path(filename).open("r", encoding="utf-8-sig") as handle:
        snapshot = json.load(handle)
    snapshot = migrate_project_snapshot(snapshot)
    validate_project_snapshot(snapshot)
    return snapshot


def restore_project_snapshot(filename: str | Path, table=None, figure_window=None) -> dict[str, Any]:
    """Restore project snapshot."""

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
            canvas = figure_window.load_project_figure_snapshot(
                snapshot["figure"],
                project_name,
                project_path=str(Path(filename)),
            )
            mark_clean = getattr(figure_window, "mark_canvas_clean", None)
            if callable(mark_clean) and canvas is not None:
                mark_clean(canvas)
        return snapshot
    except Exception:
        if figure_window is not None:
            figure_window.remove_project(project_name)
        if table_loaded:
            table.remove_project_table(project_id)
        raise
