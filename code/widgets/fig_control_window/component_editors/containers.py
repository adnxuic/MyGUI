"""Provide reusable Inspector stacks and toolboxes."""

from __future__ import annotations

from dataclasses import dataclass
import os

from Qt_core import *

from code.figuremodify.components import (
    AxesController,
    ComponentKind,
    ComponentRole,
)
from code.widgets import qss_func
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.py_empty_state import PyEmptyState

from .context import EditorContext


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(
    os.path.dirname(current_path),
    "all_mod_widgets",
    "style.qss",
)


class AxesSemanticInspectorPanel(QFrame):
    """Semantic Component Inspector pages for one Axes."""

    def __init__(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library: ColorLibrary | None = None,
    ):
        super().__init__()
        del color_library
        self.axes_controller = axes_controller
        self.context = context
        self.axes = axes_controller.resolve_target()

        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.section_toolbox = QToolBox(self)

        self.general_inspector = self._inspector(axes_controller)
        x_axis = self._axis_controller(ComponentRole.X_AXIS)
        y_axis = self._axis_controller(ComponentRole.Y_AXIS)
        axes_page = self._component_group(
            (("X Axis", x_axis), ("Y Axis", y_axis))
        )
        ticks_grid_page = self._ticks_grid_page(
            (("X", "x", x_axis), ("Y", "y", y_axis))
        )
        spines_page = self._spines_page()

        title = context.registry.find_one(
            parent_id=axes_controller.component_id,
            role=ComponentRole.TITLE,
        )
        x_label = context.registry.find_one(
            parent_id=x_axis.component_id,
            role=ComponentRole.X_LABEL,
        )
        y_label = context.registry.find_one(
            parent_id=y_axis.component_id,
            role=ComponentRole.Y_LABEL,
        )
        title_labels_page = self._component_group(
            (
                ("Title", title),
                ("X Label", x_label),
                ("Y Label", y_label),
            )
        )
        legend = context.registry.find_one(
            parent_id=axes_controller.component_id,
            kind=ComponentKind.LEGEND,
        )
        self.legend_inspector = self._inspector(legend)

        self.section_pages = []
        for widget, title_text in (
            (self.general_inspector, "General"),
            (axes_page, "X/Y Axis"),
            (spines_page, "Spines"),
            (ticks_grid_page, "Ticks/Grid"),
            (title_labels_page, "Title/Labels"),
            (self.legend_inspector, "Legend"),
        ):
            scroll_page = self._scrollable_page(widget)
            self.section_pages.append(scroll_page)
            self.section_toolbox.addItem(scroll_page, title_text)
        self.main_layout.addWidget(self.section_toolbox)

    def _inspector(self, controller):
        return self.context.editor_manager.create(
            controller,
            context=self.context,
            parent=self,
        )

    def _component_group(self, entries):
        page = QFrame(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        for title, controller in entries:
            group = QGroupBox(title, page)
            group_layout = QVBoxLayout(group)
            group_layout.addWidget(self._inspector(controller))
            layout.addWidget(group)
        layout.addStretch()
        return page

    def _axis_controller(self, axis_role):
        return self.context.registry.find_one(
            parent_id=self.axes_controller.component_id,
            kind=ComponentKind.AXIS,
            role=axis_role,
        )

    def _ticks_grid_page(self, axes):
        entries = []
        for axis_label, axis_name, axis in axes:
            for level, tick_role, tick_label_role in (
                (
                    "major",
                    ComponentRole.MAJOR_TICK,
                    ComponentRole.MAJOR_TICK_LABEL,
                ),
                (
                    "minor",
                    ComponentRole.MINOR_TICK,
                    ComponentRole.MINOR_TICK_LABEL,
                ),
            ):
                tick = self.context.registry.find_one(
                    parent_id=axis.component_id,
                    kind=ComponentKind.TICK_GROUP,
                    role=tick_role,
                    selector={"axis": axis_name, "level": level},
                )
                tick_label = self.context.registry.find_one(
                    parent_id=tick.component_id,
                    kind=ComponentKind.TICK_LABEL_GROUP,
                    role=tick_label_role,
                )
                grid = self.context.registry.find_one(
                    parent_id=axis.component_id,
                    kind=ComponentKind.GRID,
                    selector={"axis": axis_name, "level": level},
                )
                display = level.title()
                entries.extend(
                    (
                        (f"{axis_label} {display} ticks", tick),
                        (
                            f"{axis_label} {display} tick labels",
                            tick_label,
                        ),
                        (f"{axis_label} {display} grid", grid),
                    )
                )
        return self._component_group(entries)

    def _spines_page(self):
        entries = []
        for side in ("bottom", "top", "left", "right"):
            controller = self.context.registry.find_one(
                parent_id=self.axes_controller.component_id,
                kind=ComponentKind.SPINE,
                selector={"name": side},
            )
            entries.append((side.title(), controller))
        return self._component_group(entries)

    @staticmethod
    def _scrollable_page(widget):
        scroll_page = QScrollArea()
        scroll_page.setObjectName("inspector_section_scroll_area")
        scroll_page.setFrameShape(QFrame.NoFrame)
        scroll_page.setWidgetResizable(True)
        scroll_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_page.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll_page.setWidget(widget)
        return scroll_page


class ChartInspectorStack(QFrame):
    """Provide the chart inspector stack Qt widget."""

    def __init__(self, axes):
        super().__init__()
        self.axes = axes
        self._toolboxes = {}
        self.main_layout = QVBoxLayout(self)
        self.toolbox_stack = QStackedWidget(self)
        self.empty_state = PyEmptyState(
            "No chart selected",
            "Add or select a chart object to edit its parameters.",
        )
        self.toolbox_stack.addWidget(self.empty_state)
        self.main_layout.addWidget(self.toolbox_stack)

    def ensure_toolbox(self, key):
        """Ensure toolbox exists and return it."""

        toolbox = self._toolboxes.get(key)
        if toolbox is None:
            toolbox = InspectorToolBox(self)
            self._toolboxes[key] = toolbox
            self.toolbox_stack.addWidget(toolbox)
        self.toolbox_stack.setCurrentWidget(toolbox)
        return toolbox

    def toolbox(self, key):
        """Return the requested toolbox."""

        return self._toolboxes.get(key)

    def show_toolbox(self, key) -> bool:
        """Show toolbox."""

        toolbox = self.toolbox(key)
        if toolbox is None:
            return False
        self.toolbox_stack.setCurrentWidget(toolbox)
        return True

    def remove_toolbox(self, key) -> bool:
        """Remove an empty toolbox and return to the stack empty state."""

        toolbox = self._toolboxes.pop(key, None)
        if toolbox is None:
            return False
        was_current = self.toolbox_stack.currentWidget() is toolbox
        self.toolbox_stack.removeWidget(toolbox)
        if was_current:
            self.toolbox_stack.setCurrentWidget(self.empty_state)
        toolbox.setParent(None)
        toolbox.deleteLater()
        return True


class ElementInspectorStack(QFrame):
    """Provide the element inspector stack Qt widget."""

    def __init__(self, axes):
        super().__init__()
        self.axes = axes
        self._toolboxes = {}
        self.main_layout = QVBoxLayout(self)
        self.toolbox_stack = QStackedLayout()
        self.empty_state = PyEmptyState(
            "No element selected",
            "Add or select a figure element to edit its parameters.",
        )
        self.toolbox_stack.addWidget(self.empty_state)
        self.main_layout.addLayout(self.toolbox_stack)

    def ensure_toolbox(self, key):
        """Ensure toolbox exists and return it."""

        toolbox = self._toolboxes.get(key)
        if toolbox is None:
            toolbox = InspectorToolBox(self)
            self._toolboxes[key] = toolbox
            self.toolbox_stack.addWidget(toolbox)
        self.toolbox_stack.setCurrentWidget(toolbox)
        return toolbox

    def toolbox(self, key):
        """Return the requested toolbox."""

        return self._toolboxes.get(key)

    def show_toolbox(self, key) -> bool:
        """Show toolbox."""

        toolbox = self.toolbox(key)
        if toolbox is None:
            return False
        self.toolbox_stack.setCurrentWidget(toolbox)
        return True

    def remove_toolbox(self, key) -> bool:
        """Remove an empty toolbox and return to the stack empty state."""

        toolbox = self._toolboxes.pop(key, None)
        if toolbox is None:
            return False
        was_current = self.toolbox_stack.currentWidget() is toolbox
        self.toolbox_stack.removeWidget(toolbox)
        if was_current:
            self.toolbox_stack.setCurrentWidget(self.empty_state)
        toolbox.setParent(None)
        toolbox.deleteLater()
        return True


class InspectorHeader(QToolButton):
    """Explicit accordion header bound to one stable component ID."""

    deleteRequested = Signal(str)

    def __init__(self, component_id: str, text: str, parent=None):
        super().__init__(parent)
        if not component_id:
            raise ValueError("Inspector header requires a stable component ID.")
        if not isinstance(text, str) or not text:
            raise ValueError("Inspector header requires display text.")
        self.component_id = str(component_id)
        self.setObjectName("inspector_toolbox_header")
        self.setText(text)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setArrowType(Qt.RightArrow)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)


