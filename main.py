import sys
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")

from Qt_core import *

from code import status_messages
from code.database import TableRepository
from code.excel_io import import_excel_into_workspace, is_supported_excel_workbook
from code.text_io import import_text_into_workspace
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar
from code.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from code.widgets.figure_canvas.py_figure_window import PyFigureWindow
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.right_column.py_right_column import PyRightColumn
from code.widgets.table.py_table import PyTable
from code.widgets.theme import CONTROL_SIZES
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.common_widget.min_widget.color_library import ColorLibrary


class MainWindow(QMainWindow):
    WORKSPACE_SETTINGS_GROUP = "workspaceLayout"
    WORKSPACE_SETTINGS_VERSION = 1
    DEFAULT_OUTER_SPLITTER_SIZES = (45, 55)
    DEFAULT_INNER_SPLITTER_SIZES = (420, 240)
    MIN_CANVAS_WIDTH = 400
    MIN_DEFAULT_LEFT_WIDTH = 572
    MAX_DEFAULT_LEFT_WIDTH = 760
    MAX_PERSISTED_SPLITTER_SIZE = 100_000
    MIN_PERSISTED_SPLITTER_SHARE = 0.01

    def __init__(self, *, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings
        self._workspace_layout_restored = False
        self._last_visible_inner_sizes = list(self.DEFAULT_INNER_SPLITTER_SIZES)
        self.setWindowTitle("MyGUI")
        self.setup_ui()
        self.setAcceptDrops(True)

    def setup_ui(self):
        self.setObjectName("MainWindow")
        self.setStyleSheet(mainwindow_qss)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("central_widget")
        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.central_widget_layout = QVBoxLayout(self.central_widget)
        self.central_widget_layout.setSpacing(0)
        self.central_widget_layout.setContentsMargins(0, 0, 0, 0)
        # Keep this historical attribute as a top-level-layout alias.
        self.left_layout = self.central_widget_layout

        self.repository = TableRepository(self)
        self.color_library = ColorLibrary(self.settings, self)
        self.table = PyTable(self.repository)
        self.table.setMinimumWidth(220)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fig_control_window = PyFigControlWindow()
        self.fig_control_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.figure_window = PyFigureWindow(
            figure_inspector_host=(
                self.fig_control_window.figure_inspector_host
            ),
            repository=self.repository,
            color_library=self.color_library,
        )
        self.figure_window.setMinimumWidth(self.MIN_CANVAS_WIDTH)
        self.figure_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.figure_window.set_table(self.table)

        self.title_bar = PyTitleBar(self, self.figure_window, self.fig_control_window, self.table)
        self.figure_window.requestStyleSelector.connect(self.title_bar.show_style_selector)
        self.central_widget_layout.addWidget(self.title_bar, stretch=0)

        self.left_column = PyLeftColumn(self.table, self.fig_control_window)
        self.left_column.set_reset_layout_callback(self.reset_workspace_layout)
        self.right_column = PyRightColumn(self.fig_control_window.layout)
        self.left_column.setFixedWidth(CONTROL_SIZES["activity_rail"])
        self.right_column.setFixedWidth(CONTROL_SIZES["activity_rail"])

        self.table_control_splitter = QSplitter(Qt.Horizontal)
        self.table_control_splitter.setObjectName("table_control_splitter")
        self.table_control_splitter.setChildrenCollapsible(False)
        self.table_control_splitter.addWidget(self.table)
        self.table_control_splitter.addWidget(self.fig_control_window)
        self.table_control_splitter.setStretchFactor(0, 0)
        self.table_control_splitter.setStretchFactor(1, 1)
        self.table_control_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.left_workspace = QWidget()
        self.left_workspace.setObjectName("left_workspace")
        self.left_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.left_middle_layout = QHBoxLayout(self.left_workspace)
        self.left_middle_layout.setSpacing(0)
        self.left_middle_layout.setContentsMargins(0, 0, 0, 0)
        self.left_middle_layout.addWidget(self.left_column)
        self.left_middle_layout.addWidget(self.table_control_splitter)
        self.left_middle_layout.addWidget(self.right_column)

        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.setObjectName("workspace_splitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self.left_workspace)
        self.workspace_splitter.addWidget(self.figure_window)
        self.workspace_splitter.setStretchFactor(0, 45)
        self.workspace_splitter.setStretchFactor(1, 55)
        self.workspace_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.outer_splitter = self.workspace_splitter
        self.central_widget_layout.addWidget(self.workspace_splitter, stretch=1)

        self.bottom_bar = PyBottomBar()
        self.bottom_bar.setFixedHeight(CONTROL_SIZES["bottom_bar"])
        status_messages.set_status_handler(self.bottom_bar.show_message)
        self.central_widget_layout.addWidget(self.bottom_bar, stretch=0)
        self.setCentralWidget(self.central_widget)

        self._restore_workspace_layout()
        self.workspace_splitter.splitterMoved.connect(self._workspace_splitter_moved)
        self.table_control_splitter.splitterMoved.connect(self._table_splitter_moved)
        self.left_column.table_button.pressed.connect(self._remember_visible_inner_sizes)
        self.left_column.table_button.toggled.connect(self._table_visibility_changed)

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
        inner_sizes = list(self.DEFAULT_INNER_SPLITTER_SIZES)
        table_visible = True

        if self.settings is not None:
            self.settings.beginGroup(self.WORKSPACE_SETTINGS_GROUP)
            try:
                try:
                    version = int(self.settings.value("version", 0))
                except (TypeError, ValueError, OverflowError):
                    version = 0
                if version == self.WORKSPACE_SETTINGS_VERSION:
                    saved_outer = self._valid_splitter_sizes(
                        self.settings.value("outerSplitterSizes")
                    )
                    saved_inner = self._valid_splitter_sizes(
                        self.settings.value("innerSplitterSizes")
                    )
                    if saved_outer is not None and saved_inner is not None:
                        outer_sizes = saved_outer
                        inner_sizes = saved_inner
                        table_visible = self._setting_bool(
                            self.settings.value("tableVisible", True), True
                        )
                        self._workspace_layout_restored = True
            finally:
                self.settings.endGroup()

        self._last_visible_inner_sizes = list(inner_sizes)
        self.workspace_splitter.setSizes(outer_sizes)
        self.table_control_splitter.setSizes(inner_sizes)
        self.left_column.table_button.setChecked(table_visible)

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
        self.table_control_splitter.setSizes(self.DEFAULT_INNER_SPLITTER_SIZES)

    def _remember_visible_inner_sizes(self):
        if not self.left_column.table_button.isChecked():
            return
        sizes = self._valid_splitter_sizes(self.table_control_splitter.sizes())
        if sizes is not None:
            self._last_visible_inner_sizes = sizes

    def _workspace_splitter_moved(self, _position, _index):
        # Persist once on close so dragging remains free of synchronous writes.
        return None

    def _table_splitter_moved(self, _position, _index):
        self._remember_visible_inner_sizes()

    def _table_visibility_changed(self, visible):
        if visible:
            QTimer.singleShot(
                0,
                lambda: self.table_control_splitter.setSizes(
                    self._last_visible_inner_sizes
                ),
            )
            return
        geometry_sizes = [self.table.width(), self.fig_control_window.width()]
        sizes = self._valid_splitter_sizes(geometry_sizes)
        if sizes is not None:
            self._last_visible_inner_sizes = sizes

    def _save_workspace_layout(self):
        if self.settings is None:
            return
        outer_sizes = self._valid_splitter_sizes(self.workspace_splitter.sizes())
        if outer_sizes is None:
            outer_sizes = list(self.DEFAULT_OUTER_SPLITTER_SIZES)

        if self.left_column.table_button.isChecked():
            inner_sizes = self._valid_splitter_sizes(self.table_control_splitter.sizes())
            if inner_sizes is not None:
                self._last_visible_inner_sizes = inner_sizes
        inner_sizes = self._valid_splitter_sizes(self._last_visible_inner_sizes)
        if inner_sizes is None:
            inner_sizes = list(self.DEFAULT_INNER_SPLITTER_SIZES)

        self.settings.beginGroup(self.WORKSPACE_SETTINGS_GROUP)
        try:
            self.settings.setValue("version", self.WORKSPACE_SETTINGS_VERSION)
            self.settings.setValue("outerSplitterSizes", outer_sizes)
            self.settings.setValue("innerSplitterSizes", inner_sizes)
            self.settings.setValue(
                "tableVisible", self.left_column.table_button.isChecked()
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
        self._last_visible_inner_sizes = list(self.DEFAULT_INNER_SPLITTER_SIZES)
        self.left_column.table_button.setChecked(True)
        self.table_control_splitter.setSizes(self.DEFAULT_INNER_SPLITTER_SIZES)
        self._apply_default_workspace_sizes()

    def showEvent(self, event):
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

    def closeEvent(self, event):
        self._save_workspace_layout()
        if hasattr(self, "bottom_bar"):
            status_messages.clear_status_handler(self.bottom_bar.show_message)
        if hasattr(self.figure_window, "cancel_pending_draws"):
            self.figure_window.cancel_pending_draws()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("MyGUI")
    QCoreApplication.setApplicationName("MyGUI")
    window = MainWindow(settings=QSettings())
    window.showMaximized()
    sys.exit(app.exec())
