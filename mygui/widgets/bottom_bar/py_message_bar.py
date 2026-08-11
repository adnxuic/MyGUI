"""Display leveled user-facing messages in the bottom bar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy


class PyMessageBar(QFrame):
    """Provide the py message bar Qt widget."""

    _LEVELS = frozenset({"info", "success", "warning", "error"})

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("message_bar")
        self.setAccessibleName("Application messages")

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
        self.layout.addWidget(self.message_label)
        self._set_level("info")

    def show_message(self, message, level="info"):
        """Show message."""

        message = str(message)
        self.message_label.setText(message)
        self.message_label.setToolTip(message)
        self._set_level(level)

    def _set_level(self, level):
        normalized_level = str(level).lower()
        if normalized_level not in self._LEVELS:
            normalized_level = "info"

        self.setProperty("level", normalized_level)
        self.message_label.setProperty("level", normalized_level)
        for widget in (self, self.message_label):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)

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
