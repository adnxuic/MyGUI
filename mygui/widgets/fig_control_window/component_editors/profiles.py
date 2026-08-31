"""Register the production editor profiles for Figure component roles."""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    CONTROLLER_TYPES,
    ROLES_BY_KIND,
)

from .chart_sections import FunctionCurveSection, InterpolationSection
from .context import perform_editor_action
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
from .inline_spec_editors import SecondaryAxisPlacementEditor
from .sections import (
    AnnotationArrowSection,
    AnnotationContentSection,
    AnnotationPlacementSection,
    AnnotationPropertySection,
    AnnotationTypographySection,
    AxesLayoutSection,
    AxisTickSettingsSection,
    AxesLimitsSection,
    ColorbarSourceSection,
    DataReferenceSection,
    ErrorBarDataSection,
    Field2DDataSection,
    ImageInAxesSourceSection,
    LegendLocationSection,
    LineAppearanceSection,
    PaletteSection,
    PropertySection,
    RawXYDataSection,
    ReferenceMarksDataSection,
    ReferenceMarksPositionSection,
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


def _minor_properties(*keys: str):
    def factory(controller, context, parent):
        apply_properties = None
        if controller.state.selector.get("level") == "minor":
            def apply_properties(properties):
                key = next(iter(properties))
                role = controller.state.kind.value.replace("_", " ").title()
                label = key.replace("_", " ").title()
                return perform_editor_action(
                    context,
                    f"Change {role} {label}",
                    lambda: context.axes_layout.apply_minor_component_properties(
                        controller,
                        properties,
                    ),
                    merge_key=("property", controller.component_id, key),
                )

        return PropertySection(
            controller,
            context=context,
            property_keys=keys or None,
            apply_properties=apply_properties,
            parent=parent,
        )

    return factory


def _field_2d_properties(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=lambda properties: context.field_2d.apply_properties(
                controller,
                properties,
            ),
            parent=parent,
        )

    return factory


def _field_2d_data(controller, context, parent):
    return Field2DDataSection(
        controller,
        context=context,
        parent=parent,
    )


def _field_2d_preview(state) -> str:
    cmap = str((state.properties.get("colormap") or {}).get("cmap", "")).strip()
    return cmap or state.role.value.replace("_", " ").title()


def _colorbar_properties(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=lambda properties: context.colorbars.apply_properties(
                controller,
                properties,
            ),
            parent=parent,
        )

    return factory


def _colorbar_source(controller, context, parent):
    return ColorbarSourceSection(
        controller,
        context=context,
        parent=parent,
    )


def _secondary_axis_properties(*keys: str):
    def factory(controller, context, parent):
        def apply_properties(properties):
            key = next(iter(properties))
            label = key.replace("_", " ").title()
            return perform_editor_action(
                context,
                f"Change Secondary Axis {label}",
                lambda: context.secondary_axes.apply_properties(
                    controller, properties
                ),
                merge_key=("property", controller.component_id, key),
            )

        section = PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=apply_properties,
            parent=parent,
        )
        if "placement" in keys:
            editor = section.editor("placement")
            if isinstance(editor, SecondaryAxisPlacementEditor):
                orientation = (
                    "x"
                    if controller.state.role is ComponentRole.SECONDARY_X_AXIS
                    else "y"
                )
                editor.set_orientation(orientation)
        return section

    return factory


def _secondary_axis_preview(state) -> str:
    label = str(state.properties.get("label", "")).strip()
    if label:
        return label
    transform = state.properties.get("unit_transform", {})
    if transform.get("kind") == "preset":
        return str(transform.get("name", "identity")).replace("_", " ").title()
    return str(transform.get("kind", "Unit transform")).title()


def _reference_marks_properties(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=lambda properties: (
                context.reference_marks.apply_properties(
                    controller,
                    properties,
                )
            ),
            parent=parent,
        )

    return factory


def _reference_marks_position(controller, context, parent):
    return ReferenceMarksPositionSection(
        controller,
        context=context,
        property_keys=("baseline", "height"),
        apply_properties=lambda properties: (
            context.reference_marks.apply_properties(
                controller,
                properties,
            )
        ),
        parent=parent,
    )


