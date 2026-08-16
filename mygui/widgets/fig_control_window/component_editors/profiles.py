"""Register the production editor profiles for Figure component roles."""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    CONTROLLER_TYPES,
    ROLES_BY_KIND,
)

from .chart_sections import FunctionCurveSection, InterpolationSection
from .fit_sections import (
    FitActionsSection,
    FitDisplayRangeSection,
    FitResultSection,
)
from .inspector import (
    EditorPlacement,
    EditorProfile,
    SectionSpec,
    TreePresentationSpec,
)
from .sections import (
    AxesLayoutSection,
    AxesLimitsSection,
    DataReferenceSection,
    ImageInAxesSourceSection,
    LegendLocationSection,
    LineAppearanceSection,
    PaletteSection,
    PropertySection,
    RawXYDataSection,
    ScatterAppearanceSection,
    ScatterMappingSection,
    TextContentSection,
    TextPositionSection,
    TextRenderSection,
    TextTransformSection,
    TextTypographySection,
)


def _properties(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys or None,
            parent=parent,
        )

    return factory


def _axes_limits(controller, context, parent):
    return AxesLimitsSection(
        controller,
        context=context,
        parent=parent,
    )


def _axes_layout(controller, context, parent):
    return AxesLayoutSection(controller, context=context, parent=parent)


def _axis_properties_for(keys):
    def factory(controller, context, parent):
        return _axis_properties(controller, context, parent, keys=keys)

    return factory


def _axis_properties(controller, context, parent, *, keys=None):
    def apply(properties):
        key, value = next(iter(properties.items()))
        if key != "scale":
            from mygui.figuremodify.components import ComponentMutation

            return context.registry.apply_transaction(
                (
                    ComponentMutation(
                        controller.component_id,
                        properties={key: value},
                    ),
                )
            )
        dimension = str(controller.state.selector["axis"])
        return context.axes_layout.apply_linked_axis(
            controller.state.parent_id,
            dimension,
            scale=value,
        )

    return PropertySection(
        controller,
        context=context,
        property_keys=keys,
        apply_properties=apply,
        parent=parent,
    )


def _line_appearance(controller, context, parent):
    return LineAppearanceSection(
        controller,
        context=context,
        parent=parent,
    )


def _scatter_appearance(controller, context, parent):
    return ScatterAppearanceSection(
        controller,
        context=context,
        parent=parent,
    )


def _scatter_mapping(controller, context, parent):
    return ScatterMappingSection(
        controller,
        context=context,
        parent=parent,
    )


def _raw_xy_data(controller, context, parent):
    return RawXYDataSection(
        controller,
        context=context,
        parent=parent,
    )


def _curve_definition(controller, context, parent):
    return FunctionCurveSection(
        controller,
        context=context,
        parent=parent,
    )


def _chart_data_references(controller, context, parent):
    return DataReferenceSection(
        controller,
        context=context,
        apply_references=(
            lambda target, x_ref, y_ref, preprocess, _axis:
            context.chart_data.set_refs(target, x_ref, y_ref, preprocess)
        ),
        success_message=(
            lambda axis:
            f"Chart {axis.upper()} data source updated."
        ),
        parent=parent,
    )


def _fit_data_references(controller, context, parent):
    return DataReferenceSection(
        controller,
        context=context,
        apply_references=(
            lambda target, x_ref, y_ref, preprocess, _axis:
            context.fitting.set_sources(target, x_ref, y_ref, preprocess)
        ),
        success_message=(
            lambda axis:
            f"Fit {axis.upper()} data source updated; "
            "run fitting to recompute."
        ),
        parent=parent,
    )


