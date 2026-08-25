"""Generic PropertySpec Inspector section."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import (
    QWidget,
)

from mygui.figuremodify.components import ComponentKind

from ..base import ComponentEditorBase
from ..inspector import EditorSection
from ._types import ApplyProperties

class PropertySection(ComponentEditorBase, EditorSection):
    """A reusable subset of a Controller's PropertySpec form."""

    def __init__(
        self,
        controller,
        *,
        context,
        property_keys: Iterable[str] | None = None,
        apply_properties: ApplyProperties | None = None,
        parent: QWidget | None = None,
    ):
        self._apply_properties = apply_properties
        specs = controller.property_specs()
        if property_keys is None:
            selected = list(specs.values())
        else:
            selected = [
                specs[key]
                for key in property_keys
                if key in specs
            ]
        super().__init__(
            controller,
            context=context,
            color_library=context.color_library,
            property_specs=selected,
            parent=parent,
        )

    def _set_controller_property(self, key: str, value):
        if self._apply_properties is None:
            return super()._set_controller_property(key, value)
        return self._apply_properties({key: value})

    def _success_message(self, key: str, label: str) -> str:
        state = self.controller.state
        if state.kind is ComponentKind.SPINE and key == "visible":
            side = str(state.selector.get("name", "spine")).title()
            return f"{side} spine visibility updated."
        return super()._success_message(key, label)

    def flush_text(self, key: str) -> bool:
        """Commit pending text after the edit-coalescing delay."""

        binding = self._text_bindings.get(key)
        return True if binding is None else binding.flush()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        for binding in self._text_bindings.values():
            binding.cancel()


class ReferenceMarksPositionSection(PropertySection):
    """Keep automatic Reflection baseline visible but not editable."""

    def sync_from_controller(self) -> None:
        super().sync_from_controller()
        placement = self.controller.state.data.get("placement") or {}
        automatic = placement.get("kind") == "between_table_ranges"
        editor = self._editors.get("baseline")
        if editor is not None:
            editor.setEnabled(not automatic)
