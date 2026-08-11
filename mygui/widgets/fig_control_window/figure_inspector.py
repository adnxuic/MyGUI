"""Arrange stable-ID, single-Component Inspectors by Figure and Axes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from PySide6.QtWidgets import QFrame, QStackedWidget, QVBoxLayout

from mygui.figuremodify.components import (
    AxesController,
    ComponentKind,
)
from mygui.widgets.common_widget.py_empty_state import PyEmptyState
from mygui.widgets.fig_control_window.component_editors import (
    EditorKey,
    EditorContext,
    EditorPlacement,
)
from mygui.widgets.fig_control_window.component_editors.containers import (
    AxesSemanticInspectorPanel,
    ChartInspectorStack,
    ElementInspectorStack,
    InspectorToolBox,
)
from mygui.widgets.qss_func import qss_loader


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


@dataclass(slots=True)
class AxesInspectorRemoval:
    """Reversible detachment token for one Axes Inspector panel."""

    component_id: str
    panel: "AxesInspectorPanel"
    index: int
    was_current: bool


class AxesInspectorPanel(QFrame):
    """Own semantic, Chart, and Element Inspector stacks for one Axes."""

    def __init__(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library=None,
    ):
        super().__init__()
        self.setObjectName("axes_inspector_panel")
        self.axes_controller = axes_controller
        self.context = context
        self.axes = axes_controller.resolve_target()

        self.semantic_panel = AxesSemanticInspectorPanel(
            axes_controller,
            context,
            color_library,
        )
        self._chart_stack = ChartInspectorStack(self.axes)
        self._element_stack = ElementInspectorStack(self.axes)
        self._inspector_stack = QStackedWidget(self)
        self._inspector_stack.addWidget(self.semantic_panel)
        self._inspector_stack.addWidget(self._chart_stack)
        self._inspector_stack.addWidget(self._element_stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._inspector_stack)
        self._disposed = False

        self.show_component(axes_controller.component_id)

    def ensure_component(self, component_id: str):
        """Create the exact Axes-owned Inspector on first selection."""

        component_id = str(component_id)
        existing = self.inspector(component_id)
        if existing is not None:
            return existing
        registry = self.context.registry
        controller = registry.get(component_id)
        axes_ancestor = registry.ancestor(component_id, kind=ComponentKind.AXES)
        if (
            axes_ancestor is None
            or axes_ancestor.component_id != self.axes_controller.component_id
        ):
            raise ValueError("Component does not belong to this Axes.")
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            controller
        )
        if profile is None:
            raise ValueError(
                f"Component {component_id!r} has no registered Editor profile."
            )
        if profile.placement is EditorPlacement.SEMANTIC:
            return self.semantic_panel.ensure_inspector(component_id)
        if profile.placement is EditorPlacement.CHART:
            stack = self._chart_stack
        elif profile.placement is EditorPlacement.ELEMENT:
            stack = self._element_stack
        else:
            raise ValueError(
                f"Invalid Axes Inspector placement {profile.placement.value!r}."
            )
        editor_key: EditorKey = (controller.state.kind, controller.state.role)
        toolbox = stack.ensure_toolbox(editor_key)
        toolbox.set_empty_callback(
            lambda target_stack=stack, target_key=editor_key:
            self._remove_component_toolbox(target_stack, target_key)
        )
        inspector = self.context.editor_manager.create(
            controller,
            context=self.context,
            parent=toolbox,
            remover=toolbox.remove_inspector,
        )
        try:
            toolbox.add_inspector(inspector)
        except Exception:
            inspector.dispose()
            inspector.setParent(None)
            inspector.deleteLater()
            self._remove_component_toolbox(stack, editor_key)
            raise
        return inspector

    def ensure_component_toolbox(
        self,
        editor_key: EditorKey,
        placement: EditorPlacement,
    ) -> InspectorToolBox:
        """Ensure a toolbox using an explicit complete Editor key."""

        stack = (
            self._chart_stack
            if placement is EditorPlacement.CHART
            else self._element_stack
            if placement is EditorPlacement.ELEMENT
            else None
        )
        if stack is None:
            raise ValueError("Semantic/Figure profiles do not use a toolbox.")
        toolbox = stack.ensure_toolbox(editor_key)
        toolbox.set_empty_callback(
            lambda target_stack=stack, target_key=editor_key:
            self._remove_component_toolbox(target_stack, target_key)
        )
        return toolbox

    def component_toolbox(
        self,
        editor_key: EditorKey,
    ) -> InspectorToolBox | None:
        """Return an existing internal toolbox without creating one."""

        return (
            self._chart_stack.toolbox(editor_key)
            or self._element_stack.toolbox(editor_key)
        )

    def _remove_component_toolbox(self, stack, key) -> bool:
        """Remove one empty internal toolbox."""

        toolbox = stack.toolbox(key)
        if toolbox is None or toolbox.count():
            return False
        return stack.remove_toolbox(key)

    def show_component(self, component_id: str) -> bool:
        """Show exactly one Axes-owned Component Inspector."""

        try:
            inspector = self.ensure_component(component_id)
        except (KeyError, ValueError):
            return False
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            inspector.controller
        )
        if profile.placement is EditorPlacement.SEMANTIC:
            self.semantic_panel.show_component(component_id)
            self._inspector_stack.setCurrentWidget(self.semantic_panel)
            return True
        if profile.placement is EditorPlacement.CHART:
            self._chart_stack.show_component(component_id)
            self._inspector_stack.setCurrentWidget(self._chart_stack)
            return True
        if profile.placement is EditorPlacement.ELEMENT:
            self._element_stack.show_component(component_id)
            self._inspector_stack.setCurrentWidget(self._element_stack)
            return True
        return False

    def inspector(self, component_id: str):
        """Return an Inspector owned by this Axes panel."""

        return (
            self.semantic_panel.inspector(component_id)
            or self._chart_stack.inspector(component_id)
            or self._element_stack.inspector(component_id)
        )

    def remove_component(self, component_id: str) -> bool:
        """Remove one cached Inspector without mutating business state."""

        inspector = self.inspector(component_id)
        if inspector is None:
            return False
        if self.semantic_panel.inspector(component_id) is inspector:
            return self.semantic_panel.remove_inspector(inspector)
        for stack in (self._chart_stack, self._element_stack):
            if stack.remove_component(component_id):
                return True
        return False

    def current_component_id(self) -> str | None:
        current = self._inspector_stack.currentWidget()
        if current is self.semantic_panel:
            return self.semantic_panel.current_component_id()
        for stack in (self._chart_stack, self._element_stack):
            if current is stack:
                return stack.current_component_id()
        return None

    def dispose(self) -> None:
        """Recursively release all Inspectors owned by this Axes."""

        if self._disposed:
            return
        self._disposed = True
        for container in (
            self.semantic_panel,
            self._chart_stack,
            self._element_stack,
        ):
            try:
                container.dispose()
            except Exception:
                pass

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class FigureElementInspectorPanel(QFrame):
    """Own free Figure-level element Inspectors without navigation labels."""

    def __init__(self, context: EditorContext):
        super().__init__()
        self.context = context
        self._disposed = False
        self._element_stack = ElementInspectorStack(None, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._element_stack)

    def ensure_toolbox(self, editor_key: EditorKey) -> InspectorToolBox:
        toolbox = self._element_stack.ensure_toolbox(editor_key)
        toolbox.set_empty_callback(
            lambda target_key=editor_key: self.remove_toolbox(target_key)
        )
        return toolbox

    def ensure_component(self, component_id: str):
        """Create one Figure-level Element Inspector on first selection."""

        component_id = str(component_id)
        existing = self.inspector(component_id)
        if existing is not None:
            return existing
        controller = self.context.registry.get(component_id)
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            controller
        )
        if profile is None or profile.placement is not EditorPlacement.ELEMENT:
            raise ValueError("Component is not a Figure element.")
        editor_key: EditorKey = (controller.state.kind, controller.state.role)
        toolbox = self.ensure_toolbox(editor_key)
        inspector = self.context.editor_manager.create(
            controller,
            context=self.context,
            parent=toolbox,
            remover=toolbox.remove_inspector,
        )
        try:
            toolbox.add_inspector(inspector)
        except Exception:
            inspector.dispose()
            inspector.setParent(None)
            inspector.deleteLater()
            self.remove_toolbox(editor_key)
            raise
        return inspector

    def remove_toolbox(self, key) -> bool:
        toolbox = self._element_stack.toolbox(key)
        if toolbox is None or toolbox.count():
            return False
        return self._element_stack.remove_toolbox(key)

    def show_component(self, component_id: str) -> bool:
        try:
            self.ensure_component(component_id)
        except (KeyError, ValueError):
            return False
        return self._element_stack.show_component(component_id)

    def inspector(self, component_id: str):
        return self._element_stack.inspector(component_id)

    def remove_component(self, component_id: str) -> bool:
        return self._element_stack.remove_component(component_id)

    def current_component_id(self) -> str | None:
        return self._element_stack.current_component_id()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._element_stack.dispose()

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class FigureInspectorPanel(QFrame):
    """Own the Figure root, Figure elements, and Axes panels."""

    def __init__(
        self,
        root_controller,
        context: EditorContext,
        color_library=None,
    ):
        super().__init__()
        self.setObjectName("figure_inspector_panel")
        self.context = context
        self.root_component_id = root_controller.component_id
        self._axes_panels: dict[str, AxesInspectorPanel] = {}
        self._disposed = False

        self._inspector_stack = QStackedWidget(self)
        self.root_inspector = context.editor_manager.create(
            root_controller,
            context=context,
            parent=self._inspector_stack,
        )
        self._figure_elements_panel = FigureElementInspectorPanel(context)
        self._inspector_stack.addWidget(self.root_inspector)
        self._inspector_stack.addWidget(self._figure_elements_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._inspector_stack)
        self._inspector_stack.setCurrentWidget(self.root_inspector)

    def add_axes_inspector(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library=None,
    ) -> AxesInspectorPanel:
        """Add and return the single-Component panel for one Axes."""

        component_id = axes_controller.component_id
        if component_id in self._axes_panels:
            return self._axes_panels[component_id]
        panel = AxesInspectorPanel(
            axes_controller,
            context,
            color_library,
        )
        try:
            self._inspector_stack.addWidget(panel)
            self._axes_panels[component_id] = panel
        except Exception:
            panel.dispose()
            panel.setParent(None)
            panel.deleteLater()
            raise
        return panel

    def remove_axes_inspector(self, component_id: str) -> bool:
        """Remove the Axes panel associated with a stable component ID."""

        handle = self.take_axes_inspector(component_id)
        if handle is None:
            return False
        self.finalize_axes_inspector_removal(handle)
        return True

    def take_axes_inspector(
        self,
        component_id: str,
    ) -> AxesInspectorRemoval | None:
        """Detach an Axes panel without disposing it so failure can restore it."""

        component_id = str(component_id)
        panel = self._axes_panels.get(component_id)
        if panel is None:
            return None
        index = self._inspector_stack.indexOf(panel)
        was_current = self._inspector_stack.currentWidget() is panel
        try:
            self._axes_panels.pop(component_id)
            self._inspector_stack.removeWidget(panel)
        except Exception:
            self._axes_panels[component_id] = panel
            if self._inspector_stack.indexOf(panel) < 0:
                self._inspector_stack.insertWidget(max(0, index), panel)
            if was_current:
                self._inspector_stack.setCurrentWidget(panel)
            raise
        if self._inspector_stack.currentWidget() is None:
            self._inspector_stack.setCurrentWidget(self.root_inspector)
        return AxesInspectorRemoval(component_id, panel, index, was_current)

    def restore_axes_inspector(
        self,
        handle: AxesInspectorRemoval,
    ) -> None:
        """Restore the exact detached Axes panel and its stack position."""

        if handle.component_id in self._axes_panels:
            return
        self._inspector_stack.insertWidget(
            max(0, min(handle.index, self._inspector_stack.count())),
            handle.panel,
        )
        self._axes_panels[handle.component_id] = handle.panel
        if handle.was_current:
            self._inspector_stack.setCurrentWidget(handle.panel)

    @staticmethod
    def finalize_axes_inspector_removal(
        handle: AxesInspectorRemoval,
    ) -> None:
        """Dispose a panel only after the business deletion has committed."""

        try:
            handle.panel.dispose()
        except Exception:
            pass
        finally:
            handle.panel.setParent(None)
            handle.panel.deleteLater()

    def axes_inspector(self, component_id: str):
        return self._axes_panels.get(str(component_id))

    def show_axes_inspector(
        self,
        axes_inspector: AxesInspectorPanel,
    ) -> None:
        """Show the Axes component itself in its Axes panel."""

        self._inspector_stack.setCurrentWidget(axes_inspector)
        axes_inspector.show_component(
            axes_inspector.axes_controller.component_id
        )

    def show_component(self, component_id: str) -> bool:
        """Show one exact Component Inspector using Registry ancestry."""

        component_id = str(component_id)
        registry = self.context.registry
        if component_id not in registry:
            return False
        if component_id == self.root_component_id:
            self._inspector_stack.setCurrentWidget(self.root_inspector)
            return True
        controller = registry.get(component_id)
        state = controller.state
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            controller
        )
        if profile is None:
            raise ValueError(
                f"Component {component_id!r} has no registered Editor profile."
            )
        if state.parent_id == self.root_component_id:
            if (
                profile.placement is EditorPlacement.ELEMENT
                and self._figure_elements_panel.show_component(component_id)
            ):
                self._inspector_stack.setCurrentWidget(
                    self._figure_elements_panel
                )
                return True
        axes_controller = registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        if axes_controller is None:
            return False
        panel = self._axes_panels.get(axes_controller.component_id)
        if panel is None or not panel.show_component(component_id):
            return False
        self._inspector_stack.setCurrentWidget(panel)
        return True

    def ensure_component(self, component_id: str):
        """Prepare one Inspector without changing the currently visible panel."""

        component_id = str(component_id)
        registry = self.context.registry
        if component_id not in registry:
            raise KeyError(component_id)
        if component_id == self.root_component_id:
            return self.root_inspector
        controller = registry.get(component_id)
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            controller
        )
        if profile is None:
            raise ValueError(
                f"Component {component_id!r} has no registered Editor profile."
            )
        if (
            controller.state.parent_id == self.root_component_id
            and profile.placement is EditorPlacement.ELEMENT
        ):
            return self._figure_elements_panel.ensure_component(component_id)
        axes_controller = registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        panel = (
            self._axes_panels.get(axes_controller.component_id)
            if axes_controller is not None
            else None
        )
        if panel is None:
            raise ValueError(
                f"Axes Inspector for component {component_id!r} is unavailable."
            )
        return panel.ensure_component(component_id)

    def inspector(self, component_id: str):
        """Return the visible-capable Inspector for a stable ID."""

        component_id = str(component_id)
        if component_id == self.root_component_id:
            return self.root_inspector
        inspector = self._figure_elements_panel.inspector(component_id)
        if inspector is not None:
            return inspector
        axes_controller = self.context.registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        panel = (
            self._axes_panels.get(axes_controller.component_id)
            if axes_controller is not None
            else None
        )
        return panel.inspector(component_id) if panel is not None else None

    def remove_component_inspector(self, component_id: str) -> bool:
        """Remove one lazily cached Inspector without touching Registry state."""

        component_id = str(component_id)
        if component_id == self.root_component_id:
            return False
        if self._figure_elements_panel.remove_component(component_id):
            return True
        axes_controller = self.context.registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        panel = (
            self._axes_panels.get(axes_controller.component_id)
            if axes_controller is not None
            else None
        )
        return panel.remove_component(component_id) if panel is not None else False

    def current_panel(self):
        return self._inspector_stack.currentWidget()

    def current_component_id(self) -> str | None:
        current = self._inspector_stack.currentWidget()
        if current is self.root_inspector:
            return self.root_component_id
        if current is self._figure_elements_panel:
            return self._figure_elements_panel.current_component_id()
        if isinstance(current, AxesInspectorPanel):
            return current.current_component_id()
        return None

    def dispose(self) -> None:
        """Recursively release every Inspector in this Figure panel."""

        if self._disposed:
            return
        self._disposed = True
        for panel in tuple(self._axes_panels.values()):
            try:
                panel.dispose()
            except Exception:
                pass
        self._axes_panels.clear()
        for inspector in (
            self._figure_elements_panel,
            self.root_inspector,
        ):
            try:
                inspector.dispose()
            except Exception:
                pass

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class FigureInspectorHost(QFrame):
    """Project-scoped Figure Inspector host."""

    def __init__(self):
        super().__init__()
        self.setObjectName("figure_inspector_host")
        self.setStyleSheet(qss_loader(qss_path))

        self._figure_stack = QStackedWidget(self)
        self.empty_state = PyEmptyState(
            "No project",
            "Create or open a project to inspect its Components.",
            parent=self._figure_stack,
        )
        self._figure_stack.addWidget(self.empty_state)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._figure_stack)
        self._disposed = False

    def add_figure_inspector(
        self,
        root_controller,
        context: EditorContext,
        color_library=None,
        *,
        publish: bool = True,
    ) -> FigureInspectorPanel:
        """Add one project-scoped Figure Inspector panel."""

        panel = FigureInspectorPanel(
            root_controller,
            context,
            color_library,
        )
        if not publish:
            return panel
        try:
            self.publish_figure_inspector(panel)
        except Exception:
            panel.dispose()
            panel.setParent(None)
            panel.deleteLater()
            raise
        return panel

    def publish_figure_inspector(
        self,
        panel: FigureInspectorPanel,
    ) -> FigureInspectorPanel:
        """Insert one fully prepared Inspector panel into the visible stack."""

        if self._figure_stack.indexOf(panel) >= 0:
            return panel
        index = self._figure_stack.addWidget(panel)
        if index < 0:
            raise RuntimeError("Could not publish the Figure Inspector panel.")
        self._figure_stack.setCurrentWidget(panel)
        return panel

    def show_figure_inspector(
        self,
        project_index: int,
    ) -> Optional[FigureInspectorPanel]:
        panel = self._figure_inspector_at(project_index)
        if panel is None:
            self.show_empty_state()
            return None
        self._figure_stack.setCurrentWidget(panel)
        return panel

    def current_figure_inspector(self) -> Optional[FigureInspectorPanel]:
        widget = self._figure_stack.currentWidget()
        return widget if isinstance(widget, FigureInspectorPanel) else None

    def remove_figure_inspector(self, project_index: int) -> bool:
        panel = self._figure_inspector_at(project_index)
        if panel is None:
            return False
        return self.remove_figure_inspector_panel(panel)

    def remove_figure_inspector_panel(
        self,
        panel: FigureInspectorPanel,
    ) -> bool:
        """Remove one Inspector panel by stable widget identity."""

        if self._figure_stack.indexOf(panel) < 0:
            return False
        panel.dispose()
        self._figure_stack.removeWidget(panel)
        panel.setParent(None)
        panel.deleteLater()
        if self._figure_stack.count() == 1:
            self.show_empty_state()
        return True

    def show_empty_state(self) -> None:
        self._figure_stack.setCurrentWidget(self.empty_state)

    def clear_figure_inspectors(self) -> None:
        for index in range(self._figure_stack.count() - 1, 0, -1):
            widget = self._figure_stack.widget(index)
            if isinstance(widget, FigureInspectorPanel):
                try:
                    widget.dispose()
                except Exception:
                    pass
            self._figure_stack.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.show_empty_state()

    def dispose(self) -> None:
        """Recursively dispose all project Inspector panels."""

        if self._disposed:
            return
        self._disposed = True
        self.clear_figure_inspectors()

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)

    def _figure_inspector_at(
        self,
        project_index: int,
    ) -> Optional[FigureInspectorPanel]:
        stack_index = project_index + 1
        if stack_index <= 0 or stack_index >= self._figure_stack.count():
            return None
        widget = self._figure_stack.widget(stack_index)
        return widget if isinstance(widget, FigureInspectorPanel) else None
