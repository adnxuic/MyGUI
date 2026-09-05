"""Weak theme subscribers for cached dialogs and parentless Canvas popouts."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

from .models import DensityMetrics, ThemeSnapshot

if TYPE_CHECKING:
    from .icons import CachingThemeIconProvider

_CONSTRUCTION_DEPTH = 0
_SCREEN_HOOKS: dict[int, object] = {}


@dataclass(frozen=True)
class WindowPaletteMemento:
    """Transient, weak capture of one registered palette participant."""

    widget: Callable[[], QWidget | None]
    palette: QPalette
    explicitly_set: bool


def _alive_widget(widget: QWidget | None) -> QWidget | None:
    if widget is None:
        return None
    try:
        widget.objectName()
    except RuntimeError:
        return None
    return widget


def _direct_children(widget: QWidget) -> list[QWidget]:
    try:
        return list(
            widget.findChildren(
                QWidget,
                options=Qt.FindChildOption.FindDirectChildrenOnly,
            )
        )
    except RuntimeError:
        return []


def iter_widget_tree(
    roots: Iterable[QWidget],
    visited: set[int],
) -> Iterator[QWidget]:
    """Yield each live QWidget at most once via a direct-child DFS."""

    stack: list[QWidget] = []
    for root in roots:
        alive = _alive_widget(root)
        if alive is not None:
            stack.append(alive)
    while stack:
        widget = _alive_widget(stack.pop())
        if widget is None:
            continue
        key = id(widget)
        if key in visited:
            continue
        visited.add(key)
        yield widget
        children = _direct_children(widget)
        stack.extend(reversed(children))


def forest_roots(widgets: Iterable[QWidget]) -> list[QWidget]:
    """Return subscribers whose parent is not also in ``widgets``."""

    live = [_alive_widget(widget) for widget in widgets]
    live = [widget for widget in live if widget is not None]
    registered = {id(widget) for widget in live}
    roots: list[QWidget] = []
    for widget in live:
        parent = widget.parentWidget()
        covered = False
        ancestor = parent
        while ancestor is not None:
            if id(ancestor) in registered:
                covered = True
                break
            ancestor = ancestor.parentWidget()
        if not covered:
            roots.append(widget)
    return roots


def _propagate_palette_one(
    widget: QWidget,
    palette: QPalette,
    *,
    registered: bool,
) -> None:
    """Apply ``palette`` to one widget. Registered roots keep WA_SetPalette."""

    copied = QPalette(palette)
    try:
        if registered:
            widget.setPalette(copied)
            widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)
        elif not widget.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
            widget.setPalette(copied)
            widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, False)
        if isinstance(widget, QAbstractScrollArea):
            viewport = _alive_widget(widget.viewport())
            if viewport is not None:
                viewport.setPalette(copied)
                viewport.setAttribute(Qt.WidgetAttribute.WA_SetPalette, False)
                try:
                    if viewport.isVisible():
                        QWidget.update(viewport)
                except RuntimeError:
                    pass
    except RuntimeError:
        return


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
    visited: set[int] = set()
    registered = {id(root)}
    for widget in iter_widget_tree([root], visited):
        _propagate_palette_one(
            widget,
            copied,
            registered=id(widget) in registered,
        )


def _polish_widget_tree(root: QWidget, seen: set[int]) -> None:
    root = _alive_widget(root)
    if root is None:
        return
    for widget in iter_widget_tree([root], seen):
        try:
            style = QWidget.style(widget)
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
            if widget.isVisible():
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


def refresh_window_icon_cache(widget: QWidget) -> None:
    """Refresh icons for one top-level window after a DPR/screen change.

    Does not replay QSS, palette, or density metrics.
    """

    target = _alive_widget(widget)
    if target is None:
        return
    from .runtime import default_theme_runtime
    from .icons import apply_icons_to_one_widget

    runtime = default_theme_runtime()
    snapshot = runtime.snapshot
    provider = runtime.icon_provider
    if snapshot is None or provider is None:
        return
    window = target.window()
    registry = default_window_registry()
    for participant in list(registry.live_icon_participants()):
        host = _alive_widget(participant)
        if host is None:
            continue
        try:
            if host.window() is not window:
                continue
        except RuntimeError:
            continue
        apply_icons_to_one_widget(host, snapshot, provider)


class _ScreenHookFilter(QObject):
    """Bind ``screenChanged`` once a top-level window handle exists."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in {
            QEvent.Type.Show,
            QEvent.Type.WinIdChange,
            QEvent.Type.Polish,
        }:
            if isinstance(watched, QWidget):
                _connect_screen_signals(watched)
        return False


