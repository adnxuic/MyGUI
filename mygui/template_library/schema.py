"""Strict schema-v2 parsing, v1 migration, and validation for chart templates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any
from uuid import UUID

from mygui.database import ColumnRef, ColumnType, validate_component_name
from mygui.figuremodify.axes_geometry import grid_geometry_record
from mygui.figuremodify.components.serialization import (
    validate_v17_figure,
    validate_v18_figure,
    validate_v19_figure,
    validate_v20_figure,
    validate_v21_figure,
    validate_v22_figure,
)
from mygui.resource_limits import load_resource_limits, validate_json_budget

from .models import (
    ChartTemplate,
    TemplateColumnSlot,
    TemplateDataContract,
    TemplateMetadata,
    TemplateSheetSlot,
)


TEMPLATE_SCHEMA_NAME = "mygui-template"
TEMPLATE_SCHEMA_VERSION = 6
TEMPLATE_SCHEMA_V5_VERSION = 5
TEMPLATE_SCHEMA_V2_VERSION = 2
TEMPLATE_SCHEMA_V3_VERSION = 3
TEMPLATE_SCHEMA_V4_VERSION = 4
TEMPLATE_SCHEMA_V1_VERSION = 1
TEMPLATE_MATCH_ALGORITHM_VERSION = 1
TEMPLATE_PROJECT_ID = "template-project"
TEMPLATE_FILE_SUFFIX = ".mygui-template.json"
MAX_TEMPLATE_NAME_LENGTH = 80
MAX_TEMPLATE_NOTES_LENGTH = 2000

_TOKEN_RE = re.compile(r"\{\{([a-z0-9_.-]+)\}\}")


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid template field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid template field {path}: expected array.")
    return value


def _expect_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid template field {path}: expected string.")
    return value


def _exact(value: dict[str, Any], keys: set[str], path: str) -> None:
    if set(value) != keys:
        raise ValueError(
            f"Invalid template field {path}: expected exactly {sorted(keys)}, "
            f"got {sorted(value)}."
        )


def _uuid(value: Any, path: str) -> str:
    text = _expect_string(value, path).strip()
    try:
        parsed = UUID(text)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid template field {path}: expected UUID.") from exc
    if str(parsed) != text.casefold():
        raise ValueError(f"Invalid template field {path}: expected canonical UUID.")
    return text


def _timestamp(value: Any, path: str) -> str:
    text = _expect_string(value, path).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Invalid template field {path}: expected ISO date/time."
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Invalid template field {path}: timezone is required.")
    return text


def validate_template_name(value: Any) -> str:
    """Return one normalized valid template display name."""

    name = validate_component_name(_expect_string(value, "metadata.name"), "Template name")
    if len(name) > MAX_TEMPLATE_NAME_LENGTH:
        raise ValueError(
            f"Template name must contain at most {MAX_TEMPLATE_NAME_LENGTH} characters."
        )
    return name


def allowed_tokens(contract: TemplateDataContract) -> frozenset[str]:
    """Return the complete closed variable vocabulary for one contract."""

    tokens = {"project_name", "source_file_name", "source_file_stem"}
    for sheet in contract.sheets:
        tokens.add(f"sheet.{sheet.id}.name")
        for column in sheet.columns:
            tokens.add(f"column.{column.id}.name")
    return frozenset(tokens)


def _validate_tokens(value: Any, allowed: frozenset[str], path: str) -> None:
    if isinstance(value, str):
        found = set(_TOKEN_RE.findall(value))
        unknown = found - allowed
        remainder = _TOKEN_RE.sub("", value)
        if unknown:
            raise ValueError(
                f"Invalid template field {path}: unknown variables {sorted(unknown)}."
            )
        if "{{" in remainder or "}}" in remainder:
            raise ValueError(f"Invalid template field {path}: malformed variable.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_tokens(item, allowed, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_tokens(item, allowed, f"{path}[{index}]")


def _parse_contract(value: Any) -> TemplateDataContract:
    raw = _expect_dict(value, "data_contract")
    _exact(raw, {"algorithm_version", "allow_extra_columns", "sheets"}, "data_contract")
    version = raw.get("algorithm_version")
    if type(version) is not int or version != TEMPLATE_MATCH_ALGORITHM_VERSION:
        raise ValueError(
            "Unsupported template matching algorithm version "
            f"{version!r}; expected exact integer 1."
        )
    allow_extra = raw.get("allow_extra_columns")
    if type(allow_extra) is not bool or not allow_extra:
        raise ValueError("Template data_contract.allow_extra_columns must be true.")
    sheet_values = _expect_list(raw.get("sheets"), "data_contract.sheets")
    sheets: list[TemplateSheetSlot] = []
    ids: set[str] = set()
    for sheet_index, sheet_value in enumerate(sheet_values):
        path = f"data_contract.sheets[{sheet_index}]"
        record = _expect_dict(sheet_value, path)
        _exact(record, {"id", "name", "columns"}, path)
        sheet_id = _uuid(record.get("id"), f"{path}.id")
        if sheet_id in ids:
            raise ValueError(f"Duplicate template slot id: {sheet_id}")
        ids.add(sheet_id)
        sheet_name = validate_component_name(
            _expect_string(record.get("name"), f"{path}.name"),
            "Logical Sheet name",
        )
        columns: list[TemplateColumnSlot] = []
        column_names: set[str] = set()
        for column_index, column_value in enumerate(
            _expect_list(record.get("columns"), f"{path}.columns")
        ):
            column_path = f"{path}.columns[{column_index}]"
            column_record = _expect_dict(column_value, column_path)
            _exact(column_record, {"id", "name", "type"}, column_path)
            column_id = _uuid(column_record.get("id"), f"{column_path}.id")
            if column_id in ids:
                raise ValueError(f"Duplicate template slot id: {column_id}")
            ids.add(column_id)
            column_name = _expect_string(
                column_record.get("name"), f"{column_path}.name"
            ).strip()
            if not column_name:
                raise ValueError("Logical column name must not be empty.")
            folded = column_name.casefold()
            if folded in column_names:
                raise ValueError(
                    f"Duplicate logical column name in {sheet_name}: {column_name}"
                )
            column_names.add(folded)
            try:
                column_type = ColumnType(
                    _expect_string(column_record.get("type"), f"{column_path}.type")
                )
            except ValueError as exc:
                raise ValueError(
                    f"Invalid template field {column_path}.type."
                ) from exc
            if column_type is ColumnType.AUTO:
                raise ValueError("Template columns must have a resolved type.")
            columns.append(TemplateColumnSlot(column_id, column_name, column_type))
        if not columns:
            raise ValueError(f"Template Sheet slot {sheet_name!r} has no required columns.")
        sheets.append(TemplateSheetSlot(sheet_id, sheet_name, tuple(columns)))
    return TemplateDataContract(version, allow_extra, tuple(sheets))


def _template_to_dict_version(
    template: ChartTemplate, *, version: int
) -> dict[str, Any]:
    """Return one exact template wire version from the in-memory model."""

    return {
        "schema": TEMPLATE_SCHEMA_NAME,
        "schema_version": version,
        "metadata": {
            "id": template.metadata.id,
            "name": template.metadata.name,
            "notes": template.metadata.notes,
            "created_at": template.metadata.created_at,
            "updated_at": template.metadata.updated_at,
        },
        "data_contract": {
            "algorithm_version": template.data_contract.algorithm_version,
            "allow_extra_columns": template.data_contract.allow_extra_columns,
            "sheets": [
                {
                    "id": sheet.id,
                    "name": sheet.name,
                    "columns": [
                        {"id": column.id, "name": column.name, "type": column.type.value}
                        for column in sheet.columns
                    ],
                }
                for sheet in template.data_contract.sheets
            ],
        },
        "figure": deepcopy(template.figure),
    }


def template_to_dict(template: ChartTemplate) -> dict[str, Any]:
    """Return the strict current JSON wire representation for one template."""

    return _template_to_dict_version(template, version=TEMPLATE_SCHEMA_VERSION)


def _parse_template_payload(
    value: Any,
    *,
    version: int,
    figure_validator,
) -> ChartTemplate:
    """Parse one template payload at one exact version and figure schema."""

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    actual_version = root.get("schema_version")
    if type(actual_version) is not int or actual_version != version:
        raise ValueError(
            f"Unsupported template schema version {actual_version!r}; expected exact "
            f"integer {version}."
        )
    metadata_value = _expect_dict(root.get("metadata"), "metadata")
    _exact(metadata_value, {"id", "name", "notes", "created_at", "updated_at"}, "metadata")
    template_id = _uuid(metadata_value.get("id"), "metadata.id")
    name = validate_template_name(metadata_value.get("name"))
    notes = _expect_string(metadata_value.get("notes"), "metadata.notes")
    if len(notes) > MAX_TEMPLATE_NOTES_LENGTH:
        raise ValueError(
            f"Template notes must contain at most {MAX_TEMPLATE_NOTES_LENGTH} characters."
        )
    metadata = TemplateMetadata(
        template_id,
        name,
        notes,
        _timestamp(metadata_value.get("created_at"), "metadata.created_at"),
        _timestamp(metadata_value.get("updated_at"), "metadata.updated_at"),
    )
    contract = _parse_contract(root.get("data_contract"))
    refs = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column.type
        for sheet in contract.sheets
        for column in sheet.columns
    }
    figure = deepcopy(_expect_dict(root.get("figure"), "figure"))
    figure_validator(figure, refs, TEMPLATE_PROJECT_ID, None)
    _validate_tokens(figure, allowed_tokens(contract), "figure")
    return ChartTemplate(metadata, contract, figure)


def parse_template(value: Any) -> ChartTemplate:
    """Parse and strictly validate a schema-v6 template object."""

    return _parse_template_payload(
        value,
        version=TEMPLATE_SCHEMA_VERSION,
        figure_validator=validate_v22_figure,
    )


def migrate_v1_template_to_v2(value: Any) -> dict[str, Any]:
    """Strictly read a schema-v1 template and upgrade it to schema v2 dict."""

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    version = root.get("schema_version")
    if type(version) is not int or version != TEMPLATE_SCHEMA_V1_VERSION:
        raise ValueError(
            f"Unsupported template schema version {version!r}; expected exact "
            f"integer {TEMPLATE_SCHEMA_V1_VERSION}."
        )
    contract = _parse_contract(root.get("data_contract"))
    refs = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column.type
        for sheet in contract.sheets
        for column in sheet.columns
    }
    figure = deepcopy(_expect_dict(root.get("figure"), "figure"))
    validate_v17_figure(figure, refs, TEMPLATE_PROJECT_ID, None)
    migrated = deepcopy(value)
    for component in migrated["figure"]["components"]:
        if (
            component.get("kind") == "line"
            and component.get("role") == "fit_curve"
        ):
            component.setdefault("data", {}).setdefault(
                "fit_input_range", {"kind": "all"}
            )
    migrated["schema_version"] = TEMPLATE_SCHEMA_V2_VERSION
    migrated_figure = deepcopy(_expect_dict(migrated.get("figure"), "figure"))
    validate_v18_figure(migrated_figure, refs, TEMPLATE_PROJECT_ID, None)
    return migrated


def migrate_v2_template_to_v3(value: Any) -> dict[str, Any]:
    """Strictly read a schema-v2 template and upgrade it to a schema-v3 dict."""

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    version = root.get("schema_version")
    if type(version) is not int or version != TEMPLATE_SCHEMA_V2_VERSION:
        raise ValueError(
            f"Unsupported template schema version {version!r}; expected exact "
            f"integer {TEMPLATE_SCHEMA_V2_VERSION}."
        )
    contract = _parse_contract(root.get("data_contract"))
    refs = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column.type
        for sheet in contract.sheets
        for column in sheet.columns
    }
    figure = deepcopy(_expect_dict(root.get("figure"), "figure"))
    validate_v18_figure(figure, refs, TEMPLATE_PROJECT_ID, None)
    migrated = deepcopy(value)
    for component in migrated["figure"]["components"]:
        if component.get("kind") == "axes":
            component.setdefault("data", {})["geometry"] = grid_geometry_record()
            component.setdefault("properties", {}).pop("in_layout", None)
    migrated["schema_version"] = TEMPLATE_SCHEMA_V3_VERSION
    _parse_template_payload(
        migrated,
        version=TEMPLATE_SCHEMA_V3_VERSION,
        figure_validator=validate_v19_figure,
    )
    return migrated


def migrate_v3_template_to_v4(value: Any) -> dict[str, Any]:
    """Strictly read a schema-v3 template and upgrade it to a schema-v4 dict.

    v3 blueprints are full schema-v19 figures and therefore cannot contain
    Error Bar records; the migration only advances the version and revalidates
    the identical component tree against schema v20.
    """

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    version = root.get("schema_version")
    if type(version) is not int or version != TEMPLATE_SCHEMA_V3_VERSION:
        raise ValueError(
            f"Unsupported template schema version {version!r}; expected exact "
            f"integer {TEMPLATE_SCHEMA_V3_VERSION}."
        )
    contract = _parse_contract(root.get("data_contract"))
    refs = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column.type
        for sheet in contract.sheets
        for column in sheet.columns
    }
    figure = deepcopy(_expect_dict(root.get("figure"), "figure"))
    validate_v19_figure(figure, refs, TEMPLATE_PROJECT_ID, None)
    migrated = deepcopy(value)
    migrated["schema_version"] = TEMPLATE_SCHEMA_V4_VERSION
    _parse_template_payload(
        migrated,
        version=TEMPLATE_SCHEMA_V4_VERSION,
        figure_validator=validate_v20_figure,
    )
    return migrated


ERROR_BAR_TEMPLATE_V5_DEFAULTS: dict[str, Any] = {
    "markeredgewidth": 1.0,
    "markerfacecoloralt": "none",
    "fillstyle": "full",
    "drawstyle": "default",
    "antialiased": True,
    "error_linestyle": {"kind": "preset", "value": "-"},
    "error_capstyle": None,
    "error_antialiased": True,
    "errorevery": {"kind": "all"},
    "lolims": False,
    "uplims": False,
    "xlolims": False,
    "xuplims": False,
}


def migrate_v4_template_to_v5(value: Any) -> ChartTemplate:
    """Strictly read a schema-v4 template and upgrade it to schema v5.

    v4 blueprints are full schema-v20 figures whose Error Bar records carry
    exactly the v20 property set; the migration injects the deterministic
    v21 defaults and revalidates against the extended schema-v21 figure.
    """

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    version = root.get("schema_version")
    if type(version) is not int or version != TEMPLATE_SCHEMA_V4_VERSION:
        raise ValueError(
            f"Unsupported template schema version {version!r}; expected exact "
            f"integer {TEMPLATE_SCHEMA_V4_VERSION}."
        )
    contract = _parse_contract(root.get("data_contract"))
    refs = {
        ColumnRef(TEMPLATE_PROJECT_ID, sheet.id, column.id): column.type
        for sheet in contract.sheets
        for column in sheet.columns
    }
    figure = deepcopy(_expect_dict(root.get("figure"), "figure"))
    validate_v20_figure(figure, refs, TEMPLATE_PROJECT_ID, None)
    migrated = deepcopy(value)
    for component in migrated["figure"]["components"]:
        if (
            component.get("kind") == "errorbar"
            and component.get("role") == "error_bar"
        ):
            properties = component.setdefault("properties", {})
            properties.update(deepcopy(ERROR_BAR_TEMPLATE_V5_DEFAULTS))
    migrated["schema_version"] = TEMPLATE_SCHEMA_V5_VERSION
    return _parse_template_payload(
        migrated,
        version=TEMPLATE_SCHEMA_V5_VERSION,
        figure_validator=validate_v21_figure,
    )


def migrate_v5_template_to_v6(value: Any) -> ChartTemplate:
    """Promote a strict schema-v5 template without changing Figure content."""

    parsed = _parse_template_payload(
        value,
        version=TEMPLATE_SCHEMA_V5_VERSION,
        figure_validator=validate_v21_figure,
    )
    migrated = _template_to_dict_version(
        parsed,
        version=TEMPLATE_SCHEMA_VERSION,
    )
    return parse_template(migrated)


def _finish_v5_migration(template: ChartTemplate) -> ChartTemplate:
    return migrate_v5_template_to_v6(
        _template_to_dict_version(
            template,
            version=TEMPLATE_SCHEMA_V5_VERSION,
        )
    )


def parse_template_record(value: Any) -> ChartTemplate:
    """Parse one stored record, migrating strict older templates to v6."""

    if (
        isinstance(value, dict)
        and value.get("schema") == TEMPLATE_SCHEMA_NAME
        and type(value.get("schema_version")) is int
    ):
        if value["schema_version"] == TEMPLATE_SCHEMA_V1_VERSION:
            return _finish_v5_migration(
                migrate_v4_template_to_v5(
                    migrate_v3_template_to_v4(
                        migrate_v2_template_to_v3(
                            migrate_v1_template_to_v2(value)
                        )
                    )
                )
            )
        if value["schema_version"] == TEMPLATE_SCHEMA_V2_VERSION:
            return _finish_v5_migration(
                migrate_v4_template_to_v5(
                    migrate_v3_template_to_v4(migrate_v2_template_to_v3(value))
                )
            )
        if value["schema_version"] == TEMPLATE_SCHEMA_V3_VERSION:
            return _finish_v5_migration(
                migrate_v4_template_to_v5(migrate_v3_template_to_v4(value))
            )
        if value["schema_version"] == TEMPLATE_SCHEMA_V4_VERSION:
            return _finish_v5_migration(migrate_v4_template_to_v5(value))
        if value["schema_version"] == TEMPLATE_SCHEMA_V5_VERSION:
            return migrate_v5_template_to_v6(value)
    return parse_template(value)


def validate_template(template: ChartTemplate) -> None:
    """Validate one in-memory template model through its exact wire schema."""

    parse_template(template_to_dict(template))
