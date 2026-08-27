"""Validate, migrate, save, and load strict schema-v17 project snapshots."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from mygui.database import ColumnRef, ColumnType, ProjectTableDocument, TableRepository, validate_component_name
from mygui.figuremodify.components.serialization import (
    normalize_v17_figure,
    validate_v10_figure,
    validate_v11_figure,
    validate_v12_figure,
    validate_v13_figure,
    validate_v14_figure,
    validate_v15_figure,
    validate_v16_figure,
    validate_v17_figure,
)
from mygui.resource_limits import load_resource_limits, validate_json_budget


PROJECT_SCHEMA_NAME = "mygui-project"
PROJECT_SCHEMA_VERSION = 17
SCHEMA_V16_VERSION = 16
SCHEMA_V15_VERSION = 15
SCHEMA_V14_VERSION = 14
SCHEMA_V13_VERSION = 13
SCHEMA_V12_VERSION = 12
SCHEMA_V11_VERSION = 11
SCHEMA_V10_VERSION = 10
LOGGER = logging.getLogger(__name__)


def _json_bytes(payload: Any, *, pretty: bool) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=not pretty,
        allow_nan=False,
    ).encode("utf-8")


def project_fingerprint(snapshot: dict[str, Any]) -> str:
    """Return the canonical persisted-state fingerprint for a project."""

    return hashlib.sha256(_json_bytes(snapshot, pretty=False)).hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as handle:
            temp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                LOGGER.exception("Unable to remove temporary project file %s", temp_name)


def export_database_snapshot(filename: str | Path, repository: TableRepository,
                             project_id: str | None = None) -> None:
    """Export database snapshot."""

    if project_id is None:
        payload = [project.to_snapshot() for project in repository.projects.values()]
    else:
        payload = repository.snapshot(project_id)
    encoded = _json_bytes(payload, pretty=True)
    limits = load_resource_limits()
    if len(encoded) > limits.max_project_bytes:
        raise ValueError("Database export exceeds the configured file-size budget.")
    _atomic_write_bytes(Path(filename), encoded)


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected array.")
    return value


def _expect_exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"Invalid project field {path}: expected exactly {sorted(expected)}, "
            f"got {sorted(actual)}."
        )


def _expect_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid project field {path}: expected string.")
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}.")


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


def _validate_project_snapshot_version(
    snapshot: dict[str, Any],
    *,
    version: int,
    figure_validator,
) -> None:
    """Validate one exact project schema version."""

    validate_json_budget(snapshot, limits=load_resource_limits())
    root = _expect_dict(snapshot, "project")
    _expect_exact_keys(
        root,
        {"schema", "schema_version", "project", "table", "figure"},
        "project",
    )
    if _expect_string(root.get("schema"), "schema") != PROJECT_SCHEMA_NAME:
        raise ValueError("Unsupported project file.")
    actual_version = root.get("schema_version")
    if type(actual_version) is not int or actual_version != version:
        raise ValueError(
            f"Unsupported project schema version {actual_version!r}; "
            f"expected exact integer schema v{version}."
        )
    project = _expect_dict(root.get("project"), "project")
    _expect_exact_keys(project, {"id", "name"}, "project.project")
    project_id = _expect_string(project.get("id"), "project.id").strip()
    if not project_id:
        raise ValueError("Project id must not be empty.")
    project_name = validate_component_name(
        _expect_string(project.get("name"), "project.name"),
        "Project name",
    )
    refs = _validate_table(root.get("table"), project_id, project_name)
    figure_validator(root.get("figure"), refs, project_id, project_name)


def validate_project_snapshot(snapshot: dict[str, Any]) -> None:
    """Validate one exact current schema-v17 project snapshot."""

    _validate_project_snapshot_version(
        snapshot,
        version=PROJECT_SCHEMA_VERSION,
        figure_validator=validate_v17_figure,
    )


def validate_v16_project_snapshot(snapshot: dict[str, Any]) -> None:
    """Validate one exact predecessor schema-v16 project snapshot."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V16_VERSION,
        figure_validator=validate_v16_figure,
    )


