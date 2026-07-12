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
from code.widgets.title_bar.py_title_bar import PyTitleBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setup_ui()
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.hide_grips = True
        self.showMaximized()

    def setup_ui(self):
        self.setObjectName("MainWindow")
        self.setStyleSheet(mainwindow_qss)

        self.central_widget = QWidget()
        self.central_widget_layout = QHBoxLayout(self.central_widget)
        self.central_widget_layout.setSpacing(0)
        self.central_widget_layout.setContentsMargins(0, 0, 0, 0)

        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(0)

        self.repository = TableRepository(self)
        self.table = PyTable(self.repository)
        self.fig_control_window = PyFigControlWindow()
        self.figure_window = PyFigureWindow(
            fig_modify_window=self.fig_control_window.figmod_window,
            repository=self.repository,
        )
        # Keep the canvas usable on narrower screens.  Without an explicit
        # minimum the empty QTabWidget has a very small size hint, so the
        # outer layout gives nearly all available width to the table/control
        # area during the first maximized layout pass.
        self.figure_window.setMinimumWidth(400)
        self.figure_window.set_table(self.table)

        self.title_bar = PyTitleBar(self, self.figure_window, self.fig_control_window, self.table)
        self.left_layout.addWidget(self.title_bar)

        self.left_column = PyLeftColumn(self.table, self.fig_control_window)
        self.right_column = PyRightColumn(self.fig_control_window.layout)

        self.table_control_splitter = QSplitter(Qt.Horizontal)
        self.table_control_splitter.setChildrenCollapsible(False)
        self.table_control_splitter.addWidget(self.table)
        self.table_control_splitter.addWidget(self.fig_control_window)
        self.table_control_splitter.setStretchFactor(0, 0)
        self.table_control_splitter.setStretchFactor(1, 1)
        self.table_control_splitter.setSizes([420, 240])

        self.left_middle_layout = QHBoxLayout()
        self.left_middle_layout.setSpacing(0)
        self.left_middle_layout.addWidget(self.left_column)
        self.left_middle_layout.addWidget(self.table_control_splitter)
        self.left_middle_layout.addWidget(self.right_column)
        self.left_layout.addLayout(self.left_middle_layout)

        self.bottom_bar = PyBottomBar()
        status_messages.set_status_handler(self.bottom_bar.show_message)
        self.left_layout.addWidget(self.bottom_bar)

        # The left workspace keeps its preferred width (roughly
        # 420px table + 240px controls + side rails); remaining room belongs
        # to the canvas.  These stretch factors must be present before the
        # first showMaximized() layout pass.
        self.central_widget_layout.addLayout(self.left_layout, 0)
        self.central_widget_layout.addWidget(self.figure_window, 1)
        self.setCentralWidget(self.central_widget)

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
        if hasattr(self, "bottom_bar"):
            status_messages.clear_status_handler(self.bottom_bar.show_message)
        if hasattr(self.figure_window, "cancel_pending_draws"):
            self.figure_window.cancel_pending_draws()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
