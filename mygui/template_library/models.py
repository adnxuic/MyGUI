"""Immutable business models for reusable chart templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mygui.database import ColumnRef, ColumnType, ProjectTableDocument


@dataclass(frozen=True, slots=True)
class TemplateColumnSlot:
    """One logical column required by a template."""

    id: str
    name: str
    type: ColumnType


@dataclass(frozen=True, slots=True)
class TemplateSheetSlot:
    """One logical Sheet and its required columns."""

    id: str
    name: str
    columns: tuple[TemplateColumnSlot, ...]


@dataclass(frozen=True, slots=True)
class TemplateDataContract:
    """The closed header/type contract used to match imported data."""

    algorithm_version: int
    allow_extra_columns: bool
    sheets: tuple[TemplateSheetSlot, ...]


@dataclass(frozen=True, slots=True)
class TemplateMetadata:
    """Stable identity and user-managed descriptive fields."""

    id: str
    name: str
    notes: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ChartTemplate:
    """One validated, reusable Figure blueprint."""

    metadata: TemplateMetadata
    data_contract: TemplateDataContract
    figure: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TemplateColumnBinding:
    """One resolved logical-column to imported-column mapping."""

    slot_id: str
    imported_name: str
    imported_index: int
    type: ColumnType


@dataclass(frozen=True, slots=True)
class TemplateSheetBinding:
    """One resolved logical-Sheet to imported-Sheet mapping."""

    slot_id: str
    imported_index: int
    imported_name: str
    columns: tuple[TemplateColumnBinding, ...]


@dataclass(frozen=True, slots=True)
class TemplateBindingPlan:
    """Complete matching outcome plus user-facing diagnostics."""

    sheets: tuple[TemplateSheetBinding, ...]
    diagnostics: tuple[str, ...] = ()
    ambiguous_slots: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        """Return whether every contract slot has one unambiguous binding."""

        return not self.diagnostics and not self.ambiguous_slots


@dataclass(frozen=True, slots=True)
class TemplateApplicationPlan:
    """A validated project snapshot ready for staged publication."""

    project: ProjectTableDocument
    project_snapshot: dict[str, Any]
    binding: TemplateBindingPlan
    fitted_component_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TemplateLibraryEntry:
    """A valid template or a corrupt on-disk record shown by management UI."""

    path: Path
    template: ChartTemplate | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        """Return whether the entry contains a parsed template."""

        return self.template is not None and self.error is None


TemplateColumnRefMap = dict[str, ColumnRef]
