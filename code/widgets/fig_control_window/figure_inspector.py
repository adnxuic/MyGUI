"""Arrange Figure and Axes inspectors using the production container hierarchy."""

from __future__ import annotations

import os
from typing import Optional

from Qt_core import *

from code.figuremodify.components import AxesController, ComponentKind
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.py_empty_state import PyEmptyState
from code.widgets.fig_control_window.component_editors import EditorContext
from code.widgets.fig_control_window.component_editors import EditorPlacement
from code.widgets.fig_control_window.component_editors.containers import (
    AxesSemanticInspectorPanel,
    ChartInspectorStack,
    ElementInspectorStack,
    InspectorToolBox,
)
from code.widgets.fig_control_window.component_editors.dialogs import (
    ComponentBatchDeleteDialog,
)
from code.widgets.qss_func import qss_loader


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


def _show_batch_delete_menu(
    owner,
    button,
    toolbox,
    label: str,
    delete_callback,
    position,
) -> None:
    """Run the shared role-level partial-selection deletion workflow."""

    entries = toolbox.inspector_entries()
    if not entries or not callable(delete_callback):
        return
    menu = QMenu(owner)
    batch_delete = menu.addAction("Batch Delete...")
    if menu.exec(button.mapToGlobal(position)) != batch_delete:
        return
    _run_batch_delete_dialog(
        owner,
        toolbox,
        label,
        delete_callback,
    )


def _run_batch_delete_dialog(
    owner,
    toolbox,
    label: str,
    delete_callback,
) -> None:
    """Run the shared real selection dialog after menu confirmation."""

    entries = toolbox.inspector_entries()
    if not entries or not callable(delete_callback):
        return
    dialog = ComponentBatchDeleteDialog(
        entries,
        role_label=label,
        parent=owner,
    )
    accepted = dialog.exec() == QDialog.Accepted
    selected = dialog.selected_component_ids() if accepted else []
    dialog.deleteLater()
    if accepted and selected:
        delete_callback(selected, label)


