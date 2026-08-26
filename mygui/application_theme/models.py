"""Immutable appearance types. ThemeMode and Density are settings-owned."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from PySide6.QtGui import QFont, QPalette

from mygui.application_settings.models import Density as Density, ThemeMode as ThemeMode
from mygui.application_settings.values import (
    DEFAULT_UI_FONT_PT,
    MAX_UI_FONT_PT,
    MIN_UI_FONT_PT,
)

from .errors import ThemeValidationError

__all__ = [
    "AppearancePreferences",
    "APPLY_STEPS",
    "Density",
    "DensityMetrics",
    "EffectiveScheme",
    "ThemeHealth",
    "ThemeMode",
    "ThemeSnapshot",
]


class EffectiveScheme(StrEnum):
    """Resolved Light/Dark chrome. System never appears here."""

    LIGHT = "light"
    DARK = "dark"


class ThemeHealth(StrEnum):
    """Whether the published snapshot still matches applied chrome."""

    OK = "ok"
    UNCERTAIN = "uncertain"


APPLY_STEPS = ("font", "palette", "qss", "metrics", "icons")


@dataclass(frozen=True, slots=True)
class AppearancePreferences:
    """Closed appearance inputs. ``font_pt`` is 8–16 inclusive."""

    mode: ThemeMode = ThemeMode.SYSTEM
    font_pt: int = DEFAULT_UI_FONT_PT
    density: Density = Density.STANDARD

    def __post_init__(self) -> None:
        try:
            mode = ThemeMode(self.mode)
        except ValueError as exc:
            raise ThemeValidationError(
                f"Theme mode must be one of {[item.value for item in ThemeMode]}."
            ) from exc
        try:
            density = Density(self.density)
        except ValueError as exc:
            raise ThemeValidationError(
                f"Density must be one of {[item.value for item in Density]}."
            ) from exc
        if isinstance(self.font_pt, bool) or not isinstance(self.font_pt, int):
            raise ThemeValidationError(
                f"UI font size must be an integer from {MIN_UI_FONT_PT} to "
                f"{MAX_UI_FONT_PT}."
            )
        if self.font_pt < MIN_UI_FONT_PT or self.font_pt > MAX_UI_FONT_PT:
            raise ThemeValidationError(
                f"UI font size must be between {MIN_UI_FONT_PT} and "
                f"{MAX_UI_FONT_PT}."
            )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "density", density)


@dataclass(frozen=True, slots=True)
class DensityMetrics:
    """Logical-pixel chrome sizes after the font-metric floor."""

    spacing_xs: int
    spacing_sm: int
    spacing_md: int
    spacing_lg: int
    spacing_xl: int
    rail: int
    button: int
    bottom: int
    command: int
    gallery: int
    table_row: int
    table_header: int
    tree: int
    control: int
    vertical_padding: int
    font_height: int


@dataclass(frozen=True, slots=True)
class ThemeSnapshot:
    """Published chrome: scheme, palette, font, metrics, QSS tokens, icon roles."""

    scheme: EffectiveScheme
    preferences: AppearancePreferences
    palette: QPalette
    font: QFont
    metrics: DensityMetrics
    tokens: Mapping[str, str]
    icon_roles: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "palette", QPalette(self.palette))
        object.__setattr__(self, "font", QFont(self.font))
        object.__setattr__(self, "tokens", MappingProxyType(dict(self.tokens)))
        object.__setattr__(self, "icon_roles", MappingProxyType(dict(self.icon_roles)))
