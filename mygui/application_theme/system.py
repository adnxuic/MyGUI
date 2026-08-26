"""System color-scheme resolution for PySide6 6.7.1 QStyleHints."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette

from .models import EffectiveScheme, ThemeMode
from .tokens import relative_luminance

_UNKNOWN = Qt.ColorScheme.Unknown
_LIGHT = Qt.ColorScheme.Light
_DARK = Qt.ColorScheme.Dark
_LUMINANCE_LIGHT_FLOOR = 0.5


def coerce_color_scheme(value: object) -> Qt.ColorScheme:
    """Return a Qt.ColorScheme, treating unknown values as Unknown."""

    if isinstance(value, Qt.ColorScheme):
        return value
    try:
        return Qt.ColorScheme(int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _UNKNOWN


def scheme_from_palette(palette: QPalette) -> EffectiveScheme:
    """Resolve Unknown System from native Window luminance captured at startup."""

    color = QColor(
        palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
    )
    luminance = relative_luminance(color.name(QColor.NameFormat.HexRgb))
    if luminance >= _LUMINANCE_LIGHT_FLOOR:
        return EffectiveScheme.LIGHT
    return EffectiveScheme.DARK


def resolve_effective_scheme(
    mode: ThemeMode,
    color_scheme: object,
    unknown_fallback: EffectiveScheme,
) -> EffectiveScheme:
    """Resolve ThemeMode against QStyleHints.colorScheme."""

    if mode is ThemeMode.LIGHT:
        return EffectiveScheme.LIGHT
    if mode is ThemeMode.DARK:
        return EffectiveScheme.DARK
    scheme = coerce_color_scheme(color_scheme)
    if scheme == _LIGHT:
        return EffectiveScheme.LIGHT
    if scheme == _DARK:
        return EffectiveScheme.DARK
    return unknown_fallback


class FakeStyleHints(QObject):
    """Injectable stand-in for ``QStyleHints`` (tests and headless stubs)."""

    colorSchemeChanged = Signal(Qt.ColorScheme)

    def __init__(
        self,
        scheme: Qt.ColorScheme = Qt.ColorScheme.Unknown,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scheme = coerce_color_scheme(scheme)

    def colorScheme(self) -> Qt.ColorScheme:
        return self._scheme

    def set_color_scheme(self, scheme: Qt.ColorScheme) -> None:
        """Assign and emit ``colorSchemeChanged`` like the real Qt signal."""

        self._scheme = coerce_color_scheme(scheme)
        self.colorSchemeChanged.emit(self._scheme)
