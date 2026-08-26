"""Provide reusable title-bar button variants."""

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QPushButton

from mygui.resources import icon_path
from mygui.application_theme import current_qss_tokens
from mygui.application_theme.runtime import default_theme_runtime


class ChangeButton(QPushButton):
    """Switch between selector and menu command rows."""

    def __init__(self, button_name):
        super().__init__()
        self.setIcon(QIcon(icon_path("menu_change.svg")))
        self.setObjectName("change_button")
        self.setToolTip("Switch command menu")
        self.setAccessibleName("Switch command menu")
        self.setCheckable(True)
        self.clicked.connect(self.change)
        self.rotated = False
        self._apply_change_icon()

    def _apply_change_icon(self):
        angle = 90 if self.rotated else 0
        runtime = default_theme_runtime()
        snapshot = runtime.snapshot
        if snapshot is None:
            color = QColor(
                current_qss_tokens()["COLOR_TEXT_PRIMARY"]
                if self.rotated
                else current_qss_tokens()["COLOR_TEXT_ON_DARK"]
            )
            pixmap = QPixmap(icon_path("menu_change.svg"))
            rotated_pixmap = pixmap.transformed(QTransform().rotate(angle))
            painter = QPainter(rotated_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(rotated_pixmap.rect(), color)
            painter.end()
            self.setIcon(QIcon(rotated_pixmap))
            return
        variant = "on_surface" if self.rotated else "on_command"
        self.setIcon(
            runtime.icon_provider.icon(
                icon_path("menu_change.svg"),
                snapshot=snapshot,
                variant=variant,
                widget=self,
                angle=angle,
            )
        )

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Retint the command-switch glyph for the published scheme."""

        self._apply_change_icon()

    def change(self):
        """Rotate and recolor the command-switch icon."""

        self.rotated = not self.rotated
        self._apply_change_icon()


class SelectMenuButton(QPushButton):
    """Select one command gallery from the selector row."""

    def __init__(self, button_name, IconName=None):
        super().__init__()
        self.setObjectName("select_menu_button")
        self.setText(button_name)
        self.IconName = IconName
        self.setIcon(QIcon(IconName))
        self.setCheckable(True)
        self.toggled.connect(self.the_button_was_toggled)

    def the_button_was_toggled(self, checked):
        """Synchronize the icon tint with the checked state."""

        color = QColor(0, 0, 0) if checked else QColor(255, 255, 255)
        runtime = default_theme_runtime()
        snapshot = runtime.snapshot
        if snapshot is not None:
            variant = "on_surface" if checked else "on_command"
            self.setIcon(
                runtime.icon_provider.icon(
                    self.IconName,
                    snapshot=snapshot,
                    variant=variant,
                    widget=self,
                )
            )
            return
        pixmap = QPixmap(self.IconName)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        self.setIcon(QIcon(pixmap))

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Retint the selector glyph for the published scheme and checked state."""

        self.the_button_was_toggled(self.isChecked())


class MenuButton(QPushButton):
    """Display one command in the dark menu row."""

    def __init__(self, button_name, IconName=None, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("menu_button")
        self.setText(button_name)
        self.IconName = IconName
        self.setToolTip(button_name.capitalize())
        self.setAccessibleName(button_name.capitalize())
        self._set_dark_bar_icon(IconName)

    def _set_dark_bar_icon(self, icon_name):
        if not icon_name:
            self.setIcon(QIcon())
            return
        pixmap = QPixmap(icon_name)
        if pixmap.isNull():
            self.setIcon(QIcon(icon_name))
            return
        runtime = default_theme_runtime()
        snapshot = runtime.snapshot
        if snapshot is not None:
            self.setIcon(
                runtime.icon_provider.icon(
                    icon_name,
                    snapshot=snapshot,
                    variant="on_command",
                    widget=self,
                )
            )
            return
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(current_qss_tokens()["COLOR_TEXT_ON_DARK"]))
        painter.end()
        self.setIcon(QIcon(pixmap))

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Retint the dark command-row glyph."""

        self._set_dark_bar_icon(self.IconName)
