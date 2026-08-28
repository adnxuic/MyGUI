"""Fit input range specification and shared pre-fitting data selection.

The range selects which preprocessed rows feed a fitting engine.  Selection
always runs after X/Y preprocessing and invalid-row removal, includes both
endpoints, and never depends on row order.  The module is Qt-free so
Controllers, Services, and the template library can share one contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .data_preprocessing import PreprocessedPair


ALL_FIT_INPUT = "all"
BOUNDED_FIT_INPUT = "bounded"


def _finite_bound(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Fit input range {field_name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Fit input range {field_name} must be a finite number.")
    return number


@dataclass(frozen=True, slots=True)
class FitInputRangeSpec:
    """Persisted selection of the preprocessed rows used by one fit."""

    kind: str = ALL_FIT_INPUT
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in (ALL_FIT_INPUT, BOUNDED_FIT_INPUT):
            raise ValueError(f"Unknown fit input range kind: {self.kind!r}.")
        if self.kind == ALL_FIT_INPUT:
            if self.minimum is not None or self.maximum is not None:
                raise ValueError(
                    "All-data fit input range must not define bounds."
                )
            return
        object.__setattr__(self, "minimum", _finite_bound(self.minimum, "minimum"))
        object.__setattr__(self, "maximum", _finite_bound(self.maximum, "maximum"))
        if self.minimum >= self.maximum:
            raise ValueError("Fit input range minimum must be below maximum.")

    @property
    def is_bounded(self) -> bool:
        """Return whether this spec selects a closed X interval."""

        return self.kind == BOUNDED_FIT_INPUT

    def to_dict(self) -> dict[str, Any]:
        """Return the strict JSON representation used by component state."""

        if self.kind == ALL_FIT_INPUT:
            return {"kind": ALL_FIT_INPUT}
        return {
            "kind": BOUNDED_FIT_INPUT,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }

    @classmethod
    def from_dict(cls, value: "FitInputRangeSpec | Mapping[str, Any] | None") -> "FitInputRangeSpec":
        """Build a validated specification; ``None`` means all preprocessed data."""

        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Fit input range must be an object.")
        if "kind" not in value:
            raise ValueError("Fit input range must declare kind.")
        kind = value["kind"]
        if kind == ALL_FIT_INPUT:
            if set(value) != {"kind"}:
                raise ValueError(
                    "All-data fit input range must contain only kind."
                )
            return cls()
        if kind == BOUNDED_FIT_INPUT:
            if set(value) != {"kind", "minimum", "maximum"}:
                raise ValueError(
                    "Bounded fit input range must contain only kind, minimum, "
                    "and maximum."
                )
            return cls(
                kind=BOUNDED_FIT_INPUT,
                minimum=_finite_bound(value["minimum"], "minimum"),
                maximum=_finite_bound(value["maximum"], "maximum"),
            )
        raise ValueError(f"Unknown fit input range kind: {kind!r}.")


@dataclass(frozen=True, slots=True)
class SelectedFitInput:
    """Filtered fit inputs plus the drawable interval they imply."""

    x: np.ndarray
    y: np.ndarray
    excluded_count: int
    x_start: float
    x_stop: float


def select_fit_input_pair(
    pair: PreprocessedPair,
    spec: FitInputRangeSpec | Mapping[str, Any] | None = None,
    *,
    require_data: bool = True,
) -> SelectedFitInput:
    """Apply one input-range selection to an already preprocessed pair.

    ``pair`` must already carry preprocessing output and valid-row filtering;
    this function only removes rows outside the closed range.  With
    ``require_data`` the function rejects a selection without any row so the
    fit window and template execution can refuse to start a fit.
    """

    spec = FitInputRangeSpec.from_dict(spec)
    x_values = np.asarray(pair.x, dtype=float)
    y_values = np.asarray(pair.y, dtype=float)
    if spec.is_bounded and x_values.size:
        mask = (x_values >= float(spec.minimum)) & (x_values <= float(spec.maximum))
        filtered_x = x_values[mask]
        filtered_y = y_values[mask]
        excluded_count = int(x_values.size - filtered_x.size)
    else:
        filtered_x = x_values
        filtered_y = y_values
        excluded_count = 0
    if require_data and not filtered_x.size:
        raise ValueError(
            "Fit data range contains no valid preprocessed rows."
        )
    if spec.is_bounded:
        x_start = float(spec.minimum)
        x_stop = float(spec.maximum)
    elif filtered_x.size:
        x_start = float(np.min(filtered_x))
        x_stop = float(np.max(filtered_x))
    else:
        x_start = 0.0
        x_stop = 1.0
    return SelectedFitInput(
        filtered_x,
        filtered_y,
        excluded_count,
        x_start,
        x_stop,
    )
