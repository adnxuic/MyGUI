"""Provide stable-ID Inspector stacks without component navigation labels."""

from __future__ import annotations

import os

from Qt_core import *

from code.figuremodify.components import (
    AxesController,
    ComponentKind,
    ComponentRole,
)
from code.widgets import qss_func
from code.widgets.common_widget.py_empty_state import PyEmptyState

from .context import EditorContext
from .inspector import EditorPlacement


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(
    os.path.dirname(current_path),
    "all_mod_widgets",
    "style.qss",
)


class AxesSemanticInspectorPanel(QFrame):
    """Show exactly one semantic Component Inspector for one Axes."""

    def __init__(
        self,
        axes_controller: AxesController,
        context: EditorContext,
        color_library=None,
    ):
        super().__init__()
        del color_library
        self.axes_controller = axes_controller
        self.context = context
        self.axes = axes_controller.resolve_target()
        self._inspectors: dict[str, QWidget] = {}
        self._disposed = False

        self.setObjectName("axes_semantic_inspector_panel")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.inspector_stack = QStackedWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.inspector_stack)

        self.ensure_inspector(axes_controller.component_id)
        self.show_component(axes_controller.component_id)

    def ensure_inspector(self, component_id: str):
        """Create a semantic Inspector on first selection and then cache it."""

        component_id = str(component_id)
        existing = self._inspectors.get(component_id)
        if existing is not None:
            return existing
        controller = self.context.registry.get(component_id)
        axes_ancestor = self.context.registry.ancestor(
            component_id,
            kind=ComponentKind.AXES,
        )
        profile = self.context.editor_manager.editor_registry.resolve_profile(
            controller
        )
        if (
            axes_ancestor is None
            or axes_ancestor.component_id != self.axes_controller.component_id
            or profile is None
            or profile.placement is not EditorPlacement.SEMANTIC
        ):
            raise ValueError("Component is not an Axes semantic Inspector.")
        component_id = controller.component_id
        inspector = self.context.editor_manager.create(
            controller,
            context=self.context,
            parent=self.inspector_stack,
            remover=self.remove_inspector,
        )
        self._inspectors[component_id] = inspector
        try:
            self.inspector_stack.addWidget(inspector)
        except Exception:
            self.inspector_stack.removeWidget(inspector)
            self._inspectors.pop(component_id, None)
            self.context.editor_manager.release(inspector)
            inspector.dispose()
            inspector.setParent(None)
            inspector.deleteLater()
            raise
        return inspector

    def remove_inspector(self, inspector) -> bool:
        """Dispose and remove one semantic Inspector from the stack."""

        component_id = next(
            (
                item_id
                for item_id, candidate in self._inspectors.items()
                if candidate is inspector
            ),
            None,
        )
        if component_id is None:
            return False
        dispose = getattr(inspector, "dispose", None)
        if callable(dispose):
            dispose()
        self._inspectors.pop(component_id, None)
        self.inspector_stack.removeWidget(inspector)
        inspector.setParent(None)
        inspector.deleteLater()
        return True

    def show_component(self, component_id: str) -> bool:
        """Show the semantic Inspector associated with a stable ID."""

        if str(component_id) not in self.context.registry:
            return False
        try:
            inspector = self.ensure_inspector(component_id)
        except ValueError:
            return False
        self.inspector_stack.setCurrentWidget(inspector)
        return True

    def inspector(self, component_id: str):
        """Return the semantic Inspector associated with a stable ID."""

        return self._inspectors.get(str(component_id))

    def component_ids(self) -> tuple[str, ...]:
        """Return all semantic Component IDs owned by this panel."""

        return tuple(self._inspectors)

    def current_component_id(self) -> str | None:
        current = self.inspector_stack.currentWidget()
        for component_id, inspector in self._inspectors.items():
            if inspector is current:
                return component_id
        return None

    def remove_component(self, component_id: str) -> bool:
        """Remove one cached Inspector by stable component ID."""

        for toolbox in tuple(self._toolboxes.values()):
            inspector = toolbox.inspector(component_id)
            if inspector is not None:
                return toolbox.remove_inspector(inspector)
        return False

    def dispose(self) -> None:
        """Recursively release every cached semantic Inspector."""

        if self._disposed:
            return
        self._disposed = True
        for inspector in tuple(self._inspectors.values()):
            self.remove_inspector(inspector)

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class InspectorToolBox(QFrame):
    """Own an ID-keyed stack of visible Component Inspectors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspector_toolbox")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self._entries: list[tuple[str, QWidget]] = []
        self._entry_by_id: dict[str, QWidget] = {}
        self._empty_callback = None
        self._disposed = False

        self.inspector_stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.inspector_stack)

    def set_empty_callback(self, callback) -> None:
        """Set the callback invoked after the final Inspector is removed."""

        self._empty_callback = callback

    def add_inspector(self, inspector):
        """Add one Inspector keyed exclusively by its stable component ID."""

        controller = getattr(inspector, "controller", None)
        component_id = getattr(controller, "component_id", None)
        if not component_id:
            raise ValueError("Inspector requires a stable component ID.")
        component_id = str(component_id)
        if component_id in self._entry_by_id:
            raise ValueError(
                f"Duplicate Inspector component ID {component_id!r}."
            )
        self._entries.append((component_id, inspector))
        self._entry_by_id[component_id] = inspector
        try:
            self.inspector_stack.addWidget(inspector)
        except Exception:
            self.inspector_stack.removeWidget(inspector)
            self._entries.pop()
            self._entry_by_id.pop(component_id, None)
            raise
        if len(self._entries) == 1:
            self.inspector_stack.setCurrentWidget(inspector)
        return len(self._entries) - 1

    def remove_inspector(self, inspector) -> bool:
        """Dispose and remove one Inspector and release its QWidget."""

        index = self.indexOf(inspector)
        if index < 0:
            return False
        dispose = getattr(inspector, "dispose", None)
        if callable(dispose):
            dispose()
        component_id, _candidate = self._entries.pop(index)
        self._entry_by_id.pop(component_id, None)
        was_current = self.inspector_stack.currentWidget() is inspector
        self.inspector_stack.removeWidget(inspector)
        inspector.setParent(None)
        inspector.deleteLater()
        if was_current and self._entries:
            next_index = min(index, len(self._entries) - 1)
            self.inspector_stack.setCurrentWidget(
                self._entries[next_index][1]
            )
        if not self._entries and callable(self._empty_callback):
            self._empty_callback()
        return True

    def count(self) -> int:
        return len(self._entries)

    def widget(self, index: int):
        if index < 0 or index >= len(self._entries):
            return None
        return self._entries[index][1]

    def indexOf(self, inspector) -> int:
        for index, (_component_id, candidate) in enumerate(self._entries):
            if candidate is inspector:
                return index
        return -1

    def currentWidget(self):
        return self.inspector_stack.currentWidget()

    def currentIndex(self) -> int:
        return self.indexOf(self.currentWidget())

    def setCurrentIndex(self, index: int) -> None:
        target = self.widget(index)
        if target is not None:
            self.inspector_stack.setCurrentWidget(target)

    def setCurrentWidget(self, inspector) -> None:
        if self.indexOf(inspector) >= 0:
            self.inspector_stack.setCurrentWidget(inspector)

    def show_inspector(self, component_id: str) -> bool:
        """Show one Inspector selected by stable component ID."""

        inspector = self._entry_by_id.get(str(component_id))
        if inspector is None:
            return False
        self.inspector_stack.setCurrentWidget(inspector)
        return True

    def inspector(self, component_id: str):
        return self._entry_by_id.get(str(component_id))

    def component_ids(self) -> tuple[str, ...]:
        return tuple(component_id for component_id, _item in self._entries)

    def dispose(self) -> None:
        """Recursively dispose all Inspectors exactly once."""

        if self._disposed:
            return
        self._disposed = True
        self._empty_callback = None
        for _component_id, inspector in tuple(self._entries):
            self.remove_inspector(inspector)

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class _ComponentInspectorStack(QFrame):
    """Shared role-toolbox stack used by Chart and Element containers."""

    EMPTY_TITLE = "No component selected"
    EMPTY_DETAIL = "Select a Component in the tree to edit its parameters."

    def __init__(self, axes, parent=None):
        super().__init__(parent)
        self.axes = axes
        self._toolboxes = {}
        self._disposed = False
        self.toolbox_stack = QStackedWidget(self)
        self.empty_state = PyEmptyState(
            self.EMPTY_TITLE,
            self.EMPTY_DETAIL,
            parent=self.toolbox_stack,
        )
        self.toolbox_stack.addWidget(self.empty_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbox_stack)

    def ensure_toolbox(self, key):
        toolbox = self._toolboxes.get(key)
        if toolbox is None:
            toolbox = InspectorToolBox(self.toolbox_stack)
            self._toolboxes[key] = toolbox
            self.toolbox_stack.addWidget(toolbox)
        return toolbox

    def toolbox(self, key):
        return self._toolboxes.get(key)

    def show_toolbox(self, key) -> bool:
        toolbox = self.toolbox(key)
        if toolbox is None:
            return False
        self.toolbox_stack.setCurrentWidget(toolbox)
        return True

    def show_component(self, component_id: str) -> bool:
        for toolbox in self._toolboxes.values():
            if toolbox.show_inspector(component_id):
                self.toolbox_stack.setCurrentWidget(toolbox)
                return True
        return False

    def remove_toolbox(self, key) -> bool:
        toolbox = self._toolboxes.pop(key, None)
        if toolbox is None:
            return False
        was_current = self.toolbox_stack.currentWidget() is toolbox
        self.toolbox_stack.removeWidget(toolbox)
        if was_current:
            self.toolbox_stack.setCurrentWidget(self.empty_state)
        toolbox.dispose()
        toolbox.setParent(None)
        toolbox.deleteLater()
        return True

    def inspector(self, component_id: str):
        for toolbox in self._toolboxes.values():
            inspector = toolbox.inspector(component_id)
            if inspector is not None:
                return inspector
        return None

    def current_component_id(self) -> str | None:
        toolbox = self.toolbox_stack.currentWidget()
        if not isinstance(toolbox, InspectorToolBox):
            return None
        inspector = toolbox.currentWidget()
        controller = getattr(inspector, "controller", None)
        return getattr(controller, "component_id", None)

    def dispose(self) -> None:
        """Recursively release every toolbox and Inspector."""

        if self._disposed:
            return
        self._disposed = True
        for key in tuple(self._toolboxes):
            self.remove_toolbox(key)

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)


class ChartInspectorStack(_ComponentInspectorStack):
    """Own Chart Inspectors grouped internally by role."""

    EMPTY_TITLE = "No chart selected"
    EMPTY_DETAIL = "Select a chart Component in the tree."


class ElementInspectorStack(_ComponentInspectorStack):
    """Own free-element Inspectors grouped internally by role."""

    EMPTY_TITLE = "No element selected"
    EMPTY_DETAIL = "Select an element Component in the tree."
