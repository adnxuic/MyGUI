"""Helpers for registering a complete semantic Figure component tree."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure

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


def _subplot_data(
    axes: Axes, index: int, layout_group: int
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "layout_group": layout_group,
        "nrows": 1,
        "ncols": 1,
        "slot": 1,
    }
    get_subplotspec = getattr(axes, "get_subplotspec", None)
    if not callable(get_subplotspec):
        return {"subplot": data}
    try:
        subplot_spec = get_subplotspec()
        grid_spec = subplot_spec.get_gridspec()
        data.update(
            nrows=int(grid_spec.nrows),
            ncols=int(grid_spec.ncols),
            slot=int(subplot_spec.num1) + 1,
        )
    except (AttributeError, TypeError, ValueError):
        pass
    return {"subplot": data}


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
    figure_state = ComponentState(
        id=figure_id,
        kind=ComponentKind.FIGURE,
        role=ComponentRole.FIGURE,
        order=0,
        selector={"scope": "figure"},
        properties=FigureController.default_properties(),
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

    layout_groups: dict[int, int] = {}
    chart_order = 0
    for axes_index, axes in enumerate(figure.axes):
        path = f"figure/axes/{axes_index}"
        axes_id = make_id(path)
        try:
            grid_key = id(axes.get_subplotspec().get_gridspec())
        except (AttributeError, TypeError):
            grid_key = id(axes)
        if grid_key not in layout_groups:
            layout_groups[grid_key] = len(layout_groups)
        axes_state = ComponentState(
            id=axes_id,
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
            parent_id=figure_id,
            order=axes_index,
            selector={"index": axes_index},
            properties=AxesController.default_properties(),
            data=_subplot_data(axes, axes_index, layout_groups[grid_key]),
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
