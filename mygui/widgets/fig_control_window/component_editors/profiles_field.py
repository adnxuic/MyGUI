"""Field 2D, Colorbar, and Reference Inspector profiles."""

from __future__ import annotations





from .inspector import (
    EditorPlacement,
    EditorProfile,
    SectionSpec,
    TreePresentationSpec,
)


from .sections import (
    ReferenceMarksDataSection,
)


from .profile_builders import (
    _colorbar_properties,
    _colorbar_source,
    _field_2d_data,
    _field_2d_preview,
    _field_2d_properties,
    _reference_band_preview,
    _reference_guide_properties,
    _reference_line_preview,
    _reference_marks_data,
    _reference_marks_position,
    _reference_marks_properties,
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
                "shading",
                "edgecolor",
                "linewidth",
            ),
            property_keys=(
                "visible",
                "shading",
                "edgecolor",
                "linewidth",
            ),
        ),
        SectionSpec(
            "export",
            "Advanced",
            _field_2d_properties(
                "alpha",
                "zorder",
                "antialiased",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
            collapsed=True,
            property_keys=(
                "alpha",
                "zorder",
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
                "interpolation",
            ),
            property_keys=(
                "visible",
                "interpolation",
            ),
        ),
        SectionSpec(
            "export",
            "Advanced",
            _field_2d_properties(
                "alpha",
                "zorder",
                "interpolation_stage",
                "resample",
                "filternorm",
                "filterrad",
                "clip_on",
                "gid",
                "in_layout",
                "rasterized",
                "snap",
                "url",
            ),
            collapsed=True,
            property_keys=(
                "alpha",
                "zorder",
                "interpolation_stage",
                "resample",
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
                "mode",
                "levels",
                "linewidth",
                "linestyle",
            ),
            property_keys=(
                "visible",
                "mode",
                "levels",
                "linewidth",
                "linestyle",
            ),
        ),
        SectionSpec(
            "export",
            "Advanced",
            _field_2d_properties(
                "alpha",
                "zorder",
                "corner_mask",
                "extend",
                "negative_linestyle",
                "labels",
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
            collapsed=True,
            property_keys=(
                "alpha",
                "zorder",
                "corner_mask",
                "extend",
                "negative_linestyle",
                "labels",
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
            _colorbar_properties("location", "pad"),
            property_keys=("location", "pad"),
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
                "outline_visible",
                "outline_color",
            ),
            property_keys=(
                "visible",
                "outline_visible",
                "outline_color",
            ),
        ),
        SectionSpec(
            "scale_ticks",
            "Scale & Ticks",
            _colorbar_properties(
                "locator", "formatter", "minor_ticks", "ticklocation"
            ),
            collapsed=True,
            property_keys=("locator", "formatter", "minor_ticks", "ticklocation"),
        ),
        SectionSpec(
            "advanced",
            "Advanced",
            _colorbar_properties(
                "fraction",
                "shrink",
                "aspect",
                "tick_font",
                "outline_linewidth",
                "extend",
                "spacing",
                "drawedges",
            ),
            collapsed=True,
            property_keys=(
                "fraction",
                "shrink",
                "aspect",
                "tick_font",
                "outline_linewidth",
                "extend",
                "spacing",
                "drawedges",
            ),
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
            collapsed=True,
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
