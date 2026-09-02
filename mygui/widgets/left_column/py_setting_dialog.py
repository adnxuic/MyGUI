"""Edit general application settings."""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout
from mygui.widgets.english_buttons import apply_english_dialog_buttons
from mygui.application_theme import bind_widget_qss
from mygui.resources import icon_path
from mygui.application_theme import subscribe_theme_window


class PySettingDialog(QDialog):
    """Provide the py setting dialog Qt widget."""

    def __init__(self, parent=None, reset_layout_callback=None):
        super().__init__(parent)
        self._reset_layout_callback = reset_layout_callback
        self.setObjectName("setting_dialog")
        bind_widget_qss(
            self,
            "mygui/widgets/left_column/setting_dialog_style.qss",
        )
        self.setWindowTitle("Settings")
        self.setWindowIcon(QIcon(icon_path("setting.svg")))
        self.setProperty("themeChromeWindowIcon", icon_path("setting.svg"))

        layout = QVBoxLayout(self)
        title = QLabel("Workspace")
        title.setObjectName("settings_section_title")
        layout.addWidget(title)

        self.reset_layout_button = QPushButton("Reset workspace layout")
        self.reset_layout_button.setEnabled(reset_layout_callback is not None)
        self.reset_layout_button.clicked.connect(self.reset_workspace_layout)
        layout.addWidget(self.reset_layout_button)

        layout.addStretch(1)
        buttons = apply_english_dialog_buttons(QDialogButtonBox(QDialogButtonBox.Close))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        subscribe_theme_window(self)

    def set_reset_layout_callback(self, callback):
        """Set reset layout callback."""

        self._reset_layout_callback = callback
        self.reset_layout_button.setEnabled(callback is not None)

    def reset_workspace_layout(self):
        """Ask MainWindow to reset. Confirmation and Message Bar stay there."""

        if self._reset_layout_callback is None:
            return
        self._reset_layout_callback()
