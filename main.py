"""Start MyGUI and compose its top-level Qt workspace."""

import ctypes
import sys
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")

from PySide6.QtCore import QCoreApplication, QSettings, QTimer, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages, tex_config
from mygui.font_diagnostics import (
    flush_font_diagnostics,
    install_font_diagnostic_bridge,
)

tex_config.initialize_tex_runtime()
from mygui.database import TableRepository
from mygui.excel_io import import_excel_into_workspace, is_supported_excel_workbook
from mygui.resources import load_qss_resource, resource_path
from mygui.text_io import import_text_into_workspace
from mygui.widgets.bottom_bar.py_bottom_bar import PyBottomBar
from mygui.widgets.component_tree import ComponentTreeHost
from mygui.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from mygui.widgets.figure_canvas.py_figure_window import PyFigureWindow
from mygui.widgets.left_column import (
    ExplorerMode,
    LeftExplorerHost,
    PyLeftColumn,
)
from mygui.widgets.mainwindow_init import mainwindow_qss
from mygui.widgets.right_column.py_right_column import PyRightColumn
from mygui.widgets.table.py_table import PyTable
from mygui.widgets.theme import CONTROL_SIZES, FONT_FAMILIES, FONT_SIZE_PT
from mygui.widgets.title_bar.py_title_bar import PyTitleBar
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary


APP_ICON_PATH = resource_path("pictures/icons/app_icon.ico")
WINDOWS_APP_USER_MODEL_ID = "MyGUI.Desktop"


def configure_windows_taskbar_identity() -> bool:
    """Give the process a stable Windows taskbar identity when supported."""

    if sys.platform != "win32":
        return False
    try:
        result = (
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                WINDOWS_APP_USER_MODEL_ID
            )
        )
    except (AttributeError, OSError):
        return False
    return result == 0


def configure_application_icon(application: QApplication) -> QIcon:
    """Apply the shared application icon and return the loaded Qt icon."""

    icon = QIcon(str(APP_ICON_PATH))
    application.setWindowIcon(icon)
    return icon


def configure_application_font(application: QApplication) -> QFont:
    """Apply the shared cross-platform font stack and return the Qt font."""

    font = QFont()
    font.setFamilies(list(FONT_FAMILIES))
    font.setPointSize(FONT_SIZE_PT)
    application.setFont(font)
    return font


