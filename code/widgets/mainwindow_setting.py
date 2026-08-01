"""Apply persisted geometry and layout settings to the main window."""

from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.table.py_table import PyTable
from code.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from code.widgets.right_column.py_right_column import PyRightColumn
from code.database import TableRepository
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar
from code import status_messages

from Qt_core import *

class MainWindow_Setting(object):
    """Apply main window settings to the application window."""

    def setup_ui(self, parent):

        """Set up ui."""

        if not parent.objectName():
            parent.setObjectName("MainWindow")

        parent.setStyleSheet(mainwindow_qss)

        self.parent = parent

        # 整个窗口布局
        self.central_widget = QFrame()
        self.central_widget_layout = QHBoxLayout(self.central_widget)

        # 左侧布局：非画布区域
        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(0)

        # 自定义窗口标题栏:左上部分
        self.title_bar = PyTitleBar(parent)
        self.left_layout.addWidget(self.title_bar)

        # 左中部分
        self.repository = TableRepository(parent)
        self.table = PyTable(self.repository)
        self.table.setMouseTracking(True)
        self.fig_control_window = PyFigControlWindow()
        self.fig_control_window.setMouseTracking(True)
        self.left_column = PyLeftColumn()

        # 右边栏
        self.right_column = PyRightColumn(parent)

        self.left_middle_layout = QHBoxLayout()
        self.left_middle_layout.setSpacing(0)
        self.left_middle_layout.addWidget(self.left_column)
        self.left_middle_layout.addWidget(self.table)
        self.left_middle_layout.addWidget(self.fig_control_window)
        self.left_middle_layout.addWidget(self.right_column)

        self.left_layout.addLayout(self.left_middle_layout)


        # 左下状态栏
        self.bottom_bar = PyBottomBar()
        status_messages.set_status_handler(self.bottom_bar.show_message)
        self.left_layout.addWidget(self.bottom_bar)

        # 添加左侧窗口
        self.central_widget_layout.addLayout(self.left_layout)


        # 右侧布局：画布区域


        parent.setCentralWidget(self.central_widget)


    def mouseMoveEvent(self, event):
        """Handle pointer movement for the widget."""

        x_pos = event.position().toPoint().x()
        if self.is_in_draggable_area(x_pos):
            self.table.setCursor(Qt.SizeHorCursor)  # Change cursor to horizontal resize
            print('Change cursor to horizontal resize')
        else:
            self.table.unsetCursor()  # Reset cursor
            print('Reset cursor')


    def is_in_draggable_area(self, x):
        # 扩大可拖动边界的宽度
        """Return whether in draggable area."""

        boundary_width = 50  # 可根据需要调整
        left_boundary = self.table.geometry().right() - boundary_width
        right_boundary = self.fig_control_window.geometry().left() + boundary_width
        return left_boundary <= x <= right_boundary




