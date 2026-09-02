"""Text content and typography Inspector sections."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages, tex_config
from mygui.figuremodify.components import ComponentMutation

from ..common import (
    DebouncedTextBinding,
)
from ..context import perform_editor_action
from ..inspector import EditorSection
from ..lifecycle import CallbackLifecycle
from ._types import ApplyProperties
from .property import PropertySection

class TextContentSection(QWidget, EditorSection):
    """Provide the text content section Qt widget."""

    def __init__(
        self,
        controller,
        *,
        context,
        property_key: str = "text",
        apply_properties: ApplyProperties | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self.property_key = property_key
        self._apply_properties = apply_properties
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.text_content = QPlainTextEdit(self)
        self.text_content.setPlaceholderText("Text content")
        self.text_content.setPlainText(
            str(controller.read_state().properties[property_key])
        )
        self.layout.addWidget(self.text_content)
        self._text_binding = DebouncedTextBinding(
            self.text_content,
            self._apply_text_content,
            delay_ms=250,
            result_presenter=lambda result: context.messages.present(
                result,
                success="Text content updated.",
            ),
            parent=self,
        )

    def _apply_text_content(self, content: str):
        patch = {self.property_key: content}
        if self._apply_properties is not None:
            return self._apply_properties(patch)
        return self.controller.apply_mutation(
            ComponentMutation(
                self.controller.component_id,
                properties=patch,
            )
        )

    def set_text_content(self):
        """Set text content."""

        return self._text_binding.flush()

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        value = self.controller.read_state().properties[self.property_key]
        self._text_binding.set_text(str(value))

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        self._text_binding.cancel()


class TextTypographySection(PropertySection):
    """Edit the text typography properties of a component."""

    DEFAULT_KEYS = (
        "fontfamily",
        "fontsize",
        "color",
    )

    def __init__(
        self,
        controller,
        *,
        context,
        property_keys: Iterable[str] | None = None,
        apply_properties: ApplyProperties | None = None,
        parent=None,
    ):
        super().__init__(
            controller,
            context=context,
            property_keys=property_keys or self.DEFAULT_KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        if "fontfamily" in self.editors():
            self.font_input = self.editor("fontfamily")
        if "fontsize" in self.editors():
            self.font_size_input = self.editor("fontsize")

    def set_text_font(self, font: str):
        """Set text font."""

        return self.apply_property("fontfamily", str(font))

    def set_text_fontsize(self, size):
        """Set text fontsize."""

        return self.apply_property("fontsize", float(size))


class TextTransformSection(PropertySection):
    """Edit the text transform properties of a component."""

    KEYS = (
        "rotation",
        "rotation_mode",
        "horizontalalignment",
        "verticalalignment",
        "multialignment",
        "wrap",
        "linespacing",
        "transform_rotates_text",
    )

    def __init__(self, controller, *, context, apply_properties, parent=None):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )


class TextPositionSection(PropertySection):
    """Edit the text position properties of a component."""

    KEYS = ("position", "visible")

    def __init__(self, controller, *, context, apply_properties, parent=None):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        position = self.editor("position")
        self.text_x_pos, self.text_y_pos = position.inputs

    def set_xy_position(self, *_args):
        """Set xy position."""

        return self.apply_property(
            "position",
            (self.text_x_pos.value(), self.text_y_pos.value()),
        )


class TextRenderSection(QWidget, EditorSection):
    """Provide the text render section Qt widget."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._disposed = False
        self._lifecycle = CallbackLifecycle()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(QLabel("Render:", self))
        self.tex_render = QCheckBox("TeX", self)
        self.tex_render.setToolTip("Render this text with TeX")
        self.layout.addWidget(self.tex_render)
        self.layout.addStretch()
        self._listener = self._tex_state_changed
        tex_config.register_tex_availability_listener(self._listener)
        self._lifecycle.add(
            lambda: tex_config.unregister_tex_availability_listener(
                self._listener
            )
        )
        try:
            self.tex_render.toggled.connect(self.set_tex_render)
            self._sync_tex_button()
        except Exception:
            self._lifecycle.close()
            raise

    def _sync_tex_button(self):
        enabled = tex_config.is_tex_enabled()
        blocker = QSignalBlocker(self.tex_render)
        self.tex_render.setEnabled(enabled)
        self.tex_render.setChecked(
            bool(
                self.controller.read_state().properties.get(
                    "usetex", False
                )
            )
        )
        del blocker

    def _tex_state_changed(self, enabled: bool):
        if self._disposed:
            return
        self._sync_tex_button()

    def set_tex_render(self, state):
        """Set tex render."""

        if self._disposed:
            return False
        checked = (
            bool(state)
            if isinstance(state, bool)
            else state in {Qt.Checked, Qt.CheckState.Checked}
        )
        if checked and not tex_config.is_tex_enabled():
            status_messages.show_error(
                "Enable TeX before using TeX rendering for this text."
            )
            self._sync_tex_button()
            return False
        result = perform_editor_action(self.context,
            (
                "Enable Text TeX Rendering"
                if checked
                else "Disable Text TeX Rendering"
            ),
            lambda: self.context.text_rendering.apply(
                self.controller,
                {"usetex": checked},
            ),
        )
        if not self.context.messages.present(
            result,
            success=(
                "Text TeX rendering enabled."
                if checked
                else "Text TeX rendering disabled."
            ),
        ):
            self._sync_tex_button()
            return False
        return True

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        self._sync_tex_button()

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        self._lifecycle.close()
