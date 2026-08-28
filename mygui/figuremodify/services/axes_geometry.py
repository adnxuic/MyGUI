"""Transactional per-Axes geometry projection for schema v19."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from matplotlib.axes import Axes

from mygui.figuremodify.axes_geometry import (
    AxesGeometryMode,
    AxesGeometrySpec,
    grid_geometry_record,
    normalize_geometry_bounds,
)
from mygui.figuremodify.components import (
    ComponentBatchChange,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    UpdateImpact,
)
from mygui.figuremodify.components.controllers.containers import AxesController
from mygui.figuremodify.services._helpers import _controller, _rejected


def _set_target_subplotspec(target: Axes, spec: Any) -> None:
    """Set or clear a SubplotSpec inside the sole geometry boundary."""

    if spec is None:
        target._subplotspec = None
    else:
        target.set_subplotspec(spec)


@dataclass(frozen=True, slots=True)
class AxesRuntimeGeometrySnapshot:
    """Exact reversible Matplotlib geometry for one Axes target."""

    target: Axes
    subplotspec: Any
    in_layout: bool
    active_position: Any
    original_position: Any
    anchor: Any
    axes_locator: Any
    box_aspect: Any


class _GeometryRuntimeHandle:
    """Runtime memento shared by geometry, GridSpec, and Colorbar work."""

    def __init__(
        self,
        service: "AxesGeometryService",
        targets: Iterable[Axes],
    ) -> None:
        self._service = service
        self._snapshots = service.capture_runtime(targets)
        self._followers = deepcopy(service._colorbar_followers)
        self._colorbar_rebuilds: list[Any] = []
        self._closed = False

    def add_colorbar_rebuild(self, handle: Any) -> None:
        if handle is not None:
            self._colorbar_rebuilds.append(handle)

    def rollback(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        for handle in reversed(self._colorbar_rebuilds):
            try:
                handle.rollback()
            except BaseException as exc:
                errors.append(exc)
        try:
            self._service.restore_runtime(self._snapshots)
        except BaseException as exc:
            errors.append(exc)
        self._service._colorbar_followers = deepcopy(self._followers)
        self._closed = True
        if errors:
            raise RuntimeError(
                "Axes geometry runtime rollback was incomplete."
            ) from errors[0]

    def commit(self) -> None:
        if self._closed:
            return
        for handle in self._colorbar_rebuilds:
            handle.commit()
        self._closed = True


class AxesGeometryService:
    """Sole authority for grid/manual Axes and Colorbar geometry."""

    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.registry = canvas.component_registry
        self._colorbar_followers: dict[str, dict[str, Any]] = {}

    def dispose(self) -> None:
        """Clear runtime-only follower tracking."""

        self._colorbar_followers.clear()

    def twin_group(self, axes_id: str) -> tuple[AxesController, ...]:
        """Return the persisted twin group for one Axes."""

        controller = _controller(self.registry, axes_id, AxesController)
        subplot = controller.state.data.get("subplot", {})
        layout_id = subplot.get("layout_id")
        row = subplot.get("row")
        col = subplot.get("column")
        if layout_id is None or row is None or col is None:
            return (controller,)
        controllers = [
            candidate
            for candidate in self.registry.query(kind=ComponentKind.AXES)
            if candidate.state.data.get("subplot", {}).get("layout_id")
            == layout_id
            and candidate.state.data.get("subplot", {}).get("row") == row
            and candidate.state.data.get("subplot", {}).get("column") == col
        ]
        return tuple(
            sorted(
                controllers,
                key=lambda item: int(item.state.selector["index"]),
            )
        )

    def geometry_spec(self, axes_id: str) -> AxesGeometrySpec:
        """Return the validated geometry spec for an Axes."""

        controller = _controller(self.registry, axes_id, AxesController)
        record = controller.state.data.get("geometry", grid_geometry_record())
        return AxesGeometrySpec.from_dict(record)

    @staticmethod
    def capture_runtime(
        targets: Iterable[Axes],
    ) -> tuple[AxesRuntimeGeometrySnapshot, ...]:
        """Capture exact runtime geometry for distinct Axes targets."""

        snapshots: list[AxesRuntimeGeometrySnapshot] = []
        seen: set[int] = set()
        for target in targets:
            if id(target) in seen:
                continue
            seen.add(id(target))
            snapshots.append(
                AxesRuntimeGeometrySnapshot(
                    target=target,
                    subplotspec=target.get_subplotspec(),
                    in_layout=bool(target.get_in_layout()),
                    active_position=target.get_position().frozen(),
                    original_position=target.get_position(original=True).frozen(),
                    anchor=target.get_anchor(),
                    axes_locator=target.get_axes_locator(),
                    box_aspect=target.get_box_aspect(),
                )
            )
        return tuple(snapshots)

    @staticmethod
    def restore_runtime(
        snapshots: Iterable[AxesRuntimeGeometrySnapshot],
    ) -> None:
        """Restore exact runtime geometry without changing persisted state."""

        for snapshot in snapshots:
            target = snapshot.target
            _set_target_subplotspec(target, snapshot.subplotspec)
            target.set_axes_locator(snapshot.axes_locator)
            target.set_box_aspect(snapshot.box_aspect)
            target._set_position(
                snapshot.original_position,
                which="original",
            )
            target._set_position(
                snapshot.active_position,
                which="active",
            )
            target.set_anchor(snapshot.anchor)
            target.set_in_layout(snapshot.in_layout)

    def capture_owner_group(
        self,
        owner_axes_id: str,
    ) -> tuple[AxesRuntimeGeometrySnapshot, ...]:
        """Capture one owner and all persisted twin targets."""

        return self.capture_runtime(
            controller.resolve_target()
            for controller in self.twin_group(owner_axes_id)
        )

    @staticmethod
    def colorbar_owner_restore_state(
        snapshot: AxesRuntimeGeometrySnapshot,
    ) -> tuple[Any, ...]:
        """Return the deletion adapter's immutable owner restore tuple."""

        return (
            snapshot.target,
            snapshot.active_position,
            snapshot.original_position,
            snapshot.subplotspec,
            snapshot.anchor,
        )

    def project_owner_from_state(self, owner_axes_id: str) -> None:
        """Reapply authoritative geometry before Colorbar construction."""

        for controller in self.twin_group(owner_axes_id):
            self._project_controller(controller)

    def configure_colorbar_runtime(
        self,
        owner_axes_id: str,
        colorbar: Any,
        *,
        component_id: str | None = None,
    ) -> None:
        """Configure a newly created Colorbar as a manual follower if needed."""

        owner = _controller(self.registry, owner_axes_id, AxesController)
        geometry = AxesGeometrySpec.from_dict(
            owner.state.data.get("geometry", grid_geometry_record())
        )
        if geometry.mode is not AxesGeometryMode.MANUAL:
            return
        if geometry.bounds is None:
            raise ValueError("Manual Axes geometry has no bounds.")
        for controller in self.twin_group(owner_axes_id):
            self._project_manual_target(
                controller.resolve_target(),
                geometry.bounds,
            )
        cax = colorbar.ax
        cax_bounds = tuple(cax.get_position().bounds)
        _set_target_subplotspec(cax, None)
        cax.set_axes_locator(None)
        cax.set_box_aspect(None)
        cax.set_position(cax_bounds)
        cax.set_in_layout(False)
        if component_id is not None:
            self._colorbar_followers[str(component_id)] = {
                "owner_id": str(owner_axes_id),
                "source_bounds": geometry.bounds,
                "cax_bounds": cax_bounds,
            }

    def colorbar_follower_snapshot(
        self,
        component_id: str,
    ) -> dict[str, Any] | None:
        """Capture one runtime-only Colorbar follower record."""

        follower = self._colorbar_followers.get(str(component_id))
        return deepcopy(follower) if follower is not None else None

    def restore_colorbar_follower(
        self,
        component_id: str,
        follower: dict[str, Any] | None,
    ) -> None:
        """Restore or discard one runtime-only Colorbar follower record."""

        component_id = str(component_id)
        if follower is None:
            self._colorbar_followers.pop(component_id, None)
            return
        self._colorbar_followers[component_id] = deepcopy(follower)

    def switch_to_manual(
        self,
        axes_id: str,
    ) -> ComponentBatchChange | ComponentChange:
        """Capture the rendered bbox and switch one twin group to manual."""

        controller = _controller(self.registry, axes_id, AxesController)
        try:
            twin_group = self.twin_group(axes_id)
            if self.canvas.fig.canvas is not None:
                self.canvas.fig.canvas.draw()
            bboxes = [
                tuple(item.resolve_target().get_position().bounds)
                for item in twin_group
            ]
            first_bbox = bboxes[0]
            for other_bbox in bboxes[1:]:
                if not np.allclose(first_bbox, other_bbox, atol=1e-5):
                    raise ValueError(
                        "Twin Axes have inconsistent rendered bounding boxes."
                    )
            bounds = normalize_geometry_bounds(first_bbox)
            record = {
                "mode": AxesGeometryMode.MANUAL.value,
                "bounds": list(bounds),
            }

            def apply_runtime(
                group: tuple[AxesController, ...],
                _handle: _GeometryRuntimeHandle,
            ) -> None:
                for item in group:
                    self._project_manual_target(item.resolve_target(), bounds)
                for item in group:
                    self._convert_colorbars_to_followers(
                        item.component_id,
                        bounds,
                    )

            return self._apply_geometry_record(
                twin_group,
                record,
                apply_runtime,
                "Could not apply manual geometry.",
            )
        except Exception as exc:
            return _rejected(controller, str(exc))

    def set_manual_bounds(
        self,
        axes_id: str,
        bounds: Iterable[float],
    ) -> ComponentBatchChange | ComponentChange:
        """Update manual bounds for one Axes and its twin peers."""

        controller = _controller(self.registry, axes_id, AxesController)
        try:
            normalized = normalize_geometry_bounds(bounds)
            twin_group = self.twin_group(axes_id)
            geometry = self.geometry_spec(axes_id)
            if geometry.mode is not AxesGeometryMode.MANUAL:
                raise ValueError(
                    "Cannot set manual bounds on an Axes in grid mode."
                )
            old_bounds = geometry.bounds or normalized
            record = {
                "mode": AxesGeometryMode.MANUAL.value,
                "bounds": list(normalized),
            }

            def apply_runtime(
                group: tuple[AxesController, ...],
                _handle: _GeometryRuntimeHandle,
            ) -> None:
                for item in group:
                    self._project_manual_target(
                        item.resolve_target(),
                        normalized,
                    )
                for item in group:
                    self._update_colorbar_followers(
                        item.component_id,
                        old_bounds,
                        normalized,
                    )

            return self._apply_geometry_record(
                twin_group,
                record,
                apply_runtime,
                "Could not update manual bounds.",
            )
        except Exception as exc:
            return _rejected(controller, str(exc))

    def return_to_grid(
        self,
        axes_id: str,
    ) -> ComponentBatchChange | ComponentChange:
        """Return one manual twin group to the latest GridSpec projection."""

        controller = _controller(self.registry, axes_id, AxesController)
        try:
            twin_group = self.twin_group(axes_id)
            if self.geometry_spec(axes_id).mode is not AxesGeometryMode.MANUAL:
                raise ValueError("The selected Axes is already grid controlled.")

            def apply_runtime(
                group: tuple[AxesController, ...],
                handle: _GeometryRuntimeHandle,
            ) -> None:
                for item in group:
                    self._project_grid_target(item)
                self._prepare_grid_colorbar_rebuilds(group, handle)

            return self._apply_geometry_record(
                twin_group,
                grid_geometry_record(),
                apply_runtime,
                "Could not return to grid layout.",
            )
        except Exception as exc:
            return _rejected(controller, str(exc))

    def reset_to_grid_bounds(
        self,
        axes_id: str,
    ) -> ComponentBatchChange | ComponentChange:
        """Reset manual bounds to the latest raw GridSpec cell rectangle."""

        controller = _controller(self.registry, axes_id, AxesController)
        try:
            if self.geometry_spec(axes_id).mode is not AxesGeometryMode.MANUAL:
                raise ValueError("Only a manual Axes position can be reset.")
            subplot = controller.state.data["subplot"]
            normalized = normalize_geometry_bounds(
                self.canvas.axes_layout_service.subplot_bounds(
                    str(subplot["layout_id"]),
                    int(subplot["row"]),
                    int(subplot["column"]),
                )
            )
            return self.set_manual_bounds(axes_id, normalized)
        except Exception as exc:
            return _rejected(controller, str(exc))

    def prepare_layout_projection(self, layout_id: str) -> _GeometryRuntimeHandle:
        """Project one replaced GridSpec without owning its persisted definition."""

        controllers = self.canvas.axes_layout_service.axes_for_layout(layout_id)
        handle = self._runtime_handle(controllers)
        try:
            for controller in controllers:
                self._project_controller(controller)
            grid_owners = tuple(
                controller
                for controller in controllers
                if self.geometry_spec(controller.component_id).mode
                is AxesGeometryMode.GRID
            )
            self._prepare_grid_colorbar_rebuilds(grid_owners, handle)
            return handle
        except Exception:
            handle.rollback()
            raise

    def restore_persisted_geometry(self) -> None:
        """Project all persisted grid/manual geometry and Colorbar followers."""

        controllers = tuple(self.registry.query(kind=ComponentKind.AXES))
        handle = self._runtime_handle(controllers)
        try:
            for controller in controllers:
                self._project_controller(controller)
            grid_owners = tuple(
                controller
                for controller in controllers
                if self.geometry_spec(controller.component_id).mode
                is AxesGeometryMode.GRID
            )
            detached_grid_owners = tuple(
                controller
                for controller in grid_owners
                if self._owner_has_detached_colorbar(controller.component_id)
            )
            self._prepare_grid_colorbar_rebuilds(
                detached_grid_owners,
                handle,
            )
            for controller in controllers:
                geometry = self.geometry_spec(controller.component_id)
                if geometry.mode is AxesGeometryMode.MANUAL:
                    if geometry.bounds is None:
                        raise ValueError("Manual Axes geometry has no bounds.")
                    self._convert_colorbars_to_followers(
                        controller.component_id,
                        geometry.bounds,
                    )
            handle.commit()
        except Exception:
            handle.rollback()
            raise

    def _apply_geometry_record(
        self,
        twin_group: tuple[AxesController, ...],
        record: dict[str, Any],
        apply_runtime: Callable[
            [tuple[AxesController, ...], _GeometryRuntimeHandle],
            None,
        ],
        failure_message: str,
    ) -> ComponentBatchChange:
        mutations = []
        for item in twin_group:
            data = deepcopy(item.state.data)
            data["geometry"] = deepcopy(record)
            mutations.append(ComponentMutation(item.component_id, data=data))

        handle = self._runtime_handle(twin_group)
        with self.registry.registration_transaction() as transaction:
            for item in twin_group:
                transaction.watch_existing(item.component_id)
            # Restoring an Axes Controller writes its runtime ``position``;
            # Matplotlib consequently clears ``in_layout``.  Reapply this
            # authoritative geometry memento only after watched Controllers
            # have finished their own rollback.
            transaction.on_rollback_after_restore(handle.rollback)
            batch = self.registry.apply_transaction(mutations)
            if not batch.committed or not all(change.ok for change in batch.changes):
                raise ValueError(batch.message or failure_message)
            apply_runtime(twin_group, handle)
            self.registry.validate_axes_targets()
            self.canvas.validate_component_snapshot()
            self.registry.request_update(self.canvas.fig, UpdateImpact.REDRAW)
            self.canvas.redraw()
        handle.commit()
        return batch

    def _runtime_handle(
        self,
        controllers: Iterable[AxesController],
    ) -> _GeometryRuntimeHandle:
        targets: list[Axes] = []
        for controller in controllers:
            targets.append(controller.resolve_target())
            for colorbar in self.registry.query(
                kind=ComponentKind.COLORBAR,
                parent_id=controller.component_id,
            ):
                targets.append(colorbar.resolve_target().ax)
        return _GeometryRuntimeHandle(self, targets)

    def _project_controller(self, controller: AxesController) -> None:
        geometry = AxesGeometrySpec.from_dict(
            controller.state.data.get("geometry", grid_geometry_record())
        )
        if geometry.mode is AxesGeometryMode.GRID:
            self._project_grid_target(controller)
            return
        if geometry.bounds is None:
            raise ValueError("Manual Axes geometry has no bounds.")
        self._project_manual_target(controller.resolve_target(), geometry.bounds)

    def _project_grid_target(self, controller: AxesController) -> None:
        subplot = controller.state.data["subplot"]
        target = controller.resolve_target()
        _set_target_subplotspec(
            target,
            self.canvas.axes_layout_service.subplot_spec(
                str(subplot["layout_id"]),
                int(subplot["row"]),
                int(subplot["column"]),
            ),
        )
        target.set_in_layout(True)

    @staticmethod
    def _project_manual_target(
        target: Axes,
        bounds: tuple[float, float, float, float],
    ) -> None:
        _set_target_subplotspec(target, None)
        target.set_position(bounds)
        target.set_in_layout(False)

    def _prepare_grid_colorbar_rebuilds(
        self,
        controllers: Iterable[AxesController],
        handle: _GeometryRuntimeHandle,
    ) -> None:
        component_ids = tuple(
            colorbar.component_id
            for controller in controllers
            for colorbar in self.registry.query(
                kind=ComponentKind.COLORBAR,
                parent_id=controller.component_id,
            )
        )
        if not component_ids:
            return
        colorbar_service = getattr(self.canvas, "colorbar_service", None)
        if colorbar_service is None:
            raise ValueError("Colorbar runtime service is unavailable.")
        rebuild = colorbar_service.prepare_runtime_rebuilds(component_ids)
        handle.add_colorbar_rebuild(rebuild)
        for component_id in component_ids:
            self._colorbar_followers.pop(component_id, None)

    def _owner_has_detached_colorbar(self, owner_axes_id: str) -> bool:
        for colorbar in self.registry.query(
            kind=ComponentKind.COLORBAR,
            parent_id=owner_axes_id,
        ):
            cax = colorbar.resolve_target().ax
            if (
                colorbar.component_id in self._colorbar_followers
                or cax.get_subplotspec() is None
                or not cax.get_in_layout()
            ):
                return True
        return False

    def _convert_colorbars_to_followers(
        self,
        owner_axes_id: str,
        source_bounds: tuple[float, float, float, float],
    ) -> None:
        for colorbar in self.registry.query(
            kind=ComponentKind.COLORBAR,
            parent_id=owner_axes_id,
        ):
            cax = colorbar.resolve_target().ax
            cax_bounds = tuple(cax.get_position().bounds)
            _set_target_subplotspec(cax, None)
            cax.set_axes_locator(None)
            cax.set_box_aspect(None)
            cax.set_position(cax_bounds)
            cax.set_in_layout(False)
            self._colorbar_followers[colorbar.component_id] = {
                "owner_id": owner_axes_id,
                "source_bounds": source_bounds,
                "cax_bounds": cax_bounds,
            }

    def _update_colorbar_followers(
        self,
        owner_axes_id: str,
        old_source_bounds: tuple[float, float, float, float],
        new_source_bounds: tuple[float, float, float, float],
    ) -> None:
        old_x, old_y, old_width, old_height = old_source_bounds
        new_x, new_y, new_width, new_height = new_source_bounds
        scale_x = new_width / old_width
        scale_y = new_height / old_height
        for colorbar in self.registry.query(
            kind=ComponentKind.COLORBAR,
            parent_id=owner_axes_id,
        ):
            cax = colorbar.resolve_target().ax
            cax_x, cax_y, cax_width, cax_height = cax.get_position().bounds
            new_cax_bounds = (
                new_x + (cax_x - old_x) * scale_x,
                new_y + (cax_y - old_y) * scale_y,
                cax_width * scale_x,
                cax_height * scale_y,
            )
            _set_target_subplotspec(cax, None)
            cax.set_axes_locator(None)
            cax.set_box_aspect(None)
            cax.set_position(new_cax_bounds)
            cax.set_in_layout(False)
            self._colorbar_followers[colorbar.component_id] = {
                "owner_id": owner_axes_id,
                "source_bounds": new_source_bounds,
                "cax_bounds": new_cax_bounds,
            }
