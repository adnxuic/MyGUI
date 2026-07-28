from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from code.database import ColumnRef, ColumnType
from code.database.interpolate_func import interpolate_dict
from code.figuremodify.style_base.color_models import ColorCycleState, normalize_color

from .controllers import controller_type_for
from .errors import ComponentValidationError
from .models import ComponentState
CHART_KINDS = {"line", "scatter"}
DATA_ROLES = {"data_plot", "fit_curve", "interpolation", "scatter"}
SPINE_NAMES = ("left", "right", "bottom", "top")
LEVELS = ("major", "minor")
COLOR_PROPERTIES = {"color", "facecolor", "edgecolor", "markerfacecolor", "markeredgecolor"}


def deterministic_component_id(project_id: str, legacy_path: str) -> str:
    project_key = str(project_id).strip()
    path_key = str(legacy_path).strip().replace("\\", "/")
    if not project_key:
        raise ValueError("Project id must not be empty.")
    if not path_key:
        raise ValueError("Legacy component path must not be empty.")
    return str(uuid5(NAMESPACE_URL, f"mygui-project:{project_key}:{path_key}"))


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid project field {path}: expected object.")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid project field {path}: expected array.")
    return value


def _legacy_int(value: Any, path: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected integer.") from exc


def _legacy_float(value: Any, path: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: expected number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"Invalid project field {path}: expected finite number.")
    return result


def _component(
    component_id: str,
    kind: str,
    role: str,
    parent_id: str | None,
    order: int,
    selector: dict[str, Any],
    properties: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(component_id),
        "kind": kind,
        "role": role,
        "parent_id": parent_id,
        "order": int(order),
        "selector": deepcopy(selector),
        "properties": deepcopy(properties or {}),
        "data": deepcopy(data or {}),
    }


def _legacy_axis_records(legacy: dict[str, Any], axes_count: int) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for offset, raw in enumerate(_expect_list(legacy.get("axes", []), "figure.axes")):
        record = _expect_dict(raw, f"figure.axes[{offset}]")
        index = _legacy_int(record.get("index", -1), f"figure.axes[{offset}].index")
        if not 0 <= index < axes_count:
            raise ValueError(f"Invalid axes index: {index}")
        if index in result:
            raise ValueError(f"Duplicate axes index: {index}")
        result[index] = record
    return result


def _legacy_layouts(legacy: dict[str, Any], axes_count: int) -> dict[int, dict[str, int]]:
    if axes_count == 0:
        return {}
    raw_layouts = legacy.get("axes_layouts") or []
    if not isinstance(raw_layouts, list):
        raise ValueError("Invalid project field figure.axes_layouts: expected array.")
    if not raw_layouts:
        return {
            index: {
                "layout_group": 0,
                "nrows": axes_count,
                "ncols": 1,
                "slot": index + 1,
            }
            for index in range(axes_count)
        }

    layouts: dict[int, dict[str, int]] = {}
    next_start = 0
    for group, raw in enumerate(raw_layouts):
        record = _expect_dict(raw, f"figure.axes_layouts[{group}]")
        nrows = _legacy_int(record.get("nrows", 1), f"figure.axes_layouts[{group}].nrows")
        ncols = _legacy_int(record.get("ncols", 1), f"figure.axes_layouts[{group}].ncols")
        start = _legacy_int(
            record.get("start_index", next_start),
            f"figure.axes_layouts[{group}].start_index",
        )
        count = _legacy_int(
            record.get("count", nrows * ncols),
            f"figure.axes_layouts[{group}].count",
        )
        if nrows <= 0 or ncols <= 0 or count <= 0 or count > nrows * ncols:
            raise ValueError(f"Invalid subplot layout at figure.axes_layouts[{group}].")
        raw_slots = record.get("slots")
        if raw_slots is None:
            slots = list(range(1, count + 1))
        else:
            slots = [
                _legacy_int(
                    slot,
                    f"figure.axes_layouts[{group}].slots[{offset}]",
                )
                for offset, slot in enumerate(
                    _expect_list(
                        raw_slots,
                        f"figure.axes_layouts[{group}].slots",
                    )
                )
            ]
            if (
                len(slots) != count
                or len(set(slots)) != count
                or any(not 1 <= slot <= nrows * ncols for slot in slots)
            ):
                raise ValueError(
                    f"Invalid subplot slots at figure.axes_layouts[{group}]."
                )
        for slot_offset, slot in enumerate(slots):
            index = start + slot_offset
            if not 0 <= index < axes_count or index in layouts:
                raise ValueError(f"Invalid or overlapping axes layout at index {index}.")
            layouts[index] = {
                "layout_group": group,
                "nrows": nrows,
                "ncols": ncols,
                "slot": slot,
            }
        next_start = start + count
    if set(layouts) != set(range(axes_count)):
        raise ValueError("figure.axes_layouts must describe every axes exactly once.")
    return layouts


def _legacy_text_properties(
    text: Any,
    fontfamily: Any,
    fontsize: Any,
    position: Any = None,
    *,
    visible: Any = True,
) -> dict[str, Any]:
    properties = {
        "text": str(text or ""),
        "fontfamily": str(fontfamily or ""),
        "fontsize": _legacy_float(fontsize, "text.fontsize"),
        "visible": bool(visible),
        "color": "#000000",
        "fontweight": "normal",
        "fontstyle": "normal",
        "rotation": 0.0,
        "horizontalalignment": "left",
        "verticalalignment": "baseline",
        "usetex": False,
        "alpha": None,
    }
    if position is not None:
        coordinates = _expect_list(position, "text.position")
        if len(coordinates) != 2:
            raise ValueError("Invalid project field text.position: expected two coordinates.")
        properties["position"] = [
            _legacy_float(coordinates[0], "text.position[0]"),
            _legacy_float(coordinates[1], "text.position[1]"),
        ]
    return properties


def _fixed_axes_components(
    project_id: str,
    axes_id: str,
    axes_index: int,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    label_family = record.get("label_fontfamily", "")
    label_size = record.get("label_fontsize", 10.0)
    axis_ids: dict[str, str] = {}

    for axis_order, axis_name in enumerate(("x", "y")):
        axis_role = f"{axis_name}_axis"
        axis_id = deterministic_component_id(
            project_id, f"figure/axes/{axes_index}/axis/{axis_name}"
        )
        axis_ids[axis_name] = axis_id
        components.append(_component(
            axis_id,
            "axis",
            axis_role,
            axes_id,
            axis_order,
            {"axis": axis_name},
            {
                "visible": bool(record.get(f"{axis_name}axis_visible", True)),
                "scale": str(record.get(f"{axis_name}scale", "linear")),
                "ticks_position": str(
                    record.get(
                        f"{axis_name}_ticks_position",
                        "bottom" if axis_name == "x" else "left",
                    )
                ),
                "label_position": str(
                    record.get(
                        f"{axis_name}_label_side",
                        "bottom" if axis_name == "x" else "left",
                    )
                ),
                "inverted": bool(record.get(f"{axis_name}axis_inverted", False)),
            },
        ))

        label_role = f"{axis_name}_label"
        label_id = deterministic_component_id(
            project_id, f"figure/axes/{axes_index}/axis/{axis_name}/label"
        )
        label_properties = _legacy_text_properties(
            record.get(f"{axis_name}label", ""),
            label_family,
            label_size,
            record.get(f"{axis_name}_label_position", [0.5, 0.0]),
        )
        label_properties["horizontalalignment"] = "center"
        label_properties["verticalalignment"] = "top" if axis_name == "x" else "bottom"
        components.append(_component(
            label_id,
            "text",
            label_role,
            axis_id,
            0,
            {"axis": axis_name, "role": "label"},
            label_properties,
        ))

        for level_order, level in enumerate(LEVELS):
            tick_role = f"{level}_tick"
            tick_id = deterministic_component_id(
                project_id,
                f"figure/axes/{axes_index}/axis/{axis_name}/tick/{level}",
            )
            tick_properties = deepcopy(
                record.get("ticks", {}).get(axis_name, {}).get(level, {})
                if isinstance(record.get("ticks"), dict)
                else {}
            )
            tick_properties.setdefault("visible", True)
            tick_properties.setdefault("direction", "out")
            tick_properties.setdefault("length", 3.5 if level == "major" else 2.0)
            tick_properties.setdefault("width", 0.8 if level == "major" else 0.6)
            tick_properties.setdefault("color", "#000000")
            tick_properties.setdefault("pad", 3.5)
            components.append(_component(
                tick_id,
                "tick_group",
                tick_role,
                axis_id,
                level_order,
                {"axis": axis_name, "level": level},
                tick_properties,
            ))

            tick_label_id = deterministic_component_id(
                project_id,
                f"figure/axes/{axes_index}/axis/{axis_name}/tick/{level}/label",
            )
            label_properties = deepcopy(
                record.get("tick_labels", {}).get(axis_name, {}).get(level, {})
                if isinstance(record.get("tick_labels"), dict)
                else {}
            )
            label_properties.setdefault("visible", True)
            label_properties.setdefault("color", "#000000")
            label_properties.setdefault("fontsize", 10.0)
            label_properties.setdefault("rotation", 0.0)
            label_properties.setdefault("fontfamily", "sans-serif")
            label_properties.setdefault("pad", 3.5)
            components.append(_component(
                tick_label_id,
                "tick_label_group",
                f"{level}_tick_label",
                tick_id,
                0,
                {"axis": axis_name, "level": level},
                label_properties,
            ))

            grid_id = deterministic_component_id(
                project_id,
                f"figure/axes/{axes_index}/axis/{axis_name}/grid/{level}",
            )
            grid_properties = deepcopy(
                record.get("grids", {}).get(axis_name, {}).get(level, {})
                if isinstance(record.get("grids"), dict)
                else {}
            )
            grid_properties.setdefault("visible", False)
            grid_properties.setdefault("color", "#B0B0B0")
            grid_properties.setdefault("linestyle", "-")
            grid_properties.setdefault("linewidth", 0.8)
            grid_properties.setdefault("alpha", 1.0)
            components.append(_component(
                grid_id,
                "grid",
                "grid",
                axis_id,
                level_order,
                {"axis": axis_name, "level": level},
                grid_properties,
            ))

    spines = record.get("spines") if isinstance(record.get("spines"), dict) else {}
    spine_names = list(SPINE_NAMES)
    spine_names.extend(name for name in spines if name not in spine_names)
    for spine_order, name in enumerate(spine_names):
        spine_state = spines.get(name) if isinstance(spines.get(name), dict) else {}
        spine_id = deterministic_component_id(
            project_id, f"figure/axes/{axes_index}/spine/{name}"
        )
        components.append(_component(
            spine_id,
            "spine",
            "spine",
            axes_id,
            spine_order,
            {"name": name},
            {
                "visible": bool(spine_state.get("visible", True)),
                "position": deepcopy(spine_state.get("position", ["outward", 0.0])),
                "color": normalize_color(spine_state.get("color", "#000000")),
                "linewidth": _legacy_float(
                    spine_state.get("linewidth", 0.8), "spine.linewidth"
                ),
                "linestyle": str(spine_state.get("linestyle", "-")),
                "bounds": deepcopy(spine_state.get("bounds")),
                "alpha": (
                    None
                    if spine_state.get("alpha") is None
                    else _legacy_float(spine_state["alpha"], "spine.alpha")
                ),
            },
        ))

    title_state = record.get("title")
    if isinstance(title_state, dict):
        title_properties = deepcopy(title_state)
        title_properties.setdefault("text", "")
        title_properties.setdefault("fontfamily", label_family)
        title_properties.setdefault("fontsize", label_size)
        title_properties.setdefault("visible", True)
        title_properties.setdefault("position", [0.5, 1.0])
        title_properties.setdefault("color", "#000000")
        title_properties.setdefault("fontweight", "normal")
        title_properties.setdefault("fontstyle", "normal")
        title_properties.setdefault("rotation", 0.0)
        title_properties.setdefault("horizontalalignment", "center")
        title_properties.setdefault("verticalalignment", "baseline")
        title_properties.setdefault("usetex", False)
        title_properties.setdefault("alpha", None)
    else:
        title_properties = _legacy_text_properties(
            title_state or "",
            record.get("title_fontfamily", label_family),
            record.get("title_fontsize", label_size),
            record.get("title_position", [0.5, 1.0]),
        )
        title_properties["horizontalalignment"] = "center"
    components.append(_component(
        deterministic_component_id(project_id, f"figure/axes/{axes_index}/title"),
        "text",
        "title",
        axes_id,
        0,
        {"role": "title"},
        title_properties,
    ))

    legend = record.get("legend")
    legend_properties = deepcopy(legend) if isinstance(legend, dict) else {}
    if "loc" in legend_properties and "location" not in legend_properties:
        legend_properties["location"] = legend_properties.pop("loc")
    legend_properties.setdefault("visible", False)
    legend_properties.setdefault("location", "best")
    legend_properties.setdefault("ncols", 1)
    legend_properties.setdefault("fontsize", 10.0)
    legend_properties.setdefault("frameon", True)
    legend_properties.setdefault("facecolor", "#FFFFFF")
    legend_properties.setdefault("edgecolor", "#CCCCCC")
    legend_properties.setdefault("framealpha", 0.8)
    legend_properties.setdefault("title", "")
    components.append(_component(
        deterministic_component_id(project_id, f"figure/axes/{axes_index}/legend"),
        "legend",
        "legend",
        axes_id,
        0,
        {"role": "legend"},
        legend_properties,
    ))
    return components


def legacy_figure_to_v6(
    figure_snapshot: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    legacy = deepcopy(_expect_dict(figure_snapshot, "figure"))
    if set(legacy) == {"root_component_id", "components"}:
        return normalize_v6_figure(legacy)

    axes_count = _legacy_int(legacy.get("axes_count", 0), "figure.axes_count")
    if axes_count < 0:
        raise ValueError("figure.axes_count must not be negative.")
    size = _expect_list(legacy.get("size_inches", []), "figure.size_inches")
    if len(size) != 2:
        raise ValueError("figure.size_inches must contain two positive numbers.")
    size_inches = [
        _legacy_float(size[0], "figure.size_inches[0]"),
        _legacy_float(size[1], "figure.size_inches[1]"),
    ]
    if any(value <= 0 for value in size_inches):
        raise ValueError("figure.size_inches must contain two positive numbers.")
    dpi = _legacy_float(legacy.get("dpi", 100), "figure.dpi")
    if dpi <= 0:
        raise ValueError("figure.dpi must be positive.")

    root_id = deterministic_component_id(project_id, "figure")
    components = [_component(
        root_id,
        "figure",
        "figure",
        None,
        0,
        {"scope": "figure"},
        {
            "name": str(legacy.get("name", "")),
            "style": str(legacy.get("style") or "default"),
            "dpi": dpi,
            "size_inches": size_inches,
            "facecolor": normalize_color(legacy.get("facecolor", "#FFFFFF")),
            "edgecolor": normalize_color(legacy.get("edgecolor", "#FFFFFF")),
            "frameon": bool(legacy.get("frameon", True)),
            "constrained_layout": bool(legacy.get("constrained_layout", False)),
        },
    )]

    axis_records = _legacy_axis_records(legacy, axes_count)
    layouts = _legacy_layouts(legacy, axes_count)
    axes_ids: dict[int, str] = {}
    for index in range(axes_count):
        record = axis_records.get(index, {"index": index})
        axes_id = deterministic_component_id(project_id, f"figure/axes/{index}")
        axes_ids[index] = axes_id
        components.append(_component(
            axes_id,
            "axes",
            "axes",
            root_id,
            index,
            {"index": index},
            {
                "xlim": deepcopy(record.get("xlim", [0.0, 1.0])),
                "ylim": deepcopy(record.get("ylim", [0.0, 1.0])),
                "position": deepcopy(
                    record.get("position", [0.125, 0.11, 0.775, 0.77])
                ),
                "xscale": str(record.get("xscale", "linear")),
                "yscale": str(record.get("yscale", "linear")),
                "aspect": deepcopy(record.get("aspect", "auto")),
                "facecolor": normalize_color(record.get("facecolor", "#FFFFFF")),
                "visible": bool(record.get("visible", True)),
                "autoscale_on": bool(record.get("autoscale_on", True)),
                "color_cycle": deepcopy(record.get("color_cycle")),
            },
            {"subplot": layouts[index]},
        ))
        components.extend(_fixed_axes_components(project_id, axes_id, index, record))

    chart_specs = (
        ("lines", "line", "line"),
        ("curves", "line", "function_curve"),
        ("plots", "line", "data_plot"),
        ("scatters", "scatter", "scatter"),
        ("interpolates", "line", "interpolation"),
        ("fits", "line", "fit_curve"),
    )
    for collection, kind, role in chart_specs:
        records = _expect_list(legacy.get(collection, []), f"figure.{collection}")
        for index, raw in enumerate(records):
            path = f"figure.{collection}[{index}]"
            record = _expect_dict(raw, path)
            axes_index = _legacy_int(record.get("axes_index", 0), f"{path}.axes_index")
            if axes_index not in axes_ids:
                raise ValueError(f"Invalid project field {path}.axes_index: {axes_index}")
            order = _legacy_int(record.get("color_order", index), f"{path}.color_order")
            if order < 0:
                raise ValueError(f"Invalid project field {path}.color_order: {order}")
            object_id = str(record.get("object_id", "")).strip()
            if role in DATA_ROLES and not object_id:
                raise ValueError(f"Invalid or missing object id at {path}.")
            component_id = object_id or deterministic_component_id(
                project_id, f"figure/{collection}/{index}"
            )

            properties: dict[str, Any] = {
                "color": normalize_color(record.get("color", "black")),
                "label": str(record.get("label", "")),
            }
            if kind == "line":
                default_style = "solid" if role == "fit_curve" else "-"
                properties.update({
                    "linestyle": str(
                        record.get("linestyle", record.get("style", default_style))
                    ),
                    "linewidth": _legacy_float(
                        record.get("linewidth", 1.5), f"{path}.linewidth"
                    ),
                    "marker": str(record.get("marker", "None")),
                    "markersize": _legacy_float(
                        record.get(
                            "markersize",
                            record.get("size", 6.0) if role == "data_plot" else 6.0,
                        ),
                        f"{path}.markersize",
                    ),
                    "markerfacecolor": normalize_color(
                        record.get("markerfacecolor", record.get("color", "black"))
                    ),
                    "markeredgecolor": normalize_color(
                        record.get("markeredgecolor", record.get("color", "black"))
                    ),
                    "markeredgewidth": _legacy_float(
                        record.get("markeredgewidth", 1.0), f"{path}.markeredgewidth"
                    ),
                    "alpha": (
                        None
                        if record.get("alpha") is None
                        else _legacy_float(record["alpha"], f"{path}.alpha")
                    ),
                    "visible": bool(record.get("visible", True)),
                    "zorder": _legacy_float(record.get("zorder", 2.0), f"{path}.zorder"),
                })
            data: dict[str, Any]
            if role == "line":
                x_values = _expect_list(record.get("x"), f"{path}.x")
                y_values = _expect_list(record.get("y"), f"{path}.y")
                if len(x_values) != len(y_values):
                    raise ValueError(
                        f"Invalid project field {path}: x and y must have equal length."
                    )
                data = {
                    "x": [
                        _legacy_float(value, f"{path}.x[{value_index}]")
                        for value_index, value in enumerate(x_values)
                    ],
                    "y": [
                        _legacy_float(value, f"{path}.y[{value_index}]")
                        for value_index, value in enumerate(y_values)
                    ],
                }
            elif role == "function_curve":
                data = {
                    "expression": str(record.get("expression", "x")),
                    "x_start": _legacy_float(record.get("x_start", 0.0), f"{path}.x_start"),
                    "x_stop": _legacy_float(record.get("x_stop", 100.0), f"{path}.x_stop"),
                }
            elif role == "data_plot":
                data = {
                    "x_ref": deepcopy(record.get("x_ref")),
                    "y_ref": deepcopy(record.get("y_ref")),
                }
            elif role == "scatter":
                properties.update({
                    "size": _legacy_float(record.get("size", 20.0), f"{path}.size"),
                    "marker": str(record.get("marker", "o")),
                    "edgecolor": normalize_color(
                        record.get("edgecolor", record.get("color", "black"))
                    ),
                    "linewidth": _legacy_float(
                        record.get("linewidth", 1.0), f"{path}.linewidth"
                    ),
                    "alpha": (
                        None
                        if record.get("alpha") is None
                        else _legacy_float(record["alpha"], f"{path}.alpha")
                    ),
                    "visible": bool(record.get("visible", True)),
                    "zorder": _legacy_float(record.get("zorder", 1.0), f"{path}.zorder"),
                })
                data = {
                    "x_ref": deepcopy(record.get("x_ref")),
                    "y_ref": deepcopy(record.get("y_ref")),
                }
            elif role == "interpolation":
                data = {
                    "x_ref": deepcopy(record.get("x_ref")),
                    "y_ref": deepcopy(record.get("y_ref")),
                    "method": record.get("method"),
                    "k": _legacy_int(record.get("k", 3), f"{path}.k"),
                    "samples": _legacy_int(record.get("samples", 1000), f"{path}.samples"),
                    "lam": (
                        None
                        if record.get("lam") is None
                        else _legacy_float(record["lam"], f"{path}.lam")
                    ),
                    "lam_auto": bool(record.get("lam_auto", True)),
                }
            else:
                data = {
                    "x_ref": deepcopy(record.get("x_ref")),
                    "y_ref": deepcopy(record.get("y_ref")),
                    "engine": str(record.get("engine", "Python")),
                    "fit_type": deepcopy(record.get("fit_type")),
                    "fit_options": deepcopy(record.get("fit_options")),
                    "fit_result": deepcopy(record.get("fit_result")),
                    "expression": str(record.get("expression", "")),
                    "x_start": _legacy_float(record.get("x_start", 0.0), f"{path}.x_start"),
                    "x_stop": _legacy_float(record.get("x_stop", 1.0), f"{path}.x_stop"),
                }
            components.append(_component(
                component_id,
                kind,
                role,
                axes_ids[axes_index],
                order,
                {"object_id": component_id},
                properties,
                data,
            ))

    for index, raw in enumerate(_expect_list(legacy.get("texts", []), "figure.texts")):
        path = f"figure.texts[{index}]"
        record = _expect_dict(raw, path)
        scope = str(record.get("scope", "axes"))
        if scope == "figure":
            parent_id = root_id
        elif scope == "axes":
            axes_index = _legacy_int(record.get("axes_index", 0), f"{path}.axes_index")
            if axes_index not in axes_ids:
                raise ValueError(f"Invalid project field {path}.axes_index: {axes_index}")
            parent_id = axes_ids[axes_index]
        else:
            raise ValueError(f"Invalid project field {path}.scope: {scope!r}")
        component_id = str(record.get("object_id", "")).strip() or deterministic_component_id(
            project_id, f"figure/texts/{index}"
        )
        text_properties = _legacy_text_properties(
            record.get("text", ""),
            record.get("fontfamily", "Times New Roman"),
            record.get("fontsize", 20),
            [record.get("x", 0.5), record.get("y", 0.5)],
            visible=record.get("visible", True),
        )
        text_properties.update({
            "usetex": bool(record.get("usetex", False)),
            "color": normalize_color(record.get("color", "#000000")),
            "fontweight": deepcopy(record.get("fontweight", "normal")),
            "fontstyle": str(record.get("fontstyle", "normal")),
            "rotation": deepcopy(record.get("rotation", 0.0)),
            "horizontalalignment": str(
                record.get("horizontalalignment", "left")
            ),
            "verticalalignment": str(
                record.get("verticalalignment", "baseline")
            ),
            "alpha": (
                None
                if record.get("alpha") is None
                else _legacy_float(record["alpha"], f"{path}.alpha")
            ),
        })
        components.append(_component(
            component_id,
            "text",
            "text",
            parent_id,
            index,
            {"object_id": component_id, "scope": scope},
            text_properties,
        ))

    return normalize_v6_figure({
        "root_component_id": root_id,
        "components": components,
    })


def normalize_v6_figure(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
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
            component.get("properties"), f"figure.components[{index}].properties"
        )
        for name in COLOR_PROPERTIES.intersection(properties):
            if properties[name] is None:
                continue
            try:
                properties[name] = normalize_color(properties[name])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid project field figure.components[{index}].properties.{name}: "
                    f"{properties[name]!r}"
                ) from exc
    return figure


def _canonical_json_value(value: Any, path: str) -> Any:
    if isinstance(value, tuple):
        return [
            _canonical_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, list):
        return [
            _canonical_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"Invalid project field {path}: object keys must be strings.")
        return {
            key: _canonical_json_value(item, f"{path}.{key}")
            for key, item in value.items()
        }
    return deepcopy(value)


def _component_state_dict(raw: Any, path: str) -> dict[str, Any]:
    record = _expect_dict(raw, path)
    try:
        return ComponentState.from_dict(record).to_dict()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid project field {path}: {exc}") from exc


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Invalid project field {path}: expected boolean.")
    return value


def _require_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(
            f"Invalid project field {path}: expected integer >= {minimum}."
        )
    return value


def _require_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid project field {path}: expected number.")
    result = float(value)
    if not math.isfinite(result) or positive and result <= 0:
        qualifier = "positive finite number" if positive else "finite number"
        raise ValueError(f"Invalid project field {path}: expected {qualifier}.")
    return result


def _require_string(value: Any, path: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or nonempty and not value.strip():
        qualifier = "non-empty string" if nonempty else "string"
        raise ValueError(f"Invalid project field {path}: expected {qualifier}.")
    return value


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Invalid project field {path}: number must be finite.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Invalid project field {path}: object keys must be strings.")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"Invalid project field {path}: value is not JSON-compatible.")


def _require_pair(value: Any, path: str, *, positive: bool = False) -> list[float]:
    pair = _expect_list(value, path)
    if len(pair) != 2:
        raise ValueError(f"Invalid project field {path}: expected two numbers.")
    return [
        _require_number(pair[0], f"{path}[0]", positive=positive),
        _require_number(pair[1], f"{path}[1]", positive=positive),
    ]


def _require_quad(value: Any, path: str) -> list[float]:
    values = _expect_list(value, path)
    if len(values) != 4:
        raise ValueError(f"Invalid project field {path}: expected four numbers.")
    return [
        _require_number(item, f"{path}[{index}]")
        for index, item in enumerate(values)
    ]


def _validate_ref(
    value: Any,
    path: str,
    project_id: str,
    available_refs: dict[ColumnRef, ColumnType],
    *,
    x_axis: bool,
) -> None:
    try:
        ref = ColumnRef.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid data reference at {path}.") from exc
    if ref.project_id != project_id or ref not in available_refs:
        raise ValueError(f"Invalid data reference at {path}.")
    allowed = {ColumnType.NUMBER, ColumnType.DATETIME} if x_axis else {ColumnType.NUMBER}
    if available_refs[ref] not in allowed:
        raise ValueError(f"Incompatible column type at {path}.")


def _validate_component_properties(
    component: dict[str, Any],
    path: str,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
) -> None:
    kind = component["kind"]
    role = component["role"]
    selector = component["selector"]
    properties = component["properties"]
    data = component["data"]
    _validate_json_value(selector, f"{path}.selector")
    _validate_json_value(properties, f"{path}.properties")
    _validate_json_value(data, f"{path}.data")
    for color_name in COLOR_PROPERTIES.intersection(properties):
        if properties[color_name] is None:
            continue
        try:
            normalize_color(properties[color_name])
        except ValueError as exc:
            raise ValueError(
                f"Invalid project field {path}.properties.{color_name}."
            ) from exc

    if kind == "figure":
        _require_string(properties.get("name", ""), f"{path}.properties.name")
        _require_string(properties.get("style"), f"{path}.properties.style", nonempty=True)
        _require_number(properties.get("dpi"), f"{path}.properties.dpi", positive=True)
        _require_pair(properties.get("size_inches"), f"{path}.properties.size_inches", positive=True)
        _require_bool(properties.get("frameon"), f"{path}.properties.frameon")
        _require_bool(
            properties.get("constrained_layout"),
            f"{path}.properties.constrained_layout",
        )
    elif kind == "axes":
        _require_pair(properties.get("xlim"), f"{path}.properties.xlim")
        _require_pair(properties.get("ylim"), f"{path}.properties.ylim")
        _require_quad(properties.get("position"), f"{path}.properties.position")
        _require_string(properties.get("xscale"), f"{path}.properties.xscale", nonempty=True)
        _require_string(properties.get("yscale"), f"{path}.properties.yscale", nonempty=True)
        aspect = properties.get("aspect")
        if not isinstance(aspect, str):
            _require_number(aspect, f"{path}.properties.aspect", positive=True)
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_bool(properties.get("autoscale_on"), f"{path}.properties.autoscale_on")
        try:
            ColorCycleState.from_dict(properties.get("color_cycle"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid project field {path}.properties.color_cycle: {exc}") from exc
        subplot = _expect_dict(data.get("subplot"), f"{path}.data.subplot")
        _require_int(subplot.get("layout_group"), f"{path}.data.subplot.layout_group")
        nrows = _require_int(subplot.get("nrows"), f"{path}.data.subplot.nrows", 1)
        ncols = _require_int(subplot.get("ncols"), f"{path}.data.subplot.ncols", 1)
        slot = _require_int(subplot.get("slot"), f"{path}.data.subplot.slot", 1)
        if slot > nrows * ncols:
            raise ValueError(f"Invalid subplot slot at {path}.data.subplot.slot.")
    elif kind == "axis":
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_string(properties.get("scale"), f"{path}.properties.scale", nonempty=True)
        _require_string(
            properties.get("ticks_position"),
            f"{path}.properties.ticks_position",
            nonempty=True,
        )
        _require_string(
            properties.get("label_position"),
            f"{path}.properties.label_position",
            nonempty=True,
        )
        _require_bool(properties.get("inverted"), f"{path}.properties.inverted")
    elif kind == "spine":
        _require_string(selector.get("name"), f"{path}.selector.name", nonempty=True)
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        position = _expect_list(properties.get("position"), f"{path}.properties.position")
        if len(position) != 2:
            raise ValueError(f"Invalid project field {path}.properties.position.")
        _require_number(properties.get("linewidth"), f"{path}.properties.linewidth")
        _require_string(
            properties.get("linestyle"), f"{path}.properties.linestyle", nonempty=True
        )
        bounds = properties.get("bounds")
        if bounds is not None:
            _require_pair(bounds, f"{path}.properties.bounds")
        alpha = properties.get("alpha")
        if alpha is not None and not 0 <= _require_number(
            alpha, f"{path}.properties.alpha"
        ) <= 1:
            raise ValueError(f"Invalid project field {path}.properties.alpha.")
    elif kind == "tick_group":
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_string(
            properties.get("direction"), f"{path}.properties.direction", nonempty=True
        )
        for key in ("length", "width", "pad"):
            if _require_number(properties.get(key), f"{path}.properties.{key}") < 0:
                raise ValueError(f"Invalid project field {path}.properties.{key}.")
    elif kind == "tick_label_group":
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_number(
            properties.get("fontsize"), f"{path}.properties.fontsize", positive=True
        )
        _require_number(properties.get("rotation"), f"{path}.properties.rotation")
        family = properties.get("fontfamily")
        if not isinstance(family, (str, list)):
            raise ValueError(
                f"Invalid project field {path}.properties.fontfamily."
            )
        if _require_number(properties.get("pad"), f"{path}.properties.pad") < 0:
            raise ValueError(f"Invalid project field {path}.properties.pad.")
    elif kind == "grid":
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_string(
            properties.get("linestyle"), f"{path}.properties.linestyle", nonempty=True
        )
        if _require_number(
            properties.get("linewidth"), f"{path}.properties.linewidth"
        ) < 0:
            raise ValueError(f"Invalid project field {path}.properties.linewidth.")
        alpha = properties.get("alpha")
        if alpha is not None:
            alpha_value = _require_number(alpha, f"{path}.properties.alpha")
            if not 0 <= alpha_value <= 1:
                raise ValueError(f"Invalid project field {path}.properties.alpha.")
    elif kind == "text":
        if role in {"title", "x_label", "y_label", "text"}:
            _require_string(properties.get("text"), f"{path}.properties.text")
            fontfamily = properties.get("fontfamily")
            if not isinstance(fontfamily, (str, list)):
                raise ValueError(
                    f"Invalid project field {path}.properties.fontfamily."
                )
            _require_number(properties.get("fontsize"), f"{path}.properties.fontsize", positive=True)
            _require_bool(properties.get("visible", True), f"{path}.properties.visible")
            _require_pair(properties.get("position"), f"{path}.properties.position")
            _require_bool(properties.get("usetex"), f"{path}.properties.usetex")
            weight = properties.get("fontweight")
            if isinstance(weight, bool) or not isinstance(weight, (str, int, float)):
                raise ValueError(
                    f"Invalid project field {path}.properties.fontweight."
                )
            _require_string(
                properties.get("fontstyle"), f"{path}.properties.fontstyle"
            )
            rotation = properties.get("rotation")
            if not isinstance(rotation, str):
                _require_number(rotation, f"{path}.properties.rotation")
            _require_string(
                properties.get("horizontalalignment"),
                f"{path}.properties.horizontalalignment",
                nonempty=True,
            )
            _require_string(
                properties.get("verticalalignment"),
                f"{path}.properties.verticalalignment",
                nonempty=True,
            )
            alpha = properties.get("alpha")
            if alpha is not None and not 0 <= _require_number(
                alpha, f"{path}.properties.alpha"
            ) <= 1:
                raise ValueError(f"Invalid project field {path}.properties.alpha.")
    elif kind == "legend":
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        location = properties.get("location")
        if isinstance(location, bool):
            raise ValueError(f"Invalid project field {path}.properties.location.")
        if isinstance(location, int):
            _require_int(location, f"{path}.properties.location")
        elif not isinstance(location, str):
            _require_pair(location, f"{path}.properties.loc")
        _require_int(properties.get("ncols"), f"{path}.properties.ncols", 1)
        _require_number(
            properties.get("fontsize"), f"{path}.properties.fontsize", positive=True
        )
        _require_bool(properties.get("frameon"), f"{path}.properties.frameon")
        framealpha = properties.get("framealpha")
        if framealpha is not None and not 0 <= _require_number(
            framealpha, f"{path}.properties.framealpha"
        ) <= 1:
            raise ValueError(f"Invalid project field {path}.properties.framealpha.")
        _require_string(properties.get("title"), f"{path}.properties.title")
    elif kind in CHART_KINDS:
        try:
            normalize_color(properties.get("color"))
        except ValueError as exc:
            raise ValueError(f"Invalid project field {path}.properties.color.") from exc
        _require_string(properties.get("label"), f"{path}.properties.label")
        if kind == "scatter":
            if _require_number(
                properties.get("size"), f"{path}.properties.size"
            ) < 0:
                raise ValueError(f"Invalid project field {path}.properties.size.")
            if _require_number(
                properties.get("linewidth"), f"{path}.properties.linewidth"
            ) < 0:
                raise ValueError(f"Invalid project field {path}.properties.linewidth.")
        if kind == "scatter":
            _require_string(properties.get("marker"), f"{path}.properties.marker", nonempty=True)
        if kind == "line":
            _require_string(
                properties.get("linestyle"),
                f"{path}.properties.linestyle",
                nonempty=True,
            )
            for key in ("linewidth", "markersize", "markeredgewidth"):
                if _require_number(
                    properties.get(key), f"{path}.properties.{key}"
                ) < 0:
                    raise ValueError(f"Invalid project field {path}.properties.{key}.")
            _require_string(
                properties.get("marker"), f"{path}.properties.marker", nonempty=True
            )
        alpha = properties.get("alpha")
        if alpha is not None and not 0 <= _require_number(
            alpha, f"{path}.properties.alpha"
        ) <= 1:
            raise ValueError(f"Invalid project field {path}.properties.alpha.")
        _require_bool(properties.get("visible"), f"{path}.properties.visible")
        _require_number(properties.get("zorder"), f"{path}.properties.zorder")

        if role in DATA_ROLES:
            _validate_ref(
                data.get("x_ref"), f"{path}.data.x_ref", project_id, available_refs, x_axis=True
            )
            _validate_ref(
                data.get("y_ref"), f"{path}.data.y_ref", project_id, available_refs, x_axis=False
            )
        if role == "line":
            x_values = _expect_list(data.get("x"), f"{path}.data.x")
            y_values = _expect_list(data.get("y"), f"{path}.data.y")
            if len(x_values) != len(y_values):
                raise ValueError(
                    f"Invalid project field {path}.data: x and y must have equal length."
                )
            for index, value in enumerate(x_values):
                _require_number(value, f"{path}.data.x[{index}]")
            for index, value in enumerate(y_values):
                _require_number(value, f"{path}.data.y[{index}]")
        elif role == "function_curve":
            _require_string(data.get("expression"), f"{path}.data.expression", nonempty=True)
            _require_number(data.get("x_start"), f"{path}.data.x_start")
            _require_number(data.get("x_stop"), f"{path}.data.x_stop")
        elif role == "interpolation":
            if data.get("method") not in interpolate_dict:
                raise ValueError(f"Unknown interpolation method at {path}.")
            _require_int(data.get("k"), f"{path}.data.k", 1)
            _require_int(data.get("samples"), f"{path}.data.samples", 2)
            if data.get("lam") is not None:
                _require_number(data["lam"], f"{path}.data.lam")
            _require_bool(data.get("lam_auto"), f"{path}.data.lam_auto")
        elif role == "fit_curve":
            if data.get("engine") not in {"Python", "Matlab"}:
                raise ValueError(f"Unknown fitting engine at {path}.")
            _require_string(data.get("expression"), f"{path}.data.expression")
            _require_number(data.get("x_start"), f"{path}.data.x_start")
            _require_number(data.get("x_stop"), f"{path}.data.x_stop")

    # PropertySpec is the shared runtime/schema contract.  Running every
    # persisted value through it here prevents a project from mutating Table
    # or Figure state before a Controller later discovers an invalid enum,
    # selector, marker, range, or property type.
    try:
        state = ComponentState.from_dict(component)
        controller_type = controller_type_for(state)
        specs = {
            key: spec
            for key, spec in controller_type.property_specs().items()
            if spec.persistent
        }
        missing_properties = set(specs) - set(properties)
        unknown_properties = set(properties) - set(specs)
        if missing_properties or unknown_properties:
            details = []
            if missing_properties:
                details.append(
                    f"missing {sorted(missing_properties)!r}"
                )
            if unknown_properties:
                details.append(
                    f"unknown {sorted(unknown_properties)!r}"
                )
            raise ComponentValidationError(
                "property keys are invalid: " + ", ".join(details)
            )
        for key, spec in specs.items():
            spec.normalize(properties[key])
        # Controller construction performs family-specific selector and
        # cross-property validation without resolving a Matplotlib target.
        controller_type(state)
    except (ComponentValidationError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid project field {path}: {exc}"
        ) from exc

    expected_data_fields = {
        "figure": set(),
        "axes": {"subplot"},
        "x_axis": set(),
        "y_axis": set(),
        "spine": set(),
        "major_tick": set(),
        "minor_tick": set(),
        "major_tick_label": set(),
        "minor_tick_label": set(),
        "grid": set(),
        "title": set(),
        "x_label": set(),
        "y_label": set(),
        "text": set(),
        "legend": set(),
        "line": {"x", "y"},
        "function_curve": {"expression", "x_start", "x_stop"},
        "data_plot": {"x_ref", "y_ref"},
        "scatter": {"x_ref", "y_ref"},
        "interpolation": {
            "x_ref",
            "y_ref",
            "method",
            "k",
            "samples",
            "lam",
            "lam_auto",
        },
        "fit_curve": {
            "x_ref",
            "y_ref",
            "engine",
            "fit_type",
            "fit_options",
            "fit_result",
            "expression",
            "x_start",
            "x_stop",
        },
    }[role]
    if set(data) != expected_data_fields:
        raise ValueError(
            f"Invalid project field {path}.data: expected fields "
            f"{sorted(expected_data_fields)!r}."
        )


def _validate_parent(component: dict[str, Any], parent: dict[str, Any] | None, path: str) -> None:
    kind = component["kind"]
    role = component["role"]
    selector = component["selector"]
    if kind == "figure":
        if parent is not None:
            raise ValueError("The figure root must not have a parent.")
        if selector.get("scope") != "figure":
            raise ValueError(f"Invalid semantic selector at {path}.selector.")
        return
    if parent is None:
        raise ValueError(f"Missing parent component at {path}.parent_id.")

    parent_kind = parent["kind"]
    if kind == "axes":
        valid = parent_kind == "figure"
    elif kind in {"axis", "spine", "legend"}:
        valid = parent_kind == "axes"
    elif kind == "tick_group":
        valid = parent_kind == "axis"
    elif kind == "tick_label_group":
        valid = parent_kind == "tick_group"
    elif kind == "grid":
        valid = parent_kind == "axis"
    elif kind in CHART_KINDS:
        valid = parent_kind == "axes"
    elif role == "title":
        valid = parent_kind == "axes"
    elif role in {"x_label", "y_label"}:
        valid = parent_kind == "axis"
    else:
        valid = parent_kind in {"figure", "axes"}
    if not valid:
        raise ValueError(
            f"Invalid parent kind {parent_kind!r} for {kind}/{role} at {path}."
        )

    if kind == "axes":
        _require_int(selector.get("index"), f"{path}.selector.index")
    if kind == "axis":
        expected = "x" if role == "x_axis" else "y"
        if selector.get("axis") != expected:
            raise ValueError(f"Invalid semantic selector at {path}.selector.")
    if kind in {"tick_group", "tick_label_group", "grid"}:
        axis_name = selector.get("axis")
        level = selector.get("level")
        if axis_name not in {"x", "y"} or level not in LEVELS:
            raise ValueError(f"Invalid semantic selector at {path}.selector.")
        parent_axis = parent["selector"].get("axis")
        if kind == "tick_label_group":
            parent_axis = parent["selector"].get("axis")
            if parent["selector"].get("level") != level:
                raise ValueError(f"Mismatched tick label level at {path}.selector.")
        if parent_axis != axis_name:
            raise ValueError(f"Mismatched axis selector at {path}.selector.")
        if kind == "tick_group" and role != f"{level}_tick":
            raise ValueError(f"Mismatched tick role at {path}.role.")
        if kind == "tick_label_group" and role != f"{level}_tick_label":
            raise ValueError(f"Mismatched tick label role at {path}.role.")
    if role in {"x_label", "y_label"}:
        expected = "x" if role == "x_label" else "y"
        if selector.get("axis") != expected or parent["selector"].get("axis") != expected:
            raise ValueError(f"Mismatched axis label selector at {path}.selector.")
    if kind == "spine" and not selector.get("name"):
        raise ValueError(f"Invalid semantic selector at {path}.selector.")
    if kind in CHART_KINDS or role == "text":
        object_id = selector.get("object_id")
        if object_id != component["id"]:
            raise ValueError(f"Invalid object selector at {path}.selector.object_id.")


def _require_fixed_axes_components(
    axes: dict[str, Any],
    children: dict[str, list[dict[str, Any]]],
) -> None:
    axes_id = axes["id"]
    direct = children.get(axes_id, [])
    axes_path = f"figure.components[{axes_id}]"
    axis_components = [
        child for child in direct if child["kind"] == "axis"
    ]
    axis_by_name = {
        child["selector"].get("axis"): child
        for child in axis_components
    }
    if (
        len(axis_components) != 2
        or set(axis_by_name) != {"x", "y"}
    ):
        raise ValueError(f"{axes_path} must contain exactly one x and one y axis.")
    spine_components = [
        child for child in direct if child["kind"] == "spine"
    ]
    spine_names = [
        child["selector"].get("name")
        for child in spine_components
    ]
    if (
        len(spine_components) != len(SPINE_NAMES)
        or set(spine_names) != set(SPINE_NAMES)
    ):
        raise ValueError(
            f"{axes_path} must contain exactly one of each standard spine."
        )
    if sum(child["role"] == "title" for child in direct) != 1:
        raise ValueError(f"{axes_path} must contain exactly one title component.")
    if sum(child["kind"] == "legend" for child in direct) != 1:
        raise ValueError(f"{axes_path} must contain exactly one legend component.")

    for axis_name, axis in axis_by_name.items():
        axis_children = children.get(axis["id"], [])
        label_role = f"{axis_name}_label"
        if sum(child["role"] == label_role for child in axis_children) != 1:
            raise ValueError(
                f"{axes_path}/{axis_name} must contain exactly one axis label component."
            )
        tick_components = [
            child
            for child in axis_children
            if child["kind"] == "tick_group"
        ]
        tick_by_level = {
            child["selector"].get("level"): child
            for child in tick_components
        }
        grid_components = [
            child
            for child in axis_children
            if child["kind"] == "grid"
        ]
        grid_levels = [
            child["selector"].get("level")
            for child in grid_components
        ]
        if (
            len(tick_components) != len(LEVELS)
            or set(tick_by_level) != set(LEVELS)
            or len(grid_components) != len(LEVELS)
            or set(grid_levels) != set(LEVELS)
        ):
            raise ValueError(
                f"{axes_path}/{axis_name} must contain major/minor tick and grid components."
            )
        for level, tick in tick_by_level.items():
            labels = [
                child
                for child in children.get(tick["id"], [])
                if child["kind"] == "tick_label_group"
                and child["selector"].get("level") == level
            ]
            if len(labels) != 1:
                raise ValueError(
                    f"{axes_path}/{axis_name}/{level} must contain one tick-label group."
                )


def validate_v6_figure(
    figure_snapshot: Any,
    available_refs: dict[ColumnRef, ColumnType],
    project_id: str,
    project_name: str | None = None,
) -> None:
    figure = _expect_dict(figure_snapshot, "figure")
    if set(figure) != {"root_component_id", "components"}:
        raise ValueError(
            "Schema v6 figure must contain only root_component_id and components."
        )
    root_id = figure.get("root_component_id")
    if not isinstance(root_id, str) or not root_id.strip():
        raise ValueError("figure.root_component_id must be a non-empty string.")

    raw_components = _expect_list(figure.get("components"), "figure.components")
    components: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    for index, raw in enumerate(raw_components):
        path = f"figure.components[{index}]"
        component = _component_state_dict(raw, path)
        component_id = component["id"]
        if component_id in by_id:
            raise ValueError(f"Duplicate component id at {path}: {component_id}")
        by_id[component_id] = component
        paths[component_id] = path
        components.append(component)

    roots = [
        component
        for component in components
        if component["parent_id"] is None
    ]
    if len(roots) != 1 or roots[0]["id"] != root_id or roots[0]["kind"] != "figure":
        raise ValueError("Schema v6 requires one Figure root matching root_component_id.")

    selector_keys = set()
    children: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        path = paths[component["id"]]
        parent_id = component["parent_id"]
        parent = by_id.get(parent_id) if parent_id is not None else None
        if parent_id is not None and parent is None:
            raise ValueError(f"Unknown parent component at {path}.parent_id: {parent_id}")
        _validate_parent(component, parent, path)
        _validate_component_properties(component, path, available_refs, project_id)
        if parent_id is not None:
            children.setdefault(parent_id, []).append(component)
        selector_key = (
            parent_id,
            component["kind"],
            json.dumps(component["selector"], ensure_ascii=False, sort_keys=True),
        )
        if selector_key in selector_keys:
            raise ValueError(f"Duplicate semantic selector at {path}.selector.")
        selector_keys.add(selector_key)

    visit_state: dict[str, int] = {}

    def visit(component_id: str) -> None:
        state = visit_state.get(component_id, 0)
        if state == 1:
            raise ValueError("Component hierarchy contains a cycle.")
        if state == 2:
            return
        visit_state[component_id] = 1
        parent_id = by_id[component_id]["parent_id"]
        if parent_id is not None:
            visit(parent_id)
        visit_state[component_id] = 2

    for component_id in by_id:
        visit(component_id)

    axes_components = [component for component in components if component["kind"] == "axes"]
    axes_indexes = sorted(component["selector"]["index"] for component in axes_components)
    if axes_indexes != list(range(len(axes_components))):
        raise ValueError("Axes semantic indexes must be contiguous from zero.")
    for axes in axes_components:
        _require_fixed_axes_components(axes, children)

    layout_groups: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for axes in axes_components:
        subplot = axes["data"]["subplot"]
        layout_groups.setdefault(subplot["layout_group"], []).append(
            (axes["selector"]["index"], subplot)
        )
    for group, entries in layout_groups.items():
        shapes = {(entry["nrows"], entry["ncols"]) for _index, entry in entries}
        slots = [entry["slot"] for _index, entry in entries]
        if len(shapes) != 1 or len(slots) != len(set(slots)):
            raise ValueError(f"Invalid subplot layout group {group}.")
        indexes = sorted(index for index, _entry in entries)
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            raise ValueError(f"Subplot layout group {group} must use contiguous axes indexes.")

    chart_orders = [
        component["order"]
        for component in components
        if component["kind"] in CHART_KINDS
    ]
    if len(chart_orders) != len(set(chart_orders)):
        raise ValueError("Chart component order values must be unique.")

    if project_name is not None:
        saved_name = roots[0]["properties"].get("name", "")
        if saved_name != project_name:
            raise ValueError("Project and Figure component names must match.")


def _component_children(
    components: Iterable[dict[str, Any]],
) -> dict[str | None, list[dict[str, Any]]]:
    children: dict[str | None, list[dict[str, Any]]] = {}
    for component in components:
        children.setdefault(component["parent_id"], []).append(component)
    for values in children.values():
        values.sort(key=lambda component: (component["order"], component["id"]))
    return children


def v6_figure_to_legacy(figure_snapshot: dict[str, Any]) -> dict[str, Any]:
    figure = deepcopy(_expect_dict(figure_snapshot, "figure"))
    components = [
        _component_state_dict(raw, f"figure.components[{index}]")
        for index, raw in enumerate(_expect_list(figure.get("components"), "figure.components"))
    ]
    by_id = {component["id"]: component for component in components}
    root_id = figure.get("root_component_id")
    root = by_id.get(root_id)
    if root is None or root["kind"] != "figure":
        raise ValueError("Schema v6 Figure root is missing.")
    children = _component_children(components)
    root_properties = root["properties"]

    axes_components = sorted(
        (component for component in components if component["kind"] == "axes"),
        key=lambda component: component["selector"].get("index", component["order"]),
    )
    axes_indexes = {
        component["id"]: int(component["selector"]["index"])
        for component in axes_components
    }
    layouts: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for axes in axes_components:
        subplot = axes["data"]["subplot"]
        layouts.setdefault(int(subplot["layout_group"]), []).append(
            (axes_indexes[axes["id"]], subplot)
        )
    legacy_layouts = []
    for _group, group_entries in sorted(
        layouts.items(),
        key=lambda item: min(index for index, _entry in item[1]),
    ):
        entries = sorted(group_entries)
        first_index, first = entries[0]
        legacy_layouts.append({
            "nrows": int(first["nrows"]),
            "ncols": int(first["ncols"]),
            "start_index": first_index,
            "count": len(entries),
            "slots": [int(entry["slot"]) for _index, entry in entries],
        })

    axes_records: list[dict[str, Any]] = []
    for axes in axes_components:
        axes_id = axes["id"]
        direct = children.get(axes_id, [])
        axis_components = {
            component["selector"].get("axis"): component
            for component in direct
            if component["kind"] == "axis"
        }
        x_axis = axis_components.get("x")
        y_axis = axis_components.get("y")

        def axis_label(axis_component: dict[str, Any] | None, role: str) -> dict[str, Any]:
            if axis_component is None:
                return {}
            for candidate in children.get(axis_component["id"], []):
                if candidate["role"] == role:
                    return candidate["properties"]
            return {}

        x_label = axis_label(x_axis, "x_label")
        y_label = axis_label(y_axis, "y_label")

        ticks: dict[str, dict[str, Any]] = {"x": {}, "y": {}}
        tick_labels: dict[str, dict[str, Any]] = {"x": {}, "y": {}}
        grids: dict[str, dict[str, Any]] = {"x": {}, "y": {}}
        for axis_name, axis_component in axis_components.items():
            for axis_child in children.get(axis_component["id"], []):
                level = axis_child["selector"].get("level")
                if level not in LEVELS:
                    continue
                if axis_child["kind"] == "tick_group":
                    ticks[axis_name][level] = deepcopy(
                        axis_child["properties"]
                    )
                    label_component = next(
                        (
                            item
                            for item in children.get(axis_child["id"], [])
                            if item["kind"] == "tick_label_group"
                        ),
                        None,
                    )
                    if label_component is not None:
                        tick_labels[axis_name][level] = deepcopy(
                            label_component["properties"]
                        )
                elif axis_child["kind"] == "grid":
                    grids[axis_name][level] = deepcopy(
                        axis_child["properties"]
                    )
        spines = {
            str(component["selector"]["name"]): deepcopy(component["properties"])
            for component in direct
            if component["kind"] == "spine"
        }
        legend_component = next(
            (component for component in direct if component["kind"] == "legend"),
            None,
        )
        title_component = next(
            (component for component in direct if component["role"] == "title"),
            None,
        )
        legend_properties = (
            deepcopy(legend_component["properties"])
            if legend_component
            else {}
        )
        if "location" in legend_properties:
            legend_properties["loc"] = legend_properties.pop("location")
        label_family = x_label.get("fontfamily", y_label.get("fontfamily", ""))
        label_size = x_label.get("fontsize", y_label.get("fontsize", 10.0))
        axes_records.append({
            "index": axes_indexes[axes_id],
            "color_cycle": deepcopy(axes["properties"].get("color_cycle")),
            "xlim": deepcopy(axes["properties"].get("xlim", [0.0, 1.0])),
            "ylim": deepcopy(axes["properties"].get("ylim", [0.0, 1.0])),
            "position": deepcopy(
                axes["properties"].get("position", [0.125, 0.11, 0.775, 0.77])
            ),
            "aspect": deepcopy(axes["properties"].get("aspect", "auto")),
            "facecolor": axes["properties"].get("facecolor", "#FFFFFF"),
            "visible": bool(axes["properties"].get("visible", True)),
            "autoscale_on": bool(axes["properties"].get("autoscale_on", True)),
            "xlabel": str(x_label.get("text", "")),
            "ylabel": str(y_label.get("text", "")),
            "x_label": deepcopy(x_label),
            "y_label": deepcopy(y_label),
            "label_fontfamily": label_family,
            "label_fontsize": label_size,
            "x_label_position": deepcopy(x_label.get("position", [0.5, 0.0])),
            "y_label_position": deepcopy(y_label.get("position", [0.0, 0.5])),
            "xaxis_visible": bool(x_axis["properties"].get("visible", True)) if x_axis else True,
            "yaxis_visible": bool(y_axis["properties"].get("visible", True)) if y_axis else True,
            "xscale": str(axes["properties"].get(
                "xscale",
                x_axis["properties"].get("scale", "linear") if x_axis else "linear",
            )),
            "yscale": str(axes["properties"].get(
                "yscale",
                y_axis["properties"].get("scale", "linear") if y_axis else "linear",
            )),
            "spines": spines,
            "ticks": ticks,
            "tick_labels": tick_labels,
            "grids": grids,
            "title": deepcopy(title_component["properties"]) if title_component else {},
            "legend": legend_properties,
        })

    legacy: dict[str, Any] = {
        "name": str(root_properties.get("name", "")),
        "style": str(root_properties.get("style", "default")),
        "dpi": float(root_properties.get("dpi", 100)),
        "size_inches": deepcopy(root_properties.get("size_inches", [6.4, 4.8])),
        "facecolor": root_properties.get("facecolor", "#FFFFFF"),
        "edgecolor": root_properties.get("edgecolor", "#FFFFFF"),
        "frameon": bool(root_properties.get("frameon", True)),
        "constrained_layout": bool(
            root_properties.get("constrained_layout", False)
        ),
        "axes_count": len(axes_components),
        "axes_layouts": legacy_layouts,
        "axes": axes_records,
        "lines": [],
        "curves": [],
        "plots": [],
        "scatters": [],
        "interpolates": [],
        "fits": [],
        "texts": [],
    }

    for component in components:
        kind = component["kind"]
        role = component["role"]
        if kind in CHART_KINDS:
            axes_index = axes_indexes.get(component["parent_id"])
            if axes_index is None:
                raise ValueError(f"Chart component {component['id']} is not attached to an Axes.")
            visual = deepcopy(component["properties"])
            if kind == "line":
                visual["style"] = visual.pop("linestyle", "-")
                if role == "data_plot":
                    visual["size"] = visual.pop("markersize", 6.0)
            base = {
                "color_order": int(component["order"]),
                "axes_index": axes_index,
                "object_id": component["id"],
                **visual,
                **deepcopy(component["data"]),
            }
            if role == "line":
                legacy["lines"].append(base)
            elif role == "function_curve":
                legacy["curves"].append(base)
            elif role == "data_plot":
                legacy["plots"].append(base)
            elif role == "scatter":
                legacy["scatters"].append(base)
            elif role == "interpolation":
                legacy["interpolates"].append(base)
            elif role == "fit_curve":
                legacy["fits"].append(base)
        elif kind == "text" and role == "text":
            parent = by_id.get(component["parent_id"])
            text_record = deepcopy(component["properties"])
            position = text_record.pop("position", [0.5, 0.5])
            text_record["x"] = position[0]
            text_record["y"] = position[1]
            text_record.pop("visible", None)
            text_record["object_id"] = component["id"]
            if parent and parent["kind"] == "figure":
                text_record["scope"] = "figure"
            elif parent and parent["kind"] == "axes":
                text_record["scope"] = "axes"
                text_record["axes_index"] = axes_indexes[parent["id"]]
            else:
                raise ValueError(f"Text component {component['id']} has an invalid parent.")
            legacy["texts"].append(text_record)

    for collection in (
        "lines",
        "curves",
        "plots",
        "scatters",
        "interpolates",
        "fits",
    ):
        legacy[collection].sort(key=lambda record: (record["color_order"], record.get("object_id", "")))
    return legacy
