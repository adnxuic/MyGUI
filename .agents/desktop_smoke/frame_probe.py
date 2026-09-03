"""Trusted native frame timings: dispatch, first paint, and settle.

Timed intervals never call a fixed-duration ``pump()``. A 2 second timeout
fails the probe. Existing aggregate timing keys stay as compatibility aliases.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

FRAME_PROBE_TIMEOUT_S = 2.0
SETTLE_IDLE_LOOPS = 2
TIMING_SCHEMA_VERSION = 2
_PAINT_EVENTS = frozenset(
    {
        QEvent.Type.Paint,
        QEvent.Type.UpdateRequest,
    }
)
_BUSY_EVENTS = frozenset(
    {
        QEvent.Type.Paint,
        QEvent.Type.UpdateRequest,
        QEvent.Type.LayoutRequest,
    }
)


class FrameProbeTimeout(RuntimeError):
    """Raised when dispatch/paint/settle did not finish within two seconds."""


@dataclass
class FrameSample:
    dispatch_ms: float
    first_paint_ms: float
    settle_ms: float
    paint_region: str
    painted: bool


class _RegionFilter(QObject):
    """Watch Paint / UpdateRequest / LayoutRequest on one widget subtree."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.target_ids: set[int] = set()
        self.saw_paint = False
        self.saw_busy = False
        self.first_paint_at: float | None = None

    def reset_cycle(self) -> None:
        self.saw_busy = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if id(watched) not in self.target_ids:
            return False
        event_type = event.type()
        if event_type in _BUSY_EVENTS:
            self.saw_busy = True
        if event_type in _PAINT_EVENTS:
            self.saw_paint = True
            if self.first_paint_at is None:
                self.first_paint_at = time.perf_counter()
        return False


def _alive(widget: QWidget | None) -> QWidget | None:
    if widget is None:
        return None
    try:
        widget.objectName()
    except RuntimeError:
        return None
    return widget


def _is_matplotlib_canvas(widget: QWidget) -> bool:
    """Matplotlib canvas paints are out of chrome/Inspector timing regions."""

    return "FigureCanvas" in type(widget).__name__


def _region_ids(target: QWidget, *, visible_only: bool = False) -> set[int]:
    ids = {id(target)}
    try:
        for child in target.findChildren(QWidget):
            try:
                if _is_matplotlib_canvas(child):
                    continue
                if visible_only and not child.isVisible():
                    continue
            except RuntimeError:
                continue
            ids.add(id(child))
    except RuntimeError:
        pass
    return ids


def _paint_region_name(target: QWidget) -> str:
    name = str(target.objectName() or "").strip()
    if name:
        return name
    return type(target).__name__


def median_ms(samples: list[float]) -> float:
    """Return the middle value of ``samples``."""

    ordered = sorted(samples)
    return float(ordered[len(ordered) // 2])


def p95_ms(samples: list[float]) -> float:
    """Return the nearest-rank P95 of ``samples``."""

    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return float(ordered[index])


def measure_frame(
    target: QWidget,
    action: Callable[[], None],
    *,
    timeout_s: float = FRAME_PROBE_TIMEOUT_S,
    visible_only: bool = False,
) -> FrameSample:
    """Time one action against ``target`` without a fixed-duration pump."""

    widget = _alive(target)
    if widget is None:
        raise FrameProbeTimeout("Frame probe target was destroyed.")
    app = QApplication.instance()
    if app is None:
        raise FrameProbeTimeout("QApplication is missing.")

    watcher = _RegionFilter()
    watcher.target_ids = _region_ids(widget, visible_only=visible_only)
    app.installEventFilter(watcher)
    try:
        started = time.perf_counter()
        action()
        dispatch_at = time.perf_counter()
        dispatch_ms = (dispatch_at - started) * 1000.0
        deadline = started + max(0.001, float(timeout_s))
        idle_loops = 0
        settle_at = dispatch_at
        while True:
            now = time.perf_counter()
            if now > deadline:
                raise FrameProbeTimeout(
                    f"Frame probe timed out after {timeout_s:.1f}s "
                    f"on {_paint_region_name(widget)}."
                )
            watcher.reset_cycle()
            app.processEvents()
            settle_at = time.perf_counter()
            if watcher.saw_busy:
                idle_loops = 0
                continue
            idle_loops += 1
            if idle_loops >= SETTLE_IDLE_LOOPS:
                break
        if watcher.first_paint_at is None:
            first_paint_ms = dispatch_ms
            painted = False
        else:
            first_paint_ms = (watcher.first_paint_at - started) * 1000.0
            painted = True
        settle_ms = (settle_at - started) * 1000.0
        return FrameSample(
            dispatch_ms=dispatch_ms,
            first_paint_ms=first_paint_ms,
            settle_ms=settle_ms,
            paint_region=_paint_region_name(widget),
            painted=painted,
        )
    finally:
        app.removeEventFilter(watcher)


def wait_settle(
    target: QWidget,
    *,
    timeout_s: float = FRAME_PROBE_TIMEOUT_S,
    visible_only: bool = False,
) -> FrameSample:
    """Drain pending paints/layout for ``target`` without a business action."""

    return measure_frame(
        target,
        lambda: None,
        timeout_s=timeout_s,
        visible_only=visible_only,
    )


def measure_samples(
    target: QWidget,
    action: Callable[[], None],
    *,
    warmup: bool = True,
    count: int = 5,
    timeout_s: float = FRAME_PROBE_TIMEOUT_S,
    visible_only: bool = False,
) -> dict[str, Any]:
    """Warm up once, then collect ``count`` dispatch/first-paint/settle samples."""

    if warmup:
        measure_frame(
            target, action, timeout_s=timeout_s, visible_only=visible_only
        )
    samples = [
        measure_frame(
            target, action, timeout_s=timeout_s, visible_only=visible_only
        )
        for _ in range(int(count))
    ]
    dispatch = [item.dispatch_ms for item in samples]
    first_paint = [item.first_paint_ms for item in samples]
    settle = [item.settle_ms for item in samples]
    region = samples[0].paint_region if samples else _paint_region_name(target)
    return {
        "paintRegion": region,
        "dispatch_ms": {
            "samples": dispatch,
            "median": median_ms(dispatch),
            "p95": p95_ms(dispatch),
        },
        "first_paint_ms": {
            "samples": first_paint,
            "median": median_ms(first_paint),
            "p95": p95_ms(first_paint),
        },
        "settle_ms": {
            "samples": settle,
            "median": median_ms(settle),
            "p95": p95_ms(settle),
        },
    }


def staged_timing_payload(
    name: str,
    measured: dict[str, Any],
    *,
    alias_median_key: str,
    alias_p95_key: str | None = None,
) -> dict[str, Any]:
    """Return schema-v2 staged fields plus compatibility aliases."""

    settle = measured["settle_ms"]
    payload: dict[str, Any] = {
        name: measured,
        alias_median_key: settle["median"],
    }
    if alias_p95_key is not None:
        payload[alias_p95_key] = settle["p95"]
    return payload
