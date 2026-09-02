"""Normalize and validate strict schema-v10 through v23 Figure trees."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from mygui.database import ColumnRef, ColumnType
from mygui.figuremodify.style_base.color_models import normalize_color

from . import figure_schema_validators as _schema_validators
from .schema_policy import (
    COLOR_PROPERTIES as _COLOR_PROPERTIES,
    CURRENT_FIGURE_SCHEMA_VERSION,
    FigureSchemaPolicy,
    figure_schema_policy,
)

_PARENT_KINDS = _schema_validators._PARENT_KINDS
_SELECTOR_VALIDATORS = _schema_validators._SELECTOR_VALIDATORS
_expect_dict = _schema_validators._expect_dict
_expect_list = _schema_validators._expect_list
_validate_axes_selector = _schema_validators._validate_axes_selector
_validate_axis_selector = _schema_validators._validate_axis_selector
_validate_tick_or_grid_selector = _schema_validators._validate_tick_or_grid_selector
_validate_axis_label_selector = _schema_validators._validate_axis_label_selector
_validate_spine_selector = _schema_validators._validate_spine_selector
_validate_object_id_selector = _schema_validators._validate_object_id_selector
_validate_annotation_selector = _schema_validators._validate_annotation_selector
_validate_controller_contract = _schema_validators._validate_controller_contract
_validate_data_references = _schema_validators._validate_data_references
_validate_figure = _schema_validators._validate_figure
_validate_layouts = _schema_validators._validate_layouts
_validate_parent = _schema_validators._validate_parent


def deterministic_component_id(project_id: str, component_path: str) -> str:
    """Build a stable component ID from a project and semantic path."""

    project_key = str(project_id).strip()
    path_key = str(component_path).strip().replace("\\", "/")
    if not project_key:
        raise ValueError("Project id must not be empty.")
    if not path_key:
        raise ValueError("Component path must not be empty.")
    return str(uuid5(NAMESPACE_URL, f"mygui-project:{project_key}:{path_key}"))


def _canonical_json_value(value: Any, path: str) -> Any:
    if isinstance(value, (tuple, list)):
        return [
            _canonical_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(
                f"Invalid project field {path}: object keys must be strings."
            )
        return {
            key: _canonical_json_value(item, f"{path}.{key}")
            for key, item in value.items()
        }
    return deepcopy(value)


def _normalize_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-friendly copy of one component-tree wire record."""

    figure = deepcopy(_expect_dict(figure_snapshot, "figure"))
    components = _expect_list(figure.get("components"), "figure.components")
    for index, raw in enumerate(components):
        component = _expect_dict(raw, f"figure.components[{index}]")
        for field in ("selector", "properties", "data"):
            component[field] = _canonical_json_value(
                component.get(field),
                f"figure.components[{index}].{field}",
            )
        properties = _expect_dict(
            component["properties"],
            f"figure.components[{index}].properties",
        )
        for name in _COLOR_PROPERTIES.intersection(properties):
            if properties[name] is None or isinstance(properties[name], dict):
                continue
            try:
                properties[name] = normalize_color(properties[name])
            except ValueError as exc:
                raise ValueError(
                    "Invalid project field "
                    f"figure.components[{index}].properties.{name}."
                ) from exc
    return figure


def normalize_v10_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a strict schema-v10 Figure tree before migration."""

    return _normalize_figure(figure_snapshot)


def normalize_v11_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a strict schema-v11 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v12_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a strict schema-v12 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v13_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a predecessor schema-v13 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v14_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a predecessor schema-v14 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v15_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a predecessor schema-v15 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v16_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a predecessor schema-v16 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v17_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v17 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v18_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v18 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v19_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v19 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v20_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v20 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v21_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v21 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v22_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the predecessor schema-v22 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_v23_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize the current schema-v23 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def normalize_current_figure(
    figure_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the current Figure component tree without version coupling."""

    return normalize_v23_figure(figure_snapshot)


def validate_v10_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Strictly validate a schema-v10 Figure before migration."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=10,
    )


def validate_v11_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v11 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=11,
    )


def validate_v12_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v12 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=12,
    )


def validate_v13_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v13 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=13,
    )


def validate_v14_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v14 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=14,
    )


def validate_v15_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v15 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=15,
    )


def validate_v16_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v16 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=16,
    )


def validate_v17_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v17 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=17,
    )


def validate_v18_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v18 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=18,
    )


def validate_v19_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v19 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=19,
    )


def validate_v20_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v20 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=20,
    )


def validate_v21_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v21 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=21,
    )


def validate_v22_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one predecessor schema-v22 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=22,
    )


def validate_v23_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate one current schema-v23 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=23,
    )


def validate_current_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    """Validate the current Figure component tree without version coupling."""

    validate_v23_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
    )


__all__ = [
    "CURRENT_FIGURE_SCHEMA_VERSION",
    "FigureSchemaPolicy",
    "deterministic_component_id",
    "figure_schema_policy",
    "normalize_current_figure",
    "normalize_v10_figure",
    "normalize_v11_figure",
    "normalize_v12_figure",
    "normalize_v13_figure",
    "normalize_v14_figure",
    "normalize_v15_figure",
    "normalize_v16_figure",
    "normalize_v17_figure",
    "normalize_v18_figure",
    "normalize_v19_figure",
    "normalize_v20_figure",
    "normalize_v21_figure",
    "normalize_v22_figure",
    "normalize_v23_figure",
    "validate_current_figure",
    "validate_v10_figure",
    "validate_v11_figure",
    "validate_v12_figure",
    "validate_v13_figure",
    "validate_v14_figure",
    "validate_v15_figure",
    "validate_v16_figure",
    "validate_v17_figure",
    "validate_v18_figure",
    "validate_v19_figure",
    "validate_v20_figure",
    "validate_v21_figure",
    "validate_v22_figure",
    "validate_v23_figure",
]
