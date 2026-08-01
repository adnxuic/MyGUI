"""Provide project actions and Explorer shortcuts in the left activity rail."""

import os

from Qt_core import *

from code.widgets import qss_func
from code.widgets.left_column.py_setting_dialog import PySettingDialog
from code.widgets.theme import COLORS


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


def _tinted_icon(icon_path, color):
    pixmap = QPixmap(icon_path)
    if pixmap.isNull():
        return QIcon(icon_path)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


class PyLeftColumn(QFrame):
    """Provide the left activity rail Qt widget."""

    explorerModeRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setting_dialog = None
        self._reset_layout_callback = None

        self.setObjectName("left_column")
        self.setStyleSheet(qss_func.qss_loader(qss_path))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.table_button = self._explorer_button(
            "table_button",
            "pictures/icons/tables.svg",
            "Show or hide the table workspace",
            "Toggle table workspace",
            "table",
        )
        self.layout.addWidget(self.table_button)

        self.components_button = self._explorer_button(
            "components_button",
            "pictures/icons/ComTree.svg",
            "Show or hide the Components tree",
            "Toggle Components tree",
            "components",
        )
        self.layout.addWidget(self.components_button)
        self.layout.addStretch(1)

        self.setting_button = QPushButton(
            QIcon("pictures/icons/setting.svg"),
            "",
        )
        self.setting_button.setObjectName("setting_button")
        self.setting_button.setToolTip("Open settings")
        self.setting_button.setAccessibleName("Open settings")
        self.setting_button.setIcon(
            _tinted_icon(
                "pictures/icons/setting.svg",
                COLORS["text_primary"],
            )
        )
        self.setting_button.clicked.connect(self.show_setting_dialog)
        self.layout.addWidget(self.setting_button)

        self.set_explorer_state("table", True)

    def _explorer_button(
        self,
        object_name: str,
        icon_path: str,
        tooltip: str,
        accessible_name: str,
        mode: str,
    ) -> QPushButton:
        button = QPushButton(QIcon(icon_path), "")
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setAccessibleName(accessible_name)
        button.setCheckable(True)
        button.clicked.connect(
            lambda _checked=False, target=mode:
            self.explorerModeRequested.emit(target)
        )
        return button

    def set_explorer_state(self, mode: str, visible: bool) -> None:
        """Synchronize activity buttons with the Explorer state."""

        active = {
            "table": bool(visible and mode == "table"),
            "components": bool(visible and mode == "components"),
        }
        for button, key, path in (
            (
                self.table_button,
                "table",
                "pictures/icons/tables.svg",
            ),
            (
                self.components_button,
                "components",
                "pictures/icons/ComTree.svg",
            ),
        ):
            button.setChecked(active[key])
            button.setIcon(
                _tinted_icon(
                    path,
                    (
                        COLORS["text_on_dark"]
                        if active[key]
                        else COLORS["text_primary"]
                    ),
                )
            )

    def show_setting_dialog(self):
        """Show setting dialog."""

        if self.setting_dialog is None:
            self.setting_dialog = PySettingDialog(
                parent=self.window(),
                reset_layout_callback=self._reset_layout_callback,
            )
        self.setting_dialog.exec()

    def set_reset_layout_callback(self, callback):
        """Set reset layout callback."""

        self._reset_layout_callback = callback
        if self.setting_dialog is not None:
            self.setting_dialog.set_reset_layout_callback(callback)