def _interpolation_data_references(controller, context, parent):
    def apply(target, x_ref, y_ref, preprocess, _axis):
        data = target.read_state().data
        return context.interpolation.configure(
            target,
            x_ref=x_ref,
            y_ref=y_ref,
            preprocess=preprocess,
            method=data["method"],
            k=data["k"],
            samples=data["samples"],
            lam=data["lam"],
            lam_auto=data["lam_auto"],
        )

    return DataReferenceSection(
        controller,
        context=context,
        apply_references=apply,
        success_message="Interpolation curve updated.",
        parent=parent,
    )


def _fit_actions(controller, context, parent):
    return FitActionsSection(
        controller,
        context=context,
        parent=parent,
    )


def _fit_result(controller, context, parent):
    return FitResultSection(
        controller,
        context=context,
        parent=parent,
    )


def _fit_range(controller, context, parent):
    return FitDisplayRangeSection(
        controller,
        context=context,
        parent=parent,
    )


def _interpolation_options(controller, context, parent):
    return InterpolationSection(
        controller,
        context=context,
        parent=parent,
    )


def _text_apply(controller, context):
    return lambda properties: context.text_rendering.apply(
        controller,
        properties,
    )


def _text_content(controller, context, parent):
    return TextContentSection(
        controller,
        context=context,
        apply_properties=_text_apply(controller, context),
        parent=parent,
    )


def _text_typography(controller, context, parent):
    return TextTypographySection(
        controller,
        context=context,
        apply_properties=_text_apply(controller, context),
        parent=parent,
    )


def _text_transform(controller, context, parent):
    return TextTransformSection(
        controller,
        context=context,
        apply_properties=_text_apply(controller, context),
        parent=parent,
    )


def _text_position(controller, context, parent):
    return TextPositionSection(
        controller,
        context=context,
        apply_properties=_text_apply(controller, context),
        parent=parent,
    )


def _text_render(controller, context, parent):
    return TextRenderSection(
        controller,
        context=context,
        parent=parent,
    )


TEXT_ADVANCED_KEYS = (
    "bbox",
    "antialiased",
    "label",
    "clip_on",
    "gid",
    "in_layout",
    "rasterized",
    "sketch_params",
    "snap",
    "url",
)


def _text_advanced(controller, context, parent):
    return PropertySection(
        controller,
        context=context,
        property_keys=TEXT_ADVANCED_KEYS,
        apply_properties=_text_apply(controller, context),
        parent=parent,
    )


def _image_in_axes_source(controller, context, parent):
    return ImageInAxesSourceSection(
        controller,
        context=context,
        parent=parent,
    )


def _ensure_legend_apply(controller, context):
    def apply(properties):
        return context.axes_commands.apply_legend_properties(
            controller,
            properties,
        )

    return apply


def _legend_title(controller, context, parent):
    return TextContentSection(
        controller,
        context=context,
        property_key="title",
        apply_properties=_ensure_legend_apply(controller, context),
        parent=parent,
    )


def _legend_typography(controller, context, parent):
    return PropertySection(
        controller,
        context=context,
        property_keys=("label_font", "title_font"),
        apply_properties=_ensure_legend_apply(controller, context),
        parent=parent,
    )


def _legend_location(controller, context, parent):
    return LegendLocationSection(
        controller,
        context=context,
        parent=parent,
    )


def _legend_frame(controller, context, parent):
    return PropertySection(
        controller,
        context=context,
        property_keys=(
            "frameon",
            "facecolor",
            "edgecolor",
            "framealpha",
            "fancybox",
            "shadow",
            "frame_linewidth",
            "frame_linestyle",
            "frame_hatch",
        ),
        apply_properties=_ensure_legend_apply(controller, context),
        parent=parent,
    )


LEGEND_DETAIL_KEYS = (
    "bbox_to_anchor",
    "mode",
    "alignment",
    "reverse",
    "markerfirst",
    "draggable",
    "draggable_update",
    "numpoints",
    "scatterpoints",
    "scatteryoffsets",
    "markerscale",
    "borderpad",
    "labelspacing",
    "handlelength",
    "handleheight",
    "handletextpad",
    "borderaxespad",
    "columnspacing",
)


