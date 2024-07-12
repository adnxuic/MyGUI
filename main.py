import sys
import os

from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.table.py_table import PyTable
from code.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from code.widgets.right_column.py_right_column import PyRightColumn
from code.widgets.right_column.py_matlab_window import PyMatlabWindow
from code.widgets.right_column.py_tex_window import PyTexWindow
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar

from Qt_core import *


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 设置窗口为无边框
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setup_ui()

        self.setMouseTracking(True)

        self.hide_grips = True  # 隐藏窗口

        # 最大化窗口
        self.showMaximized()

    def setup_ui(self):
        if not self.objectName():
            self.setObjectName("MainWindow")

        self.setStyleSheet(mainwindow_qss)

        # 整个窗口布局
        self.central_widget = QWidget()
        self.central_widget.setMouseTracking(True)
        self.central_widget_layout = QHBoxLayout(self.central_widget)

        # 左侧布局：非画布区域
        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(0)

        # 自定义窗口标题栏:左上部分
        self.title_bar = PyTitleBar(self)
        self.left_layout.addWidget(self.title_bar)

        # 左中部分
        self.table = PyTable()
        self.table.setMouseTracking(True)
        self.fig_control_window = PyFigControlWindow()
        self.fig_control_window.setMouseTracking(True)
        self.left_column = PyLeftColumn(self.table, self.fig_control_window)

        # 拖动鼠标改变窗口大小相关
        self.table_fig_dragging = False

        self.table_fig_timer = QTimer(self)  # 创建计时器
        self.table_fig_timer.setInterval(1)  # 设置更新间隔为10毫秒
        self.table_fig_timer.timeout.connect(self.updatePositions)  # 连接计时器超时信号到更新函数

        # 右边栏
        self.right_column = PyRightColumn(self)

        self.left_middle_layout = QHBoxLayout()
        self.left_middle_layout.setSpacing(0)
        self.left_middle_layout.addWidget(self.left_column)
        self.left_middle_layout.addWidget(self.table)
        self.left_middle_layout.addWidget(self.fig_control_window)
        self.left_middle_layout.addWidget(self.right_column)

        self.left_layout.addLayout(self.left_middle_layout)

        # 左下状态栏
        self.bottom_bar = PyBottomBar()
        self.left_layout.addWidget(self.bottom_bar)

        # 添加左侧窗口
        self.central_widget_layout.addLayout(self.left_layout)

        # 右侧布局：画布区域

        self.setCentralWidget(self.central_widget)


    def mousePressEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self.is_in_draggable_area(event.position().toPoint().x()):
                self.table_fig_dragging = True
                self.drag_position = event.position().toPoint().x()
                print("dragging")

    def mouseMoveEvent(self, event):
        x_pos = event.position().toPoint().x()
        if self.is_in_draggable_area(x_pos):
            self.central_widget.setCursor(Qt.SizeHorCursor)  # Change cursor to horizontal resize
        else:
            self.central_widget.unsetCursor()  # Reset cursor

        if self.table_fig_dragging:
            self.drag_position = x_pos
            if not self.table_fig_timer.isActive():
                self.table_fig_timer.start()  # Start the table_fig_timer if not already started
                print("move")

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.table_fig_timer.stop()
        self.updatePositions()
        self.unsetCursor()  # 还原到默认光标
        print("dragging end")

    # def updatePositions(self):
    #     if self.table_fig_dragging:
    #         new_x = self.drag_position
    #         table_height = self.table.height()
    #         fig_control_window_height = self.fig_control_window.height()
    #         # 调整第一个组件的宽度
    #         new_width1 = new_x - 10
    #         if 10 <= new_width1 <= (self.width() - 20 - self.fig_control_window.width()):
    #             self.table.setFixedWidth(new_width1)
    #
    #         # 调整第二个组件的位置和宽度
    #         new_width2 = self.width() - new_x - 10
    #         if 10 <= new_width2 <= (self.width() - 20 - self.table.width()):
    #             self.fig_control_window.setFixedWidth(new_width2)
    #
    #         self.update()  # 请求重绘窗口

    def updatePositions(self):
        if self.table_fig_dragging:
            new_x = self.drag_position
            total_width = self.width() - 20  # 假设总宽度减去左右两侧的边距

            # 调整table的宽度
            new_width_table = new_x - 10  # new_x是分隔线的位置，减去左边距
            new_width_fig_control_window = total_width - new_width_table  # 确保两个组件的宽度之和不变

            # 设置新宽度，保持table的左边和fig_control_window的右边固定
            self.table.setFixedWidth(new_width_table)
            self.fig_control_window.setGeometry(self.width() - 10 - new_width_fig_control_window, 10,
                                                new_width_fig_control_window, self.fig_control_window.height())

            self.update()  # 请求重绘窗口

    def is_in_draggable_area(self, x):
        # 扩大可拖动边界的宽度
        boundary_width = 10  # 可根据需要调整
        left_boundary = self.table.geometry().right() - boundary_width
        right_boundary = self.fig_control_window.geometry().left() + boundary_width
        return left_boundary <= x <= right_boundary


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
