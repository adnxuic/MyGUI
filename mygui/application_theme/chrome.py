"""QPalette, QFont, and placeholder QSS used by the theme transaction."""

from __future__ import annotations

from typing import Mapping

from PySide6.QtGui import QColor, QFont, QPalette

from .models import ThemeSnapshot

UI_FONT_FAMILIES = ("Segoe UI", "Microsoft YaHei", "sans-serif")


def build_font(point_size: int) -> QFont:
    """Return the application chrome font. Does not mutate QApplication."""

    font = QFont()
    font.setFamilies(list(UI_FONT_FAMILIES))
    font.setPointSize(int(point_size))
    return font


def build_palette(tokens: Mapping[str, str]) -> QPalette:
    """Return a QPalette from snapshot tokens. Does not mutate QApplication."""

    palette = QPalette()
    window = QColor(tokens["COLOR_CONTENT_BACKGROUND"])
    base = QColor(tokens["COLOR_SURFACE"])
    alternate = QColor(tokens["COLOR_SURFACE_ALT"])
    text = QColor(tokens["COLOR_TEXT_PRIMARY"])
    muted = QColor(tokens["COLOR_TEXT_MUTED"])
    button = QColor(tokens["COLOR_SURFACE"])
    highlight = QColor(tokens["COLOR_ACCENT"])
    highlighted = QColor(tokens["COLOR_TEXT_ON_DARK"])
    link = QColor(tokens["COLOR_ACCENT"])
    tooltip_base = QColor(tokens["COLOR_SURFACE"])
    tooltip_text = QColor(tokens["COLOR_TEXT_PRIMARY"])

    def set_role(role: QPalette.ColorRole, color: QColor) -> None:
        palette.setColor(QPalette.ColorGroup.Active, role, color)
        palette.setColor(QPalette.ColorGroup.Inactive, role, color)

    set_role(QPalette.ColorRole.Window, window)
    set_role(QPalette.ColorRole.WindowText, text)
    set_role(QPalette.ColorRole.Base, base)
    set_role(QPalette.ColorRole.AlternateBase, alternate)
    set_role(QPalette.ColorRole.Text, text)
    set_role(QPalette.ColorRole.Button, button)
    set_role(QPalette.ColorRole.ButtonText, text)
    set_role(QPalette.ColorRole.Highlight, highlight)
    set_role(QPalette.ColorRole.HighlightedText, highlighted)
    set_role(QPalette.ColorRole.Link, link)
    set_role(QPalette.ColorRole.LinkVisited, link)
    set_role(QPalette.ColorRole.ToolTipBase, tooltip_base)
    set_role(QPalette.ColorRole.ToolTipText, tooltip_text)
    set_role(QPalette.ColorRole.PlaceholderText, muted)
    set_role(QPalette.ColorRole.BrightText, highlighted)

    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.Window, window)
    palette.setColor(disabled, QPalette.ColorRole.WindowText, muted)
    palette.setColor(disabled, QPalette.ColorRole.Base, base)
    palette.setColor(disabled, QPalette.ColorRole.Text, muted)
    palette.setColor(disabled, QPalette.ColorRole.Button, button)
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, muted)
    palette.setColor(disabled, QPalette.ColorRole.PlaceholderText, muted)
    return palette


def render_placeholder_application_qss(snapshot: ThemeSnapshot) -> str:
    """Minimal app stylesheet so this phase can apply palette/font/QSS tokens."""

    content = snapshot.tokens["COLOR_CONTENT_BACKGROUND"]
    text = snapshot.tokens["COLOR_TEXT_PRIMARY"]
    accent = snapshot.tokens["COLOR_ACCENT"]
    return (
        f"/* mygui-theme:{snapshot.scheme.value} */\n"
        f"QWidget {{ background-color: {content}; color: {text}; }}\n"
        f"QWidget:focus {{ border-color: {accent}; }}"
    )


def render_placeholder_resource_qss(resource: str, snapshot: ThemeSnapshot) -> str:
    """Placeholder local QSS. SubAgent B replaces this with bundled documents."""

    return f"/* mygui-theme-resource:{resource}:{snapshot.scheme.value} */"
