"""Resolve New Figure size and document DPI for first-time creation.

Style creation and first-time text/Excel import consume this adapter. Project
restore and schema v15 open must not call it. Do not cache a settings snapshot
here; callers read ``NewFigureDefaultsProvider.current()`` at use time.
"""

from __future__ import annotations

from .models import NewFigureSettings
from .ports import NewFigureDefaultsProvider

BUILTIN_FIGURE_WIDTH_IN = 6.4
BUILTIN_FIGURE_HEIGHT_IN = 4.8
BUILTIN_DOCUMENT_DPI = 100.0


class FixedNewFigureDefaults:
    """Narrow adapter that always returns one ``NewFigureSettings`` value.

    Tests and the composition root may inject this. It is not the settings
    service and does not retain a live snapshot copy beyond the given value.
    """

    def __init__(self, settings: NewFigureSettings) -> None:
        self._settings = settings

    def current(self) -> NewFigureSettings:
        return self._settings


def resolve_new_figure_defaults(
    provider: NewFigureDefaultsProvider | None = None,
    *,
    width: float | None = None,
    height: float | None = None,
    dpi: float | None = None,
) -> NewFigureSettings:
    """Apply explicit input > application defaults > built-in defaults."""

    applied = NewFigureSettings(
        width_in=BUILTIN_FIGURE_WIDTH_IN,
        height_in=BUILTIN_FIGURE_HEIGHT_IN,
        document_dpi=BUILTIN_DOCUMENT_DPI,
    )
    if provider is not None:
        applied = provider.current()
    return NewFigureSettings(
        width_in=applied.width_in if width is None else float(width),
        height_in=applied.height_in if height is None else float(height),
        document_dpi=applied.document_dpi if dpi is None else float(dpi),
    )


def format_new_figure_field(value: float) -> str:
    """Format a width, height, or DPI value for the Style creation fields."""

    return f"{float(value):.10g}"
