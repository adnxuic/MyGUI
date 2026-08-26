"""Controller-free creation inputs shared by dialogs and Inspector sections."""

from __future__ import annotations

from .appearance_inputs import (
    InAxesInput,
    InterpolationOptionsInput,
    LineAppearanceInput,
)
from .data_inputs import (
    DataReferenceInput,
    Field2DDataReferenceInput,
    MultiSeriesDataReferenceInput,
    ScatterMappingInput,
)
from .reference_inputs import (
    ColorbarInput,
    ReferenceBandInput,
    ReferenceLineInput,
    ReferenceMarksInput,
)

__all__ = [
    "ColorbarInput",
    "DataReferenceInput",
    "Field2DDataReferenceInput",
    "InAxesInput",
    "InterpolationOptionsInput",
    "LineAppearanceInput",
    "MultiSeriesDataReferenceInput",
    "ReferenceBandInput",
    "ReferenceLineInput",
    "ReferenceMarksInput",
    "ScatterMappingInput",
]
