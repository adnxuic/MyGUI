"""Snapshot apply helpers that keep selection authority on the Canvas host."""

from __future__ import annotations

from typing import Any

import numpy as np

from mygui import status_messages
from mygui import tex_config
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentState,
)
from mygui.widgets.figure_canvas.canvas_host import CanvasSnapshotHost


def component_paths_from_tree(
    component_tree: dict[str, Any] | None,
) -> dict[str, str]:
    """Map fixed semantic paths to IDs from a validated component tree."""

    if not isinstance(component_tree, dict):
        return {}
    raw_components = component_tree.get("components")
    root_id = component_tree.get("root_component_id")
    if not isinstance(raw_components, list) or not isinstance(root_id, str):
        return {}
    components = [
        item for item in raw_components if isinstance(item, dict)
    ]
    children: dict[str | None, list[dict[str, Any]]] = {}
    for component in components:
        children.setdefault(component.get("parent_id"), []).append(component)

    paths: dict[str, str] = {"figure": root_id}
    axes_components = sorted(
        (
            item
            for item in components
            if item.get("kind") == ComponentKind.AXES.value
            and item.get("parent_id") == root_id
        ),
        key=lambda item: int(item.get("selector", {}).get("index", 0)),
    )
    for fallback_index, axes_component in enumerate(axes_components):
        selector = axes_component.get("selector", {})
        axes_index = int(selector.get("index", fallback_index))
        axes_id = axes_component.get("id")
        if not isinstance(axes_id, str):
            continue
        axes_path = f"figure/axes/{axes_index}"
        paths[axes_path] = axes_id
        direct = children.get(axes_id, [])
        axis_ids: dict[str, str] = {}
        for component in direct:
            component_id = component.get("id")
            kind = component.get("kind")
            role = component.get("role")
            component_selector = component.get("selector", {})
            if not isinstance(component_id, str):
                continue
            if kind == ComponentKind.AXIS.value:
                axis_name = component_selector.get("axis")
                if axis_name in {"x", "y"}:
                    axis_ids[axis_name] = component_id
                    paths[f"{axes_path}/axis/{axis_name}"] = component_id
            elif kind == ComponentKind.SPINE.value:
                name = component_selector.get("name")
                if name in {"left", "right", "top", "bottom"}:
                    paths[f"{axes_path}/spine/{name}"] = component_id
            elif role == ComponentRole.TITLE.value:
                paths[f"{axes_path}/title"] = component_id
            elif kind == ComponentKind.LEGEND.value:
                paths[f"{axes_path}/legend"] = component_id

        for axis_name, axis_id in axis_ids.items():
            for component in children.get(axis_id, []):
                component_id = component.get("id")
                kind = component.get("kind")
                role = component.get("role")
                selector = component.get("selector", {})
                if not isinstance(component_id, str):
                    continue
                if role == f"{axis_name}_label":
                    paths[f"{axes_path}/axis/{axis_name}/label"] = component_id
                    continue
                level = selector.get("level")
                if level not in {"major", "minor"}:
                    continue
                if kind == ComponentKind.TICK_GROUP.value:
                    tick_path = f"{axes_path}/axis/{axis_name}/tick/{level}"
                    paths[tick_path] = component_id
                    label = next(
                        (
                            item
                            for item in children.get(component_id, [])
                            if item.get("kind")
                            == ComponentKind.TICK_LABEL_GROUP.value
                        ),
                        None,
                    )
                    if label is not None and isinstance(label.get("id"), str):
                        paths[f"{tick_path}/label"] = label["id"]
                elif kind == ComponentKind.GRID.value:
                    paths[f"{axes_path}/axis/{axis_name}/grid/{level}"] = (
                        component_id
                    )
    return paths


