"""Structural layout signatures. Geometry pixels and styles are excluded."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QBoxLayout,
    QDockWidget,
    QFormLayout,
    QGridLayout,
    QLayout,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QWidget,
)


def _qt_layout(widget: QWidget) -> QLayout | None:
    """Return the Qt layout even when ``widget.layout`` is an instance attribute."""

    method = getattr(QWidget, "layout", None)
    if callable(method):
        try:
            result = method(widget)
        except TypeError:
            result = object()
        else:
            if result is None or isinstance(result, QLayout):
                return result
    attribute = getattr(widget, "layout", None)
    return attribute if isinstance(attribute, QLayout) else None


def _include_widget(widget: QWidget) -> bool:
    name = widget.objectName() or ""
    if name.startswith("qt_"):
        return False
    module = type(widget).__module__ or ""
    return not module.startswith("matplotlib")


def _stretch(layout: QLayout | None, index: int) -> int:
    if isinstance(layout, QBoxLayout):
        return int(layout.stretch(index))
    if isinstance(layout, QGridLayout):
        return 0
    if isinstance(layout, QFormLayout):
        return 0
    return 0


def _nested_layout(layout: QLayout) -> dict[str, object]:
    children: list[object] = []
    stretches: list[int] = []
    for index in range(layout.count()):
        stretches.append(_stretch(layout, index))
        item = layout.itemAt(index)
        if item is None:
            children.append({"class": "empty"})
            continue
        widget = item.widget()
        if widget is not None:
            if _include_widget(widget):
                children.append(capture_layout_signature(widget))
            continue
        nested = item.layout()
        if nested is not None:
            children.append(_nested_layout(nested))
            continue
        if item.spacerItem() is not None:
            children.append({"class": "QSpacerItem"})
            continue
        children.append({"class": "item"})
    return {
        "class": type(layout).__name__,
        "name": "",
        "layout": type(layout).__name__,
        "stretch": tuple(stretches),
        "children": children,
    }


def capture_layout_signature(widget: QWidget) -> dict[str, object]:
    """Return parentage, layout type, child order, stretch, splitter, and tabs.

    Ignores pixel geometry, fonts, stylesheets, and Qt internal ``qt_*``
    children so density and theme changes do not shift the signature.
    """

    layout = _qt_layout(widget)
    payload: dict[str, object] = {
        "class": type(widget).__name__,
        "name": widget.objectName() or "",
        "layout": type(layout).__name__ if layout is not None else "",
        "stretch": (),
        "children": [],
    }
    if isinstance(widget, QSplitter):
        payload["splitter"] = {
            "orientation": int(widget.orientation().value),
            "count": int(widget.count()),
        }
    if isinstance(widget, QTabWidget):
        payload["tabs"] = tuple(
            widget.widget(index).objectName() if widget.widget(index) is not None else ""
            for index in range(widget.count())
        )
        payload["tab_count"] = int(widget.count())
    if isinstance(widget, QStackedWidget):
        payload["stack_count"] = int(widget.count())
    if isinstance(widget, QDockWidget):
        parent = widget.parentWidget()
        parent_layout = _qt_layout(parent) if parent is not None else None
        payload["dock"] = {
            "area": int(parent_layout.indexOf(widget))
            if parent_layout is not None
            else -1,
            "features": int(widget.features().value)
            if hasattr(widget.features(), "value")
            else int(widget.features()),
        }
    if layout is not None:
        nested = _nested_layout(layout)
        payload["stretch"] = nested["stretch"]
        payload["children"] = nested["children"]
        return payload
    children: list[object] = []
    for child in widget.children():
        if not isinstance(child, QWidget) or child.parent() is not widget:
            continue
        if not _include_widget(child):
            continue
        children.append(capture_layout_signature(child))
    payload["children"] = children
    return payload


def signature_paths(payload: dict[str, object], prefix: str = "") -> tuple[str, ...]:
    """Flatten a signature into comparable parentage path strings."""

    name = str(payload.get("name") or "")
    klass = str(payload.get("class") or "")
    layout = str(payload.get("layout") or "")
    node = f"{klass}#{name}:{layout}"
    path = f"{prefix}/{node}" if prefix else node
    rows = [path]
    for child in payload.get("children") or ():
        if isinstance(child, dict):
            rows.extend(signature_paths(child, path))
    splitter = payload.get("splitter")
    if isinstance(splitter, dict):
        rows.append(f"{path}|splitter={splitter['orientation']},{splitter['count']}")
    tabs = payload.get("tabs")
    if isinstance(tabs, tuple):
        rows.append(f"{path}|tabs={','.join(tabs)}")
    return tuple(rows)
