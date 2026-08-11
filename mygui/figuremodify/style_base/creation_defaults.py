"""Resolve effective component-creation defaults from Matplotlib styles."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import matplotlib as mpl
from matplotlib import style as mpl_style
from matplotlib.figure import Figure

from .color_models import PaletteDefinition, PaletteSource, normalize_color


MATPLOTLIB_STYLE_PALETTE_SOURCE = PaletteSource.MATPLOTLIB_STYLE


@dataclass(frozen=True, slots=True)
class LineCreationDefaults:
    """Effective defaults for a newly created Matplotlib line."""

    linestyle: str
    linewidth: float
    marker: str
    markersize: float
    markeredgewidth: float


@dataclass(frozen=True, slots=True)
class ScatterCreationDefaults:
    """Effective defaults for a newly created Matplotlib scatter collection."""

    marker: str
    size: float
    linewidth: float


@dataclass(frozen=True, slots=True)
class TextCreationDefaults:
    """Effective defaults for newly created free text."""

    fontfamily: str
    fontsize: float
    color: str
    fontweight: str | int | float
    fontstyle: str


@dataclass(frozen=True, slots=True)
class InAxesCreationDefaults:
    """Effective style defaults for a newly created inset Axes."""

    facecolor: str
    edgecolor: str
    linewidth: float
    indicator_color: str
    indicator_linestyle: str
    indicator_linewidth: float
    image_interpolation: str


@dataclass(frozen=True, slots=True)
class ComponentCreationDefaults:
    """Effective defaults and chart palette for one Figure style."""

    style: str
    line: LineCreationDefaults
    scatter: ScatterCreationDefaults
    text: TextCreationDefaults
    in_axes: InAxesCreationDefaults
    chart_palette: PaletteDefinition


def _style_palette(
    style: str,
    colors: tuple[str, ...],
) -> PaletteDefinition:
    fingerprint = sha256(
        (style + "\0" + "\0".join(colors)).encode("utf-8")
    ).hexdigest()[:20]
    return PaletteDefinition(
        id=f"matplotlib-style:{fingerprint}",
        name=f"Matplotlib style: {style}",
        category="Matplotlib",
        source=MATPLOTLIB_STYLE_PALETTE_SOURCE,
        colors=colors,
    )


def resolve_style_palette(style: str | None) -> PaletteDefinition:
    """Resolve only the ordered chart colors for a Matplotlib style."""

    style_name = str(style or "default")
    with mpl_style.context(style_name):
        cycle_colors = tuple(
            normalize_color(color)
            for color in mpl.rcParams["axes.prop_cycle"].by_key().get(
                "color",
                (),
            )
        )
        if not cycle_colors:
            figure = Figure()
            axes = figure.subplots()
            line, = axes.plot([], [])
            cycle_colors = (normalize_color(line.get_color()),)
        return _style_palette(style_name, cycle_colors)


def resolve_component_creation_defaults(
    style: str | None,
) -> ComponentCreationDefaults:
    """Probe Matplotlib artists and return defaults for ``style``.

    A short-lived style context is important here: Matplotlib rcParams are
    process-global, while the returned value must be an immutable per-canvas
    snapshot suitable for constructing a dialog after the context has exited.
    """

    style_name = str(style or "default")
    with mpl_style.context(style_name):
        figure = Figure()
        line_axes = figure.add_subplot(1, 3, 1)
        scatter_axes = figure.add_subplot(1, 3, 2)
        text_axes = figure.add_subplot(1, 3, 3)

        line, = line_axes.plot([], [])
        scatter = scatter_axes.scatter([], [])
        text = text_axes.text(0.0, 0.0, "")
        inset = text_axes.inset_axes((0.55, 0.55, 0.35, 0.35))
        indicator, _connectors = text_axes.indicate_inset_zoom(inset)

        cycle_colors = tuple(
            normalize_color(color)
            for color in mpl.rcParams["axes.prop_cycle"].by_key().get(
                "color",
                (),
            )
        )
        if not cycle_colors:
            cycle_colors = (normalize_color(line.get_color()),)

        scatter_sizes = scatter.get_sizes()
        scatter_widths = scatter.get_linewidths()
        text_families = text.get_fontfamily()

        defaults = ComponentCreationDefaults(
            style=style_name,
            line=LineCreationDefaults(
                linestyle=str(line.get_linestyle()),
                linewidth=float(line.get_linewidth()),
                marker=str(line.get_marker()),
                markersize=float(line.get_markersize()),
                markeredgewidth=float(line.get_markeredgewidth()),
            ),
            scatter=ScatterCreationDefaults(
                marker=str(mpl.rcParams["scatter.marker"]),
                size=float(scatter_sizes[0]) if len(scatter_sizes) else 0.0,
                linewidth=(
                    float(scatter_widths[0])
                    if len(scatter_widths)
                    else 0.0
                ),
            ),
            text=TextCreationDefaults(
                fontfamily=(
                    str(text_families[0])
                    if text_families
                    else "sans-serif"
                ),
                fontsize=float(text.get_fontsize()),
                color=normalize_color(text.get_color()),
                fontweight=text.get_fontweight(),
                fontstyle=str(text.get_fontstyle()),
            ),
            in_axes=InAxesCreationDefaults(
                facecolor=normalize_color(inset.get_facecolor()),
                edgecolor=normalize_color(
                    inset.spines["left"].get_edgecolor()
                ),
                linewidth=float(inset.spines["left"].get_linewidth()),
                indicator_color=normalize_color(indicator.get_edgecolor()),
                indicator_linestyle=str(indicator.get_linestyle()),
                indicator_linewidth=float(indicator.get_linewidth()),
                image_interpolation=(
                    str(mpl.rcParams["image.interpolation"])
                    if str(mpl.rcParams["image.interpolation"])
                    in {"nearest", "bilinear", "bicubic"}
                    else "bilinear"
                ),
            ),
            chart_palette=_style_palette(style_name, cycle_colors),
        )
    return defaults
