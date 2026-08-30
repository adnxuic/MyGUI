"""Implement reusable appearance and text editor sections."""

from ._types import (
    ApplyProperties,
    ApplyReferences,
)

from .property import (
    PropertySection,
    ReferenceMarksPositionSection,
)

from .data import (
    DataReferenceSection,
    Field2DDataSection,
    RawXYDataSection,
    ReferenceMarksDataSection,
    ScatterMappingSection,
    ColorbarSourceSection,
    ImageInAxesSourceSection,
)

from .errorbar import (
    ErrorBarDataSection,
)

from .axes import (
    AxesLimitsSection,
    AxesLayoutSection,
)
from .axis_ticks import (
    AxisTickSettingsDialog,
    AxisTickSettingsSection,
)

from .appearance import (
    LineAppearanceSection,
    ScatterAppearanceSection,
)

from .text import (
    TextContentSection,
    TextTypographySection,
    TextTransformSection,
    TextPositionSection,
    TextRenderSection,
)

from .annotation import (
    ANNOTATION_PLACEMENT_PRESETS,
    AnnotationArrowSection,
    AnnotationContentSection,
    AnnotationPlacementSection,
    AnnotationPropertySection,
    AnnotationTypographySection,
)

from .legend import (
    LegendLocationSection,
)

from .palette import (
    PaletteSection,
    _PalettePreview,
)


__all__ = [
    "ANNOTATION_PLACEMENT_PRESETS",
    "AnnotationArrowSection",
    "AnnotationContentSection",
    "AnnotationPlacementSection",
    "AnnotationPropertySection",
    "AnnotationTypographySection",
    "ApplyProperties",
    "ApplyReferences",
    "PropertySection",
    "ReferenceMarksPositionSection",
    "DataReferenceSection",
    "Field2DDataSection",
    "RawXYDataSection",
    "ReferenceMarksDataSection",
    "ScatterMappingSection",
    "ColorbarSourceSection",
    "ImageInAxesSourceSection",
    "ErrorBarDataSection",
    "AxesLimitsSection",
    "AxesLayoutSection",
    "AxisTickSettingsDialog",
    "AxisTickSettingsSection",
    "LineAppearanceSection",
    "ScatterAppearanceSection",
    "TextContentSection",
    "TextTypographySection",
    "TextTransformSection",
    "TextPositionSection",
    "TextRenderSection",
    "LegendLocationSection",
    "PaletteSection",
    "_PalettePreview",
]
