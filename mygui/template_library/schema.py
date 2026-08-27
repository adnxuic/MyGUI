"""Strict schema-v1 parsing and validation for MyGUI chart templates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any
from uuid import UUID

from mygui.database import ColumnRef, ColumnType, validate_component_name
from mygui.figuremodify.components.serialization import validate_v16_figure
from mygui.resource_limits import load_resource_limits, validate_json_budget

from .models import (
    ChartTemplate,
    TemplateColumnSlot,
    TemplateDataContract,
    TemplateMetadata,
    TemplateSheetSlot,
)


TEMPLATE_SCHEMA_NAME = "mygui-template"
TEMPLATE_SCHEMA_VERSION = 1
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


def template_to_dict(template: ChartTemplate) -> dict[str, Any]:
    """Return the strict JSON wire representation for one template."""

    return {
        "schema": TEMPLATE_SCHEMA_NAME,
        "schema_version": TEMPLATE_SCHEMA_VERSION,
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


def parse_template(value: Any) -> ChartTemplate:
    """Parse and strictly validate a schema-v1 template object."""

    validate_json_budget(value, limits=load_resource_limits())
    root = _expect_dict(value, "template")
    _exact(root, {"schema", "schema_version", "metadata", "data_contract", "figure"}, "template")
    if _expect_string(root.get("schema"), "schema") != TEMPLATE_SCHEMA_NAME:
        raise ValueError("Unsupported template file.")
    version = root.get("schema_version")
    if type(version) is not int or version != TEMPLATE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported template schema version {version!r}; expected exact integer 1."
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
    validate_v16_figure(figure, refs, TEMPLATE_PROJECT_ID, None)
    _validate_tokens(figure, allowed_tokens(contract), "figure")
    return ChartTemplate(metadata, contract, figure)


def validate_template(template: ChartTemplate) -> None:
    """Validate one in-memory template model through its exact wire schema."""

    parse_template(template_to_dict(template))
