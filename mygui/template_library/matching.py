"""Deterministic header/type matching for template application."""

from __future__ import annotations

from collections import OrderedDict
import re
import unicodedata

from mygui.database import ColumnRef, ProjectTableDocument, SheetDocument
from mygui.database.table_document import new_id, validate_component_name
from mygui.excel_io import ExcelSheetSpec

from .models import (
    ChartTemplate,
    TemplateBindingPlan,
    TemplateColumnBinding,
    TemplateSheetBinding,
)


_WHITESPACE = re.compile(r"\s+")


def normalize_header(value: str) -> str:
    """Normalize headers while retaining punctuation and units."""

    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", str(value)).strip()).casefold()


class TemplateMatcher:
    """Match one imported workbook/text preview against a template contract."""

    def _candidate(
        self,
        sheet_slot,
        imported: ExcelSheetSpec,
        imported_index: int,
    ) -> tuple[TemplateSheetBinding | None, tuple[str, ...]]:
        by_name: dict[str, list[tuple[int, object]]] = {}
        for column_index, column in enumerate(imported.columns):
            by_name.setdefault(normalize_header(column.name), []).append((column_index, column))
        diagnostics: list[str] = []
        bindings: list[TemplateColumnBinding] = []
        for slot in sheet_slot.columns:
            matches = by_name.get(normalize_header(slot.name), [])
            if not matches:
                diagnostics.append(f"{sheet_slot.name}/{slot.name}: missing column")
                continue
            if len(matches) > 1:
                diagnostics.append(f"{sheet_slot.name}/{slot.name}: duplicate normalized header")
                continue
            column_index, column = matches[0]
            if column.type is not slot.type:
                diagnostics.append(
                    f"{sheet_slot.name}/{slot.name}: expected {slot.type.value}, got {column.type.value}"
                )
                continue
            bindings.append(
                TemplateColumnBinding(slot.id, column.name, column_index, column.type)
            )
        if diagnostics:
            return None, tuple(diagnostics)
        return (
            TemplateSheetBinding(
                sheet_slot.id,
                imported_index,
                imported.target_name,
                tuple(bindings),
            ),
            (),
        )

    def match(
        self,
        template: ChartTemplate,
        imported_sheets: list[ExcelSheetSpec],
        *,
        explicit_sheet_mapping: dict[str, int] | None = None,
    ) -> TemplateBindingPlan:
        """Return complete mapping or deterministic diagnostics/ambiguities."""

        if not imported_sheets:
            return TemplateBindingPlan((), ("No Sheets are selected for import.",), ())
        explicit = dict(explicit_sheet_mapping or {})
        used: set[int] = set()
        chosen: list[TemplateSheetBinding] = []
        diagnostics: list[str] = []
        ambiguous: list[str] = []
        for slot in template.data_contract.sheets:
            candidates: list[TemplateSheetBinding] = []
            candidate_failures: list[str] = []
            for index, imported in enumerate(imported_sheets):
                binding, failures = self._candidate(slot, imported, index)
                if binding is not None:
                    candidates.append(binding)
                else:
                    candidate_failures.extend(failures)
            if slot.id in explicit:
                requested = explicit[slot.id]
                selected = next(
                    (item for item in candidates if item.imported_index == requested),
                    None,
                )
                if selected is None:
                    diagnostics.append(
                        f"{slot.name}: selected Sheet does not satisfy all required columns and types."
                    )
                    continue
            else:
                available = [item for item in candidates if item.imported_index not in used]
                if len(available) == 1:
                    selected = available[0]
                elif len(available) > 1:
                    ambiguous.append(slot.id)
                    continue
                else:
                    diagnostics.append(
                        f"{slot.name}: no distinct imported Sheet contains all required columns with compatible types."
                    )
                    if candidate_failures:
                        diagnostics.extend(sorted(set(candidate_failures)))
                    continue
            if selected.imported_index in used:
                diagnostics.append(f"{slot.name}: each logical Sheet must map to a distinct imported Sheet.")
                continue
            used.add(selected.imported_index)
            chosen.append(selected)
        return TemplateBindingPlan(tuple(chosen), tuple(diagnostics), tuple(ambiguous))

    def candidate_sheet_indices(
        self,
        template: ChartTemplate,
        imported_sheets: list[ExcelSheetSpec],
    ) -> dict[str, tuple[int, ...]]:
        """Return compatible imported Sheet indices for every logical slot."""

        result = {}
        for slot in template.data_contract.sheets:
            candidates = [
                index
                for index, imported in enumerate(imported_sheets)
                if self._candidate(slot, imported, index)[0] is not None
            ]
            candidates.sort(
                key=lambda index: (
                    normalize_header(imported_sheets[index].source_name)
                    != normalize_header(slot.name),
                    index,
                )
            )
            result[slot.id] = tuple(candidates)
        return result


def build_project_document(
    name: str,
    imported_sheets: list[ExcelSheetSpec],
) -> tuple[ProjectTableDocument, dict[tuple[int, int], ColumnRef]]:
    """Build a fresh in-memory project while preserving every previewed column."""

    project = ProjectTableDocument(
        id=new_id(),
        name=validate_component_name(name, "Project name"),
        sheets=OrderedDict(),
    )
    refs: dict[tuple[int, int], ColumnRef] = {}
    for sheet_index, spec in enumerate(imported_sheets):
        target_name = project.unique_sheet_name(spec.target_name)
        row_count = max((len(column.values) for column in spec.columns), default=0)
        sheet = SheetDocument(id=new_id(), name=target_name, row_count=row_count)
        for column_index, column in enumerate(spec.columns):
            schema = sheet.add_column(
                name=column.name,
                column_type=column.type,
                values=column.values,
            )
            refs[(sheet_index, column_index)] = ColumnRef(project.id, sheet.id, schema.id)
        project.add_sheet(sheet=sheet)
    if not project.sheets:
        raise ValueError("At least one imported Sheet is required.")
    return project, refs


def slot_column_refs(
    binding: TemplateBindingPlan,
    runtime_refs: dict[tuple[int, int], ColumnRef],
) -> dict[str, ColumnRef]:
    """Resolve logical column-slot IDs to fresh runtime references."""

    if not binding.valid:
        raise ValueError("Template mapping is incomplete.")
    return {
        column.slot_id: runtime_refs[(sheet.imported_index, column.imported_index)]
        for sheet in binding.sheets
        for column in sheet.columns
    }
