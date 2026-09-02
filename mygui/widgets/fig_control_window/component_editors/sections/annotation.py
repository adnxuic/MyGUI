"""Annotation-specific Inspector sections."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..common import DebouncedTextBinding
from ..inspector import EditorSection
from ..inspector_layout import apply_expanding_field, configure_inspector_form
from ._types import ApplyProperties
from .property import PropertySection
from .text import TextTypographySection

ANNOTATION_PLACEMENT_PRESETS: tuple[tuple[str, tuple[float, float]], ...] = (
    ("Above", (0.0, 20.0)),
    ("Below", (0.0, -20.0)),
    ("Left", (-20.0, 0.0)),
    ("Right", (20.0, 0.0)),
    ("Upper Left", (-20.0, 20.0)),
    ("Upper Right", (20.0, 20.0)),
    ("Lower Left", (-20.0, -20.0)),
    ("Lower Right", (20.0, -20.0)),
)

_ANNOTATION_CHOICE_LABELS = {
    "data": "Data",
    "axes_fraction": "Axes fraction",
    "offset_points": "Offset points",
    "line": "Line",
    "arrow": "Arrow",
    "filled_arrow": "Filled Arrow",
    "double_arrow": "Double Arrow",
    "straight": "Straight",
    "angle": "Angle",
    "arc": "Arc",
    "normal": "Normal",
    "italic": "Italic",
    "oblique": "Oblique",
    "left": "Left",
    "center": "Center",
    "right": "Right",
    "top": "Top",
    "bottom": "Bottom",
    "baseline": "Baseline",
    "center_baseline": "Center baseline",
}


def _label_choice_editors(section: PropertySection) -> None:
    for editor in section._editors.values():
        if not isinstance(editor, QComboBox):
            continue
        for index in range(editor.count()):
            value = editor.itemData(index)
            label = _ANNOTATION_CHOICE_LABELS.get(str(value))
            if label is not None:
                editor.setItemText(index, label)


class AnnotationPropertySection(PropertySection):
    """Property section with human-readable Annotation enum labels."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _label_choice_editors(self)


