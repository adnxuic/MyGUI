"""Theme binding ports. SubAgent B fills real QSS; C registers hidden widgets."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Iterator, Mapping
from typing import Protocol, runtime_checkable

from PySide6.QtWidgets import QWidget

from .models import DensityMetrics, ThemeSnapshot


@runtime_checkable
class ThemeBindingPort(Protocol):
    """Production widgets style through ``bind_qss``. Bindings are weak."""

    def bind_qss(self, widget: QWidget, resource: str) -> None:
        """Register ``widget`` for retokenized ``resource``. Detach on destroyed."""


@runtime_checkable
class QssDocumentRenderer(Protocol):
    """Pre-render QSS with no widget side effects. B supplies real documents."""

    def render_application(self, snapshot: ThemeSnapshot) -> str:
        """Return the application stylesheet for ``snapshot``."""

    def render_resource(self, resource: str, snapshot: ThemeSnapshot) -> str:
        """Return one bundled QSS document expanded from ``snapshot`` tokens."""


@runtime_checkable
class ThemeIconProvider(Protocol):
    """Monochrome chrome icons. C implements DPR/scheme/density caching."""

    def prerender(self, snapshot: ThemeSnapshot) -> object:
        """Build icon artifacts with no widget side effects."""

    def apply(self, rendered: object) -> None:
        """Publish prerendered icons."""

    def capture(self) -> object:
        """Return a memento of the currently applied icons."""

    def restore(self, memento: object) -> None:
        """Restore icons from ``capture``."""


@runtime_checkable
class MetricsBindingPort(Protocol):
    """Optional structural-size applier. Missing ports no-op inside the transaction."""

    def apply(self, metrics: DensityMetrics) -> None:
        """Apply density metrics to bound chrome."""

    def capture(self) -> object:
        """Return a memento of structural sizes."""

    def restore(self, memento: object) -> None:
        """Restore structural sizes from ``capture``."""


class PlaceholderQssRenderer:
    """Expand bundled QSS from snapshot tokens. Missing resources keep apply markers."""

    def render_application(self, snapshot: ThemeSnapshot) -> str:
        from .qss import render_application_stylesheet

        return render_application_stylesheet(snapshot)

    def render_resource(self, resource: str, snapshot: ThemeSnapshot) -> str:
        from .qss import render_resource_stylesheet

        return render_resource_stylesheet(resource, snapshot)


class NullThemeIconProvider:
    """No-op icon provider so the icons transaction step stays complete."""

    def prerender(self, snapshot: ThemeSnapshot) -> object:
        return {
            "scheme": snapshot.scheme.value,
            "density": snapshot.preferences.density.value,
        }

    def apply(self, rendered: object) -> None:
        return None

    def capture(self) -> object:
        return None

    def restore(self, memento: object) -> None:
        return None


class ThemeBindingRegistry:
    """Weak ``bind_qss`` registry. Hidden widgets and popouts use the same API."""

    def __init__(self) -> None:
        self._items: dict[int, tuple[Callable[[], QWidget | None], str]] = {}

    def bind_qss(self, widget: QWidget, resource: str) -> None:
        if widget is None:
            return
        key = id(widget)
        path = str(resource)
        if key in self._items:
            ref, _previous = self._items[key]
            self._items[key] = (ref, path)
        else:
            self._items[key] = (weakref.ref(widget), path)

            def _on_destroyed(*_args: object, widget_id: int = key) -> None:
                self._items.pop(widget_id, None)

            widget.destroyed.connect(_on_destroyed)
        from .qss import try_render_bound_resource

        rendered = try_render_bound_resource(path)
        if rendered is not None:
            widget.setStyleSheet(rendered)

    def iter_bindings(self) -> Iterator[tuple[QWidget, str]]:
        dead: list[int] = []
        for key, (ref, resource) in self._items.items():
            widget = ref()
            if widget is None:
                dead.append(key)
                continue
            yield widget, resource
        for key in dead:
            self._items.pop(key, None)

    def capture_stylesheets(self) -> dict[int, str]:
        captured: dict[int, str] = {}
        for widget, _resource in self.iter_bindings():
            captured[id(widget)] = widget.styleSheet()
        return captured

    def restore_stylesheets(self, captured: Mapping[int, str]) -> None:
        for widget, _resource in self.iter_bindings():
            key = id(widget)
            if key in captured:
                widget.setStyleSheet(captured[key])

    def apply_stylesheets(self, rendered_by_resource: Mapping[str, str]) -> None:
        for widget, resource in self.iter_bindings():
            stylesheet = rendered_by_resource.get(resource)
            if stylesheet is not None:
                widget.setStyleSheet(stylesheet)


class RecordingThemeBindingPort(ThemeBindingRegistry):
    """Registry that records bind/apply for tests and for C's hidden hosts."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, str]] = []

    def bind_qss(self, widget: QWidget, resource: str) -> None:
        self.events.append(("bind", str(resource)))
        super().bind_qss(widget, resource)

    def apply_stylesheets(self, rendered_by_resource: Mapping[str, str]) -> None:
        self.events.append(("apply", ",".join(sorted(rendered_by_resource))))
        super().apply_stylesheets(rendered_by_resource)


def binding_iter(port: ThemeBindingPort | None) -> Iterator[tuple[QWidget, str]]:
    iterator = getattr(port, "iter_bindings", None) if port is not None else None
    if iterator is None:
        return iter(())
    return iterator()


def binding_capture(port: ThemeBindingPort | None) -> dict[int, str]:
    capture = getattr(port, "capture_stylesheets", None) if port is not None else None
    if capture is None:
        return {}
    return dict(capture())


def binding_restore(port: ThemeBindingPort | None, captured: Mapping[int, str]) -> None:
    restore = getattr(port, "restore_stylesheets", None) if port is not None else None
    if restore is not None:
        restore(captured)


def binding_apply(
    port: ThemeBindingPort | None,
    rendered_by_resource: Mapping[str, str],
) -> None:
    apply = getattr(port, "apply_stylesheets", None) if port is not None else None
    if apply is not None:
        apply(rendered_by_resource)