def _connect_screen_signals(widget: QWidget) -> None:
    target = _alive_widget(widget)
    if target is None:
        return
    window = target.window()
    if window is not target:
        return
    handle = window.windowHandle()
    if handle is None:
        return
    key = id(handle)
    if key in _SCREEN_HOOKS:
        return

    def _on_screen(*_args: object, host: QWidget = window) -> None:
        refresh_window_icon_cache(host)

    handle.screenChanged.connect(_on_screen)
    dpr_changed = getattr(handle, "devicePixelRatioChanged", None)
    if dpr_changed is not None:
        dpr_changed.connect(_on_screen)

    def _on_destroyed(*_args: object, handle_id: int = key) -> None:
        _SCREEN_HOOKS.pop(handle_id, None)

    handle.destroyed.connect(_on_destroyed)
    _SCREEN_HOOKS[key] = _on_screen


_INDEPENDENT_OBJECT_NAMES = frozenset({
    "MainWindow",
    "setting_dialog",
    "style_dialog",
    "layout_dialog",
    "fit_dialog",
    "figure_popout_window",
})


def _is_independent_theme_root(widget: QWidget) -> bool:
    """Return whether ``widget`` is a top-level or independent style root."""

    target = _alive_widget(widget)
    if target is None:
        return False
    try:
        if target.parentWidget() is None or target.isWindow():
            return True
    except RuntimeError:
        return False
    return target.objectName() in _INDEPENDENT_OBJECT_NAMES


