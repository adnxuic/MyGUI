from __future__ import annotations

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
        toolbox = self._toolboxes.get(key)
        if toolbox is None:
            toolbox = InspectorToolBox(self)
            self._toolboxes[key] = toolbox
            self.toolbox_stack.addWidget(toolbox)
        self.toolbox_stack.setCurrentWidget(toolbox)
        return toolbox

    def toolbox(self, key):
        return self._toolboxes.get(key)

    def show_toolbox(self, key) -> bool:
        toolbox = self.toolbox(key)
        if toolbox is None:
            return False
        self.toolbox_stack.setCurrentWidget(toolbox)
        return True


class ElementInspectorStack(QFrame):
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
        toolbox = self._toolboxes.get(key)
        if toolbox is None:
            toolbox = InspectorToolBox(self)
            self._toolboxes[key] = toolbox
            self.toolbox_stack.addWidget(toolbox)
        self.toolbox_stack.setCurrentWidget(toolbox)
        return toolbox

    def toolbox(self, key):
        return self._toolboxes.get(key)

    def show_toolbox(self, key) -> bool:
        toolbox = self.toolbox(key)
        if toolbox is None:
            return False
        self.toolbox_stack.setCurrentWidget(toolbox)
        return True


class InspectorToolBox(QToolBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self._item_count = 0
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    def add_inspector(self, inspector, label: str):
        index = self.addItem(inspector, label + str(self._item_count))
        self._item_count += 1
        return index

    def remove_inspector(self, inspector) -> bool:
        index = self.indexOf(inspector)
        if index < 0:
            return False
        self.removeItem(index)
        inspector.setParent(None)
        inspector.deleteLater()
        return True

    def contextMenuEvent(self, event):
        inspector = self.currentWidget()
        if (
            inspector is None
            or not getattr(inspector, "can_delete", True)
            or not callable(getattr(inspector, "delete_object", None))
        ):
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_inspector(self.currentIndex())

    def delete_inspector(self, index: int | None = None):
        if index is None:
            index = self.currentIndex()
        if index is None or index < 0 or index >= self.count():
            return False
        inspector = self.widget(index)
        delete_object = getattr(inspector, "delete_object", None)
        if not callable(delete_object):
            return False
        result = delete_object()
        if result is False:
            return False
        self.remove_inspector(inspector)
        return True
