"""Plan and publish an all-or-nothing chart-template application."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from mygui.project_io import (
    PROJECT_SCHEMA_NAME,
    PROJECT_SCHEMA_VERSION,
    restore_project_payload,
    validate_project_snapshot,
)

from .fit_execution import FitExecutionService
from .matching import TemplateMatcher, build_project_document, slot_column_refs
from .models import ChartTemplate, TemplateApplicationPlan
from .tokens import resolve_tokens, token_values
from .transform import remap_template_figure


class TemplateApplyService:
    """Own preprocessing, fitting, validation, and staged project publication."""

    def __init__(self, repository=None, fit_executor: FitExecutionService | None = None):
        self.repository = repository
        self.matcher = TemplateMatcher()
        self.fit_executor = fit_executor or FitExecutionService()

    def prepare(
        self,
        template: ChartTemplate,
        imported_sheets,
        *,
        source_file: str | Path,
        project_name: str,
        explicit_sheet_mapping: dict[str, int] | None = None,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> TemplateApplicationPlan:
        """Build a strictly valid schema-v16 snapshot without publishing state."""

        if self.repository is not None and self.repository.project_by_name(
            project_name, required=False
        ) is not None:
            raise ValueError(f"Project already exists: {project_name}")
        binding = self.matcher.match(
            template,
            list(imported_sheets),
            explicit_sheet_mapping=explicit_sheet_mapping,
        )
        if not binding.valid:
            parts = list(binding.diagnostics)
            if binding.ambiguous_slots:
                parts.append("Choose a distinct imported Sheet for every ambiguous template Sheet.")
            raise ValueError("Template data mapping is incomplete: " + "; ".join(parts))
        project, runtime_refs = build_project_document(project_name, list(imported_sheets))
        figure = remap_template_figure(
            template,
            project_id=project.id,
            column_refs=slot_column_refs(binding, runtime_refs),
        )
        figure = resolve_tokens(
            figure,
            token_values(
                template,
                binding,
                project_name=project.name,
                source_file=source_file,
            ),
        )
        fitted_ids = self.fit_executor.execute_all(
            project,
            figure,
            cancelled=cancelled,
            progress=progress,
        )
        if cancelled is not None and cancelled():
            raise RuntimeError("Template application was cancelled.")
        snapshot = {
            "schema": PROJECT_SCHEMA_NAME,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project": {"id": project.id, "name": project.name},
            "table": project.to_snapshot(),
            "figure": figure,
        }
        validate_project_snapshot(snapshot)
        return TemplateApplicationPlan(project, snapshot, binding, fitted_ids)

    def publish(self, plan: TemplateApplicationPlan, *, table, figure_window):
        """Publish one prepared plan through the shared project restore transaction."""

        from mygui.figuremodify.services.template_axes import (
            TemplateAxesAutoscaleService,
        )

        restored = restore_project_payload(
            plan.project_snapshot,
            table=table,
            figure_window=figure_window,
            project_path=None,
            mark_clean=False,
            before_figure_publish=lambda canvas: TemplateAxesAutoscaleService(
                canvas.component_registry
            ).recompute(),
        )
        canvas = figure_window.current_canva
        stack = figure_window.repository.undo_stack(plan.project.id)
        stack.clear()
        if canvas is None or canvas.project_id != plan.project.id:
            raise RuntimeError("Template project publication did not select the new project.")
        return restored