class ThemeWindowRegistry:
    """Weak top-level windows plus explicit metrics/icon/palette participants."""

    def __init__(self) -> None:
        self._items: dict[int, Callable[[], QWidget | None]] = {}
        self._metrics: dict[int, Callable[[], QWidget | None]] = {}
        self._icons: dict[int, Callable[[], QWidget | None]] = {}
        self._palettes: dict[int, Callable[[], QWidget | None]] = {}
        self._screen_filter = _ScreenHookFilter()
        self.last_stage_visits: dict[str, dict[int, int]] = {
            "palette": {},
            "metrics": {},
            "icons": {},
        }
        self.last_root_count = 0
        self.last_child_count = 0

    def register(self, widget: QWidget) -> None:
        """Subscribe a top-level or independent style root."""

        target = _alive_widget(widget)
        if target is None:
            return
        existed = id(target) in self._items
        self._store(self._items, target)
        if existed:
            return
        target.installEventFilter(self._screen_filter)
        _connect_screen_signals(target)

    def register_participant(
        self,
        widget: QWidget,
        *,
        metrics: bool = True,
        icons: bool = True,
        palette: bool = False,
    ) -> None:
        """Subscribe an explicit chrome participant. Idempotent."""

        if metrics:
            self._store(self._metrics, widget)
        if icons:
            self._store(self._icons, widget)
        if palette:
            self._store(self._palettes, widget)

    def unregister(self, widget: QWidget) -> None:
        """Drop ``widget`` from every table if it is still registered."""

        key = id(widget)
        self._items.pop(key, None)
        self._metrics.pop(key, None)
        self._icons.pop(key, None)
        self._palettes.pop(key, None)

    def contains(self, widget: QWidget) -> bool:
        """Return whether ``widget`` is a live window or participant."""

        key = id(widget)
        for table in (self._items, self._metrics, self._icons, self._palettes):
            ref = table.get(key)
            if ref is not None and ref() is widget:
                return True
        return False

    def contains_window(self, widget: QWidget) -> bool:
        """Return whether ``widget`` is a live independent theme window."""

        ref = self._items.get(id(widget))
        return ref is not None and ref() is widget

    def live_widgets(self) -> Iterator[QWidget]:
        """Yield live window roots, pruning dead weakrefs."""

        yield from self._live(self._items)

    def live_metrics_participants(self) -> Iterator[QWidget]:
        yield from self._live(self._metrics)

    def live_icon_participants(self) -> Iterator[QWidget]:
        yield from self._live(self._icons)

    def live_palette_participants(self) -> Iterator[QWidget]:
        yield from self._live(self._palettes)

    def _store(
        self,
        table: dict[int, Callable[[], QWidget | None]],
        widget: QWidget,
    ) -> None:
        if widget is None:
            return
        key = id(widget)
        if key in table:
            return
        table[key] = weakref.ref(widget)

        def _on_destroyed(*_args: object, widget_id: int = key) -> None:
            self.unregister_id(widget_id)

        widget.destroyed.connect(_on_destroyed)

    def unregister_id(self, widget_id: int) -> None:
        """Idempotent drop by widget identity."""

        self._items.pop(widget_id, None)
        self._metrics.pop(widget_id, None)
        self._icons.pop(widget_id, None)
        self._palettes.pop(widget_id, None)

    def _live(
        self,
        table: dict[int, Callable[[], QWidget | None]],
    ) -> Iterator[QWidget]:
        dead: list[int] = []
        for key, ref in table.items():
            widget = ref()
            if widget is None:
                dead.append(key)
                continue
            yield widget
        for key in dead:
            table.pop(key, None)

    def _record_visit(self, stage: str, widget: QWidget) -> None:
        counts = self.last_stage_visits.setdefault(stage, {})
        key = id(widget)
        counts[key] = counts.get(key, 0) + 1

    def apply_palette(self, palette: QPalette) -> None:
        """Apply ``palette`` to window roots and explicit palette participants."""

        copied = QPalette(palette)
        self.last_stage_visits["palette"] = {}
        windows = list(self.live_widgets())
        self.last_root_count = len(windows)
        visited: set[int] = set()
        for widget in windows:
            self._record_visit("palette", widget)
            visited.add(id(widget))
            _propagate_palette_one(widget, copied, registered=True)
        extra = 0
        for widget in list(self.live_palette_participants()):
            if id(widget) in visited:
                continue
            extra += 1
            self._record_visit("palette", widget)
            _propagate_palette_one(widget, copied, registered=False)
        self.last_child_count = extra

    def _palette_targets(self) -> dict[int, QWidget]:
        targets = {id(widget): widget for widget in self.live_widgets()}
        targets.update({id(widget): widget for widget in self.live_palette_participants()})
        for widget in list(targets.values()):
            if isinstance(widget, QAbstractScrollArea):
                viewport = widget.viewport()
                targets[id(viewport)] = viewport
        return targets

    def capture_palettes(self) -> tuple[WindowPaletteMemento, ...]:
        """Capture the explicit registry only, never the descendant tree."""

        return tuple(
            WindowPaletteMemento(
                weakref.ref(widget),
                QPalette(widget.palette()),
                widget.testAttribute(Qt.WidgetAttribute.WA_SetPalette),
            )
            for widget in self._palette_targets().values()
        )

    def restore_palettes(
        self, captured: tuple[WindowPaletteMemento, ...], palette: QPalette,
    ) -> None:
        """Restore exact captured palettes; new subscribers use the target palette."""

        targets = self._palette_targets()
        restored: set[int] = set()
        for item in captured:
            widget = _alive_widget(item.widget())
            if widget is None or targets.get(id(widget)) is not widget:
                continue
            widget.setPalette(QPalette(item.palette))
            widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, item.explicitly_set)
            restored.add(id(widget))
        for widget in self.live_widgets():
            if id(widget) not in restored:
                _propagate_palette_one(widget, palette, registered=True)
        for widget in self.live_palette_participants():
            if id(widget) not in restored:
                _propagate_palette_one(widget, palette, registered=False)

    def apply_metrics(self, metrics: DensityMetrics) -> None:
        from .participants import apply_metrics_to_one_widget

        self.last_stage_visits["metrics"] = {}
        for widget in list(self.live_metrics_participants()):
            self._record_visit("metrics", widget)
            apply_metrics_to_one_widget(widget, metrics)

    def apply_icons(
        self,
        snapshot: ThemeSnapshot,
        provider: CachingThemeIconProvider,
    ) -> None:
        from .icons import apply_icons_to_one_widget

        self.last_stage_visits["icons"] = {}
        for widget in list(self.live_icon_participants()):
            self._record_visit("icons", widget)
            apply_icons_to_one_widget(widget, snapshot, provider)

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

    def max_visits(self, stage: str) -> int:
        """Return the highest per-widget visit count from the last ``stage``."""

        counts = self.last_stage_visits.get(stage) or {}
        return max(counts.values()) if counts else 0


