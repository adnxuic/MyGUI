"""Parse XYZ columns, rebuild FIELD_2D runtimes, and notify Colorbars."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from mygui.database import ColumnRef, ColumnType
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    ContourController,
    Field2DController,
    Field2DData,
    HeatmapController,
    ObserverFailure,
    PseudocolorController,
)
from mygui.figuremodify.components.property_values import (
    DEFAULT_COLOR_MAP,
    DEFAULT_CONTOUR_LABELS,
    DEFAULT_CONTOUR_LEVELS,
    DEFAULT_GRID_EDGE,
    normalize_color_map_spec,
)
from mygui.figuremodify.field_2d_runtime import (
    Field2DRuntime,
    create_field_2d_runtime,
)
from mygui.figuremodify.field_grid import (
    Field2DGrid,
    Field2DGridError,
    build_field_grid,
)
from mygui.figuremodify.matplotlib_adapter import (
    IMAGE_INTERPOLATION_CHOICES,
    has_colormap,
    matplotlib_style_context,
)
from mygui.figuremodify.style_base.creation_defaults import _linestyle_preset
from ._helpers import (
    _column_ref,
    _controller,
    _notices,
    _rejected,
    _warning,
)
from .colorbar import ColorbarService

import matplotlib as mpl


_ROLE_CONTROLLERS = {
    ComponentRole.PSEUDOCOLOR: PseudocolorController,
    ComponentRole.HEATMAP: HeatmapController,
    ComponentRole.CONTOUR: ContourController,
}


def field_2d_style_seed(style: str | None) -> dict[str, Any]:
    """Freeze Figure-style cmap/interpolation/negative linestyle into state."""

    with matplotlib_style_context(style):
        cmap = str(mpl.rcParams.get("image.cmap", "viridis"))
        interpolation = str(mpl.rcParams.get("image.interpolation", "antialiased"))
        negative = _linestyle_preset(
            mpl.rcParams.get("contour.negative_linestyle", "dashed")
        )
    if interpolation not in IMAGE_INTERPOLATION_CHOICES:
        interpolation = "antialiased"
    if not has_colormap(cmap):
        cmap = "viridis"
    colormap = deepcopy(DEFAULT_COLOR_MAP)
    colormap["cmap"] = cmap
    return {
        "colormap": normalize_color_map_spec(colormap),
        "interpolation": interpolation,
        "negative_linestyle": {"kind": "preset", "value": negative},
    }


def default_field_2d_properties(
    role: ComponentRole,
    style: str | None,
) -> dict[str, Any]:
    """Return role defaults with style-derived values frozen in."""

    controller_type = _ROLE_CONTROLLERS[role]
    properties = controller_type.default_properties()
    seed = field_2d_style_seed(style)
    properties["colormap"] = deepcopy(seed["colormap"])
    if role is ComponentRole.HEATMAP:
        properties["interpolation"] = seed["interpolation"]
    if role is ComponentRole.CONTOUR:
        properties["negative_linestyle"] = deepcopy(seed["negative_linestyle"])
        properties.setdefault("levels", deepcopy(DEFAULT_CONTOUR_LEVELS))
        properties.setdefault("labels", deepcopy(DEFAULT_CONTOUR_LABELS))
    if role is ComponentRole.PSEUDOCOLOR:
        properties.setdefault("edgecolor", deepcopy(DEFAULT_GRID_EDGE))
    return properties


class Field2DService:
    """Resolve table XYZ data and rebuild FIELD_2D runtimes transactionally."""

    def __init__(
        self,
        repository,
        registry: ComponentRegistry,
        *,
        colorbar_service: ColorbarService | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.colorbar_service = colorbar_service
        self._observer_failures: list[ObserverFailure] = []

    def drain_observer_failures(self) -> tuple[ObserverFailure, ...]:
        failures, self._observer_failures = tuple(self._observer_failures), []
        return failures

    @staticmethod
    def refs_for(controller) -> tuple[ColumnRef, ColumnRef, ColumnRef]:
        data = controller.state.data
        return (
            _column_ref(data["x_ref"]),
            _column_ref(data["y_ref"]),
            _column_ref(data["z_ref"]),
        )

    def _validate_xyz(
        self,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        z_ref: ColumnRef,
    ) -> None:
        refs = (x_ref, y_ref, z_ref)
        if len({ref.project_id for ref in refs}) != 1:
            raise ComponentValidationError(
                "FIELD_2D X, Y, and Z must belong to one project."
            )
        if len({ref.sheet_id for ref in refs}) != 1:
            raise ComponentValidationError(
                "FIELD_2D X, Y, and Z must belong to the same worksheet."
            )
        for name, ref in (("X", x_ref), ("Y", y_ref), ("Z", z_ref)):
            if not self.repository.has_ref(ref):
                raise ComponentValidationError(
                    f"FIELD_2D {name} data source was removed."
                )
            column = self.repository.sheet(ref.project_id, ref.sheet_id).column(
                ref.column_id
            )
            if column.type is not ColumnType.NUMBER:
                raise ComponentValidationError(
                    f"FIELD_2D {name} data must be a numeric column."
                )

    def resolve_grid(
        self,
        x_ref: ColumnRef,
        y_ref: ColumnRef,
        z_ref: ColumnRef,
        role: ComponentRole,
    ) -> Field2DGrid:
        self._validate_xyz(x_ref, y_ref, z_ref)
        x_values = list(self.repository.series(x_ref))
        y_values = list(self.repository.series(y_ref))
        z_values = list(self.repository.series(z_ref))
        require_equispaced = role is ComponentRole.HEATMAP
        minimum_shape = (2, 2) if role is ComponentRole.CONTOUR else (1, 1)
        try:
            return build_field_grid(
                x_values,
                y_values,
                z_values,
                require_equispaced=require_equispaced,
                minimum_shape=minimum_shape,
            )
        except Field2DGridError as exc:
            raise ComponentValidationError(str(exc)) from exc

    def create_runtime(
        self,
        axes: Axes,
        role: ComponentRole,
        grid: Field2DGrid,
        properties: dict[str, Any],
        *,
        style: str | None = None,
        gid: str | None = None,
    ) -> Field2DRuntime:
        controller_type = _ROLE_CONTROLLERS[role]
        specs = controller_type.property_specs()
        normalized = controller_type.default_properties()
        unknown = set(properties) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown FIELD_2D properties: {sorted(unknown)!r}."
            )
        normalized.update(
            {key: specs[key].normalize(value) for key, value in properties.items()}
        )
        candidate = ComponentState(
            "field-2d-preflight",
            ComponentKind.FIELD_2D,
            role,
            "axes-preflight",
            0,
            {"object_id": "field-2d-preflight"},
            normalized,
            {
                "x_ref": {"project_id": "p", "sheet_id": "s", "column_id": "x"},
                "y_ref": {"project_id": "p", "sheet_id": "s", "column_id": "y"},
                "z_ref": {"project_id": "p", "sheet_id": "s", "column_id": "z"},
            },
        )
        controller_type(candidate)
        try:
            runtime = create_field_2d_runtime(
                axes,
                role,
                grid,
                normalized,
                style=style,
                gid=gid,
            )
        except Exception:
            raise
        if not isinstance(runtime, Field2DRuntime):
            raise ComponentValidationError("FIELD_2D runtime was not created.")
        return runtime

    def destroy_runtime(self, runtime: Field2DRuntime | None) -> None:
        if runtime is None:
            return
        runtime.remove()

    def _refresh_colorbar(
        self,
        controller: Field2DController,
        change: ComponentChange,
    ) -> ComponentChange:
        if (
            not change.ok
            or self.colorbar_service is None
            or not self.colorbar_service.has_dependents(controller.component_id)
        ):
            return change
        try:
            self.colorbar_service.refresh_source(controller.component_id)
        except Exception as exc:
            return _notices(
                change,
                _warning(
                    f"FIELD_2D updated, but its Colorbar refresh failed: {exc}"
                ),
            )
        return change

    def _verify_render(self, runtime: Field2DRuntime) -> None:
        figure = runtime.axes.figure
        if isinstance(figure, Figure) and figure.canvas is not None:
            figure.canvas.draw()

    def replace_runtime(
        self,
        controller: Field2DController,
        runtime: Field2DRuntime,
        mutation: ComponentMutation,
    ) -> ComponentChange:
        old = controller.resolve_target()
        before = controller.state
        old_handle = controller.prepare_remove()
        controller.commit_remove(old_handle)
        try:
            self.registry.locator.bind(controller.component_id, runtime)

            def verify() -> None:
                self._verify_render(runtime)

            batch = self.registry.apply_transaction(
                (mutation,),
                verifier=verify,
            )
            if not batch.committed or not batch.changes:
                raise ComponentValidationError(
                    batch.message or "FIELD_2D render failed."
                )
            change = batch.changes[0]
        except Exception:
            self.destroy_runtime(runtime)
            self.registry.locator.bind(controller.component_id, old)
            controller._state = before.clone()
            controller.rollback_remove(old_handle)
            raise
        controller._finalize_remove(old_handle)
        return change

    def set_refs(
        self,
        component,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        z_ref: ColumnRef | dict[str, Any],
    ) -> ComponentChange:
        controller = _controller(self.registry, component, Field2DController)
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            z_ref = _column_ref(z_ref)
            grid = self.resolve_grid(x_ref, y_ref, z_ref, controller.state.role)
            data = {
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
                "z_ref": z_ref.to_dict(),
            }
            runtime = self.create_runtime(
                controller.resolve_target().axes,
                controller.state.role,
                grid,
                controller.state.properties,
                gid=controller.component_id,
            )
            change = self.replace_runtime(
                controller,
                runtime,
                ComponentMutation(
                    controller.component_id,
                    data=data,
                    runtime_data=Field2DData(grid.x, grid.y, grid.z, grid.empty),
                ),
            )
        except Exception as exc:
            return _rejected(controller, str(exc))
        notices = []
        if grid.skipped_xy_count:
            notices.append(
                _warning(
                    "Skipped "
                    f"{grid.skipped_xy_count} row(s) with missing or non-finite "
                    "X or Y coordinates."
                )
            )
        if grid.empty or change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning(
                    "FIELD_2D has no drawable data yet; the component was kept."
                )
            )
        if notices:
            change = _notices(change, *notices)
        return self._refresh_colorbar(controller, change)

    def refresh(self, component) -> ComponentChange:
        controller = _controller(self.registry, component, Field2DController)
        try:
            x_ref, y_ref, z_ref = self.refs_for(controller)
        except Exception as exc:
            return _rejected(controller, str(exc))
        return self.set_refs(controller, x_ref, y_ref, z_ref)

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        controller = _controller(self.registry, component, Field2DController)
        patch = dict(properties)
        try:
            rebuild = set(patch).intersection(controller.REBUILD_KEYS)
            old = controller.resolve_target()

            def verify_render() -> None:
                self._verify_render(old)

            if not rebuild:
                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_render,
                )
                if not batch.changes:
                    return _rejected(
                        controller,
                        batch.message or "FIELD_2D render failed.",
                    )
                return self._refresh_colorbar(controller, batch.changes[0])

            before = controller.state
            merged = deepcopy(before.properties)
            specs = controller.property_specs()
            for key, value in patch.items():
                if key not in specs:
                    raise ComponentValidationError(
                        f"Unknown FIELD_2D property {key!r}."
                    )
                merged[key] = specs[key].normalize(value)
            x_ref, y_ref, z_ref = self.refs_for(controller)
            grid = self.resolve_grid(x_ref, y_ref, z_ref, before.role)
            runtime = self.create_runtime(
                old.axes,
                before.role,
                grid,
                merged,
                gid=controller.component_id,
            )
            change = self.replace_runtime(
                controller,
                runtime,
                ComponentMutation(controller.component_id, properties=patch),
            )
            if grid.skipped_xy_count:
                change = _notices(
                    change,
                    _warning(
                        "Skipped "
                        f"{grid.skipped_xy_count} row(s) with missing or "
                        "non-finite X or Y coordinates."
                    ),
                )
            return self._refresh_colorbar(controller, change)
        except Exception as exc:
            return _rejected(controller, str(exc))

    def refresh_affected(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> list[ComponentChange]:
        changed = set(changed_columns)
        results: list[ComponentChange] = []
        with self.registry.batch_updates():
            for controller in self.registry.query(
                capabilities={"field_2d", "auto_refresh"}
            ):
                if not isinstance(controller, Field2DController):
                    continue
                try:
                    refs = set(self.refs_for(controller))
                except Exception as exc:
                    self._observer_failures.append(
                        ObserverFailure(
                            "Field2DService",
                            "data-reference",
                            exc,
                            component_id=controller.component_id,
                            reference=deepcopy(controller.state.data),
                        )
                    )
                    continue
                if not refs.intersection(changed):
                    continue
                results.append(self.refresh(controller))
        return results
