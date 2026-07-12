from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

import numpy as np
import pandas as pd

from Qt_core import QObject, QUndoCommand, QUndoStack, Signal

from code.database.table_document import (
    ColumnRef,
    ColumnType,
    ProjectTableDocument,
    SheetDocument,
)


@dataclass
class TableChangeSet:
    project_id: str
    changed_columns: set[ColumnRef] = field(default_factory=set)
    metadata_changed: bool = False
    structure_changed: bool = False
    reason: str = "edit"

    def merge(self, other: "TableChangeSet") -> None:
        if self.project_id != other.project_id:
            raise ValueError("Cannot merge changes from different projects.")
        self.changed_columns.update(other.changed_columns)
        self.metadata_changed = self.metadata_changed or other.metadata_changed
        self.structure_changed = self.structure_changed or other.structure_changed
        if self.reason == "edit" and other.reason != "edit":
            self.reason = other.reason


@dataclass(frozen=True)
class AlignedPair:
    x: np.ndarray
    y: np.ndarray
    valid_mask: np.ndarray
    missing_count: int


class TableMutationCommand(QUndoCommand):
    def __init__(self, text: str, repository: "TableRepository", project_id: str,
                 redo_action: Callable[[], None], undo_action: Callable[[], None],
                 changes: Callable[[], TableChangeSet] | TableChangeSet):
        super().__init__(text)
        self.repository = repository
        self.project_id = project_id
        self.redo_action = redo_action
        self.undo_action = undo_action
        self.changes = changes

    def _change_set(self) -> TableChangeSet:
        return self.changes() if callable(self.changes) else self.changes

    def redo(self) -> None:
        with self.repository.transaction(self.project_id):
            self.redo_action()
            self.repository.record_change(self._change_set())

    def undo(self) -> None:
        with self.repository.transaction(self.project_id):
            self.undo_action()
            self.repository.record_change(self._change_set())


