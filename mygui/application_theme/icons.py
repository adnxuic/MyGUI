"""DPR-aware chrome icon cache. Implements ``ports.ThemeIconProvider``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from mygui.application_settings.models import Density
from mygui.resources import icon_directory, icon_path

from .models import EffectiveScheme, ThemeSnapshot
from .tokens import ICON_ROLES

_PREVIEW_FOLDERS = (
    "chart_images/",
    "style_images/",
    "layout_images/",
    "element_images/",
)
_BRAND_NAMES = frozenset({"matlab.svg", "app_icon.ico"})
_CHROME_TINT_TOKEN = "COLOR_TEXT_PRIMARY"
_ON_COMMAND_TOKEN = "COLOR_TEXT_ON_DARK"
_ON_ACCENT_TOKEN = "COLOR_TEXT_ON_DARK"


class IconRole(StrEnum):
    """How an icon participates in theme recoloring."""

    CHROME = "chrome"
    BRAND = "brand"
    PREVIEW = "preview"
    USER_DATA = "user_data"


@dataclass(frozen=True, slots=True)
class IconCacheKey:
    """source / role / logical size / scheme / density / DPR, plus a variant."""

    source: str
    role: IconRole
    logical_size: int
    scheme: EffectiveScheme
    density: Density
    dpr: float
    variant: str = ""


def normalize_icon_source(source: str) -> str:
    """Return a stable cache source using POSIX separators."""

    return str(source).replace("\\", "/")


def classify_icon_source(source: str) -> IconRole:
    """Classify a path as chrome (recolor) or original-color."""

    posix = normalize_icon_source(source)
    name = Path(posix).name.lower()
    if name in _BRAND_NAMES:
        return IconRole.BRAND
    lowered = posix.replace("\\", "/").lower()
    if any(folder in lowered for folder in _PREVIEW_FOLDERS):
        return IconRole.PREVIEW
    try:
        root = icon_directory().resolve()
        path = Path(posix)
        if path.is_absolute() and root not in path.resolve().parents and path.resolve() != root:
            return IconRole.USER_DATA
    except FileNotFoundError:
        return IconRole.USER_DATA
    return IconRole.CHROME


def resolve_device_pixel_ratio(widget: QWidget | None = None) -> float:
    """Return the widget, screen, or application device-pixel ratio."""

    if widget is not None:
        handle = widget.windowHandle()
        if handle is not None:
            return float(handle.devicePixelRatio())
        screen = widget.screen()
        if screen is not None:
            return float(screen.devicePixelRatio())
    app = QGuiApplication.instance()
    if app is not None:
        return float(app.devicePixelRatio())
    return 1.0


def icon_logical_size(button_px: int) -> int:
    """Chrome glyph size derived from the density button band."""

    return max(16, int(button_px) - 16)


def _round_dpr(dpr: float) -> float:
    return round(float(dpr), 3)


def iter_bundled_chrome_sources() -> tuple[str, ...]:
    """Return top-level bundled SVG paths that are monochrome chrome."""

    directory = icon_directory()
    sources: list[str] = []
    for path in sorted(directory.glob("*.svg")):
        if classify_icon_source(str(path)) is IconRole.CHROME:
            sources.append(str(path))
    return tuple(sources)


def _tint_for_role(snapshot: ThemeSnapshot, role: IconRole, variant: str) -> str | None:
    if role is not IconRole.CHROME:
        return None
    tokens = snapshot.tokens
    if variant in {"on_command", "unchecked_command"}:
        return str(tokens.get(_ON_COMMAND_TOKEN, "#f8fafc"))
    if variant in {"on_accent", "checked_accent"}:
        return str(tokens.get(_ON_ACCENT_TOKEN, "#f8fafc"))
    if variant in {"on_surface", "checked_surface"}:
        return str(tokens.get(_CHROME_TINT_TOKEN, "#1f2937"))
    return str(tokens.get(_CHROME_TINT_TOKEN, "#1f2937"))


class CachingThemeIconProvider:
    """Production icon provider: cache, recolor chrome, leave brand/preview."""

    def __init__(self) -> None:
        self._cache: dict[IconCacheKey, QIcon] = {}
        self._applied: dict[str, object] | None = None
        self.recolor_calls = 0
        self.hits = 0
        self.misses = 0

    def cache_key(
        self,
        source: str,
        role: IconRole,
        logical_size: int,
        scheme: EffectiveScheme,
        density: Density,
        dpr: float,
        variant: str = "",
    ) -> IconCacheKey:
        """Return the canonical cache key for one render."""

        return IconCacheKey(
            source=normalize_icon_source(source),
            role=role,
            logical_size=int(logical_size),
            scheme=scheme,
            density=density,
            dpr=_round_dpr(dpr),
            variant=str(variant),
        )

    def icon(
        self,
        source: str,
        *,
        snapshot: ThemeSnapshot,
        role: IconRole | None = None,
        logical_size: int | None = None,
        dpr: float | None = None,
        variant: str = "",
        widget: QWidget | None = None,
        angle: float = 0.0,
    ) -> QIcon:
        """Return a (possibly cached) themed icon. Chrome is recolored once per key."""

        resolved_role = role or classify_icon_source(source)
        size = int(
            logical_size
            if logical_size is not None
            else icon_logical_size(snapshot.metrics.button)
        )
        ratio = _round_dpr(
            dpr if dpr is not None else resolve_device_pixel_ratio(widget)
        )
        if angle:
            variant = f"{variant}|rot{int(angle)}" if variant else f"rot{int(angle)}"
        key = self.cache_key(
            source,
            resolved_role,
            size,
            snapshot.scheme,
            snapshot.preferences.density,
            ratio,
            variant,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        tint = _tint_for_role(snapshot, resolved_role, variant)
        rendered = self._render(
            source,
            size,
            ratio,
            tint=tint,
            angle=angle,
        )
        self._cache[key] = rendered
        return rendered

    def prerender(self, snapshot: ThemeSnapshot) -> object:
        """Render chrome icons for this snapshot with no widget side effects."""

        dprs = {1.0, resolve_device_pixel_ratio(None)}
        size = icon_logical_size(snapshot.metrics.button)
        icons: dict[IconCacheKey, QIcon] = {}
        previous_recolor = self.recolor_calls
        for source in iter_bundled_chrome_sources():
            for dpr in dprs:
                key = self.cache_key(
                    source,
                    IconRole.CHROME,
                    size,
                    snapshot.scheme,
                    snapshot.preferences.density,
                    dpr,
                )
                if key not in icons:
                    icons[key] = self._render(
                        source,
                        size,
                        _round_dpr(dpr),
                        tint=_tint_for_role(snapshot, IconRole.CHROME, ""),
                    )
        return {
            "scheme": snapshot.scheme.value,
            "density": snapshot.preferences.density.value,
            "icons": icons,
            "snapshot": snapshot,
            "recolor_calls": self.recolor_calls - previous_recolor,
            "icon_roles": dict(ICON_ROLES),
        }

    def apply(self, rendered: object) -> None:
        """Replace the live cache with prerendered icons and refresh windows."""

        payload = dict(rendered) if isinstance(rendered, dict) else {}
        icons = payload.get("icons") or {}
        self._cache = dict(icons)
        self._applied = payload
        snapshot = payload.get("snapshot")
        if snapshot is None:
            return
        from .runtime import default_theme_runtime
        from .windows import default_window_registry

        runtime = default_theme_runtime()
        runtime.snapshot = snapshot
        registry = default_window_registry()
        registry.apply_palette(snapshot.palette)
        registry.apply_icons(snapshot, self)

    def capture(self) -> object:
        """Return a memento of the currently applied icon cache."""

        return {
            "cache": dict(self._cache),
            "applied": None if self._applied is None else dict(self._applied),
            "recolor_calls": self.recolor_calls,
            "hits": self.hits,
            "misses": self.misses,
        }

    def restore(self, memento: object) -> None:
        """Restore icons from ``capture`` and replay them to live theme windows."""

        payload = dict(memento) if isinstance(memento, dict) else {}
        self._cache = dict(payload.get("cache") or {})
        applied = payload.get("applied")
        self._applied = None if applied is None else dict(applied)
        self.recolor_calls = int(payload.get("recolor_calls") or 0)
        self.hits = int(payload.get("hits") or 0)
        self.misses = int(payload.get("misses") or 0)
        snapshot = (
            self._applied.get("snapshot")
            if isinstance(self._applied, dict)
            else None
        ) or payload.get("snapshot")
        if snapshot is None:
            return
        from .runtime import default_theme_runtime
        from .windows import default_window_registry

        runtime = default_theme_runtime()
        runtime.snapshot = snapshot
        registry = default_window_registry()
        registry.apply_icons(snapshot, self)

    def invalidate(self) -> None:
        """Drop every cached pixmap. Scheme changes call this via ``apply``."""

        self._cache.clear()

    def _render(
        self,
        source: str,
        logical_size: int,
        dpr: float,
        *,
        tint: str | None,
        angle: float = 0.0,
    ) -> QIcon:
        path = source
        if not Path(path).is_file():
            try:
                path = icon_path(source)
            except FileNotFoundError:
                return QIcon()
        pixel = max(1, int(round(logical_size * dpr)))
        pixmap = QIcon(path).pixmap(QSize(pixel, pixel))
        if pixmap.isNull():
            pixmap = QPixmap(path)
            if pixmap.isNull():
                return QIcon(path)
            pixmap = pixmap.scaled(
                pixel,
                pixel,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if angle:
            pixmap = pixmap.transformed(QTransform().rotate(angle))
        if tint:
            self.recolor_calls += 1
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(tint))
            painter.end()
        pixmap.setDevicePixelRatio(dpr)
        return QIcon(pixmap)


def apply_icons_to_widget(
    widget: QWidget,
    snapshot: ThemeSnapshot,
    provider: CachingThemeIconProvider,
) -> None:
    """Ask a subscribed chrome widget and themed children to refresh icons."""

    seen: set[int] = set()

    def visit(target: QWidget) -> None:
        key = id(target)
        if key in seen:
            return
        seen.add(key)
        method = getattr(target, "apply_theme_icons", None)
        if callable(method):
            method(snapshot, provider)
        window_icon_source = target.property("themeChromeWindowIcon")
        if window_icon_source:
            target.setWindowIcon(
                provider.icon(
                    str(window_icon_source),
                    snapshot=snapshot,
                    widget=target,
                )
            )
        for child in target.findChildren(QWidget):
            visit(child)

    visit(widget)