def json_component_value(value):
    if isinstance(value, dict):
        return {
            str(key): json_component_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_component_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_component_value(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


class CanvasSnapshotApplier:
    """Apply persisted component states after Matplotlib targets exist."""

    def __init__(self, host: CanvasSnapshotHost) -> None:
        self._host = host

    def apply_component_tree(
        self, component_tree: dict[str, Any] | None
    ) -> None:
        host = self._host
        if not isinstance(component_tree, dict):
            return
        states = [
            ComponentState.from_dict(raw_state)
            for raw_state in component_tree.get("components", [])
        ]
        states = list(
            host.axes_layout_service.repair_legacy_minor_locator_states(states)
        )
        source_by_id = {state.id: state for state in states}
        runtime_ids = {
            controller.component_id
            for controller in host.component_registry.query()
        }
        missing = sorted(set(source_by_id) - runtime_ids)
        unexpected = sorted(runtime_ids - set(source_by_id))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise ValueError(
                "Project components could not be restored: "
                + "; ".join(details)
            )

        figure_states = [
            state for state in states if state.kind is ComponentKind.FIGURE
        ]
        axes_states = [state for state in states if state.kind is ComponentKind.AXES]
        legend_states = [
            state for state in states
            if state.kind is ComponentKind.LEGEND
        ]
        body_states = [
            state for state in states
            if state.kind not in {
                ComponentKind.FIGURE,
                ComponentKind.AXES,
                ComponentKind.LEGEND,
            }
        ]
        in_axes_states = [
            state
            for state in body_states
            if state.kind is ComponentKind.IN_AXES
        ]
        body_states = [
            state
            for state in body_states
            if state.kind is not ComponentKind.IN_AXES
        ]
        tex_fallback = False

        def apply_states(values: list[ComponentState]) -> None:
            nonlocal tex_fallback
            with host.component_registry.batch_updates():
                for source_state in sorted(
                    values,
                    key=lambda item: (item.order, item.id),
                ):
                    controller = host.component_registry.get(source_state.id)
                    use_effective_fallback = (
                        source_state.kind
                        in {ComponentKind.TEXT, ComponentKind.ANNOTATION}
                        and source_state.properties.get("usetex")
                        and not tex_config.is_tex_enabled()
                    )
                    change = controller.apply_state(source_state)
                    if not change.ok:
                        raise ValueError(
                            f"Could not restore component {source_state.id}: {change.message}"
                        )
                    if use_effective_fallback:
                        fallback = (
                            host.text_render_service.apply_tex_availability(
                                False,
                                force=True,
                            )
                        )
                        if not fallback.committed:
                            raise ValueError(fallback.message)
                        tex_fallback = True

        apply_states(figure_states)
        if figure_states:
            root_properties = figure_states[0].properties
            host._document_dpi = float(
                root_properties.get("dpi", host._document_dpi)
            )
            host.style = str(root_properties.get("style", host.style or "default"))

        # Apply containers/semantics first.  Chart labels and persisted raw
        # data are then allowed to refresh limits and legends once.
        apply_states(axes_states)
        apply_states(body_states)

        # Raw Line/Scatter data can autoscale the Axes.  Reapply the persisted
        # Axes range after that update has been coalesced.
        apply_states(axes_states)
        apply_states(in_axes_states)
        host.in_axes_service.refresh_all_zoom()

        for legend_state in legend_states:
            controller = host.component_registry.get(legend_state.id)
            try:
                controller.resolve_target()
            except Exception:
                if bool(legend_state.properties.get("visible", True)):
                    host.axes_commands.ensure_legend(
                        legend_state.parent_id
                    )
            result = host.axes_commands.apply_legend_properties(
                controller,
                legend_state.properties,
            )
            if not result.ok:
                raise ValueError(
                    f"Could not restore component {legend_state.id}: {result.message}"
                )
        host.axes_layout_service.restore_persisted_geometry()
        host.axes_layout_service.restore_runtime_relationships(refresh=True)
        host.component_registry.validate_tree()
        host.component_registry.validate_axes_targets()
        if tex_fallback:
            status_messages.show_warning(
                "TeX text is displayed with Matplotlib text rendering until "
                "TeX is enabled; its saved TeX preference was preserved."
            )

        host.redraw()

    def materialize_history_states(
        self,
        target_states: tuple[ComponentState, ...],
        added_ids: set[str],
    ) -> None:
        """Restore structural history through Axes/materializer architecture."""

        host = self._host
        state_by_id = {state.id: state for state in target_states}
        missing = set(added_ids) - set(state_by_id)
        if missing:
            raise ValueError(
                "Figure history is missing target states: "
                + ", ".join(sorted(missing))
            )
        axes_states = tuple(
            sorted(
                (
                    state_by_id[component_id]
                    for component_id in added_ids
                    if state_by_id[component_id].kind is ComponentKind.AXES
                ),
                key=lambda state: int(state.selector["index"]),
            )
        )
        dynamic_states = tuple(
            state_by_id[component_id]
            for component_id in added_ids
            if (state_by_id[component_id].kind, state_by_id[component_id].role)
            in host.component_materializers.keys
        )
        restorable_ids = {
            state.id for state in axes_states
        } | {state.id for state in dynamic_states}
        fixed_ids = set(added_ids) - restorable_ids
        for component_id in fixed_ids:
            state = state_by_id[component_id]
            cursor = state.parent_id
            while cursor is not None and cursor not in restorable_ids:
                parent = state_by_id.get(cursor)
                cursor = parent.parent_id if parent is not None else None
            if cursor is None:
                raise ValueError(
                    f"No materializer owns added component {component_id!r}."
                )

        previous_restoring = host._restoring_component_tree_now
        host._restoring_component_tree_now = True
        try:
            with (
                host._history_component_id_overrides(target_states),
                host.component_registry.registration_transaction(),
            ):
                if axes_states:
                    host.axes_layout_service.materialize(axes_states)
                for phase in host.component_materializers.phases:
                    for state in host.component_materializers.states_for_phase(
                        dynamic_states,
                        phase,
                    ):
                        host._restore_component_state(state)
        finally:
            host._restoring_component_tree_now = previous_restoring
        unresolved = sorted(
            component_id
            for component_id in added_ids
            if component_id not in host.component_registry
        )
        if unresolved:
            raise ValueError(
                "Figure history materialization did not restore: "
                + ", ".join(unresolved)
            )
