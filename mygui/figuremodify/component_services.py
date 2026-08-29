"""Application services for Controller-managed Matplotlib components.

Controllers remain independent from Qt and the table repository.  These
services adapt application data, fitting and render validation to the atomic
Controller mutation API without becoming a second state store.

Implementation lives under ``mygui.figuremodify.services``; this module remains
the stable import facade.
"""

from __future__ import annotations

from .services.annotation import AnnotationService
from .services.axes_command import AxesCommandService, AxesPaletteStatus
from .services.axes_geometry import AxesGeometryService
from .services.chart_data import (
    ChartDataService,
    FitService,
    FunctionCurveService,
    InterpolationService,
)
from .services.colorbar import (
    ColorbarService,
    ColorbarSourceResolution,
    ColorbarSourceResolverRegistry,
    Field2DColorbarSourceResolver,
    ScatterColorbarSourceResolver,
    production_colorbar_source_resolvers,
)
from .services.deletion import (
    ColorConsumptionLedger,
    ColorCycleDeletionEffect,
    ColorLedgerDeletionPlan,
    ComponentDeletionService,
    DeleteReason,
    DeletionHandler,
    DeletionHandlerRegistry,
    DeletionOutcome,
    DeletionPlan,
    DeletionRequest,
    PreparedDeletion,
    production_deletion_handlers,
)
from .services.dependency import (
    ComponentDependencyService,
    ComponentDependencySnapshot,
)
from .services.errorbar import (
    ErrorBarDataService,
    ErrorBarRuntime,
    ErrorBarSwapMemento,
    create_errorbar_container,
    errorbar_properties_from_appearance,
    resolve_errorbar_data,
)
from .services.field_2d import Field2DService, default_field_2d_properties
from .services.reference_marks import ReferenceGuideService, ReferenceMarksService
from .services.text_render import TextRenderService

__all__ = [
    "AnnotationService",
    "AxesCommandService",
    "AxesGeometryService",
    "AxesPaletteStatus",
    "ChartDataService",
    "ColorConsumptionLedger",
    "ColorCycleDeletionEffect",
    "ColorLedgerDeletionPlan",
    "ColorbarService",
    "ColorbarSourceResolution",
    "ColorbarSourceResolverRegistry",
    "ComponentDeletionService",
    "ComponentDependencyService",
    "ComponentDependencySnapshot",
    "DeleteReason",
    "DeletionHandler",
    "DeletionHandlerRegistry",
    "DeletionOutcome",
    "DeletionPlan",
    "DeletionRequest",
    "ErrorBarDataService",
    "ErrorBarRuntime",
    "ErrorBarSwapMemento",
    "create_errorbar_container",
    "errorbar_properties_from_appearance",
    "FitService",
    "Field2DColorbarSourceResolver",
    "Field2DService",
    "FunctionCurveService",
    "InterpolationService",
    "PreparedDeletion",
    "ReferenceGuideService",
    "ReferenceMarksService",
    "ScatterColorbarSourceResolver",
    "TextRenderService",
    "default_field_2d_properties",
    "production_colorbar_source_resolvers",
    "production_deletion_handlers",
    "resolve_errorbar_data",
    "create_errorbar_container",
    "errorbar_properties_from_appearance",
]