def _legend_details(controller, context, parent):
    return PropertySection(
        controller,
        context=context,
        property_keys=LEGEND_DETAIL_KEYS,
        apply_properties=_ensure_legend_apply(controller, context),
        parent=parent,
    )


LEGEND_ADVANCED_KEYS = (
    "zorder",
    "alpha",
    "label",
    "clip_on",
    "gid",
    "in_layout",
    "rasterized",
    "sketch_params",
    "snap",
    "url",
)


def _legend_advanced(controller, context, parent):
    return PropertySection(
        controller,
        context=context,
        property_keys=LEGEND_ADVANCED_KEYS,
        apply_properties=_ensure_legend_apply(controller, context),
        parent=parent,
    )


def _palette(controller, context, parent):
    return PaletteSection(
        controller,
        context=context,
        parent=parent,
    )


def _property_value(key: str):
    return lambda state: state.properties.get(key)


def _line_preview(state):
    label = state.properties.get("label")
    if str(label or "").strip() and not str(label).startswith("_"):
        return label
    if state.role is ComponentRole.FUNCTION_CURVE:
        return state.data.get("expression")
    return ""


def _axes_label(state):
    return f"Axes {int(state.selector.get('index', state.order)) + 1}"


def _axis_label(state):
    axis = str(state.selector.get("axis", "")).upper()
    return f"{axis} Axis" if axis else "Axis"


def _spine_label(state):
    side = str(state.selector.get("name", "")).replace("_", " ").title()
    return f"{side} Spine" if side else "Spine"


def _tick_label(state):
    axis = str(state.selector.get("axis", "")).upper()
    level = str(state.selector.get("level", "")).title()
    suffix = (
        "Tick Labels"
        if state.kind is ComponentKind.TICK_LABEL_GROUP
        else "Ticks"
    )
    return " ".join(part for part in (axis, level, suffix) if part)


def _grid_label(state):
    axis = str(state.selector.get("axis", "")).upper()
    level = str(state.selector.get("level", "")).title()
    return " ".join(part for part in (axis, level, "Grid") if part)


def _semantic_text_label(state):
    return {
        ComponentRole.TITLE: "Title",
        ComponentRole.X_LABEL: "X Label",
        ComponentRole.Y_LABEL: "Y Label",
    }.get(state.role, "Text")


def _semantic_sort(state):
    if state.kind is ComponentKind.AXIS:
        return (0 if state.selector.get("axis") == "x" else 1,)
    if state.kind is ComponentKind.SPINE:
        return ({"left": 0, "right": 1, "top": 2, "bottom": 3}.get(
            str(state.selector.get("name", "")), 99
        ),)
    if state.role is ComponentRole.TITLE:
        return (0,)
    if state.kind is ComponentKind.LEGEND:
        return (1,)
    level = str(state.selector.get("level", ""))
    return ({"major": 0, "minor": 1}.get(level, state.order),)


