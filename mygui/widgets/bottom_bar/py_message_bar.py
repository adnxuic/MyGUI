"""Display leveled user-facing messages in the bottom bar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

from mygui.widgets.ui_components import (
    UiRole,
    UiTextRole,
    UiTone,
    apply_elided_text,
    apply_text_style,
    apply_ui_style,
)


class PyMessageBar(QFrame):
    """Provide the py message bar Qt widget."""

    _LEVELS = frozenset({"info", "success", "warning", "error"})
    _PREFIXES = {
        "info": "",
        "success": "Success — ",
        "warning": "Warning — ",
        "error": "Error — ",
    }
    _TONE = {
        "info": UiTone.INFO,
        "success": UiTone.SUCCESS,
        "warning": UiTone.WARNING,
        "error": UiTone.ERROR,
    }
    _LEVEL_NAMES = {
        "info": "Info",
        "success": "Success",
        "warning": "Warning",
        "error": "Error",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("message_bar")
        self.setAccessibleName("Application messages")
        apply_ui_style(self, role=UiRole.STATUS, tone=UiTone.INFO)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.message_label = QLabel("")
        self.message_label.setObjectName("bottom_bar_message")
        self.message_label.setAccessibleName("Application message")
        self.message_label.setTextFormat(Qt.PlainText)
        self.message_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.message_label.setWordWrap(False)
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._full_text = ""
        self.layout.addWidget(self.message_label)
        self._set_level("info")

    @property
    def full_message(self) -> str:
        """Return the unelided message body without a level prefix."""

        return self._full_text

    def show_message(self, message, level="info"):
        """Show message."""

        self._full_text = str(message)
        normalized_level = str(level).lower()
        if normalized_level not in self._LEVELS:
            normalized_level = "info"
        current = str(self.property("level") or "info")
        if current != normalized_level:
            self._set_level(normalized_level)
        self._apply_visible_text()

    def resizeEvent(self, event):
        """Re-elide the current message when the existing bar width changes."""

        super().resizeEvent(event)
        self._apply_visible_text()

    def _prefixed_text(self, level: str) -> str:
        body = self._full_text
        if not body:
            return ""
        return f"{self._PREFIXES.get(level, '')}{body}"

    def _apply_visible_text(self):
        if not hasattr(self, "_full_text"):
            return
        level = str(self.property("level") or "info")
        if level not in self._LEVELS:
            level = "info"
        display = self._prefixed_text(level)
        label = self.message_label
        width = max(1, label.width() - 12)
        font_key = label.font().toString()
        cache_key = (display, width, font_key, level, self._full_text)
        if cache_key == getattr(self, "_visible_cache", None):
            return
        self._visible_cache = cache_key
        apply_elided_text(label, display)
        if display:
            label.setToolTip(display)
            description = f"{self._LEVEL_NAMES[level]}: {self._full_text}"
            label.setAccessibleName(description)
            label.setAccessibleDescription(description)
            self.setAccessibleDescription(description)
        else:
            label.setToolTip("")
            label.setAccessibleName("Application message")
            label.setAccessibleDescription("")
            self.setAccessibleDescription("")

    def _set_level(self, level):
        normalized_level = str(level).lower()
        if normalized_level not in self._LEVELS:
            normalized_level = "info"

        tone = self._TONE[normalized_level]
        self.setProperty("level", normalized_level)
        self.message_label.setProperty("level", normalized_level)
        apply_ui_style(self, role=UiRole.STATUS, tone=tone)
        apply_ui_style(self.message_label, role=UiRole.STATUS, tone=tone)
        apply_text_style(self.message_label, UiTextRole.BODY, tone=tone)

    def show_error(self, message):
        """Show error."""

        self.show_message(message, "error")

    def show_success(self, message):
        """Show success."""

        self.show_message(message, "success")

    def show_warning(self, message):
        """Show warning."""

        self.show_message(message, "warning")

    def clear_message(self):
        """Clear the current Message Bar text and reset its level."""

        self.show_message("", "info")
