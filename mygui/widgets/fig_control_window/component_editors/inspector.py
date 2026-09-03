"""Compose component inspectors from registered editor sections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QGroupBox, QVBoxLayout, QWidget
from mygui.application_theme import current_density_metrics, subscribe_theme_window
from mygui.widgets.ui_components import annotate_form_fields, annotate_section
from mygui.figuremodify.components import DeletionPolicy
from mygui.widgets.fig_control_window.component_editors.cleanup import (
    isolate_cleanup,
)
from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
    request_inspector_geometry_refresh,
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


def _collapse_inspector_section(section: QWidget, expanded: bool) -> None:
    """Toggle visibility without leaving QGroupBox children disabled."""

    section.setVisible(expanded)
    section.setEnabled(True)
    parent = section.parentWidget()
    restore = getattr(parent, "_keep_children_enabled", None)
    if callable(restore):
        restore()
    request_inspector_geometry_refresh(section)


class InspectorSectionGroup(QGroupBox):
    """Collapsible Inspector chrome that hides children instead of disabling them."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(title, parent)
        self.setObjectName("component_inspector_section")
        self._full_title = title
        self.setToolTip(title)
        self.setAccessibleName(title)

    def setTitle(self, title: str) -> None:  # noqa: N802
        self._full_title = str(title)
        self.setToolTip(self._full_title)
        self.setAccessibleName(self._full_title)
        super().setTitle(self._full_title)
        self._apply_title_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_title_elide()

    def _apply_title_elide(self) -> None:
        full = getattr(self, "_full_title", self.title())
        if not full or self.width() <= 1:
            return
        metrics = current_density_metrics()
        left = (
            metrics.section_title_left
            if self.isCheckable()
            else metrics.spacing_sm
        )
        available = max(
            8,
            self.width()
            - left
            - (2 * metrics.spacing_xs)
            - metrics.spacing_sm
            - 4,
        )
        elided = QFontMetrics(self.font()).elidedText(
            full,
            Qt.TextElideMode.ElideRight,
            available,
        )
        if elided != self.title():
            super().setTitle(elided)

    def full_title(self) -> str:
        """Return the unelided section title used by tests and smoke."""

        return getattr(self, "_full_title", self.title())

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._keep_children_enabled()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.EnabledChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ParentChange,
            QEvent.Type.FontChange,
        ):
            self._keep_children_enabled()
            if event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange):
                self._apply_title_elide()

    def childEvent(self, event) -> None:
        super().childEvent(event)
        self._keep_children_enabled()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._keep_children_enabled()
        self._apply_title_elide()

    def _keep_children_enabled(self) -> None:
        if not self.isCheckable() or self.isChecked():
            return
        for child in self.children():
            if isinstance(child, QWidget):
                child.setEnabled(True)

    def apply_theme_metrics(self, metrics) -> None:
        """Apply density padding without walking unrelated Inspector widgets."""

        layout = self.layout()
        if layout is None:
            return
        pad = metrics.spacing_sm
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(pad)
        self._apply_title_elide()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(1, hint.height())


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

                group = InspectorSectionGroup(spec.title, self)
                group_layout = QVBoxLayout(group)
                pad = metrics.spacing_sm
                group_layout.setContentsMargins(pad, pad, pad, pad)
                group_layout.setSpacing(pad)
                group_layout.addWidget(section)
                if spec.collapsed:
                    group.setCheckable(True)
                    group.setChecked(False)
                    section.setVisible(False)
                    group._keep_children_enabled()
                    group.toggled.connect(
                        lambda checked, current=section: _collapse_inspector_section(
                            current, checked
                        )
                    )
                annotate_section(group)
                self.layout.addWidget(group)
            annotate_form_fields(self)
        except Exception:
            self._dispose_sections()
            raise

        self.layout.addStretch()
        subscribe_theme_window(self)

    def minimumSizeHint(self) -> QSize:
        hint = QFrame.minimumSizeHint(self)
        return QSize(1, hint.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if event.oldSize().width() == event.size().width():
            return
        from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
            InspectorFormLabel,
        )

        for form_label in self.findChildren(InspectorFormLabel):
            form_label.apply_theme_metrics()

    def apply_theme_metrics(self, metrics) -> None:
        """Update section spacing from the published density metrics."""

        self.layout.setSpacing(metrics.spacing_sm)
        for index in range(self.layout.count()):
            item = self.layout.itemAt(index)
            widget = item.widget() if item is not None else None
            apply = getattr(widget, "apply_theme_metrics", None)
            if callable(apply):
                apply(metrics)
        from mygui.widgets.fig_control_window.component_editors.common import (
            RangeEditor,
        )

        for editor in self.findChildren(RangeEditor):
            editor.apply_theme_metrics(metrics)
        from mygui.widgets.fig_control_window.component_editors.inspector_layout import (
            InspectorFormLabel,
        )

        for form_label in self.findChildren(InspectorFormLabel):
            form_label.apply_theme_metrics(metrics)

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