LINE_PROFILES = {
    ComponentRole.LINE: EditorProfile(
        "line",
        "Line",
        (
            SectionSpec(
                "data",
                "Raw X/Y data",
                _raw_xy_data,
                data_keys=RawXYDataSection.DATA_KEYS,
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
                property_keys=LineAppearanceSection.PROPERTY_KEYS,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Line", "Lines", "curve", _line_preview, 30,
            delete_label="Line",
        ),
    ),
    ComponentRole.FUNCTION_CURVE: EditorProfile(
        "function_curve",
        "Function curve",
        (
            SectionSpec(
                "definition",
                "Definition and range",
                _curve_definition,
                data_keys=("expression", "x_start", "x_stop", "samples"),
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
                property_keys=LineAppearanceSection.PROPERTY_KEYS,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Function Curve", "Function Curves", "curve", _line_preview, 30,
            delete_label="Function Curve",
        ),
    ),
    ComponentRole.DATA_PLOT: EditorProfile(
        "data_plot",
        "Plot",
        (
            SectionSpec(
                "data",
                "Data source",
                _chart_data_references,
                data_keys=("x_ref", "y_ref", "preprocess"),
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
                property_keys=LineAppearanceSection.PROPERTY_KEYS,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Plot", "Plots", "plot", _line_preview, 30,
            delete_label="Plot",
        ),
    ),
    ComponentRole.FIT_CURVE: EditorProfile(
        "fit_curve",
        "Fit curve",
        (
            SectionSpec(
                "data",
                "Data source",
                _fit_data_references,
                data_keys=("x_ref", "y_ref", "preprocess"),
            ),
            SectionSpec(
                "actions",
                "Fit operations",
                _fit_actions,
                data_keys=("engine", "fit_type", "fit_options"),
            ),
            SectionSpec(
                "result",
                "Fit result",
                _fit_result,
                data_keys=("fit_result", "expression"),
            ),
            SectionSpec(
                "range",
                "Display range",
                _fit_range,
                data_keys=("x_start", "x_stop"),
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
                property_keys=LineAppearanceSection.PROPERTY_KEYS,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Fit Curve", "Fit Curves", "fitting", _line_preview, 30,
            delete_label="Fit Curve",
        ),
    ),
    ComponentRole.INTERPOLATION: EditorProfile(
        "interpolation",
        "Interpolation",
        (
            SectionSpec(
                "data",
                "Data source",
                _interpolation_data_references,
                data_keys=("x_ref", "y_ref", "preprocess"),
            ),
            SectionSpec(
                "interpolation",
                "Interpolation parameters",
                _interpolation_options,
                data_keys=("method", "k", "samples", "lam", "lam_auto"),
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
                property_keys=LineAppearanceSection.PROPERTY_KEYS,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Interpolation", "Interpolations", "interpolate", _line_preview, 30,
            delete_label="Interpolation",
        ),
    ),
}


SCATTER_PROFILE = EditorProfile(
    "scatter",
    "Scatter",
    (
        SectionSpec(
            "data",
            "Data source",
            _chart_data_references,
            data_keys=("x_ref", "y_ref", "preprocess"),
        ),
        SectionSpec(
            "mapping",
            "Color and size mapping",
            _scatter_mapping,
            property_keys=ScatterMappingSection.PROPERTY_KEYS,
            data_keys=ScatterMappingSection.DATA_KEYS,
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _scatter_appearance,
            property_keys=ScatterAppearanceSection.PROPERTY_KEYS,
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Scatter", "Scatters", "scatter", _line_preview, 30,
        delete_label="Scatter",
    ),
)


def _text_sections(*, free: bool) -> tuple[SectionSpec, ...]:
    position_keys = tuple(
        key
        for key in TextPositionSection.KEYS
        if free or key != "coordinate_system"
    )
    return (
        SectionSpec(
            "content", "Content", _text_content,
            property_keys=("text",),
        ),
        SectionSpec(
            "typography", "Typography", _text_typography,
            property_keys=TextTypographySection.DEFAULT_KEYS,
        ),
        SectionSpec(
            "transform",
            "Rotation and alignment",
            _text_transform,
            collapsed=True,
            property_keys=TextTransformSection.KEYS,
        ),
        SectionSpec(
            "position", "Position and visibility", _text_position,
            property_keys=position_keys,
        ),
        SectionSpec(
            "render", "Rendering", _text_render,
            property_keys=("usetex",),
        ),
        SectionSpec(
            "advanced", "Advanced", _text_advanced,
            collapsed=True,
            property_keys=TEXT_ADVANCED_KEYS,
        ),
    )


TEXT_PROFILE = EditorProfile(
    "text",
    "Text",
    _text_sections(free=True),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Text",
        "Texts",
        "text",
        _property_value("text"),
        40,
        delete_label="Text",
    ),
)


IN_AXES_ZOOM_PROFILE = EditorProfile(
    "in_axes_zoom",
    "Zoom inset",
    (
        SectionSpec(
            "layout",
            "Layout",
            _properties("bounds", "visible", "zorder"),
            property_keys=("bounds", "visible", "zorder"),
        ),
        SectionSpec(
            "frame",
            "Frame",
            _properties(
                "facecolor",
                "frameon",
                "edgecolor",
                "linewidth",
            ),
            property_keys=("facecolor", "frameon", "edgecolor", "linewidth"),
        ),
        SectionSpec(
            "range",
            "Zoom range",
            _properties("xlim", "ylim", "ticks_visible"),
            property_keys=("xlim", "ylim", "ticks_visible"),
        ),
        SectionSpec(
            "indicator",
            "Indicator",
            _properties(
                "region_visible",
                "region_color",
                "region_linestyle",
                "region_linewidth",
                "region_alpha",
                "region_facecolor",
                "region_fill",
                "region_hatch",
                "region_zorder",
                "connectors",
            ),
            property_keys=(
                "region_visible", "region_color", "region_linestyle",
                "region_linewidth", "region_alpha", "region_facecolor",
                "region_fill", "region_hatch", "region_zorder", "connectors",
            ),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Zoom Inset",
        "Zoom Insets",
        "zoom inset",
        preview=lambda state: (
            f"X {tuple(state.properties.get('xlim', ()))}; "
            f"Y {tuple(state.properties.get('ylim', ()))}"
        ),
        sort_bucket=45,
        delete_label="Zoom Inset",
    ),
)


IN_AXES_IMAGE_PROFILE = EditorProfile(
    "in_axes_image",
    "Image inset",
    (
        SectionSpec(
            "layout",
            "Layout",
            _properties("bounds", "visible", "zorder"),
            property_keys=("bounds", "visible", "zorder"),
        ),
        SectionSpec(
            "frame",
            "Frame",
            _properties(
                "facecolor",
                "frameon",
                "edgecolor",
                "linewidth",
            ),
            property_keys=("facecolor", "frameon", "edgecolor", "linewidth"),
        ),
        SectionSpec(
            "source", "Image", _image_in_axes_source,
            data_keys=("filename", "mime_type", "payload_base64"),
        ),
        SectionSpec(
            "display",
            "Display",
            _properties(
                "opacity", "fit_mode", "interpolation", "origin", "extent",
                "resample", "filternorm", "filterrad", "interpolation_stage",
                "image_visible", "image_zorder", "image_clip_on",
                "image_rasterized", "image_in_layout", "image_snap",
                "image_gid", "image_label", "image_sketch_params",
                "image_url",
            ),
            property_keys=(
                "opacity", "fit_mode", "interpolation", "origin", "extent",
                "resample", "filternorm", "filterrad", "interpolation_stage",
                "image_visible", "image_zorder", "image_clip_on",
                "image_rasterized", "image_in_layout", "image_snap",
                "image_gid", "image_label", "image_sketch_params",
                "image_url",
            ),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Image Inset",
        "Image Insets",
        "image inset",
        preview=lambda state: state.data.get("filename", ""),
        sort_bucket=45,
        delete_label="Image Inset",
    ),
)


SEMANTIC_TEXT_PROFILE = EditorProfile(
    "semantic_text",
    "Text",
    _text_sections(free=False),
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        _semantic_text_label,
        preview=_property_value("text"),
        sort_bucket=20,
        sort_key=_semantic_sort,
        group_title="Axes Components",
        group_key="axes_components",
        group_order=-1,
        always_group=True,
    ),
)


LEGEND_PROFILE = EditorProfile(
    "legend",
    "Legend",
    (
        SectionSpec(
            "content", "Title", _legend_title,
            property_keys=("title",),
        ),
        SectionSpec(
            "typography", "Typography", _legend_typography,
            property_keys=("label_font", "title_font"),
        ),
        SectionSpec(
            "layout", "Layout", _legend_location,
            property_keys=("visible", "location", "ncols", "entry_scope"),
        ),
        SectionSpec(
            "layout_details", "Layout details", _legend_details,
            collapsed=True,
            property_keys=LEGEND_DETAIL_KEYS,
        ),
        SectionSpec(
            "frame", "Frame", _legend_frame,
            property_keys=(
                "frameon", "facecolor", "edgecolor", "framealpha",
                "fancybox", "shadow", "frame_linewidth",
                "frame_linestyle", "frame_hatch",
            ),
        ),
        SectionSpec(
            "advanced", "Advanced", _legend_advanced,
            collapsed=True,
            property_keys=LEGEND_ADVANCED_KEYS,
        ),
    ),
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        "Legend",
        preview=_property_value("title"),
        sort_bucket=20,
        sort_key=_semantic_sort,
        group_title="Axes Components",
        group_key="axes_components",
        group_order=-1,
        always_group=True,
    ),
)


AXES_PROFILE = EditorProfile(
    "axes",
    "Axes",
    (
        SectionSpec(
            "layout", "Layout relationship", _axes_layout,
        ),
        SectionSpec(
            "palette", "Palette", _palette,
            property_keys=("color_cycle",),
        ),
        SectionSpec(
            "limits",
            "Limits and autoscale",
            _axes_limits,
            property_keys=AxesLimitsSection.PROPERTY_KEYS,
            proxy_keys=AxesLimitsSection.PROXY_KEYS,
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _properties(
                "aspect",
                "facecolor",
                "visible",
                "xmargin",
                "ymargin",
                "adjustable",
                "anchor",
                "box_aspect",
                "axisbelow",
                "frameon",
                "zorder",
            ),
            property_keys=(
                "aspect", "facecolor", "visible", "xmargin", "ymargin",
                "adjustable", "anchor", "box_aspect", "axisbelow",
                "frameon", "zorder",
            ),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _properties(
                "rasterization_zorder", "alpha", "label", "clip_on", "gid",
                "in_layout", "rasterized", "sketch_params", "snap", "url",
            ),
            collapsed=True,
            property_keys=(
                "rasterization_zorder", "alpha", "label", "clip_on", "gid",
                "in_layout", "rasterized", "sketch_params", "snap", "url",
            ),
        ),
    ),
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        _axes_label,
        sort_bucket=0,
        sort_key=lambda state: (
            int(state.selector.get("index", state.order)),
        ),
        delete_label="Axes",
    ),
)


PROPERTY_PROFILE_KINDS = frozenset(
    {
        ComponentKind.FIGURE,
        ComponentKind.AXIS,
        ComponentKind.SPINE,
        ComponentKind.TICK_GROUP,
        ComponentKind.TICK_LABEL_GROUP,
        ComponentKind.GRID,
    }
)


def _controller_property_keys(
    kind: ComponentKind,
    role: ComponentRole,
    *,
    advanced: bool,
) -> tuple[str, ...]:
    controller_type = CONTROLLER_TYPES[(kind, role)]
    return tuple(
        spec.key
        for spec in controller_type.PROPERTY_SPECS
        if spec.persistent and bool(spec.advanced) is advanced
    )


def _property_profile(kind: ComponentKind, role: ComponentRole) -> EditorProfile:
    title = kind.value.replace("_", " ").title()
    presentations = {
        ComponentKind.FIGURE: TreePresentationSpec(
            "Figure",
            preview=_property_value("name"),
            sort_bucket=0,
        ),
        ComponentKind.AXIS: TreePresentationSpec(
            _axis_label,
            sort_bucket=0,
            sort_key=_semantic_sort,
        ),
        ComponentKind.SPINE: TreePresentationSpec(
            _spine_label,
            sort_bucket=10,
            sort_key=_semantic_sort,
        ),
        ComponentKind.TICK_GROUP: TreePresentationSpec(
            _tick_label,
            sort_bucket=10,
            sort_key=_semantic_sort,
        ),
        ComponentKind.TICK_LABEL_GROUP: TreePresentationSpec(
            _tick_label,
            sort_bucket=0,
            sort_key=_semantic_sort,
        ),
        ComponentKind.GRID: TreePresentationSpec(
            _grid_label,
            sort_bucket=20,
            sort_key=_semantic_sort,
        ),
    }
    placement = (
        EditorPlacement.FIGURE
        if kind is ComponentKind.FIGURE
        else EditorPlacement.SEMANTIC
    )
    core_keys = _controller_property_keys(kind, role, advanced=False)
    advanced_keys = _controller_property_keys(kind, role, advanced=True)
    core_factory = (
        _axis_properties_for(core_keys)
        if kind is ComponentKind.AXIS
        else _properties(*core_keys)
    )
    advanced_factory = (
        _axis_properties_for(advanced_keys)
        if kind is ComponentKind.AXIS
        else _properties(*advanced_keys)
    )
    sections = [
        SectionSpec(
            "properties",
            "Properties",
            core_factory,
            property_keys=core_keys,
        )
    ]
    if advanced_keys:
        sections.append(
            SectionSpec(
                "advanced",
                "Advanced",
                advanced_factory,
                collapsed=True,
                property_keys=advanced_keys,
            )
        )
    return EditorProfile(
        f"{kind.value}:{role.value}:properties",
        title,
        tuple(sections),
        placement=placement,
        tree=(
            presentations[kind]
            if kind is ComponentKind.FIGURE
            else TreePresentationSpec(
                presentations[kind].label,
                preview=presentations[kind].preview,
                sort_bucket=presentations[kind].sort_bucket,
                sort_key=presentations[kind].sort_key,
                group_title="Axes Components",
                group_key="axes_components",
                group_order=-1,
                always_group=True,
            )
        ),
    )


PROPERTY_PROFILES = {
    (kind, role): _property_profile(kind, role)
    for kind in PROPERTY_PROFILE_KINDS
    for role in ROLES_BY_KIND[kind]
}


def register_production_profiles(editor_registry) -> None:
    """Register every first-party Inspector profile in one place."""

    for role, profile in LINE_PROFILES.items():
        editor_registry.register_profile(
            ComponentKind.LINE,
            profile,
            role=role,
        )
    editor_registry.register_profile(
        ComponentKind.SCATTER,
        SCATTER_PROFILE,
        role=ComponentRole.SCATTER,
    )
    editor_registry.register_profile(
        ComponentKind.TEXT,
        TEXT_PROFILE,
        role=ComponentRole.TEXT,
    )
    for role in (
        ComponentRole.TITLE,
        ComponentRole.X_LABEL,
        ComponentRole.Y_LABEL,
    ):
        editor_registry.register_profile(
            ComponentKind.TEXT,
            SEMANTIC_TEXT_PROFILE,
            role=role,
        )
    editor_registry.register_profile(
        ComponentKind.LEGEND,
        LEGEND_PROFILE,
        role=ComponentRole.LEGEND,
    )
    editor_registry.register_profile(
        ComponentKind.AXES,
        AXES_PROFILE,
        role=ComponentRole.AXES,
    )
    editor_registry.register_profile(
        ComponentKind.IN_AXES,
        IN_AXES_ZOOM_PROFILE,
        role=ComponentRole.IN_AXES_ZOOM,
    )
    editor_registry.register_profile(
        ComponentKind.IN_AXES,
        IN_AXES_IMAGE_PROFILE,
        role=ComponentRole.IN_AXES_IMAGE,
    )
    for (kind, role), profile in PROPERTY_PROFILES.items():
        editor_registry.register_profile(kind, profile, role=role)
    editor_registry.validate_production_profiles()
