from __future__ import annotations

from code.figuremodify.components import ComponentKind, ComponentRole

from .chart_sections import FunctionCurveSection, InterpolationSection
from .fit_sections import (
    FitActionsSection,
    FitDisplayRangeSection,
    FitResultSection,
)
from .inspector import EditorProfile, SectionSpec
from .sections import (
    DataReferenceSection,
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
            lambda target, x_ref, y_ref, _axis:
            context.chart_data.set_refs(target, x_ref, y_ref)
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
            lambda target, x_ref, y_ref, _axis:
            context.fitting.set_sources(target, x_ref, y_ref)
        ),
        success_message=(
            lambda axis:
            f"Fit {axis.upper()} data source updated; "
            "run fitting to recompute."
        ),
        parent=parent,
    )


def _interpolation_data_references(controller, context, parent):
    def apply(target, x_ref, y_ref, _axis):
        data = target.read_state().data
        return context.interpolation.configure(
            target,
            x_ref=x_ref,
            y_ref=y_ref,
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
        deletion="remove",
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
        deletion="remove",
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
        deletion="remove",
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
        deletion="remove",
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
        deletion="remove",
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
    deletion="remove",
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
    deletion="remove",
)


SEMANTIC_TEXT_PROFILE = EditorProfile(
    "semantic_text",
    "Text",
    TEXT_PROFILE.sections,
    deletion="none",
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
    for kind, profile in PROPERTY_PROFILES.items():
        editor_registry.register_profile(kind, profile)
