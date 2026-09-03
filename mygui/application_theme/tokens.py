"""Light and Dark QSS token tables. Not a live ThemeService publisher.

Token names match bundled QSS placeholders (``{{COLOR_*}}``, ``{{SPACE_*}}``,
``{{RADIUS_*}}``, ``{{SIZE_*}}``) and the architecture roles in
``.agents/architecture/application-theme.md``. Callers pass a snapshot mapping
into ``load_qss_resource`` / ``bind_qss``; this module is frozen data.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .models import EffectiveScheme


# Architecture Dark core colors (closed).
_DARK_CORE = MappingProxyType(
    {
        "content": "#0F172A",
        "surface": "#1F2937",
        "surface_alt": "#273449",
        "command": "#0B1220",
        "text": "#F8FAFC",
        "muted": "#CBD5E1",
        "accent": "#2563EB",
        "focus": "#60A5FA",
        "border": "#475569",
        "error": "#FCA5A5",
    }
)

# Light keeps current mygui.widgets.theme semantic roles.
LIGHT_ROLE_COLORS = MappingProxyType(
    {
        "content_background": "#f3f5f7",
        "surface": "#ffffff",
        "command_background": "#111827",
        "status_background": "#343b48",
        "text_primary": "#1f2937",
        "text_on_dark": "#f8fafc",
        "text_muted_on_dark": "#cbd5e1",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_soft": "#dbeafe",
        "focus": "#60a5fa",
        "success": "#4ade80",
        "warning": "#fde047",
        "error": "#ff7d7d",
        "border": "#d1d5db",
        "border_strong": "#9ca3af",
        "hover_light": "#e5e7eb",
        "surface_alt": "#f3f4f6",
        "text_muted": "#4b5563",
        "command_hover": "#1f2937",
        "separator": "#94a3b8",
        "text_danger": "#B00020",
        "text_success": "#166534",
        "text_info": "#1d4ed8",
        "error_soft": "#fecaca",
    }
)

DARK_ROLE_COLORS = MappingProxyType(
    {
        "content_background": _DARK_CORE["content"],
        "surface": _DARK_CORE["surface"],
        "command_background": _DARK_CORE["command"],
        "status_background": _DARK_CORE["command"],
        "text_primary": _DARK_CORE["text"],
        "text_on_dark": _DARK_CORE["text"],
        "text_muted_on_dark": _DARK_CORE["muted"],
        "accent": _DARK_CORE["accent"],
        "accent_hover": "#3B82F6",
        "accent_soft": "#1E3A5F",
        "focus": _DARK_CORE["focus"],
        "success": "#4ADE80",
        "warning": "#FDE047",
        "error": _DARK_CORE["error"],
        "border": _DARK_CORE["border"],
        "border_strong": "#94A3B8",
        "hover_light": "#334155",
        "surface_alt": _DARK_CORE["surface_alt"],
        "text_muted": _DARK_CORE["muted"],
        "command_hover": _DARK_CORE["surface"],
        "separator": "#64748B",
        "text_danger": _DARK_CORE["error"],
        "text_success": "#86EFAC",
        "text_info": "#93C5FD",
        "error_soft": "#7F1D1D",
    }
)

LIGHT_SPACING = MappingProxyType(
    {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 24,
    }
)

LIGHT_RADII = MappingProxyType(
    {
        "sm": 4,
        "md": 6,
        "lg": 10,
    }
)

# Standard density (historical first-run chrome).
LIGHT_CONTROL_SIZES = MappingProxyType(
    {
        "command_row": 48,
        "tool_gallery": 60,
        "gallery_icon": 32,
        "activity_rail": 44,
        "bottom_bar": 28,
        "focus_border": 2,
        "button": 40,
        "control": 30,
        "table_row": 24,
        "table_header": 44,
        "tree": 26,
        "indicator": 16,
        "scrollbar": 10,
    }
)

FONT_FAMILIES = ("Segoe UI", "Microsoft YaHei", "sans-serif")
FONT_SIZE_PT = 9

# Resource-resolved icon URLs are merged by load_qss_resource, not snapshots.
ICON_QSS_TOKEN_NAMES = (
    "ICON_ARROW_DOWN",
    "ICON_ARROW_UP",
    "ICON_CHECK",
    "ICON_CHECK_INDETERMINATE",
)


def _ui_semantic_aliases(tokens: dict[str, str]) -> dict[str, str]:
    """Map shadcn-inspired names onto the existing Light/Dark chrome colors."""

    destructive = tokens["COLOR_TEXT_DANGER"]
    destructive_fg = tokens["COLOR_TEXT_ON_DARK"]
    if destructive.lower() == tokens["COLOR_ERROR"].lower():
        destructive_fg = tokens["COLOR_COMMAND_BACKGROUND"]
    return {
        "UI_BACKGROUND": tokens["COLOR_CONTENT_BACKGROUND"],
        "UI_FOREGROUND": tokens["COLOR_TEXT_PRIMARY"],
        "UI_CARD": tokens["COLOR_SURFACE"],
        "UI_CARD_FOREGROUND": tokens["COLOR_TEXT_PRIMARY"],
        "UI_POPOVER": tokens["COLOR_SURFACE"],
        "UI_POPOVER_FOREGROUND": tokens["COLOR_TEXT_PRIMARY"],
        "UI_PRIMARY": tokens["COLOR_ACCENT"],
        "UI_PRIMARY_FOREGROUND": tokens["COLOR_TEXT_ON_DARK"],
        "UI_PRIMARY_HOVER": tokens["COLOR_ACCENT_HOVER"],
        "UI_SECONDARY": tokens["COLOR_SURFACE_ALT"],
        "UI_SECONDARY_FOREGROUND": tokens["COLOR_TEXT_PRIMARY"],
        "UI_MUTED": tokens["COLOR_SURFACE_ALT"],
        "UI_MUTED_FOREGROUND": tokens["COLOR_TEXT_MUTED"],
        "UI_ACCENT": tokens["COLOR_ACCENT_SOFT"],
        "UI_ACCENT_FOREGROUND": tokens["COLOR_TEXT_PRIMARY"],
        "UI_DESTRUCTIVE": destructive,
        "UI_DESTRUCTIVE_FOREGROUND": destructive_fg,
        "UI_DESTRUCTIVE_SOFT": tokens["COLOR_ERROR_SOFT"],
        "UI_BORDER": tokens["COLOR_BORDER"],
        "UI_INPUT": tokens["COLOR_BORDER_STRONG"],
        "UI_RING": tokens["COLOR_FOCUS"],
        "UI_INFO": tokens["COLOR_TEXT_INFO"],
        "UI_SUCCESS": tokens["COLOR_TEXT_SUCCESS"],
        "UI_WARNING": tokens["COLOR_WARNING"],
        "UI_ERROR": tokens["COLOR_ERROR"],
    }


def _qss_tokens_from_roles(
    colors: Mapping[str, str],
    spacing: Mapping[str, int],
    radii: Mapping[str, int],
    sizes: Mapping[str, int],
) -> MappingProxyType[str, str]:
    button = int(sizes.get("button", 40))
    tokens = {
        "COLOR_CONTENT_BACKGROUND": colors["content_background"],
        "COLOR_SURFACE": colors["surface"],
        "COLOR_COMMAND_BACKGROUND": colors["command_background"],
        "COLOR_STATUS_BACKGROUND": colors["status_background"],
        "COLOR_TEXT_PRIMARY": colors["text_primary"],
        "COLOR_TEXT_ON_DARK": colors["text_on_dark"],
        "COLOR_TEXT_MUTED_ON_DARK": colors["text_muted_on_dark"],
        "COLOR_ACCENT": colors["accent"],
        "COLOR_ACCENT_HOVER": colors["accent_hover"],
        "COLOR_ACCENT_SOFT": colors["accent_soft"],
        "COLOR_FOCUS": colors["focus"],
        "COLOR_SUCCESS": colors["success"],
        "COLOR_WARNING": colors["warning"],
        "COLOR_ERROR": colors["error"],
        "COLOR_BORDER": colors["border"],
        "COLOR_BORDER_STRONG": colors["border_strong"],
        "COLOR_HOVER_LIGHT": colors["hover_light"],
        "COLOR_SURFACE_ALT": colors["surface_alt"],
        "COLOR_TEXT_MUTED": colors["text_muted"],
        "COLOR_COMMAND_HOVER": colors["command_hover"],
        "COLOR_SEPARATOR": colors["separator"],
        "COLOR_TEXT_DANGER": colors["text_danger"],
        "COLOR_TEXT_SUCCESS": colors["text_success"],
        "COLOR_TEXT_INFO": colors["text_info"],
        "COLOR_ERROR_SOFT": colors["error_soft"],
        "SPACE_XS": str(spacing["xs"]),
        "SPACE_SM": str(spacing["sm"]),
        "SPACE_MD": str(spacing["md"]),
        "SPACE_LG": str(spacing["lg"]),
        "SPACE_XL": str(spacing["xl"]),
        "RADIUS_SM": str(radii["sm"]),
        "RADIUS_MD": str(radii["md"]),
        "RADIUS_LG": str(radii["lg"]),
        "SIZE_COMMAND_ROW": str(sizes["command_row"]),
        "SIZE_CHANGE_BUTTON": str(max(1, sizes["command_row"] - 4)),
        "SIZE_TOOL_GALLERY": str(sizes["tool_gallery"]),
        "SIZE_TITLE_BAR": str(sizes["command_row"] + sizes["tool_gallery"]),
        "SIZE_GALLERY_ICON": str(sizes.get("gallery_icon", 32)),
        "SIZE_ACTIVITY_RAIL": str(sizes["activity_rail"]),
        "SIZE_BOTTOM_BAR": str(sizes["bottom_bar"]),
        "SIZE_FOCUS_BORDER": str(sizes["focus_border"]),
        "SIZE_BUTTON": str(button),
        "SIZE_BUTTON_SMALL": str(max(1, button - 8)),
        "SIZE_BUTTON_LARGE": str(button + 8),
        "SIZE_ICON_BUTTON": str(button),
        "SIZE_CONTROL": str(sizes.get("control", 30)),
        "SIZE_TABLE_ROW": str(sizes.get("table_row", 24)),
        "SIZE_TABLE_HEADER": str(sizes.get("table_header", 44)),
        "SIZE_TREE": str(sizes.get("tree", 26)),
        "SIZE_INDICATOR": str(sizes.get("indicator", 16)),
        "SIZE_RADIO_RADIUS": str(max(1, int(sizes.get("indicator", 16)) // 2)),
        "SIZE_SECTION_TITLE_TOP": str(spacing["xs"]),
        "SIZE_SECTION_TITLE_LEFT": str(
            int(spacing["sm"]) + int(sizes.get("indicator", 16)) + int(spacing["xs"])
        ),
        "SIZE_SECTION_MARGIN_TOP": str(
            int(spacing["xs"])
            + max(int(sizes.get("indicator", 16)), int(spacing["lg"]))
            + int(spacing["xs"])
        ),
        "SIZE_SCROLLBAR": str(sizes.get("scrollbar", 10)),
        "SIZE_SCROLLBAR_HANDLE": str(sizes.get("table_row", 24)),
        "SIZE_MENU_ITEM_PAD_V": str(spacing["xs"] + 2),
        "SIZE_MENU_ITEM_PAD_H": str(spacing["lg"] + spacing["sm"]),
        "SIZE_PROGRESS_MIN": str(spacing["sm"]),
        "SIZE_PROGRESS_MAX": str(spacing["md"]),
        "FONT_PT_BODY": str(FONT_SIZE_PT),
        "FONT_PT_PAGE_TITLE": str(FONT_SIZE_PT + 2),
        "FONT_PT_SECTION_TITLE": str(FONT_SIZE_PT),
        "FONT_PT_CAPTION": str(max(8, FONT_SIZE_PT - 1)),
        "FONT_WEIGHT_TITLE": "600",
        "FONT_WEIGHT_BODY": "400",
    }
    tokens.update(_ui_semantic_aliases(tokens))
    return MappingProxyType(tokens)


LIGHT_QSS_TOKENS = _qss_tokens_from_roles(
    LIGHT_ROLE_COLORS,
    LIGHT_SPACING,
    LIGHT_RADII,
    LIGHT_CONTROL_SIZES,
)
DARK_QSS_TOKENS = _qss_tokens_from_roles(
    DARK_ROLE_COLORS,
    LIGHT_SPACING,
    LIGHT_RADII,
    LIGHT_CONTROL_SIZES,
)

QSS_TOKEN_NAMES = tuple(LIGHT_QSS_TOKENS.keys())

# Body-text pairs (4.5:1) and focus/control-boundary pairs (3:1).
# COLOR_BORDER is an architecture hairline; control chrome uses COLOR_BORDER_STRONG.
CONTRAST_TEXT_PAIRS = (
    ("COLOR_TEXT_PRIMARY", "COLOR_CONTENT_BACKGROUND"),
    ("COLOR_TEXT_PRIMARY", "COLOR_SURFACE"),
    ("COLOR_TEXT_PRIMARY", "COLOR_SURFACE_ALT"),
    ("COLOR_TEXT_MUTED", "COLOR_SURFACE"),
    ("COLOR_TEXT_MUTED", "COLOR_CONTENT_BACKGROUND"),
    ("COLOR_TEXT_ON_DARK", "COLOR_COMMAND_BACKGROUND"),
    ("COLOR_TEXT_ON_DARK", "COLOR_STATUS_BACKGROUND"),
    ("COLOR_TEXT_MUTED_ON_DARK", "COLOR_STATUS_BACKGROUND"),
    ("COLOR_SUCCESS", "COLOR_STATUS_BACKGROUND"),
    ("COLOR_WARNING", "COLOR_STATUS_BACKGROUND"),
    ("COLOR_ERROR", "COLOR_STATUS_BACKGROUND"),
    ("COLOR_TEXT_DANGER", "COLOR_SURFACE"),
    ("COLOR_TEXT_SUCCESS", "COLOR_SURFACE"),
    ("COLOR_TEXT_INFO", "COLOR_SURFACE"),
    ("COLOR_TEXT_ON_DARK", "COLOR_ACCENT"),
)

CONTRAST_BOUNDARY_PAIRS = (
    ("COLOR_FOCUS", "COLOR_SURFACE"),
    ("COLOR_FOCUS", "COLOR_CONTENT_BACKGROUND"),
    ("COLOR_FOCUS", "COLOR_COMMAND_BACKGROUND"),
    ("COLOR_BORDER_STRONG", "COLOR_SURFACE"),
    ("COLOR_BORDER_STRONG", "COLOR_CONTENT_BACKGROUND"),
)


def qss_tokens_for_scheme(scheme: EffectiveScheme | str) -> MappingProxyType[str, str]:
    """Return the frozen QSS token table for Light or Dark."""

    resolved = EffectiveScheme(str(scheme).lower())
    if resolved is EffectiveScheme.DARK:
        return DARK_QSS_TOKENS
    return LIGHT_QSS_TOKENS


# --- Snapshot helpers used by ThemeService and chrome appliers ---

LIGHT_COLOR_TOKENS = MappingProxyType(
    {key: value for key, value in LIGHT_QSS_TOKENS.items() if key.startswith("COLOR_")}
)
DARK_CORE_TOKENS = MappingProxyType(
    {
        "content": "#0F172A",
        "surface": "#1F2937",
        "surface-alt": "#273449",
        "command": "#0B1220",
        "text": "#F8FAFC",
        "muted": "#CBD5E1",
        "accent": "#2563EB",
        "focus": "#60A5FA",
        "border": "#475569",
        "error": "#FCA5A5",
    }
)
ICON_ROLES = MappingProxyType(
    {
        "chrome": "monochrome",
        "brand": "original",
        "preview": "original",
        "user-data": "original",
    }
)
CONTRAST_PAIRS_BODY = (
    ("light", "COLOR_TEXT_PRIMARY", "COLOR_CONTENT_BACKGROUND"),
    ("light", "COLOR_TEXT_PRIMARY", "COLOR_SURFACE"),
    ("light", "COLOR_TEXT_PRIMARY", "COLOR_SURFACE_ALT"),
    ("light", "COLOR_TEXT_MUTED", "COLOR_CONTENT_BACKGROUND"),
    ("light", "COLOR_TEXT_MUTED", "COLOR_SURFACE"),
    ("dark", "COLOR_TEXT_PRIMARY", "COLOR_CONTENT_BACKGROUND"),
    ("dark", "COLOR_TEXT_PRIMARY", "COLOR_SURFACE"),
    ("dark", "COLOR_TEXT_PRIMARY", "COLOR_SURFACE_ALT"),
    ("dark", "COLOR_TEXT_MUTED", "COLOR_CONTENT_BACKGROUND"),
    ("dark", "COLOR_TEXT_MUTED", "COLOR_SURFACE"),
    ("dark", "COLOR_TEXT_ON_DARK", "COLOR_ACCENT"),
)
CONTRAST_PAIRS_FOCUS = (
    ("light", "COLOR_ACCENT", "COLOR_SURFACE"),
    ("light", "COLOR_FOCUS", "COLOR_COMMAND_BACKGROUND"),
    ("light", "COLOR_BORDER_STRONG", "COLOR_COMMAND_BACKGROUND"),
    ("dark", "COLOR_FOCUS", "COLOR_CONTENT_BACKGROUND"),
    ("dark", "COLOR_FOCUS", "COLOR_SURFACE"),
    ("dark", "COLOR_FOCUS", "COLOR_COMMAND_BACKGROUND"),
    ("dark", "COLOR_FOCUS", "COLOR_SURFACE_ALT"),
    ("dark", "COLOR_ACCENT", "COLOR_CONTENT_BACKGROUND"),
    ("dark", "COLOR_BORDER_STRONG", "COLOR_SURFACE"),
    ("dark", "COLOR_BORDER_STRONG", "COLOR_CONTENT_BACKGROUND"),
)


def _linearize(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """Return WCAG 2.1 relative luminance for ``#RRGGBB``."""

    text = hex_color.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) < 6:
        raise ValueError(f"Invalid hex color {hex_color!r}.")
    red = int(text[0:2], 16) / 255.0
    green = int(text[2:4], 16) / 255.0
    blue = int(text[4:6], 16) / 255.0
    return (
        0.2126 * _linearize(red)
        + 0.7152 * _linearize(green)
        + 0.0722 * _linearize(blue)
    )


