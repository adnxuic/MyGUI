"""Coordinate table projects, undoable mutations, and data-reference lookup."""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping

import numpy as np
import pandas as pd

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from mygui.database.table_document import (
    ColumnRef,
    ColumnType,
    ProjectTableDocument,
    SheetDocument,
)


@dataclass
class TableChangeSet:
    """Describe table change set values shared across application layers."""

    project_id: str
    changed_columns: set[ColumnRef] = field(default_factory=set)
    metadata_changed: bool = False
    structure_changed: bool = False
    reason: str = "edit"

    def merge(self, other: "TableChangeSet") -> None:
        """Merge another change set into this one without duplicating IDs."""

        if self.project_id != other.project_id:
            raise ValueError("Cannot merge changes from different projects.")
        self.changed_columns.update(other.changed_columns)
        self.metadata_changed = self.metadata_changed or other.metadata_changed
        self.structure_changed = self.structure_changed or other.structure_changed
        if self.reason == "edit" and other.reason != "edit":
            self.reason = other.reason


@dataclass(frozen=True)
class AlignedPair:
    """Represent the application's aligned pair."""

    x: np.ndarray
    y: np.ndarray
    valid_mask: np.ndarray
    missing_count: int


@dataclass
class _ProjectRollback:
    project: ProjectTableDocument
    state: ProjectTableDocument
    sheets: dict[str, SheetDocument]
    columns: dict[str, dict[str, Any]]


class _MutationRejected(RuntimeError):
    """Internal control flow for a command rejected before commit."""


class TableMutationCommand(QUndoCommand):
    """Represent the application's table mutation command."""

    def __init__(self, text: str, repository: "TableRepository", project_id: str,
                 redo_action: Callable[[], None], undo_action: Callable[[], None],
                 changes: Callable[[], TableChangeSet] | TableChangeSet,
                 *, rollback_on_error: bool = False):
        super().__init__(text)
        self.repository = repository
        self.project_id = project_id
        self.redo_action = redo_action
        self.undo_action = undo_action
        self.changes = changes
        self.rollback_on_error = bool(rollback_on_error)
        self.last_succeeded = False

    def redo(self) -> None:
        """Reapply this table mutation."""

        self.last_succeeded = False
        try:
            with self.repository.mutate(
                self.changes,
                project_id=self.project_id,
                rollback=self.rollback_on_error,
            ):
                if self.redo_action() is False:
                    raise _MutationRejected
                self.last_succeeded = True
        except _MutationRejected:
            self.setObsolete(True)

    def undo(self) -> None:
        """Reverse this table mutation."""

        self.last_succeeded = False
        try:
            with self.repository.mutate(
                self.changes,
                project_id=self.project_id,
                rollback=self.rollback_on_error,
            ):
                if self.undo_action() is False:
                    raise _MutationRejected
                self.last_succeeded = True
        except _MutationRejected:
            return


