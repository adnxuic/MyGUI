"""Axis, In-Axes, Secondary Axis, and semantic property Inspector profiles."""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentRole,
    ROLES_BY_KIND,
)




from .inspector import (
    EditorPlacement,
    EditorProfile,
    SectionSpec,
    TreePresentationSpec,
)


from .sections import (
    AxesLimitsSection,
)


from .profile_builders import (
    PROPERTY_PROFILE_KINDS,
    _axes_label,
    _axes_layout,
    _axes_limits,
    _image_in_axes_source,
    _palette,
    _properties,
    _property_profile,
    _secondary_axis_preview,
    _secondary_axis_properties,
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


PROPERTY_PROFILES = {
    (kind, role): _property_profile(kind, role)
    for kind in PROPERTY_PROFILE_KINDS
    for role in ROLES_BY_KIND[kind]
}
