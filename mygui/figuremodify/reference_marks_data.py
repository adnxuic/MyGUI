"""Resolve merged Reflection Positions from manual values and Table columns."""

from __future__ import annotations

from typing import Any

from mygui.database import ColumnRef, ColumnType, TableRepository
from mygui.database.table_document import is_missing
from mygui.figuremodify.components.errors import ComponentValidationError


def _normalize_required_ref(
    repository: TableRepository | None,
    project_id: str | None,
    position_ref: Any,
    *,
    field: str,
) -> ColumnRef:
    from mygui.figuremodify.components.controllers import normalize_position_ref

    normalized_ref = normalize_position_ref(position_ref)
    if normalized_ref is None:
        raise ComponentValidationError(
            f"Reflection {field} must be a column reference."
        )
    if repository is None or not project_id:
        raise ComponentValidationError(
            f"Reflection {field} requires the shared TableRepository."
        )
    ref = ColumnRef.from_dict(normalized_ref)
    if ref.project_id != str(project_id):
        raise ComponentValidationError(
            f"Reflection {field} must belong to the current project."
        )
    if not repository.has_ref(ref):
        raise ComponentValidationError(
            f"Reflection {field} does not resolve to a table column."
        )
    column = repository.sheet(ref.project_id, ref.sheet_id).column(ref.column_id)
    if column.type is not ColumnType.NUMBER:
        raise ComponentValidationError(
            f"Reflection {field} may only reference a Number column."
        )
    return ref


def number_column_finite_values(
    repository: TableRepository | None,
    project_id: str | None,
    position_ref: Any,
    *,
    field: str = "position_ref",
) -> list[float]:
    """Return finite Number-column values in row order, skipping empty cells."""

    from mygui.figuremodify.components.controllers import (
        normalize_reference_positions,
    )

    ref = _normalize_required_ref(
        repository,
        project_id,
        position_ref,
        field=field,
    )
    try:
        series = repository.series(ref)
    except Exception as exc:
        raise ComponentValidationError(
            f"Reflection {field} could not be read from the table."
        ) from exc
    values: list[float] = []
    for value in series.tolist():
        if is_missing(value):
            continue
        try:
            values.extend(normalize_reference_positions([value]))
        except ComponentValidationError as exc:
            raise ComponentValidationError(
                f"Reflection {field} values must be finite numbers."
            ) from exc
    return values


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
    if normalize_position_ref(position_ref) is None:
        return merged
    merged.extend(
        number_column_finite_values(
            repository,
            project_id,
            position_ref,
            field="position_ref",
        )
    )
    return merged


def between_table_range_extrema(
    repository: TableRepository | None,
    project_id: str | None,
    placement: Any,
) -> tuple[float, float]:
    """Return (lower_top, upper_bottom) data values for automatic placement."""

    from mygui.figuremodify.components.controllers import (
        normalize_reflection_placement,
    )

    normalized = normalize_reflection_placement(placement)
    if normalized["kind"] != "between_table_ranges":
        raise ComponentValidationError(
            "Automatic Reflection placement requires between_table_ranges."
        )
    lower_values = number_column_finite_values(
        repository,
        project_id,
        normalized["lower_ref"],
        field="placement.lower_ref",
    )
    if not lower_values:
        raise ComponentValidationError(
            "Automatic Reflection placement lower column has no finite values."
        )
    upper_bottoms: list[float] = []
    for index, item in enumerate(normalized["upper_refs"]):
        values = number_column_finite_values(
            repository,
            project_id,
            item,
            field=f"placement.upper_refs[{index}]",
        )
        if not values:
            raise ComponentValidationError(
                "Automatic Reflection placement upper column has no finite values."
            )
        upper_bottoms.append(min(values))
    lower_top = max(lower_values)
    upper_bottom = min(upper_bottoms)
    if not (lower_top < upper_bottom):
        raise ComponentValidationError(
            "The residual and main intensities do not leave a display gap "
            "for Reflection Positions."
        )
    return lower_top, upper_bottom
