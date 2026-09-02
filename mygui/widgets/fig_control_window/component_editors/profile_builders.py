"""Shared Inspector profile factories and section builders."""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    CONTROLLER_TYPES,
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
    "fontweight",
    "fontstyle",
    "fontstretch",
    "fontvariant",
    "math_fontfamily",
    "parse_math",
    "alpha",
    "zorder",
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


def _text_advanced_for(*keys: str):
    def factory(controller, context, parent):
        return PropertySection(
            controller,
            context=context,
            property_keys=keys,
            apply_properties=_text_apply(controller, context),
            parent=parent,
        )

    return factory


def _text_advanced(controller, context, parent):
    return _text_advanced_for(*TEXT_ADVANCED_KEYS)(controller, context, parent)


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


def _errorbar_data(controller, context, parent):
    return ErrorBarDataSection(
        controller,
        context=context,
        parent=parent,
    )


def _text_sections(*, free: bool) -> tuple[SectionSpec, ...]:
    position_keys = tuple(
        key
        for key in TextPositionSection.KEYS
        if free or key != "coordinate_system"
    )
    advanced_keys = TEXT_ADVANCED_KEYS + (
        ("coordinate_system",) if free else ()
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
            collapsed=True,
            property_keys=("usetex",),
        ),
        SectionSpec(
            "advanced", "Advanced", _text_advanced_for(*advanced_keys),
            collapsed=True,
            property_keys=advanced_keys,
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
            collapsed=True,
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
