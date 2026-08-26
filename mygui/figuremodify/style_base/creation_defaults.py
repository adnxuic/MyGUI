"""Resolve effective component-creation defaults from Matplotlib styles."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import matplotlib as mpl
from matplotlib.figure import Figure

from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context

from .color_models import PaletteDefinition, PaletteSource, normalize_color


MATPLOTLIB_STYLE_PALETTE_SOURCE = PaletteSource.MATPLOTLIB_STYLE

_LINESTYLE_ALIASES = {
    "solid": "-",
    "dashed": "--",
    "dashdot": "-.",
    "dash-dot": "-.",
    "dotted": ":",
    "none": "None",
}


def _linestyle_preset(value: object) -> str:
    text = str(value).strip()
    return _LINESTYLE_ALIASES.get(text.casefold(), text)


def _font_family(artist) -> str:
    families = artist.get_fontfamily()
    if isinstance(families, str):
        return families or "sans-serif"
    if families:
        return str(families[0])
    return "sans-serif"


def _axisbelow_value(value: object) -> bool | str:
    if value is True or value is False:
        return value
    if str(value).strip().casefold() == "line":
        return "line"
    return bool(value)


def _tick_level_defaults(axis, *, which: str) -> AxisLevelCreationDefaults:
    ticks = (
        axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
    )
    if not ticks:
        return AxisLevelCreationDefaults(
            ticks=TickCreationDefaults(
                primary_visible=which == "major",
                secondary_visible=False,
                direction="out",
                length=3.5 if which == "major" else 2.0,
                width=0.8 if which == "major" else 0.6,
                color="#000000",
            ),
            tick_labels=TickLabelCreationDefaults(
                primary_visible=which == "major",
                secondary_visible=False,
                color="#000000",
                fontfamily="sans-serif",
                fontsize=10.0,
                fontweight="normal",
                fontstyle="normal",
                rotation=0.0,
                pad=3.5 if which == "major" else 3.4,
            ),
            grid=GridCreationDefaults(
                visible=False,
                color="#B0B0B0",
                linestyle="-",
                linewidth=0.8,
                alpha=1.0,
            ),
        )
    tick = ticks[0]
    label = tick.label1
    gridline = tick.gridline
    alpha = gridline.get_alpha()
    return AxisLevelCreationDefaults(
        ticks=TickCreationDefaults(
            primary_visible=any(item.tick1line.get_visible() for item in ticks),
            secondary_visible=any(
                item.tick2line.get_visible() for item in ticks
            ),
            direction=str(getattr(tick, "_tickdir", "out") or "out"),
            length=float(tick.tick1line.get_markersize()),
            width=float(tick.tick1line.get_markeredgewidth()),
            color=normalize_color(tick.tick1line.get_color()),
        ),
        tick_labels=TickLabelCreationDefaults(
            primary_visible=any(item.label1.get_visible() for item in ticks),
            secondary_visible=any(item.label2.get_visible() for item in ticks),
            color=normalize_color(label.get_color()),
            fontfamily=_font_family(label),
            fontsize=float(label.get_fontsize()),
            fontweight=label.get_fontweight(),
            fontstyle=str(label.get_fontstyle()),
            rotation=float(label.get_rotation()),
            pad=float(tick.get_pad()),
        ),
        grid=GridCreationDefaults(
            visible=any(item.gridline.get_visible() for item in ticks),
            color=normalize_color(gridline.get_color()),
            linestyle=_linestyle_preset(gridline.get_linestyle()),
            linewidth=float(gridline.get_linewidth()),
            alpha=None if alpha is None else float(alpha),
        ),
    )


def _spine_defaults(axes, side: str) -> SpineCreationDefaults:
    spine = axes.spines[side]
    return SpineCreationDefaults(
        visible=bool(spine.get_visible()),
        color=normalize_color(spine.get_edgecolor()),
        linewidth=float(spine.get_linewidth()),
        linestyle=_linestyle_preset(spine.get_linestyle()),
    )


def _axes_creation_defaults(axes) -> AxesCreationDefaults:
    axes.minorticks_on()
    return AxesCreationDefaults(
        facecolor=normalize_color(axes.get_facecolor()),
        frameon=bool(axes.get_frame_on()),
        axisbelow=_axisbelow_value(axes.get_axisbelow()),
        spines=SpineBoxCreationDefaults(
            left=_spine_defaults(axes, "left"),
            right=_spine_defaults(axes, "right"),
            top=_spine_defaults(axes, "top"),
            bottom=_spine_defaults(axes, "bottom"),
        ),
        x=AxisSideCreationDefaults(
            major=_tick_level_defaults(axes.xaxis, which="major"),
            minor=_tick_level_defaults(axes.xaxis, which="minor"),
        ),
        y=AxisSideCreationDefaults(
            major=_tick_level_defaults(axes.yaxis, which="major"),
            minor=_tick_level_defaults(axes.yaxis, which="minor"),
        ),
    )


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
class ReferenceMarksCreationDefaults:
    """Style-derived defaults for auxiliary reflection-position marks."""

    color: str
    linewidth: float


@dataclass(frozen=True, slots=True)
class SpineCreationDefaults:
    """Effective defaults for one Axes spine."""

    visible: bool
    color: str
    linewidth: float
    linestyle: str


@dataclass(frozen=True, slots=True)
class SpineBoxCreationDefaults:
    """Effective defaults for the four standard Axes spines."""

    left: SpineCreationDefaults
    right: SpineCreationDefaults
    top: SpineCreationDefaults
    bottom: SpineCreationDefaults


@dataclass(frozen=True, slots=True)
class TickCreationDefaults:
    """Effective defaults for one Tick group."""

    primary_visible: bool
    secondary_visible: bool
    direction: str
    length: float
    width: float
    color: str


@dataclass(frozen=True, slots=True)
class TickLabelCreationDefaults:
    """Effective defaults for one Tick Label group."""

    primary_visible: bool
    secondary_visible: bool
    color: str
    fontfamily: str
    fontsize: float
    fontweight: str | int | float
    fontstyle: str
    rotation: float
    pad: float


@dataclass(frozen=True, slots=True)
class GridCreationDefaults:
    """Effective defaults for one Grid."""

    visible: bool
    color: str
    linestyle: str
    linewidth: float
    alpha: float | None


@dataclass(frozen=True, slots=True)
class AxisLevelCreationDefaults:
    """Ticks, tick labels, and grid for one major/minor level."""

    ticks: TickCreationDefaults
    tick_labels: TickLabelCreationDefaults
    grid: GridCreationDefaults


@dataclass(frozen=True, slots=True)
class AxisSideCreationDefaults:
    """Effective X or Y appearance for one style."""

    major: AxisLevelCreationDefaults
    minor: AxisLevelCreationDefaults


@dataclass(frozen=True, slots=True)
class AxesCreationDefaults:
    """Effective style defaults for a newly created ordinary Axes."""

    facecolor: str
    frameon: bool
    axisbelow: bool | str
    spines: SpineBoxCreationDefaults
    x: AxisSideCreationDefaults
    y: AxisSideCreationDefaults


@dataclass(frozen=True, slots=True)
class ComponentCreationDefaults:
    """Effective defaults and chart palette for one Figure style."""

    style: str
    line: LineCreationDefaults
    scatter: ScatterCreationDefaults
    text: TextCreationDefaults
    in_axes: InAxesCreationDefaults
    reference_marks: ReferenceMarksCreationDefaults
    chart_palette: PaletteDefinition
    axes: AxesCreationDefaults


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
    with matplotlib_style_context(style_name):
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
    with matplotlib_style_context(style_name):
        figure = Figure()
        line_axes = figure.add_subplot(1, 3, 1)
        scatter_axes = figure.add_subplot(1, 3, 2)
        text_axes = figure.add_subplot(1, 3, 3)

        line, = line_axes.plot([], [])
        scatter = scatter_axes.scatter([], [])
        text = text_axes.text(0.0, 0.0, "")
        reference_tick = text_axes.xaxis.get_major_ticks()[0].tick1line
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
            reference_marks=ReferenceMarksCreationDefaults(
                color=normalize_color(reference_tick.get_color()),
                linewidth=float(reference_tick.get_markeredgewidth()),
            ),
            chart_palette=_style_palette(style_name, cycle_colors),
            axes=_axes_creation_defaults(line_axes),
        )
    return defaults
