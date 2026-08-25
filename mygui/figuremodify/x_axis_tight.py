"""Apply tight X limits after ordinary autoscale when xmargin is 0.

Matplotlib 3.9 ``autoscale_view`` still expands X through the major locator
when the Axes is not tight, even if ``xmargin`` is 0.  Call this after
``relim``/``autoscale_view`` so autoscale X matches the data interval.
Manual X limits are left unchanged when autoscale is off.
"""

from __future__ import annotations

import math

from matplotlib.axes import Axes


def apply_tight_xlim(axes: Axes) -> None:
    """Set view X limits to the data interval when X margin is exactly 0.

    Call this only after ordinary ``relim``/``autoscale_view``.  A non-zero
    ``xmargin`` is a no-op.  Manual X limits are left unchanged when autoscale
    is off.  Axis inversion is preserved.
    """

    if not isinstance(axes, Axes) or not axes.get_autoscalex_on():
        return
    try:
        margin = float(axes.get_xmargin())
    except (TypeError, ValueError):
        return
    if not math.isfinite(margin) or margin != 0.0:
        return
    try:
        left, right = (float(value) for value in axes.dataLim.intervalx)
    except (TypeError, ValueError):
        return
    x0 = min(left, right)
    x1 = max(left, right)
    if not math.isfinite(x0) or not math.isfinite(x1) or x0 == x1:
        return
    current = tuple(float(value) for value in axes.get_xlim())
    if current[0] > current[1]:
        axes.set_xlim(x1, x0, auto=None)
        return
    axes.set_xlim(x0, x1, auto=None)
