"""Text, Annotation, Title, and Legend Inspector profiles."""

from __future__ import annotations





from .inspector import (
    EditorPlacement,
    EditorProfile,
    SectionSpec,
    TreePresentationSpec,
)


from .sections import (
    AnnotationArrowSection,
)


from .profile_builders import (
    LEGEND_ADVANCED_KEYS,
    LEGEND_DETAIL_KEYS,
    _annotation_arrow,
    _annotation_content,
    _annotation_preview,
    _annotation_target,
    _annotation_text_position,
    _annotation_text_style,
    _annotation_transform,
    _legend_advanced,
    _legend_details,
    _legend_frame,
    _legend_location,
    _legend_title,
    _legend_typography,
    _properties,
    _property_value,
    _semantic_sort,
    _semantic_text_label,
    _text_sections,
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
            collapsed=True,
            property_keys=AnnotationArrowSection.KEYS,
        ),
        SectionSpec(
            "text_style",
            "Text Style",
            _annotation_text_style,
            collapsed=True,
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
            collapsed=True,
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
            collapsed=True,
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
            collapsed=True,
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
