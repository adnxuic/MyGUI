"""Narrow Canvas helper host capabilities.

Helpers hold only a host reference. They must not cache ``ComponentState``,
selection, or color-cycle cursor state. ``PyFigureCanvas`` remains the
selection authority and the public ``add_*`` / ``restore_component_tree``
surface. These Protocols describe capability slices; they are not a second
business-state store.
"""

from __future__ import annotations

from typing import Any, Protocol

from mygui.figuremodify.components import ComponentState


class CanvasRegistrationHost(Protocol):
    """Register Controllers through the Canvas; do not cache published state."""

    component_registry: Any

    def _prepare_created_component(self, controller: Any, transaction: Any) -> None:
        ...

    def _finish_created_component(self, controller: Any) -> None:
        ...

    def _remove_created_artist(self, artist: Any) -> None:
        ...

    def _claim_color_order(self, preferred: int | None = None) -> int:
        ...

    def _next_child_order(self, parent_id: str, *, kind: Any = None) -> int:
        ...

    def _register_chart_controller(
        self,
        controller_type: Any,
        component_id: str,
        role: Any,
        artist: Any,
        order: int,
        properties: dict[str, Any],
        data: dict[str, Any],
    ) -> Any:
        ...

    def _register_text_controller(self, *args: Any, **kwargs: Any) -> Any:
        ...


class CanvasSelectionHost(Protocol):
    """Select through Canvas-owned APIs; never assign ``current_component_id``."""

    def select_component(self, component_id: str) -> None:
        ...

    def _select_created_component(self, controller: Any) -> None:
        ...

    def redraw(self) -> None:
        ...


class CanvasCreationHost(Protocol):
    """Public creation surface used by restore materializers."""

    def add_in_axes(self, spec: Any, *, object_id: str | None = None) -> Any:
        ...

    def add_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_component_line(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_plot(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_scatter(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_errorbar(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_pseudocolor(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_heatmap(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_contour(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_colorbar(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_secondary_axis(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_marks(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_line(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_reference_band(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_interpolate_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_fit_curve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_text(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_global_text(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add_annotation(self, *args: Any, **kwargs: Any) -> Any:
        ...


class CanvasSnapshotHost(Protocol):
    """Apply snapshots after Matplotlib targets already exist."""

    component_registry: Any
    axes_layout_service: Any
    text_render_service: Any
    in_axes_service: Any
    axes_commands: Any
    component_materializers: Any
    _document_dpi: float
    style: str | None
    _restoring_component_tree_now: bool

    def redraw(self) -> None:
        ...

    def _history_component_id_overrides(self, target_states: Any) -> Any:
        ...

    def _restore_component_state(self, state: ComponentState) -> Any:
        ...


class CanvasDeletionHost(Protocol):
    """Deletion coordination reads Canvas state; it does not cache selection."""

    deletion_service: Any
    message_presenter: Any
    component_registry: Any
    current_component_id: str | None
    root_component_id: str
    editor_registry: Any
    figure_inspector: Any
    component_editor_manager: Any
    color_consumption_ledger: Any
    axes_layout_service: Any
    fig: Any

    def select_component(self, component_id: str) -> None:
        ...

    def redraw(self) -> None:
        ...


class CanvasDependencyRestoreHost(Protocol):
    """Restore Axes relationships and data-dependency snapshots."""

    axes_layout_service: Any
    dependency_service: Any


class CanvasHelperHost(
    CanvasRegistrationHost,
    CanvasSelectionHost,
    CanvasCreationHost,
    CanvasSnapshotHost,
    CanvasDeletionHost,
    CanvasDependencyRestoreHost,
    Protocol,
):
    """Composed helper surface implemented by ``PyFigureCanvas``."""
