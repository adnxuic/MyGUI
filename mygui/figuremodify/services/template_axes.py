"""Recompute template-restored automatic Axes before project publication."""

from __future__ import annotations

from mygui.figuremodify.components import ComponentKind
from mygui.figuremodify.x_axis_tight import apply_tight_xlim
from mygui.figuremodify.y_axis_reserve import apply_y_lower_reserve


class TemplateAxesAutoscaleService:
    """Refresh only Axes dimensions whose persisted auto flags are enabled."""

    def __init__(self, registry):
        self.registry = registry

    def recompute(self) -> tuple[str, ...]:
        """Recompute limits from newly materialized data and sync Controller state."""

        updated = []
        for controller in self.registry.query(kind=ComponentKind.AXES):
            state = controller.state
            auto_x = bool(state.properties.get("autoscalex_on", True))
            auto_y = bool(state.properties.get("autoscaley_on", True))
            if not auto_x and not auto_y:
                continue
            axes = controller.resolve_target()
            if not axes.has_data():
                continue
            axes.relim()
            for collection in axes.collections:
                try:
                    axes.update_datalim(collection.get_datalim(axes.transData))
                except (AttributeError, TypeError, ValueError):
                    continue
            axes.autoscale_view(scalex=auto_x, scaley=auto_y)
            if auto_x:
                apply_tight_xlim(axes)
            if auto_y:
                apply_y_lower_reserve(axes)
            controller.sync_from_target(strict=True)
            updated.append(controller.component_id)
        return tuple(updated)
