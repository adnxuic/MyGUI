"""Resolve merged Reflection Positions from manual values and a Table column."""

from __future__ import annotations

from typing import Any

from mygui.database import ColumnRef, ColumnType, TableRepository
from mygui.database.table_document import is_missing
from mygui.figuremodify.components.errors import ComponentValidationError


def merged_reference_positions(
    repository: TableRepository | None,
    project_id: str | None,
    positions: Any,
    position_ref: Any,
) -> list[float]:
    """Return manual positions followed by Number-column values in row order.

    Empty cells are skipped.  Duplicates and input order are preserved.
    Invalid refs and non-finite column values are rejected atomically.
    """

    from mygui.figuremodify.components.controllers import (
        normalize_position_ref,
        normalize_reference_positions,
    )

    merged = list(normalize_reference_positions(positions))
    normalized_ref = normalize_position_ref(position_ref)
    if normalized_ref is None:
        return merged
    if repository is None or not project_id:
        raise ComponentValidationError(
            "Reflection position_ref requires the shared TableRepository."
        )
    ref = ColumnRef.from_dict(normalized_ref)
    if ref.project_id != str(project_id):
        raise ComponentValidationError(
            "Reflection position_ref must belong to the current project."
        )
    if not repository.has_ref(ref):
        raise ComponentValidationError(
            "Reflection position_ref does not resolve to a table column."
        )
    column = repository.sheet(ref.project_id, ref.sheet_id).column(ref.column_id)
    if column.type is not ColumnType.NUMBER:
        raise ComponentValidationError(
            "Reflection position_ref may only reference a Number column."
        )
    try:
        series = repository.series(ref)
    except Exception as exc:
        raise ComponentValidationError(
            "Reflection position_ref could not be read from the table."
        ) from exc
    for value in series.tolist():
        if is_missing(value):
            continue
        try:
            merged.extend(normalize_reference_positions([value]))
        except ComponentValidationError as exc:
            raise ComponentValidationError(
                "Reflection position column values must be finite numbers."
            ) from exc
    return merged