def _reference_marks_data(controller, context, parent):
    return ReferenceMarksDataSection(
        controller,
        context=context,
        parent=parent,
    )


def _reference_guide_properties(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=_reference_guide_apply(controller, context),
            parent=parent,
        )

    return factory


_REFERENCE_GUIDE_HISTORY_LABELS = {
    "facecolor": "Face Color",
    "edgecolor": "Edge Color",
    "linewidth": "Line Width",
    "linestyle": "Line Style",
    "span_start": "Span Start",
    "span_end": "Span End",
    "clip_on": "Clip On",
    "zorder": "Z-order",
}


def _reference_guide_apply(controller, context):
    """Route one guide Inspector intent through Service and Figure history."""

    def apply(properties):
        patch = dict(properties)
        role = controller.state.role.value.replace("_", " ").title()
        if len(patch) == 1:
            property_key = next(iter(patch))
            label = _REFERENCE_GUIDE_HISTORY_LABELS.get(
                property_key,
                property_key.replace("_", " ").title(),
            )
            text = f"Change {role} {label}"
            merge_key = (
                "property",
                controller.component_id,
                property_key,
            )
        else:
            text = f"Change {role} Properties"
            merge_key = None
        return perform_editor_action(
            context,
            text,
            lambda: context.reference_guides.apply_properties(
                controller,
                patch,
            ),
            merge_key=merge_key,
        )

    return apply


