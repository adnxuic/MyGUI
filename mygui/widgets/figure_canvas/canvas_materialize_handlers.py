"""Canvas-owned materializer handlers that call public creation APIs."""

from __future__ import annotations

from typing import Any, Protocol

from mygui.database import ColumnRef, DataPreprocessSpec, resolve_preprocessed_pair
from mygui.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    FitEngine,
)
from mygui.figuremodify.components.property_values import marker_value
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from mygui.widgets.figure_canvas.component_materializers import ComponentMaterializer


class CanvasMaterializeHost(Protocol):
    """Canvas surface used by restore materializers."""

    component_registry: Any
    repository: Any
    root_component_id: str
    component_materializers: Any

    def add_in_axes(self, spec: Any, *, object_id: str | None = None) -> Any:
        ...

    def add_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_component_line(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_plot(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_scatter(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_pseudocolor(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_heatmap(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_contour(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_colorbar(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_marks(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_line(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_band(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_interpolate_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_fit_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_text(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_global_text(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_annotation(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def _materialize_zoom_in_axes(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_image_in_axes(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_function_curve(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_line(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_data_plot(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_scatter(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_field_2d(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_colorbar(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_reference_marks(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_reference_line(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_reference_band(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_interpolation(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_fit(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_text(self, state: Any, _transaction: Any) -> None:
        ...

    def _materialize_annotation(self, state: Any, _transaction: Any) -> None:
        ...


def _linestyle_from_state(state) -> Any:
    pattern = state.properties.get("linestyle", {"kind": "preset", "value": "-"})
    if pattern.get("kind") == "preset":
        return pattern.get("value", "-")
    return (pattern["offset"], pattern["dashes"])


def materializer_pair(host: CanvasMaterializeHost, state, *, preserve_gaps: bool):
    x_ref = ColumnRef.from_dict(state.data["x_ref"])
    y_ref = ColumnRef.from_dict(state.data["y_ref"])
    preprocess = DataPreprocessSpec.from_dict(state.data["preprocess"])
    pair = resolve_preprocessed_pair(
        host.repository,
        x_ref,
        y_ref,
        preprocess,
        preserve_gaps=preserve_gaps,
    )
    return x_ref, y_ref, preprocess, pair


def materialize_zoom_in_axes(host: CanvasMaterializeHost, state, _transaction) -> None:
    if state.role is not ComponentRole.IN_AXES_ZOOM:
        raise ValueError("Zoom materializer requires an in-axes Zoom state.")
    properties = state.properties
    spec = ZoomInAxesCreateSpec(
        bounds=tuple(properties["bounds"]),
        xlim=tuple(properties["xlim"]),
        ylim=tuple(properties["ylim"]),
        facecolor=properties["facecolor"],
        edgecolor=properties["edgecolor"],
        linewidth=properties["linewidth"],
        indicator_color=properties["region_color"],
        indicator_linestyle=(
            properties["region_linestyle"].get("value", "-")
            if isinstance(properties["region_linestyle"], dict)
            else properties["region_linestyle"]
        ),
        indicator_linewidth=properties["region_linewidth"],
        indicator_alpha=properties["region_alpha"],
        visible=properties["visible"],
        zorder=properties["zorder"],
        frameon=properties["frameon"],
        ticks_visible=properties["ticks_visible"],
        region_visible=properties["region_visible"],
        connectors_visible=any(item["visible"] for item in properties["connectors"]),
    )
    host.add_in_axes(spec, object_id=state.id)


def materialize_image_in_axes(host: CanvasMaterializeHost, state, _transaction) -> None:
    if state.role is not ComponentRole.IN_AXES_IMAGE:
        raise ValueError("Image materializer requires an in-axes Image state.")
    properties = state.properties
    data = state.data
    spec = ImageInAxesCreateSpec(
        bounds=tuple(properties["bounds"]),
        filename=data["filename"],
        mime_type=data["mime_type"],
        payload_base64=data["payload_base64"],
        facecolor=properties["facecolor"],
        edgecolor=properties["edgecolor"],
        linewidth=properties["linewidth"],
        opacity=properties["opacity"],
        fit_mode=properties["fit_mode"],
        interpolation=properties["interpolation"],
        origin=properties["origin"],
        extent=properties["extent"],
        resample=properties["resample"],
        filternorm=properties["filternorm"],
        filterrad=properties["filterrad"],
        interpolation_stage=properties["interpolation_stage"],
        image_visible=properties["image_visible"],
        image_zorder=properties["image_zorder"],
        image_clip_on=properties["image_clip_on"],
        image_rasterized=properties["image_rasterized"],
        image_in_layout=properties["image_in_layout"],
        image_snap=properties["image_snap"],
        image_gid=properties["image_gid"],
        image_url=properties["image_url"],
        visible=properties["visible"],
        zorder=properties["zorder"],
        frameon=properties["frameon"],
    )
    host.add_in_axes(spec, object_id=state.id)


def materialize_function_curve(host: CanvasMaterializeHost, state, _transaction) -> None:
    style = _linestyle_from_state(state)
    host.add_curve(
        state.data["expression"],
        state.data["x_start"],
        state.data["x_stop"],
        style,
        state.properties.get("color", "black"),
        state.properties.get("label", ""),
        object_id=state.id,
        color_order=state.order,
    )


def materialize_line(host: CanvasMaterializeHost, state, _transaction) -> None:
    style = _linestyle_from_state(state)
    host.add_component_line(
        state.data.get("x", []),
        state.data.get("y", []),
        style,
        state.properties.get("color", "black"),
        state.properties.get("label", ""),
        object_id=state.id,
        color_order=state.order,
    )


def materialize_data_plot(host: CanvasMaterializeHost, state, _transaction) -> None:
    x_ref, y_ref, preprocess, pair = materializer_pair(
        host,
        state,
        preserve_gaps=True,
    )
    style = _linestyle_from_state(state)
    host.add_plot(
        pair.x,
        pair.y,
        style,
        state.properties.get("markersize", 2.0),
        state.properties.get("color", "black"),
        state.properties.get("label", ""),
        x_ref,
        y_ref,
        object_id=state.id,
        color_order=state.order,
        preprocess=preprocess,
    )


def materialize_scatter(host: CanvasMaterializeHost, state, _transaction) -> None:
    x_ref, y_ref, preprocess, pair = materializer_pair(
        host,
        state,
        preserve_gaps=False,
    )
    host.add_scatter(
        pair.x,
        pair.y,
        state.properties.get("size", 20.0),
        state.properties.get("color", "black"),
        marker_value(state.properties.get("marker", {"kind": "symbol", "value": "o"})),
        state.properties.get("label", ""),
        x_ref,
        y_ref,
        object_id=state.id,
        color_order=state.order,
        preprocess=preprocess,
        color_ref=(
            None
            if state.data.get("color_ref") is None
            else ColumnRef.from_dict(state.data["color_ref"])
        ),
        size_ref=(
            None
            if state.data.get("size_ref") is None
            else ColumnRef.from_dict(state.data["size_ref"])
        ),
        color_mapping=state.properties["color_mapping"],
        size_mapping=state.properties["size_mapping"],
    )


def materialize_field_2d(host: CanvasMaterializeHost, state, _transaction) -> None:
    if state.kind is not ComponentKind.FIELD_2D:
        raise ValueError("FIELD_2D materializer requires a field_2d state.")
    adder = {
        ComponentRole.PSEUDOCOLOR: host.add_pseudocolor,
        ComponentRole.HEATMAP: host.add_heatmap,
        ComponentRole.CONTOUR: host.add_contour,
    }.get(state.role)
    if adder is None:
        raise ValueError(f"Unsupported FIELD_2D role {state.role!r}.")
    adder(
        ColumnRef.from_dict(state.data["x_ref"]),
        ColumnRef.from_dict(state.data["y_ref"]),
        ColumnRef.from_dict(state.data["z_ref"]),
        state.properties,
        object_id=state.id,
        color_order=state.order,
        announce=False,
    )


def materialize_colorbar(host: CanvasMaterializeHost, state, _transaction) -> None:
    if (
        state.kind is not ComponentKind.COLORBAR
        or state.role is not ComponentRole.COLORBAR
    ):
        raise ValueError("Colorbar materializer requires a Colorbar state.")
    source_id = state.data.get("source_component_id")
    if not isinstance(source_id, str) or source_id not in host.component_registry:
        raise ValueError("Colorbar source component is unavailable.")
    host.add_colorbar(
        source_id,
        state.properties,
        object_id=state.id,
        component_order=state.order,
        announce=False,
    )


def materialize_reference_marks(host: CanvasMaterializeHost, state, _transaction) -> None:
    if (
        state.kind is not ComponentKind.REFERENCE_MARKS
        or state.role is not ComponentRole.REFLECTION_POSITIONS
    ):
        raise ValueError(
            "Reference Marks materializer requires Reflection Positions."
        )
    host.add_reference_marks(
        state.data["positions"],
        state.properties,
        object_id=state.id,
        component_order=state.order,
        announce=False,
        position_ref=state.data.get("position_ref"),
        placement=state.data.get("placement"),
    )


def materialize_reference_line(host: CanvasMaterializeHost, state, _transaction) -> None:
    if (
        state.kind is not ComponentKind.REFERENCE_GUIDE
        or state.role is not ComponentRole.REFERENCE_LINE
    ):
        raise ValueError(
            "Reference Line materializer requires a Reference Line state."
        )
    host.add_reference_line(
        state.properties,
        object_id=state.id,
        component_order=state.order,
        announce=False,
    )


def materialize_reference_band(host: CanvasMaterializeHost, state, _transaction) -> None:
    if (
        state.kind is not ComponentKind.REFERENCE_GUIDE
        or state.role is not ComponentRole.REFERENCE_BAND
    ):
        raise ValueError(
            "Reference Band materializer requires a Reference Band state."
        )
    host.add_reference_band(
        state.properties,
        object_id=state.id,
        component_order=state.order,
        announce=False,
    )


def materialize_interpolation(host: CanvasMaterializeHost, state, _transaction) -> None:
    x_ref, y_ref, preprocess, pair = materializer_pair(
        host,
        state,
        preserve_gaps=False,
    )
    host.add_interpolate_curve(
        pair.x,
        pair.y,
        x_ref,
        y_ref,
        state.data["method"],
        k=state.data.get("k", 3),
        label=state.properties.get("label", "interpolate"),
        color=state.properties.get("color", "black"),
        samples=state.data.get("samples", DEFAULT_INTERPOLATION_SAMPLES),
        lam=state.data.get("lam"),
        lam_auto=state.data.get("lam_auto", True),
        object_id=state.id,
        color_order=state.order,
        allow_empty=True,
        preprocess=preprocess,
        announce=False,
    )


def materialize_fit(host: CanvasMaterializeHost, state, _transaction) -> None:
    x_ref, y_ref, preprocess, pair = materializer_pair(
        host,
        state,
        preserve_gaps=False,
    )
    style = _linestyle_from_state(state)
    host.add_fit_curve(
        pair.x,
        pair.y,
        state.properties.get("color", "black"),
        state.properties.get("label", "fitting"),
        x_ref,
        y_ref,
        engine=state.data.get("engine", FitEngine.PYTHON.value),
        fit_type=state.data.get("fit_type"),
        fit_options=state.data.get("fit_options"),
        fit_result=state.data.get("fit_result"),
        expression=state.data.get("expression", ""),
        x_start=state.data.get("x_start"),
        x_stop=state.data.get("x_stop"),
        style=style,
        object_id=state.id,
        color_order=state.order,
        preprocess=preprocess,
    )


def materialize_text(host: CanvasMaterializeHost, state, _transaction) -> None:
    properties = state.properties
    position = properties.get("position", (0.0, 0.0))
    family = properties.get("fontfamily", "sans-serif")
    if isinstance(family, (list, tuple)):
        family = family[0] if family else "sans-serif"
    kwargs = dict(
        x=float(position[0]),
        y=float(position[1]),
        text=properties.get("text", ""),
        fontfamily=family,
        fontsize=properties.get("fontsize", 10.0),
        usetex=properties.get("usetex", False),
        object_id=state.id,
    )
    if state.parent_id == host.root_component_id:
        host.add_global_text(**kwargs)
    else:
        host.add_text(**kwargs)


def materialize_annotation(host: CanvasMaterializeHost, state, _transaction) -> None:
    if (
        state.kind is not ComponentKind.ANNOTATION
        or state.role is not ComponentRole.ANNOTATION
    ):
        raise ValueError("Annotation materializer requires an Annotation state.")
    host.add_annotation(
        state.properties,
        axes_id=state.parent_id,
        object_id=state.id,
        component_order=state.order,
        announce=False,
    )


def register_canvas_materializers(host: CanvasMaterializeHost, expected_phases) -> None:
    """Register Canvas-bound handlers on the generic materializer registry."""

    declarations = (
        ComponentMaterializer(
            (ComponentKind.IN_AXES, ComponentRole.IN_AXES_ZOOM),
            host._materialize_zoom_in_axes,
            expected_phases[
                (ComponentKind.IN_AXES, ComponentRole.IN_AXES_ZOOM)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE),
            host._materialize_image_in_axes,
            expected_phases[
                (ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE),
            host._materialize_function_curve,
            expected_phases[
                (ComponentKind.LINE, ComponentRole.FUNCTION_CURVE)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.LINE),
            host._materialize_line,
            expected_phases[(ComponentKind.LINE, ComponentRole.LINE)],
        ),
        ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.DATA_PLOT),
            host._materialize_data_plot,
            expected_phases[
                (ComponentKind.LINE, ComponentRole.DATA_PLOT)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.SCATTER, ComponentRole.SCATTER),
            host._materialize_scatter,
            expected_phases[
                (ComponentKind.SCATTER, ComponentRole.SCATTER)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.FIELD_2D, ComponentRole.PSEUDOCOLOR),
            host._materialize_field_2d,
            expected_phases[
                (ComponentKind.FIELD_2D, ComponentRole.PSEUDOCOLOR)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.FIELD_2D, ComponentRole.HEATMAP),
            host._materialize_field_2d,
            expected_phases[
                (ComponentKind.FIELD_2D, ComponentRole.HEATMAP)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.FIELD_2D, ComponentRole.CONTOUR),
            host._materialize_field_2d,
            expected_phases[
                (ComponentKind.FIELD_2D, ComponentRole.CONTOUR)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.COLORBAR, ComponentRole.COLORBAR),
            host._materialize_colorbar,
            expected_phases[
                (ComponentKind.COLORBAR, ComponentRole.COLORBAR)
            ],
        ),
        ComponentMaterializer(
            (
                ComponentKind.REFERENCE_MARKS,
                ComponentRole.REFLECTION_POSITIONS,
            ),
            host._materialize_reference_marks,
            expected_phases[
                (
                    ComponentKind.REFERENCE_MARKS,
                    ComponentRole.REFLECTION_POSITIONS,
                )
            ],
        ),
        ComponentMaterializer(
            (
                ComponentKind.REFERENCE_GUIDE,
                ComponentRole.REFERENCE_LINE,
            ),
            host._materialize_reference_line,
            expected_phases[
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_LINE,
                )
            ],
        ),
        ComponentMaterializer(
            (
                ComponentKind.REFERENCE_GUIDE,
                ComponentRole.REFERENCE_BAND,
            ),
            host._materialize_reference_band,
            expected_phases[
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_BAND,
                )
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.INTERPOLATION),
            host._materialize_interpolation,
            expected_phases[
                (ComponentKind.LINE, ComponentRole.INTERPOLATION)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.FIT_CURVE),
            host._materialize_fit,
            expected_phases[
                (ComponentKind.LINE, ComponentRole.FIT_CURVE)
            ],
        ),
        ComponentMaterializer(
            (ComponentKind.TEXT, ComponentRole.TEXT),
            host._materialize_text,
            expected_phases[(ComponentKind.TEXT, ComponentRole.TEXT)],
        ),
        ComponentMaterializer(
            (ComponentKind.ANNOTATION, ComponentRole.ANNOTATION),
            host._materialize_annotation,
            expected_phases[
                (ComponentKind.ANNOTATION, ComponentRole.ANNOTATION)
            ],
        ),
    )
    for declaration in declarations:
        host.component_materializers.register(declaration)
    host.component_materializers.validate_complete(expected_phases)
