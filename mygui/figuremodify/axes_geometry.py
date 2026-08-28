"""Strict per-Axes geometry mode value types (schema v19).

Every persisted Axes carries one ``geometry`` record in ``data`` next to its
``subplot`` record.  ``grid`` mode means the Axes follows its Figure layout
GridSpec cell; ``manual`` mode pins the Axes to a Figure-normalized
[left, bottom, width, height] allocation rectangle and opts out of GridSpec
and automatic layout-engine projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any


class AxesGeometryMode(str, Enum):
    """Persisted per-Axes geometry projection mode."""

    GRID = "grid"
    MANUAL = "manual"


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid Axes geometry {path}: expected number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(
            f"Invalid Axes geometry {path}: expected finite number."
        )
    return result


def normalize_geometry_bounds(
    value: Any,
    path: str = "bounds",
) -> tuple[float, float, float, float]:
    """Validate and normalize one manual geometry allocation rectangle."""

    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(
            f"Invalid Axes geometry {path}: expected "
            "[left, bottom, width, height]."
        )
    if len(value) != 4:
        raise ValueError(
            f"Invalid Axes geometry {path}: expected exactly four values."
        )
    left, bottom, width, height = (
        _finite_number(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    )
    if left < 0 or bottom < 0:
        raise ValueError(
            f"Invalid Axes geometry {path}: left and bottom must be >= 0."
        )
    if width <= 0 or height <= 0:
        raise ValueError(
            f"Invalid Axes geometry {path}: width and height must be > 0."
        )
    if left + width > 1 or bottom + height > 1:
        raise ValueError(
            f"Invalid Axes geometry {path}: the rectangle must fit inside "
            "the unit Figure."
        )
    return (
        round(left, 6),
        round(bottom, 6),
        round(width, 6),
        round(height, 6),
    )


@dataclass(frozen=True, slots=True)
class AxesGeometrySpec:
    """One validated per-Axes geometry value."""

    mode: AxesGeometryMode
    bounds: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        mode = AxesGeometryMode(self.mode)
        object.__setattr__(self, "mode", mode)
        if mode is AxesGeometryMode.GRID:
            if self.bounds is not None:
                raise ValueError("Grid Axes geometry must not carry bounds.")
            return
        object.__setattr__(
            self,
            "bounds",
            normalize_geometry_bounds(self.bounds),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the strict persisted wire shape."""

        if self.mode is AxesGeometryMode.GRID:
            return {"mode": AxesGeometryMode.GRID.value}
        return {
            "mode": AxesGeometryMode.MANUAL.value,
            "bounds": [float(value) for value in self.bounds or ()],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AxesGeometrySpec":
        """Parse one strictly shaped persisted geometry record."""

        if not isinstance(value, dict):
            raise ValueError("Axes geometry must be an object.")
        mode = value.get("mode")
        if mode == AxesGeometryMode.GRID.value:
            if set(value) != {"mode"}:
                raise ValueError(
                    "Grid Axes geometry must contain only mode."
                )
            return cls(AxesGeometryMode.GRID)
        if mode == AxesGeometryMode.MANUAL.value:
            if set(value) != {"mode", "bounds"}:
                raise ValueError(
                    "Manual Axes geometry must contain only mode and bounds."
                )
            return cls(
                AxesGeometryMode.MANUAL,
                bounds=normalize_geometry_bounds(value.get("bounds")),
            )
        raise ValueError(f"Unknown Axes geometry mode: {mode!r}.")


def grid_geometry_record() -> dict[str, Any]:
    """Return the canonical persisted grid-mode geometry record."""

    return {"mode": AxesGeometryMode.GRID.value}


def validate_geometry_record(value: Any, path: str) -> None:
    """Strictly validate one persisted geometry record at ``path``."""

    try:
        AxesGeometrySpec.from_dict(value)
    except ValueError as exc:
        raise ValueError(f"Invalid project field {path}: {exc}") from exc
