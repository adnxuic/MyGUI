"""Merge style, Axes palette, and application Components defaults at creation.

This module does not import ``ApplicationSettingsService``. Callers pass a
narrow Components snapshot or ``None``. Restore and history replay must not
call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mygui.figuremodify.style_base.color_models import ColorSelection, normalize_color
from mygui.figuremodify.style_base.creation_defaults import (
    AxesCreationDefaults,
    AxisLevelCreationDefaults,
    AxisSideCreationDefaults,
    GridCreationDefaults,
    LineCreationDefaults,
    ScatterCreationDefaults,
    SpineBoxCreationDefaults,
    SpineCreationDefaults,
    TextCreationDefaults,
    TickCreationDefaults,
    TickLabelCreationDefaults,
)


def _mode_value(setting: Any) -> str | None:
    if setting is None:
        return None
    mode = getattr(setting, "mode", None)
    if mode is None:
        return None
    return str(getattr(mode, "value", mode)).casefold()


def is_override(setting: Any) -> bool:
    """Return whether a Components field is an application override."""

    return _mode_value(setting) == "override"


def resolve_inheritable(explicit: Any, setting: Any, inherited: Any) -> Any:
    """Apply explicit input > Components override > style/palette inherited."""

    if explicit is not None:
        return explicit
    if is_override(setting):
        return setting.value
    return inherited


def resolve_chart_color_selection(
    *,
    explicit_color: Any = None,
    explicit_selection: ColorSelection | None = None,
    setting: Any = None,
    palette_selection: ColorSelection,
) -> ColorSelection:
    """Resolve Line/Scatter color. Inherit uses the Axes palette cursor."""

    if explicit_selection is not None:
        return explicit_selection
    if explicit_color is not None:
        return ColorSelection(normalize_color(explicit_color))
    if is_override(setting):
        return ColorSelection(normalize_color(setting.value))
    return palette_selection


@dataclass(frozen=True, slots=True)
class ResolvedLineAppearance:
    """Concrete Line kwargs for one creation. Not a style-probe snapshot."""

    color: str
    linestyle: str
    linewidth: float
    marker: str
    markersize: float
    markeredgewidth: float
    color_selection: ColorSelection

    @property
    def consume_palette(self) -> bool:
        return self.color_selection.palette is not None

    def plot_kwargs(self, *, label: str) -> dict[str, Any]:
        return {
            "color": self.color,
            "linestyle": self.linestyle,
            "linewidth": float(self.linewidth),
            "marker": self.marker,
            "markersize": float(self.markersize),
            "markeredgewidth": float(self.markeredgewidth),
            "label": label,
        }


@dataclass(frozen=True, slots=True)
class ResolvedScatterAppearance:
    """Concrete Scatter kwargs for one creation."""

    color: str
    marker: str
    size: float
    linewidth: float
    color_selection: ColorSelection

    @property
    def consume_palette(self) -> bool:
        return self.color_selection.palette is not None


@dataclass(frozen=True, slots=True)
class ResolvedTextAppearance:
    """Concrete free-Text kwargs for one creation.

    Inherited color/weight/style are ``None`` so the Figure style context
    supplies Matplotlib's native values (for example ``white``).
    """

    fontfamily: str
    fontsize: float
    color: str | None
    fontweight: str | int | float | None
    fontstyle: str | None


def resolve_line_appearance(
    style: LineCreationDefaults,
    settings: Any | None,
    *,
    palette_selection: ColorSelection,
    color: Any = None,
    color_selection: ColorSelection | None = None,
    linestyle: Any = None,
    linewidth: Any = None,
    marker: Any = None,
    markersize: Any = None,
    markeredgewidth: Any = None,
) -> ResolvedLineAppearance:
    """Resolve Line appearance for Function Curve, Plot, Fit, and Interpolation."""

    line_settings = None if settings is None else getattr(settings, "line", settings)
    selection = resolve_chart_color_selection(
        explicit_color=color,
        explicit_selection=color_selection,
        setting=getattr(line_settings, "color", None),
        palette_selection=palette_selection,
    )
    return ResolvedLineAppearance(
        color=selection.color,
        linestyle=str(
            resolve_inheritable(
                linestyle, getattr(line_settings, "linestyle", None), style.linestyle
            )
        ),
        linewidth=float(
            resolve_inheritable(
                linewidth, getattr(line_settings, "linewidth", None), style.linewidth
            )
        ),
        marker=str(
            resolve_inheritable(
                marker, getattr(line_settings, "marker", None), style.marker
            )
        ),
        markersize=float(
            resolve_inheritable(
                markersize, getattr(line_settings, "markersize", None), style.markersize
            )
        ),
        markeredgewidth=float(
            resolve_inheritable(
                markeredgewidth,
                getattr(line_settings, "markeredgewidth", None),
                style.markeredgewidth,
            )
        ),
        color_selection=selection,
    )


def resolve_scatter_appearance(
    style: ScatterCreationDefaults,
    settings: Any | None,
    *,
    palette_selection: ColorSelection,
    color: Any = None,
    color_selection: ColorSelection | None = None,
    marker: Any = None,
    size: Any = None,
    linewidth: Any = None,
) -> ResolvedScatterAppearance:
    """Resolve ordinary Scatter appearance. Mapping/XRD explicit values still win."""

    scatter_settings = (
        None if settings is None else getattr(settings, "scatter", settings)
    )
    selection = resolve_chart_color_selection(
        explicit_color=color,
        explicit_selection=color_selection,
        setting=getattr(scatter_settings, "color", None),
        palette_selection=palette_selection,
    )
    return ResolvedScatterAppearance(
        color=selection.color,
        marker=str(
            resolve_inheritable(
                marker, getattr(scatter_settings, "marker", None), style.marker
            )
        ),
        size=float(
            resolve_inheritable(size, getattr(scatter_settings, "size", None), style.size)
        ),
        linewidth=float(
            resolve_inheritable(
                linewidth, getattr(scatter_settings, "linewidth", None), style.linewidth
            )
        ),
        color_selection=selection,
    )


def resolve_text_appearance(
    style: TextCreationDefaults,
    settings: Any | None,
    *,
    fontfamily: Any = None,
    fontsize: Any = None,
    color: Any = None,
    fontweight: Any = None,
    fontstyle: Any = None,
) -> ResolvedTextAppearance:
    """Resolve free Text. Title and axis labels must not use this path."""

    text_settings = None if settings is None else getattr(settings, "text", settings)
    color_setting = getattr(text_settings, "color", None)
    if color is not None:
        resolved_color = color
    elif is_override(color_setting):
        resolved_color = normalize_color(color_setting.value)
    else:
        resolved_color = None
    weight_setting = getattr(text_settings, "fontweight", None)
    if fontweight is not None:
        resolved_weight = fontweight
    elif is_override(weight_setting):
        resolved_weight = weight_setting.value
    else:
        resolved_weight = None
    style_setting = getattr(text_settings, "fontstyle", None)
    if fontstyle is not None:
        resolved_style = fontstyle
    elif is_override(style_setting):
        resolved_style = str(style_setting.value)
    else:
        resolved_style = None
    return ResolvedTextAppearance(
        fontfamily=str(
            resolve_inheritable(
                fontfamily,
                getattr(text_settings, "fontfamily", None),
                style.fontfamily,
            )
        ),
        fontsize=float(
            resolve_inheritable(
                fontsize, getattr(text_settings, "fontsize", None), style.fontsize
            )
        ),
        color=resolved_color if resolved_color is None else str(resolved_color),
        fontweight=resolved_weight,
        fontstyle=resolved_style,
    )


MATPLOTLIB_39_AXES_FALLBACK = AxesCreationDefaults(
    facecolor="#FFFFFF",
    frameon=True,
    axisbelow="line",
    spines=SpineBoxCreationDefaults(
        left=SpineCreationDefaults(True, "#000000", 0.8, "-"),
        right=SpineCreationDefaults(True, "#000000", 0.8, "-"),
        top=SpineCreationDefaults(True, "#000000", 0.8, "-"),
        bottom=SpineCreationDefaults(True, "#000000", 0.8, "-"),
    ),
    x=AxisSideCreationDefaults(
        major=AxisLevelCreationDefaults(
            ticks=TickCreationDefaults(True, False, "out", 3.5, 0.8, "#000000"),
            tick_labels=TickLabelCreationDefaults(
                True, False, "#000000", "sans-serif", 10.0, "normal", "normal", 0.0, 3.5
            ),
            grid=GridCreationDefaults(False, "#B0B0B0", "-", 0.8, None),
        ),
        minor=AxisLevelCreationDefaults(
            ticks=TickCreationDefaults(False, False, "out", 2.0, 0.6, "#000000"),
            tick_labels=TickLabelCreationDefaults(
                False, False, "#000000", "sans-serif", 10.0, "normal", "normal", 0.0, 3.4
            ),
            grid=GridCreationDefaults(False, "#B0B0B0", "-", 0.8, None),
        ),
    ),
    y=AxisSideCreationDefaults(
        major=AxisLevelCreationDefaults(
            ticks=TickCreationDefaults(True, False, "out", 3.5, 0.8, "#000000"),
            tick_labels=TickLabelCreationDefaults(
                True, False, "#000000", "sans-serif", 10.0, "normal", "normal", 0.0, 3.5
            ),
            grid=GridCreationDefaults(False, "#B0B0B0", "-", 0.8, None),
        ),
        minor=AxisLevelCreationDefaults(
            ticks=TickCreationDefaults(False, False, "out", 2.0, 0.6, "#000000"),
            tick_labels=TickLabelCreationDefaults(
                False, False, "#000000", "sans-serif", 10.0, "normal", "normal", 0.0, 3.4
            ),
            grid=GridCreationDefaults(False, "#B0B0B0", "-", 0.8, None),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ResolvedAxesAppearance:
    """Concrete ordinary-Axes appearance for one creation. Not project state."""

    facecolor: str
    frameon: bool
    axisbelow: bool | str
    spines: SpineBoxCreationDefaults
    x: AxisSideCreationDefaults
    y: AxisSideCreationDefaults


def _resolve_or_fallback(setting: Any, inherited: Any, fallback: Any) -> Any:
    resolved = resolve_inheritable(None, setting, inherited)
    if resolved is None and fallback is not None and setting is not None:
        if not is_override(setting):
            return inherited if inherited is not None else fallback
    if resolved is None:
        return fallback
    return resolved


def _resolve_color(setting: Any, inherited: str, fallback: str) -> str:
    resolved = _resolve_or_fallback(setting, inherited, fallback)
    return normalize_color(resolved)


def _resolve_spine(
    setting: Any,
    inherited: SpineCreationDefaults,
    fallback: SpineCreationDefaults,
) -> SpineCreationDefaults:
    return SpineCreationDefaults(
        visible=bool(
            _resolve_or_fallback(
                getattr(setting, "visible", None),
                inherited.visible,
                fallback.visible,
            )
        ),
        color=_resolve_color(
            getattr(setting, "color", None), inherited.color, fallback.color
        ),
        linewidth=float(
            _resolve_or_fallback(
                getattr(setting, "linewidth", None),
                inherited.linewidth,
                fallback.linewidth,
            )
        ),
        linestyle=str(
            _resolve_or_fallback(
                getattr(setting, "linestyle", None),
                inherited.linestyle,
                fallback.linestyle,
            )
        ),
    )


def _resolve_ticks(
    setting: Any,
    inherited: TickCreationDefaults,
    fallback: TickCreationDefaults,
) -> TickCreationDefaults:
    return TickCreationDefaults(
        primary_visible=bool(
            _resolve_or_fallback(
                getattr(setting, "primary_visible", None),
                inherited.primary_visible,
                fallback.primary_visible,
            )
        ),
        secondary_visible=bool(
            _resolve_or_fallback(
                getattr(setting, "secondary_visible", None),
                inherited.secondary_visible,
                fallback.secondary_visible,
            )
        ),
        direction=str(
            _resolve_or_fallback(
                getattr(setting, "direction", None),
                inherited.direction,
                fallback.direction,
            )
        ),
        length=float(
            _resolve_or_fallback(
                getattr(setting, "length", None), inherited.length, fallback.length
            )
        ),
        width=float(
            _resolve_or_fallback(
                getattr(setting, "width", None), inherited.width, fallback.width
            )
        ),
        color=_resolve_color(
            getattr(setting, "color", None), inherited.color, fallback.color
        ),
    )


def _resolve_tick_labels(
    setting: Any,
    inherited: TickLabelCreationDefaults,
    fallback: TickLabelCreationDefaults,
) -> TickLabelCreationDefaults:
    return TickLabelCreationDefaults(
        primary_visible=bool(
            _resolve_or_fallback(
                getattr(setting, "primary_visible", None),
                inherited.primary_visible,
                fallback.primary_visible,
            )
        ),
        secondary_visible=bool(
            _resolve_or_fallback(
                getattr(setting, "secondary_visible", None),
                inherited.secondary_visible,
                fallback.secondary_visible,
            )
        ),
        color=_resolve_color(
            getattr(setting, "color", None), inherited.color, fallback.color
        ),
        fontfamily=str(
            _resolve_or_fallback(
                getattr(setting, "fontfamily", None),
                inherited.fontfamily,
                fallback.fontfamily,
            )
        ),
        fontsize=float(
            _resolve_or_fallback(
                getattr(setting, "fontsize", None),
                inherited.fontsize,
                fallback.fontsize,
            )
        ),
        fontweight=_resolve_or_fallback(
            getattr(setting, "fontweight", None),
            inherited.fontweight,
            fallback.fontweight,
        ),
        fontstyle=str(
            _resolve_or_fallback(
                getattr(setting, "fontstyle", None),
                inherited.fontstyle,
                fallback.fontstyle,
            )
        ),
        rotation=float(
            _resolve_or_fallback(
                getattr(setting, "rotation", None),
                inherited.rotation,
                fallback.rotation,
            )
        ),
        pad=float(
            _resolve_or_fallback(
                getattr(setting, "pad", None), inherited.pad, fallback.pad
            )
        ),
    )


def _resolve_grid(
    setting: Any,
    inherited: GridCreationDefaults,
    fallback: GridCreationDefaults,
) -> GridCreationDefaults:
    alpha_setting = getattr(setting, "alpha", None)
    if is_override(alpha_setting):
        alpha = alpha_setting.value
    else:
        alpha = inherited.alpha
    return GridCreationDefaults(
        visible=bool(
            _resolve_or_fallback(
                getattr(setting, "visible", None),
                inherited.visible,
                fallback.visible,
            )
        ),
        color=_resolve_color(
            getattr(setting, "color", None), inherited.color, fallback.color
        ),
        linestyle=str(
            _resolve_or_fallback(
                getattr(setting, "linestyle", None),
                inherited.linestyle,
                fallback.linestyle,
            )
        ),
        linewidth=float(
            _resolve_or_fallback(
                getattr(setting, "linewidth", None),
                inherited.linewidth,
                fallback.linewidth,
            )
        ),
        alpha=None if alpha is None else float(alpha),
    )


def _resolve_level(
    setting: Any,
    inherited: AxisLevelCreationDefaults,
    fallback: AxisLevelCreationDefaults,
) -> AxisLevelCreationDefaults:
    return AxisLevelCreationDefaults(
        ticks=_resolve_ticks(
            getattr(setting, "ticks", None), inherited.ticks, fallback.ticks
        ),
        tick_labels=_resolve_tick_labels(
            getattr(setting, "tick_labels", None),
            inherited.tick_labels,
            fallback.tick_labels,
        ),
        grid=_resolve_grid(
            getattr(setting, "grid", None), inherited.grid, fallback.grid
        ),
    )


def _resolve_axis(
    setting: Any,
    inherited: AxisSideCreationDefaults,
    fallback: AxisSideCreationDefaults,
) -> AxisSideCreationDefaults:
    return AxisSideCreationDefaults(
        major=_resolve_level(
            getattr(setting, "major", None), inherited.major, fallback.major
        ),
        minor=_resolve_level(
            getattr(setting, "minor", None), inherited.minor, fallback.minor
        ),
    )


def resolve_axes_appearance(
    style: AxesCreationDefaults | None,
    settings: Any | None,
) -> ResolvedAxesAppearance:
    """Merge Axes Components overrides with Figure style and Matplotlib 3.9 fallbacks.

    Explicit AxesViewSpec / XRD / layout values are applied after this snapshot.
    """

    inherited = style if style is not None else MATPLOTLIB_39_AXES_FALLBACK
    axes_settings = None if settings is None else getattr(settings, "axes", settings)
    fallback = MATPLOTLIB_39_AXES_FALLBACK
    spines_settings = getattr(axes_settings, "spines", None)
    return ResolvedAxesAppearance(
        facecolor=_resolve_color(
            getattr(axes_settings, "facecolor", None),
            inherited.facecolor,
            fallback.facecolor,
        ),
        frameon=bool(
            _resolve_or_fallback(
                getattr(axes_settings, "frameon", None),
                inherited.frameon,
                fallback.frameon,
            )
        ),
        axisbelow=_resolve_or_fallback(
            getattr(axes_settings, "axisbelow", None),
            inherited.axisbelow,
            fallback.axisbelow,
        ),
        spines=SpineBoxCreationDefaults(
            left=_resolve_spine(
                getattr(spines_settings, "left", None),
                inherited.spines.left,
                fallback.spines.left,
            ),
            right=_resolve_spine(
                getattr(spines_settings, "right", None),
                inherited.spines.right,
                fallback.spines.right,
            ),
            top=_resolve_spine(
                getattr(spines_settings, "top", None),
                inherited.spines.top,
                fallback.spines.top,
            ),
            bottom=_resolve_spine(
                getattr(spines_settings, "bottom", None),
                inherited.spines.bottom,
                fallback.spines.bottom,
            ),
        ),
        x=_resolve_axis(
            getattr(axes_settings, "x", None), inherited.x, fallback.x
        ),
        y=_resolve_axis(
            getattr(axes_settings, "y", None), inherited.y, fallback.y
        ),
    )