def _guide_number(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "?"


def _reference_line_preview(state) -> str:
    label = str(state.properties.get("label", "")).strip()
    if label:
        return label
    coordinate = (
        "x" if state.properties.get("orientation") == "vertical" else "y"
    )
    return f"{coordinate} = {_guide_number(state.properties.get('value'))}"


def _reference_band_preview(state) -> str:
    label = str(state.properties.get("label", "")).strip()
    if label:
        return label
    coordinate = (
        "x" if state.properties.get("orientation") == "vertical" else "y"
    )
    lower = _guide_number(state.properties.get("lower"))
    upper = _guide_number(state.properties.get("upper"))
    return f"{lower} ≤ {coordinate} ≤ {upper}"


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
        def operation():
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

        axis_name = str(controller.state.selector["axis"]).upper()
        return perform_editor_action(
            context,
            f"Change {axis_name} Axis {key}",
            operation,
            merge_key=("property", controller.component_id, key),
            scan_all=key == "scale",
        )

    return PropertySection(
        controller,
        context=context,
        property_keys=keys,
        apply_properties=apply,
        parent=parent,
    )


def _axis_ticks(controller, context, parent):
    return AxisTickSettingsSection(
        controller,
        context=context,
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


_TEXT_HISTORY_LABELS = {
    "text": "Content",
    "fontsize": "Font Size",
    "color": "Color",
    "position": "Position",
}


def _text_history_label(property_key: str) -> str:
    return _TEXT_HISTORY_LABELS.get(
        property_key,
        property_key.replace("_", " ").title(),
    )


def _text_apply(controller, context):
    def apply(properties):
        patch = dict(properties)
        if len(patch) == 1:
            property_key = next(iter(patch))
            text = f"Change Text {_text_history_label(property_key)}"
            merge_key = (
                "property",
                controller.component_id,
                property_key,
            )
        else:
            text = "Change Text Properties"
            merge_key = None
        return perform_editor_action(
            context,
            text,
            lambda: context.text_rendering.apply(controller, patch),
            merge_key=merge_key,
        )

    return apply


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
    if state.kind is ComponentKind.TICK_LABEL_GROUP:
        return "Tick Labels"
    axis = str(state.selector.get("axis", "")).upper()
    level = str(state.selector.get("level", "")).title()
    suffix = "Ticks"
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
    if state.role in (ComponentRole.X_LABEL, ComponentRole.Y_LABEL):
        return (0,)
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
                data_keys=("engine", "fit_type", "fit_options", "fit_input_range"),
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


def _errorbar_data(controller, context, parent):
    return ErrorBarDataSection(
        controller,
        context=context,
        parent=parent,
    )


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


ERROR_BAR_PROFILE = EditorProfile(
    "errorbar",
    "Error Bar",
    (
        SectionSpec(
            "data",
            "Data",
            _errorbar_data,
            data_keys=("x_ref", "y_ref", "xerr", "yerr", "preprocess"),
        ),
        SectionSpec(
            "line",
            "Line",
            _properties(
                "label",
                "color",
                "linestyle",
                "linewidth",
                "drawstyle",
                "antialiased",
                "visible",
            ),
            property_keys=(
                "label",
                "color",
                "linestyle",
                "linewidth",
                "drawstyle",
                "antialiased",
                "visible",
            ),
        ),
        SectionSpec(
            "marker",
            "Marker",
            _properties(
                "marker",
                "markersize",
                "markerfacecolor",
                "markeredgecolor",
                "markeredgewidth",
                "markerfacecoloralt",
                "fillstyle",
            ),
            property_keys=(
                "marker",
                "markersize",
                "markerfacecolor",
                "markeredgecolor",
                "markeredgewidth",
                "markerfacecoloralt",
                "fillstyle",
            ),
        ),
        SectionSpec(
            "error_bars",
            "Error Bars",
            _properties(
                "ecolor",
                "elinewidth",
                "capsize",
                "capthick",
                "error_linestyle",
                "error_capstyle",
                "error_antialiased",
                "errorevery",
                "lolims",
                "uplims",
                "xlolims",
                "xuplims",
                "barsabove",
            ),
            property_keys=(
                "ecolor",
                "elinewidth",
                "capsize",
                "capthick",
                "error_linestyle",
                "error_capstyle",
                "error_antialiased",
                "errorevery",
                "lolims",
                "uplims",
                "xlolims",
                "xuplims",
                "barsabove",
            ),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _properties("alpha", "zorder", "clip_on"),
            property_keys=("alpha", "zorder", "clip_on"),
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Error Bar", "Error Bars", "errorbar", _line_preview, 30,
        delete_label="Error Bar",
    ),
)


PSEUDOCOLOR_PROFILE = EditorProfile(
    "pseudocolor",
    "Pseudocolor",
    (
        SectionSpec(
            "data",
            "Data source",
            _field_2d_data,
            data_keys=("x_ref", "y_ref", "z_ref"),
        ),
        SectionSpec(
            "colormap",
            "Color mapping",
            _field_2d_properties("colormap"),
            property_keys=("colormap",),
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _field_2d_properties(
                "visible",
                "alpha",
                "zorder",
                "shading",
                "edgecolor",
                "linewidth",
                "antialiased",
            ),
            property_keys=(
                "visible",
                "alpha",
                "zorder",
                "shading",
                "edgecolor",
                "linewidth",
                "antialiased",
            ),
        ),
        SectionSpec(
            "export",
            "Export",
            _field_2d_properties(
                "clip_on", "gid", "in_layout", "rasterized", "snap", "url"
            ),
            property_keys=(
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Pseudocolor", "Pseudocolor", "pseudocolor", _field_2d_preview, 32,
        delete_label="Pseudocolor",
    ),
)


HEATMAP_PROFILE = EditorProfile(
    "heatmap",
    "Heatmap",
    (
        SectionSpec(
            "data",
            "Data source",
            _field_2d_data,
            data_keys=("x_ref", "y_ref", "z_ref"),
        ),
        SectionSpec(
            "colormap",
            "Color mapping",
            _field_2d_properties("colormap"),
            property_keys=("colormap",),
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _field_2d_properties(
                "visible",
                "alpha",
                "zorder",
                "interpolation",
                "interpolation_stage",
                "resample",
            ),
            property_keys=(
                "visible",
                "alpha",
                "zorder",
                "interpolation",
                "interpolation_stage",
                "resample",
            ),
        ),
        SectionSpec(
            "export",
            "Export",
            _field_2d_properties(
                "filternorm",
                "filterrad",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
            property_keys=(
                "filternorm",
                "filterrad",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Heatmap", "Heatmaps", "heatmap", _field_2d_preview, 32,
        delete_label="Heatmap",
    ),
)


CONTOUR_PROFILE = EditorProfile(
    "contour",
    "Contour",
    (
        SectionSpec(
            "data",
            "Data source",
            _field_2d_data,
            data_keys=("x_ref", "y_ref", "z_ref"),
        ),
        SectionSpec(
            "colormap",
            "Color mapping",
            _field_2d_properties("colormap"),
            property_keys=("colormap",),
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _field_2d_properties(
                "visible",
                "alpha",
                "zorder",
                "mode",
                "levels",
                "corner_mask",
                "extend",
                "linewidth",
                "linestyle",
                "negative_linestyle",
                "labels",
            ),
            property_keys=(
                "visible",
                "alpha",
                "zorder",
                "mode",
                "levels",
                "corner_mask",
                "extend",
                "linewidth",
                "linestyle",
                "negative_linestyle",
                "labels",
            ),
        ),
        SectionSpec(
            "export",
            "Export",
            _field_2d_properties(
                "algorithm",
                "nchunk",
                "antialiased",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
            property_keys=(
                "algorithm",
                "nchunk",
                "antialiased",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
        ),
    ),
    placement=EditorPlacement.CHART,
    tree=TreePresentationSpec(
        "Contour", "Contours", "contour", _field_2d_preview, 32,
        delete_label="Contour",
    ),
)


COLORBAR_PROFILE = EditorProfile(
    "colorbar",
    "Colorbar",
    (
        SectionSpec(
            "source",
            "Source",
            _colorbar_source,
            data_keys=("source_component_id",),
        ),
        SectionSpec(
            "placement",
            "Placement",
            _colorbar_properties(
                "location", "fraction", "shrink", "aspect", "pad"
            ),
            property_keys=("location", "fraction", "shrink", "aspect", "pad"),
        ),
        SectionSpec(
            "scale_ticks",
            "Scale & Ticks",
            _colorbar_properties(
                "locator", "formatter", "minor_ticks", "ticklocation"
            ),
            property_keys=("locator", "formatter", "minor_ticks", "ticklocation"),
        ),
        SectionSpec(
            "label",
            "Label",
            _colorbar_properties("label", "label_font"),
            property_keys=("label", "label_font"),
        ),
        SectionSpec(
            "appearance",
            "Appearance",
            _colorbar_properties(
                "visible",
                "tick_font",
                "outline_visible",
                "outline_color",
                "outline_linewidth",
            ),
            property_keys=(
                "visible",
                "tick_font",
                "outline_visible",
                "outline_color",
                "outline_linewidth",
            ),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _colorbar_properties("extend", "spacing", "drawedges"),
            collapsed=True,
            property_keys=("extend", "spacing", "drawedges"),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Colorbar",
        "Colorbars",
        "colorbar",
        preview=lambda state: str(state.data.get("source_component_id", ""))[:8],
        sort_bucket=50,
        delete_label="Colorbar",
    ),
)


SECONDARY_AXIS_PROFILE = EditorProfile(
    "secondary_axis",
    "Secondary Axis",
    (
        SectionSpec("general", "General", _secondary_axis_properties("visible"), property_keys=("visible",)),
        SectionSpec("unit_transform", "Unit Transform", _secondary_axis_properties("unit_transform"), property_keys=("unit_transform",)),
        SectionSpec("placement", "Placement", _secondary_axis_properties("placement"), property_keys=("placement",)),
        SectionSpec(
            "label", "Label",
            _secondary_axis_properties("label", "label_pad", "label_rotation", "label_font"),
            property_keys=("label", "label_pad", "label_rotation", "label_font"),
        ),
        SectionSpec(
            "scale_ticks", "Scale && Ticks",
            _secondary_axis_properties("ticker_mode", "major_locator", "major_formatter", "minor_locator", "minor_formatter"),
            property_keys=("ticker_mode", "major_locator", "major_formatter", "minor_locator", "minor_formatter"),
        ),
        SectionSpec(
            "tick_appearance", "Tick Appearance",
            _secondary_axis_properties(
                "major_ticks_visible", "major_labels_visible", "minor_ticks_visible", "minor_labels_visible",
                "tick_direction", "tick_length", "tick_width", "tick_color", "tick_pad", "tick_rotation",
                "tick_font", "offset_visible", "offset_font", "remove_overlapping_locs",
            ),
            property_keys=(
                "major_ticks_visible", "major_labels_visible", "minor_ticks_visible", "minor_labels_visible",
                "tick_direction", "tick_length", "tick_width", "tick_color", "tick_pad", "tick_rotation",
                "tick_font", "offset_visible", "offset_font", "remove_overlapping_locs",
            ),
        ),
        SectionSpec(
            "spine", "Spine",
            _secondary_axis_properties("spine_visible", "spine_color", "spine_linewidth", "spine_linestyle", "spine_bounds", "spine_alpha"),
            property_keys=("spine_visible", "spine_color", "spine_linewidth", "spine_linestyle", "spine_bounds", "spine_alpha"),
        ),
        SectionSpec("advanced", "Advanced", _secondary_axis_properties("zorder"), collapsed=True, property_keys=("zorder",)),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        label=lambda state: "Secondary X Axis" if state.role is ComponentRole.SECONDARY_X_AXIS else "Secondary Y Axis",
        group_title="Secondary Axes",
        instance_prefix="Secondary Axis",
        preview=_secondary_axis_preview,
        sort_bucket=52,
        group_key="secondary_axes",
        group_order=52,
        always_group=True,
        delete_label="Secondary Axis",
    ),
)


REFERENCE_MARKS_PROFILE = EditorProfile(
    "reflection_positions",
    "Reflection Positions",
    (
        SectionSpec(
            "general",
            "General",
            _reference_marks_properties("label", "visible"),
            property_keys=("label", "visible"),
        ),
        SectionSpec(
            "position",
            "Position",
            _reference_marks_position,
            property_keys=("baseline", "height"),
        ),
        SectionSpec(
            "line",
            "Line",
            _reference_marks_properties(
                "color", "linewidth", "linestyle", "alpha"
            ),
            property_keys=("color", "linewidth", "linestyle", "alpha"),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _reference_marks_properties("zorder", "clip_on"),
            collapsed=True,
            property_keys=("zorder", "clip_on"),
        ),
        SectionSpec(
            "data",
            "Data",
            _reference_marks_data,
            data_keys=ReferenceMarksDataSection.DATA_KEYS,
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Reflection Positions",
        preview=lambda state: str(state.properties.get("label", "")),
        sort_bucket=50,
        delete_label="Reflection Positions",
    ),
)


REFERENCE_LINE_PROFILE = EditorProfile(
    "reference_line",
    "Reference Line",
    (
        SectionSpec(
            "general",
            "General",
            _reference_guide_properties("label", "visible"),
            property_keys=("label", "visible"),
        ),
        SectionSpec(
            "position",
            "Position",
            _reference_guide_properties("orientation", "value"),
            property_keys=("orientation", "value"),
        ),
        SectionSpec(
            "line",
            "Line",
            _reference_guide_properties(
                "color", "linewidth", "linestyle", "alpha"
            ),
            property_keys=("color", "linewidth", "linestyle", "alpha"),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _reference_guide_properties(
                "span_start", "span_end", "zorder", "clip_on"
            ),
            collapsed=True,
            property_keys=("span_start", "span_end", "zorder", "clip_on"),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Reference Line",
        group_title="Reference Guides",
        instance_prefix="Reference Line ",
        preview=_reference_line_preview,
        sort_bucket=50,
        group_key="reference-guides",
        group_order=50,
        always_group=True,
        delete_label="Reference Line",
    ),
)


REFERENCE_BAND_PROFILE = EditorProfile(
    "reference_band",
    "Reference Band",
    (
        SectionSpec(
            "general",
            "General",
            _reference_guide_properties("label", "visible"),
            property_keys=("label", "visible"),
        ),
        SectionSpec(
            "position",
            "Position",
            _reference_guide_properties("orientation", "lower", "upper"),
            property_keys=("orientation", "lower", "upper"),
        ),
        SectionSpec(
            "fill",
            "Fill",
            _reference_guide_properties("facecolor", "alpha"),
            property_keys=("facecolor", "alpha"),
        ),
        SectionSpec(
            "border",
            "Border",
            _reference_guide_properties(
                "edgecolor", "linewidth", "linestyle"
            ),
            property_keys=("edgecolor", "linewidth", "linestyle"),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _reference_guide_properties(
                "span_start", "span_end", "zorder", "clip_on"
            ),
            collapsed=True,
            property_keys=("span_start", "span_end", "zorder", "clip_on"),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Reference Band",
        group_title="Reference Guides",
        instance_prefix="Reference Band ",
        preview=_reference_band_preview,
        sort_bucket=50,
        group_key="reference-guides",
        group_order=50,
        always_group=True,
        delete_label="Reference Band",
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


_ANNOTATION_HISTORY_LABELS = {
    "text": "Content",
    "label": "Name",
    "xy": "Target Position",
    "xycoords": "Target Coordinates",
    "xytext": "Text Position",
    "textcoords": "Text Coordinates",
    "fontsize": "Font Size",
    "color": "Color",
    "bbox": "Box",
}


def _annotation_history_label(property_key: str) -> str:
    return _ANNOTATION_HISTORY_LABELS.get(
        property_key,
        property_key.replace("_", " ").title(),
    )


def _annotation_apply(controller, context):
    def apply(properties):
        patch = dict(properties)
        if len(patch) == 1:
            property_key = next(iter(patch))
            text = (
                f"Change Annotation {_annotation_history_label(property_key)}"
            )
            merge_key = (
                "property",
                controller.component_id,
                property_key,
            )
        else:
            text = "Change Annotation Properties"
            merge_key = None
        return perform_editor_action(
            context,
            text,
            lambda: context.annotations.apply_properties(controller, patch),
            merge_key=merge_key,
        )

    return apply


def _annotation_content(controller, context, parent):
    return AnnotationContentSection(
        controller,
        context=context,
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_target(controller, context, parent):
    return AnnotationPropertySection(
        controller,
        context=context,
        property_keys=("xy", "xycoords"),
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_text_position(controller, context, parent):
    return AnnotationPlacementSection(
        controller,
        context=context,
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_arrow(controller, context, parent):
    return AnnotationArrowSection(
        controller,
        context=context,
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_text_style(controller, context, parent):
    return AnnotationTypographySection(
        controller,
        context=context,
        property_keys=(
            "fontfamily",
            "fontsize",
            "fontweight",
            "fontstyle",
            "color",
        ),
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_transform(controller, context, parent):
    return AnnotationPropertySection(
        controller,
        context=context,
        property_keys=(
            "rotation",
            "horizontalalignment",
            "verticalalignment",
        ),
        apply_properties=_annotation_apply(controller, context),
        parent=parent,
    )


def _annotation_preview(state):
    label = str(state.properties.get("label", "")).strip()
    if label:
        preview = label
    else:
        preview = " ".join(
            str(state.properties.get("text", "")).split()
        )
    if len(preview) > 32:
        return preview[:31].rstrip() + "…"
    return preview


ANNOTATION_PROFILE = EditorProfile(
    "annotation",
    "Annotation",
    (
        SectionSpec(
            "content",
            "Content",
            _annotation_content,
            property_keys=("text", "visible", "label"),
        ),
        SectionSpec(
            "target",
            "Target",
            _annotation_target,
            property_keys=("xy", "xycoords"),
        ),
        SectionSpec(
            "text_position",
            "Text Position",
            _annotation_text_position,
            property_keys=("xytext", "textcoords"),
        ),
        SectionSpec(
            "arrow",
            "Arrow",
            _annotation_arrow,
            property_keys=AnnotationArrowSection.KEYS,
        ),
        SectionSpec(
            "text_style",
            "Text Style",
            _annotation_text_style,
            property_keys=(
                "fontfamily",
                "fontsize",
                "fontweight",
                "fontstyle",
                "color",
            ),
        ),
        SectionSpec(
            "transform",
            "Rotation and alignment",
            _annotation_transform,
            property_keys=(
                "rotation",
                "horizontalalignment",
                "verticalalignment",
            ),
        ),
        SectionSpec(
            "box",
            "Box",
            _properties("bbox"),
            property_keys=("bbox",),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _properties("usetex", "alpha", "zorder", "clip_on"),
            collapsed=True,
            property_keys=("usetex", "alpha", "zorder", "clip_on"),
        ),
    ),
    placement=EditorPlacement.ELEMENT,
    tree=TreePresentationSpec(
        "Annotation",
        "Annotations",
        "annotation",
        _annotation_preview,
        46,
        group_key="annotations",
        group_order=46,
        always_group=True,
        delete_label="Annotation",
        duplicate_label="Duplicate Annotation",
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


TITLE_PROFILE = EditorProfile(
    "title",
    "Title",
    _text_sections(free=False),
    placement=EditorPlacement.SEMANTIC,
    tree=TreePresentationSpec(
        "Title",
        preview=_property_value("text"),
        sort_bucket=20,
        sort_key=_semantic_sort,
        group_title="Axes Structure",
        group_key="axes_structure",
        group_order=-1,
        always_group=True,
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
        sort_bucket=30,
        sort_key=_semantic_sort,
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
        group_title="Axes Structure",
        group_key="axes_structure",
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
                "rasterized", "sketch_params", "snap", "url",
            ),
            collapsed=True,
            property_keys=(
                "rasterization_zorder", "alpha", "label", "clip_on", "gid",
                "rasterized", "sketch_params", "snap", "url",
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
            group_title="Axes Structure",
            group_key="axes_structure",
            group_order=-1,
            always_group=True,
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
    if kind is ComponentKind.AXIS:
        ticker_keys = (
            "major_locator",
            "major_formatter",
            "minor_locator",
            "minor_formatter",
        )
        core_keys = tuple(key for key in core_keys if key not in ticker_keys)
        core_factory = _axis_properties_for(core_keys)
        advanced_factory = _axis_properties_for(advanced_keys)
    elif kind in {
        ComponentKind.TICK_GROUP,
        ComponentKind.TICK_LABEL_GROUP,
        ComponentKind.GRID,
    }:
        core_factory = _minor_properties(*core_keys)
        advanced_factory = _minor_properties(*advanced_keys)
    else:
        core_factory = _properties(*core_keys)
        advanced_factory = _properties(*advanced_keys)
    sections = [
        SectionSpec(
            "properties",
            "Properties",
            core_factory,
            property_keys=core_keys,
        )
    ]
    if kind is ComponentKind.AXIS:
        sections.append(
            SectionSpec(
                "ticks_labels",
                "Ticks & Labels",
                _axis_ticks,
                property_keys=ticker_keys,
            )
        )
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
        tree=presentations[kind],
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
        ComponentKind.ERRORBAR,
        ERROR_BAR_PROFILE,
        role=ComponentRole.ERROR_BAR,
    )
    editor_registry.register_profile(
        ComponentKind.FIELD_2D,
        PSEUDOCOLOR_PROFILE,
        role=ComponentRole.PSEUDOCOLOR,
    )
    editor_registry.register_profile(
        ComponentKind.FIELD_2D,
        HEATMAP_PROFILE,
        role=ComponentRole.HEATMAP,
    )
    editor_registry.register_profile(
        ComponentKind.FIELD_2D,
        CONTOUR_PROFILE,
        role=ComponentRole.CONTOUR,
    )
    editor_registry.register_profile(
        ComponentKind.COLORBAR,
        COLORBAR_PROFILE,
        role=ComponentRole.COLORBAR,
    )
    for role in (
        ComponentRole.SECONDARY_X_AXIS,
        ComponentRole.SECONDARY_Y_AXIS,
    ):
        editor_registry.register_profile(
            ComponentKind.SECONDARY_AXIS,
            SECONDARY_AXIS_PROFILE,
            role=role,
        )
    editor_registry.register_profile(
        ComponentKind.REFERENCE_MARKS,
        REFERENCE_MARKS_PROFILE,
        role=ComponentRole.REFLECTION_POSITIONS,
    )
    editor_registry.register_profile(
        ComponentKind.REFERENCE_GUIDE,
        REFERENCE_LINE_PROFILE,
        role=ComponentRole.REFERENCE_LINE,
    )
    editor_registry.register_profile(
        ComponentKind.REFERENCE_GUIDE,
        REFERENCE_BAND_PROFILE,
        role=ComponentRole.REFERENCE_BAND,
    )
    editor_registry.register_profile(
        ComponentKind.TEXT,
        TEXT_PROFILE,
        role=ComponentRole.TEXT,
    )
    editor_registry.register_profile(
        ComponentKind.ANNOTATION,
        ANNOTATION_PROFILE,
        role=ComponentRole.ANNOTATION,
    )
    editor_registry.register_profile(
        ComponentKind.TEXT,
        TITLE_PROFILE,
        role=ComponentRole.TITLE,
    )
    for role in (
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
