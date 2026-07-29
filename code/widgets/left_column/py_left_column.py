"""Provide project actions and integration shortcuts in the left column."""

from Qt_core import *
from code.widgets import qss_func
from code.widgets.left_column.py_setting_dialog import PySettingDialog
from code.widgets.theme import COLORS

import os

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
    """Provide the py left column Qt widget."""

    def __init__(self, table, fig_control_window):
        super().__init__()
        self.table = table
        self.fig_control_window = fig_control_window
        self.setting_dialog = None
        self._reset_layout_callback = None

        self.setObjectName("left_column")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 图表按钮
        self.table_button = QPushButton(QIcon("pictures/icons/tables.svg"), "")
        self.table_button.setObjectName("table_button")
        self.table_button.setToolTip("Show or hide the table workspace")
        self.table_button.setAccessibleName("Toggle table workspace")
        self.table_button.setCheckable(True)
        self.table_button.setChecked(True)
        self.table_button.toggled.connect(self.the_button_was_toggled)
        self._update_table_icon(True)
        self.layout.addWidget(self.table_button)

        # 添加弹性空间
        self.layout.addStretch(1)


        # 设置按钮
        self.setting_button = QPushButton(QIcon("pictures/icons/setting.svg"), "")
        self.setting_button.setObjectName("setting_button")
        self.setting_button.setToolTip("Open settings")
        self.setting_button.setAccessibleName("Open settings")
        self.setting_button.setIcon(
            _tinted_icon("pictures/icons/setting.svg", COLORS["text_primary"])
        )
        self.setting_button.clicked.connect(self.show_setting_dialog)
        self.layout.addWidget(self.setting_button)


    def the_button_was_toggled(self, checked):
        """Synchronize the button appearance after its checked state changes."""

        self.table.setVisible(checked)

        self._update_table_icon(checked)

    def _update_table_icon(self, checked):
        color = COLORS["text_on_dark"] if checked else COLORS["text_primary"]
        self.table_button.setIcon(_tinted_icon("pictures/icons/tables.svg", color))

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
