"""Display compact title-bar actions with overflow handling."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

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

from mygui.application_theme import current_density_metrics, subscribe_theme_window
from mygui.application_theme.icons import IconRole, classify_icon_source
from mygui.application_theme.runtime import default_theme_runtime
from mygui.widgets.title_bar.style_gallery import LAYOUT_BUTTON_MIN_WIDTH
from mygui.widgets.ui_components import (
    UiRole,
    UiVariant,
    apply_elided_text,
    apply_ui_style,
)

if TYPE_CHECKING:
    from mygui.application_theme.icons import CachingThemeIconProvider
    from mygui.application_theme.models import ThemeSnapshot

DialogFactory = Callable[[QWidget | None], QDialog]
IconSource = str | QIcon | Path
QWIDGETSIZE_MAX = 16777215
_FILE_ICON_CACHE: dict[str, QIcon] = {}


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
        toolbar_label: str | None = None,
        tooltip: str | None = None,
    ):
        self._icon_source = icon
        resolved_icon = self._resolve_icon(icon, parent)
        display = toolbar_label if toolbar_label is not None else text
        super().__init__(resolved_icon, display, parent)
        hint = tooltip if tooltip is not None else text
        self.setToolTip(hint)
        self.setStatusTip(hint)
        self._accessible_name = hint
        self._dialog_factory = dialog_factory
        self._reuse_dialog = reuse_dialog
        self._dialog: QDialog | None = None
        self.triggered.connect(self.show_dialog)

    @staticmethod
    def _resolve_icon(icon: IconSource, parent: QObject | None = None) -> QIcon:
        if isinstance(icon, QIcon):
            return icon
        source = str(icon)
        runtime = default_theme_runtime()
        snapshot = runtime.snapshot
        if snapshot is not None and runtime.icon_provider is not None:
            if classify_icon_source(source) is IconRole.CHROME:
                widget = parent if isinstance(parent, QWidget) else None
                return runtime.icon_provider.icon(
                    source,
                    snapshot=snapshot,
                    widget=widget,
                )
        cached = _FILE_ICON_CACHE.get(source)
        if cached is not None:
            return QIcon(cached)
        resolved = QIcon(source)
        _FILE_ICON_CACHE[source] = QIcon(resolved)
        return resolved

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
            subscribe_theme_window(dialog)
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
        metrics = current_density_metrics()
        self.toolbar.setIconSize(QSize(metrics.gallery_icon, metrics.gallery_icon))
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.overflow_button = self.toolbar.findChild(
            QToolButton, "qt_toolbar_ext_button"
        )
        self._overflow_timer = QTimer(self)
        self._overflow_timer.setSingleShot(True)
        self._overflow_timer.timeout.connect(self._sync_overflow_reservation)
        self._overflow_syncing = False

        self.action_dict: dict[str, LazyDialogAction] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        subscribe_theme_window(self)

    def apply_theme_metrics(self, metrics) -> None:
        """Apply gallery height and icon size from the published density metrics."""

        self.setMinimumHeight(metrics.gallery)
        self.setMaximumHeight(metrics.gallery)
        self.toolbar.setIconSize(QSize(metrics.gallery_icon, metrics.gallery_icon))
        for action in self.action_dict.values():
            button = self.toolbar.widgetForAction(action)
            if button is None:
                continue
            if button.objectName() == "layout_template_button":
                button.setMinimumWidth(LAYOUT_BUTTON_MIN_WIDTH)
                button.setMaximumWidth(QWIDGETSIZE_MAX)
            button.setMinimumHeight(0)
            button.setMaximumHeight(metrics.gallery)
        self._schedule_overflow_reservation()

    def apply_theme_icons(
        self,
        snapshot: ThemeSnapshot,
        provider: CachingThemeIconProvider,
    ) -> None:
        """Retint chrome action icons for the published scheme."""

        for action in self.action_dict.values():
            source = getattr(action, "_icon_source", None)
            if isinstance(source, (str, Path)):
                if classify_icon_source(str(source)) is IconRole.CHROME:
                    action.setIcon(
                        provider.icon(
                            str(source),
                            snapshot=snapshot,
                            widget=self,
                        )
                    )
        self._schedule_overflow_reservation()

    def showEvent(self, event):
        """Refresh the widget when Qt makes it visible."""

        super().showEvent(event)
        self._schedule_overflow_reservation()

    def resizeEvent(self, event):
        """Reflow child controls after the widget is resized."""

        super().resizeEvent(event)
        if self._overflow_syncing:
            return
        if event.size() == event.oldSize():
            return
        self._schedule_overflow_reservation()

    def _schedule_overflow_reservation(self):
        if self._overflow_timer.isActive() or self._overflow_syncing:
            return
        self._overflow_timer.start(0)

    def _sync_overflow_reservation(self):
        """Reserve the width added to Qt's native toolbar extension by QSS."""
        button = self.overflow_button
        if button is None:
            return

        self._overflow_syncing = True
        try:
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
            if margins.right() != required_margin:
                self.toolbar.setContentsMargins(
                    margins.left(),
                    margins.top(),
                    required_margin,
                    margins.bottom(),
                )
            self._elide_gallery_labels()
        finally:
            self._overflow_syncing = False

    def _elide_gallery_labels(self) -> None:
        """Elide visible gallery labels inside existing button widths."""

        for action in self.action_dict.values():
            button = self.toolbar.widgetForAction(action)
            if button is None or button.width() < 24:
                continue
            full = str(action.toolTip() or action.text())
            apply_elided_text(button, full, padding=16)
            button.setToolTip(full)

    def add_dialog_action(
        self,
        name: str,
        icon: IconSource,
        dialog_factory: DialogFactory,
        *,
        reuse_dialog: bool = True,
        toolbar_label: str | None = None,
        tooltip: str | None = None,
    ) -> LazyDialogAction:
        """Add dialog action."""

        action = LazyDialogAction(
            name,
            icon,
            dialog_factory,
            self,
            reuse_dialog=reuse_dialog,
            toolbar_label=toolbar_label,
            tooltip=tooltip,
        )
        self.action_dict[name] = action
        self.toolbar.addAction(action)
        button = self.toolbar.widgetForAction(action)
        if button is not None:
            accessible = tooltip if tooltip is not None else name
            button.setAccessibleName(accessible)
            button.setToolTip(accessible)
            apply_ui_style(
                button,
                role=UiRole.BUTTON,
                variant=UiVariant.GHOST,
            )
        return action
