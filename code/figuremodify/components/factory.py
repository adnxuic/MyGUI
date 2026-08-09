"""Helpers for registering a complete semantic Figure component tree."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure

from code.figuremodify.axes_layout import stable_layout_id, stable_share_group

from .controllers import (
    AxesController,
    AxisLabelController,
    FigureController,
    GridController,
    LegendController,
    LineController,
    ScatterController,
    SpineController,
    TextController,
    TickGroupController,
    TickLabelGroupController,
    TitleController,
    XAxisController,
    YAxisController,
)
from .models import ComponentKind, ComponentRole, ComponentState
from .registry import ComponentRegistry


IdFactory = Callable[[str], str]


def _random_id(_path: str) -> str:
    return str(uuid4())


def _v9_layout_records(
    figure: Figure,
    figure_id: str,
) -> tuple[list[dict[str, Any]], dict[Axes, dict[str, Any]]]:
    """Describe an existing regular Figure with schema-v9 layout records."""

    groups: dict[int, list[tuple[int, Axes, Any, int, int]]] = {}
    standalone: list[tuple[int, Axes]] = []
    for index, axes in enumerate(figure.axes):
        try:
            subplot_spec = axes.get_subplotspec()
            grid_spec = subplot_spec.get_gridspec()
            if len(subplot_spec.rowspan) != 1 or len(subplot_spec.colspan) != 1:
                raise ValueError
            groups.setdefault(id(grid_spec), []).append(
                (
                    index,
                    axes,
                    grid_spec,
                    int(subplot_spec.rowspan.start),
                    int(subplot_spec.colspan.start),
                )
            )
        except (AttributeError, TypeError, ValueError):
            standalone.append((index, axes))

    definitions: list[dict[str, Any]] = []
    records: dict[Axes, dict[str, Any]] = {}
    group_number = 0
    for entries in groups.values():
        grid_spec = entries[0][2]
        layout_id = stable_layout_id(figure_id, group_number)
        group_number += 1
        params = grid_spec.get_subplot_params(figure)
        width_ratios = grid_spec.get_width_ratios() or [1.0] * int(grid_spec.ncols)
        height_ratios = grid_spec.get_height_ratios() or [1.0] * int(grid_spec.nrows)
        definitions.append(
            {
                "id": layout_id,
                "nrows": int(grid_spec.nrows),
                "ncols": int(grid_spec.ncols),
                "width_ratios": [float(value) for value in width_ratios],
                "height_ratios": [float(value) for value in height_ratios],
                "margins": {
                    "left": float(params.left),
                    "right": float(params.right),
                    "bottom": float(params.bottom),
                    "top": float(params.top),
                },
                "spacing": {
                    "wspace": float(params.wspace),
                    "hspace": float(params.hspace),
                },
            }
        )
        by_cell: dict[tuple[int, int], list[tuple[int, Axes]]] = {}
        for index, axes, _grid, row, column in entries:
            by_cell.setdefault((row, column), []).append((index, axes))
        for (row, column), members in by_cell.items():
            ordered_members = sorted(members)
            if len(ordered_members) > 2:
                raise ValueError(
                    "An existing Figure cell cannot contain more than one right Y Axes."
                )
            if len(ordered_members) == 2:
                primary_axes = ordered_members[0][1]
                secondary_axes = ordered_members[1][1]
                if not primary_axes.get_shared_x_axes().joined(
                    primary_axes,
                    secondary_axes,
                ):
                    raise ValueError(
                        "Overlapping existing Axes must form a supported right Y twin pair."
                    )
            for offset, (_index, axes) in enumerate(ordered_members):
                layer = "primary" if offset == 0 else "right_y"
                records[axes] = {
                    "subplot": {
                        "layout_id": layout_id,
                        "row": row,
                        "column": column,
                        "layer": layer,
                        "share_x_group": None,
                        "share_y_group": None,
                    }
                }

        for dimension, field in (("x", "share_x_group"), ("y", "share_y_group")):
            remaining = {axes for _index, axes, _grid, _row, _column in entries}
            groups_for_dimension: list[set[Axes]] = []
            while remaining:
                anchor = remaining.pop()
                grouper = (
                    anchor.get_shared_x_axes()
                    if dimension == "x"
                    else anchor.get_shared_y_axes()
                )
                connected = {anchor}
                changed = True
                while changed:
                    changed = False
                    for candidate in tuple(remaining):
                        if any(grouper.joined(member, candidate) for member in connected):
                            connected.add(candidate)
                            remaining.remove(candidate)
                            changed = True
                groups_for_dimension.append(connected)
            for number, members in enumerate(groups_for_dimension):
                if len(members) < 2:
                    continue
                group_id = stable_share_group(
                    layout_id,
                    dimension,
                    f"import-{number}",
                )
                for axes in members:
                    records[axes]["subplot"][field] = group_id

    for index, axes in standalone:
        layout_id = stable_layout_id(figure_id, group_number)
        group_number += 1
        left, bottom, width, height = axes.get_position().bounds
        definitions.append(
            {
                "id": layout_id,
                "nrows": 1,
                "ncols": 1,
                "width_ratios": [1.0],
                "height_ratios": [1.0],
                "margins": {
                    "left": float(left),
                    "right": float(left + width),
                    "bottom": float(bottom),
                    "top": float(bottom + height),
                },
                "spacing": {"wspace": 0.2, "hspace": 0.2},
            }
        )
        records[axes] = {
            "subplot": {
                "layout_id": layout_id,
                "row": 0,
                "column": 0,
                "layer": "primary",
                "share_x_group": None,
                "share_y_group": None,
            }
        }
    return definitions, records


def create_semantic_children(
    registry: ComponentRegistry,
    axes_id: str,
    axes: Axes,
    *,
    path: str = "axes",
    id_factory: IdFactory | None = None,
    start_order: int = 0,
) -> list[str]:
    """Register fixed Axis/Spine/Tick/Grid/Text/Legend children for an Axes."""

    make_id = id_factory or _random_id
    created: list[str] = []
    order = start_order

    def add(
        controller_type: type,
        kind: ComponentKind,
        role: ComponentRole,
        name: str,
        selector: dict[str, Any] | None = None,
        target: Any | None = None,
        parent_id: str | None = None,
    ) -> str:
        nonlocal order
        component_id = make_id(f"{path}/{name}")
        properties = controller_type.default_properties()
        if controller_type is LegendController and target is None:
            properties["visible"] = False
        state = ComponentState(
            id=component_id,
            kind=kind,
            role=role,
            parent_id=parent_id or axes_id,
            order=order,
            selector=selector or {},
            properties=properties,
        )
        controller = controller_type(state)
        registry.register(controller, target=target)
        try:
            controller.sync_from_target()
        except Exception:
            pass
        created.append(component_id)
        order += 1
        return component_id

    x_axis_id = add(
        XAxisController,
        ComponentKind.AXIS,
        ComponentRole.X_AXIS,
        "axis/x",
        {"axis": "x"},
    )
    y_axis_id = add(
        YAxisController,
        ComponentKind.AXIS,
        ComponentRole.Y_AXIS,
        "axis/y",
        {"axis": "y"},
    )
    axis_ids = {"x": x_axis_id, "y": y_axis_id}

    for side in ("left", "right", "top", "bottom"):
        add(
            SpineController,
            ComponentKind.SPINE,
            ComponentRole.SPINE,
            f"spine/{side}",
            {"name": side},
        )

    for axis_name in ("x", "y"):
        for level in ("major", "minor"):
            tick_role = (
                ComponentRole.MAJOR_TICK
                if level == "major"
                else ComponentRole.MINOR_TICK
            )
            label_role = (
                ComponentRole.MAJOR_TICK_LABEL
                if level == "major"
                else ComponentRole.MINOR_TICK_LABEL
            )
            selector = {"axis": axis_name, "level": level}
            tick_id = add(
                TickGroupController,
                ComponentKind.TICK_GROUP,
                tick_role,
                f"axis/{axis_name}/tick/{level}",
                selector,
                parent_id=axis_ids[axis_name],
            )
            add(
                TickLabelGroupController,
                ComponentKind.TICK_LABEL_GROUP,
                label_role,
                f"axis/{axis_name}/tick/{level}/label",
                selector,
                parent_id=tick_id,
            )
            add(
                GridController,
                ComponentKind.GRID,
                ComponentRole.GRID,
                f"axis/{axis_name}/grid/{level}",
                selector,
                parent_id=axis_ids[axis_name],
            )

    add(
        TitleController,
        ComponentKind.TEXT,
        ComponentRole.TITLE,
        "title",
        target=axes.title,
    )
    add(
        AxisLabelController,
        ComponentKind.TEXT,
        ComponentRole.X_LABEL,
        "axis/x/label",
        {"axis": "x"},
        axes.xaxis.label,
        x_axis_id,
    )
    add(
        AxisLabelController,
        ComponentKind.TEXT,
        ComponentRole.Y_LABEL,
        "axis/y/label",
        {"axis": "y"},
        axes.yaxis.label,
        y_axis_id,
    )
    add(
        LegendController,
        ComponentKind.LEGEND,
        ComponentRole.LEGEND,
        "legend",
        target=axes.get_legend(),
    )
    return created


def register_figure_components(
    figure: Figure,
    *,
    registry: ComponentRegistry | None = None,
    root_id: str | None = None,
    id_factory: IdFactory | None = None,
    include_artists: bool = True,
) -> ComponentRegistry:
    """Create controllers for an existing Figure.

    ``id_factory`` receives stable semantic paths.  Project IO can inject a
    deterministic UUID factory, while interactive figures default to UUID4.
    Existing line artists are registered with the generic ``line`` role;
    callers that know whether a line is a curve, plot, fit or interpolation
    should register that role directly instead.
    """

    result = registry or ComponentRegistry()
    make_id = id_factory or _random_id
    figure_id = root_id or make_id("figure")
    layout_definitions, subplot_records = _v9_layout_records(figure, figure_id)
    figure_state = ComponentState(
        id=figure_id,
        kind=ComponentKind.FIGURE,
        role=ComponentRole.FIGURE,
        order=0,
        selector={"scope": "figure"},
        properties=FigureController.default_properties(),
        data={"layouts": layout_definitions},
    )
    figure_controller = FigureController(figure_state)
    result.register(figure_controller, target=figure)
    figure_controller.sync_from_target()

    figure_text_order = len(figure.axes)
    for text_index, text in enumerate(figure.texts):
        text_id = make_id(f"figure/text/{text_index}")
        state = ComponentState(
            id=text_id,
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
            parent_id=figure_id,
            order=figure_text_order + text_index,
            selector={
                "index": text_index,
                "object_id": text_id,
                "scope": "figure",
            },
            properties=TextController.default_properties(),
        )
        controller = TextController(state)
        result.register(controller, target=text)
        controller.sync_from_target()
        text.set_gid(text_id)

    chart_order = 0
    for axes_index, axes in enumerate(figure.axes):
        path = f"figure/axes/{axes_index}"
        axes_id = make_id(path)
        axes_state = ComponentState(
            id=axes_id,
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
            parent_id=figure_id,
            order=axes_index,
            selector={"index": axes_index},
            properties=AxesController.default_properties(),
            data=subplot_records[axes],
        )
        axes_controller = AxesController(axes_state)
        result.register(axes_controller, target=axes)
        axes_controller.sync_from_target()
        next_order = len(
            create_semantic_children(
                result,
                axes_id,
                axes,
                path=path,
                id_factory=make_id,
            )
        )
        if not include_artists:
            continue

        for text_index, text in enumerate(axes.texts):
            text_id = make_id(f"{path}/text/{text_index}")
            state = ComponentState(
                id=text_id,
                kind=ComponentKind.TEXT,
                role=ComponentRole.TEXT,
                parent_id=axes_id,
                order=next_order,
                selector={
                    "index": text_index,
                    "object_id": text_id,
                },
                properties=TextController.default_properties(),
            )
            controller = TextController(state)
            result.register(controller, target=text)
            controller.sync_from_target()
            text.set_gid(text_id)
            next_order += 1

        for line_index, line in enumerate(axes.lines):
            line_id = make_id(f"{path}/line/{line_index}")
            state = ComponentState(
                id=line_id,
                kind=ComponentKind.LINE,
                role=ComponentRole.LINE,
                parent_id=axes_id,
                order=chart_order,
                selector={
                    "index": line_index,
                    "object_id": line_id,
                },
                properties=LineController.default_properties(),
                data={
                    "x": np.asarray(line.get_xdata()).tolist(),
                    "y": np.asarray(line.get_ydata()).tolist(),
                },
            )
            controller = LineController(state)
            result.register(controller, target=line)
            controller.sync_from_target()
            line.set_gid(line_id)
            next_order += 1
            chart_order += 1

        scatter_index = 0
        for collection_index, collection in enumerate(axes.collections):
            if not isinstance(collection, PathCollection):
                continue
            scatter_id = make_id(f"{path}/scatter/{scatter_index}")
            state = ComponentState(
                id=scatter_id,
                kind=ComponentKind.SCATTER,
                role=ComponentRole.SCATTER,
                parent_id=axes_id,
                order=chart_order,
                selector={
                    "index": collection_index,
                    "object_id": scatter_id,
                },
                properties=ScatterController.default_properties(),
            )
            controller = ScatterController(state)
            result.register(controller, target=collection)
            controller.sync_from_target()
            collection.set_gid(scatter_id)
            scatter_index += 1
            next_order += 1
            chart_order += 1

    result.validate_tree()
    return result
