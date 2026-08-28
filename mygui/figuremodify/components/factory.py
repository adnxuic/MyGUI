"""Helpers for registering a complete semantic Figure component tree."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any
from uuid import uuid4

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure

from mygui.figuremodify.axes_geometry import grid_geometry_record
from mygui.figuremodify.axes_layout import stable_layout_id, stable_share_group

from .controllers import (
    AxesController,
    AxisLabelController,
    ColorbarController,
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


def _layout_records(
    figure: Figure,
    figure_id: str,
    *,
    axes_values: list[Axes] | None = None,
) -> tuple[list[dict[str, Any]], dict[Axes, dict[str, Any]]]:
    """Describe an existing regular Figure with persisted layout records."""

    groups: dict[int, list[tuple[int, Axes, Any, int, int]]] = {}
    standalone: list[tuple[int, Axes]] = []
    for index, axes in enumerate(axes_values or list(figure.axes)):
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
                    },
                    "geometry": grid_geometry_record(),
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
            },
            "geometry": grid_geometry_record(),
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
        controller = controller_type(state, target=target)
        if target is not None:
            controller.sync_from_target(strict=True)
        registry.register(controller, target=target)
        created.append(component_id)
        order += 1
        return component_id

    x_axis_id = add(
        XAxisController,
        ComponentKind.AXIS,
        ComponentRole.X_AXIS,
        "axis/x",
        {"axis": "x"},
        target=axes.xaxis,
    )
    y_axis_id = add(
        YAxisController,
        ComponentKind.AXIS,
        ComponentRole.Y_AXIS,
        "axis/y",
        {"axis": "y"},
        target=axes.yaxis,
    )
    axis_ids = {"x": x_axis_id, "y": y_axis_id}

    for side in ("left", "right", "top", "bottom"):
        add(
            SpineController,
            ComponentKind.SPINE,
            ComponentRole.SPINE,
            f"spine/{side}",
            {"name": side},
            target=axes.spines[side],
        )

    for axis_name in ("x", "y"):
        axis_target = axes.xaxis if axis_name == "x" else axes.yaxis
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
                target=axis_target,
                parent_id=axis_ids[axis_name],
            )
            add(
                TickLabelGroupController,
                ComponentKind.TICK_LABEL_GROUP,
                label_role,
                f"axis/{axis_name}/tick/{level}/label",
                selector,
                target=axis_target,
                parent_id=tick_id,
            )
            add(
                GridController,
                ComponentKind.GRID,
                ComponentRole.GRID,
                f"axis/{axis_name}/grid/{level}",
                selector,
                target=axis_target,
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
    known_colorbars: list[tuple[Colorbar, Any]] = []
    seen_colorbars: set[int] = set()
    for axes in figure.axes:
        for mappable in (*tuple(axes.collections), *tuple(axes.images)):
            colorbar = getattr(mappable, "colorbar", None)
            if (
                isinstance(colorbar, Colorbar)
                and isinstance(colorbar.ax, Axes)
                and colorbar.ax.figure is figure
                and id(colorbar) not in seen_colorbars
            ):
                known_colorbars.append((colorbar, mappable))
                seen_colorbars.add(id(colorbar))
    auxiliary_axes = {colorbar.ax for colorbar, _source in known_colorbars}
    regular_axes = [axes for axes in figure.axes if axes not in auxiliary_axes]
    layout_definitions, subplot_records = _layout_records(
        figure,
        figure_id,
        axes_values=regular_axes,
    )
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

    figure_text_order = len(regular_axes)
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
            properties={
                **TextController.default_properties(),
                "coordinate_system": "figure",
            },
        )
        controller = TextController(state)
        result.register(controller, target=text)
        controller.sync_from_target()
        text.set_gid(text_id)

    chart_order = 0
    axes_ids_by_target: dict[int, str] = {}
    source_ids_by_target: dict[int, str] = {}
    for axes_index, axes in enumerate(regular_axes):
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
        axes_ids_by_target[id(axes)] = axes_id
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
            if collection.get_array() is not None:
                properties = deepcopy(state.properties)
                mapping = deepcopy(properties["color_mapping"])
                mapping["enabled"] = True
                mapping["cmap"] = collection.get_cmap().name
                properties["color_mapping"] = mapping
                state = state.clone(properties=properties)
            controller = ScatterController(state)
            result.register(controller, target=collection)
            controller.sync_from_target()
            collection.set_gid(scatter_id)
            source_ids_by_target[id(collection)] = scatter_id
            scatter_index += 1
            next_order += 1
            chart_order += 1

    for colorbar_index, (colorbar, source) in enumerate(known_colorbars):
        source_id = source_ids_by_target.get(id(source))
        owner = getattr(source, "axes", None)
        axes_id = axes_ids_by_target.get(id(owner))
        if source_id is None or axes_id is None:
            continue
        path = f"figure/axes/{regular_axes.index(owner)}/colorbar/{colorbar_index}"
        colorbar_id = make_id(path)
        properties = ColorbarController.default_properties()
        info = getattr(colorbar.ax, "_colorbar_info", {})
        properties.update(
            {
                "location": str(
                    info.get(
                        "location",
                        "right" if colorbar.orientation == "vertical" else "bottom",
                    )
                ),
                "fraction": float(info.get("fraction", 0.15)),
                "shrink": float(info.get("shrink", 1.0)),
                "aspect": float(info.get("aspect", 20.0)),
                "pad": float(info.get("pad", 0.05)),
                "extend": str(colorbar.extend),
                "spacing": str(colorbar.spacing),
                "drawedges": bool(colorbar.drawedges),
            }
        )
        order = max(
            (
                child.state.order
                for child in result.children(axes_id)
            ),
            default=-1,
        ) + 1
        state = ComponentState(
            id=colorbar_id,
            kind=ComponentKind.COLORBAR,
            role=ComponentRole.COLORBAR,
            parent_id=axes_id,
            order=order,
            selector={"object_id": colorbar_id},
            properties=properties,
            data={"source_component_id": source_id},
        )
        controller = ColorbarController(state)
        result.register(controller, target=colorbar)
        controller.sync_from_target(strict=True)

    result.validate_tree()
    return result