class MainWindow(QMainWindow):
    """Coordinate the application's table, Figure, and Inspector workspaces."""

    WORKSPACE_SETTINGS_GROUP = "workspaceLayout"
    WORKSPACE_SETTINGS_VERSION = 2
    DEFAULT_OUTER_SPLITTER_SIZES = (45, 55)
    DEFAULT_EXPLORER_SPLITTER_SIZES = (420, 240)
    MIN_CANVAS_WIDTH = 400
    MIN_DEFAULT_LEFT_WIDTH = 572
    MAX_DEFAULT_LEFT_WIDTH = 760
    MAX_PERSISTED_SPLITTER_SIZE = 100_000
    MIN_PERSISTED_SPLITTER_SHARE = 0.01

    def __init__(self, *, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings
        self._workspace_layout_restored = False
        self._last_visible_explorer_sizes = list(
            self.DEFAULT_EXPLORER_SPLITTER_SIZES
        )
        self._explorer_mode = ExplorerMode.TABLE
        self._explorer_visible = True
        self.setWindowTitle("MyGUI")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setup_ui()
        self.setAcceptDrops(True)

    def setup_ui(self):
        """Build the main window and connect its shared application services."""

        self.setObjectName("MainWindow")
        self.setStyleSheet(mainwindow_qss)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("central_widget")
        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.central_widget_layout = QVBoxLayout(self.central_widget)
        self.central_widget_layout.setSpacing(0)
        self.central_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.repository = TableRepository(self)
        self.color_library = ColorLibrary(self.settings, self)
        self.table = PyTable(self.repository)
        self.table.setMinimumWidth(220)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.component_tree_host = ComponentTreeHost()
        self.component_tree_host.setMinimumWidth(220)
        self.component_tree_host.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.left_explorer = LeftExplorerHost(
            self.table,
            self.component_tree_host,
        )
        self.left_explorer.setMinimumWidth(220)
        self.left_explorer.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.fig_control_window = PyFigControlWindow()
        self.fig_control_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.figure_window = PyFigureWindow(
            figure_inspector_host=(
                self.fig_control_window.figure_inspector_host
            ),
            repository=self.repository,
            color_library=self.color_library,
            component_tree_host=self.component_tree_host,
        )
        self.figure_window.setMinimumWidth(self.MIN_CANVAS_WIDTH)
        self.figure_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.figure_window.set_table(self.table)

        self.title_bar = PyTitleBar(
            self,
            figure_window=self.figure_window,
            table=self.table,
        )
        self.figure_window.requestStyleSelector.connect(self.title_bar.show_style_selector)
        self.figure_window.projectCloseRequested.connect(
            self.close_project_from_tab
        )
        self.figure_window.figureExportRequested.connect(
            self.title_bar.menu_bar.export_canvas
        )
        self.central_widget_layout.addWidget(self.title_bar, stretch=0)

        self.left_column = PyLeftColumn()
        self.left_column.set_reset_layout_callback(self.reset_workspace_layout)
        self.right_column = PyRightColumn(self.fig_control_window.layout)
        self.left_column.setFixedWidth(CONTROL_SIZES["activity_rail"])
        self.right_column.setFixedWidth(CONTROL_SIZES["activity_rail"])

        self.explorer_control_splitter = QSplitter(Qt.Horizontal)
        self.explorer_control_splitter.setObjectName(
            "explorer_control_splitter"
        )
        self.explorer_control_splitter.setChildrenCollapsible(False)
        self.explorer_control_splitter.addWidget(self.left_explorer)
        self.explorer_control_splitter.addWidget(self.fig_control_window)
        self.explorer_control_splitter.setStretchFactor(0, 0)
        self.explorer_control_splitter.setStretchFactor(1, 1)
        self.explorer_control_splitter.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.left_workspace = QWidget()
        self.left_workspace.setObjectName("left_workspace")
        self.left_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.left_middle_layout = QHBoxLayout(self.left_workspace)
        self.left_middle_layout.setSpacing(0)
        self.left_middle_layout.setContentsMargins(0, 0, 0, 0)
        self.left_middle_layout.addWidget(self.left_column)
        self.left_middle_layout.addWidget(self.explorer_control_splitter)
        self.left_middle_layout.addWidget(self.right_column)

        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.setObjectName("workspace_splitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self.left_workspace)
        self.workspace_splitter.addWidget(self.figure_window)
        self.workspace_splitter.setStretchFactor(0, 45)
        self.workspace_splitter.setStretchFactor(1, 55)
        self.workspace_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.central_widget_layout.addWidget(self.workspace_splitter, stretch=1)

        self.bottom_bar = PyBottomBar()
        self.bottom_bar.setFixedHeight(CONTROL_SIZES["bottom_bar"])
        status_messages.set_status_handler(self.bottom_bar.show_message)
        flush_font_diagnostics()
        self.central_widget_layout.addWidget(self.bottom_bar, stretch=0)
        self.setCentralWidget(self.central_widget)

        self._restore_workspace_layout()
        self.workspace_splitter.splitterMoved.connect(self._workspace_splitter_moved)
        self.explorer_control_splitter.splitterMoved.connect(
            self._explorer_splitter_moved
        )
        self.left_column.explorerModeRequested.connect(
            self._explorer_mode_requested
        )

    @classmethod
    def _valid_splitter_sizes(cls, value):
        if isinstance(value, str):
            value = value.strip().strip("[]()")
            value = [part.strip() for part in value.split(",") if part.strip()]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        try:
            sizes = [int(item) for item in value]
        except (TypeError, ValueError, OverflowError):
            return None
        if any(size <= 0 or size > cls.MAX_PERSISTED_SPLITTER_SIZE for size in sizes):
            return None
        total = sum(sizes)
        if min(sizes) / total < cls.MIN_PERSISTED_SPLITTER_SHARE:
            return None
        return sizes

    @staticmethod
    def _setting_bool(value, default=True):
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default

    def _restore_workspace_layout(self):
        outer_sizes = list(self.DEFAULT_OUTER_SPLITTER_SIZES)
        explorer_sizes = list(self.DEFAULT_EXPLORER_SPLITTER_SIZES)
        explorer_mode = ExplorerMode.TABLE
        explorer_visible = True

        if self.settings is not None:
            self.settings.beginGroup(self.WORKSPACE_SETTINGS_GROUP)
            try:
                try:
                    version = int(self.settings.value("version", 0))
                except (TypeError, ValueError, OverflowError):
                    version = 0
                if version in {1, self.WORKSPACE_SETTINGS_VERSION}:
                    saved_outer = self._valid_splitter_sizes(
                        self.settings.value("outerSplitterSizes")
                    )
                    saved_explorer = self._valid_splitter_sizes(
                        self.settings.value("innerSplitterSizes")
                    )
                    if (
                        saved_outer is not None
                        and saved_explorer is not None
                    ):
                        outer_sizes = saved_outer
                        explorer_sizes = saved_explorer
                        if version == 1:
                            explorer_mode = ExplorerMode.TABLE
                            explorer_visible = self._setting_bool(
                                self.settings.value(
                                    "tableVisible",
                                    True,
                                ),
                                True,
                            )
                        else:
                            try:
                                explorer_mode = ExplorerMode(
                                    self.settings.value(
                                        "explorerMode",
                                        ExplorerMode.TABLE.value,
                                    )
                                )
                            except (TypeError, ValueError):
                                explorer_mode = ExplorerMode.TABLE
                            explorer_visible = self._setting_bool(
                                self.settings.value(
                                    "explorerVisible",
                                    True,
                                ),
                                True,
                            )
                        self._workspace_layout_restored = True
            finally:
                self.settings.endGroup()

        self._last_visible_explorer_sizes = list(explorer_sizes)
        self._explorer_mode = explorer_mode
        self._explorer_visible = explorer_visible
        self.workspace_splitter.setSizes(outer_sizes)
        self.explorer_control_splitter.setSizes(explorer_sizes)
        self._apply_explorer_state(restore_sizes=False)

    def _apply_default_workspace_sizes(self):
        if self._workspace_layout_restored:
            return
        available = self.workspace_splitter.width() - self.workspace_splitter.handleWidth()
        if available <= 0:
            return
        preferred_left = min(
            self.MAX_DEFAULT_LEFT_WIDTH,
            max(
                self.MIN_DEFAULT_LEFT_WIDTH,
                round(available * self.DEFAULT_OUTER_SPLITTER_SIZES[0] / 100),
            ),
        )
        left_width = min(preferred_left, max(1, available - self.MIN_CANVAS_WIDTH))
        self.workspace_splitter.setSizes([left_width, max(1, available - left_width)])
        self.explorer_control_splitter.setSizes(
            self.DEFAULT_EXPLORER_SPLITTER_SIZES
        )

    def _remember_visible_explorer_sizes(self):
        if not self._explorer_visible:
            return
        sizes = self._valid_splitter_sizes(
            self.explorer_control_splitter.sizes()
        )
        if sizes is not None:
            self._last_visible_explorer_sizes = sizes

    def _workspace_splitter_moved(self, _position, _index):
        # Persist once on close so dragging remains free of synchronous writes.
        return None

    def _explorer_splitter_moved(self, _position, _index):
        self._remember_visible_explorer_sizes()

    def _explorer_mode_requested(self, mode_value: str) -> None:
        mode = ExplorerMode(mode_value)
        if self._explorer_visible and mode is self._explorer_mode:
            self._remember_visible_explorer_sizes()
            self._explorer_visible = False
        else:
            self._explorer_mode = mode
            self._explorer_visible = True
        self._apply_explorer_state(restore_sizes=True)

    def _apply_explorer_state(self, *, restore_sizes: bool) -> None:
        self.left_explorer.set_mode(self._explorer_mode)
        self.left_explorer.setVisible(self._explorer_visible)
        self.left_column.set_explorer_state(
            self._explorer_mode.value,
            self._explorer_visible,
        )
        if self._explorer_visible and restore_sizes:
            QTimer.singleShot(
                0,
                lambda: self.explorer_control_splitter.setSizes(
                    self._last_visible_explorer_sizes
                ),
            )

    def _save_workspace_layout(self):
        if self.settings is None:
            return
        outer_sizes = self._valid_splitter_sizes(self.workspace_splitter.sizes())
        if outer_sizes is None:
            outer_sizes = list(self.DEFAULT_OUTER_SPLITTER_SIZES)

        self._remember_visible_explorer_sizes()
        explorer_sizes = self._valid_splitter_sizes(
            self._last_visible_explorer_sizes
        )
        if explorer_sizes is None:
            explorer_sizes = list(self.DEFAULT_EXPLORER_SPLITTER_SIZES)

        self.settings.beginGroup(self.WORKSPACE_SETTINGS_GROUP)
        try:
            self.settings.setValue("version", self.WORKSPACE_SETTINGS_VERSION)
            self.settings.setValue("outerSplitterSizes", outer_sizes)
            self.settings.setValue(
                "innerSplitterSizes",
                explorer_sizes,
            )
            self.settings.setValue(
                "explorerMode",
                self._explorer_mode.value,
            )
            self.settings.setValue(
                "explorerVisible",
                self._explorer_visible,
            )
        finally:
            self.settings.endGroup()
        self.settings.sync()

    def reset_workspace_layout(self):
        """Clear persisted workspace state and restore the versioned defaults."""
        if self.settings is not None:
            self.settings.beginGroup(self.WORKSPACE_SETTINGS_GROUP)
            try:
                self.settings.remove("")
            finally:
                self.settings.endGroup()
            self.settings.sync()

        self._workspace_layout_restored = False
        self._last_visible_explorer_sizes = list(
            self.DEFAULT_EXPLORER_SPLITTER_SIZES
        )
        self._explorer_mode = ExplorerMode.TABLE
        self._explorer_visible = True
        self._apply_explorer_state(restore_sizes=False)
        self.explorer_control_splitter.setSizes(
            self.DEFAULT_EXPLORER_SPLITTER_SIZES
        )
        self._apply_default_workspace_sizes()

    def showEvent(self, event):
        """Restore persisted workspace geometry the first time the window opens."""

        super().showEvent(event)
        QTimer.singleShot(0, self._apply_default_workspace_sizes)

    @staticmethod
    def _local_drop_paths(event) -> list[Path]:
        mime_data = event.mimeData()
        if mime_data is None or not mime_data.hasUrls():
            return []
        return [
            Path(url.toLocalFile())
            for url in mime_data.urls()
            if url.isLocalFile() and url.toLocalFile()
        ]

    def dragEnterEvent(self, event):
        """Accept supported workbook and text files dragged onto the window."""

        paths = self._local_drop_paths(event)
        if len(paths) == 1 and paths[0].is_file():
            event.acceptProposedAction()
            return
        event.ignore()
        if paths:
            status_messages.show_warning(
                "Drop one Excel workbook or text data file at a time."
            )

    def import_excel_file(self, file_name: str, show_preview: bool = True):
        """Import an Excel workbook into the table workspace."""

        subtable = import_excel_into_workspace(
            file_name,
            self.table,
            figure_window=self.figure_window,
            parent=self,
            show_preview=show_preview,
        )
        if subtable is not None:
            status_messages.show_success(f"Excel imported: {Path(file_name).name}")
        return subtable

    def import_text_file(self, file_name: str, show_preview: bool = True):
        """Import a delimited text file into the table workspace."""

        subtable = import_text_into_workspace(
            file_name,
            self.table,
            figure_window=self.figure_window,
            parent=self,
            show_preview=show_preview,
        )
        if subtable is not None:
            status_messages.show_success(f"Text data imported: {Path(file_name).name}")
        return subtable

    def dropEvent(self, event):
        """Import the first supported local file from a Qt drop event."""

        paths = self._local_drop_paths(event)
        if len(paths) != 1 or not paths[0].is_file():
            event.ignore()
            status_messages.show_warning(
                "Drop one Excel workbook or text data file at a time."
            )
            return
        event.acceptProposedAction()
        try:
            if is_supported_excel_workbook(paths[0]):
                self.import_excel_file(str(paths[0]))
            else:
                self.import_text_file(str(paths[0]))
        except Exception as exc:
            status_messages.show_error(str(exc))
            QMessageBox.warning(self, "Import Data", str(exc))

    def _project_close_choice(self, canvas):
        """Ask how to handle one dirty project."""

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Unsaved Project")
        dialog.setText(
            f'Save changes to "{canvas.project_name}" before closing?'
        )
        dialog.setInformativeText(
            "Unsaved changes will be lost if you choose Discard."
        )
        dialog.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )
        dialog.setDefaultButton(QMessageBox.Save)
        choice = dialog.exec()
        dialog.deleteLater()
        return choice

    def _prepare_canvas_close(self, canvas) -> str | None:
        """Return the accepted close mode, saving first when requested."""

        if not self.figure_window.is_canvas_dirty(canvas):
            return "clean"
        choice = self._project_close_choice(canvas)
        if choice == QMessageBox.Cancel:
            return None
        if choice == QMessageBox.Save:
            saved = self.title_bar.menu_bar.save_canvas(
                canvas,
                announce=False,
            )
            return "saved" if saved else None
        if choice == QMessageBox.Discard:
            return "discarded"
        return None

    def close_project_from_tab(self, index: int) -> bool:
        """Close the exact tab requested by its context menu."""

        if index < 0 or index >= self.figure_window.tabwindow.count():
            return False
        canvas = self.figure_window.tabwindow.widget(index)
        mode = self._prepare_canvas_close(canvas)
        if mode is None:
            return False
        project_name = canvas.project_name
        if not self.figure_window.close_project_at(index):
            status_messages.show_error(
                f"Could not close project: {project_name}"
            )
            return False
        if mode == "saved":
            status_messages.show_success(
                f"Project saved and closed: {project_name}"
            )
        elif mode == "discarded":
            status_messages.show_success(
                f"Project closed without saving: {project_name}"
            )
        else:
            status_messages.show_success(f"Project closed: {project_name}")
        return True

    def close_without_prompt(self) -> bool:
        """Close programmatically without unsaved-project dialogs."""

        self._skip_close_confirmation = True
        return self.close()

    def closeEvent(self, event):
        """Persist layout state and release global callbacks before closing."""

        should_confirm = (
            self.isVisible()
            and not getattr(self, "_skip_close_confirmation", False)
        )
        if should_confirm:
            for canvas in self.figure_window.canvases():
                if self._prepare_canvas_close(canvas) is None:
                    event.ignore()
                    return
        self._save_workspace_layout()
        if hasattr(self, "bottom_bar"):
            status_messages.clear_status_handler(self.bottom_bar.show_message)
            self.bottom_bar.cleanup()
        if hasattr(self.figure_window, "clear_figures"):
            self.figure_window.clear_figures()
        if hasattr(self.table, "clear_tables"):
            self.table.clear_tables()
        super().closeEvent(event)


if __name__ == "__main__":
    configure_windows_taskbar_identity()
    app = QApplication(sys.argv)
    font_diagnostic_bridge = install_font_diagnostic_bridge()
    configure_application_icon(app)
    configure_application_font(app)
    app.setStyleSheet(
        load_qss_resource("mygui/widgets/mainwindow_init/app_style.qss")
    )
    QCoreApplication.setOrganizationName("MyGUI")
    QCoreApplication.setApplicationName("MyGUI")
    window = MainWindow(settings=QSettings())
    window.showMaximized()
    sys.exit(app.exec())