class AnnotationTypographySection(TextTypographySection):
    """Shared typography controls with readable Annotation enum labels."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _label_choice_editors(self)


class AnnotationContentSection(QWidget, EditorSection):
    """Edit one Annotation's text, name, and visibility together."""

    def __init__(
        self,
        controller,
        *,
        context,
        apply_properties: ApplyProperties | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.context = context
        self._apply_properties = apply_properties
        self._disposed = False
        state = controller.read_state()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text_content = QPlainTextEdit(self)
        self.text_content.setPlaceholderText("Annotation text")
        self.text_content.setPlainText(str(state.properties["text"]))
        layout.addWidget(self.text_content)

        details = QFormLayout()
        configure_inspector_form(details)
        details.setContentsMargins(0, 6, 0, 0)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Component Tree name")
        apply_expanding_field(self.name_input)
        self.name_input.setText(str(state.properties.get("label", "")))
        self.visible_input = QCheckBox(self)
        self.visible_input.setChecked(bool(state.properties.get("visible", True)))
        details.addRow(QLabel("Name", self), self.name_input)
        details.addRow(QLabel("Visible", self), self.visible_input)
        layout.addLayout(details)

        self._text_binding = DebouncedTextBinding(
            self.text_content,
            self._apply_patch,
            delay_ms=250,
            result_presenter=lambda result: context.messages.present(
                result,
                success="Annotation text updated.",
            ),
            parent=self,
        )
        self._name_binding = DebouncedTextBinding(
            self.name_input,
            self._apply_name,
            delay_ms=250,
            result_presenter=lambda result: context.messages.present(
                result,
                success="Annotation name updated.",
            ),
            parent=self,
        )
        self.visible_input.toggled.connect(self._apply_visible)

    def _apply_patch(self, content: str):
        return self._apply({"text": content})

    def _apply_name(self, name: str):
        return self._apply({"label": name})

    def _apply_visible(self, state) -> bool:
        if self._disposed:
            return False
        checked = (
            bool(state)
            if isinstance(state, bool)
            else state in {Qt.Checked, Qt.CheckState.Checked}
        )
        result = self._apply({"visible": checked})
        accepted = self.context.messages.present(
            result,
            success="Annotation visibility updated.",
        )
        if not accepted:
            blocker = QSignalBlocker(self.visible_input)
            self.visible_input.setChecked(
                bool(
                    self.controller.read_state().properties.get(
                        "visible", True
                    )
                )
            )
            del blocker
        return accepted

    def _apply(self, patch: dict):
        if self._apply_properties is not None:
            return self._apply_properties(patch)
        return self.controller.set_property(
            next(iter(patch)), next(iter(patch.values()))
        )

    def set_text_content(self):
        """Flush the pending annotation text edit."""

        return self._text_binding.flush()

    def sync_from_controller(self) -> None:
        """Refresh controls from authoritative Controller state."""

        state = self.controller.read_state()
        text = str(state.properties["text"])
        name = str(state.properties.get("label", ""))
        # A compound change (for example a placement preset) has no single
        # property key and therefore refreshes every Section.  Preserve a
        # user's still-pending text/name edit unless the authoritative value
        # for that exact field actually changed.
        if text != self._text_binding.last_valid_text:
            self._text_binding.set_text(text)
        if name != self._name_binding.last_valid_text:
            self._name_binding.set_text(name)
        blocker = QSignalBlocker(self.visible_input)
        self.visible_input.setChecked(bool(state.properties.get("visible", True)))
        del blocker

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        self._text_binding.cancel()
        self._name_binding.cancel()
        try:
            self.visible_input.toggled.disconnect(self._apply_visible)
        except (RuntimeError, TypeError):
            pass


class AnnotationPlacementSection(AnnotationPropertySection):
    """Edit the Annotation text position plus the UI-only placement preset."""

    KEYS = ("xytext", "textcoords")

    def __init__(
        self,
        controller,
        *,
        context,
        apply_properties,
        parent=None,
    ):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        self.preset_input = QComboBox(self)
        self.preset_input.addItem("Custom")
        for name, _offset in ANNOTATION_PLACEMENT_PRESETS:
            self.preset_input.addItem(name)
        self.preset_input.setCurrentIndex(0)
        self.preset_input.setToolTip(
            "Fill the text position with one fixed offset preset"
        )
        self.form_layout.addRow("Placement preset", self.preset_input)
        self.preset_input.activated.connect(self._apply_preset)

    def _apply_preset(self, index: int) -> None:
        if index <= 0:
            self.preset_input.setCurrentIndex(0)
            return
        _name, offset = ANNOTATION_PLACEMENT_PRESETS[index - 1]
        result = self._apply_properties(
            {"textcoords": "offset_points", "xytext": list(offset)}
        )
        accepted = self.context.messages.present(
            result,
            success="Annotation text position updated.",
        )
        self.preset_input.setCurrentIndex(0)
        if not accepted:
            self.sync_from_controller()

    def sync_from_controller(self) -> None:
        """Placement presets are one-shot and never persist a selection."""

        self.preset_input.setCurrentIndex(0)
        super().sync_from_controller()


class AnnotationArrowSection(AnnotationPropertySection):
    """Edit the Annotation arrow; hidden arrows keep their values."""

    KEYS = (
        "arrow_enabled",
        "arrow_style",
        "arrow_color",
        "arrow_linewidth",
        "connection_style",
    )

    def __init__(self, controller, *, context, apply_properties, parent=None):
        super().__init__(
            controller,
            context=context,
            property_keys=self.KEYS,
            apply_properties=apply_properties,
            parent=parent,
        )
        self._sync_arrow_enabled()

    def _sync_arrow_enabled(self) -> None:
        enabled = bool(
            self.controller.read_state().properties.get("arrow_enabled", True)
        )
        for key in self.KEYS[1:]:
            editor = self._editors.get(key)
            if editor is not None:
                editor.setEnabled(enabled)

    def sync_from_controller(self) -> None:
        """Refresh controls and arrow-dependent enablement."""

        super().sync_from_controller()
        self._sync_arrow_enabled()
