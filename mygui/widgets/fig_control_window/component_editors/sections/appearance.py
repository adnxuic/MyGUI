"""Line and scatter appearance Inspector sections."""

from __future__ import annotations


from PySide6.QtWidgets import (
    QToolBox,
    QVBoxLayout,
    QWidget,
)


from ..inspector import EditorSection
from .property import PropertySection

class LineAppearanceSection(QWidget, EditorSection):
    """The single shared appearance editor for every LineController role."""

    BASIC_KEYS = (
        "label",
        "visible",
        "color",
        "linestyle",
        "linewidth",
        "drawstyle",
        "gapcolor",
    )
    MARKER_KEYS = (
        "marker",
        "markersize",
        "markerfacecolor",
        "markerfacecoloralt",
        "markeredgecolor",
        "markeredgewidth",
        "fillstyle",
        "markevery",
    )
    ADVANCED_KEYS = (
        "alpha",
        "zorder",
        "dash_capstyle",
        "dash_joinstyle",
        "solid_capstyle",
        "solid_joinstyle",
        "antialiased",
        "clip_on",
        "gid",
        "in_layout",
        "rasterized",
        "sketch_params",
        "snap",
        "url",
    )
    PROPERTY_KEYS = BASIC_KEYS + MARKER_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QToolBox(self)

        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.BASIC_KEYS,
            parent=self,
        )
        self._marker = PropertySection(
            controller,
            context=context,
            property_keys=self.MARKER_KEYS,
            parent=self,
        )
        self._advanced = PropertySection(
            controller,
            context=context,
            property_keys=self.ADVANCED_KEYS,
            parent=self,
        )
        self.toolbox.addItem(self._base, "Basic")
        self.toolbox.addItem(self._marker, "Marker")
        self.toolbox.addItem(self._advanced, "Advanced")
        self.layout.addWidget(self.toolbox)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        for section in (self._base, self._marker, self._advanced):
            try:
                return section.editor(key)
            except KeyError:
                continue
        raise KeyError(key)

    def editors(self):
        """Return the available editors."""

        result = {}
        for section in (self._base, self._marker, self._advanced):
            result.update(section.editors())
        return result

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        for section in (self._base, self._marker, self._advanced):
            if key in section.editors():
                return section.flush_text(key)
        raise KeyError(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()
        self._marker.sync_from_controller()
        self._advanced.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()
        self._marker.dispose()
        self._advanced.dispose()


class ScatterAppearanceSection(QWidget, EditorSection):
    """Provide the scatter appearance section Qt widget."""

    BASIC_KEYS = (
        "label",
        "visible",
        "color",
        "edgecolor",
        "marker",
        "size",
        "linewidth",
        "linestyle",
        "hatch",
        "capstyle",
        "joinstyle",
    )
    ADVANCED_KEYS = (
        "alpha",
        "zorder",
        "antialiased",
        "clip_on",
        "gid",
        "in_layout",
        "rasterized",
        "sketch_params",
        "snap",
        "url",
        "urls",
    )
    PROPERTY_KEYS = BASIC_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.toolbox = QToolBox(self)
        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.BASIC_KEYS,
            parent=self,
        )
        self._advanced = PropertySection(
            controller,
            context=context,
            property_keys=self.ADVANCED_KEYS,
            parent=self,
        )
        self.toolbox.addItem(self._base, "Basic")
        self.toolbox.addItem(self._advanced, "Advanced")
        self.layout.addWidget(self.toolbox)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        for section in (self._base, self._advanced):
            try:
                return section.editor(key)
            except KeyError:
                continue
        raise KeyError(key)

    def editors(self):
        """Return the available editors."""

        result = {}
        result.update(self._base.editors())
        result.update(self._advanced.editors())
        return result

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        for section in (self._base, self._advanced):
            if key in section.editors():
                return section.flush_text(key)
        raise KeyError(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()
        self._advanced.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()
        self._advanced.dispose()
