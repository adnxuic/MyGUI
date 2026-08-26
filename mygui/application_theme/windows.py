"""Weak theme subscribers for cached dialogs and parentless Canvas popouts."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

from .models import DensityMetrics, ThemeSnapshot

if TYPE_CHECKING:
    from .icons import CachingThemeIconProvider


def _alive_widget(widget: QWidget | None) -> QWidget | None:
    if widget is None:
        return None
    try:
        widget.objectName()
    except RuntimeError:
        return None
    return widget


def _propagate_palette(root: QWidget, palette: QPalette) -> None:
    """Copy ``palette`` onto descendants that do not own an explicit palette.

    ``QScrollArea`` viewports keep a resolved ``Window`` role across theme
    switches; they receive the snapshot palette without ``WA_SetPalette`` so
    later application/parent updates can still inherit.
    """

    copied = QPalette(palette)
    root = _alive_widget(root)
    if root is None:
        return
    try:
        descendants = list(root.findChildren(QWidget))
    except RuntimeError:
        return
    for child in descendants:
        target = _alive_widget(child)
        if target is None:
            continue
        try:
            if target.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
                continue
            target.setPalette(copied)
            target.setAttribute(Qt.WidgetAttribute.WA_SetPalette, False)
        except RuntimeError:
            continue
    scroll_roots: list[QWidget] = [root, *descendants]
    for candidate in scroll_roots:
        scroll = _alive_widget(candidate)
        if scroll is None or not isinstance(scroll, QAbstractScrollArea):
            continue
        try:
            viewport = scroll.viewport()
        except RuntimeError:
            continue
        viewport = _alive_widget(viewport)
        if viewport is None:
            continue
        try:
            viewport.setPalette(copied)
            viewport.setAttribute(Qt.WidgetAttribute.WA_SetPalette, False)
            QWidget.update(viewport)
        except Exception:  # noqa: BLE001
            continue


def _polish_widget_tree(root: QWidget, seen: set[int]) -> None:
    root = _alive_widget(root)
    if root is None:
        return
    targets = [root]
    try:
        targets.extend(root.findChildren(QWidget))
    except RuntimeError:
        return
    for target in targets:
        widget = _alive_widget(target)
        if widget is None:
            continue
        key = id(widget)
        if key in seen:
            continue
        seen.add(key)
        try:
            style = QWidget.style(widget)
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
            QWidget.update(widget)
        except Exception:  # noqa: BLE001
            continue


def refresh_chrome_style() -> None:
    """Invalidate native-style QSS caches on bound and subscribed chrome."""

    seen: set[int] = set()
    widgets: list[QWidget] = []
    try:
        from .qss import iter_bound_widgets

        widgets.extend(iter_bound_widgets())
    except ImportError:
        pass
    try:
        from .ports import binding_iter
        from .runtime import default_theme_runtime

        widgets.extend(
            widget for widget, _resource in binding_iter(default_theme_runtime().binding_port)
        )
    except ImportError:
        pass
    widgets.extend(default_window_registry().live_widgets())
    for widget in widgets:
        try:
            _polish_widget_tree(widget, seen)
        except Exception:  # noqa: BLE001
            continue


class ThemeWindowRegistry:
    """Weak widget registry. ``destroyed`` drops the entry; hidden windows stay."""

    def __init__(self) -> None:
        self._items: dict[int, Callable[[], QWidget | None]] = {}

    def register(self, widget: QWidget) -> None:
        """Subscribe ``widget`` and detach automatically on ``destroyed``."""

        if widget is None:
            return
        key = id(widget)
        if key in self._items:
            return
        self._items[key] = weakref.ref(widget)

        def _on_destroyed(*_args: object, widget_id: int = key) -> None:
            self._items.pop(widget_id, None)

        widget.destroyed.connect(_on_destroyed)

    def unregister(self, widget: QWidget) -> None:
        """Drop ``widget`` if it is still registered."""

        self._items.pop(id(widget), None)

    def contains(self, widget: QWidget) -> bool:
        """Return whether ``widget`` is a live subscriber."""

        ref = self._items.get(id(widget))
        return ref is not None and ref() is widget

    def live_widgets(self) -> Iterator[QWidget]:
        """Yield live subscribers, pruning dead weakrefs."""

        dead: list[int] = []
        for key, ref in self._items.items():
            widget = ref()
            if widget is None:
                dead.append(key)
                continue
            yield widget
        for key in dead:
            self._items.pop(key, None)

    def apply_palette(self, palette: QPalette) -> None:
        """Apply ``palette`` to hidden, visible, and parentless subscribers."""

        copied = QPalette(palette)
        for widget in self.live_widgets():
            widget.setPalette(copied)
            widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)
            _propagate_palette(widget, copied)

    def apply_metrics(self, metrics: DensityMetrics) -> None:
        from .participants import apply_metrics_to_widget

        for widget in self.live_widgets():
            apply_metrics_to_widget(widget, metrics)

    def apply_icons(
        self,
        snapshot: ThemeSnapshot,
        provider: CachingThemeIconProvider,
    ) -> None:
        from .icons import apply_icons_to_widget

        for widget in self.live_widgets():
            apply_icons_to_widget(widget, snapshot, provider)

    def apply_snapshot(
        self,
        snapshot: ThemeSnapshot,
        provider: CachingThemeIconProvider | None = None,
    ) -> None:
        """Apply palette, metrics, then icons. Does not cache Figure state."""

        self.apply_palette(snapshot.palette)
        self.apply_metrics(snapshot.metrics)
        if provider is not None:
            self.apply_icons(snapshot, provider)


_REGISTRY: ThemeWindowRegistry | None = None


def default_window_registry() -> ThemeWindowRegistry:
    """Return the process-wide chrome window registry."""

    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ThemeWindowRegistry()
    return _REGISTRY


def reset_window_registry_for_tests() -> ThemeWindowRegistry:
    """Replace the process registry. Tests must not leak destroyed connections."""

    global _REGISTRY
    _REGISTRY = ThemeWindowRegistry()
    return _REGISTRY


def subscribe_theme_window(widget: QWidget) -> None:
    """Register a cached dialog, Inspector host, Fit dialog, or Canvas popout.

    The registry holds only a weak QWidget reference. Callers must not store
    ``ComponentState``, selection IDs, or color-cycle cursors on the window.
    """

    registry = default_window_registry()
    registry.register(widget)
    from .runtime import default_theme_runtime

    runtime = default_theme_runtime()
    snapshot = runtime.snapshot
    if snapshot is None:
        return
    widget.setPalette(QPalette(snapshot.palette))
    widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)
    _propagate_palette(widget, snapshot.palette)
    from .participants import apply_metrics_to_widget

    apply_metrics_to_widget(widget, snapshot.metrics)
    if runtime.icon_provider is not None:
        from .icons import apply_icons_to_widget

        apply_icons_to_widget(widget, snapshot, runtime.icon_provider)
