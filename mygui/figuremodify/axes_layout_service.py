"""Transactional creation and synchronization for Figure Axes layouts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from matplotlib.axes import Axes
from matplotlib.colors import to_hex
from matplotlib.figure import Figure

from mygui.figuremodify.matplotlib_adapter import matplotlib_style_context

from mygui.figuremodify.axes_layout import (
    AxesLayer,
    AxesLayoutSpec,
    AxesViewSpec,
    share_group_for_cell,
    stable_share_group,
    subplot_record,
)
from mygui.figuremodify.components import (
    AxesController,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    UpdateImpact,
)
from mygui.figuremodify.components.base import _refresh_legend
from mygui.figuremodify.components.property_values import (
    default_minor_locator_for_scale,
)
from mygui.figuremodify.style_base.axes_appearance import (
    apply_resolved_axes_appearance,
)
from mygui.figuremodify.style_base.creation_preferences import (
    ResolvedAxesAppearance,
    resolve_axes_appearance,
)


_UNSET = object()


@dataclass(slots=True)
class _AxesDescriptor:
    target: Axes
    layout_id: str
    row: int
    column: int
    layer: AxesLayer
    share_x_group: str | None
    share_y_group: str | None
    view: AxesViewSpec
    merge_legend: bool = False
    component_id: str | None = None
    component_index: int | None = None


class AxesLayoutService:
    """Own multi-Axes geometry, relationships, and linked view mutations."""

    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.registry = canvas.component_registry
        self._grids: dict[str, Any] = {}

    def dispose(self) -> None:
        """Release runtime-only GridSpec references."""

        self._clear_runtime_relationships()
        self._grids.clear()

    def _clear_runtime_relationships(self) -> None:
        for axes in tuple(self.canvas.fig.axes):
            for name in (
                "_mygui_twin_peer",
                "_mygui_twin_primary",
                "_mygui_merged_legend_peer",
                "_mygui_merged_legend_owner",
            ):
                if hasattr(axes, name):
                    delattr(axes, name)

    @staticmethod
    def _set_runtime_pair(primary: Axes, secondary: Axes, *, merged: bool) -> None:
        primary._mygui_twin_peer = secondary
        secondary._mygui_twin_primary = primary
        if merged:
            primary._mygui_merged_legend_peer = secondary
            secondary._mygui_merged_legend_owner = primary

    def restore_runtime_relationships(self, *, refresh: bool = False) -> None:
        """Rebuild non-persisted artist links from authoritative persisted state."""

        self._clear_runtime_relationships()
        by_cell: dict[tuple[str, int, int], dict[str, AxesController]] = {}
        for controller in self.registry.query(kind=ComponentKind.AXES):
            subplot = controller.state.data.get("subplot", {})
            if "layout_id" not in subplot:
                continue
            key = (
                str(subplot["layout_id"]),
                int(subplot["row"]),
                int(subplot["column"]),
            )
            by_cell.setdefault(key, {})[str(subplot["layer"])] = controller
        for layers in by_cell.values():
            primary = layers.get(AxesLayer.PRIMARY.value)
            secondary = layers.get(AxesLayer.RIGHT_Y.value)
            if primary is None or secondary is None:
                continue
            legend = self.registry.find_one(
                parent_id=primary.component_id,
                kind=ComponentKind.LEGEND,
                role=ComponentRole.LEGEND,
                recursive=False,
            )
            merged = legend.state.properties.get("entry_scope") == "twin_pair"
            primary_target = primary.resolve_target()
            secondary_target = secondary.resolve_target()
            self._set_runtime_pair(primary_target, secondary_target, merged=merged)
            if refresh and merged and primary_target.get_legend() is not None:
                _refresh_legend(primary_target)

    def restore_persisted_geometry(self) -> None:
        """Synchronize GridSpecs from authoritative Figure/Axes state.

        Project restore, layout editing, and Figure-history replay all use the
        same persisted layout definitions.  This method changes only derived
        Matplotlib geometry and rolls that runtime projection back on failure.
        """

        definitions = {
            str(item["id"]): item for item in self.layout_definitions()
        }
        grids = {
            layout_id: self._grid_from_definition(self.canvas.fig, definition)
            for layout_id, definition in definitions.items()
        }
        snapshots = []
        try:
            for controller in self.registry.query(kind=ComponentKind.AXES):
                subplot = controller.state.data.get("subplot", {})
                layout_id = str(subplot.get("layout_id", ""))
                if layout_id not in grids:
                    raise ValueError(
                        f"Axes {controller.component_id!r} references an "
                        "unavailable Figure layout."
                    )
                target = controller.resolve_target()
                snapshots.append(
                    (
                        target,
                        target.get_subplotspec(),
                        tuple(target.get_position().bounds),
                    )
                )
                target.set_subplotspec(
                    grids[layout_id][
                        int(subplot["row"]),
                        int(subplot["column"]),
                    ]
                )
        except Exception:
            self._restore_subplot_specs(snapshots)
            raise
        self._grids = grids
        self.registry.request_update(self.canvas.fig, UpdateImpact.REDRAW)

    def set_legend_scope(self, axes_id: str, scope: str):
        """Set independent/merged legend entries for one primary twin pair."""

        scope = str(scope)
        if scope not in {"axes", "twin_pair"}:
            raise ValueError("Legend entry scope must be axes or twin_pair.")
        axes = self.registry.get(axes_id)
        subplot = axes.state.data.get("subplot", {})
        if subplot.get("layer") != AxesLayer.PRIMARY.value:
            raise ValueError("Only a primary Axes can own a merged twin legend.")
        peer = next(
            (
                candidate
                for candidate in self.axes_for_layout(str(subplot["layout_id"]))
                if candidate.state.data["subplot"].get("row") == subplot.get("row")
                and candidate.state.data["subplot"].get("column") == subplot.get("column")
                and candidate.state.data["subplot"].get("layer") == AxesLayer.RIGHT_Y.value
            ),
            None,
        )
        if scope == "twin_pair" and peer is None:
            raise ValueError("This primary Axes has no right Y Axes to merge.")
        legend = self.registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
            recursive=False,
        )
        before = legend.state
        properties = dict(before.properties)
        properties["entry_scope"] = scope
        primary_target = axes.resolve_target()
        secondary_target = peer.resolve_target() if peer is not None else None
        try:
            with self.registry.registration_transaction() as transaction:
                transaction.watch_existing(legend.component_id)
                self._clear_pair_merge(primary_target, secondary_target)
                if scope == "twin_pair" and secondary_target is not None:
                    self._set_runtime_pair(
                        primary_target,
                        secondary_target,
                        merged=True,
                    )
                result = legend.apply_state(before.clone(properties=properties))
                if not result.ok:
                    raise ValueError(result.message)
                if primary_target.get_legend() is not None:
                    _refresh_legend(primary_target)
        except Exception:
            self.restore_runtime_relationships()
            raise
        return result

    @staticmethod
    def _clear_pair_merge(primary: Axes, secondary: Axes | None) -> None:
        if hasattr(primary, "_mygui_merged_legend_peer"):
            delattr(primary, "_mygui_merged_legend_peer")
        if secondary is not None and hasattr(secondary, "_mygui_merged_legend_owner"):
            delattr(secondary, "_mygui_merged_legend_owner")

    def _root(self):
        return self.registry.get(self.canvas.root_component_id)

    def creation_view_defaults(
        self,
        appearance: ResolvedAxesAppearance | None = None,
    ) -> AxesViewSpec:
        """Resolve exposed Axes creation defaults from style, then appearance."""

        with matplotlib_style_context(self.canvas.component_style):
            figure = Figure()
            axes = figure.add_subplot(1, 1, 1)
            x_major = any(line.get_visible() for line in axes.get_xgridlines())
            y_major = any(line.get_visible() for line in axes.get_ygridlines())
            axes.minorticks_on()
            x_minor = any(
                tick.gridline.get_visible()
                for tick in axes.xaxis.get_minor_ticks()
            )
            y_minor = any(
                tick.gridline.get_visible()
                for tick in axes.yaxis.get_minor_ticks()
            )
            facecolor = to_hex(axes.get_facecolor(), keep_alpha=True)
            xscale = axes.get_xscale()
            yscale = axes.get_yscale()
            aspect = axes.get_aspect()
        if appearance is not None:
            facecolor = appearance.facecolor
            x_major = bool(appearance.x.major.grid.visible)
            x_minor = bool(appearance.x.minor.grid.visible)
            y_major = bool(appearance.y.major.grid.visible)
            y_minor = bool(appearance.y.minor.grid.visible)
        return AxesViewSpec(
            xscale=xscale,
            yscale=yscale,
            aspect=aspect,
            facecolor=facecolor,
            x_major_grid=x_major,
            x_minor_grid=x_minor,
            y_major_grid=y_major,
            y_minor_grid=y_minor,
        )

    def constrained_layout_enabled(self) -> bool:
        """Return constrained/compressed layout from Figure Controller state."""

        layout = self._root().read_state().properties.get(
            "layout_engine",
            {"kind": "none", "params": {}},
        )
        return isinstance(layout, dict) and layout.get("kind") in {
            "constrained",
            "compressed",
        }

    def layout_definitions(self) -> tuple[dict[str, Any], ...]:
        data = self._root().state.data
        return tuple(deepcopy(data.get("layouts", ())))

    def layout_definition(self, layout_id: str) -> dict[str, Any]:
        for definition in self.layout_definitions():
            if definition.get("id") == layout_id:
                return definition
        raise ValueError(f"Unknown Figure layout: {layout_id}")

    def _set_layout_definitions(
        self,
        definitions: Iterable[dict[str, Any]],
        *,
        constrained_layout: bool | None = None,
    ) -> None:
        root = self._root()
        state = root.state
        properties = dict(state.properties)
        if constrained_layout is not None:
            properties["layout_engine"] = (
                {
                    "kind": "constrained",
                    "params": {
                        "w_pad": None,
                        "h_pad": None,
                        "wspace": None,
                        "hspace": None,
                        "rect": None,
                    },
                }
                if constrained_layout
                else {"kind": "none", "params": {}}
            )
        change = root.apply_state(
            state.clone(
                properties=properties,
                data={"layouts": [deepcopy(item) for item in definitions]},
            )
        )
        if not change.ok:
            raise ValueError(change.message)

    @staticmethod
    def _groups_for_spec(
        spec: AxesLayoutSpec,
        layout_id: str,
    ) -> dict[tuple[int, int], tuple[str | None, str | None]]:
        raw: dict[tuple[int, int], tuple[str | None, str | None]] = {}
        x_counts: dict[str, int] = {}
        y_counts: dict[str, int] = {}
        for cell in spec.cells:
            x_group = share_group_for_cell(
                layout_id,
                "x",
                spec.share_x,
                cell.row,
                cell.column,
            )
            y_group = share_group_for_cell(
                layout_id,
                "y",
                spec.share_y,
                cell.row,
                cell.column,
            )
            if cell.right_y is not None and x_group is None:
                x_group = stable_share_group(
                    layout_id,
                    "x",
                    f"cell-{cell.row}-{cell.column}",
                )
            raw[(cell.row, cell.column)] = (x_group, y_group)
            if x_group is not None:
                x_counts[x_group] = x_counts.get(x_group, 0) + 1
                if cell.right_y is not None:
                    x_counts[x_group] += 1
            if y_group is not None:
                y_counts[y_group] = y_counts.get(y_group, 0) + 1
        return {
            key: (
                x_group if x_group is not None and x_counts[x_group] >= 2 else None,
                y_group if y_group is not None and y_counts[y_group] >= 2 else None,
            )
            for key, (x_group, y_group) in raw.items()
        }

    @staticmethod
    def _validate_shared_views(
        spec: AxesLayoutSpec,
        groups: dict[tuple[int, int], tuple[str | None, str | None]],
    ) -> None:
        x_values: dict[str, tuple[Any, ...]] = {}
        y_values: dict[str, tuple[Any, ...]] = {}
        for cell in spec.cells:
            x_group, y_group = groups[(cell.row, cell.column)]
            if x_group is not None:
                value = (
                    cell.primary.xlim,
                    cell.primary.xscale,
                    cell.primary.invert_x,
                    cell.primary.autoscalex_on,
                )
                previous = x_values.setdefault(x_group, value)
                if previous != value:
                    raise ValueError(
                        "Axes in one shared X group must use the same X view settings."
                    )
            if y_group is not None:
                value = (
                    cell.primary.ylim,
                    cell.primary.yscale,
                    cell.primary.invert_y,
                    cell.primary.autoscaley_on,
                )
                previous = y_values.setdefault(y_group, value)
                if previous != value:
                    raise ValueError(
                        "Axes in one shared Y group must use the same Y view settings."
                    )

    @staticmethod
    def _apply_view(target: Axes, view: AxesViewSpec, *, right_y: bool = False) -> None:
        if not right_y:
            target.set_xscale(view.xscale)
        target.set_yscale(view.yscale)
        if not right_y and view.xlim is not None:
            target.set_xlim(*view.xlim)
        if view.ylim is not None:
            target.set_ylim(*view.ylim)
        if not right_y:
            target.set_autoscalex_on(view.autoscalex_on)
        target.set_autoscaley_on(view.autoscaley_on)
        if not right_y and bool(target.xaxis_inverted()) != bool(view.invert_x):
            target.invert_xaxis()
        if bool(target.yaxis_inverted()) != bool(view.invert_y):
            target.invert_yaxis()
        target.set_aspect("auto" if right_y else view.aspect)
        if right_y:
            target.set_facecolor("none")
        elif view.facecolor is not None:
            target.set_facecolor(view.facecolor)
        if not right_y and view.x_minor_grid:
            target.xaxis.minorticks_on()
        if view.y_minor_grid:
            target.yaxis.minorticks_on()
        if not right_y:
            if view.x_major_grid is not None:
                target.grid(view.x_major_grid, axis="x", which="major")
            if view.x_minor_grid is not None:
                target.grid(view.x_minor_grid, axis="x", which="minor")
        if view.y_major_grid is not None:
            target.grid(view.y_major_grid, axis="y", which="major")
        if view.y_minor_grid is not None:
            target.grid(view.y_minor_grid, axis="y", which="minor")

    def _apply_outer_labels(
        self,
        descriptors: Iterable[_AxesDescriptor],
        spec: AxesLayoutSpec,
    ) -> None:
        mutations: list[ComponentMutation] = []
        for item in descriptors:
            if item.layer is AxesLayer.RIGHT_Y or item.component_id is None:
                continue
            if spec.outer_x_labels and item.row < spec.nrows - 1:
                label = self.registry.find_one(
                    parent_id=item.component_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.X_LABEL,
                    recursive=True,
                )
                mutations.append(
                    ComponentMutation(label.component_id, properties={"visible": False})
                )
                for role in (
                    ComponentRole.MAJOR_TICK_LABEL,
                    ComponentRole.MINOR_TICK_LABEL,
                ):
                    tick_labels = self.registry.find_one(
                        parent_id=item.component_id,
                        kind=ComponentKind.TICK_LABEL_GROUP,
                        role=role,
                        selector={"axis": "x"},
                        recursive=True,
                    )
                    mutations.append(
                        ComponentMutation(
                            tick_labels.component_id,
                            properties={
                                "primary_visible": False,
                                "secondary_visible": False,
                            },
                        )
                    )
            if spec.outer_y_labels and item.column > 0:
                label = self.registry.find_one(
                    parent_id=item.component_id,
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.Y_LABEL,
                    recursive=True,
                )
                mutations.append(
                    ComponentMutation(label.component_id, properties={"visible": False})
                )
                for role in (
                    ComponentRole.MAJOR_TICK_LABEL,
                    ComponentRole.MINOR_TICK_LABEL,
                ):
                    tick_labels = self.registry.find_one(
                        parent_id=item.component_id,
                        kind=ComponentKind.TICK_LABEL_GROUP,
                        role=role,
                        selector={"axis": "y"},
                        recursive=True,
                    )
                    mutations.append(
                        ComponentMutation(
                            tick_labels.component_id,
                            properties={
                                "primary_visible": False,
                                "secondary_visible": False,
                            },
                        )
                    )
        if mutations:
            result = self.registry.apply_transaction(mutations)
            if not result.ok:
                raise ValueError(result.message or "Could not apply outer labels.")

    @staticmethod
    def _grid_from_definition(figure, definition: dict[str, Any]):
        margins = definition["margins"]
        spacing = definition["spacing"]
        return figure.add_gridspec(
            int(definition["nrows"]),
            int(definition["ncols"]),
            width_ratios=definition["width_ratios"],
            height_ratios=definition["height_ratios"],
            left=float(margins["left"]),
            right=float(margins["right"]),
            bottom=float(margins["bottom"]),
            top=float(margins["top"]),
            wspace=float(spacing["wspace"]),
            hspace=float(spacing["hspace"]),
        )

    def _register_descriptors(
        self,
        descriptors: list[_AxesDescriptor],
        transaction,
        *,
        start_index: int,
    ) -> tuple[str, ...]:
        component_ids: list[str] = []
        for offset, item in enumerate(descriptors):
            axes_index = (
                start_index + offset
                if item.component_index is None
                else int(item.component_index)
            )
            axes_id, _controllers = self.canvas._register_axes_components(
                item.target,
                axes_index,
                subplot=subplot_record(
                    item.layout_id,
                    item.row,
                    item.column,
                    layer=item.layer,
                    share_x_group=item.share_x_group,
                    share_y_group=item.share_y_group,
                ),
            )
            item.component_id = axes_id
            axes_controller = self.registry.get(axes_id)
            self.canvas.figure_inspector.add_axes_inspector(
                axes_controller,
                self.canvas.editor_context,
            )
            transaction.on_rollback(
                lambda target_id=axes_id:
                self.canvas.figure_inspector.remove_axes_inspector(target_id)
            )
            component_ids.append(axes_id)

            if item.merge_legend and item.layer is AxesLayer.PRIMARY:
                legend = self.registry.find_one(
                    parent_id=axes_id,
                    kind=ComponentKind.LEGEND,
                    role=ComponentRole.LEGEND,
                    recursive=False,
                )
                state = legend.state
                properties = dict(state.properties)
                properties["entry_scope"] = "twin_pair"
                change = legend.apply_state(state.clone(properties=properties))
                if not change.ok:
                    raise ValueError(change.message)
        return tuple(component_ids)

    def _resolve_appearance_once(self) -> ResolvedAxesAppearance:
        """Read Components defaults once for programmatic create without a snapshot."""

        style = self.canvas.component_creation_defaults().axes
        settings = None
        reader = getattr(self.canvas, "_read_component_defaults", None)
        if callable(reader):
            settings = reader()
        return resolve_axes_appearance(style, settings)

    @staticmethod
    def _apply_right_y_structure(primary: Axes, secondary: Axes) -> None:
        secondary.set_facecolor("none")
        secondary.patch.set_visible(False)
        secondary.xaxis.set_visible(False)
        primary.spines["right"].set_visible(False)
        secondary.spines["left"].set_visible(False)
        secondary.yaxis.tick_right()
        secondary.yaxis.set_label_position("right")
        primary.yaxis.tick_left()

    def create(
        self,
        spec: AxesLayoutSpec,
        *,
        select: bool = True,
        appearance: ResolvedAxesAppearance | None = None,
    ) -> tuple[str, ...]:
        """Create one complete layout as one registration transaction."""

        frozen = (
            appearance if appearance is not None else self._resolve_appearance_once()
        )
        layout_id = spec.resolved_layout_id()
        if any(item["id"] == layout_id for item in self.layout_definitions()):
            raise ValueError(f"Figure layout already exists: {layout_id}")
        groups = self._groups_for_spec(spec, layout_id)
        self._validate_shared_views(spec, groups)
        definition = spec.layout_definition(layout_id)
        grid = self._grid_from_definition(self.canvas.fig, definition)
        # Figure.axes also contains auxiliary Matplotlib Axes such as a
        # Colorbar's cax.  Persisted semantic Axes indexes belong exclusively
        # to registered AXES components, so auxiliary targets must not advance
        # the selector sequence.
        start_index = len(self.registry.query(kind=ComponentKind.AXES))
        allocated_ids_before = set(self.canvas._allocated_component_ids)
        descriptors: list[_AxesDescriptor] = []
        x_anchors: dict[str, Axes] = {}
        y_anchors: dict[str, Axes] = {}
        first_controller = None

        with self.registry.registration_transaction() as transaction:
            transaction.watch_existing(self.canvas.root_component_id)
            transaction.on_rollback(
                lambda: setattr(
                    self.canvas,
                    "_allocated_component_ids",
                    allocated_ids_before,
                )
            )
            definitions = list(self.layout_definitions())
            definitions.append(definition)
            self._set_layout_definitions(
                definitions,
                constrained_layout=spec.constrained_layout,
            )
            with matplotlib_style_context(self.canvas.component_style):
                for cell in sorted(spec.cells, key=lambda item: (item.row, item.column)):
                    x_group, y_group = groups[(cell.row, cell.column)]
                    primary = self.canvas.fig.add_subplot(
                        grid[cell.row, cell.column],
                        sharex=x_anchors.get(x_group) if x_group else None,
                        sharey=y_anchors.get(y_group) if y_group else None,
                    )
                    transaction.on_rollback(
                        lambda target=primary:
                        self.canvas._remove_created_artist(target)
                    )
                    apply_resolved_axes_appearance(primary, frozen, right_y=False)
                    self._apply_view(primary, cell.primary)
                    descriptors.append(
                        _AxesDescriptor(
                            primary,
                            layout_id,
                            cell.row,
                            cell.column,
                            AxesLayer.PRIMARY,
                            x_group,
                            y_group,
                            cell.primary,
                            cell.merge_legend,
                        )
                    )
                    if x_group:
                        x_anchors.setdefault(x_group, primary)
                    if y_group:
                        y_anchors.setdefault(y_group, primary)

                    if cell.right_y is not None:
                        secondary = primary.twinx()
                        transaction.on_rollback(
                            lambda target=secondary:
                            self.canvas._remove_created_artist(target)
                        )
                        apply_resolved_axes_appearance(
                            secondary, frozen, right_y=True
                        )
                        self._apply_view(secondary, cell.right_y, right_y=True)
                        self._apply_right_y_structure(primary, secondary)
                        descriptors.append(
                            _AxesDescriptor(
                                secondary,
                                layout_id,
                                cell.row,
                                cell.column,
                                AxesLayer.RIGHT_Y,
                                x_group,
                                None,
                                cell.right_y,
                            )
                        )

            component_ids = self._register_descriptors(
                descriptors,
                transaction,
                start_index=start_index,
            )
            self._apply_outer_labels(descriptors, spec)
            self.registry.validate_axes_targets()
            self.canvas.validate_component_snapshot()
            if component_ids:
                first_controller = self.registry.get(component_ids[0])

        self._grids[layout_id] = grid
        self.restore_runtime_relationships()
        self.canvas.message_presenter.discard_pending()
        if select and first_controller is not None:
            self.canvas.update_current_axes(first_controller.component_id)
        self.canvas.redraw()
        return component_ids

    def materialize(self, axes_states: Iterable[ComponentState]) -> tuple[str, ...]:
        """Create persisted Axes in selector order before applying state."""

        ordered = sorted(
            tuple(axes_states),
            key=lambda state: int(state.selector["index"]),
        )
        if not ordered:
            return ()
        definitions = {item["id"]: item for item in self.layout_definitions()}
        grids = {
            layout_id: self._grid_from_definition(self.canvas.fig, definition)
            for layout_id, definition in definitions.items()
        }
        x_anchors: dict[str, Axes] = {}
        y_anchors: dict[str, Axes] = {}
        primaries: dict[tuple[str, int, int], Axes] = {}
        descriptors: list[_AxesDescriptor] = []
        allocated_ids_before = set(self.canvas._allocated_component_ids)

        with self.registry.registration_transaction() as transaction:
            transaction.on_rollback(
                lambda: setattr(
                    self.canvas,
                    "_allocated_component_ids",
                    allocated_ids_before,
                )
            )
            with matplotlib_style_context(self.canvas.component_style):
                for state in ordered:
                    subplot = state.data["subplot"]
                    layout_id = subplot["layout_id"]
                    key = (layout_id, subplot["row"], subplot["column"])
                    layer = AxesLayer(subplot["layer"])
                    if layer is AxesLayer.PRIMARY:
                        target = self.canvas.fig.add_subplot(
                            grids[layout_id][subplot["row"], subplot["column"]],
                            sharex=x_anchors.get(subplot["share_x_group"]),
                            sharey=y_anchors.get(subplot["share_y_group"]),
                        )
                        primaries[key] = target
                    else:
                        primary = primaries.get(key)
                        if primary is None:
                            raise ValueError(
                                "A persisted right Y Axes has no materialized primary Axes."
                            )
                        target = primary.twinx()
                    transaction.on_rollback(
                        lambda axes=target: self.canvas._remove_created_artist(axes)
                    )
                    if subplot["share_x_group"]:
                        x_anchors.setdefault(subplot["share_x_group"], target)
                    if subplot["share_y_group"]:
                        y_anchors.setdefault(subplot["share_y_group"], target)
                    descriptors.append(
                        _AxesDescriptor(
                            target,
                            layout_id,
                            subplot["row"],
                            subplot["column"],
                            layer,
                            subplot["share_x_group"],
                            subplot["share_y_group"],
                            AxesViewSpec(),
                            component_index=int(state.selector["index"]),
                        )
                    )
            component_ids = self._register_descriptors(
                descriptors,
                transaction,
                start_index=0,
            )
            self.registry.validate_axes_targets()
        self._grids.update(grids)
        return component_ids

    def axes_for_layout(self, layout_id: str) -> tuple[AxesController, ...]:
        return tuple(
            sorted(
                (
                    controller
                    for controller in self.registry.query(kind=ComponentKind.AXES)
                    if controller.state.data["subplot"].get("layout_id") == layout_id
                ),
                key=lambda controller: int(controller.state.selector["index"]),
            )
        )

    def apply_minor_component_properties(
        self,
        controller,
        properties: dict[str, Any],
    ):
        """Apply one minor semantic edit with any required Axis locator."""

        if self.registry.get(controller.component_id) is not controller:
            raise ValueError("Minor component is not owned by this Figure.")
        if controller.state.kind not in {
            ComponentKind.TICK_GROUP,
            ComponentKind.TICK_LABEL_GROUP,
            ComponentKind.GRID,
        }:
            raise ValueError("Minor edits require a Tick, Tick Label, or Grid.")
        patch = dict(properties)
        mutations: list[ComponentMutation] = []
        state = controller.state
        enabling = False
        if state.selector.get("level") == "minor":
            if state.kind is ComponentKind.GRID:
                enabling = patch.get("visible") is True
            else:
                enabling = any(
                    patch.get(key) is True
                    for key in ("primary_visible", "secondary_visible")
                )
        if enabling:
            axis = self.registry.ancestor(
                controller.component_id,
                kind=ComponentKind.AXIS,
                include_self=False,
            )
            if axis is None:
                raise ValueError("Minor component has no owning Axis.")
            locator = axis.state.properties["minor_locator"]
            if locator.get("kind") == "null":
                mutations.append(
                    ComponentMutation(
                        axis.component_id,
                        properties={
                            "minor_locator": default_minor_locator_for_scale(
                                axis.state.properties["scale"]
                            )
                        },
                    )
                )
        mutations.append(
            ComponentMutation(controller.component_id, properties=patch)
        )
        return self.registry.apply_transaction(mutations)

    @staticmethod
    def repair_legacy_minor_locator_states(
        states: Iterable[ComponentState],
    ) -> tuple[ComponentState, ...]:
        """Repair explicit pre-fix minor intent without enabling default ticks."""

        values = tuple(states)
        children: dict[str | None, list[ComponentState]] = {}
        for state in values:
            children.setdefault(state.parent_id, []).append(state)
        replacements: dict[str, ComponentState] = {}
        for axis in values:
            if axis.kind is not ComponentKind.AXIS:
                continue
            locator = axis.properties.get("minor_locator", {})
            if locator.get("kind") != "null":
                continue
            explicit_intent = False
            for child in children.get(axis.id, ()):  # Tick/Grid children.
                if child.selector.get("level") != "minor":
                    continue
                if (
                    child.kind is ComponentKind.GRID
                    and child.properties.get("visible") is True
                ) or (
                    child.kind is ComponentKind.TICK_GROUP
                    and child.properties.get("secondary_visible") is True
                ):
                    explicit_intent = True
                if child.kind is ComponentKind.TICK_GROUP:
                    explicit_intent = explicit_intent or any(
                        label.kind is ComponentKind.TICK_LABEL_GROUP
                        and label.properties.get("secondary_visible") is True
                        for label in children.get(child.id, ())
                    )
                if explicit_intent:
                    break
            if not explicit_intent:
                continue
            properties = deepcopy(axis.properties)
            properties["minor_locator"] = default_minor_locator_for_scale(
                properties["scale"]
            )
            replacements[axis.id] = axis.clone(properties=properties)
        return tuple(replacements.get(state.id, state) for state in values)

    def linked_axes(self, axes_id: str, dimension: str) -> tuple[AxesController, ...]:
        axes = self.registry.get(axes_id)
        if not isinstance(axes, AxesController):
            raise ValueError("Linked view changes require an Axes component.")
        key = "share_x_group" if dimension == "x" else "share_y_group"
        group = axes.state.data["subplot"].get(key)
        if group is None:
            return (axes,)
        return tuple(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXES)
            if controller.state.data["subplot"].get(key) == group
        )

    def apply_linked_axis(
        self,
        axes_id: str,
        dimension: str,
        *,
        limits: Any = _UNSET,
        scale: Any = _UNSET,
        autoscale: Any = _UNSET,
        inverted: Any = _UNSET,
    ):
        """Apply one X/Y view action to every member and semantic Axis state."""

        if dimension not in {"x", "y"}:
            raise ValueError("Linked Axes dimension must be x or y.")
        axes_key = "xlim" if dimension == "x" else "ylim"
        autoscale_key = (
            "autoscalex_on" if dimension == "x" else "autoscaley_on"
        )
        axis_role = (
            ComponentRole.X_AXIS if dimension == "x" else ComponentRole.Y_AXIS
        )
        mutations: list[ComponentMutation] = []
        for controller in self.linked_axes(axes_id, dimension):
            patch: dict[str, Any] = {}
            if limits is not _UNSET:
                patch[axes_key] = tuple(limits)
            if autoscale is not _UNSET:
                patch[autoscale_key] = bool(autoscale)
            if inverted is not _UNSET and limits is _UNSET:
                current = tuple(controller.state.properties[axes_key])
                is_inverted = current[0] > current[1]
                if bool(inverted) != is_inverted:
                    patch[axes_key] = tuple(reversed(current))
            if patch:
                mutations.append(
                    ComponentMutation(controller.component_id, properties=patch)
                )
            if scale is not _UNSET:
                axis = self.registry.find_one(
                    parent_id=controller.component_id,
                    kind=ComponentKind.AXIS,
                    role=axis_role,
                    recursive=False,
                )
                mutations.append(
                    ComponentMutation(
                        axis.component_id,
                        properties={"scale": scale},
                    )
                )
        return self.registry.apply_transaction(mutations)

    def update_geometry(self, spec: AxesLayoutSpec) -> tuple[str, ...]:
        """Safely replace one layout's GridSpec without replacing its Axes."""

        if spec.layout_id is None:
            raise ValueError("Editing a layout requires its stable layout id.")
        layout_id = str(spec.layout_id)
        controllers = self.axes_for_layout(layout_id)
        if not controllers:
            raise ValueError("The selected Figure layout has no Axes.")
        for controller in controllers:
            subplot = controller.state.data["subplot"]
            if subplot["row"] >= spec.nrows or subplot["column"] >= spec.ncols:
                raise ValueError(
                    "Delete Axes outside the requested trailing rows or columns first."
                )

        definition = spec.layout_definition(layout_id)
        new_grid = self._grid_from_definition(self.canvas.fig, definition)
        snapshots = []
        with self.registry.registration_transaction() as transaction:
            transaction.watch_existing(self.canvas.root_component_id)
            for controller in controllers:
                target = controller.resolve_target()
                snapshots.append(
                    (
                        target,
                        target.get_subplotspec(),
                        tuple(target.get_position().bounds),
                    )
                )
            transaction.on_rollback(
                lambda: self._restore_subplot_specs(snapshots)
            )
            definitions = [
                definition if item["id"] == layout_id else item
                for item in self.layout_definitions()
            ]
            self._set_layout_definitions(
                definitions,
                constrained_layout=spec.constrained_layout,
            )
            for controller in controllers:
                subplot = controller.state.data["subplot"]
                target = controller.resolve_target()
                target.set_subplotspec(
                    new_grid[subplot["row"], subplot["column"]]
                )
            self.canvas.validate_component_snapshot()
        self._grids[layout_id] = new_grid
        self.canvas.message_presenter.discard_pending()
        self.canvas.redraw()
        return tuple(controller.component_id for controller in controllers)

    @staticmethod
    def _restore_subplot_specs(snapshots) -> None:
        for target, subplot_spec, bounds in snapshots:
            target.set_subplotspec(subplot_spec)
            target.set_position(bounds)
