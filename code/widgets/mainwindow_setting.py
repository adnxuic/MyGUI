import sys

from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.left_window.py_left_window import PyLeftWindow
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.left_window.py_left_middle_window import PyLeftMiddleWindow
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.table.py_table import PyTable
from code.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from code.widgets.right_column.py_right_column import PyRightColumn
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar

from Qt_core import *

class MainWindow_Setting(object):
    def setup_ui(self, parent):

        if not parent.objectName():
            parent.setObjectName("MainWindow")

        parent.setStyleSheet(mainwindow_qss)

        # 整个窗口布局
        self.central_widget = QWidget()
        self.central_widget_layout = QHBoxLayout(self.central_widget)

        # 左侧布局：非画布区域
        self.left_window = PyLeftWindow()
        self.left_layout = QVBoxLayout(self.left_window)
        self.left_layout.setSpacing(0)

        # 自定义窗口标题栏:左上部分
        self.title_bar = PyTitleBar(parent)
        self.left_layout.addWidget(self.title_bar)

        # 左中部分
        self.left_middle_window = PyLeftMiddleWindow()
        self.left_middle_layout = QHBoxLayout(self.left_middle_window)
        self.left_middle_layout.setSpacing(0)

        self.left_middle_layout.addWidget(PyLeftColumn())
        self.left_middle_layout.addWidget(PyTable())
        self.left_middle_layout.addWidget(PyFigControlWindow())
        self.left_middle_layout.addWidget(PyRightColumn())

        self.left_layout.addWidget(self.left_middle_window)

        # 左下状态栏
        self.left_layout.addWidget(PyBottomBar())




        # 添加左侧窗口
        self.central_widget_layout.addWidget(self.left_window)


        # 右侧布局：画布区域




        parent.setCentralWidget(self.central_widget)






