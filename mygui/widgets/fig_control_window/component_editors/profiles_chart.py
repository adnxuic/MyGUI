"""Line-family, Scatter, and Error Bar Inspector profiles."""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentRole,
)




from .inspector import (
    EditorPlacement,
    EditorProfile,
    SectionSpec,
    TreePresentationSpec,
)


from .sections import (
    LineAppearanceSection,
    RawXYDataSection,
    ScatterAppearanceSection,
    ScatterMappingSection,
)


from .profile_builders import (
    _chart_data_references,
    _curve_definition,
    _errorbar_data,
    _fit_actions,
    _fit_data_references,
    _fit_range,
    _fit_result,
    _interpolation_data_references,
    _interpolation_options,
    _line_appearance,
    _line_preview,
    _properties,
    _raw_xy_data,
    _scatter_appearance,
    _scatter_mapping,
)

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