_REGISTRY: ThemeWindowRegistry | None = None


def default_window_registry() -> ThemeWindowRegistry:
    """Return the process-wide chrome window registry."""

    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ThemeWindowRegistry()
    return _REGISTRY


def reset_window_registry_for_tests() -> ThemeWindowRegistry:
    """Replace the process registry. Tests must not leak destroyed connections."""

    global _REGISTRY, _SCREEN_HOOKS
    _SCREEN_HOOKS = {}
    _REGISTRY = ThemeWindowRegistry()
    return _REGISTRY


def _sync_widget(widget: QWidget) -> None:
    from .runtime import default_theme_runtime

    runtime = default_theme_runtime()
    snapshot = runtime.snapshot
    if snapshot is None:
        return
    target = _alive_widget(widget)
    if target is None:
        return
    copied = QPalette(snapshot.palette)
    if _is_independent_theme_root(target):
        _propagate_palette_one(target, copied, registered=True)
    elif isinstance(target, QAbstractScrollArea):
        viewport = _alive_widget(target.viewport())
        if viewport is not None:
            _propagate_palette_one(viewport, copied, registered=False)
    from .participants import apply_metrics_to_one_widget

    apply_metrics_to_one_widget(target, snapshot.metrics)
    if runtime.icon_provider is not None:
        from .icons import apply_icons_to_one_widget

        apply_icons_to_one_widget(target, snapshot, runtime.icon_provider)


def _flush_construction_sync() -> None:
    registry = default_window_registry()
    from .runtime import default_theme_runtime

    runtime = default_theme_runtime()
    snapshot = runtime.snapshot
    if snapshot is None:
        return
    registry.apply_snapshot(snapshot, runtime.icon_provider)


@contextmanager
def theme_construction_batch():
    """Register theme windows during construction; sync once on exit."""

    global _CONSTRUCTION_DEPTH
    _CONSTRUCTION_DEPTH += 1
    try:
        yield
    finally:
        _CONSTRUCTION_DEPTH -= 1
        if _CONSTRUCTION_DEPTH == 0:
            _flush_construction_sync()


def in_theme_construction_batch() -> bool:
    """Return whether MainWindow construction is deferring theme sync."""

    return _CONSTRUCTION_DEPTH > 0


def subscribe_theme_window(
    widget: QWidget,
    *,
    sync_initial: bool = True,
) -> None:
    """Register a cached dialog, independent root, or nested chrome participant.

    The registry holds only weak QWidget references. Callers must not store
    ``ComponentState``, selection IDs, or color-cycle cursors on the window.
    During ``theme_construction_batch()`` this only registers; the batch exit
    syncs final top-level roots once. Nested chrome becomes an explicit
    metrics/icon participant and is not walked as a second tree root. Dynamic
    widgets that already consumed the current metrics during construction may
    pass ``sync_initial=False`` to avoid repeating that work before first
    polish; later theme publications still visit the registered participant.
    """

    target = _alive_widget(widget)
    if target is None:
        return
    registry = default_window_registry()
    if _is_independent_theme_root(target):
        registry.register(target)
    registry.register_participant(target, metrics=True, icons=True)
    if isinstance(target, QAbstractScrollArea):
        viewport = _alive_widget(target.viewport())
        if viewport is not None:
            registry.register_participant(viewport, metrics=False, icons=False, palette=True)
    if _CONSTRUCTION_DEPTH > 0 or not sync_initial:
        return
    _sync_widget(target)
