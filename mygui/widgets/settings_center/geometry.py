"""Logical-pixel placement for the Settings Center. Never persisted."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QWidget

INITIAL_WIDTH = 840
INITIAL_HEIGHT = 620
MINIMUM_WIDTH = 720
MINIMUM_HEIGHT = 520
NAV_PANE_WIDTH = 190
SCREEN_FRACTION = 0.90

AvailableGeometryProvider = Callable[[], QRect]


def constrain_to_available(
    available: QRect,
    *,
    preferred: tuple[int, int] = (INITIAL_WIDTH, INITIAL_HEIGHT),
    minimum: tuple[int, int] = (MINIMUM_WIDTH, MINIMUM_HEIGHT),
    fraction: float = SCREEN_FRACTION,
) -> QRect:
    """Center ``preferred`` in ``available``, clamped to ``fraction`` of the screen.

    When 90% of the available area is smaller than ``minimum``, the window
    shrinks to that 90% rectangle instead of forcing the minimum off-screen.
    Sizes are logical pixels.
    """

    max_w = max(1, int(available.width() * fraction))
    max_h = max(1, int(available.height() * fraction))
    pref_w, pref_h = preferred
    min_w, min_h = minimum
    width = min(pref_w, max_w)
    height = min(pref_h, max_h)
    if max_w >= min_w:
        width = max(width, min_w)
    if max_h >= min_h:
        height = max(height, min_h)
    width = max(1, min(width, max_w))
    height = max(1, min(height, max_h))
    x = available.x() + (available.width() - width) // 2
    y = available.y() + (available.height() - height) // 2
    return QRect(x, y, width, height)


def current_available_geometry(
    widget: QWidget,
    provider: AvailableGeometryProvider | None = None,
) -> QRect:
    """Return the current screen available geometry, or a stub from ``provider``."""

    if provider is not None:
        return QRect(provider())
    screen = widget.screen()
    if screen is None:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return QRect(0, 0, INITIAL_WIDTH, INITIAL_HEIGHT)
    return QRect(screen.availableGeometry())
