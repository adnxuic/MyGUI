"""Shared, Controller-free helpers for chart creation dialogs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mygui import status_messages
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.figuremodify.style_base.creation_defaults import (
    resolve_component_creation_defaults,
)
from mygui.widgets.fig_control_window.component_editors import (
    LineAppearanceInput,
)


@dataclass(frozen=True, slots=True)
class CreationRunResult:
    """Outcome of one Canvas creation request. ``succeeded`` is independent of value."""

    succeeded: bool
    value: Any = None

    def __bool__(self) -> bool:
        return self.succeeded


class CreationDialogSession:
    """Execute one Canvas creation request with a single Message Bar result.

    Dialogs keep constructing typed requests and local QMessageBox pre-checks.
    This session runs the Canvas call, isolates exceptions, and does not emit
    an extra Message Bar result on success unless the caller presents one.
    """

    def __init__(self, dialog, figure_window: Any) -> None:
        self.dialog = dialog
        self.figure_window = figure_window

    @property
    def canvas(self):
        return getattr(self.figure_window, "current_canva", None)

    def run(
        self,
        request: Callable[[], Any],
        *,
        errors: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> CreationRunResult:
        """Run a typed Canvas request. Failures stay on this one result path."""

        try:
            return CreationRunResult(True, request())
        except errors as exc:
            if on_error is None:
                status_messages.show_error(str(exc))
            else:
                on_error(exc)
            return CreationRunResult(False)


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
