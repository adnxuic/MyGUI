"""Lifecycle service for parent-bound Secondary Axis components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from matplotlib.axes import Axes

from mygui.figuremodify.components import (
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRegistry,
    ComponentRole,
    ComponentValidationError,
    SecondaryAxisController,
    SecondaryAxisRuntime,
)
from mygui.figuremodify.components.secondary_axis_values import (
    DEFAULT_SECONDARY_X_PLACEMENT,
    DEFAULT_SECONDARY_Y_PLACEMENT,
    DEFAULT_UNIT_TRANSFORM,
    normalize_secondary_axis_placement,
    normalize_unit_transform,
    parent_scale_domain_samples,
    secondary_axis_placement_key,
    validate_unit_transform_domain,
)

from ._helpers import _controller, _rejected


@dataclass(frozen=True, slots=True)
class UnitTransformSpec:
    """Public creation value for one persisted unit mapping."""

    value: dict[str, Any]

    def normalized(self) -> dict[str, Any]:
        return normalize_unit_transform(self.value)


@dataclass(frozen=True, slots=True)
class SecondaryAxisPlacementSpec:
    """Public creation value for one Secondary Axis location."""

    value: dict[str, Any]

    def normalized(self, orientation: str) -> dict[str, Any]:
        return normalize_secondary_axis_placement(self.value, orientation=orientation)


@dataclass(frozen=True, slots=True)
class SecondaryAxisCreateSpec:
    """Controller-free Secondary Axis creation request."""

    orientation: str
    unit_transform: dict[str, Any] | UnitTransformSpec | None = None
    placement: dict[str, Any] | SecondaryAxisPlacementSpec | None = None
    properties: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        orientation = str(self.orientation).casefold()
        if orientation not in {"x", "y"}:
            raise ComponentValidationError("Secondary Axis orientation must be 'x' or 'y'.")
        object.__setattr__(self, "orientation", orientation)

    def normalized_unit_transform(self) -> dict[str, Any]:
        value = self.unit_transform
        if value is None:
            value = DEFAULT_UNIT_TRANSFORM
        if isinstance(value, UnitTransformSpec):
            return value.normalized()
        return normalize_unit_transform(value)

    def normalized_placement(self) -> dict[str, Any]:
        value = self.placement
        if value is None:
            value = (
                DEFAULT_SECONDARY_X_PLACEMENT
                if self.orientation == "x"
                else DEFAULT_SECONDARY_Y_PLACEMENT
            )
        if isinstance(value, SecondaryAxisPlacementSpec):
            return value.normalized(self.orientation)
        return normalize_secondary_axis_placement(value, orientation=self.orientation)


class SecondaryAxisService:
    """Create and edit Secondary Axes without creating a parallel Axes store."""

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        warning_callback: Callable[[str], Any] | None = None,
    ) -> None:
        self.registry = registry
        self._warning_callback = warning_callback

    @staticmethod
    def _role(orientation: str) -> ComponentRole:
        return (
            ComponentRole.SECONDARY_X_AXIS if orientation == "x" else ComponentRole.SECONDARY_Y_AXIS
        )

    @staticmethod
    def _orientation(role: ComponentRole) -> str:
        return "x" if role is ComponentRole.SECONDARY_X_AXIS else "y"

    def _validate_unique(
        self,
        owner_axes_id: str,
        orientation: str,
        placement: dict[str, Any],
        *,
        exclude_component_id: str | None = None,
    ) -> None:
        requested = secondary_axis_placement_key(placement, orientation=orientation)
        for controller in self.registry.query(
            parent_id=owner_axes_id, kind=ComponentKind.SECONDARY_AXIS
        ):
            if controller.component_id == exclude_component_id:
                continue
            state = controller.state
            if self._orientation(state.role) != orientation:
                continue
            existing = secondary_axis_placement_key(
                state.properties["placement"], orientation=orientation
            )
            if existing == requested:
                raise ComponentValidationError(
                    "A Secondary Axis already occupies this normalized placement."
                )

    def normalize_creation(
        self,
        owner_axes_id: str,
        spec: SecondaryAxisCreateSpec,
        *,
        allow_invalid_domain: bool = False,
    ) -> tuple[dict[str, Any], Axes]:
        owner = self.registry.resolve_target(str(owner_axes_id))
        if not isinstance(owner, Axes):
            raise ComponentValidationError("Secondary Axis requires a registered owner Axes.")
        properties = SecondaryAxisController.default_properties()
        requested = dict(spec.properties or {})
        unknown = set(requested) - set(SecondaryAxisController.property_specs())
        if unknown:
            raise ComponentValidationError(
                f"Unknown Secondary Axis properties: {sorted(unknown)!r}."
            )
        property_specs = SecondaryAxisController.property_specs()
        properties.update(
            {key: property_specs[key].normalize(value) for key, value in requested.items()}
        )
        properties["unit_transform"] = spec.normalized_unit_transform()
        properties["placement"] = spec.normalized_placement()
        self._validate_unique(owner_axes_id, spec.orientation, properties["placement"])
        limits = owner.get_xlim() if spec.orientation == "x" else owner.get_ylim()
        if not allow_invalid_domain:
            validate_unit_transform_domain(
                properties["unit_transform"],
                *limits,
                source_values=parent_scale_domain_samples(owner, spec.orientation),
            )
        return properties, owner

    def create_runtime(
        self,
        owner_axes_id: str,
        spec: SecondaryAxisCreateSpec,
        *,
        allow_invalid_domain: bool = False,
    ) -> tuple[SecondaryAxisRuntime, dict[str, Any]]:
        properties, owner = self.normalize_creation(
            owner_axes_id,
            spec,
            allow_invalid_domain=allow_invalid_domain,
        )
        runtime = SecondaryAxisRuntime(
            owner,
            spec.orientation,
            properties["unit_transform"],
            properties["placement"],
            requested_visible=properties["visible"],
            warning_callback=self._warning_callback,
        )
        return runtime, properties

    @staticmethod
    def destroy_runtime(runtime: SecondaryAxisRuntime) -> None:
        if not isinstance(runtime, SecondaryAxisRuntime):
            return
        try:
            if runtime.axis in runtime.parent_axes.child_axes:
                runtime.axis.remove()
        finally:
            runtime.dispose()

    def apply_properties(
        self,
        component: Any,
        properties: dict[str, Any],
    ) -> ComponentChange:
        controller = _controller(self.registry, component, SecondaryAxisController)
        patch = dict(properties)
        try:
            specs = controller.property_specs()
            unknown = set(patch) - set(specs)
            if unknown:
                raise ComponentValidationError(
                    f"Unknown Secondary Axis properties: {sorted(unknown)!r}."
                )
            if "placement" in patch:
                orientation = controller.orientation
                normalized = normalize_secondary_axis_placement(
                    patch["placement"], orientation=orientation
                )
                self._validate_unique(
                    controller.state.parent_id or "",
                    orientation,
                    normalized,
                    exclude_component_id=controller.component_id,
                )
                patch["placement"] = normalized
            if "unit_transform" in patch:
                runtime = controller.resolve_target()
                normalized_transform = normalize_unit_transform(patch["unit_transform"])
                limits = (
                    runtime.parent_axes.get_xlim()
                    if controller.orientation == "x"
                    else runtime.parent_axes.get_ylim()
                )
                validate_unit_transform_domain(
                    normalized_transform,
                    *limits,
                    source_values=parent_scale_domain_samples(
                        runtime.parent_axes, controller.orientation
                    ),
                )
                patch["unit_transform"] = normalized_transform

            runtime = controller.resolve_target()

            def verify_render() -> None:
                canvas = runtime.parent_axes.figure.canvas
                if canvas is not None:
                    canvas.draw()

            batch = self.registry.apply_transaction(
                (ComponentMutation(controller.component_id, properties=patch),),
                verifier=verify_render,
            )
            if not batch.changes:
                return _rejected(
                    controller,
                    batch.message or "Secondary Axis render failed.",
                )
            return batch.changes[0]
        except Exception as exc:
            return _rejected(controller, str(exc))

    def reapply_runtime_styles(self) -> None:
        """Refresh scale-domain health and custom tickers before each draw."""

        for controller in self.registry.query(kind=ComponentKind.SECONDARY_AXIS):
            if not isinstance(controller, SecondaryAxisController):
                continue
            controller.reapply_runtime_style()
