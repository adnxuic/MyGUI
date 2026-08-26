"""Build sorted, masked 2D field grids from long-table XYZ columns."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

import numpy as np

from mygui.resource_limits import load_resource_limits


class Field2DGridError(ValueError):
    """Reject a FIELD_2D grid that cannot be submitted."""


@dataclass(frozen=True, slots=True)
class Field2DGrid:
    """Ascending X/Y centers and a ``Z[y_index, x_index]`` masked array."""

    x: np.ndarray
    y: np.ndarray
    z: np.ma.MaskedArray
    skipped_xy_count: int
    empty: bool

    @property
    def nx(self) -> int:
        return int(np.asarray(self.x).size)

    @property
    def ny(self) -> int:
        return int(np.asarray(self.y).size)

    @property
    def cell_count(self) -> int:
        return self.nx * self.ny

    def heatmap_extent(self) -> tuple[float, float, float, float]:
        """Return imshow extent from coordinate centers with ``origin='lower'``."""

        return heatmap_extent(self.x, self.y)


_HEATMAP_RTOL = 1e-7


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        if value is np.ma.masked:
            return True
    except (TypeError, ValueError):
        pass
    type_name = type(value).__name__
    if type_name in {"NAType", "NaTType"}:
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def _as_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        raise Field2DGridError("FIELD_2D coordinates must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise Field2DGridError("FIELD_2D values must be numeric.") from exc
    return result


def _trim_trailing_blank_rows(
    x_values: Iterable[Any],
    y_values: Iterable[Any],
    z_values: Iterable[Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    xs = list(x_values)
    ys = list(y_values)
    zs = list(z_values)
    length = min(len(xs), len(ys), len(zs))
    xs = xs[:length]
    ys = ys[:length]
    zs = zs[:length]
    end = length
    while end > 0 and _is_blank(xs[end - 1]) and _is_blank(ys[end - 1]) and _is_blank(zs[end - 1]):
        end -= 1
    return xs[:end], ys[:end], zs[:end]


def _unique_sorted(values: np.ndarray) -> np.ndarray:
    unique = np.unique(values)
    unique.sort()
    return unique.astype(float, copy=False)


def max_field_grid_cells(environ: Mapping[str, str] | None = None) -> int:
    """Return the configured ``nx * ny`` allocation budget."""

    return int(load_resource_limits(environ).max_field_grid_cells)


def is_equispaced(
    values: np.ndarray,
    *,
    rtol: float = _HEATMAP_RTOL,
) -> bool:
    """Return whether a multi-point axis is equally spaced within tolerance."""

    coords = np.asarray(values, dtype=float)
    if coords.size < 2:
        return True
    steps = np.diff(coords)
    step = float(steps[0])
    atol = 1e-12 * max(1.0, abs(step))
    return bool(np.allclose(steps, step, rtol=rtol, atol=atol))


def heatmap_extent(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    """Derive imshow extent from ascending cell centers."""

    x_coords = np.asarray(x, dtype=float)
    y_coords = np.asarray(y, dtype=float)
    if x_coords.size == 0 or y_coords.size == 0:
        raise Field2DGridError("Heatmap extent requires at least one X and Y center.")

    def bounds(coords: np.ndarray) -> tuple[float, float]:
        if coords.size == 1:
            center = float(coords[0])
            return center - 0.5, center + 0.5
        step = float(coords[1] - coords[0])
        return float(coords[0] - step / 2.0), float(coords[-1] + step / 2.0)

    x0, x1 = bounds(x_coords)
    y0, y1 = bounds(y_coords)
    return x0, x1, y0, y1


def centers_to_edges(centers: np.ndarray) -> np.ndarray:
    """Convert sorted cell centers to pcolormesh edges for flat shading."""

    coords = np.asarray(centers, dtype=float)
    if coords.size == 0:
        return np.empty(0, dtype=float)
    if coords.size == 1:
        center = float(coords[0])
        return np.array([center - 0.5, center + 0.5], dtype=float)
    deltas = np.diff(coords)
    first = float(coords[0] - deltas[0] / 2.0)
    last = float(coords[-1] + deltas[-1] / 2.0)
    mids = coords[:-1] + deltas / 2.0
    return np.concatenate(([first], mids, [last]))


def build_field_grid(
    x_values: Iterable[Any],
    y_values: Iterable[Any],
    z_values: Iterable[Any],
    *,
    max_cells: int | None = None,
    require_equispaced: bool = False,
    minimum_shape: tuple[int, int] = (1, 1),
) -> Field2DGrid:
    """Build one ascending masked grid from long-table XYZ rows.

    Duplicate ``(X, Y)`` coordinates are rejected. Missing or non-finite X/Y
    rows are skipped. Missing or non-finite Z values are masked. Trailing
    all-blank rows are ignored before those rules apply.
    """

    xs, ys, zs = _trim_trailing_blank_rows(x_values, y_values, z_values)
    skipped = 0
    points: list[tuple[float, float, float | None]] = []
    seen: set[tuple[float, float]] = set()
    for x_raw, y_raw, z_raw in zip(xs, ys, zs):
        x_value = _as_float(x_raw)
        y_value = _as_float(y_raw)
        if x_value is None or y_value is None or not math.isfinite(x_value) or not math.isfinite(y_value):
            skipped += 1
            continue
        key = (x_value, y_value)
        if key in seen:
            raise Field2DGridError(
                "Duplicate (X, Y) coordinates are not allowed; FIELD_2D "
                "does not interpolate repeats."
            )
        seen.add(key)
        z_value = _as_float(z_raw)
        if z_value is None or not math.isfinite(z_value):
            points.append((x_value, y_value, None))
        else:
            points.append((x_value, y_value, z_value))

    if not points:
        return Field2DGrid(
            np.empty(0, dtype=float),
            np.empty(0, dtype=float),
            np.ma.masked_all((0, 0), dtype=float),
            skipped,
            True,
        )

    x_coords = _unique_sorted(np.array([item[0] for item in points], dtype=float))
    y_coords = _unique_sorted(np.array([item[1] for item in points], dtype=float))
    nx = int(x_coords.size)
    ny = int(y_coords.size)
    budget = max_field_grid_cells() if max_cells is None else int(max_cells)
    if budget < 1:
        raise Field2DGridError("FIELD_2D grid cell budget must be positive.")
    if nx * ny > budget:
        raise Field2DGridError(
            f"FIELD_2D grid {nx} by {ny} exceeds the configured cell budget "
            f"of {budget}."
        )
    if require_equispaced:
        if not is_equispaced(x_coords) or not is_equispaced(y_coords):
            raise Field2DGridError(
                "Heatmap X and Y coordinates must be equally spaced."
            )

    z_grid = np.ma.masked_all((ny, nx), dtype=float)
    x_index = {float(value): index for index, value in enumerate(x_coords)}
    y_index = {float(value): index for index, value in enumerate(y_coords)}
    drawable = False
    for x_value, y_value, z_value in points:
        if z_value is None:
            continue
        z_grid[y_index[y_value], x_index[x_value]] = z_value
        drawable = True

    min_ny, min_nx = minimum_shape
    empty = (
        not drawable
        or ny < int(min_ny)
        or nx < int(min_nx)
    )
    return Field2DGrid(x_coords, y_coords, z_grid, skipped, empty)
