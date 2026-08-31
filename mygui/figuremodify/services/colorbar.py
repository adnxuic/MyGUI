"""Colorbar source resolution and lifecycle services."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from matplotlib.axes import Axes
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure

from mygui.figuremodify.components import (
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    ControllerRuntimeMemento,
    ColorbarController,
    Field2DController,
    ScatterController,
    UpdateImpact,
)
from mygui.figuremodify.field_2d_runtime import Field2DRuntime
from mygui.figuremodify.components.matplotlib_removal import MATPLOTLIB_REMOVAL
from ._helpers import (
    _controller,
    _rejected,
)

@dataclass(frozen=True, slots=True)
class ColorbarSourceResolution:
    """Validated source/owner targets for one Colorbar operation."""

    source_controller: Any
    mappable: Any
    owner_axes_id: str
    owner_axes: Axes


class ColorbarSourceResolverRegistry:
    """Resolve scalar-mappable sources through exact component contracts."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry
        self._resolvers: dict[tuple[ComponentKind, ComponentRole], Callable] = {}

    def register(
        self,
        kind: ComponentKind,
        role: ComponentRole,
        resolver: Callable,
    ) -> None:
        key = (ComponentKind(kind), ComponentRole(role))
        if key in self._resolvers:
            raise ComponentValidationError(
                f"Duplicate Colorbar source resolver for {kind.value}/{role.value}."
            )
        if not callable(resolver):
            raise TypeError("Colorbar source resolver must be callable.")
        self._resolvers[key] = resolver

    def resolve(self, component, *, allow_empty: bool = False) -> ColorbarSourceResolution:
        controller = _controller(self.registry, component)
        state = controller.state
        resolver = self._resolvers.get((state.kind, state.role))
        if resolver is None:
            raise ComponentValidationError(
                f"{state.kind.value}/{state.role.value} cannot be used as a "
                "Colorbar source."
            )
        if isinstance(resolver, Field2DColorbarSourceResolver):
            return resolver(controller, allow_empty=allow_empty)
        return resolver(controller)


class ScatterColorbarSourceResolver:
    """First-party resolver for scalar-mapped Scatter components."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def __call__(self, component) -> ColorbarSourceResolution:
        controller = _controller(self.registry, component, ScatterController)
        state = controller.state
        mapping = state.properties.get("color_mapping", {})
        if not bool(mapping.get("enabled")):
            raise ComponentValidationError(
                "Scatter scalar color mapping must be enabled before adding a Colorbar."
            )
        # Existing-Figure discovery may register an external scalar mappable
        # without TableRepository data. Persisted/project-managed Scatter
        # sources always require a stable color_ref.
        if state.data and state.data.get("color_ref") is None:
            raise ComponentValidationError(
                "Scatter Colorbar sources require a valid color_ref."
            )
        mappable = controller.resolve_target()
        if getattr(mappable, "get_array", lambda: None)() is None:
            raise ComponentValidationError(
                "Scatter source is not an active Matplotlib ScalarMappable."
            )
        owner_axes_id = state.parent_id
        if owner_axes_id is None:
            raise ComponentValidationError("Scatter source has no owner Axes.")
        owner_axes = self.registry.resolve_target(owner_axes_id)
        if not isinstance(owner_axes, Axes) or getattr(mappable, "axes", None) is not owner_axes:
            raise ComponentValidationError(
                "Scatter source and owner Axes targets are inconsistent."
            )
        return ColorbarSourceResolution(
            controller,
            mappable,
            owner_axes_id,
            owner_axes,
        )


class Field2DColorbarSourceResolver:
    """Resolver for Pseudocolor, Heatmap, and Contour ScalarMappable sources."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def __call__(self, component, *, allow_empty: bool = False) -> ColorbarSourceResolution:
        controller = _controller(self.registry, component, Field2DController)
        runtime = controller.resolve_target()
        if not isinstance(runtime, Field2DRuntime):
            raise ComponentValidationError(
                "FIELD_2D Colorbar source is missing its runtime."
            )
        if not allow_empty and not runtime.has_drawable:
            raise ComponentValidationError(
                "Empty FIELD_2D components cannot receive a new Colorbar."
            )
        mappable = runtime.mappable
        if mappable is None or not hasattr(mappable, "get_array"):
            raise ComponentValidationError(
                "FIELD_2D source is not an active Matplotlib ScalarMappable."
            )
        owner_axes_id = controller.state.parent_id
        if owner_axes_id is None:
            raise ComponentValidationError("FIELD_2D source has no owner Axes.")
        owner_axes = self.registry.resolve_target(owner_axes_id)
        if not isinstance(owner_axes, Axes) or runtime.axes is not owner_axes:
            raise ComponentValidationError(
                "FIELD_2D source and owner Axes targets are inconsistent."
            )
        return ColorbarSourceResolution(
            controller,
            mappable,
            owner_axes_id,
            owner_axes,
        )