class TableRepository(QObject):
    """Own and query table application state."""

    transaction_committed = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._projects: "OrderedDict[str, ProjectTableDocument]" = OrderedDict()
        self._undo_stacks: dict[str, QUndoStack] = {}
        self._unpublished_projects: set[str] = set()
        self._transaction_depths: dict[str, int] = {}
        self._transaction_rollbacks: dict[str, _ProjectRollback] = {}
        self._transaction_failed: set[str] = set()
        self._pending: dict[str, TableChangeSet] = {}

    @property
    def projects(self) -> Mapping[str, ProjectTableDocument]:
        """Expose project membership without permitting mapping mutation."""

        return MappingProxyType(self._projects)

    def clear(self) -> None:
        """Remove all owned entries and detach their callbacks."""

        project_ids = list(self._projects)
        self._projects.clear()
        self._undo_stacks.clear()
        self._unpublished_projects.clear()
        for project_id in project_ids:
            self.transaction_committed.emit(TableChangeSet(
                project_id=project_id,
                metadata_changed=True,
                structure_changed=True,
                reason="clear",
            ))

    def create_project(self, name: str, first_sheet_name: str = "Sheet1",
                       project_id: str | None = None, *,
                       publish: bool = True) -> ProjectTableDocument:
        """Create project."""

        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("Project name must not be empty.")
        if self.project_by_name(cleaned, required=False) is not None:
            raise ValueError(f"Project already exists: {cleaned}")
        project = ProjectTableDocument.create(cleaned, first_sheet_name)
        if project_id is not None:
            project.id = project_id
        self.register_project(project, publish=publish)
        return project

    def register_project(
        self,
        project: ProjectTableDocument,
        *,
        publish: bool = True,
    ) -> None:
        """Register project."""

        if project.id in self._projects:
            raise ValueError(f"Project id already exists: {project.id}")
        if self.project_by_name(project.name, required=False) is not None:
            raise ValueError(f"Project already exists: {project.name}")
        self._projects[project.id] = project
        stack = QUndoStack(self)
        stack.setUndoLimit(50)
        self._undo_stacks[project.id] = stack
        if publish:
            self.publish_project_added(project.id)
        else:
            self._unpublished_projects.add(project.id)

    def publish_project_added(self, project_id: str) -> None:
        """Publish a fully prepared project to repository observers."""

        self.project(project_id)
        self._unpublished_projects.discard(project_id)
        self.transaction_committed.emit(TableChangeSet(
            project_id=project_id,
            metadata_changed=True,
            structure_changed=True,
            reason="project-added",
        ))

    def remove_project(
        self,
        project_id: str,
        *,
        publish: bool = True,
    ) -> ProjectTableDocument | None:
        """Remove project."""

        project = self._projects.pop(project_id, None)
        self._unpublished_projects.discard(project_id)
        stack = self._undo_stacks.pop(project_id, None)
        if stack is not None:
            stack.deleteLater()
        if project is not None and publish:
            self.transaction_committed.emit(TableChangeSet(
                project_id=project_id,
                metadata_changed=True,
                structure_changed=True,
                reason="project-removed",
            ))
        return project

    def project(self, project_id: str) -> ProjectTableDocument:
        """Return the requested project."""

        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project: {project_id}") from exc

    def project_by_name(self, name: str, required: bool = True) -> ProjectTableDocument | None:
        """Return the project with the requested display name."""

        normalized = str(name).strip().casefold()
        for project in self._projects.values():
            if project.name.casefold() == normalized:
                return project
        if required:
            raise KeyError(f"Unknown project: {name}")
        return None

    def sheet(self, project_id: str, sheet_id: str) -> SheetDocument:
        """Return the requested sheet."""

        project = self.project(project_id)
        try:
            return project.sheets[sheet_id]
        except KeyError as exc:
            raise KeyError(f"Unknown sheet: {sheet_id}") from exc

    def undo_stack(self, project_id: str) -> QUndoStack:
        """Return the undo stack for the requested project."""

        try:
            return self._undo_stacks[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project undo stack: {project_id}") from exc

    def push(self, project_id: str, command: QUndoCommand) -> bool:
        """Push an undoable table mutation onto the project stack."""

        self.undo_stack(project_id).push(command)
        return bool(getattr(command, "last_succeeded", False))

    def _capture_rollback(self, project_id: str) -> _ProjectRollback:
        project = self.project(project_id)
        return _ProjectRollback(
            project=project,
            state=deepcopy(project),
            sheets=dict(project.sheets),
            columns={
                sheet_id: {column.id: column for column in sheet.columns}
                for sheet_id, sheet in project.sheets.items()
            },
        )

    @staticmethod
    def _restore_rollback(rollback: _ProjectRollback) -> None:
        project = rollback.project
        state = rollback.state
        project.id = state.id
        project.name = state.name
        restored_sheets: "OrderedDict[str, SheetDocument]" = OrderedDict()
        for sheet_id, saved_sheet in state.sheets.items():
            sheet = rollback.sheets.get(sheet_id, saved_sheet)
            sheet.id = saved_sheet.id
            sheet.name = saved_sheet.name
            sheet.row_count = saved_sheet.row_count
            existing_columns = rollback.columns.get(sheet_id, {})
            restored_columns = []
            for saved_column in saved_sheet.columns:
                column = existing_columns.get(saved_column.id, saved_column)
                column.id = saved_column.id
                column.name = saved_column.name
                column.type = saved_column.type
                column.width = saved_column.width
                restored_columns.append(column)
            sheet.columns = restored_columns
            sheet.frame = saved_sheet.frame.copy(deep=True)
            restored_sheets[sheet_id] = sheet
        project.sheets.clear()
        project.sheets.update(restored_sheets)

    @contextmanager
    def transaction(
        self,
        project_id: str,
        *,
        rollback: bool = True,
    ) -> Iterator[None]:
        """Group changes and optionally restore exact document state on failure."""

        depth = self._transaction_depths.get(project_id, 0)
        if depth == 0 and rollback:
            self._transaction_rollbacks[project_id] = self._capture_rollback(
                project_id
            )
        self._transaction_depths[project_id] = depth + 1
        raised_here = False
        try:
            yield
        except BaseException:
            raised_here = True
            self._transaction_failed.add(project_id)
            raise
        finally:
            remaining = self._transaction_depths[project_id] - 1
            if remaining:
                self._transaction_depths[project_id] = remaining
            else:
                self._transaction_depths.pop(project_id, None)
                failed = project_id in self._transaction_failed
                self._transaction_failed.discard(project_id)
                rollback_state = self._transaction_rollbacks.pop(
                    project_id,
                    None,
                )
                if failed:
                    self._pending.pop(project_id, None)
                    if rollback_state is not None:
                        self._restore_rollback(rollback_state)
                    if not raised_here:
                        raise RuntimeError(
                            "Nested table transaction failed and was rolled back."
                        )
                else:
                    changes = self._pending.pop(project_id, None)
                    if (
                        changes is not None
                        and project_id not in self._unpublished_projects
                    ):
                        self.transaction_committed.emit(changes)

    @contextmanager
    def mutate(
        self,
        changes: Callable[[], TableChangeSet] | TableChangeSet,
        *,
        project_id: str | None = None,
        rollback: bool = True,
    ) -> Iterator[ProjectTableDocument]:
        """Run one document mutation and publish its ChangeSet exactly once."""

        if callable(changes):
            if project_id is None:
                raise ValueError(
                    "Callable Table changes require a stable project_id."
                )
            resolved_project_id = str(project_id)
        elif isinstance(changes, TableChangeSet):
            resolved_project_id = changes.project_id
        else:
            raise TypeError("Table mutation requires a TableChangeSet.")
        project = self.project(resolved_project_id)
        with self.transaction(resolved_project_id, rollback=rollback):
            yield project
            resolved = changes() if callable(changes) else changes
            if not isinstance(resolved, TableChangeSet):
                raise TypeError("Table mutation did not produce a ChangeSet.")
            if resolved.project_id != resolved_project_id:
                raise ValueError("Table mutation ChangeSet project ID changed.")
            self._record_change(resolved)

    def _record_change(self, changes: TableChangeSet) -> None:
        """Queue an already successful mutation for outermost publication."""

        existing = self._pending.get(changes.project_id)
        if existing is None:
            self._pending[changes.project_id] = changes
        else:
            existing.merge(changes)
        if self._transaction_depths.get(changes.project_id, 0) == 0:
            pending = self._pending.pop(changes.project_id)
            if changes.project_id not in self._unpublished_projects:
                self.transaction_committed.emit(pending)

    def column_ref(self, project_id: str, sheet_id: str, column_id: str) -> ColumnRef:
        """Build a stable reference to the requested table column."""

        self.sheet(project_id, sheet_id).column(column_id)
        return ColumnRef(project_id, sheet_id, column_id)

    def has_ref(self, ref: ColumnRef | None) -> bool:
        """Return whether a column reference still resolves."""

        if ref is None:
            return False
        try:
            self.sheet(ref.project_id, ref.sheet_id).column(ref.column_id)
        except KeyError:
            return False
        return True

    def iter_column_refs(self, project_id: str | None = None,
                         allowed_types: Iterable[ColumnType] | None = None) -> Iterator[ColumnRef]:
        """Iterate over column refs."""

        allowed = set(allowed_types) if allowed_types is not None else None
        projects = self._projects.values() if project_id is None else (self.project(project_id),)
        for project in projects:
            for sheet in project.sheets.values():
                for column in sheet.columns:
                    if allowed is None or column.type in allowed:
                        yield ColumnRef(project.id, sheet.id, column.id)

    def ref_label(self, ref: ColumnRef) -> str:
        """Return the ref label."""

        project = self.project(ref.project_id)
        sheet = self.sheet(ref.project_id, ref.sheet_id)
        column = sheet.column(ref.column_id)
        return f"{project.name}/{sheet.name}/{column.name}"

    def series(self, ref: ColumnRef) -> pd.Series:
        """Return a copy of the series referenced by a column reference."""

        if not self.has_ref(ref):
            raise KeyError("Data column no longer exists.")
        return self.sheet(ref.project_id, ref.sheet_id).frame[ref.column_id].copy(
            deep=True
        )

    def line_pair(self, x_ref: ColumnRef, y_ref: ColumnRef) -> AlignedPair:
        """Return aligned numeric x/y data for two column references."""

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
        """Return whether two references resolve to aligned numeric data."""

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
        """Return a serializable snapshot of the current state."""

        return self.project(project_id).to_snapshot()

    def restore_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        publish: bool = True,
    ) -> ProjectTableDocument:
        """Restore snapshot."""

        project = ProjectTableDocument.from_snapshot(snapshot)
        self.register_project(project, publish=publish)
        return project
