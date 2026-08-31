"""Shared, Controller-free helpers for chart creation dialogs."""

from __future__ import annotations

from typing import Any

from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.figuremodify.style_base.creation_defaults import (
    resolve_component_creation_defaults,
)
from mygui.widgets.fig_control_window.component_editors import (
    LineAppearanceInput,
)


def creation_defaults(figure_window: Any):
    """Return the frozen Figure-style defaults for a dialog opening."""

    canvas = getattr(figure_window, "current_canva", None)
    if canvas is None:
        return resolve_component_creation_defaults("default")
    return canvas.component_creation_defaults()


def settings_snapshot(figure_window: Any):
    """Return one immutable Components-defaults snapshot when available."""

    snapshot = getattr(figure_window, "snapshot_component_defaults", None)
    if not callable(snapshot):
        return None
    return snapshot()


def palette_selection(figure_window: Any) -> ColorSelection:
    """Peek at the current Axes palette without consuming its cursor."""

    selector = figure_window.get_current_canvas_axes_colorselector()
    if selector is None:
        return ColorSelection("#1F77B4")
    return selector.peek()


def new_line_appearance_input(
    figure_window: Any,
    *,
    parent=None,
    **kwargs,
) -> LineAppearanceInput:
    """Build a Controller-free line appearance input for one dialog."""

    return LineAppearanceInput(
        colorselector=figure_window.get_current_canvas_axes_colorselector(),
        color_library=figure_window.color_library,
        parent=parent,
        **kwargs,
    )
