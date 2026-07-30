"""Compose component inspectors from registered editor sections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from Qt_core import (
    QFrame,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)
from code.figuremodify.components import DeletionPolicy


class EditorSection:
    """Lifecycle contract implemented by reusable Inspector sections."""

    section_key = ""

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        return None

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        return None


SectionFactory = Callable[[object, object, QWidget | None], QWidget]


class EditorPlacement(str, Enum):
    """Purely visual destination for a registered Inspector profile."""

    CHART = "chart"
    ELEMENT = "element"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """Describe section spec values shared across application layers."""

    key: str
    title: str
    factory: SectionFactory
    collapsed: bool = False


@dataclass(frozen=True, slots=True)
class EditorProfile:
    """Represent the application's editor profile."""

    key: str
    title: str
    sections: tuple[SectionSpec, ...]
    placement: EditorPlacement = EditorPlacement.SEMANTIC
    instance_label_prefix: str = ""


class ComponentInspector(QFrame):
    """One production editor shell composed from role-specific sections."""

    def __init__(
        self,
        controller,
        *,
        context,
        profile: EditorProfile,
        color_library=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        del color_library
        self.controller = controller
        self.context = context
        self.profile = profile
        self.can_delete = (
            controller.DELETION_POLICY is DeletionPolicy.REMOVE
        )
        self._sections: list[QWidget] = []
        self._sections_by_key: dict[str, QWidget] = {}
        self._disposed = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

        for spec in profile.sections:
            section = spec.factory(controller, context, self)
            setattr(section, "section_key", spec.key)
            self._sections.append(section)
            self._sections_by_key[spec.key] = section

            group = QGroupBox(spec.title, self)
            group.setObjectName("component_inspector_section")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(6, 6, 6, 6)
            group_layout.addWidget(section)
            if spec.collapsed:
                group.setCheckable(True)
                group.setChecked(False)
                section.setVisible(False)
                group.toggled.connect(section.setVisible)
            self.layout.addWidget(group)

        self.layout.addStretch()

    def section(self, key: str) -> QWidget:
        """Return the requested section."""

        return self._sections_by_key[key]

    def sections(self) -> tuple[QWidget, ...]:
        """Return the available sections."""

        return tuple(self._sections)

    def editor(self, key: str) -> QWidget:
        """Return the editor widget used for the property."""

        for section in self._sections:
            getter = getattr(section, "editor", None)
            if not callable(getter):
                continue
            try:
                return getter(key)
            except KeyError:
                continue
        raise KeyError(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        for section in tuple(self._sections):
            sync = getattr(section, "sync_from_controller", None)
            if callable(sync):
                sync()

    def delete_object(self):
        """Delete object."""

        if not self.can_delete:
            return False
        service = getattr(self.context, "deletion_service", None)
        result = (
            service.delete_many((self.controller.component_id,))
            if service is not None
            else self.context.registry.delete(self.controller.component_id)
        )
        return self.context.messages.present(
            result,
            success=f"{self.profile.title} deleted.",
        )

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        for section in tuple(self._sections):
            cleanup = getattr(section, "dispose", None)
            if callable(cleanup):
                cleanup()
        manager = getattr(self.context, "editor_manager", None)
        release = getattr(manager, "release", None)
        if callable(release):
            release(self)

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)
