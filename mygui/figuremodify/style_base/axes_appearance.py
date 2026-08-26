"""Apply resolved ordinary-Axes appearance to a live Matplotlib Axes.

Settings and Settings Center pages must not import this module. Creation
dialogs consume ``ResolvedAxesAppearance`` only.
"""

from __future__ import annotations

from matplotlib.axes import Axes

from mygui.figuremodify.style_base.creation_defaults import (
    AxisLevelCreationDefaults,
    AxisSideCreationDefaults,
)
from mygui.figuremodify.style_base.creation_preferences import ResolvedAxesAppearance


def apply_resolved_axes_appearance(
    target: Axes,
    appearance: ResolvedAxesAppearance,
    *,
    right_y: bool = False,
) -> None:
    """Write resolved appearance onto ``target`` before view-spec overrides."""

    target.set_facecolor(appearance.facecolor)
    target.set_frame_on(bool(appearance.frameon))
    target.set_axisbelow(appearance.axisbelow)
    for side in ("left", "right", "top", "bottom"):
        spine = target.spines[side]
        spec = getattr(appearance.spines, side)
        spine.set_visible(bool(spec.visible))
        spine.set_edgecolor(spec.color)
        spine.set_linewidth(float(spec.linewidth))
        spine.set_linestyle(spec.linestyle)
    sides = (appearance.y,) if right_y else (appearance.x, appearance.y)
    names = ("y",) if right_y else ("x", "y")
    for name, side in zip(names, sides, strict=True):
        _apply_axis_side(target, name, side)


def _minor_needed(side: AxisSideCreationDefaults) -> bool:
    minor = side.minor
    return bool(
        minor.ticks.primary_visible
        or minor.ticks.secondary_visible
        or minor.tick_labels.primary_visible
        or minor.tick_labels.secondary_visible
        or minor.grid.visible
    )


def _apply_axis_side(
    target: Axes,
    axis_name: str,
    side: AxisSideCreationDefaults,
) -> None:
    axis = target.xaxis if axis_name == "x" else target.yaxis
    if _minor_needed(side):
        axis.minorticks_on()
    _apply_level(target, axis_name, "major", side.major)
    _apply_level(target, axis_name, "minor", side.minor)


def _apply_level(
    target: Axes,
    axis_name: str,
    which: str,
    level: AxisLevelCreationDefaults,
) -> None:
    ticks = level.ticks
    labels = level.tick_labels
    if axis_name == "x":
        tick_kwargs = {
            "bottom": bool(ticks.primary_visible),
            "top": bool(ticks.secondary_visible),
            "labelbottom": bool(labels.primary_visible),
            "labeltop": bool(labels.secondary_visible),
        }
    else:
        tick_kwargs = {
            "left": bool(ticks.primary_visible),
            "right": bool(ticks.secondary_visible),
            "labelleft": bool(labels.primary_visible),
            "labelright": bool(labels.secondary_visible),
        }
    target.tick_params(
        axis=axis_name,
        which=which,
        direction=str(ticks.direction),
        length=float(ticks.length),
        width=float(ticks.width),
        color=ticks.color,
        labelcolor=labels.color,
        labelsize=float(labels.fontsize),
        labelrotation=float(labels.rotation),
        labelfontfamily=str(labels.fontfamily),
        pad=float(labels.pad),
        **tick_kwargs,
    )
    axis = target.xaxis if axis_name == "x" else target.yaxis
    tick_artists = (
        axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
    )
    for tick in tick_artists:
        for label in (tick.label1, tick.label2):
            label.set_fontweight(labels.fontweight)
            label.set_fontstyle(str(labels.fontstyle))
    grid = level.grid
    grid_kwargs: dict[str, object] = {
        "color": grid.color,
        "linestyle": grid.linestyle,
        "linewidth": float(grid.linewidth),
    }
    if grid.alpha is not None:
        grid_kwargs["alpha"] = float(grid.alpha)
    visible = bool(grid.visible)
    target.grid(True, axis=axis_name, which=which, **grid_kwargs)
    target.grid(visible, axis=axis_name, which=which)
