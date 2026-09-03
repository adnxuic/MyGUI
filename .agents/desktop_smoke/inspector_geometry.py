"""Map Inspector chrome rects into the host and fail on occlusion."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QLabel, QWidget

from desktop_smoke.harness import SmokeError
from mygui.widgets.fig_control_window.component_editors.inspector import (
    InspectorSectionGroup,
)
from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
    section_group_subcontrol_rects,
)


def _mapped_rect(widget: QWidget, origin: QWidget) -> QRect:
    return QRect(widget.mapTo(origin, QPoint(0, 0)), widget.size())


def _parent_path(widget: QWidget, host: QWidget) -> str:
    parts: list[str] = []
    current: QWidget | None = widget
    while current is not None:
        name = current.objectName() or type(current).__name__
        parts.append(name)
        if current is host:
            break
        current = current.parentWidget()
    return "/".join(reversed(parts))


def _direct_children(widget: QWidget) -> list[QWidget]:
    return list(
        widget.findChildren(
            QWidget,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )
    )


def collect_inspector_rects(host: QWidget) -> list[dict[str, Any]]:
    """Record visible control rects in host coordinates plus GroupBox chrome."""

    payload: list[dict[str, Any]] = []
    for child in host.findChildren(QWidget):
        if not child.isVisible():
            continue
        mapped = _mapped_rect(child, host)
        buddy = child.buddy() if isinstance(child, QLabel) else None
        item: dict[str, Any] = {
            "class": type(child).__name__,
            "name": child.objectName(),
            "parentPath": _parent_path(child, host),
            "x": mapped.x(),
            "y": mapped.y(),
            "w": mapped.width(),
            "h": mapped.height(),
        }
        if isinstance(child, QLabel):
            item["text"] = child.text()
            item["wordWrap"] = bool(child.wordWrap())
            if buddy is not None:
                item["buddy"] = {
                    "class": type(buddy).__name__,
                    "name": buddy.objectName(),
                    "path": _parent_path(buddy, host),
                }
        if isinstance(child, InspectorSectionGroup):
            style_rects = section_group_subcontrol_rects(child)
            origin = child.mapTo(host, QPoint(0, 0))
            item["groupBox"] = {
                "title": child.title(),
                "checkable": child.isCheckable(),
                "checked": child.isChecked(),
                "titleRect": _shift(style_rects["title"], origin),
                "indicatorRect": _shift(style_rects["indicator"], origin),
                "contentsRect": _shift(style_rects["contents"], origin),
                "frameRect": _shift(style_rects["frame"], origin),
            }
        payload.append(item)
    return payload


def _shift(rect: QRect, origin: QPoint) -> dict[str, int]:
    return {
        "x": origin.x() + rect.x(),
        "y": origin.y() + rect.y(),
        "w": rect.width(),
        "h": rect.height(),
    }


def assert_inspector_geometry(host: QWidget, label: str) -> None:
    """Fail when labels, siblings, or GroupBox subcontrols are occluded."""

    host_rect = host.rect().adjusted(-2, -2, 2, 2)
    for child in host.findChildren(QLabel):
        if not child.isVisible() or child.width() <= 0:
            continue
        buddy = child.buddy()
        if buddy is None:
            continue
        text = (getattr(child, "_full_text", None) or child.text()).strip()
        if not text:
            continue
        mapped = _mapped_rect(child, host)
        natural = child.fontMetrics().horizontalAdvance(text)
        if mapped.width() + 1 < natural:
            tooltip = child.toolTip() or ""
            if tooltip != text:
                raise SmokeError(
                    f"{label}: truncated label {text!r} has no full tooltip."
                )
            floor = max(child.fontMetrics().averageCharWidth() * 2, 8)
            if mapped.width() < min(natural, floor):
                raise SmokeError(
                    f"{label}: label {text!r} is not readable ({mapped.width()}px)."
                )
        elif mapped.width() < natural - 1:
            raise SmokeError(
                f"{label}: label {text!r} width {mapped.width()} < natural {natural}."
            )
        if any(char.isalnum() for char in text) and mapped.width() <= 2:
            raise SmokeError(f"{label}: label {text!r} collapsed to punctuation.")
        if buddy.isVisible() and buddy.width() > 0:
            buddy_rect = _mapped_rect(buddy, host)
            if mapped.intersects(buddy_rect):
                raise SmokeError(f"{label}: label {text!r} overlaps its buddy.")
            if buddy_rect.right() > host_rect.right() + 2:
                raise SmokeError(f"{label}: buddy for {text!r} overflows the Inspector.")

    parents = {host}
    for child in host.findChildren(QWidget):
        if child.isVisible():
            parents.add(child)
    for parent in parents:
        visible = [
            sibling
            for sibling in _direct_children(parent)
            if sibling.isVisible() and sibling.width() > 0 and sibling.height() > 0
        ]
        for index, left in enumerate(visible):
            left_rect = _mapped_rect(left, host)
            for right in visible[index + 1 :]:
                right_rect = _mapped_rect(right, host)
                overlap = left_rect.intersected(right_rect)
                if overlap.width() > 1 and overlap.height() > 1:
                    raise SmokeError(
                        f"{label}: siblings overlap "
                        f"{type(left).__name__}#{left.objectName()} and "
                        f"{type(right).__name__}#{right.objectName()}."
                    )

    from mygui.application_theme import current_density_metrics

    gap = current_density_metrics().spacing_xs
    for group in host.findChildren(InspectorSectionGroup):
        if not group.isVisible():
            continue
        style_rects = section_group_subcontrol_rects(group)
        box = group.rect().adjusted(-1, -1, 1, 1)
        title = style_rects["title"]
        indicator = style_rects["indicator"]
        if not box.contains(title):
            raise SmokeError(
                f"{label}: section {group.title()!r} title leaves the GroupBox."
            )
        if group.isCheckable() and not box.contains(indicator):
            raise SmokeError(
                f"{label}: section {group.title()!r} indicator leaves the GroupBox."
            )
        section = next(
            (
                child
                for child in _direct_children(group)
                if child.isVisible() and child.width() > 0 and child.height() > 0
            ),
            None,
        )
        if section is None:
            continue
        section_rect = QRect(section.mapTo(group, QPoint(0, 0)), section.size())
        if title.intersects(section_rect):
            raise SmokeError(
                f"{label}: section {group.title()!r} title covers contents."
            )
        if group.isCheckable() and indicator.intersects(section_rect):
            raise SmokeError(
                f"{label}: section {group.title()!r} indicator covers contents."
            )
        band = title.bottom()
        if group.isCheckable():
            band = max(band, indicator.bottom())
        if section_rect.top() < band + gap - 1:
            raise SmokeError(
                f"{label}: section {group.title()!r} contents sit inside the title band."
            )
