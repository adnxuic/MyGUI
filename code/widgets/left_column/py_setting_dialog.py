"""Edit general application settings."""

import os

from Qt_core import *

from code import status_messages
from code.widgets import qss_func


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "setting_dialog_style.qss")


class PySettingDialog(QDialog):
    """Provide the py setting dialog Qt widget."""

    def __init__(self, parent=None, reset_layout_callback=None):
        super().__init__(parent)
        self._reset_layout_callback = reset_layout_callback
        self.setObjectName("setting_dialog")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.setWindowTitle("Settings")
        self.setWindowIcon(QIcon("pictures/icons/setting.svg"))

        layout = QVBoxLayout(self)
        title = QLabel("Workspace")
        title.setObjectName("settings_section_title")
        layout.addWidget(title)

        self.reset_layout_button = QPushButton("Reset workspace layout")
        self.reset_layout_button.setEnabled(reset_layout_callback is not None)
        self.reset_layout_button.clicked.connect(self.reset_workspace_layout)
        layout.addWidget(self.reset_layout_button)

        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_reset_layout_callback(self, callback):
        """Set reset layout callback."""

        self._reset_layout_callback = callback
        self.reset_layout_button.setEnabled(callback is not None)

    def reset_workspace_layout(self):
        """Reset workspace layout."""

        if self._reset_layout_callback is None:
            return
        self._reset_layout_callback()
        status_messages.show_success("Workspace layout reset.")

