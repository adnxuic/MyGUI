"""Compose component inspectors from registered editor sections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from PySide6.QtWidgets import QFrame, QGroupBox, QVBoxLayout, QWidget
from mygui.figuremodify.components import DeletionPolicy


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

    FIGURE = "figure"
    CHART = "chart"
    ELEMENT = "element"
    SEMANTIC = "semantic"


TreeLabelFactory = Callable[[object], str]
TreePreviewFactory = Callable[[object], Any]
TreeSortFactory = Callable[[object], tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class TreePresentationSpec:
    """Describe UI-only component-tree labeling, grouping and ordering."""

    label: str | TreeLabelFactory
    group_title: str | None = None
    instance_prefix: str | None = None
    preview: TreePreviewFactory | None = None
    sort_bucket: int = 50
    sort_key: TreeSortFactory | None = None

    def __post_init__(self) -> None:
        if isinstance(self.label, str) and not self.label.strip():
            raise ValueError("Tree presentation label must not be empty.")
        if not isinstance(self.label, str) and not callable(self.label):
            raise TypeError("Tree presentation label must be text or callable.")
        if self.preview is not None and not callable(self.preview):
            raise TypeError("Tree preview extractor must be callable.")
        if self.sort_key is not None and not callable(self.sort_key):
            raise TypeError("Tree sort key must be callable.")


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
    placement: EditorPlacement
    tree: TreePresentationSpec

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Editor profile key must not be empty.")
        if not self.title.strip():
            raise ValueError("Editor profile title must not be empty.")
        if not isinstance(self.placement, EditorPlacement):
            raise TypeError("Editor profile placement must be explicit.")
        if not isinstance(self.tree, TreePresentationSpec):
            raise TypeError("Editor profile tree presentation must be explicit.")
        if not self.sections:
            raise ValueError("Editor profile must declare at least one section.")
        keys = [spec.key.strip() for spec in self.sections]
        if any(not key for key in keys):
            raise ValueError("Editor section keys must not be empty.")
        if len(keys) != len(set(keys)):
            raise ValueError("Editor section keys must be unique per profile.")
        if any(not callable(spec.factory) for spec in self.sections):
            raise TypeError("Editor section factories must be callable.")


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

        try:
            for spec in profile.sections:
                section = spec.factory(controller, context, self)
                if not isinstance(section, QWidget):
                    raise TypeError(
                        f"Section {spec.key!r} did not create a QWidget."
                    )
                if not isinstance(section, EditorSection):
                    raise TypeError(
                        f"Section {spec.key!r} must implement EditorSection."
                    )
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
        except Exception:
            self._dispose_sections()
            raise

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
        """Delegate physical deletion to the Canvas-owned command."""

        if not self.can_delete:
            return False
        command = getattr(self.context, "delete_command", None)
        if not callable(command):
            return False
        return command(
            (self.controller.component_id,),
            anchor_id=self.controller.component_id,
            reason="single",
            role_label=self.profile.title,
        )

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        manager = getattr(self.context, "editor_manager", None)
        release = getattr(manager, "release", None)
        if callable(release):
            release(self)
        self._dispose_sections()

    def _dispose_sections(self) -> None:
        """Release every constructed Section even if one cleanup fails."""

        sections = tuple(reversed(self._sections))
        self._sections.clear()
        self._sections_by_key.clear()
        for section in sections:
            cleanup = getattr(section, "dispose", None)
            try:
                if callable(cleanup):
                    cleanup()
            except Exception:
                pass
            try:
                section.setParent(None)
                section.deleteLater()
            except RuntimeError:
                pass

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)
