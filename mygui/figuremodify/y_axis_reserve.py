"""Apply Axes lower-Y visual reserve after ordinary autoscale.

The helper expands the Y interval toward the visual bottom in axis-transform
space so ordinary autoscale content occupies the upper ``1 - r`` of the final
display height.  It is idempotent when invoked after a fresh autoscale: it
never accumulates across repeated calls.
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.axes import Axes


Y_LOWER_RESERVE_ATTR = "_mygui_y_lower_reserve"
ORDINARY_YLIM_ATTR = "_mygui_y_ordinary_ylim"
APPLIED_YLIM_ATTR = "_mygui_y_reserved_ylim"


def read_y_lower_reserve(axes: Axes) -> float:
    """Return the Axes-owned lower-Y reserve ratio."""

    value = getattr(axes, Y_LOWER_RESERVE_ATTR, 0.0)
    try:
        ratio = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(ratio) or ratio <= 0.0:
        return 0.0
    return ratio


def write_y_lower_reserve(axes: Axes, value: float) -> None:
    """Store the Axes-owned lower-Y reserve ratio on the artist."""

    setattr(axes, Y_LOWER_RESERVE_ATTR, float(value))


def _ylim_tuple(axes: Axes) -> tuple[float, float]:
    y0, y1 = (float(value) for value in axes.get_ylim())
    return (y0, y1)


def _ylim_close(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return bool(np.allclose(left, right, rtol=1e-9, atol=1e-12))


def _axis_transform_values(transform, values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    try:
        out = transform.transform(array)
    except Exception:
        out = transform.transform(array.reshape(-1, 1))
    return np.asarray(out, dtype=float).reshape(-1)


def apply_y_lower_reserve(axes: Axes) -> None:
    """Expand the current Y interval toward the visual bottom by the stored ratio.

    Call this only after ordinary ``relim``/``autoscale_view``.  A ratio of
    ``0`` is a no-op.  Manual Y limits are left unchanged when autoscale is off.
    """

    if not isinstance(axes, Axes) or not axes.get_autoscaley_on():
        return
    ratio = read_y_lower_reserve(axes)
    if ratio <= 0.0 or ratio >= 0.9:
        return
    current = _ylim_tuple(axes)
    applied = getattr(axes, APPLIED_YLIM_ATTR, None)
    ordinary = getattr(axes, ORDINARY_YLIM_ATTR, None)
    if (
        isinstance(applied, tuple)
        and len(applied) == 2
        and isinstance(ordinary, tuple)
        and len(ordinary) == 2
        and _ylim_close(current, (float(applied[0]), float(applied[1])))
    ):
        y0, y1 = (float(ordinary[0]), float(ordinary[1]))
    else:
        y0, y1 = current
        setattr(axes, ORDINARY_YLIM_ATTR, current)
    transform = axes.yaxis.get_transform()
    try:
        t0, t1 = (
            float(value)
            for value in _axis_transform_values(transform, [y0, y1])
        )
        span = t1 - t0
        if not math.isfinite(span) or span == 0.0:
            return
        t_new = t0 - span * ratio / (1.0 - ratio)
        inverse = transform.inverted()
        new_bottom = float(_axis_transform_values(inverse, [t_new])[0])
    except Exception:
        return
    if not math.isfinite(new_bottom):
        return
    axes.set_ylim(new_bottom, y1, auto=None)
    setattr(axes, APPLIED_YLIM_ATTR, _ylim_tuple(axes))
