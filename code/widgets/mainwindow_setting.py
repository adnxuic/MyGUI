import sys

from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.left_window import PyLeftWindow

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


        # 自定义窗口标题栏:左上部分
        self.title_bar = PyTitleBar()
        self.left_layout.addWidget(self.title_bar)

        # 左中部分


        # 左下状态栏


        # try
        self.label = QLabel("This is a label")
        self.left_layout.addWidget(self.label)


        # 添加左侧窗口
        self.central_widget_layout.addWidget(self.left_window)


        # 右侧布局：画布区域




        parent.setCentralWidget(self.central_widget)






