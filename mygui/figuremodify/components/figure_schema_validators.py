"""Pure Figure schema validators composed from ``FigureSchemaPolicy``.

Public ``validate_v*`` wrappers remain on ``serialization``. This module holds
version-independent helpers plus one orchestrator per concern so each function
stays below the compatibility-hardening McCabe ceilings.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any

from mygui.database import ColumnRef, ColumnType, DataPreprocessSpec
from mygui.figuremodify.style_base.color_models import normalize_color

from .controllers import (
    CONTROLLER_TYPES,
    ERROR_BAR_V20_PROPERTY_KEYS,
    ERROR_BAR_V21_DEFAULTS,
    controller_type_for,
    decode_in_axes_image,
)
from .errors import ComponentValidationError
from .models import ComponentKind, ComponentRole, ComponentState
from .schema_policy import (
    COLOR_PROPERTIES,
    FigureSchemaPolicy,
    figure_schema_policy,
)


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
_FIELD_2D_ROLES = frozenset(
    {
        ComponentRole.PSEUDOCOLOR,
        ComponentRole.HEATMAP,
        ComponentRole.CONTOUR,
    }
)


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected array.")
    return value


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
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


def _validate_line_xy_data(state: ComponentState, path: str) -> None:
    if state.kind is not ComponentKind.LINE or state.role is not ComponentRole.LINE:
        return
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


def _validate_fit_curve_input_range(
    state: ComponentState,
    policy: FigureSchemaPolicy,
) -> None:
    if state.kind is not ComponentKind.LINE or state.role is not ComponentRole.FIT_CURVE:
        return
    has_input_range = "fit_input_range" in state.data
    if policy.requires_fit_input_range and not has_input_range:
        raise ComponentValidationError(
            "Schema v18 Fit Curve data requires fit_input_range."
        )
    if policy.forbids_fit_input_range and has_input_range:
        raise ComponentValidationError(
            f"Fit Curve data must not contain fit_input_range before "
            f"schema v18; schema v{policy.version} rejected it."
        )


def _validate_axes_geometry_presence(
    state: ComponentState,
    policy: FigureSchemaPolicy,
) -> None:
    if state.kind is not ComponentKind.AXES:
        return
    has_geometry = "geometry" in state.data
    if policy.requires_axes_geometry and not has_geometry:
        raise ComponentValidationError(
            "Schema v19 Axes data requires geometry."
        )
    if policy.forbids_axes_geometry and has_geometry:
        raise ComponentValidationError(
            f"Axes data must not contain geometry before "
            f"schema v19; schema v{policy.version} rejected it."
        )


def _validate_axis_ticker_kinds(
    state: ComponentState,
    policy: FigureSchemaPolicy,
) -> None:
    if state.kind is not ComponentKind.AXIS or policy.allows_index_locator:
        return
    for key in ("major_locator", "minor_locator"):
        value = state.properties.get(key)
        if isinstance(value, dict) and value.get("kind") == "index":
            raise ComponentValidationError(
                f"{key} kind 'index' is not part of schema v{policy.version}."
            )
    if policy.allows_format_str_formatter:
        return
    for key in ("major_formatter", "minor_formatter"):
        value = state.properties.get(key)
        if isinstance(value, dict) and value.get("kind") == "format_str":
            raise ComponentValidationError(
                f"{key} kind 'format_str' is not part of schema v{policy.version}."
            )


def _validate_legacy_tick_label_fontfamily(fontfamily: Any, font_path: str) -> None:
    if isinstance(fontfamily, str):
        if not fontfamily.strip():
            raise ValueError(
                f"Invalid project field {font_path}: expected non-empty string."
            )
        return
    if not isinstance(fontfamily, list):
        raise ValueError(
            f"Invalid project field {font_path}: expected string or string array."
        )
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


def _validate_tick_label_fontfamily(
    state: ComponentState,
    path: str,
    policy: FigureSchemaPolicy,
) -> None:
    if state.kind is not ComponentKind.TICK_LABEL_GROUP:
        return
    font_path = f"{path}.properties.fontfamily"
    fontfamily = state.properties.get("fontfamily")
    if policy.tick_label_fontfamily_string_only:
        if not isinstance(fontfamily, str) or not fontfamily.strip():
            raise ValueError(
                f"Invalid project field {font_path}: expected non-empty string."
            )
        return
    _validate_legacy_tick_label_fontfamily(fontfamily, font_path)


def _validate_color_properties(state: ComponentState, path: str) -> None:
    for key in COLOR_PROPERTIES.intersection(state.properties):
        value = state.properties[key]
        if value is None or isinstance(value, dict):
            continue
        try:
            normalize_color(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid project field {path}.properties.{key}."
            ) from exc


def _adapt_axes_in_layout(
    state: ComponentState,
    candidate: ComponentState,
    expected: set[str],
    policy: FigureSchemaPolicy,
) -> tuple[ComponentState, set[str]]:
    if state.kind is not ComponentKind.AXES or not policy.axes_persists_in_layout:
        return candidate, expected
    expected.add("in_layout")
    return (
        state.clone(
            properties={
                key: value
                for key, value in state.properties.items()
                if key != "in_layout"
            }
        ),
        expected,
    )


def _adapt_pre_v15_defaults(
    state: ComponentState,
    candidate: ComponentState,
    expected: set[str],
    policy: FigureSchemaPolicy,
) -> tuple[ComponentState, set[str]]:
    if not policy.injects_missing_y_lower_reserve:
        return candidate, expected
    if state.kind is ComponentKind.AXES:
        expected.discard("y_lower_reserve")
        if "y_lower_reserve" not in state.properties:
            candidate = candidate.clone(
                properties={
                    **candidate.properties,
                    "y_lower_reserve": 0.0,
                }
            )
    return candidate, expected


def _adapt_reference_marks_data(
    state: ComponentState,
    candidate: ComponentState,
    policy: FigureSchemaPolicy,
) -> ComponentState:
    if state.kind is not ComponentKind.REFERENCE_MARKS:
        return candidate
    if policy.reference_marks_positions_only:
        if set(state.data) != {"positions"}:
            raise ComponentValidationError(
                "Reference Marks data requires only positions."
            )
        return candidate.clone(
            data={
                **candidate.data,
                "position_ref": None,
                "placement": {"kind": "fixed"},
            }
        )
    if set(state.data) != {"positions", "position_ref", "placement"}:
        raise ComponentValidationError(
            "Reference Marks data requires positions, position_ref, "
            "and placement."
        )
    return candidate


def _adapt_errorbar_v20_properties(
    state: ComponentState,
    candidate: ComponentState,
    policy: FigureSchemaPolicy,
) -> tuple[ComponentState, ComponentState]:
    if state.kind is not ComponentKind.ERRORBAR or not policy.errorbar_v20_properties:
        return state, candidate
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
    return state, state


def _validate_property_key_set(
    state: ComponentState,
    expected: set[str],
) -> None:
    actual = set(state.properties)
    if actual == expected:
        return
    details = []
    if expected - actual:
        details.append(f"missing {sorted(expected - actual)!r}")
    if actual - expected:
        details.append(f"unknown {sorted(actual - expected)!r}")
    raise ComponentValidationError(
        "property keys are invalid: " + ", ".join(details)
    )


def _validate_property_value_types(candidate: ComponentState) -> None:
    controller_type = controller_type_for(candidate)
    for key, spec in controller_type.property_specs().items():
        if not spec.persistent or key not in candidate.properties:
            continue
        expected_types = (
            spec.value_type
            if isinstance(spec.value_type, tuple)
            else (spec.value_type,)
        )
        value = candidate.properties[key]
        if dict in expected_types and value is not None and not isinstance(value, dict):
            raise ComponentValidationError(
                f"property {key!r} must use its tagged JSON object form"
            )


def _validate_persistent_property_contract(
    state: ComponentState,
    path: str,
    policy: FigureSchemaPolicy,
) -> None:
    try:
        _validate_color_properties(state, path)
        controller_type = controller_type_for(state)
        expected = {
            key
            for key, spec in controller_type.property_specs().items()
            if spec.persistent
        }
        candidate = state
        candidate, expected = _adapt_axes_in_layout(state, candidate, expected, policy)
        candidate, expected = _adapt_pre_v15_defaults(
            state, candidate, expected, policy
        )
        candidate = _adapt_reference_marks_data(state, candidate, policy)
        state, candidate = _adapt_errorbar_v20_properties(state, candidate, policy)
        _validate_property_key_set(state, expected)
        _validate_property_value_types(candidate)
        controller_type_for(candidate)(candidate)
        if state.role is ComponentRole.IN_AXES_IMAGE:
            decode_in_axes_image(state.data)
    except (ComponentValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: {exc}") from exc


def _validate_controller_contract(
    state: ComponentState,
    path: str,
    *,
    schema_version: int,
) -> None:
    policy = figure_schema_policy(schema_version)
    _validate_line_xy_data(state, path)
    _validate_fit_curve_input_range(state, policy)
    _validate_axes_geometry_presence(state, policy)
    _validate_axis_ticker_kinds(state, policy)
    _validate_tick_label_fontfamily(state, path, policy)
    _validate_persistent_property_contract(state, path, policy)


_FIGURE_PARENT = None
_AXES_PARENT = frozenset({ComponentKind.AXES})
_FIGURE_KIND_PARENT = frozenset({ComponentKind.FIGURE})
_AXIS_PARENT = frozenset({ComponentKind.AXIS})
_TICK_GROUP_PARENT = frozenset({ComponentKind.TICK_GROUP})
_FIGURE_OR_AXES_PARENT = frozenset({ComponentKind.FIGURE, ComponentKind.AXES})

_PARENT_KINDS: dict[
    tuple[ComponentKind, ComponentRole],
    frozenset[ComponentKind] | None,
] = {
    (ComponentKind.FIGURE, ComponentRole.FIGURE): _FIGURE_PARENT,
    (ComponentKind.AXES, ComponentRole.AXES): _FIGURE_KIND_PARENT,
    (ComponentKind.AXIS, ComponentRole.X_AXIS): _AXES_PARENT,
    (ComponentKind.AXIS, ComponentRole.Y_AXIS): _AXES_PARENT,
    (ComponentKind.SPINE, ComponentRole.SPINE): _AXES_PARENT,
    (ComponentKind.TICK_GROUP, ComponentRole.MAJOR_TICK): _AXIS_PARENT,
    (ComponentKind.TICK_GROUP, ComponentRole.MINOR_TICK): _AXIS_PARENT,
    (ComponentKind.TICK_LABEL_GROUP, ComponentRole.MAJOR_TICK_LABEL): _TICK_GROUP_PARENT,
    (ComponentKind.TICK_LABEL_GROUP, ComponentRole.MINOR_TICK_LABEL): _TICK_GROUP_PARENT,
    (ComponentKind.GRID, ComponentRole.GRID): _AXIS_PARENT,
    (ComponentKind.TEXT, ComponentRole.TITLE): _AXES_PARENT,
    (ComponentKind.TEXT, ComponentRole.X_LABEL): _AXIS_PARENT,
    (ComponentKind.TEXT, ComponentRole.Y_LABEL): _AXIS_PARENT,
    (ComponentKind.TEXT, ComponentRole.TEXT): _FIGURE_OR_AXES_PARENT,
    (ComponentKind.ANNOTATION, ComponentRole.ANNOTATION): _AXES_PARENT,
    (ComponentKind.LEGEND, ComponentRole.LEGEND): _AXES_PARENT,
    (ComponentKind.LINE, ComponentRole.LINE): _AXES_PARENT,
    (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE): _AXES_PARENT,
    (ComponentKind.LINE, ComponentRole.DATA_PLOT): _AXES_PARENT,
    (ComponentKind.LINE, ComponentRole.FIT_CURVE): _AXES_PARENT,
    (ComponentKind.LINE, ComponentRole.INTERPOLATION): _AXES_PARENT,
    (ComponentKind.SCATTER, ComponentRole.SCATTER): _AXES_PARENT,
    (ComponentKind.ERRORBAR, ComponentRole.ERROR_BAR): _AXES_PARENT,
    (ComponentKind.FIELD_2D, ComponentRole.PSEUDOCOLOR): _AXES_PARENT,
    (ComponentKind.FIELD_2D, ComponentRole.HEATMAP): _AXES_PARENT,
    (ComponentKind.FIELD_2D, ComponentRole.CONTOUR): _AXES_PARENT,
    (ComponentKind.REFERENCE_MARKS, ComponentRole.REFLECTION_POSITIONS): _AXES_PARENT,
    (ComponentKind.REFERENCE_GUIDE, ComponentRole.REFERENCE_LINE): _AXES_PARENT,
    (ComponentKind.REFERENCE_GUIDE, ComponentRole.REFERENCE_BAND): _AXES_PARENT,
    (ComponentKind.COLORBAR, ComponentRole.COLORBAR): _AXES_PARENT,
    (ComponentKind.SECONDARY_AXIS, ComponentRole.SECONDARY_X_AXIS): _AXES_PARENT,
    (ComponentKind.SECONDARY_AXIS, ComponentRole.SECONDARY_Y_AXIS): _AXES_PARENT,
    (ComponentKind.IN_AXES, ComponentRole.IN_AXES_ZOOM): _AXES_PARENT,
    (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE): _AXES_PARENT,
}


def _validate_no_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    return None


def _validate_axes_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    index = state.selector.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError(f"Invalid Axes selector at {path}.selector.")


def _validate_axis_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    expected = "x" if state.role is ComponentRole.X_AXIS else "y"
    if state.selector.get("axis") != expected:
        raise ValueError(f"Invalid Axis selector at {path}.selector.")


def _validate_tick_role_alignment(
    state: ComponentState,
    parent: ComponentState,
    path: str,
    level: str,
) -> None:
    if state.kind is ComponentKind.TICK_LABEL_GROUP:
        if parent.selector.get("level") != level:
            raise ValueError(f"Mismatched tick level at {path}.selector.")
        expected_role = (
            ComponentRole.MAJOR_TICK_LABEL
            if level == "major"
            else ComponentRole.MINOR_TICK_LABEL
        )
        if state.role is not expected_role:
            raise ValueError(f"Mismatched tick-label role at {path}.role.")
        return
    if state.kind is ComponentKind.TICK_GROUP:
        expected_role = (
            ComponentRole.MAJOR_TICK
            if level == "major"
            else ComponentRole.MINOR_TICK
        )
        if state.role is not expected_role:
            raise ValueError(f"Mismatched tick role at {path}.role.")


def _validate_tick_or_grid_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    selector = state.selector
    axis_name = selector.get("axis")
    level = selector.get("level")
    if axis_name not in {"x", "y"} or level not in _LEVELS:
        raise ValueError(f"Invalid tick/grid selector at {path}.selector.")
    if parent.selector.get("axis") != axis_name:
        raise ValueError(f"Mismatched Axis selector at {path}.selector.")
    _validate_tick_role_alignment(state, parent, path, str(level))


def _validate_axis_label_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    expected = "x" if state.role is ComponentRole.X_LABEL else "y"
    if state.selector.get("axis") != expected or parent.selector.get("axis") != expected:
        raise ValueError(f"Mismatched Axis label selector at {path}.selector.")


def _validate_spine_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    if state.selector.get("name") not in _SPINE_NAMES:
        raise ValueError(f"Invalid Spine selector at {path}.selector.")


def _validate_object_id_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    if state.selector.get("object_id") != state.id:
        raise ValueError(f"Invalid object selector at {path}.selector.object_id.")


def _validate_annotation_selector(
    state: ComponentState,
    parent: ComponentState,
    path: str,
) -> None:
    if set(state.selector) != {"object_id"}:
        raise ValueError(
            f"Invalid Annotation selector at {path}.selector: expected only "
            "object_id."
        )
    _validate_object_id_selector(state, parent, path)


_SELECTOR_VALIDATORS: dict[
    tuple[ComponentKind, ComponentRole],
    Any,
] = {
    key: _validate_no_selector for key in CONTROLLER_TYPES
}
_SELECTOR_VALIDATORS[(ComponentKind.AXES, ComponentRole.AXES)] = _validate_axes_selector
_SELECTOR_VALIDATORS[(ComponentKind.AXIS, ComponentRole.X_AXIS)] = _validate_axis_selector
_SELECTOR_VALIDATORS[(ComponentKind.AXIS, ComponentRole.Y_AXIS)] = _validate_axis_selector
_SELECTOR_VALIDATORS[(ComponentKind.SPINE, ComponentRole.SPINE)] = _validate_spine_selector
_SELECTOR_VALIDATORS[(ComponentKind.TICK_GROUP, ComponentRole.MAJOR_TICK)] = (
    _validate_tick_or_grid_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TICK_GROUP, ComponentRole.MINOR_TICK)] = (
    _validate_tick_or_grid_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TICK_LABEL_GROUP, ComponentRole.MAJOR_TICK_LABEL)] = (
    _validate_tick_or_grid_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TICK_LABEL_GROUP, ComponentRole.MINOR_TICK_LABEL)] = (
    _validate_tick_or_grid_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.GRID, ComponentRole.GRID)] = (
    _validate_tick_or_grid_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TEXT, ComponentRole.X_LABEL)] = (
    _validate_axis_label_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TEXT, ComponentRole.Y_LABEL)] = (
    _validate_axis_label_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.TEXT, ComponentRole.TEXT)] = (
    _validate_object_id_selector
)
_SELECTOR_VALIDATORS[(ComponentKind.ANNOTATION, ComponentRole.ANNOTATION)] = (
    _validate_annotation_selector
)
for _kind, _role in CONTROLLER_TYPES:
    if _kind in _CHART_KINDS | {
        ComponentKind.IN_AXES,
        ComponentKind.COLORBAR,
        ComponentKind.REFERENCE_MARKS,
        ComponentKind.REFERENCE_GUIDE,
        ComponentKind.SECONDARY_AXIS,
    }:
        _SELECTOR_VALIDATORS[(_kind, _role)] = _validate_object_id_selector

if set(_PARENT_KINDS) != set(CONTROLLER_TYPES):
    raise RuntimeError(
        "Schema parent validators must cover every Controller kind/role exactly."
    )
if set(_SELECTOR_VALIDATORS) != set(CONTROLLER_TYPES):
    raise RuntimeError(
        "Schema selector validators must cover every Controller kind/role exactly."
    )


def _validate_parent(
    state: ComponentState,
    parent: ComponentState | None,
    path: str,
) -> None:
    key = (state.kind, state.role)
    try:
        expected = _PARENT_KINDS[key]
    except KeyError as exc:
        raise ValueError(
            f"Invalid parent kind {getattr(parent, 'kind', None)!r} for "
            f"{state.kind.value}/{state.role.value} at {path}."
        ) from exc
    if expected is None:
        if parent is not None or state.selector != {"scope": "figure"}:
            raise ValueError(f"Invalid Figure root at {path}.")
        return
    if parent is None:
        raise ValueError(f"Missing parent component at {path}.parent_id.")
    if parent.kind not in expected:
        raise ValueError(
            f"Invalid parent kind {parent.kind.value!r} for "
            f"{state.kind.value}/{state.role.value} at {path}."
        )
    _SELECTOR_VALIDATORS[key](state, parent, path)


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


def _validate_reference_marks_refs(
    state: ComponentState,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
) -> None:
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
    if not isinstance(placement, dict) or placement.get("kind") != "between_table_ranges":
        return
    _validate_reference(
        placement.get("lower_ref"),
        f"{path}.data.placement.lower_ref",
        project_id,
        available_refs,
        x_axis=False,
    )
    for index, item in enumerate(placement.get("upper_refs") or ()):
        _validate_reference(
            item,
            f"{path}.data.placement.upper_refs[{index}]",
            project_id,
            available_refs,
            x_axis=False,
        )


def _validate_field_2d_refs(
    state: ComponentState,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
) -> None:
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


def _validate_chart_data_refs(
    state: ComponentState,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
) -> None:
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
            for index, raw in enumerate(error_spec_references(state.data.get(key))):
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


def _validate_data_references(
    state: ComponentState,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
    *,
    schema_version: int,
) -> None:
    policy = figure_schema_policy(schema_version)
    if (
        not policy.reference_marks_positions_only
        and state.kind is ComponentKind.REFERENCE_MARKS
    ):
        _validate_reference_marks_refs(state, path, project_id, available_refs)
        return
    if state.kind is ComponentKind.FIELD_2D:
        _validate_field_2d_refs(state, path, project_id, available_refs)
        return
    if state.role in _DATA_ROLES:
        _validate_chart_data_refs(state, path, project_id, available_refs)


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
        _require_axis_semantic_children(axes_path, axis_name, axis, children)


def _require_tick_label_child(
    axes_path: str,
    axis_name: str,
    ticks: dict[Any, ComponentState],
    children: dict[str, list[ComponentState]],
) -> None:
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


def _require_axis_semantic_children(
    axes_path: str,
    axis_name: str,
    axis: ComponentState,
    children: dict[str, list[ComponentState]],
) -> None:
    axis_children = children.get(axis.id, [])
    label_role = (
        ComponentRole.X_LABEL if axis_name == "x" else ComponentRole.Y_LABEL
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
    _require_tick_label_child(axes_path, axis_name, ticks, children)


def _layout_axis_state(
    axes: ComponentState,
    children: dict[str, list[ComponentState]],
    dimension: str,
) -> ComponentState:
    role = ComponentRole.X_AXIS if dimension == "x" else ComponentRole.Y_AXIS
    return next(child for child in children[axes.id] if child.role is role)


def _collect_layout_occupancy(
    axes_components: list[ComponentState],
    layouts: dict[str, dict[str, Any]],
) -> tuple[
    dict[tuple[str, int, int], dict[str, ComponentState]],
    dict[str, list[ComponentState]],
    dict[str, list[ComponentState]],
    set[str],
]:
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
    return occupied, share_x, share_y, used_layouts


def _validate_twin_cell(
    row: int,
    column: int,
    layers: dict[str, ComponentState],
    policy: FigureSchemaPolicy,
) -> None:
    primary = layers.get("primary")
    secondary = layers.get("right_y")
    if primary is None:
        raise ValueError(
            f"Figure layout cell {row + 1},{column + 1} has no primary Axes."
        )
    if secondary is None:
        return
    primary_x = primary.data["subplot"]["share_x_group"]
    secondary_x = secondary.data["subplot"]["share_x_group"]
    if primary_x is None or primary_x != secondary_x:
        raise ValueError("Twin Axes must share one stable X group.")
    if secondary.selector["index"] <= primary.selector["index"]:
        raise ValueError("A right Y Axes must follow its primary Axes.")
    if (
        policy.twin_axes_require_identical_geometry
        and primary.data["geometry"] != secondary.data["geometry"]
    ):
        raise ValueError("Twin Axes must persist identical geometry.")


def _validate_cell_legends(
    layers: dict[str, ComponentState],
    children: dict[str, list[ComponentState]],
) -> None:
    secondary = layers.get("right_y")
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


def _validate_share_groups(
    groups: dict[str, list[ComponentState]],
    dimension: str,
    children: dict[str, list[ComponentState]],
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
        expected_scale = _layout_axis_state(members[0], children, dimension).properties[
            "scale"
        ]
        for member in members[1:]:
            actual = tuple(member.properties[key] for key in properties)
            scale = _layout_axis_state(member, children, dimension).properties["scale"]
            if actual != expected or scale != expected_scale:
                raise ValueError(
                    f"Shared {dimension.upper()} Axes state is inconsistent."
                )


def _validate_layouts(
    root: ComponentState,
    axes_components: list[ComponentState],
    children: dict[str, list[ComponentState]],
    *,
    schema_version: int,
) -> None:
    policy = figure_schema_policy(schema_version)
    records = root.data["layouts"]
    layouts = {record["id"]: record for record in records}
    if len(layouts) != len(records):
        raise ValueError("Figure layout ids must be unique.")
    occupied, share_x, share_y, used_layouts = _collect_layout_occupancy(
        axes_components, layouts
    )
    if set(layouts) != used_layouts:
        raise ValueError("Every Figure layout must contain at least one Axes.")
    for (_layout_id, row, column), layers in occupied.items():
        _validate_twin_cell(row, column, layers, policy)
        _validate_cell_legends(layers, children)
    _validate_share_groups(share_x, "x", children)
    _validate_share_groups(share_y, "y", children)


def _reject_unintroduced_kind(
    state: ComponentState,
    path: str,
    policy: FigureSchemaPolicy,
) -> None:
    since = policy.kind_introduced_at.get(state.kind)
    if since is None or policy.version >= since:
        return
    template = policy.kind_rejection_messages[state.kind]
    raise ValueError(
        f"Invalid project field {path}: {template.format(version=policy.version)}"
    )


def _load_figure_states(
    figure: dict[str, Any],
    policy: FigureSchemaPolicy,
) -> tuple[list[ComponentState], dict[str, ComponentState], dict[str, str]]:
    raw_components = _expect_list(figure.get("components"), "figure.components")
    states: list[ComponentState] = []
    by_id: dict[str, ComponentState] = {}
    paths: dict[str, str] = {}
    for index, raw in enumerate(raw_components):
        path = f"figure.components[{index}]"
        state = _state_from_raw(raw, path)
        _reject_unintroduced_kind(state, path, policy)
        if state.id in by_id:
            raise ValueError(f"Duplicate component id at {path}: {state.id}")
        by_id[state.id] = state
        paths[state.id] = path
        states.append(state)
    return states, by_id, paths


def _require_figure_root(
    figure: dict[str, Any],
    states: list[ComponentState],
    policy: FigureSchemaPolicy,
) -> ComponentState:
    root_id = figure.get("root_component_id")
    roots = [state for state in states if state.parent_id is None]
    if (
        len(roots) != 1
        or roots[0].id != root_id
        or roots[0].kind is not ComponentKind.FIGURE
    ):
        raise ValueError(
            f"Schema v{policy.version} requires one Figure root matching "
            "root_component_id."
        )
    return roots[0]


def _validate_component_membership(
    states: list[ComponentState],
    by_id: dict[str, ComponentState],
    paths: dict[str, str],
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    policy: FigureSchemaPolicy,
) -> dict[str, list[ComponentState]]:
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
            schema_version=policy.version,
        )
        _validate_data_references(
            state,
            path,
            project_id,
            available_refs,
            schema_version=policy.version,
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
    return children


def _validate_component_hierarchy(by_id: dict[str, ComponentState]) -> None:
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


def _validate_axes_indexes(states: list[ComponentState]) -> list[ComponentState]:
    axes_components = [
        state for state in states if state.kind is ComponentKind.AXES
    ]
    axes_indexes = sorted(state.selector["index"] for state in axes_components)
    if axes_indexes != list(range(len(axes_components))):
        raise ValueError("Axes semantic indexes must be contiguous from zero.")
    return axes_components


def _validate_chart_orders(states: list[ComponentState]) -> None:
    chart_orders = [
        state.order for state in states if state.kind in _CHART_KINDS
    ]
    if len(chart_orders) != len(set(chart_orders)):
        raise ValueError("Chart component order values must be unique.")


def _validate_secondary_axis_placements(
    states: list[ComponentState],
    paths: dict[str, str],
) -> None:
    placements: set[tuple[str | None, ComponentRole, str, float]] = set()
    for state in states:
        if state.kind is not ComponentKind.SECONDARY_AXIS:
            continue
        from .secondary_axis_values import secondary_axis_placement_key

        orientation = (
            "x" if state.role is ComponentRole.SECONDARY_X_AXIS else "y"
        )
        coordinate_system, value = secondary_axis_placement_key(
            state.properties["placement"], orientation=orientation
        )
        placement_key = (
            state.parent_id,
            state.role,
            coordinate_system,
            value,
        )
        if placement_key in placements:
            raise ValueError(
                f"Invalid project field {paths[state.id]}: duplicate "
                "Secondary Axis placement for one parent and orientation."
            )
        placements.add(placement_key)


def _validate_colorbar_source(
    state: ComponentState,
    source: ComponentState | None,
    path: str,
    policy: FigureSchemaPolicy,
) -> None:
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
        policy.colorbar_allows_field_2d_source
        and source.kind is ComponentKind.FIELD_2D
        and source.role in _FIELD_2D_ROLES
    )
    if not policy.colorbar_allows_field_2d_source:
        if not scatter_source:
            raise ValueError(
                f"Invalid project field {path}.data.source_component_id: "
                "expected a Scatter component id."
            )
        return
    if not scatter_source and not field_source:
        raise ValueError(
            f"Invalid project field {path}.data.source_component_id: "
            "expected a Scatter or FIELD_2D component id."
        )


def _validate_colorbar_binding(
    state: ComponentState,
    source: ComponentState,
    path: str,
    colorbar_sources: set[str],
) -> None:
    if source.parent_id != state.parent_id:
        raise ValueError(
            f"Invalid project field {path}: Colorbar and source must "
            "share one owner Axes."
        )
    scatter_source = (
        source.kind is ComponentKind.SCATTER
        and source.role is ComponentRole.SCATTER
    )
    if scatter_source and (
        not source.properties.get("color_mapping", {}).get("enabled")
        or source.data.get("color_ref") is None
    ):
        raise ValueError(
            f"Invalid project field {path}.data.source_component_id: "
            "Scatter scalar color mapping is not enabled."
        )
    source_id = state.data["source_component_id"]
    if source_id in colorbar_sources:
        raise ValueError(
            f"Invalid project field {path}.data.source_component_id: "
            "a source may own at most one Colorbar."
        )
    colorbar_sources.add(source_id)


def _validate_colorbar_relations(
    states: list[ComponentState],
    by_id: dict[str, ComponentState],
    paths: dict[str, str],
    policy: FigureSchemaPolicy,
) -> None:
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
        _validate_colorbar_source(state, source, path, policy)
        assert source is not None
        _validate_colorbar_binding(state, source, path, colorbar_sources)


def _validate_figure_envelope(
    figure_snapshot: Any,
    policy: FigureSchemaPolicy,
) -> dict[str, Any]:
    figure = _expect_dict(figure_snapshot, "figure")
    if set(figure) != {"root_component_id", "components"}:
        raise ValueError(
            f"Schema v{policy.version} figure must contain only "
            "root_component_id and components."
        )
    root_id = figure.get("root_component_id")
    if not isinstance(root_id, str) or not root_id.strip():
        raise ValueError("figure.root_component_id must be a non-empty string.")
    return figure


def _validate_figure_project_name(
    root: ComponentState,
    project_name: str | None,
) -> None:
    if project_name is not None and root.properties.get("name", "") != project_name:
        raise ValueError("Project and Figure component names must match.")


def _validate_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
    *,
    schema_version: int,
) -> None:
    """Validate one exact versioned Figure before runtime publication."""

    policy = figure_schema_policy(schema_version)
    figure = _validate_figure_envelope(figure_snapshot, policy)
    states, by_id, paths = _load_figure_states(figure, policy)
    root = _require_figure_root(figure, states, policy)
    children = _validate_component_membership(
        states, by_id, paths, available_refs, project_id, policy
    )
    _validate_component_hierarchy(by_id)
    axes_components = _validate_axes_indexes(states)
    for axes in axes_components:
        _require_fixed_axes_components(axes, children)
    _validate_layouts(
        root, axes_components, children, schema_version=policy.version
    )
    _validate_chart_orders(states)
    _validate_secondary_axis_placements(states, paths)
    _validate_colorbar_relations(states, by_id, paths, policy)
    _validate_figure_project_name(root, project_name)
