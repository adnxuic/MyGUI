"""Register the production editor profiles for Figure component roles."""

from __future__ import annotations

from code.figuremodify.components import (
    ComponentKind,
    ComponentRole,
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
    DataReferenceSection,
    ImageInAxesSourceSection,
    LegendLocationSection,
    LineAppearanceSection,
    PaletteSection,
    PropertySection,
    ScatterAppearanceSection,
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


def _image_in_axes_source(controller, context, parent):
    return ImageInAxesSourceSection(
        controller,
        context=context,
        parent=parent,
    )


def _ensure_legend_apply(controller, context):
    def apply(properties):
        try:
            controller.resolve_target()
        except Exception:
            context.axes_commands.ensure_legend(
                controller.state.parent_id
            )
        if len(properties) == 1:
            key, value = next(iter(properties.items()))
            return controller.set_property(key, value)
        state = controller.read_state()
        updated = dict(state.properties)
        updated.update(properties)
        return controller.apply_state(
            state.clone(properties=updated)
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
    return TextTypographySection(
        controller,
        context=context,
        property_keys=("fontsize",),
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
        ),
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
                "appearance",
                "Appearance",
                _line_appearance,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Line", "Lines", "curve", _line_preview, 30
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
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Function Curve", "Function Curves", "curve", _line_preview, 30
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
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Plot", "Plots", "plot", _line_preview, 30
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
            ),
            SectionSpec("actions", "Fit operations", _fit_actions),
            SectionSpec("result", "Fit result", _fit_result),
            SectionSpec("range", "Display range", _fit_range),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Fit Curve", "Fit Curves", "fitting", _line_preview, 30
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
            ),
            SectionSpec(
                "interpolation",
                "Interpolation parameters",
                _interpolation_options,
            ),
            SectionSpec(
                "appearance",
                "Appearance",
                _line_appearance,
            ),
        ),
        placement=EditorPlacement.CHART,
        tree=TreePresentationSpec(
            "Interpolation", "Interpolations", "interpolate", _line_preview, 30
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
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _scatter_appearance,
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Scatter", "Scatters", "scatter", _line_preview, 30
    ),
)


TEXT_PROFILE = EditorProfile(
    "text",
    "Text",
    (
        SectionSpec("content", "Content", _text_content),
        SectionSpec("typography", "Typography", _text_typography),
        SectionSpec(
            "transform",
            "Rotation and alignment",
            _text_transform,
            collapsed=True,
        ),
        SectionSpec("position", "Position and visibility", _text_position),
        SectionSpec("render", "Rendering", _text_render),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Text",
        "Texts",
        "text",
        _property_value("text"),
        40,
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
        ),
        SectionSpec(
            "range",
            "Zoom range",
            _properties("xlim", "ylim", "ticks_visible"),
        ),
        SectionSpec(
            "indicator",
            "Indicator",
            _properties(
                "region_visible",
                "connectors_visible",
                "indicator_color",
                "indicator_linestyle",
                "indicator_linewidth",
                "indicator_alpha",
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
        ),
        SectionSpec("source", "Image", _image_in_axes_source),
        SectionSpec(
            "display",
            "Display",
            _properties("opacity", "fit_mode", "interpolation"),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Image Inset",
        "Image Insets",
        "image inset",
        preview=lambda state: state.data.get("filename", ""),
        sort_bucket=45,
    ),
)


SEMANTIC_TEXT_PROFILE = EditorProfile(
    "semantic_text",
    "Text",
    TEXT_PROFILE.sections,
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        _semantic_text_label,
        preview=_property_value("text"),
        sort_bucket=20,
        sort_key=_semantic_sort,
    ),
)


LEGEND_PROFILE = EditorProfile(
    "legend",
    "Legend",
    (
        SectionSpec("content", "Title", _legend_title),
        SectionSpec("typography", "Typography", _legend_typography),
        SectionSpec("layout", "Layout", _legend_location),
        SectionSpec("frame", "Frame", _legend_frame),
    ),
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        "Legend",
        preview=_property_value("title"),
        sort_bucket=20,
        sort_key=_semantic_sort,
    ),
)


AXES_PROFILE = EditorProfile(
    "axes",
    "Axes",
    (
        SectionSpec("palette", "Palette", _palette),
        SectionSpec(
            "limits",
            "Limits and scale",
            _properties(
                "xlim",
                "ylim",
                "xscale",
                "yscale",
                "autoscale_on",
            ),
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _properties(
                "position",
                "aspect",
                "facecolor",
                "visible",
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
    ),
)


PROPERTY_PROFILE_KEYS = {
    ComponentKind.FIGURE: (
        "name",
        "style",
        "size_inches",
        "dpi",
        "facecolor",
        "edgecolor",
        "frameon",
        "constrained_layout",
    ),
    ComponentKind.AXIS: (
        "visible",
        "scale",
        "ticks_position",
        "label_position",
        "inverted",
    ),
    ComponentKind.SPINE: (
        "visible",
        "color",
        "linewidth",
        "linestyle",
        "position",
        "bounds",
        "alpha",
    ),
    ComponentKind.TICK_GROUP: (
        "visible",
        "direction",
        "length",
        "width",
        "color",
        "pad",
    ),
    ComponentKind.TICK_LABEL_GROUP: (
        "visible",
        "color",
        "fontsize",
        "rotation",
        "fontfamily",
        "pad",
    ),
    ComponentKind.GRID: (
        "visible",
        "color",
        "linestyle",
        "linewidth",
        "alpha",
    ),
}


def _property_profile(kind: ComponentKind) -> EditorProfile:
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
    return EditorProfile(
        f"{kind.value}:properties",
        title,
        (
            SectionSpec(
                "properties",
                "Properties",
                _properties(*PROPERTY_PROFILE_KEYS[kind]),
            ),
        ),
        placement=placement,
        tree=presentations[kind],
    )


PROPERTY_PROFILES = {
    kind: _property_profile(kind)
    for kind in PROPERTY_PROFILE_KEYS
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
    for kind, profile in PROPERTY_PROFILES.items():
        for role in ROLES_BY_KIND[kind]:
            editor_registry.register_profile(kind, profile, role=role)
    editor_registry.validate_production_profiles()
