"""Compose component inspectors from registered editor sections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from PySide6.QtWidgets import QFrame, QGroupBox, QVBoxLayout, QWidget
from mygui.application_theme import current_density_metrics
from mygui.figuremodify.components import DeletionPolicy
from mygui.widgets.fig_control_window.component_editors.cleanup import (
    isolate_cleanup,
)


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
    group_key: str | None = None
    group_order: int | None = None
    always_group: bool = False
    delete_label: str | None = None
    duplicate_label: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.label, str) and not self.label.strip():
            raise ValueError("Tree presentation label must not be empty.")
        if not isinstance(self.label, str) and not callable(self.label):
            raise TypeError("Tree presentation label must be text or callable.")
        if self.preview is not None and not callable(self.preview):
            raise TypeError("Tree preview extractor must be callable.")
        if self.sort_key is not None and not callable(self.sort_key):
            raise TypeError("Tree sort key must be callable.")
        if self.group_key is not None and not self.group_key.strip():
            raise ValueError("Tree group key must not be empty.")
        if self.group_key is not None and not self.group_title:
            raise ValueError("Tree group key requires a group title.")
        if self.always_group and not self.group_title:
            raise ValueError("Always-group presentation requires a group title.")
        if self.delete_label is not None and not self.delete_label.strip():
            raise ValueError("Tree delete label must not be empty.")
        if self.duplicate_label is not None and not self.duplicate_label.strip():
            raise ValueError("Tree duplicate label must not be empty.")


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """Describe section spec values shared across application layers."""

    key: str
    title: str
    factory: SectionFactory
    collapsed: bool = False
    property_keys: tuple[str, ...] = ()
    data_keys: tuple[str, ...] = ()
    proxy_keys: tuple[str, ...] = ()
    intentionally_hidden: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.title.strip():
            raise ValueError("Editor section key and title must not be empty.")
        if not callable(self.factory):
            raise TypeError("Editor section factory must be callable.")
        for name in (
            "property_keys",
            "data_keys",
            "proxy_keys",
            "intentionally_hidden",
        ):
            values = tuple(str(value).strip() for value in getattr(self, name))
            if any(not value for value in values):
                raise ValueError(f"Section {name} entries must not be empty.")
            if len(values) != len(set(values)):
                raise ValueError(f"Section {name} entries must be unique.")
            object.__setattr__(self, name, values)
        declared = (
            set(self.property_keys)
            | set(self.data_keys)
            | set(self.proxy_keys)
            | set(self.intentionally_hidden)
        )
        total = sum(
            len(values)
            for values in (
                self.property_keys,
                self.data_keys,
                self.proxy_keys,
                self.intentionally_hidden,
            )
        )
        if len(declared) != total:
            raise ValueError(
                "A section key cannot have more than one exposure role."
            )


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
        metrics = current_density_metrics()
        self.layout.setSpacing(metrics.spacing_sm)

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
                group.setMinimumWidth(1)
                group_layout = QVBoxLayout(group)
                pad = metrics.spacing_sm
                group_layout.setContentsMargins(pad, pad, pad, pad)
                group_layout.setSpacing(pad)
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

    def sync_property_from_controller(self, property_key: str) -> bool:
        """Refresh only Sections that expose one changed property."""

        handled = False
        for spec in self.profile.sections:
            if property_key in spec.intentionally_hidden:
                handled = True
            if property_key not in spec.property_keys:
                continue
            section = self._sections_by_key.get(spec.key)
            if section is None:
                continue
            sync = getattr(section, "sync_from_controller", None)
            if callable(sync):
                sync()
            handled = True
        return handled

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
        owner = type(self).__name__
        target = getattr(self.controller, "component_id", owner)
        if callable(release):
            isolate_cleanup(
                lambda: release(self),
                owner=owner,
                target=str(target),
                operation="release",
            )
        self._dispose_sections()

    def _dispose_sections(self) -> None:
        """Release every constructed Section even if one cleanup fails."""

        sections = tuple(reversed(self._sections))
        self._sections.clear()
        self._sections_by_key.clear()
        owner = type(self).__name__
        for section in sections:
            target = str(getattr(section, "section_key", None) or type(section).__name__)
            cleanup = getattr(section, "dispose", None)
            if callable(cleanup):
                isolate_cleanup(
                    cleanup,
                    owner=owner,
                    target=target,
                    operation="dispose",
                )
            isolate_cleanup(
                lambda current=section: current.setParent(None),
                owner=owner,
                target=target,
                operation="setParent",
            )
            isolate_cleanup(
                lambda current=section: current.deleteLater(),
                owner=owner,
                target=target,
                operation="deleteLater",
            )

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)