class AxesInspectorPanel(QFrame):
    """Navigation and Inspector containers for one Matplotlib Axes."""

    def __init__(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library: ColorLibrary | None = None,
    ):
        super().__init__()
        self.setObjectName("axes_inspector_panel")
        self.setMouseTracking(True)

        self.axes_controller = axes_controller
        self.context = context
        self.axes = axes_controller.resolve_target()

        self.main_layout = QVBoxLayout()
        self._button_bars = []
        self._chart_button_bar = QFrame()
        self._element_button_bar = QFrame()
        self._button_bars.extend(
            (self._chart_button_bar, self._element_button_bar)
        )
        self._chart_buttons = {}
        self._element_buttons = {}
        self._chart_button_layout = QHBoxLayout()
        self._element_button_layout = QHBoxLayout()

        self.semantic_panel = AxesSemanticInspectorPanel(
            axes_controller,
            context,
            color_library,
        )
        self._chart_stack = ChartInspectorStack(self.axes)
        self._element_stack = ElementInspectorStack(self.axes)
        self._inspector_stack = QStackedWidget()
        self._inspector_stack.addWidget(self.semantic_panel)
        self._inspector_stack.addWidget(self._chart_stack)
        self._inspector_stack.addWidget(self._element_stack)

        self._chart_button_bar.setLayout(self._chart_button_layout)
        self._element_button_bar.setLayout(self._element_button_layout)
        self.main_layout.addWidget(self._inspector_stack)
        self.main_layout.addWidget(self._chart_button_bar)
        self.main_layout.addWidget(self._element_button_bar)
        self.setLayout(self.main_layout)

    def show_semantic_inspector(self) -> None:
        """Show semantic inspector."""

        self._show_category(0)

    def ensure_component_toolbox(
        self,
        kind: ComponentKind,
        key,
        label: str,
        delete_callback=None,
        *,
        placement: EditorPlacement | None = None,
    ) -> InspectorToolBox:
        """Ensure component toolbox exists and return it."""

        if placement is None:
            controllers = self.context.registry.query(
                parent_id=self.axes_controller.component_id,
                kind=kind,
                role=key,
            )
            if not controllers:
                raise ValueError(
                    "Cannot resolve Inspector placement without a component."
                )
            profile = (
                self.context.editor_manager.editor_registry.resolve_profile(
                    controllers[0]
                )
            )
            if profile is None:
                raise ValueError("Component has no registered Editor profile.")
            placement = profile.placement
        if placement is EditorPlacement.CHART:
            return self._ensure_toolbox(
                category_index=1,
                stack=self._chart_stack,
                button_layout=self._chart_button_layout,
                button_map=self._chart_buttons,
                key=key,
                label=label,
                delete_callback=delete_callback,
            )
        return self._ensure_toolbox(
            category_index=2,
            stack=self._element_stack,
            button_layout=self._element_button_layout,
            button_map=self._element_buttons,
            key=key,
            label=label,
            delete_callback=delete_callback,
        )

    def component_toolbox(
        self,
        kind: ComponentKind,
        key,
    ) -> InspectorToolBox | None:
        """Return an existing role toolbox without creating one."""

        del kind
        return (
            self._chart_stack.toolbox(key)
            or self._element_stack.toolbox(key)
        )

    def _ensure_toolbox(
        self,
        *,
        category_index: int,
        stack,
        button_layout,
        button_map,
        key,
        label: str,
        delete_callback=None,
    ) -> InspectorToolBox:
        toolbox = stack.toolbox(key)
        if toolbox is not None:
            return toolbox

        toolbox = stack.ensure_toolbox(key)
        toolbox.set_delete_callback(delete_callback, label)
        button = QPushButton(label)
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.clicked.connect(
            lambda: self._show_toolbox(category_index, stack, key)
        )
        button.customContextMenuRequested.connect(
            lambda position, target=button, target_toolbox=toolbox:
            _show_batch_delete_menu(
                self,
                target,
                target_toolbox,
                label,
                delete_callback,
                position,
            )
        )
        button_layout.addWidget(button)
        button_map[key] = button
        toolbox.set_empty_callback(
            lambda target_key=key, target_stack=stack:
            self.remove_component_toolbox(target_stack, target_key)
        )
        return toolbox

    def remove_component_toolbox(self, stack, key) -> bool:
        """Remove an empty role toolbox and its navigation button."""

        toolbox = stack.toolbox(key)
        if toolbox is None or toolbox.count():
            return False
        if stack is self._chart_stack:
            button_map = self._chart_buttons
            button_layout = self._chart_button_layout
        else:
            button_map = self._element_buttons
            button_layout = self._element_button_layout
        button = button_map.pop(key, None)
        if button is not None:
            button_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        return stack.remove_toolbox(key)

    def _show_toolbox(self, category_index: int, stack, key) -> None:
        stack.show_toolbox(key)
        self._show_category(category_index)

    def _show_category(self, index: int) -> None:
        self._inspector_stack.setCurrentIndex(index)
        self._update_navigation_layout(index)

    def _update_navigation_layout(self, active_index: int) -> None:
        for index in reversed(range(self.main_layout.count())):
            item = self.main_layout.itemAt(index)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for index, button_bar in enumerate(self._button_bars):
            if index == active_index:
                self.main_layout.addWidget(self._inspector_stack)
            self.main_layout.addWidget(button_bar)

        if active_index == len(self._button_bars):
            self.main_layout.addWidget(self._inspector_stack)


