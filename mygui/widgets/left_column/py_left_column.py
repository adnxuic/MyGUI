"""Provide project actions and Explorer shortcuts in the left activity rail."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout
from mygui.application_theme import (
    bind_widget_qss,
    current_density_metrics,
    current_qss_tokens,
    subscribe_theme_window,
)
from mygui.resources import icon_path as resolve_icon_path
from mygui.widgets.left_column.py_setting_dialog import PySettingDialog
from mygui.application_theme.runtime import default_theme_runtime
from mygui.widgets.ui_components import UiRole, UiVariant, apply_ui_style


def _tinted_icon(icon_path, color):
    pixmap = QPixmap(icon_path)
    if pixmap.isNull():
        return QIcon(icon_path)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


def _chrome_icon(icon_path, *, variant="", fallback_color=None, widget=None):
    runtime = default_theme_runtime()
    snapshot = runtime.snapshot
    if snapshot is None:
        return _tinted_icon(
            icon_path,
            fallback_color
            or current_qss_tokens().get("COLOR_TEXT_PRIMARY", "#1f2937"),
        )
    return runtime.icon_provider.icon(
        icon_path,
        snapshot=snapshot,
        variant=variant,
        widget=widget,
    )


class PyLeftColumn(QFrame):
    """Provide the left activity rail Qt widget."""

    explorerModeRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setting_dialog = None
        self._reset_layout_callback = None
        self._open_settings = None

        self.setObjectName("left_column")
        bind_widget_qss(self, "mygui/widgets/left_column/style.qss")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.table_button = self._explorer_button(
            "table_button",
            resolve_icon_path("tables.svg"),
            "Show or hide the table workspace",
            "Toggle table workspace",
            "table",
        )
        self.layout.addWidget(self.table_button)

        self.components_button = self._explorer_button(
            "components_button",
            resolve_icon_path("ComTree.svg"),
            "Show or hide the Components tree",
            "Toggle Components tree",
            "components",
        )
        self.layout.addWidget(self.components_button)
        self.layout.addStretch(1)

        self.setting_button = QPushButton(
            QIcon(resolve_icon_path("setting.svg")),
            "",
        )
        self.setting_button.setObjectName("setting_button")
        self.setting_button.setToolTip("Open settings")
        self.setting_button.setAccessibleName("Open settings")
        apply_ui_style(
            self.setting_button,
            role=UiRole.BUTTON,
            variant=UiVariant.GHOST,
        )
        self.setting_button.setIcon(
            _chrome_icon(
                resolve_icon_path("setting.svg"),
                fallback_color=current_qss_tokens().get("COLOR_TEXT_PRIMARY", "#1f2937"),
                widget=self,
            )
        )
        self.setting_button.clicked.connect(self.show_setting_dialog)
        self.layout.addWidget(self.setting_button)

        self.set_explorer_state("table", True)
        subscribe_theme_window(self)
        self.apply_theme_metrics(current_density_metrics())

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
        apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.GHOST)
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
                resolve_icon_path("tables.svg"),
            ),
            (
                self.components_button,
                "components",
                resolve_icon_path("ComTree.svg"),
            ),
        ):
            button.setChecked(active[key])
            button.setIcon(
                _chrome_icon(
                    path,
                    variant="on_accent" if active[key] else "",
                    fallback_color=(
                        current_qss_tokens().get("COLOR_TEXT_ON_DARK", "#f8fafc")
                        if active[key]
                        else current_qss_tokens().get("COLOR_TEXT_PRIMARY", "#1f2937")
                    ),
                    widget=self,
                )
            )

    def apply_theme_metrics(self, metrics) -> None:
        """Apply activity-rail width from the published density metrics."""

        self.setFixedWidth(metrics.rail)

    def apply_theme_icons(self, snapshot, provider) -> None:
        """Retint rail chrome icons for the published scheme."""

        self.set_explorer_state(
            "table" if self.table_button.isChecked() else "components",
            self.table_button.isChecked() or self.components_button.isChecked(),
        )
        self.setting_button.setIcon(
            provider.icon(
                resolve_icon_path("setting.svg"),
                snapshot=snapshot,
                widget=self,
            )
        )

    def show_setting_dialog(self):
        """Open Settings. Production injects the Settings Center host."""

        if self._open_settings is not None:
            self._open_settings()
            return
        if self.setting_dialog is None:
            self.setting_dialog = PySettingDialog(
                parent=self.window(),
                reset_layout_callback=self._reset_layout_callback,
            )
        self.setting_dialog.exec()

    def set_open_settings(self, callback):
        """Inject the shared Settings Center opener (gear, menu, shortcut)."""

        self._open_settings = callback

    def set_reset_layout_callback(self, callback):
        """Set reset layout callback."""

        self._reset_layout_callback = callback
        if self.setting_dialog is not None:
            self.setting_dialog.set_reset_layout_callback(callback)
