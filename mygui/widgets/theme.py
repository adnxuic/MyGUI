"""Shared visual tokens for the MyGUI widget layer.

The mappings keep Python-side semantics readable while ``QSS_TOKENS`` exposes
the flat, string-only values consumed by :func:`mygui.resources.load_qss_resource`.
QSS files use tokens in the form ``{{TOKEN_NAME}}``.
"""

from types import MappingProxyType


COLORS = MappingProxyType(
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
    }
)

SPACING = MappingProxyType(
    {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 24,
    }
)

RADII = MappingProxyType(
    {
        "sm": 4,
        "md": 6,
        "lg": 10,
    }
)

CONTROL_SIZES = MappingProxyType(
    {
        "command_row": 48,
        "tool_gallery": 72,
        "activity_rail": 44,
        "bottom_bar": 28,
        "focus_border": 2,
    }
)

FONT_FAMILIES = ("Segoe UI", "Microsoft YaHei", "sans-serif")
FONT_SIZE_PT = 9


QSS_TOKENS = MappingProxyType(
    {
        "COLOR_CONTENT_BACKGROUND": COLORS["content_background"],
        "COLOR_SURFACE": COLORS["surface"],
        "COLOR_COMMAND_BACKGROUND": COLORS["command_background"],
        "COLOR_STATUS_BACKGROUND": COLORS["status_background"],
        "COLOR_TEXT_PRIMARY": COLORS["text_primary"],
        "COLOR_TEXT_ON_DARK": COLORS["text_on_dark"],
        "COLOR_TEXT_MUTED_ON_DARK": COLORS["text_muted_on_dark"],
        "COLOR_ACCENT": COLORS["accent"],
        "COLOR_ACCENT_HOVER": COLORS["accent_hover"],
        "COLOR_ACCENT_SOFT": COLORS["accent_soft"],
        "COLOR_FOCUS": COLORS["focus"],
        "COLOR_SUCCESS": COLORS["success"],
        "COLOR_WARNING": COLORS["warning"],
        "COLOR_ERROR": COLORS["error"],
        "COLOR_BORDER": COLORS["border"],
        "COLOR_BORDER_STRONG": COLORS["border_strong"],
        "COLOR_HOVER_LIGHT": COLORS["hover_light"],
        "COLOR_SURFACE_ALT": COLORS["surface_alt"],
        "COLOR_TEXT_MUTED": COLORS["text_muted"],
        "COLOR_COMMAND_HOVER": COLORS["command_hover"],
        "COLOR_SEPARATOR": COLORS["separator"],
        "SPACE_XS": str(SPACING["xs"]),
        "SPACE_SM": str(SPACING["sm"]),
        "SPACE_MD": str(SPACING["md"]),
        "SPACE_LG": str(SPACING["lg"]),
        "SPACE_XL": str(SPACING["xl"]),
        "RADIUS_SM": str(RADII["sm"]),
        "RADIUS_MD": str(RADII["md"]),
        "RADIUS_LG": str(RADII["lg"]),
        "SIZE_COMMAND_ROW": str(CONTROL_SIZES["command_row"]),
        "SIZE_TOOL_GALLERY": str(CONTROL_SIZES["tool_gallery"]),
        "SIZE_ACTIVITY_RAIL": str(CONTROL_SIZES["activity_rail"]),
        "SIZE_BOTTOM_BAR": str(CONTROL_SIZES["bottom_bar"]),
        "SIZE_FOCUS_BORDER": str(CONTROL_SIZES["focus_border"]),
    }
)
