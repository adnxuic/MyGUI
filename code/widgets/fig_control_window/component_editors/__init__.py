"""Reusable Qt editors for Matplotlib component controllers.

The package depends on Controller objects only through their public interface.
Editors therefore remain reusable across concrete component roles.
"""

from .base import ComponentEditorBase
from .common import (
    DebouncedTextBinding,
    LineStyleEditor,
    NullableDoubleEditor,
    NumericTupleEditor,
    RangeEditor,
    ScatterStyleEditor,
    SpinePositionEditor,
    modification_succeeded,
    normalize_line_style,
)
from .registry import EditorKey, EditorRegistry
from .inspector import (
    ComponentInspector,
    EditorProfile,
    EditorPlacement,
    EditorSection,
    SectionSpec,
    TreePresentationSpec,
)
from .inputs import (
    DataReferenceInput,
    InterpolationOptionsInput,
    LineAppearanceInput,
)
from .profiles import register_production_profiles
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
from .context import (
    ComponentEditorManager,
    EditorContext,
    MessagePresenter,
)

__all__ = [
    "ComponentEditorBase",
    "DebouncedTextBinding",
    "EditorRegistry",
    "EditorKey",
    "ComponentInspector",
    "EditorProfile",
    "EditorPlacement",
    "EditorSection",
    "SectionSpec",
    "TreePresentationSpec",
    "DataReferenceInput",
    "InterpolationOptionsInput",
    "LineAppearanceInput",
    "register_production_profiles",
    "DataReferenceSection",
    "PropertySection",
    "LineAppearanceSection",
    "ScatterAppearanceSection",
    "TextContentSection",
    "TextTypographySection",
    "TextTransformSection",
    "TextPositionSection",
    "TextRenderSection",
    "LegendLocationSection",
    "PaletteSection",
    "ComponentEditorManager",
    "EditorContext",
    "MessagePresenter",
    "LineStyleEditor",
    "NullableDoubleEditor",
    "NumericTupleEditor",
    "RangeEditor",
    "ScatterStyleEditor",
    "SpinePositionEditor",
    "modification_succeeded",
    "normalize_line_style",
]
