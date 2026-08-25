"""Axes semantic-child and palette command services."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from matplotlib.axes import Axes

from mygui.figuremodify.components import (
    AxesController,
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentValidationError,
    LegendController,
)
from mygui.figuremodify.components.property_values import (
    legend_anchor_value,
    legend_location_value,
)
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
    PaletteSource,
    normalize_color,
)
from mygui.figuremodify.style_base.creation_defaults import resolve_style_palette
from ._helpers import (
    _controller,
    _rejected,
    _warning,
)

@dataclass(frozen=True, slots=True)
class AxesPaletteStatus:
    """Describe the effective palette source displayed for one Axes."""

    mode: str
    palette: PaletteDefinition
    figure_style: str

    @property
    def uses_style_default(self) -> bool:
        """Return whether the current palette follows the Figure style."""

        return self.mode == "style"


class AxesCommandService:
    """Atomic commands spanning an Axes and its semantic child components."""

    def __init__(self, registry: ComponentRegistry):
        self.registry = registry

    def _axes(self, axes_id: str) -> AxesController:
        return _controller(self.registry, axes_id, AxesController)

    def semantic(
        self,
        axes_id: str,
        *,
        kind=None,
        role=None,
        selector=None,
        recursive: bool = True,
    ):
        """Return the Controller for an axes semantic component."""

        return self.registry.find_one(
            parent_id=axes_id,
            kind=kind,
            role=role,
            selector=selector,
            recursive=recursive,
        )

    def set_label_style(
        self,
        axes_id: str,
        *,
        fontfamily: str | None = None,
        fontsize: float | None = None,
    ) -> ComponentBatchChange:
        """Set label style."""

        patch = {}
        if fontfamily is not None:
            patch["fontfamily"] = fontfamily
        if fontsize is not None:
            patch["fontsize"] = float(fontsize)
        controllers = (
            self.semantic(axes_id, role=ComponentRole.X_LABEL),
            self.semantic(axes_id, role=ComponentRole.Y_LABEL),
        )
        return self.registry.apply_transaction(
            ComponentMutation(item.component_id, properties=patch)
            for item in controllers
        )

    def set_label_positions(
        self,
        axes_id: str,
        x_position,
        y_position,
    ) -> ComponentBatchChange:
        """Set label positions."""

        x_label = self.semantic(axes_id, role=ComponentRole.X_LABEL)
        y_label = self.semantic(axes_id, role=ComponentRole.Y_LABEL)
        return self.registry.apply_transaction(
            (
                ComponentMutation(
                    x_label.component_id,
                    properties={"position": tuple(x_position)},
                ),
                ComponentMutation(
                    y_label.component_id,
                    properties={"position": tuple(y_position)},
                ),
            )
        )

    def set_spine_visible(
        self,
        axes_id: str,
        side: str,
        visible: bool,
    ) -> ComponentBatchChange:
        """Set spine visible."""

        spine = self.semantic(
            axes_id,
            kind=ComponentKind.SPINE,
            selector={"name": side},
        )
        return self.registry.apply_transaction(
            (
                ComponentMutation(
                    spine.component_id,
                    properties={"visible": bool(visible)},
                ),
            )
        )

    def ensure_legend(self, axes_id: str):
        """Return the current legend, creating it only when necessary."""

        controller = self.semantic(
            axes_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
        )
        target = self.registry.resolve_target(controller.component_id)
        if target is not None:
            return controller, target
        axes = self.registry.resolve_target(axes_id)
        if not isinstance(axes, Axes):
            raise ValueError("Axes target is unavailable.")
        handles, labels = axes.get_legend_handles_labels()
        peer = getattr(axes, "_mygui_merged_legend_peer", None)
        if isinstance(peer, Axes) and peer in axes.figure.axes:
            peer_handles, peer_labels = peer.get_legend_handles_labels()
            handles = [*handles, *peer_handles]
            labels = [*labels, *peer_labels]
        legend = axes.legend(handles, labels)
        self.registry.locator.bind(controller.component_id, legend)
        return controller, legend

    def set_legend_position(
        self,
        axes_id: str,
        position,
    ) -> ComponentChange:
        """Set legend position."""

        controller, legend = self.ensure_legend(axes_id)
        del legend
        return controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "location": position,
                    "visible": True,
                },
            )
        )

    def apply_legend_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply Legend properties, rebuilding constructor-only layout safely."""

        controller = _controller(self.registry, component, LegendController)
        try:
            controller, old = self.ensure_legend(controller.state.parent_id)
            patch = dict(properties)

            def verify_render() -> None:
                old.figure.canvas.draw()

            rebuild = bool(set(patch) & controller.REBUILD_KEYS)
            if not rebuild:
                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_render,
                )
                if not batch.changes:
                    return _rejected(
                        controller,
                        batch.message or "Legend render failed.",
                    )
                change = batch.changes[0]
                if not batch.committed:
                    return replace(
                        change,
                        message=(
                            "Legend render failed; keeping the last valid legend."
                        ),
                    )
                return change
            state = controller.read_state(strict=True)
            merged = deepcopy(state.properties)
            merged.update(patch)
            candidate = state.clone(properties=merged)
            controller._validate_replacement(candidate)
            axes = old.axes
            handles, labels = axes.get_legend_handles_labels()
            peer = getattr(axes, "_mygui_merged_legend_peer", None)
            if isinstance(peer, Axes) and peer in axes.figure.axes:
                peer_handles, peer_labels = peer.get_legend_handles_labels()
                handles = [*handles, *peer_handles]
                labels = [*labels, *peer_labels]
            kwargs = {
                "loc": legend_location_value(merged["location"]),
                "bbox_to_anchor": legend_anchor_value(
                    merged["bbox_to_anchor"]
                ),
                "ncols": merged["ncols"],
                "mode": merged["mode"],
                "alignment": merged["alignment"],
                "reverse": merged["reverse"],
                "markerfirst": merged["markerfirst"],
                "numpoints": merged["numpoints"],
                "scatterpoints": merged["scatterpoints"],
                "scatteryoffsets": merged["scatteryoffsets"],
                "markerscale": merged["markerscale"],
                "borderpad": merged["borderpad"],
                "labelspacing": merged["labelspacing"],
                "handlelength": merged["handlelength"],
                "handleheight": merged["handleheight"],
                "handletextpad": merged["handletextpad"],
                "borderaxespad": merged["borderaxespad"],
                "columnspacing": merged["columnspacing"],
                "fancybox": merged["fancybox"],
                "shadow": merged["shadow"],
                "frameon": merged["frameon"],
            }
            new = axes.legend(handles, labels, **kwargs)
            old_visible = old.get_visible()
            runtime_snapshot = (
                deepcopy(controller._constructor_properties),
                controller._entry_scope,
            )
            try:
                old.set_visible(False)
                self.registry.locator.bind(controller.component_id, new)
                specs = controller.property_specs()
                for key, value in merged.items():
                    if key in patch or key in controller.REBUILD_KEYS:
                        continue
                    controller._write_property(new, specs[key], deepcopy(value))
                batch = self.registry.apply_transaction(
                    (
                        ComponentMutation(
                            controller.component_id,
                            properties=patch,
                        ),
                    ),
                    verifier=verify_render,
                )
                if not batch.committed:
                    raise ComponentValidationError(
                        batch.message or "Legend render failed."
                    )
                change = batch.changes[0]
            except Exception:
                (
                    controller._constructor_properties,
                    controller._entry_scope,
                ) = runtime_snapshot
                try:
                    new.remove()
                finally:
                    if old.axes is None:
                        axes.add_artist(old)
                    axes.legend_ = old
                    old.set_visible(old_visible)
                    self.registry.locator.bind(controller.component_id, old)
                raise
            if old is not new:
                try:
                    old.remove()
                except ValueError:
                    pass
            axes.legend_ = new
            return change
        except Exception as exc:
            return _rejected(controller, str(exc))

    def cycle_state(self, axes_id: str) -> ColorCycleState:
        """Return the axes color-cycle state, creating it when absent."""

        value = self._axes(axes_id).state.properties.get("color_cycle")
        return ColorCycleState.from_dict(value)

    def _figure_style(self, axes_id: str) -> str:
        axes_state = self._axes(axes_id).state
        figure_id = axes_state.parent_id
        if figure_id is None:
            raise ValueError("Axes is not attached to a Figure component.")
        figure_state = self.registry.get(figure_id).state
        if figure_state.kind is not ComponentKind.FIGURE:
            raise ValueError("Axes parent is not a Figure component.")
        return str(
            figure_state.properties.get("style", "default")
        )

    def style_palette(self, axes_id: str) -> PaletteDefinition:
        """Resolve the current Figure style palette for an Axes."""

        return resolve_style_palette(self._figure_style(axes_id))

    def palette_status(self, axes_id: str) -> AxesPaletteStatus:
        """Return the effective Style-default or user-selected palette."""

        figure_style = self._figure_style(axes_id)
        style_palette = self.style_palette(axes_id)
        active = self.cycle_state(axes_id).active_palette
        if (
            active is not None
            and active.source is not PaletteSource.MATPLOTLIB_STYLE
        ):
            return AxesPaletteStatus(
                "user",
                active,
                figure_style,
            )
        return AxesPaletteStatus(
            "style",
            style_palette,
            figure_style,
        )

    def peek_color(self, axes_id: str) -> ColorSelection:
        """Preview the next chart color without advancing the cycle."""

        cycle = self.cycle_state(axes_id)
        palette = cycle.active_palette
        if palette is None:
            return cycle.peek()
        return self.preview_color_cycle(
            axes_id,
            palette,
            cycle.next_index,
        ).peek()

    def preview_color_cycle(
        self,
        axes_id: str,
        fallback_palette: PaletteDefinition,
        fallback_index: int,
    ) -> ColorCycleState:
        """Return the user cycle or a non-mutating style-cycle preview."""

        cycle = self.cycle_state(axes_id)
        active = cycle.active_palette
        if active is not None and (
            active.source is not PaletteSource.MATPLOTLIB_STYLE
            or active.id == fallback_palette.id
        ):
            preview = ColorCycleState.from_dict(cycle.to_dict())
        else:
            preview = ColorCycleState(
                fallback_palette,
                max(0, int(fallback_index)) % len(fallback_palette.colors),
            )
        palette = preview.active_palette
        if palette is None:
            return preview
        occupied: set[int] = set()
        for controller in self.registry.query(
            parent_id=axes_id,
            recursive=True,
            capabilities={"color", "data"},
        ):
            try:
                color = normalize_color(
                    controller.state.properties["color"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            occupied.update(
                index
                for index, palette_color in enumerate(palette.colors)
                if palette_color == color
            )
        start = preview.next_index
        for offset in range(len(palette.colors)):
            candidate = (start + offset) % len(palette.colors)
            if candidate not in occupied:
                preview.activate(palette, candidate)
                break
        return preview

    def commit_color_selection(
        self,
        axes_id: str,
        selection: ColorSelection,
        *,
        preview_cycle: ColorCycleState | None = None,
    ) -> ComponentChange:
        """Commit a previewed color after component creation succeeds."""

        # Preview and commit are deliberately separate: cancelled or failed
        # chart creation must not consume a color from the axes sequence.
        cycle = (
            ColorCycleState.from_dict(preview_cycle.to_dict())
            if preview_cycle is not None
            else self.cycle_state(axes_id)
        )
        cycle.commit(selection)
        return self._axes(axes_id).set_property(
            "color_cycle",
            cycle.to_dict(),
        )

    def apply_palette(
        self,
        axes_id: str,
        palette: PaletteDefinition,
    ) -> ComponentBatchChange:
        """Apply palette."""

        controllers = self.registry.query(
            capabilities={"color", "data"},
            parent_id=axes_id,
            recursive=True,
        )
        cycle = ColorCycleState()
        cycle.commit_palette_for_count(palette, len(controllers))
        mutations = [
            ComponentMutation(
                controller.component_id,
                properties={
                    "color": palette.colors[
                        index % len(palette.colors)
                    ]
                },
            )
            for index, controller in enumerate(controllers)
        ]
        mutations.append(
            ComponentMutation(
                axes_id,
                properties={"color_cycle": cycle.to_dict()},
            )
        )
        result = self.registry.apply_transaction(mutations)
        if controllers or not result.ok:
            return result
        return replace(
            result,
            notices=(
                _warning(
                    "Palette selected for future charts; the current "
                    "axes has no chart components to recolor."
                ),
            ),
            message="Palette selected for future charts.",
        )
