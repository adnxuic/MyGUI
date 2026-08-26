"""Light chrome aliases for remaining Python call sites.

Live appearance is published by ``ThemeBindingPort`` / ThemeService. These
mappings are the frozen Light semantic roles (same values as
``mygui.application_theme.tokens.LIGHT_*``). Do not treat this module as a
theme publisher.
"""

from mygui.application_theme.tokens import (
    FONT_FAMILIES,
    FONT_SIZE_PT,
    LIGHT_CONTROL_SIZES as CONTROL_SIZES,
    LIGHT_QSS_TOKENS as QSS_TOKENS,
    LIGHT_RADII as RADII,
    LIGHT_ROLE_COLORS as COLORS,
    LIGHT_SPACING as SPACING,
)

__all__ = [
    "COLORS",
    "CONTROL_SIZES",
    "FONT_FAMILIES",
    "FONT_SIZE_PT",
    "QSS_TOKENS",
    "RADII",
    "SPACING",
]