def validate_v15_project_snapshot(snapshot: dict[str, Any]) -> None:
    """Validate one exact predecessor schema-v15 project snapshot."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V15_VERSION,
        figure_validator=validate_v15_figure,
    )


def validate_v14_project_snapshot(snapshot: dict[str, Any]) -> None:
    """Validate one exact predecessor schema-v14 project snapshot."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V14_VERSION,
        figure_validator=validate_v14_figure,
    )


def migrate_v10_to_v11(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate and migrate a schema-v10 tree to schema v11."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V10_VERSION,
        figure_validator=validate_v10_figure,
    )
    migrated = deepcopy(snapshot)
    migrated["schema_version"] = SCHEMA_V11_VERSION
    # The eight-field component tree is unchanged. Schema v10 cannot contain
    # Colorbar records, so no component-level rewrite is needed.
    _validate_project_snapshot_version(
        migrated,
        version=SCHEMA_V11_VERSION,
        figure_validator=validate_v11_figure,
    )
    return migrated


def migrate_v11_to_v12(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate and migrate a schema-v11 tree to schema v12."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V11_VERSION,
        figure_validator=validate_v11_figure,
    )
    migrated = deepcopy(snapshot)
    migrated["schema_version"] = SCHEMA_V12_VERSION
    # Reference Marks is a new v12 record. Existing v11 records retain their
    # exact eight-field wire shape and stable IDs.
    _validate_project_snapshot_version(
        migrated,
        version=SCHEMA_V12_VERSION,
        figure_validator=validate_v12_figure,
    )
    return migrated


def migrate_v12_to_v13(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate and migrate a schema-v12 tree to schema v13."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V12_VERSION,
        figure_validator=validate_v12_figure,
    )
    migrated = deepcopy(snapshot)
    migrated["schema_version"] = SCHEMA_V13_VERSION
    # Reference Guides are new v13 records. Existing v12 records retain their
    # exact eight-field wire shape, IDs, order, selectors, properties, and data.
    _validate_project_snapshot_version(
        migrated,
        version=SCHEMA_V13_VERSION,
        figure_validator=validate_v13_figure,
    )
    return migrated