class TableRepository(QObject):
    transaction_committed = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.projects: "OrderedDict[str, ProjectTableDocument]" = OrderedDict()
        self._undo_stacks: dict[str, QUndoStack] = {}
        self._transaction_depth = 0
        self._pending: dict[str, TableChangeSet] = {}

    def clear(self) -> None:
        project_ids = list(self.projects)
        self.projects.clear()
        self._undo_stacks.clear()
        for project_id in project_ids:
            self.transaction_committed.emit(TableChangeSet(
                project_id=project_id,
                metadata_changed=True,
                structure_changed=True,
                reason="clear",
            ))

    def create_project(self, name: str, first_sheet_name: str = "Sheet1",
                       project_id: str | None = None) -> ProjectTableDocument:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("Project name must not be empty.")
        if self.project_by_name(cleaned, required=False) is not None:
            raise ValueError(f"Project already exists: {cleaned}")
        project = ProjectTableDocument.create(cleaned, first_sheet_name)
        if project_id is not None:
            project.id = project_id
        self.register_project(project)
        return project

    def register_project(self, project: ProjectTableDocument) -> None:
        if project.id in self.projects:
            raise ValueError(f"Project id already exists: {project.id}")
        if self.project_by_name(project.name, required=False) is not None:
            raise ValueError(f"Project already exists: {project.name}")
        self.projects[project.id] = project
        stack = QUndoStack(self)
        stack.setUndoLimit(50)
        self._undo_stacks[project.id] = stack
        self.transaction_committed.emit(TableChangeSet(
            project_id=project.id,
            metadata_changed=True,
            structure_changed=True,
            reason="project-added",
        ))

    def remove_project(self, project_id: str) -> ProjectTableDocument | None:
        project = self.projects.pop(project_id, None)
        stack = self._undo_stacks.pop(project_id, None)
        if stack is not None:
            stack.deleteLater()
        if project is not None:
            self.transaction_committed.emit(TableChangeSet(
                project_id=project_id,
                metadata_changed=True,
                structure_changed=True,
                reason="project-removed",
            ))
        return project

    def project(self, project_id: str) -> ProjectTableDocument:
        try:
            return self.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project: {project_id}") from exc

    def project_by_name(self, name: str, required: bool = True) -> ProjectTableDocument | None:
        normalized = str(name).strip().casefold()
        for project in self.projects.values():
            if project.name.casefold() == normalized:
                return project
        if required:
            raise KeyError(f"Unknown project: {name}")
        return None

    def sheet(self, project_id: str, sheet_id: str) -> SheetDocument:
        project = self.project(project_id)
        try:
            return project.sheets[sheet_id]
        except KeyError as exc:
            raise KeyError(f"Unknown sheet: {sheet_id}") from exc

    def undo_stack(self, project_id: str) -> QUndoStack:
        try:
            return self._undo_stacks[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project undo stack: {project_id}") from exc

    def push(self, project_id: str, command: QUndoCommand) -> None:
        self.undo_stack(project_id).push(command)

    @contextmanager
    def transaction(self, project_id: str) -> Iterator[None]:
        self._transaction_depth += 1
        try:
            yield
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                pending = list(self._pending.values())
                self._pending.clear()
                for changes in pending:
                    self.transaction_committed.emit(changes)

    def record_change(self, changes: TableChangeSet) -> None:
        existing = self._pending.get(changes.project_id)
        if existing is None:
            self._pending[changes.project_id] = changes
        else:
            existing.merge(changes)
        if self._transaction_depth == 0:
            pending = self._pending.pop(changes.project_id)
            self.transaction_committed.emit(pending)

    def column_ref(self, project_id: str, sheet_id: str, column_id: str) -> ColumnRef:
        self.sheet(project_id, sheet_id).column(column_id)
        return ColumnRef(project_id, sheet_id, column_id)

    def has_ref(self, ref: ColumnRef | None) -> bool:
        if ref is None:
            return False
        try:
            self.sheet(ref.project_id, ref.sheet_id).column(ref.column_id)
        except KeyError:
            return False
        return True

    def iter_column_refs(self, project_id: str | None = None,
                         allowed_types: Iterable[ColumnType] | None = None) -> Iterator[ColumnRef]:
        allowed = set(allowed_types) if allowed_types is not None else None
        projects = self.projects.values() if project_id is None else (self.project(project_id),)
        for project in projects:
            for sheet in project.sheets.values():
                for column in sheet.columns:
                    if allowed is None or column.type in allowed:
                        yield ColumnRef(project.id, sheet.id, column.id)

    def ref_label(self, ref: ColumnRef) -> str:
        project = self.project(ref.project_id)
        sheet = self.sheet(ref.project_id, ref.sheet_id)
        column = sheet.column(ref.column_id)
        return f"{project.name}/{sheet.name}/{column.name}"

    def series(self, ref: ColumnRef) -> pd.Series:
        if not self.has_ref(ref):
            raise KeyError("Data column no longer exists.")
        return self.sheet(ref.project_id, ref.sheet_id).frame[ref.column_id]

    def line_pair(self, x_ref: ColumnRef, y_ref: ColumnRef) -> AlignedPair:
        x_series, y_series = self._aligned_series(x_ref, y_ref)
        if len(x_series) != len(y_series):
            raise ValueError("Data columns must belong to row-aligned sheets.")
        valid = (x_series.notna() & y_series.notna()).to_numpy(dtype=bool)
        x = self._plot_values(x_series)
        y = self._plot_values(y_series)
        if np.issubdtype(x.dtype, np.datetime64):
            x = x.astype("datetime64[ns]")
            x[~valid] = np.datetime64("NaT")
        else:
            x = x.astype(float, copy=True)
            x[~valid] = np.nan
        y = y.astype(float, copy=True)
        y[~valid] = np.nan
        return AlignedPair(x, y, valid, int((~valid).sum()))

    def valid_pair(self, x_ref: ColumnRef, y_ref: ColumnRef) -> AlignedPair:
        x_series, y_series = self._aligned_series(x_ref, y_ref)
        if len(x_series) != len(y_series):
            raise ValueError("Data columns must belong to row-aligned sheets.")
        valid = (x_series.notna() & y_series.notna()).to_numpy(dtype=bool)
        x_all = self._numeric_values(x_series)
        y_all = self._numeric_values(y_series)
        finite = np.isfinite(x_all) & np.isfinite(y_all)
        valid &= finite
        return AlignedPair(
            x=x_all[valid],
            y=y_all[valid],
            valid_mask=valid,
            missing_count=int((~valid).sum()),
        )

    def _aligned_series(self, x_ref: ColumnRef, y_ref: ColumnRef) -> tuple[pd.Series, pd.Series]:
        x_series = self.series(x_ref)
        y_series = self.series(y_ref)
        if len(x_series) != len(y_series):
            raise ValueError("Data columns must belong to row-aligned sheets.")
        occupied = (x_series.notna() | y_series.notna()).to_numpy(dtype=bool)
        if not occupied.any():
            return x_series.iloc[:0], y_series.iloc[:0]
        stop = int(np.flatnonzero(occupied)[-1]) + 1
        return x_series.iloc[:stop], y_series.iloc[:stop]

    @staticmethod
    def _numeric_values(series: pd.Series) -> np.ndarray:
        if pd.api.types.is_datetime64_any_dtype(series.dtype):
            values = series.astype("int64", copy=False).to_numpy(dtype=float)
            values[series.isna().to_numpy()] = np.nan
            return values
        try:
            return series.to_numpy(dtype=float, na_value=np.nan)
        except (TypeError, ValueError) as exc:
            raise ValueError("Selected data column must be numeric or date/time.") from exc

    @staticmethod
    def _plot_values(series: pd.Series) -> np.ndarray:
        if pd.api.types.is_datetime64_any_dtype(series.dtype):
            return series.to_numpy(dtype="datetime64[ns]")
        return TableRepository._numeric_values(series)

    def snapshot(self, project_id: str) -> dict[str, Any]:
        return self.project(project_id).to_snapshot()

    def restore_snapshot(self, snapshot: dict[str, Any]) -> ProjectTableDocument:
        project = ProjectTableDocument.from_snapshot(snapshot)
        self.register_project(project)
        return project
