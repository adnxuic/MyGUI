"""Structural chrome sizes: participant list and MetricsBindingPort applier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QFrame,
    QLayout,
    QPushButton,
    QTableView,
    QToolBar,
    QToolButton,
    QWidget,
)

from .models import DensityMetrics

LAYOUT_BUTTON_MIN_WIDTH = 112
QWIDGETSIZE_MAX = 16777215

# Production widgets whose Python-side chrome sizes read snapshot metrics.
SIZE_PARTICIPANTS: tuple[dict[str, str], ...] = (
    {
        "object_name": "left_column",
        "metric": "rail",
        "axis": "width",
        "description": "Left activity rail",
    },
    {
        "object_name": "right_column",
        "metric": "rail",
        "axis": "width",
        "description": "Right activity rail",
    },
    {
        "object_name": "bottom_bar",
        "metric": "bottom",
        "axis": "height",
        "description": "Message and state bar",
    },
    {
        "object_name": "title_bar",
        "metric": "command+gallery",
        "axis": "height",
        "description": "Command row plus tool gallery",
    },
    {
        "object_name": "selector_menu_bar",
        "metric": "command",
        "axis": "height",
        "description": "Style/layout/chart/element command row",
    },
    {
        "object_name": "menu_bar",
        "metric": "command",
        "axis": "height",
        "description": "File/edit command row",
    },
    {
        "object_name": "selector_menu",
        "metric": "gallery",
        "axis": "height",
        "description": "Tool gallery",
    },
    {
        "object_name": "change_button",
        "metric": "command",
        "axis": "height",
        "description": "Command/gallery switch button",
    },
    {
        "object_name": "sheet_table_view",
        "metric": "table_row/table_header",
        "axis": "height",
        "description": "Sheet table rows and header",
    },
    {
        "object_name": "component_tree_view",
        "metric": "tree",
        "axis": "height",
        "description": "Components tree rows",
    },
    {
        "object_name": "component_tree_search",
        "metric": "control",
        "axis": "height",
        "description": "Components tree search field",
    },
    {
        "object_name": "component_tree_host",
        "metric": "spacing_sm",
        "axis": "padding",
        "description": "Components tree host padding",
    },
    {
        "object_name": "figure_inspector_host",
        "metric": "control",
        "axis": "height",
        "description": "Inspector combo/line/spin minimum height",
    },
    {
        "object_name": "setting_dialog",
        "metric": "control",
        "axis": "height",
        "description": "Cached Settings dialog controls",
    },
    {
        "object_name": "style_dialog",
        "metric": "control",
        "axis": "height",
        "description": "Cached Style creation dialog controls",
    },
    {
        "object_name": "layout_dialog",
        "metric": "control",
        "axis": "height",
        "description": "Layout dialog controls",
    },
    {
        "object_name": "fit_dialog",
        "metric": "control",
        "axis": "height",
        "description": "Fit dialog controls",
    },
    {
        "object_name": "figure_popout_window",
        "metric": "none",
        "axis": "palette",
        "description": "Parentless Canvas popout (palette/icons, no ComponentState)",
    },
)


@dataclass
class _SizeMemento:
    widget_id: int
    minimum: QSize
    maximum: QSize
    extras: dict[str, Any] = field(default_factory=dict)


def _qt_layout(widget: QWidget) -> QLayout | None:
    """Return a widget layout even when ``layout`` is shadowed by an attribute."""

    layout_attr = getattr(widget, "layout", None)
    if callable(layout_attr):
        return layout_attr()
    if isinstance(layout_attr, QLayout):
        return layout_attr
    return QWidget.layout(widget)


def apply_metrics_to_one_widget(widget: QWidget, metrics: DensityMetrics) -> None:
    """Apply density metrics to ``widget`` only. Does not walk descendants."""

    method = getattr(widget, "apply_theme_metrics", None)
    if callable(method):
        method(metrics)
    _apply_by_object_name(widget, metrics)


def apply_metrics_to_widget(widget: QWidget, metrics: DensityMetrics) -> None:
    """Apply density metrics to one chrome participant."""

    apply_metrics_to_one_widget(widget, metrics)


def _apply_by_object_name(widget: QWidget, metrics: DensityMetrics) -> None:
    name = widget.objectName()
    if name in {"left_column", "right_column"}:
        widget.setFixedWidth(metrics.rail)
        for button in widget.findChildren(QPushButton):
            button.setMinimumSize(metrics.button, metrics.button)
    elif name == "bottom_bar":
        widget.setFixedHeight(metrics.bottom)
    elif name == "title_bar":
        widget.setFixedHeight(metrics.command + metrics.gallery)
    elif name in {"selector_menu_bar", "menu_bar"}:
        widget.setFixedHeight(metrics.command)
    elif name == "selector_menu":
        widget.setMinimumHeight(metrics.gallery)
        widget.setMaximumHeight(metrics.gallery)
        toolbar = widget.findChild(QToolBar)
        if toolbar is not None:
            toolbar.setIconSize(QSize(metrics.gallery_icon, metrics.gallery_icon))
            _apply_gallery_button_metrics(toolbar, metrics)
    elif name == "change_button":
        widget.setMinimumHeight(metrics.command)
    elif name == "sheet_table_view":
        _apply_table_metrics(widget, metrics)
    elif name == "component_tree_view":
        setattr(widget, "_theme_row_height", metrics.tree)
        relayout = getattr(widget, "doItemsLayout", None)
        if callable(relayout):
            relayout()
    elif name == "component_tree_search":
        widget.setMinimumHeight(metrics.control)
        widget.setMaximumHeight(metrics.control)
    elif name == "component_tree_host":
        layout = _qt_layout(widget)
        if layout is not None:
            pad = metrics.spacing_sm
            layout.setContentsMargins(pad, pad, pad, pad)
            layout.setSpacing(pad)
    elif name in {
        "figure_inspector_host",
        "setting_dialog",
        "style_dialog",
        "layout_dialog",
        "fit_dialog",
        "figure_inspector_panel",
        "axes_inspector_panel",
    }:
        apply = getattr(widget, "apply_theme_metrics", None)
        if callable(apply):
            apply(metrics)
    elif name == "command_separator" and isinstance(widget, QFrame):
        widget.setFixedHeight(metrics.bottom)


def _apply_gallery_button_metrics(toolbar: QToolBar, metrics: DensityMetrics) -> None:
    for button in toolbar.findChildren(QToolButton):
        if button.objectName() == "qt_toolbar_ext_button":
            continue
        if button.objectName() == "layout_template_button":
            button.setMinimumWidth(LAYOUT_BUTTON_MIN_WIDTH)
            button.setMaximumWidth(QWIDGETSIZE_MAX)
        button.setMinimumHeight(0)
        button.setMaximumHeight(metrics.gallery)


def _apply_table_metrics(widget: QWidget, metrics: DensityMetrics) -> None:
    if not isinstance(widget, QTableView):
        return
    header = widget.horizontalHeader()
    header.setFixedHeight(metrics.table_header)
    widget.verticalHeader().setDefaultSectionSize(metrics.table_row)


def capture_widget_metrics(widget: QWidget) -> dict[str, Any]:
    """Capture structural sizes for transaction rollback."""

    extras: dict[str, Any] = {}
    if isinstance(widget, QTableView):
        extras["table_header"] = widget.horizontalHeader().height()
        extras["table_row"] = widget.verticalHeader().defaultSectionSize()
    tree_height = getattr(widget, "_theme_row_height", None)
    if tree_height is not None:
        extras["tree_row"] = int(tree_height)
    toolbar = widget.findChild(QToolBar) if widget.objectName() == "selector_menu" else None
    if toolbar is not None:
        extras["icon_size"] = toolbar.iconSize()
    layout = _qt_layout(widget)
    if layout is not None and widget.objectName() == "component_tree_host":
        margins = layout.contentsMargins()
        extras["margins"] = (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )
        extras["spacing"] = layout.spacing()
    return {
        "minimum": widget.minimumSize(),
        "maximum": widget.maximumSize(),
        "extras": extras,
    }


def restore_widget_metrics(widget: QWidget, memento: dict[str, Any]) -> None:
    """Restore structural sizes from ``capture_widget_metrics``."""

    minimum = memento.get("minimum")
    maximum = memento.get("maximum")
    if isinstance(minimum, QSize):
        widget.setMinimumSize(minimum)
    if isinstance(maximum, QSize):
        widget.setMaximumSize(maximum)
    extras = memento.get("extras") or {}
    if isinstance(widget, QTableView):
        if "table_header" in extras:
            widget.horizontalHeader().setFixedHeight(int(extras["table_header"]))
        if "table_row" in extras:
            widget.verticalHeader().setDefaultSectionSize(int(extras["table_row"]))
    if "tree_row" in extras:
        setattr(widget, "_theme_row_height", int(extras["tree_row"]))
    if "icon_size" in extras:
        toolbar = widget.findChild(QToolBar)
        if toolbar is not None:
            toolbar.setIconSize(extras["icon_size"])
    layout = _qt_layout(widget)
    if layout is not None and "margins" in extras:
        left, top, right, bottom = extras["margins"]
        layout.setContentsMargins(left, top, right, bottom)
        layout.setSpacing(int(extras.get("spacing", layout.spacing())))


class ThemeMetricsApplier:
    """Injectable ``MetricsBindingPort`` for ThemeService transaction step 4."""

    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry
        self._applied: DensityMetrics | None = None

    def _windows(self) -> tuple[QWidget, ...]:
        if self._registry is not None:
            return tuple(self._registry.live_widgets())
        from .windows import default_window_registry

        return tuple(default_window_registry().live_widgets())

    def _targets(self) -> tuple[QWidget, ...]:
        registry = self._registry
        if registry is None:
            from .windows import default_window_registry

            registry = default_window_registry()
        seen: set[int] = set()
        widgets: list[QWidget] = []
        streams = [registry.live_widgets()]
        live_metrics = getattr(registry, "live_metrics_participants", None)
        if callable(live_metrics):
            streams.append(live_metrics())
        for stream in streams:
            for widget in stream:
                key = id(widget)
                if key in seen:
                    continue
                seen.add(key)
                widgets.append(widget)
        return tuple(widgets)

    def apply(self, metrics: DensityMetrics) -> None:
        """Apply density metrics to every subscribed chrome window."""

        self._applied = metrics
        from .windows import default_window_registry

        registry = self._registry if self._registry is not None else default_window_registry()
        apply_metrics = getattr(registry, "apply_metrics", None)
        if callable(apply_metrics):
            apply_metrics(metrics)
            return
        for widget in self._windows():
            apply_metrics_to_widget(widget, metrics)

    def capture(self) -> object:
        """Return structural-size mementos for rollback."""

        captured: dict[int, dict[str, Any]] = {}
        for widget in self._targets():
            captured[id(widget)] = capture_widget_metrics(widget)
        return {"widgets": captured, "metrics": self._applied}

    def restore(self, memento: object) -> None:
        """Restore structural sizes from ``capture``."""

        payload = dict(memento) if isinstance(memento, dict) else {}
        captured = payload.get("widgets") or {}
        for widget in self._targets():
            item = captured.get(id(widget))
            if item is not None:
                restore_widget_metrics(widget, item)
        self._applied = payload.get("metrics")