class FigureElementInspectorPanel(QFrame):
    """Provide the figure element inspector panel Qt widget."""

    def __init__(self):
        super().__init__()
        self.main_layout = QVBoxLayout()
        self._button_bar = QFrame()
        self._button_layout = QHBoxLayout()
        self._element_stack = ElementInspectorStack(None)
        self._buttons = {}

        self._button_bar.setLayout(self._button_layout)
        self.main_layout.addWidget(self._button_bar)
        self.main_layout.addWidget(self._element_stack)
        self.setLayout(self.main_layout)

    def ensure_toolbox(
        self,
        key,
        label: str,
        delete_callback=None,
    ) -> InspectorToolBox:
        """Ensure toolbox exists and return it."""

        toolbox = self._element_stack.toolbox(key)
        if toolbox is not None:
            return toolbox

        toolbox = self._element_stack.ensure_toolbox(key)
        toolbox.set_delete_callback(delete_callback, label)
        button = QPushButton(label)
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.clicked.connect(
            lambda: self._element_stack.show_toolbox(key)
        )
        button.customContextMenuRequested.connect(
            lambda position, target=button, target_toolbox=toolbox:
            _show_batch_delete_menu(
                self,
                target,
                target_toolbox,
                label,
                delete_callback,
                position,
            )
        )
        self._button_layout.addWidget(button)
        self._buttons[key] = button
        toolbox.set_empty_callback(
            lambda target_key=key: self.remove_toolbox(target_key)
        )
        return toolbox

    def remove_toolbox(self, key) -> bool:
        """Remove an empty Figure-element toolbox and navigation button."""

        toolbox = self._element_stack.toolbox(key)
        if toolbox is None or toolbox.count():
            return False
        button = self._buttons.pop(key, None)
        if button is not None:
            self._button_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        return self._element_stack.remove_toolbox(key)


class FigureInspectorPanel(QFrame):
    """Inspector navigation for one Figure."""

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setObjectName("figure_inspector_panel")

        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self._axes_button_bar = QFrame()
        self._axes_button_layout = QHBoxLayout()
        self._inspector_stack = QStackedLayout()
        self._axes_button_bar.setLayout(self._axes_button_layout)
        self.main_layout.addWidget(self._axes_button_bar)
        self.main_layout.addLayout(self._inspector_stack)
        self.setLayout(self.main_layout)

        self._axes_count = 0
        self._axes_entries = []
        self.no_axes_state = PyEmptyState(
            "No axes",
            "Choose a layout from the command bar before adding charts or axes elements.",
        )
        self._figure_elements_panel = FigureElementInspectorPanel()
        self._inspector_stack.addWidget(self.no_axes_state)
        self._inspector_stack.addWidget(self._figure_elements_panel)

        figure_button = QPushButton("figure")
        figure_button.clicked.connect(self.show_figure_elements)
        self._axes_button_layout.addWidget(figure_button)

    def add_axes_inspector(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library: ColorLibrary | None = None,
        delete_callback=None,
    ):
        """Add axes inspector."""

        axes_inspector = AxesInspectorPanel(
            axes_controller,
            context,
            color_library,
        )
        self._inspector_stack.addWidget(axes_inspector)
        self.show_axes_inspector(axes_inspector)

        self._axes_count += 1
        button = QPushButton("axe" + str(self._axes_count))
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.clicked.connect(
            lambda: self.show_axes_inspector(axes_inspector)
        )
        button.customContextMenuRequested.connect(
            lambda position, target=button, component_id=(
                axes_controller.component_id
            ):
            self._show_axes_context_menu(
                target,
                component_id,
                delete_callback,
                position,
            )
        )
        self._axes_button_layout.addWidget(button)
        self._axes_entries.append(
            (axes_controller.component_id, axes_inspector, button)
        )
        return button

    def _show_axes_context_menu(
        self,
        button,
        component_id: str,
        delete_callback,
        position,
    ) -> None:
        if not callable(delete_callback):
            return
        menu = QMenu(self)
        delete_axes = menu.addAction("Delete Axes")
        if menu.exec(button.mapToGlobal(position)) == delete_axes:
            delete_callback(component_id)

    def remove_axes_inspector(self, component_id: str) -> bool:
        """Remove one Axes panel/button and relabel remaining entries."""

        for index, (target_id, inspector, button) in enumerate(
            tuple(self._axes_entries)
        ):
            if target_id != component_id:
                continue
            self._axes_entries.pop(index)
            self._inspector_stack.removeWidget(inspector)
            inspector.setParent(None)
            inspector.deleteLater()
            self._axes_button_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
            self._axes_count = len(self._axes_entries)
            for label_index, (_id, _panel, target_button) in enumerate(
                self._axes_entries,
                start=1,
            ):
                target_button.setText(f"axe{label_index}")
            if not self._axes_entries:
                self._inspector_stack.setCurrentWidget(self.no_axes_state)
            return True
        return False

    def axes_inspector(self, component_id: str):
        """Return the Axes panel registered for a stable component ID."""

        for target_id, inspector, _button in self._axes_entries:
            if target_id == component_id:
                return inspector
        return None

    def show_axes_inspector(
        self,
        axes_inspector: AxesInspectorPanel,
    ) -> None:
        """Show axes inspector."""

        self._inspector_stack.setCurrentWidget(axes_inspector)
        axes_inspector.show_semantic_inspector()

    def find_axes_inspector(self, axes) -> Optional[AxesInspectorPanel]:
        """Find axes inspector matching the supplied identity."""

        for index in range(self._inspector_stack.count()):
            widget = self._inspector_stack.widget(index)
            if (
                isinstance(widget, AxesInspectorPanel)
                and widget.axes == axes
            ):
                return widget
        return None

    def show_figure_elements(self) -> None:
        """Show figure elements."""

        self._inspector_stack.setCurrentWidget(
            self._figure_elements_panel
        )

    def ensure_figure_element_toolbox(
        self,
        key,
        label: str,
        delete_callback=None,
    ) -> InspectorToolBox:
        """Ensure figure element toolbox exists and return it."""

        return self._figure_elements_panel.ensure_toolbox(
            key,
            label,
            delete_callback,
        )

    def current_panel(self):
        """Return the current panel."""

        return self._inspector_stack.currentWidget()


