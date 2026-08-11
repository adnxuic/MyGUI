"""Provide a reusable empty-state widget for unpopulated views."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class PyEmptyState(QFrame):
    """Reusable empty-state panel with an optional primary action."""

    primaryRequested = Signal()

    def __init__(self, title: str, detail: str, primary_text: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("empty_state")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("empty_state_title")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.detail_label = QLabel(detail, self)
        self.detail_label.setObjectName("empty_state_detail")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.primary_button = None
        if primary_text:
            self.primary_button = QPushButton(primary_text, self)
            self.primary_button.setObjectName("empty_state_primary_button")
            self.primary_button.setAccessibleName(primary_text)
            self.primary_button.clicked.connect(self.primaryRequested)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(self.primary_button)
            button_row.addStretch(1)
            layout.addLayout(button_row)

        layout.addStretch(1)

