"""Display compact title-bar actions with overflow handling."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QSize, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStyle,
    QToolBar,
    QToolButton,
    QWidget,
)


DialogFactory = Callable[[QWidget | None], QDialog]
IconSource = str | QIcon


class LazyDialogAction(QAction):
    """Toolbar action that creates its dialog only when it is first used."""

    def __init__(
        self,
        text: str,
        icon: IconSource,
        dialog_factory: DialogFactory,
        parent: QObject,
        *,
        reuse_dialog: bool = True,
    ):
        super().__init__(QIcon(icon), text, parent)
        self.setToolTip(text)
        self.setStatusTip(text)
        self._dialog_factory = dialog_factory
        self._reuse_dialog = reuse_dialog
        self._dialog: QDialog | None = None
        self.triggered.connect(self.show_dialog)

    @property
    def dialog(self) -> QDialog | None:
        """Return the dialog."""

        return self._dialog

    def _dialog_parent(self) -> QWidget | None:
        parent = self.parent()
        if isinstance(parent, QWidget):
            return parent.window()
        return None

    def show_dialog(self, _checked: bool = False):
        """Show dialog."""

        dialog = self._dialog
        if dialog is None:
            dialog = self._dialog_factory(self._dialog_parent())
            if self._reuse_dialog:
                self._dialog = dialog
        dialog.exec()
        if not self._reuse_dialog:
            dialog.deleteLater()


class ResponsiveActionGallery(QFrame):
    """A compact action gallery that delegates overflow to ``QToolBar``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("selector_menu")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("selector_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.toolbar.setIconSize(QSize(40, 40))
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.overflow_button = self.toolbar.findChild(
            QToolButton, "qt_toolbar_ext_button"
        )
        self._overflow_timer = QTimer(self)
        self._overflow_timer.setSingleShot(True)
        self._overflow_timer.timeout.connect(self._sync_overflow_reservation)

        self.action_dict: dict[str, LazyDialogAction] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)

    def showEvent(self, event):
        """Refresh the widget when Qt makes it visible."""

        super().showEvent(event)
        self._schedule_overflow_reservation()

    def resizeEvent(self, event):
        """Reflow child controls after the widget is resized."""

        super().resizeEvent(event)
        self._schedule_overflow_reservation()

    def _schedule_overflow_reservation(self):
        self._overflow_timer.start(0)

    def _sync_overflow_reservation(self):
        """Reserve the width added to Qt's native toolbar extension by QSS."""
        button = self.overflow_button
        if button is None:
            return

        reserved_by_style = self.toolbar.style().pixelMetric(
            QStyle.PM_ToolBarExtensionExtent,
            None,
            self.toolbar,
        )
        required_margin = (
            max(0, button.width() - reserved_by_style)
            if button.isVisible()
            else 0
        )
        margins = self.toolbar.contentsMargins()
        if margins.right() == required_margin:
            return
        self.toolbar.setContentsMargins(
            margins.left(),
            margins.top(),
            required_margin,
            margins.bottom(),
        )

    def add_dialog_action(
        self,
        name: str,
        icon: IconSource,
        dialog_factory: DialogFactory,
        *,
        reuse_dialog: bool = True,
    ) -> LazyDialogAction:
        """Add dialog action."""

        action = LazyDialogAction(
            name,
            icon,
            dialog_factory,
            self,
            reuse_dialog=reuse_dialog,
        )
        self.action_dict[name] = action
        self.toolbar.addAction(action)
        button = self.toolbar.widgetForAction(action)
        if button is not None:
            button.setAccessibleName(name)
            button.setToolTip(name)
        return action
