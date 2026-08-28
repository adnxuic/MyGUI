"""Public domain API for reusable MyGUI chart templates."""

from .application import TemplateApplyService
from .fit_execution import FitExecutionResult, FitExecutionService
from .matching import TemplateMatcher, build_project_document, normalize_header, slot_column_refs
from .models import (
    ChartTemplate,
    TemplateApplicationPlan,
    TemplateBindingPlan,
    TemplateColumnBinding,
    TemplateColumnSlot,
    TemplateDataContract,
    TemplateLibraryEntry,
    TemplateMetadata,
    TemplateSheetBinding,
    TemplateSheetSlot,
)
from .schema import (
    TEMPLATE_FILE_SUFFIX,
    TEMPLATE_PROJECT_ID,
    TEMPLATE_SCHEMA_NAME,
    TEMPLATE_SCHEMA_VERSION,
    migrate_v1_template_to_v2,
    parse_template,
    parse_template_record,
    template_to_dict,
    validate_template,
)
from .storage import TemplateLibrary
from .tokens import resolve_tokens, token_values
from .transform import TemplateExtractor, remap_template_figure, template_content_summary

__all__ = [
    "ChartTemplate",
    "FitExecutionResult",
    "FitExecutionService",
    "TemplateApplicationPlan",
    "TemplateApplyService",
    "TemplateBindingPlan",
    "TemplateColumnBinding",
    "TemplateColumnSlot",
    "TemplateDataContract",
    "TemplateExtractor",
    "TemplateLibrary",
    "TemplateLibraryEntry",
    "TemplateMatcher",
    "TemplateMetadata",
    "TemplateSheetBinding",
    "TemplateSheetSlot",
    "TEMPLATE_FILE_SUFFIX",
    "TEMPLATE_PROJECT_ID",
    "TEMPLATE_SCHEMA_NAME",
    "TEMPLATE_SCHEMA_VERSION",
    "build_project_document",
    "migrate_v1_template_to_v2",
    "normalize_header",
    "parse_template",
    "parse_template_record",
    "remap_template_figure",
    "resolve_tokens",
    "slot_column_refs",
    "template_content_summary",
    "template_to_dict",
    "token_values",
    "validate_template",
]
