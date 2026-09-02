"""Line and scatter appearance Inspector sections."""

from __future__ import annotations


from PySide6.QtWidgets import (
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
        "marker",
        "markersize",
    )
    MARKER_KEYS = ()
    ADVANCED_KEYS = (
        "drawstyle",
        "gapcolor",
        "markerfacecolor",
        "markerfacecoloralt",
        "markeredgecolor",
        "markeredgewidth",
        "fillstyle",
        "markevery",
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
    PRIMARY_KEYS = BASIC_KEYS + MARKER_KEYS
    PROPERTY_KEYS = PRIMARY_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.PRIMARY_KEYS,
            parent=self,
        )
        self.layout.addWidget(self._base)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        return self._base.editor(key)

    def editors(self):
        """Return the available editors."""

        return self._base.editors()

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        return self._base.flush_text(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()


class ScatterAppearanceSection(QWidget, EditorSection):
    """Provide the scatter appearance section Qt widget."""

    BASIC_KEYS = (
        "visible",
        "color",
        "marker",
        "size",
        "edgecolor",
        "linewidth",
    )
    ADVANCED_KEYS = (
        "label",
        "linestyle",
        "hatch",
        "capstyle",
        "joinstyle",
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
    PRIMARY_KEYS = BASIC_KEYS
    PROPERTY_KEYS = PRIMARY_KEYS + ADVANCED_KEYS

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self._base = PropertySection(
            controller,
            context=context,
            property_keys=self.PRIMARY_KEYS,
            parent=self,
        )
        self.layout.addWidget(self._base)

    def editor(self, key: str):
        """Return the editor widget used for the property."""

        return self._base.editor(key)

    def editors(self):
        """Return the available editors."""

        return self._base.editors()

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        return self._base.flush_text(key)

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._base.sync_from_controller()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._base.dispose()