def migrate_v13_to_v14(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strictly migrate Tick Label font families from schema v13 to v14."""

    _validate_project_snapshot_version(
        snapshot,
        version=SCHEMA_V13_VERSION,
        figure_validator=validate_v13_figure,
    )
    migrated = deepcopy(snapshot)
    for index, component in enumerate(migrated["figure"]["components"]):
        if component["kind"] != "tick_label_group":
            continue
        fontfamily = component["properties"]["fontfamily"]
        if isinstance(fontfamily, list):
            component["properties"]["fontfamily"] = fontfamily[0]
        elif not isinstance(fontfamily, str):
            # The predecessor validator normally catches this. Keep the
            # migration boundary explicit if its contract changes later.
            raise ValueError(
                "Invalid project field "
                f"figure.components[{index}].properties.fontfamily: "
                "expected string or non-empty string array."
            )
    migrated["schema_version"] = SCHEMA_V14_VERSION
    validate_v14_project_snapshot(migrated)
    return migrated


def migrate_v14_to_v15(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Add position_ref, placement, and y_lower_reserve defaults from schema v14 to v15."""

    validate_v14_project_snapshot(snapshot)
    migrated = deepcopy(snapshot)
    for component in migrated["figure"]["components"]:
        kind = component.get("kind")
        if kind == "reference_marks":
            data = component.setdefault("data", {})
            data.setdefault("position_ref", None)
            data.setdefault("placement", {"kind": "fixed"})
        elif kind == "axes":
            properties = component.setdefault("properties", {})
            properties.setdefault("y_lower_reserve", 0.0)
    migrated["schema_version"] = SCHEMA_V15_VERSION
    validate_v15_project_snapshot(migrated)
    return migrated


def migrate_v15_to_v16(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Promote a strictly valid schema-v15 tree to schema v16 without rewrite."""

    validate_v15_project_snapshot(snapshot)
    migrated = deepcopy(snapshot)
    migrated["schema_version"] = SCHEMA_V16_VERSION
    validate_v16_project_snapshot(migrated)
    return migrated


def migrate_v16_to_v17(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Promote a strictly valid schema-v16 tree to schema v17 without rewrite."""

    validate_v16_project_snapshot(snapshot)
    migrated = deepcopy(snapshot)
    migrated["schema_version"] = PROJECT_SCHEMA_VERSION
    validate_project_snapshot(migrated)
    return migrated


def project_snapshot(figure_window=None, *, canvas=None) -> dict[str, Any]:
    """Build the complete serializable project snapshot."""

    if figure_window is None:
        raise ValueError("No Figure window is available to save.")
    if canvas is None:
        canvas = getattr(figure_window, "current_canva", None)
    if canvas is None:
        raise ValueError("No current project canvas to save.")
    project = figure_window.repository.project(canvas.project_id)
    figure = normalize_v17_figure(canvas.component_snapshot())
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
    payload = _json_bytes(snapshot, pretty=True)
    if len(payload) > load_resource_limits().max_project_bytes:
        raise ValueError("Project exceeds the configured file-size budget.")
    fingerprint = project_fingerprint(snapshot)
    _atomic_write_bytes(path, payload)

    # The file is committed at this point. Runtime bookkeeping must never turn
    # a successful atomic replacement into a reported save failure.
    try:
        if canvas is not None:
            canvas.project_path = str(path)
        mark_clean = getattr(figure_window, "mark_canvas_clean", None)
        if callable(mark_clean) and canvas is not None:
            mark_clean(canvas, fingerprint=fingerprint)
    except Exception:
        LOGGER.exception("Project file was saved but clean-state bookkeeping failed")
    return snapshot


def load_project_file(filename: str | Path) -> dict[str, Any]:
    """Load project file."""

    path = Path(filename)
    limits = load_resource_limits()
    if not path.is_file():
        raise ValueError(f"Project file does not exist: {path}")
    if path.stat().st_size > limits.max_project_bytes:
        raise ValueError("Project file exceeds the configured file-size budget.")
    with path.open("r", encoding="utf-8-sig") as handle:
        snapshot = json.load(
            handle,
            parse_constant=_reject_json_constant,
        )
    validate_json_budget(snapshot, limits=limits)
    version = snapshot.get("schema_version") if isinstance(snapshot, dict) else None
    if type(version) is not int:
        raise ValueError(
            f"Unsupported project schema version {version!r}; schema versions "
            "must use exact integers."
        )
    if version == SCHEMA_V10_VERSION:
        return migrate_v16_to_v17(
            migrate_v15_to_v16(
                migrate_v14_to_v15(
                    migrate_v13_to_v14(
                        migrate_v12_to_v13(
                            migrate_v11_to_v12(migrate_v10_to_v11(snapshot))
                        )
                    )
                )
            )
        )
    if version == SCHEMA_V11_VERSION:
        return migrate_v16_to_v17(
            migrate_v15_to_v16(
                migrate_v14_to_v15(
                    migrate_v13_to_v14(
                        migrate_v12_to_v13(migrate_v11_to_v12(snapshot))
                    )
                )
            )
        )
    if version == SCHEMA_V12_VERSION:
        return migrate_v16_to_v17(
            migrate_v15_to_v16(
                migrate_v14_to_v15(
                    migrate_v13_to_v14(migrate_v12_to_v13(snapshot))
                )
            )
        )
    if version == SCHEMA_V13_VERSION:
        return migrate_v16_to_v17(
            migrate_v15_to_v16(migrate_v14_to_v15(migrate_v13_to_v14(snapshot)))
        )
    if version == SCHEMA_V14_VERSION:
        return migrate_v16_to_v17(migrate_v15_to_v16(migrate_v14_to_v15(snapshot)))
    if version == SCHEMA_V15_VERSION:
        return migrate_v16_to_v17(migrate_v15_to_v16(snapshot))
    if version == SCHEMA_V16_VERSION:
        return migrate_v16_to_v17(snapshot)
    if version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {version!r}; only schema "
            f"v{PROJECT_SCHEMA_VERSION}, strict v16 migration, strict v15 "
            "migration, strict v14 migration, strict v13 migration, and "
            "chained strict v10-v12 migration are supported."
        )
    validate_project_snapshot(snapshot)
    return snapshot


def restore_project_payload(
    snapshot: dict[str, Any],
    *,
    table=None,
    figure_window=None,
    project_path: str | Path | None = None,
    mark_clean: bool = False,
    before_figure_publish=None,
) -> dict[str, Any]:
    """Stage and publish one already decoded, strictly validated snapshot.

    File opening and template application share this transaction boundary so
    neither path can leave a Table, Canvas, Inspector, tree, or tab half
    published after a failure.
    """

    snapshot = deepcopy(snapshot)
    validate_project_snapshot(snapshot)
    project_meta = snapshot["project"]
    project_id = project_meta["id"]
    project_name = project_meta["name"]
    table_repository = getattr(table, "repository", None)
    figure_repository = getattr(figure_window, "repository", None)
    if (
        table_repository is not None
        and figure_repository is not None
        and table_repository is not figure_repository
    ):
        raise ValueError(
            "Project restore requires Table and Figure windows to share one "
            "TableRepository."
        )
    repository = table_repository or figure_repository
    if repository is None:
        raise ValueError("Project restore requires a TableRepository-backed window.")
    if project_id in repository.projects or repository.project_by_name(project_name, required=False) is not None:
        raise ValueError(f"Project already exists: {project_name}")

    previous_table_project_id = getattr(table, "current_project_id", None)
    previous_canvas = getattr(figure_window, "current_canva", None)
    canvas = None

    def discard_restore_messages() -> None:
        presenter = getattr(canvas, "message_presenter", None)
        discard = getattr(presenter, "discard_pending", None)
        if callable(discard):
            discard()

    try:
        if table is None:
            raise ValueError("Project restore requires the Table widget.")
        table.load_project_table_snapshot(snapshot["table"], publish=False)
        if figure_window is not None:
            figure_kwargs = {
                "project_path": (
                    str(Path(project_path)) if project_path is not None else None
                )
            }
            if before_figure_publish is not None:
                figure_kwargs["before_publish"] = before_figure_publish
            canvas = figure_window.load_project_figure_snapshot(
                snapshot["figure"],
                project_name,
                **figure_kwargs,
            )
            mark_clean_canvas = getattr(figure_window, "mark_canvas_clean", None)
            if mark_clean and callable(mark_clean_canvas) and canvas is not None:
                mark_clean_canvas(canvas)
        repository.publish_project_added(project_id)
        discard_restore_messages()
        return snapshot
    except Exception:
        discard_restore_messages()
        cleanup_errors = []
        if figure_window is not None:
            try:
                figure_window.remove_project_by_id(project_id)
            except Exception as cleanup_error:
                cleanup_errors.append(f"Figure cleanup: {cleanup_error}")
        if table is not None and project_id in repository.projects:
            try:
                table.remove_project_table(project_id, publish=False)
            except Exception as cleanup_error:
                cleanup_errors.append(f"Table cleanup: {cleanup_error}")
        try:
            if (
                previous_canvas is not None
                and previous_canvas.project_id in getattr(
                    figure_window,
                    "canvas",
                    {},
                )
            ):
                figure_window.tabwindow.setCurrentWidget(previous_canvas)
                figure_window.change_current_canvas()
            elif (
                previous_table_project_id is not None
                and previous_table_project_id in repository.projects
            ):
                table.switch_to_table(previous_table_project_id)
        except Exception as cleanup_error:
            cleanup_errors.append(f"Selection restore: {cleanup_error}")
        if cleanup_errors:
            LOGGER.error(
                "Project restore rollback was incomplete: %s",
                "; ".join(cleanup_errors),
            )
        raise


def restore_project_snapshot(filename: str | Path, table=None, figure_window=None) -> dict[str, Any]:
    """Load and restore one project file through the shared publish boundary."""

    path = Path(filename)
    snapshot = load_project_file(path)
    return restore_project_payload(
        snapshot,
        table=table,
        figure_window=figure_window,
        project_path=path,
        mark_clean=True,
    )