def contrast_ratio(first: str, second: str) -> float:
    """Return WCAG contrast ratio between two hex colors."""

    lighter = max(relative_luminance(first), relative_luminance(second))
    darker = min(relative_luminance(first), relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def build_tokens(scheme, metrics, preferences) -> dict[str, str]:
    """Return snapshot tokens: QSS colors plus live density sizes."""

    dark = str(getattr(scheme, "value", scheme)).lower() == "dark"
    colors = dict(DARK_QSS_TOKENS if dark else LIGHT_QSS_TOKENS)
    roles = dict(DARK_CORE_TOKENS) if dark else {
        "content": LIGHT_QSS_TOKENS["COLOR_CONTENT_BACKGROUND"],
        "surface": LIGHT_QSS_TOKENS["COLOR_SURFACE"],
        "surface-alt": LIGHT_QSS_TOKENS["COLOR_SURFACE_ALT"],
        "command": LIGHT_QSS_TOKENS["COLOR_COMMAND_BACKGROUND"],
        "text": LIGHT_QSS_TOKENS["COLOR_TEXT_PRIMARY"],
        "muted": LIGHT_QSS_TOKENS["COLOR_TEXT_MUTED"],
        "accent": LIGHT_QSS_TOKENS["COLOR_ACCENT"],
        "focus": LIGHT_QSS_TOKENS["COLOR_FOCUS"],
        "border": LIGHT_QSS_TOKENS["COLOR_BORDER"],
        "error": LIGHT_QSS_TOKENS["COLOR_ERROR"],
    }
    colors.update(
        {
            **roles,
            "SCHEME": scheme.value,
            "DENSITY": preferences.density.value,
            "FONT_POINT_SIZE": str(preferences.font_pt),
            "SPACE_XS": str(metrics.spacing_xs),
            "SPACE_SM": str(metrics.spacing_sm),
            "SPACE_MD": str(metrics.spacing_md),
            "SPACE_LG": str(metrics.spacing_lg),
            "SPACE_XL": str(metrics.spacing_xl),
            "SIZE_COMMAND_ROW": str(metrics.command),
            "SIZE_CHANGE_BUTTON": str(max(1, metrics.command - 4)),
            "SIZE_TOOL_GALLERY": str(metrics.gallery),
            "SIZE_TITLE_BAR": str(metrics.command + metrics.gallery),
            "SIZE_GALLERY_ICON": str(metrics.gallery_icon),
            "SIZE_ACTIVITY_RAIL": str(metrics.rail),
            "SIZE_BOTTOM_BAR": str(metrics.bottom),
            "SIZE_BUTTON": str(metrics.button),
            "SIZE_TABLE_ROW": str(metrics.table_row),
            "SIZE_TABLE_HEADER": str(metrics.table_header),
            "SIZE_TREE": str(metrics.tree),
            "SIZE_CONTROL": str(metrics.control),
            "SIZE_INDICATOR": str(metrics.indicator),
            "SIZE_RADIO_RADIUS": str(max(1, metrics.indicator // 2)),
            "SIZE_SECTION_TITLE_TOP": str(metrics.section_title_top),
            "SIZE_SECTION_TITLE_LEFT": str(metrics.section_title_left),
            "SIZE_SECTION_MARGIN_TOP": str(metrics.section_margin_top),
            "SIZE_SCROLLBAR": str(metrics.scrollbar),
            "SIZE_SCROLLBAR_HANDLE": str(metrics.table_row),
            "SIZE_MENU_ITEM_PAD_V": str(metrics.spacing_xs + 2),
            "SIZE_MENU_ITEM_PAD_H": str(metrics.spacing_lg + metrics.spacing_sm),
            "SIZE_PROGRESS_MIN": str(metrics.spacing_sm),
            "SIZE_PROGRESS_MAX": str(metrics.spacing_md),
            "SIZE_BUTTON_SMALL": str(max(1, metrics.button - 8)),
            "SIZE_BUTTON_LARGE": str(metrics.button + 8),
            "SIZE_ICON_BUTTON": str(metrics.button),
            "FONT_PT_BODY": str(preferences.font_pt),
            "FONT_PT_PAGE_TITLE": str(preferences.font_pt + 2),
            "FONT_PT_SECTION_TITLE": str(preferences.font_pt),
            "FONT_PT_CAPTION": str(max(8, preferences.font_pt - 1)),
            "FONT_WEIGHT_TITLE": "600",
            "FONT_WEIGHT_BODY": "400",
        }
    )
    colors.update(_ui_semantic_aliases(colors))
    return colors
