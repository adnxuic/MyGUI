"""Short Inspector labels. Full explanations stay in PropertySpec tooltips."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

INSPECTOR_LABELS: dict[str, tuple[str, str]] = {
    "dpi": ("DPI", "Canvas resolution in dots per inch."),
    "facecolor": ("Background", "Background fill color."),
    "edgecolor": ("Border", "Border outline color."),
    "size_inches": ("Size", "Physical figure size in inches (width, height)."),
    "layout_engine": ("Layout Engine", "Figure layout engine and its parameters."),
    "frameon": ("Frame", "Draw the background rectangle and bounding frame."),
    "linewidth": ("Line Width", "Border stroke width in points."),
    "autoscalex_on": ("Autoscale X", "Fit the X limits to the current data."),
    "autoscaley_on": ("Autoscale Y", "Fit the Y limits to the current data."),
    "xlim": ("X Limits", "X-axis data limits."),
    "ylim": ("Y Limits", "Y-axis data limits."),
    "xmargin": ("X Margin", "Padding added to each side of the X data range during autoscale."),
    "ymargin": ("Y Margin", "Padding added to each side of the Y data range during autoscale."),
    "y_lower_reserve": ("Y Reserve", "Extra visual clearance below the autoscale interval."),
    "axisbelow": ("Axis Below", "Whether grid and ticks draw below chart artists."),
    "linestyle": ("Line Style", "Line pattern."),
    "markersize": ("Marker Size", "Marker size in points."),
    "markerfacecolor": ("Marker Face", "Marker fill color."),
    "markeredgecolor": ("Marker Edge", "Marker outline color."),
    "markeredgewidth": ("Marker Edge Width", "Marker outline width."),
    "clip_on": ("Clip", "Clip this artist to its parent Axes."),
    "rasterized": ("Rasterized", "Rasterize this artist in vector exports."),
    "sketch_params": ("Sketch", "Hand-drawn sketch effect (scale, length, randomness)."),
    "in_layout": ("In Layout", "Include this artist in layout-engine calculations."),
    "color_cycle": ("Palette", "Ordered color cycle for newly created series."),
}


def _declared_text(spec: Any, field: str) -> str:
    if isinstance(spec, Mapping):
        value = spec.get(field)
    else:
        value = getattr(spec, field, None)
    if value is None:
        return ""
    return str(value).strip()


def inspector_label(spec: Any, key: str) -> str:
    """Return the short Inspector label for a property."""

    declared = _declared_text(spec, "label")
    if declared:
        return declared
    mapped = INSPECTOR_LABELS.get(key)
    if mapped is not None:
        return mapped[0]
    return str(key).replace("_", " ").title()


def inspector_tooltip(spec: Any, key: str) -> str:
    """Return the full Inspector tooltip for a property."""

    declared = _declared_text(spec, "tooltip")
    if declared:
        return declared
    mapped = INSPECTOR_LABELS.get(key)
    if mapped is not None:
        return mapped[1]
    return ""
