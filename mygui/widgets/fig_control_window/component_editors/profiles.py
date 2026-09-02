"""Register the production editor profiles for Figure component roles.

This module is the stable facade. Domain profiles live in Axis,
Text/Annotation, Chart, and Field/Mapping modules and are registered
explicitly; there is no generic or JSON fallback.
"""

from __future__ import annotations

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
)

from .profiles_axis import (
    SECONDARY_AXIS_PROFILE,
    IN_AXES_ZOOM_PROFILE,
    IN_AXES_IMAGE_PROFILE,
    AXES_PROFILE,
    PROPERTY_PROFILES,
)
from .profiles_text import (
    TEXT_PROFILE,
    ANNOTATION_PROFILE,
    TITLE_PROFILE,
    SEMANTIC_TEXT_PROFILE,
    LEGEND_PROFILE,
)
from .profiles_chart import (
    LINE_PROFILES,
    SCATTER_PROFILE,
    ERROR_BAR_PROFILE,
)
from .profiles_field import (
    PSEUDOCOLOR_PROFILE,
    HEATMAP_PROFILE,
    CONTOUR_PROFILE,
    COLORBAR_PROFILE,
    REFERENCE_MARKS_PROFILE,
    REFERENCE_LINE_PROFILE,
    REFERENCE_BAND_PROFILE,
)

__all__ = [
    "register_production_profiles",
    "SECONDARY_AXIS_PROFILE",
    "IN_AXES_ZOOM_PROFILE",
    "IN_AXES_IMAGE_PROFILE",
    "AXES_PROFILE",
    "PROPERTY_PROFILES",
    "TEXT_PROFILE",
    "ANNOTATION_PROFILE",
    "TITLE_PROFILE",
    "SEMANTIC_TEXT_PROFILE",
    "LEGEND_PROFILE",
    "LINE_PROFILES",
    "SCATTER_PROFILE",
    "ERROR_BAR_PROFILE",
    "PSEUDOCOLOR_PROFILE",
    "HEATMAP_PROFILE",
    "CONTOUR_PROFILE",
    "COLORBAR_PROFILE",
    "REFERENCE_MARKS_PROFILE",
    "REFERENCE_LINE_PROFILE",
    "REFERENCE_BAND_PROFILE",
]

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
