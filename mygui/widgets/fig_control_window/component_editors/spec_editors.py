"""Structured dialog editors for the current closed value contracts.

This module is the stable facade. Domain editors live in Axis, Text/Annotation,
Chart, and Field/Mapping modules and are registered explicitly; there is no
generic or JSON fallback.
"""

from __future__ import annotations

from .spec_editor_base import StructuredValueEditor
from .spec_editors_axis import (
    AxisFormatterEditor,
    AxisLocatorEditor,
    AxisScaleEditor,
    FigureLayoutEditor,
)
from .spec_editors_chart import (
    CONNECTOR_LABELS,
    ErrorEveryEditor,
    MarkEveryEditor,
    ScatterColorMapEditor,
    ScatterSizeMapEditor,
    ZoomConnectorsEditor,
    normalize_connectors,
)
from .spec_editors_field import (
    ColorMapSpecEditor,
    ContourLabelSpecEditor,
    ContourLevelsSpecEditor,
    GridEdgeSpecEditor,
    NormSpecEditor,
)
from .spec_editors_text import (
    AnnotationBoxEditor,
    FontSpecEditor,
    TEXT_BOX_STYLES,
    TextBoxEditor,
)

__all__ = [
    "AxisFormatterEditor",
    "AxisLocatorEditor",
    "AxisScaleEditor",
    "CONNECTOR_LABELS",
    "ColorMapSpecEditor",
    "ContourLabelSpecEditor",
    "ContourLevelsSpecEditor",
    "ErrorEveryEditor",
    "FigureLayoutEditor",
    "FontSpecEditor",
    "GridEdgeSpecEditor",
    "MarkEveryEditor",
    "NormSpecEditor",
    "ScatterColorMapEditor",
    "ScatterSizeMapEditor",
    "StructuredValueEditor",
    "TEXT_BOX_STYLES",
    "TextBoxEditor",
    "ZoomConnectorsEditor",
    "normalize_connectors",
    "AnnotationBoxEditor",
]
