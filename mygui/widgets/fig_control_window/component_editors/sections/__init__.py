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
    RawXYDataSection,
    ReferenceMarksDataSection,
    ScatterMappingSection,
    ColorbarSourceSection,
    ImageInAxesSourceSection,
)

from .axes import (
    AxesLimitsSection,
    AxesLayoutSection,
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

from .legend import (
    LegendLocationSection,
)

from .palette import (
    PaletteSection,
    _PalettePreview,
)


__all__ = [
    "ApplyProperties",
    "ApplyReferences",
    "PropertySection",
    "ReferenceMarksPositionSection",
    "DataReferenceSection",
    "RawXYDataSection",
    "ReferenceMarksDataSection",
    "ScatterMappingSection",
    "ColorbarSourceSection",
    "ImageInAxesSourceSection",
    "AxesLimitsSection",
    "AxesLayoutSection",
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