@dataclass(slots=True)
class _InspectorEntry:
    component_id: str
    label: str
    inspector: QWidget
    header: InspectorHeader


class InspectorToolBox(QFrame):
    """Own an explicit, stable-ID accordion of component Inspectors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self._item_count = 0
        self._entries: list[_InspectorEntry] = []
        self._entry_by_id: dict[str, _InspectorEntry] = {}
        self._current: QWidget | None = None
        self._empty_callback = None
        self._delete_callback = None
        self._role_label = "component"
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addStretch()

    def set_empty_callback(self, callback) -> None:
        """Set the callback invoked after the last Inspector is removed."""

        self._empty_callback = callback

    def set_delete_callback(self, callback, role_label="component") -> None:
        """Set the sole business callback used by header and batch deletion."""

        self._delete_callback = callback
        self._role_label = str(role_label or "component")

    def add_inspector(self, inspector, label: str):
        """Atomically add a validated accordion entry."""

        controller = getattr(inspector, "controller", None)
        component_id = getattr(controller, "component_id", None)
        if not component_id:
            raise ValueError(
                "Inspector labels require a stable component ID."
            )
        component_id = str(component_id)
        if component_id in self._entry_by_id:
            raise ValueError(
                f"Duplicate Inspector component ID {component_id!r}."
            )
        display_label = f"{label}{self._item_count}"
        header = InspectorHeader(component_id, display_label, self)
        header.clicked.connect(
            lambda _checked=False, target=inspector:
            self.setCurrentWidget(target)
        )
        header.customContextMenuRequested.connect(
            lambda position, target=header:
            self._show_header_context_menu(target, position)
        )
        entry = _InspectorEntry(
            component_id,
            display_label,
            inspector,
            header,
        )
        previous_current = self._current
        index = len(self._entries)
        try:
            self._entries.append(entry)
            self._entry_by_id[component_id] = entry
            self.main_layout.insertWidget(self.main_layout.count() - 1, header)
            self.main_layout.insertWidget(
                self.main_layout.count() - 1,
                inspector,
            )
            inspector.setVisible(False)
            if previous_current is None:
                self.setCurrentWidget(inspector)
        except Exception:
            self.main_layout.removeWidget(inspector)
            self.main_layout.removeWidget(header)
            self._entry_by_id.pop(component_id, None)
            if entry in self._entries:
                self._entries.remove(entry)
            header.setParent(None)
            header.deleteLater()
            self._current = previous_current
            if previous_current is not None:
                previous_current.setVisible(True)
            raise
        self._item_count += 1
        return index

    def remove_inspector(self, inspector) -> bool:
        """Remove inspector."""

        index = self.indexOf(inspector)
        if index < 0:
            return False
        entry = self._entries[index]
        was_current = inspector is self._current
        self._entries.pop(index)
        self._entry_by_id.pop(entry.component_id, None)
        self.main_layout.removeWidget(entry.header)
        self.main_layout.removeWidget(inspector)
        entry.header.setParent(None)
        entry.header.deleteLater()
        inspector.setParent(None)
        inspector.deleteLater()
        if was_current:
            self._current = None
            if self._entries:
                next_index = min(index, len(self._entries) - 1)
                self.setCurrentWidget(self._entries[next_index].inspector)
        if self.count() == 0 and callable(self._empty_callback):
            self._empty_callback()
        return True

    def count(self) -> int:
        """Return the number of Inspector entries."""

        return len(self._entries)

    def widget(self, index: int):
        """Return the Inspector at ``index`` or ``None``."""

        if index < 0 or index >= len(self._entries):
            return None
        return self._entries[index].inspector

    def indexOf(self, inspector) -> int:
        """Return the stable entry index for an Inspector."""

        for index, entry in enumerate(self._entries):
            if entry.inspector is inspector:
                return index
        return -1

    def itemText(self, index: int) -> str:
        """Return the immutable display label at ``index``."""

        if index < 0 or index >= len(self._entries):
            return ""
        return self._entries[index].label

    def currentWidget(self):
        """Return the expanded Inspector, if any."""

        return self._current

    def currentIndex(self) -> int:
        """Return the expanded Inspector index."""

        return self.indexOf(self._current)

    def setCurrentIndex(self, index: int) -> None:
        """Expand the Inspector at ``index``."""

        target = self.widget(index)
        if target is not None:
            self.setCurrentWidget(target)

    def setCurrentWidget(self, inspector) -> None:
        """Expand exactly one Inspector without changing entry identity."""

        if self.indexOf(inspector) < 0:
            return
        self._current = inspector
        for entry in self._entries:
            active = entry.inspector is inspector
            entry.inspector.setVisible(active)
            entry.header.setChecked(active)
            entry.header.setArrowType(
                Qt.DownArrow if active else Qt.RightArrow
            )

    def inspector_entries(self) -> list[tuple[str, str]]:
        """Return visible component IDs and labels in page order."""

        return [
            (entry.component_id, entry.label)
            for entry in self._entries
        ]

    def inspector(self, component_id: str):
        """Return the visible Inspector associated with a stable ID."""

        entry = self._entry_by_id.get(str(component_id))
        return entry.inspector if entry is not None else None

    def header(self, component_id: str):
        """Return the explicit Header associated with a stable ID."""

        entry = self._entry_by_id.get(str(component_id))
        return entry.header if entry is not None else None

    def _show_header_context_menu(self, header, position) -> None:
        component_id = getattr(header, "component_id", None)
        inspector = self.inspector(component_id) if component_id else None
        if (
            inspector is None
            or not getattr(inspector, "can_delete", True)
        ):
            return
        if self._confirm_header_delete(header, position):
            header.deleteRequested.emit(component_id)
            self._submit_delete(component_id, inspector)

    def _confirm_header_delete(self, header, position) -> bool:
        """Return whether the explicit Header menu confirmed deletion."""

        menu = QMenu(self)
        delete_action = menu.addAction("Delete Component")
        action = menu.exec(header.mapToGlobal(position))
        return action == delete_action

    def _submit_delete(self, component_id: str, inspector) -> bool:
        if callable(self._delete_callback):
            return self._delete_callback(
                (component_id,),
                self._role_label,
            ) is not False
        delete_object = getattr(inspector, "delete_object", None)
        return bool(callable(delete_object) and delete_object() is not False)

    def delete_inspector(self, target=None):
        """Delete inspector."""

        if target is None:
            inspector = self.currentWidget()
        elif isinstance(target, int):
            if target < 0 or target >= self.count():
                return False
            inspector = self.widget(target)
        else:
            inspector = target
        if inspector is None or self.indexOf(inspector) < 0:
            return False
        controller = getattr(inspector, "controller", None)
        component_id = getattr(controller, "component_id", None)
        if not component_id:
            return False
        # The Registry REMOVED event is the sole production path that disposes
        # and removes the Inspector through ComponentEditorManager.
        return self._submit_delete(str(component_id), inspector)
