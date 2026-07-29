"""Arrange Figure and Axes inspectors using the production container hierarchy."""

from __future__ import annotations

import os
from typing import Optional

from Qt_core import *

from code.figuremodify.components import AxesController, ComponentKind
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.py_empty_state import PyEmptyState
from code.widgets.fig_control_window.component_editors import EditorContext
from code.widgets.fig_control_window.component_editors.containers import (
    AxesSemanticInspectorPanel,
    ChartInspectorStack,
    ElementInspectorStack,
    InspectorToolBox,
)
from code.widgets.qss_func import qss_loader


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


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
    ) -> InspectorToolBox:
        """Ensure component toolbox exists and return it."""

        if kind in {ComponentKind.LINE, ComponentKind.SCATTER}:
            return self._ensure_toolbox(
                category_index=1,
                stack=self._chart_stack,
                button_layout=self._chart_button_layout,
                key=key,
                label=label,
            )
        return self._ensure_toolbox(
            category_index=2,
            stack=self._element_stack,
            button_layout=self._element_button_layout,
            key=key,
            label=label,
        )

    def _ensure_toolbox(
        self,
        *,
        category_index: int,
        stack,
        button_layout,
        key,
        label: str,
    ) -> InspectorToolBox:
        toolbox = stack.toolbox(key)
        if toolbox is not None:
            return toolbox

        toolbox = stack.ensure_toolbox(key)
        button = QPushButton(label)
        button.clicked.connect(
            lambda: self._show_toolbox(category_index, stack, key)
        )
        button_layout.addWidget(button)
        return toolbox

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

        self._button_bar.setLayout(self._button_layout)
        self.main_layout.addWidget(self._button_bar)
        self.main_layout.addWidget(self._element_stack)
        self.setLayout(self.main_layout)

    def ensure_toolbox(self, key, label: str) -> InspectorToolBox:
        """Ensure toolbox exists and return it."""

        toolbox = self._element_stack.toolbox(key)
        if toolbox is not None:
            return toolbox

        toolbox = self._element_stack.ensure_toolbox(key)
        button = QPushButton(label)
        button.clicked.connect(
            lambda: self._element_stack.show_toolbox(key)
        )
        self._button_layout.addWidget(button)
        return toolbox


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
        button.clicked.connect(
            lambda: self.show_axes_inspector(axes_inspector)
        )
        self._axes_button_layout.addWidget(button)
        return button

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
    ) -> InspectorToolBox:
        """Ensure figure element toolbox exists and return it."""

        return self._figure_elements_panel.ensure_toolbox(key, label)

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
