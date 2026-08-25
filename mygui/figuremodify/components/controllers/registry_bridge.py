"""First-party Controller type registry and factories."""

from __future__ import annotations

from typing import Any



from ..base import ComponentController
from ..errors import ComponentValidationError
from ..models import (
    ComponentKind,
    ComponentRole,
    ComponentState,
    EditorKind,
    RestorePhase,
)
from .axes_semantics import (
    GridController,
    SpineController,
    TickGroupController,
    TickLabelGroupController,
    XAxisController,
    YAxisController,
)
from .colorbar import ColorbarController
from .collections import (
    ReferenceBandController,
    ReferenceLineController,
    ReferenceMarksController,
    ScatterController,
)
from .containers import AxesController, FigureController
from .in_axes import ImageInAxesController, ZoomInAxesController
from .legend import LegendController
from .lines import (
    DataPlotController,
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    LineController,
)
from .text import AxisLabelController, TextController, TitleController

CONTROLLER_TYPES: dict[
    tuple[ComponentKind, ComponentRole],
    type[ComponentController[Any]],
] = {
    (ComponentKind.FIGURE, ComponentRole.FIGURE): FigureController,
    (ComponentKind.AXES, ComponentRole.AXES): AxesController,
    (ComponentKind.AXIS, ComponentRole.X_AXIS): XAxisController,
    (ComponentKind.AXIS, ComponentRole.Y_AXIS): YAxisController,
    (ComponentKind.SPINE, ComponentRole.SPINE): SpineController,
    (ComponentKind.TICK_GROUP, ComponentRole.MAJOR_TICK): TickGroupController,
    (ComponentKind.TICK_GROUP, ComponentRole.MINOR_TICK): TickGroupController,
    (
        ComponentKind.TICK_LABEL_GROUP,
        ComponentRole.MAJOR_TICK_LABEL,
    ): TickLabelGroupController,
    (
        ComponentKind.TICK_LABEL_GROUP,
        ComponentRole.MINOR_TICK_LABEL,
    ): TickLabelGroupController,
    (ComponentKind.GRID, ComponentRole.GRID): GridController,
    (ComponentKind.TEXT, ComponentRole.TITLE): TitleController,
    (ComponentKind.TEXT, ComponentRole.X_LABEL): AxisLabelController,
    (ComponentKind.TEXT, ComponentRole.Y_LABEL): AxisLabelController,
    (ComponentKind.TEXT, ComponentRole.TEXT): TextController,
    (ComponentKind.LEGEND, ComponentRole.LEGEND): LegendController,
    (ComponentKind.LINE, ComponentRole.LINE): LineController,
    (
        ComponentKind.LINE,
        ComponentRole.FUNCTION_CURVE,
    ): FunctionCurveController,
    (ComponentKind.LINE, ComponentRole.DATA_PLOT): DataPlotController,
    (ComponentKind.LINE, ComponentRole.FIT_CURVE): FitCurveController,
    (
        ComponentKind.LINE,
        ComponentRole.INTERPOLATION,
    ): InterpolationController,
    (ComponentKind.SCATTER, ComponentRole.SCATTER): ScatterController,
    (
        ComponentKind.REFERENCE_MARKS,
        ComponentRole.REFLECTION_POSITIONS,
    ): ReferenceMarksController,
    (
        ComponentKind.REFERENCE_GUIDE,
        ComponentRole.REFERENCE_LINE,
    ): ReferenceLineController,
    (
        ComponentKind.REFERENCE_GUIDE,
        ComponentRole.REFERENCE_BAND,
    ): ReferenceBandController,
    (ComponentKind.COLORBAR, ComponentRole.COLORBAR): ColorbarController,
    (
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_ZOOM,
    ): ZoomInAxesController,
    (
        ComponentKind.IN_AXES,
        ComponentRole.IN_AXES_IMAGE,
    ): ImageInAxesController,
}


def validate_controller_contracts() -> dict[
    tuple[ComponentKind, ComponentRole], RestorePhase
]:
    """Validate first-party Controller declarations and return materializers.

    The returned mapping is derived only from the Controller contracts, so it
    is an independent completeness source for the Canvas materializer registry.
    """

    materializers: dict[
        tuple[ComponentKind, ComponentRole], RestorePhase
    ] = {}
    for key, controller_type in CONTROLLER_TYPES.items():
        kind, role = key
        if controller_type.KIND is not kind or role not in controller_type.ROLES:
            raise ComponentValidationError(
                "Controller contract does not match registry key "
                f"{kind.value}/{role.value}."
            )
        specs = controller_type.PROPERTY_SPECS
        spec_keys = [spec.key for spec in specs]
        if len(spec_keys) != len(set(spec_keys)):
            raise ComponentValidationError(
                f"Controller {controller_type.__name__} declares duplicate "
                "PropertySpec keys."
            )
        for spec in specs:
            if not isinstance(spec.editor, EditorKind):
                raise ComponentValidationError(
                    f"Property {controller_type.__name__}.{spec.key} does not "
                    "declare a valid EditorKind."
                )
            if spec.editor is EditorKind.ENUM and not spec.choices:
                raise ComponentValidationError(
                    f"Property {controller_type.__name__}.{spec.key} declares "
                    "an enum editor without choices."
                )
        phase = controller_type.RESTORE_PHASE
        if phase is not None:
            if not isinstance(phase, RestorePhase):
                raise ComponentValidationError(
                    f"Controller {controller_type.__name__} declares an invalid "
                    "restore phase."
                )
            materializers[key] = phase
    return materializers


def controller_type_for(
    state: ComponentState,
) -> type[ComponentController[Any]]:
    """Return the Controller class registered for the component state."""

    try:
        return CONTROLLER_TYPES[(state.kind, state.role)]
    except KeyError as exc:
        raise ComponentValidationError(
            f"No controller is registered for "
            f"{state.kind.value}/{state.role.value}."
        ) from exc


def create_controller(
    state: ComponentState,
    *,
    target: Any | None = None,
    locator: Any | None = None,
    registry: Any | None = None,
) -> ComponentController[Any]:
    """Create controller."""

    return controller_type_for(state)(
        state,
        target=target,
        locator=locator,
        registry=registry,
    )