class FigureInspectorHost(QFrame):
    """Project-scoped Figure Inspector host."""

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setObjectName("figure_inspector_host")
        self.setStyleSheet(qss_loader(qss_path))

        self._figure_stack = QStackedLayout()
        self._figure_stack.setSpacing(0)
        self._figure_stack.setContentsMargins(0, 0, 0, 0)
        self.empty_state = PyEmptyState(
            "No project",
            "Choose a style to create a project and open its inspector.",
        )
        self._figure_stack.addWidget(self.empty_state)
        self.setLayout(self._figure_stack)

    def add_figure_inspector(self) -> FigureInspectorPanel:
        """Add figure inspector."""

        figure_inspector = FigureInspectorPanel()
        self._figure_stack.addWidget(figure_inspector)
        self._figure_stack.setCurrentWidget(figure_inspector)
        return figure_inspector

    def show_figure_inspector(
        self,
        project_index: int,
    ) -> Optional[FigureInspectorPanel]:
        """Show figure inspector."""

        figure_inspector = self._figure_inspector_at(project_index)
        if figure_inspector is None:
            self.show_empty_state()
            return None
        self._figure_stack.setCurrentWidget(figure_inspector)
        return figure_inspector

    def current_figure_inspector(self) -> Optional[FigureInspectorPanel]:
        """Return the current figure inspector."""

        widget = self._figure_stack.currentWidget()
        if isinstance(widget, FigureInspectorPanel):
            return widget
        return None

    def remove_figure_inspector(self, project_index: int) -> bool:
        """Remove figure inspector."""

        figure_inspector = self._figure_inspector_at(project_index)
        if figure_inspector is None:
            return False
        self._figure_stack.removeWidget(figure_inspector)
        figure_inspector.deleteLater()
        if self._figure_stack.count() == 1:
            self.show_empty_state()
        return True

    def show_empty_state(self) -> None:
        """Show empty state."""

        self._figure_stack.setCurrentWidget(self.empty_state)

    def clear_figure_inspectors(self) -> None:
        """Clear figure inspectors."""

        for index in range(self._figure_stack.count() - 1, 0, -1):
            widget = self._figure_stack.widget(index)
            self._figure_stack.removeWidget(widget)
            widget.deleteLater()
        self.show_empty_state()

    def _figure_inspector_at(
        self,
        project_index: int,
    ) -> Optional[FigureInspectorPanel]:
        stack_index = int(project_index) + 1
        if stack_index < 1 or stack_index >= self._figure_stack.count():
            return None
        widget = self._figure_stack.widget(stack_index)
        if isinstance(widget, FigureInspectorPanel):
            return widget
        return None
