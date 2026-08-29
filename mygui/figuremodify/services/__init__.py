"""Domain services split from the historical component_services module."""

from .axes_command import AxesCommandService, AxesPaletteStatus
from .axes_geometry import AxesGeometryService
from .chart_data import (
    ChartDataService,
    FitService,
    FunctionCurveService,
    InterpolationService,
)
from .colorbar import (
    ColorbarService,
    ColorbarSourceResolution,
    ColorbarSourceResolverRegistry,
    Field2DColorbarSourceResolver,
    ScatterColorbarSourceResolver,
    production_colorbar_source_resolvers,
)
from .deletion import (
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
from .dependency import ComponentDependencyService, ComponentDependencySnapshot
from .errorbar import (
    ErrorBarDataService,
    ErrorBarRuntime,
    ErrorBarSwapMemento,
    create_errorbar_container,
    errorbar_properties_from_appearance,
    resolve_errorbar_data,
)
from .field_2d import Field2DService, default_field_2d_properties, field_2d_style_seed
from .reference_marks import ReferenceGuideService, ReferenceMarksService
from .text_render import TextRenderService

__all__ = [
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
    "field_2d_style_seed",
    "production_colorbar_source_resolvers",
    "production_deletion_handlers",
    "resolve_errorbar_data",
    "create_errorbar_container",
    "errorbar_properties_from_appearance",
]