def production_colorbar_source_resolvers(
    registry: ComponentRegistry,
) -> ColorbarSourceResolverRegistry:
    """Build the closed first-party Colorbar source resolver registry."""

    resolvers = ColorbarSourceResolverRegistry(registry)
    scatter = ScatterColorbarSourceResolver(registry)
    resolvers.register(
        ComponentKind.SCATTER,
        ComponentRole.SCATTER,
        scatter,
    )
    field_resolver = Field2DColorbarSourceResolver(registry)
    for role in (
        ComponentRole.PSEUDOCOLOR,
        ComponentRole.HEATMAP,
        ComponentRole.CONTOUR,
    ):
        resolvers.register(ComponentKind.FIELD_2D, role, field_resolver)
    return resolvers


@dataclass(slots=True)
class _ColorbarRuntimeRebuildItem:
    controller: ColorbarController
    old_target: Colorbar
    removal_handle: Any
    new_target: Colorbar
    controller_runtime: ControllerRuntimeMemento
    follower_runtime: dict[str, Any] | None


class ColorbarRuntimeRebuildBatch:
    """Deferred-finalization Colorbar rebuilds with exact rollback."""

    def __init__(self, service: "ColorbarService") -> None:
        self._service = service
        self._items: list[_ColorbarRuntimeRebuildItem] = []
        self._closed = False

    def append(self, item: _ColorbarRuntimeRebuildItem) -> None:
        self._items.append(item)

    def rollback(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        for item in reversed(self._items):
            try:
                self._service.destroy_runtime(item.new_target)
                self._service.registry.locator.bind(
                    item.controller.component_id,
                    item.old_target,
                )
                item.controller.rollback_remove(item.removal_handle)
                item.controller.restore_runtime_memento(
                    item.controller_runtime
                )
                geometry = self._service.geometry_service
                if geometry is not None:
                    geometry.restore_colorbar_follower(
                        item.controller.component_id,
                        item.follower_runtime,
                    )
            except BaseException as exc:
                errors.append(exc)
        self._closed = True
        if errors:
            raise RuntimeError(
                "Colorbar runtime rebuild rollback was incomplete."
            ) from errors[0]

    def commit(self) -> None:
        if self._closed:
            return
        for item in self._items:
            item.controller.finalize_removal(item.removal_handle)
        self._closed = True


class ColorbarService:
    """Create, rebuild, refresh, and inspect Colorbars transactionally."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        source_resolvers: ColorbarSourceResolverRegistry | None = None,
        geometry_service: Any | None = None,
    ) -> None:
        self.registry = registry
        self.source_resolvers = (
            source_resolvers or production_colorbar_source_resolvers(registry)
        )
        self.geometry_service = geometry_service

    def dependents(self, source_component_id: str) -> tuple[ColorbarController, ...]:
        return tuple(
            controller
            for controller in self.registry.query(kind=ComponentKind.COLORBAR)
            if controller.state.data.get("source_component_id")
            == str(source_component_id)
        )

    def has_dependents(self, source_component_id: str) -> bool:
        return bool(self.dependents(source_component_id))

    def validate_source(
        self,
        owner_axes_id: str,
        source_component_id: str,
    ) -> ColorbarSourceResolution:
        """Resolve one eligible source before beginning a creation transaction."""

        source = self.source_resolvers.resolve(source_component_id)
        if source.owner_axes_id != str(owner_axes_id):
            raise ComponentValidationError(
                "Colorbar source must belong to the selected owner Axes."
            )
        if self.has_dependents(source_component_id):
            raise ComponentValidationError(
                "The selected source already has a Colorbar."
            )
        return source

    def eligible_sources(self, owner_axes_id: str) -> tuple[ColorbarSourceResolution, ...]:
        existing = {
            controller.state.data["source_component_id"]
            for controller in self.registry.query(kind=ComponentKind.COLORBAR)
        }
        resolved = []
        for controller in self.registry.query(parent_id=owner_axes_id):
            if controller.component_id in existing:
                continue
            try:
                source = self.source_resolvers.resolve(controller)
            except (ComponentValidationError, TypeError):
                continue
            if source.owner_axes_id == owner_axes_id:
                resolved.append(source)
        return tuple(
            sorted(
                resolved,
                key=lambda item: (
                    item.source_controller.state.order,
                    item.source_controller.component_id,
                ),
            )
        )

    @staticmethod
    def source_preview(source: ColorbarSourceResolution) -> str:
        state = source.source_controller.state
        label = str(state.properties.get("label", "")).strip()
        if label:
            return label
        role = state.role.value.replace("_", " ").title()
        cmap = ""
        if state.kind is ComponentKind.FIELD_2D:
            cmap = str(state.properties.get("colormap", {}).get("cmap", "")).strip()
        suffix = f" ({cmap})" if cmap else ""
        return f"{role} {state.id[:8]}{suffix}"

    @staticmethod
    def _constructor_kwargs(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": properties["location"],
            "fraction": properties["fraction"],
            "shrink": properties["shrink"],
            "aspect": properties["aspect"],
            "pad": properties["pad"],
            "extend": properties["extend"],
            "spacing": properties["spacing"],
            "drawedges": properties["drawedges"],
            "ticklocation": properties["ticklocation"],
        }

    def _create_runtime(
        self,
        source: ColorbarSourceResolution,
        properties: dict[str, Any],
        *,
        component_id: str | None = None,
    ) -> Colorbar:
        owner = source.owner_axes
        figure = owner.figure
        if not isinstance(figure, Figure):
            raise ComponentValidationError("Colorbar owner Axes has no Figure.")
        geometry = self.geometry_service
        if geometry is None:
            raise ComponentValidationError(
                "Colorbar runtime creation requires AxesGeometryService."
            )
        before_axes = tuple(figure.axes)
        owner_snapshots = geometry.capture_owner_group(source.owner_axes_id)
        owner_snapshot = next(
            item for item in owner_snapshots if item.target is owner
        )
        try:
            colorbar = figure.colorbar(
                source.mappable,
                ax=owner,
                use_gridspec=True,
                **self._constructor_kwargs(properties),
            )
            if not isinstance(colorbar, Colorbar) or colorbar.mappable is not source.mappable:
                raise ComponentValidationError(
                    "Matplotlib did not create the requested Colorbar."
                )
            colorbar._mygui_owner_restore_state = (
                geometry.colorbar_owner_restore_state(owner_snapshot),
            )
            geometry.configure_colorbar_runtime(
                source.owner_axes_id,
                colorbar,
                component_id=component_id,
            )
            return colorbar
        except Exception:
            leaked = getattr(source.mappable, "colorbar", None)
            if isinstance(leaked, Colorbar) and leaked.ax not in before_axes:
                try:
                    leaked.remove()
                except Exception:
                    pass
            for axes in tuple(figure.axes):
                if axes not in before_axes:
                    try:
                        figure.delaxes(axes)
                    except Exception:
                        pass
            geometry.restore_runtime(owner_snapshots)
            raise

    def create_runtime(
        self,
        owner_axes_id: str,
        source_component_id: str,
        properties: dict[str, Any],
        *,
        component_id: str | None = None,
    ) -> tuple[Colorbar, dict[str, Any]]:
        """Create one runtime Colorbar after complete source preflight."""

        source = self.validate_source(owner_axes_id, source_component_id)
        specs = ColorbarController.property_specs()
        normalized = ColorbarController.default_properties()
        unknown = set(properties) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown Colorbar properties: {sorted(unknown)!r}."
            )
        normalized.update(
            {
                key: specs[key].normalize(value)
                for key, value in properties.items()
            }
        )
        candidate = ComponentState(
            "colorbar-preflight",
            ComponentKind.COLORBAR,
            ComponentRole.COLORBAR,
            str(owner_axes_id),
            0,
            {"object_id": "colorbar-preflight"},
            normalized,
            {"source_component_id": str(source_component_id)},
        )
        ColorbarController(candidate)
        return (
            self._create_runtime(
                source,
                normalized,
                component_id=component_id,
            ),
            normalized,
        )

    @staticmethod
    def destroy_runtime(colorbar: Colorbar) -> None:
        """Remove a staged Colorbar and restore its pre-creation owner layout."""

        if not isinstance(colorbar, Colorbar):
            return
        try:
            handle = MATPLOTLIB_REMOVAL.prepare_colorbar(colorbar)
            MATPLOTLIB_REMOVAL.commit(handle)
            MATPLOTLIB_REMOVAL.finalize(handle)
        except (AttributeError, KeyError, RuntimeError, ValueError):
            figure = getattr(colorbar.ax, "figure", None)
            if isinstance(figure, Figure) and colorbar.ax in figure.axes:
                figure.delaxes(colorbar.ax)
            mappable = getattr(colorbar, "mappable", None)
            if mappable is not None and getattr(mappable, "colorbar", None) is colorbar:
                mappable.colorbar = None
                mappable.colorbar_cid = None

    def refresh_source(self, source_component_id: str) -> None:
        """Synchronize dependent Colorbars without copying source state."""

        source = self.source_resolvers.resolve(
            source_component_id,
            allow_empty=True,
        )
        for controller in self.dependents(source_component_id):
            target = controller.resolve_target()
            target.update_normal(source.mappable)
            state = controller.state
            for key in (
                "locator",
                "formatter",
                "minor_ticks",
                "ticklocation",
                "label_font",
                "tick_font",
                "outline_visible",
                "outline_color",
                "outline_linewidth",
            ):
                controller._write_property(
                    target,
                    controller.property_specs()[key],
                    deepcopy(state.properties[key]),
                )
            controller._request_updates(UpdateImpact.REDRAW, target)

    def apply_properties(
        self,
        component,
        properties: dict[str, Any],
    ) -> ComponentChange:
        """Apply safe edits in place and rebuild constructor-sensitive edits."""

        controller = _controller(self.registry, component, ColorbarController)
        patch = dict(properties)
        try:
            old = controller.resolve_target()

            def verify_render() -> None:
                canvas = old.ax.figure.canvas
                if canvas is not None:
                    canvas.draw()

            if not set(patch).intersection(controller.REBUILD_KEYS):
                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_render,
                )
                if not batch.changes:
                    return _rejected(controller, batch.message or "Colorbar render failed.")
                return batch.changes[0]

            before = controller.state
            merged = deepcopy(before.properties)
            specs = controller.property_specs()
            for key, value in patch.items():
                if key not in specs:
                    raise ComponentValidationError(
                        f"Unknown Colorbar property {key!r}."
                    )
                merged[key] = specs[key].normalize(value)
            candidate = before.clone(properties=merged)
            controller.validate_candidate_state(candidate)
            source = self.source_resolvers.resolve(
                before.data["source_component_id"],
                allow_empty=True,
            )
            controller_memento = controller.capture_runtime_memento()
            follower_snapshot = None
            if self.geometry_service is not None:
                follower_snapshot = (
                    self.geometry_service.colorbar_follower_snapshot(
                        controller.component_id
                    )
                )
            old_handle = controller.prepare_remove()
            controller.commit_remove(old_handle)
            new = None
            try:
                if self.geometry_service is None:
                    raise ComponentValidationError(
                        "Colorbar runtime rebuild requires AxesGeometryService."
                    )
                self.geometry_service.project_owner_from_state(
                    source.owner_axes_id
                )
                new = self._create_runtime(
                    source,
                    merged,
                    component_id=controller.component_id,
                )
                temporary = ColorbarController(candidate, target=new)
                configured = temporary.apply_state(candidate)
                if not configured.ok:
                    raise ComponentValidationError(configured.message)
                self.registry.locator.bind(controller.component_id, new)
                controller.adopt_runtime_configuration(
                    temporary.runtime_configuration(),
                    include_constructor_properties=False,
                )

                def verify_new_render() -> None:
                    canvas = new.ax.figure.canvas
                    if canvas is not None:
                        canvas.draw()

                batch = self.registry.apply_transaction(
                    (ComponentMutation(controller.component_id, properties=patch),),
                    verifier=verify_new_render,
                )
                if not batch.committed or not batch.changes:
                    raise ComponentValidationError(
                        batch.message or "Colorbar render failed."
                    )
                change = batch.changes[0]
            except Exception:
                if new is not None:
                    self.destroy_runtime(new)
                self.registry.locator.bind(controller.component_id, old)
                controller.rollback_remove(old_handle)
                controller.restore_runtime_memento(controller_memento)
                if self.geometry_service is not None:
                    self.geometry_service.restore_colorbar_follower(
                        controller.component_id,
                        follower_snapshot,
                    )
                raise
            controller.finalize_removal(old_handle)
            return change
        except Exception as exc:
            return _rejected(controller, str(exc))

    def prepare_runtime_rebuilds(
        self,
        colorbar_component_ids: tuple[str, ...],
    ) -> ColorbarRuntimeRebuildBatch:
        """Stage Colorbar rebuilds while retaining exact rollback handles."""

        batch = ColorbarRuntimeRebuildBatch(self)
        try:
            for component_id in dict.fromkeys(colorbar_component_ids):
                controller = _controller(
                    self.registry,
                    component_id,
                    ColorbarController,
                )
                source = self.source_resolvers.resolve(
                    controller.state.data["source_component_id"],
                    allow_empty=True,
                )
                old = controller.resolve_target()
                controller_runtime = controller.capture_runtime_memento()
                follower_runtime = None
                if self.geometry_service is not None:
                    follower_runtime = (
                        self.geometry_service.colorbar_follower_snapshot(
                            controller.component_id
                        )
                    )
                removal_handle = controller.prepare_remove()
                controller.commit_remove(removal_handle)
                new = None
                try:
                    if self.geometry_service is None:
                        raise ComponentValidationError(
                            "Colorbar runtime rebuild requires "
                            "AxesGeometryService."
                        )
                    self.geometry_service.project_owner_from_state(
                        source.owner_axes_id
                    )
                    new = self._create_runtime(
                        source,
                        controller.state.properties,
                        component_id=controller.component_id,
                    )
                    temporary = ColorbarController(
                        controller.state,
                        target=new,
                    )
                    configured = temporary.apply_state(controller.state)
                    if not configured.ok:
                        raise ComponentValidationError(configured.message)
                    self.registry.locator.bind(controller.component_id, new)
                    controller.adopt_runtime_configuration(
                        temporary.runtime_configuration()
                    )
                except Exception:
                    if new is not None:
                        self.destroy_runtime(new)
                    self.registry.locator.bind(controller.component_id, old)
                    controller.rollback_remove(removal_handle)
                    controller.restore_runtime_memento(controller_runtime)
                    if self.geometry_service is not None:
                        self.geometry_service.restore_colorbar_follower(
                            controller.component_id,
                            follower_runtime,
                        )
                    raise
                batch.append(
                    _ColorbarRuntimeRebuildItem(
                        controller,
                        old,
                        removal_handle,
                        new,
                        controller_runtime,
                        follower_runtime,
                    )
                )
        except Exception:
            batch.rollback()
            raise
        return batch

    def rebuild_runtime(self, colorbar_component_id: str) -> None:
        """Rebuild one existing Colorbar runtime target using its persisted state."""

        batch = self.prepare_runtime_rebuilds((colorbar_component_id,))
        batch.commit()
