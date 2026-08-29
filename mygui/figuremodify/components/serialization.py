"""Normalize and validate strict schema-v10 through v21 Figure trees."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from mygui.database import ColumnRef, ColumnType, DataPreprocessSpec
from mygui.figuremodify.style_base.color_models import normalize_color

from .controllers import (
    ERROR_BAR_V20_PROPERTY_KEYS,
    ERROR_BAR_V21_DEFAULTS,
    controller_type_for,
    decode_in_axes_image,
)
from .errors import ComponentValidationError
from .models import ComponentKind, ComponentRole, ComponentState


_CHART_KINDS = frozenset(
    {
        ComponentKind.LINE,
        ComponentKind.SCATTER,
        ComponentKind.ERRORBAR,
        ComponentKind.FIELD_2D,
    }
)
_DATA_ROLES = frozenset(
    {
        ComponentRole.DATA_PLOT,
        ComponentRole.FIT_CURVE,
        ComponentRole.INTERPOLATION,
        ComponentRole.SCATTER,
        ComponentRole.ERROR_BAR,
    }
)
_SPINE_NAMES = frozenset({"left", "right", "bottom", "top"})
_LEVELS = frozenset({"major", "minor"})
_COLOR_PROPERTIES = frozenset(
    {
        "color",
        "facecolor",
        "edgecolor",
        "markerfacecolor",
        "markeredgecolor",
        "gapcolor",
        "region_color",
        "region_facecolor",
        "outline_color",
    }
)


def deterministic_component_id(project_id: str, component_path: str) -> str:
    """Build a stable component ID from a project and semantic path."""

    project_key = str(project_id).strip()
    path_key = str(component_path).strip().replace("\\", "/")
    if not project_key:
        raise ValueError("Project id must not be empty.")
    if not path_key:
        raise ValueError("Component path must not be empty.")
    return str(uuid5(NAMESPACE_URL, f"mygui-project:{project_key}:{path_key}"))


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected array.")
    return value


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
    """Normalize the current schema-v21 Figure component tree."""

    return _normalize_figure(figure_snapshot)


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Invalid project field {path}: expected finite number.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(
                f"Invalid project field {path}: object keys must be strings."
            )
        for key, item in value.items():
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(
        f"Invalid project field {path}: unsupported JSON value "
        f"{type(value).__name__}."
    )


def _state_from_raw(raw: Any, path: str) -> ComponentState:
    record = _expect_dict(raw, path)
    try:
        state = ComponentState.from_dict(record)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: {exc}") from exc
    _validate_json_value(state.selector, f"{path}.selector")
    _validate_json_value(state.properties, f"{path}.properties")
    _validate_json_value(state.data, f"{path}.data")
    return state


def _validate_controller_contract(
    state: ComponentState,
    path: str,
    *,
    schema_version: int,
) -> None:
    if (
        state.kind is ComponentKind.LINE
        and state.role is ComponentRole.LINE
    ):
        x_values = _expect_list(state.data.get("x"), f"{path}.data.x")
        y_values = _expect_list(state.data.get("y"), f"{path}.data.y")
        if set(state.data) != {"x", "y"}:
            raise ValueError(
                f"Invalid project field {path}.data: expected only x and y."
            )
        if len(x_values) != len(y_values):
            raise ValueError(
                f"Invalid project field {path}.data: x and y must have equal length."
            )
        for index, value in enumerate(y_values):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"Invalid project field {path}.data.y[{index}]: "
                    "expected number."
                )
    if state.kind is ComponentKind.LINE and state.role is ComponentRole.FIT_CURVE:
        has_input_range = "fit_input_range" in state.data
        if schema_version >= 18 and not has_input_range:
            raise ComponentValidationError(
                "Schema v18 Fit Curve data requires fit_input_range."
            )
        if schema_version < 18 and has_input_range:
            raise ComponentValidationError(
                f"Fit Curve data must not contain fit_input_range before "
                f"schema v18; schema v{schema_version} rejected it."
            )
    if state.kind is ComponentKind.AXES:
        has_geometry = "geometry" in state.data
        if schema_version >= 19 and not has_geometry:
            raise ComponentValidationError(
                "Schema v19 Axes data requires geometry."
            )
        if schema_version < 19 and has_geometry:
            raise ComponentValidationError(
                f"Axes data must not contain geometry before "
                f"schema v19; schema v{schema_version} rejected it."
            )
    if state.kind is ComponentKind.TICK_LABEL_GROUP:
        font_path = f"{path}.properties.fontfamily"
        fontfamily = state.properties.get("fontfamily")
        if schema_version >= 14:
            if not isinstance(fontfamily, str) or not fontfamily.strip():
                raise ValueError(
                    f"Invalid project field {font_path}: expected non-empty string."
                )
        elif isinstance(fontfamily, str):
            if not fontfamily.strip():
                raise ValueError(
                    f"Invalid project field {font_path}: expected non-empty string."
                )
        elif isinstance(fontfamily, list):
            if not fontfamily:
                raise ValueError(
                    f"Invalid project field {font_path}: font list must not be empty."
                )
            for index, item in enumerate(fontfamily):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        "Invalid project field "
                        f"{font_path}[{index}]: expected non-empty string."
                    )
        else:
            raise ValueError(
                f"Invalid project field {font_path}: expected string or string array."
            )
    try:
        for key in _COLOR_PROPERTIES.intersection(state.properties):
            value = state.properties[key]
            if value is None or isinstance(value, dict):
                continue
            try:
                normalize_color(value)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid project field {path}.properties.{key}."
                ) from exc
        controller_type = controller_type_for(state)
        expected = {
            key
            for key, spec in controller_type.property_specs().items()
            if spec.persistent
        }
        candidate = state
        if state.kind is ComponentKind.AXES and schema_version < 19:
            expected.add("in_layout")
            candidate = state.clone(
                properties={
                    key: value
                    for key, value in state.properties.items()
                    if key != "in_layout"
                }
            )
        if schema_version < 15:
            if state.kind is ComponentKind.AXES:
                expected.discard("y_lower_reserve")
                if "y_lower_reserve" not in state.properties:
                    candidate = candidate.clone(
                        properties={
                            **candidate.properties,
                            "y_lower_reserve": 0.0,
                        }
                    )
            if state.kind is ComponentKind.REFERENCE_MARKS:
                if set(state.data) != {"positions"}:
                    raise ComponentValidationError(
                        "Reference Marks data requires only positions."
                    )
                candidate = candidate.clone(
                    data={
                        **candidate.data,
                        "position_ref": None,
                        "placement": {"kind": "fixed"},
                    }
                )
        elif state.kind is ComponentKind.REFERENCE_MARKS:
            if set(state.data) != {"positions", "position_ref", "placement"}:
                raise ComponentValidationError(
                    "Reference Marks data requires positions, position_ref, "
                    "and placement."
                )
        if (
            state.kind is ComponentKind.ERRORBAR
            and schema_version < 21
        ):
            # Schema v20 pins the exact predecessor Error Bar property set;
            # the live Controller contract already owns the extended v21 set,
            # so the migration defaults below must come from the recorded
            # constant, not from the Controller.
            if set(state.properties) != ERROR_BAR_V20_PROPERTY_KEYS:
                raise ComponentValidationError(
                    "Schema v20 Error Bar properties must be exactly "
                    f"{sorted(ERROR_BAR_V20_PROPERTY_KEYS)!r}."
                )
            state = state.clone(
                properties={
                    **state.properties,
                    **deepcopy(ERROR_BAR_V21_DEFAULTS),
                }
            )
            candidate = state
        actual = set(state.properties)
        if actual != expected:
            details = []
            if expected - actual:
                details.append(f"missing {sorted(expected - actual)!r}")
            if actual - expected:
                details.append(f"unknown {sorted(actual - expected)!r}")
            raise ComponentValidationError(
                "property keys are invalid: " + ", ".join(details)
            )
        for key, spec in controller_type.property_specs().items():
            if not spec.persistent or key not in candidate.properties:
                continue
            expected_types = (
                spec.value_type
                if isinstance(spec.value_type, tuple)
                else (spec.value_type,)
            )
            value = candidate.properties[key]
            if (
                dict in expected_types
                and value is not None
                and not isinstance(value, dict)
            ):
                raise ComponentValidationError(
                    f"property {key!r} must use its tagged JSON object form"
                )
        controller_type(candidate)
        if state.role is ComponentRole.IN_AXES_IMAGE:
            decode_in_axes_image(state.data)
    except (ComponentValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: {exc}") from exc


def _validate_parent(
    state: ComponentState,
    parent: ComponentState | None,
    path: str,
) -> None:
    if state.kind is ComponentKind.FIGURE:
        if parent is not None or state.selector != {"scope": "figure"}:
            raise ValueError(f"Invalid Figure root at {path}.")
        return
    if parent is None:
        raise ValueError(f"Missing parent component at {path}.parent_id.")

    parent_kind = parent.kind
    if state.kind is ComponentKind.AXES:
        valid = parent_kind is ComponentKind.FIGURE
    elif state.kind in {
        ComponentKind.AXIS,
        ComponentKind.SPINE,
        ComponentKind.LEGEND,
        ComponentKind.ANNOTATION,
        ComponentKind.COLORBAR,
        ComponentKind.REFERENCE_MARKS,
        ComponentKind.REFERENCE_GUIDE,
    }:
        valid = parent_kind is ComponentKind.AXES
    elif state.kind is ComponentKind.TICK_GROUP:
        valid = parent_kind is ComponentKind.AXIS
    elif state.kind is ComponentKind.TICK_LABEL_GROUP:
        valid = parent_kind is ComponentKind.TICK_GROUP
    elif state.kind is ComponentKind.GRID:
        valid = parent_kind is ComponentKind.AXIS
    elif state.kind in _CHART_KINDS | {ComponentKind.IN_AXES}:
        valid = parent_kind is ComponentKind.AXES
    elif state.role is ComponentRole.TITLE:
        valid = parent_kind is ComponentKind.AXES
    elif state.role in {ComponentRole.X_LABEL, ComponentRole.Y_LABEL}:
        valid = parent_kind is ComponentKind.AXIS
    else:
        valid = parent_kind in {ComponentKind.FIGURE, ComponentKind.AXES}
    if not valid:
        raise ValueError(
            f"Invalid parent kind {parent_kind.value!r} for "
            f"{state.kind.value}/{state.role.value} at {path}."
        )

    selector = state.selector
    if state.kind is ComponentKind.AXES:
        index = selector.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(f"Invalid Axes selector at {path}.selector.")
    if state.kind is ComponentKind.AXIS:
        expected = "x" if state.role is ComponentRole.X_AXIS else "y"
        if selector.get("axis") != expected:
            raise ValueError(f"Invalid Axis selector at {path}.selector.")
    if state.kind in {
        ComponentKind.TICK_GROUP,
        ComponentKind.TICK_LABEL_GROUP,
        ComponentKind.GRID,
    }:
        axis_name = selector.get("axis")
        level = selector.get("level")
        if axis_name not in {"x", "y"} or level not in _LEVELS:
            raise ValueError(f"Invalid tick/grid selector at {path}.selector.")
        if parent.selector.get("axis") != axis_name:
            raise ValueError(f"Mismatched Axis selector at {path}.selector.")
        if state.kind is ComponentKind.TICK_LABEL_GROUP:
            if parent.selector.get("level") != level:
                raise ValueError(f"Mismatched tick level at {path}.selector.")
        if state.kind is ComponentKind.TICK_GROUP:
            expected_role = (
                ComponentRole.MAJOR_TICK
                if level == "major"
                else ComponentRole.MINOR_TICK
            )
            if state.role is not expected_role:
                raise ValueError(f"Mismatched tick role at {path}.role.")
        if state.kind is ComponentKind.TICK_LABEL_GROUP:
            expected_role = (
                ComponentRole.MAJOR_TICK_LABEL
                if level == "major"
                else ComponentRole.MINOR_TICK_LABEL
            )
            if state.role is not expected_role:
                raise ValueError(f"Mismatched tick-label role at {path}.role.")
    if state.role in {ComponentRole.X_LABEL, ComponentRole.Y_LABEL}:
        expected = "x" if state.role is ComponentRole.X_LABEL else "y"
        if selector.get("axis") != expected or parent.selector.get("axis") != expected:
            raise ValueError(f"Mismatched Axis label selector at {path}.selector.")
    if state.kind is ComponentKind.SPINE:
        if selector.get("name") not in _SPINE_NAMES:
            raise ValueError(f"Invalid Spine selector at {path}.selector.")
    if state.kind is ComponentKind.ANNOTATION and set(selector) != {"object_id"}:
        raise ValueError(
            f"Invalid Annotation selector at {path}.selector: expected only "
            "object_id."
        )
    if (
        state.kind
        in _CHART_KINDS
        | {
            ComponentKind.IN_AXES,
            ComponentKind.COLORBAR,
            ComponentKind.REFERENCE_MARKS,
            ComponentKind.REFERENCE_GUIDE,
            ComponentKind.ANNOTATION,
        }
        or state.role is ComponentRole.TEXT
    ) and selector.get("object_id") != state.id:
        raise ValueError(f"Invalid object selector at {path}.selector.object_id.")


def _validate_reference(
    raw: Any,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
    *,
    x_axis: bool,
) -> ColumnRef:
    try:
        ref = ColumnRef.from_dict(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid data reference at {path}.") from exc
    if ref.project_id != project_id or ref not in available_refs:
        raise ValueError(f"Invalid data reference at {path}.")
    allowed = (
        {ColumnType.NUMBER, ColumnType.DATETIME}
        if x_axis
        else {ColumnType.NUMBER}
    )
    if available_refs[ref] not in allowed:
        raise ValueError(f"Incompatible column type at {path}.")
    return ref


def _validate_data_references(
    state: ComponentState,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
    *,
    schema_version: int,
) -> None:
    if (
        schema_version >= 15
        and state.kind is ComponentKind.REFERENCE_MARKS
    ):
        raw = state.data.get("position_ref")
        if raw is not None:
            _validate_reference(
                raw,
                f"{path}.data.position_ref",
                project_id,
                available_refs,
                x_axis=False,
            )
        placement = state.data.get("placement")
        if isinstance(placement, dict) and placement.get("kind") == "between_table_ranges":
            _validate_reference(
                placement.get("lower_ref"),
                f"{path}.data.placement.lower_ref",
                project_id,
                available_refs,
                x_axis=False,
            )
            upper_refs = placement.get("upper_refs") or ()
            for index, item in enumerate(upper_refs):
                _validate_reference(
                    item,
                    f"{path}.data.placement.upper_refs[{index}]",
                    project_id,
                    available_refs,
                    x_axis=False,
                )
        return
    if state.kind is ComponentKind.FIELD_2D:
        if set(state.data) != {"x_ref", "y_ref", "z_ref"}:
            raise ValueError(
                f"Invalid project field {path}.data: expected exactly "
                "x_ref, y_ref, and z_ref."
            )
        for key in ("x_ref", "y_ref", "z_ref"):
            _validate_reference(
                state.data.get(key),
                f"{path}.data.{key}",
                project_id,
                available_refs,
                x_axis=False,
            )
        return
    if state.role not in _DATA_ROLES:
        return
    x_ref = _validate_reference(
        state.data.get("x_ref"),
        f"{path}.data.x_ref",
        project_id,
        available_refs,
        x_axis=True,
    )
    _validate_reference(
        state.data.get("y_ref"),
        f"{path}.data.y_ref",
        project_id,
        available_refs,
        x_axis=False,
    )
    if state.role is ComponentRole.SCATTER:
        for key in ("color_ref", "size_ref"):
            raw = state.data.get(key)
            if raw is not None:
                _validate_reference(
                    raw,
                    f"{path}.data.{key}",
                    project_id,
                    available_refs,
                    x_axis=False,
                )
    if state.role is ComponentRole.ERROR_BAR:
        from .property_values import error_spec_references

        for key in ("xerr", "yerr"):
            for index, raw in enumerate(
                error_spec_references(state.data.get(key))
            ):
                _validate_reference(
                    raw,
                    f"{path}.data.{key}[{index}]",
                    project_id,
                    available_refs,
                    x_axis=False,
                )
    try:
        preprocess = DataPreprocessSpec.from_dict(state.data.get("preprocess"))
        if available_refs[x_ref] is ColumnType.DATETIME:
            preprocess.validate_datetime_x()
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid project field {path}.data.preprocess: {exc}"
        ) from exc


def _require_fixed_axes_components(
    axes: ComponentState,
    children: dict[str, list[ComponentState]],
) -> None:
    direct = children.get(axes.id, [])
    axes_path = f"figure.components[{axes.id}]"
    axes_by_name = {
        child.selector.get("axis"): child
        for child in direct
        if child.kind is ComponentKind.AXIS
    }
    if len(axes_by_name) != 2 or set(axes_by_name) != {"x", "y"}:
        raise ValueError(f"{axes_path} must contain one x and one y Axis.")
    spines = [
        child.selector.get("name")
        for child in direct
        if child.kind is ComponentKind.SPINE
    ]
    if len(spines) != 4 or set(spines) != _SPINE_NAMES:
        raise ValueError(f"{axes_path} must contain all standard Spines.")
    if sum(child.role is ComponentRole.TITLE for child in direct) != 1:
        raise ValueError(f"{axes_path} must contain one Title.")
    if sum(child.kind is ComponentKind.LEGEND for child in direct) != 1:
        raise ValueError(f"{axes_path} must contain one legend component.")

    for axis_name, axis in axes_by_name.items():
        axis_children = children.get(axis.id, [])
        label_role = (
            ComponentRole.X_LABEL
            if axis_name == "x"
            else ComponentRole.Y_LABEL
        )
        if sum(child.role is label_role for child in axis_children) != 1:
            raise ValueError(f"{axes_path}/{axis_name} must contain one label.")
        ticks = {
            child.selector.get("level"): child
            for child in axis_children
            if child.kind is ComponentKind.TICK_GROUP
        }
        grids = {
            child.selector.get("level")
            for child in axis_children
            if child.kind is ComponentKind.GRID
        }
        if set(ticks) != _LEVELS or grids != _LEVELS:
            raise ValueError(
                f"{axes_path}/{axis_name} must contain major/minor ticks and grids."
            )
        for level, tick in ticks.items():
            labels = [
                child
                for child in children.get(tick.id, [])
                if child.kind is ComponentKind.TICK_LABEL_GROUP
                and child.selector.get("level") == level
            ]
            if len(labels) != 1:
                raise ValueError(
                    f"{axes_path}/{axis_name}/{level} must contain one tick-label group."
                )


def _validate_layouts(
    root: ComponentState,
    axes_components: list[ComponentState],
    children: dict[str, list[ComponentState]],
    *,
    schema_version: int,
) -> None:
    records = root.data["layouts"]
    layouts = {record["id"]: record for record in records}
    if len(layouts) != len(records):
        raise ValueError("Figure layout ids must be unique.")
    occupied: dict[tuple[str, int, int], dict[str, ComponentState]] = {}
    share_x: dict[str, list[ComponentState]] = {}
    share_y: dict[str, list[ComponentState]] = {}
    used_layouts: set[str] = set()
    for axes in axes_components:
        subplot = axes.data["subplot"]
        layout_id = subplot["layout_id"]
        layout = layouts.get(layout_id)
        if layout is None:
            raise ValueError(f"Axes {axes.id} references an unknown Figure layout.")
        used_layouts.add(layout_id)
        row = subplot["row"]
        column = subplot["column"]
        if row >= layout["nrows"] or column >= layout["ncols"]:
            raise ValueError(f"Axes {axes.id} lies outside its Figure layout.")
        cell = occupied.setdefault((layout_id, row, column), {})
        layer = subplot["layer"]
        if layer in cell:
            raise ValueError(
                f"Figure layout cell {row + 1},{column + 1} has duplicate {layer} Axes."
            )
        cell[layer] = axes
        if subplot["share_x_group"] is not None:
            share_x.setdefault(subplot["share_x_group"], []).append(axes)
        if subplot["share_y_group"] is not None:
            share_y.setdefault(subplot["share_y_group"], []).append(axes)
    if set(layouts) != used_layouts:
        raise ValueError("Every Figure layout must contain at least one Axes.")

    def axis_state(axes: ComponentState, dimension: str) -> ComponentState:
        role = (
            ComponentRole.X_AXIS
            if dimension == "x"
            else ComponentRole.Y_AXIS
        )
        return next(child for child in children[axes.id] if child.role is role)

    for (_layout_id, row, column), layers in occupied.items():
        primary = layers.get("primary")
        secondary = layers.get("right_y")
        if primary is None:
            raise ValueError(
                f"Figure layout cell {row + 1},{column + 1} has no primary Axes."
            )
        if secondary is not None:
            primary_x = primary.data["subplot"]["share_x_group"]
            secondary_x = secondary.data["subplot"]["share_x_group"]
            if primary_x is None or primary_x != secondary_x:
                raise ValueError("Twin Axes must share one stable X group.")
            if secondary.selector["index"] <= primary.selector["index"]:
                raise ValueError("A right Y Axes must follow its primary Axes.")
            if schema_version >= 19 and (
                primary.data["geometry"] != secondary.data["geometry"]
            ):
                raise ValueError("Twin Axes must persist identical geometry.")
        for layer, axes in layers.items():
            legend = next(
                child
                for child in children[axes.id]
                if child.kind is ComponentKind.LEGEND
            )
            if legend.properties.get("entry_scope", "axes") == "twin_pair" and (
                layer != "primary" or secondary is None
            ):
                raise ValueError(
                    "A twin-pair Legend requires a primary Axes with a right Y Axes."
                )

    def validate_share_groups(
        groups: dict[str, list[ComponentState]],
        dimension: str,
    ) -> None:
        properties = (
            ("xlim", "autoscalex_on")
            if dimension == "x"
            else ("ylim", "autoscaley_on")
        )
        for group_id, members in groups.items():
            if len(members) < 2:
                raise ValueError(
                    f"Shared {dimension.upper()} group {group_id!r} has fewer than two Axes."
                )
            if len({item.data["subplot"]["layout_id"] for item in members}) != 1:
                raise ValueError("Shared Axes groups cannot cross Figure layouts.")
            expected = tuple(members[0].properties[key] for key in properties)
            expected_scale = axis_state(members[0], dimension).properties["scale"]
            for member in members[1:]:
                actual = tuple(member.properties[key] for key in properties)
                scale = axis_state(member, dimension).properties["scale"]
                if actual != expected or scale != expected_scale:
                    raise ValueError(
                        f"Shared {dimension.upper()} Axes state is inconsistent."
                    )

    validate_share_groups(share_x, "x")
    validate_share_groups(share_y, "y")


def _validate_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
    *,
    schema_version: int,
) -> None:
    """Validate one exact versioned Figure before runtime publication."""

    figure = _expect_dict(figure_snapshot, "figure")
    if set(figure) != {"root_component_id", "components"}:
        raise ValueError(
            f"Schema v{schema_version} figure must contain only "
            "root_component_id and components."
        )
    root_id = figure.get("root_component_id")
    if not isinstance(root_id, str) or not root_id.strip():
        raise ValueError("figure.root_component_id must be a non-empty string.")

    raw_components = _expect_list(figure.get("components"), "figure.components")
    states: list[ComponentState] = []
    by_id: dict[str, ComponentState] = {}
    paths: dict[str, str] = {}
    for index, raw in enumerate(raw_components):
        path = f"figure.components[{index}]"
        state = _state_from_raw(raw, path)
        if schema_version == 10 and state.kind is ComponentKind.COLORBAR:
            raise ValueError(
                f"Invalid project field {path}: Colorbar is not part of schema v10."
            )
        if (
            schema_version < 12
            and state.kind is ComponentKind.REFERENCE_MARKS
        ):
            raise ValueError(
                f"Invalid project field {path}: Reference Marks is not part "
                f"of schema v{schema_version}."
            )
        if (
            schema_version < 13
            and state.kind is ComponentKind.REFERENCE_GUIDE
        ):
            raise ValueError(
                f"Invalid project field {path}: Reference Guides are not part "
                f"of schema v{schema_version}."
            )
        if (
            schema_version < 16
            and state.kind is ComponentKind.FIELD_2D
        ):
            raise ValueError(
                f"Invalid project field {path}: FIELD_2D is not part "
                f"of schema v{schema_version}."
            )
        if (
            schema_version < 17
            and state.kind is ComponentKind.ANNOTATION
        ):
            raise ValueError(
                f"Invalid project field {path}: Annotation is not part "
                f"of schema v{schema_version}."
            )
        if (
            schema_version < 20
            and state.kind is ComponentKind.ERRORBAR
        ):
            raise ValueError(
                f"Invalid project field {path}: Error Bar is not part "
                f"of schema v{schema_version}."
            )
        if state.id in by_id:
            raise ValueError(f"Duplicate component id at {path}: {state.id}")
        by_id[state.id] = state
        paths[state.id] = path
        states.append(state)

    roots = [state for state in states if state.parent_id is None]
    if (
        len(roots) != 1
        or roots[0].id != root_id
        or roots[0].kind is not ComponentKind.FIGURE
    ):
        raise ValueError(
            f"Schema v{schema_version} requires one Figure root matching "
            "root_component_id."
        )
    root = roots[0]
    children: dict[str, list[ComponentState]] = {}
    selector_keys: set[tuple[Any, ...]] = set()
    for state in states:
        path = paths[state.id]
        parent = by_id.get(state.parent_id) if state.parent_id is not None else None
        if state.parent_id is not None and parent is None:
            raise ValueError(
                f"Unknown parent component at {path}.parent_id: {state.parent_id}"
            )
        _validate_parent(state, parent, path)
        _validate_controller_contract(
            state,
            path,
            schema_version=schema_version,
        )
        _validate_data_references(
            state,
            path,
            project_id,
            available_refs,
            schema_version=schema_version,
        )
        if state.parent_id is not None:
            children.setdefault(state.parent_id, []).append(state)
        selector_key = (
            state.parent_id,
            state.kind,
            json.dumps(state.selector, ensure_ascii=False, sort_keys=True),
        )
        if selector_key in selector_keys:
            raise ValueError(f"Duplicate semantic selector at {path}.selector.")
        selector_keys.add(selector_key)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(component_id: str) -> None:
        if component_id in visiting:
            raise ValueError("Component hierarchy contains a cycle.")
        if component_id in visited:
            return
        visiting.add(component_id)
        parent_id = by_id[component_id].parent_id
        if parent_id is not None:
            visit(parent_id)
        visiting.remove(component_id)
        visited.add(component_id)

    for component_id in by_id:
        visit(component_id)

    axes_components = [
        state for state in states if state.kind is ComponentKind.AXES
    ]
    axes_indexes = sorted(state.selector["index"] for state in axes_components)
    if axes_indexes != list(range(len(axes_components))):
        raise ValueError("Axes semantic indexes must be contiguous from zero.")
    for axes in axes_components:
        _require_fixed_axes_components(axes, children)
    _validate_layouts(root, axes_components, children, schema_version=schema_version)

    chart_orders = [
        state.order for state in states if state.kind in _CHART_KINDS
    ]
    if len(chart_orders) != len(set(chart_orders)):
        raise ValueError("Chart component order values must be unique.")
    colorbar_sources: set[str] = set()
    for state in states:
        if state.kind is not ComponentKind.COLORBAR:
            continue
        path = paths[state.id]
        if set(state.data) != {"source_component_id"}:
            raise ValueError(
                f"Invalid project field {path}.data: expected only "
                "source_component_id."
            )
        source_id = state.data["source_component_id"]
        source = by_id.get(source_id)
        if source is None:
            raise ValueError(
                f"Invalid project field {path}.data.source_component_id: "
                "expected a Scatter or FIELD_2D component id."
            )
        scatter_source = (
            source.kind is ComponentKind.SCATTER
            and source.role is ComponentRole.SCATTER
        )
        field_source = (
            schema_version >= 16
            and source.kind is ComponentKind.FIELD_2D
            and source.role
            in {
                ComponentRole.PSEUDOCOLOR,
                ComponentRole.HEATMAP,
                ComponentRole.CONTOUR,
            }
        )
        if schema_version < 16:
            if not scatter_source:
                raise ValueError(
                    f"Invalid project field {path}.data.source_component_id: "
                    "expected a Scatter component id."
                )
        elif not scatter_source and not field_source:
            raise ValueError(
                f"Invalid project field {path}.data.source_component_id: "
                "expected a Scatter or FIELD_2D component id."
            )
        if source.parent_id != state.parent_id:
            raise ValueError(
                f"Invalid project field {path}: Colorbar and source must "
                "share one owner Axes."
            )
        if scatter_source and (
            not source.properties.get("color_mapping", {}).get("enabled")
            or source.data.get("color_ref") is None
        ):
            raise ValueError(
                f"Invalid project field {path}.data.source_component_id: "
                "Scatter scalar color mapping is not enabled."
            )
        if source_id in colorbar_sources:
            raise ValueError(
                f"Invalid project field {path}.data.source_component_id: "
                "a source may own at most one Colorbar."
            )
        colorbar_sources.add(source_id)
    if project_name is not None and root.properties.get("name", "") != project_name:
        raise ValueError("Project and Figure component names must match.")


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
    """Validate a predecessor schema-v15 Figure component tree."""

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
    """Validate a predecessor schema-v16 Figure component tree."""

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
    """Validate a predecessor schema-v17 Figure component tree."""

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
    """Validate a predecessor schema-v18 Figure component tree."""

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
    """Validate the predecessor schema-v19 Figure component tree."""

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
    """Validate the predecessor schema-v20 Figure component tree."""

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
    """Validate the current schema-v21 Figure component tree."""

    _validate_figure(
        figure_snapshot,
        available_refs,
        project_id,
        project_name,
        schema_version=21,
    )
