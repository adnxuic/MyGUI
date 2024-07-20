import sys
import os

from code.widgets.mainwindow_init import mainwindow_qss
from code.widgets.title_bar.py_title_bar import PyTitleBar
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.table.py_table import PyTable
from code.widgets.fig_control_window.py_fig_control_window import PyFigControlWindow
from code.widgets.right_column.py_right_column import PyRightColumn
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

        # self.setStyleSheet(mainwindow_qss)

        # 整个窗口布局
        self.central_widget = QWidget()
        self.central_widget.setMouseTracking(True)
        self.central_widget_layout = QHBoxLayout(self.central_widget)
        self.central_widget_layout.setSpacing(0)
        self.central_widget_layout.setContentsMargins(0, 0, 0, 0)

        # 左侧布局：非画布区域
        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(0)

        # 自定义窗口标题栏:左上部分
        self.title_bar = PyTitleBar(self)
        self.left_layout.addWidget(self.title_bar)

        # 左中部分
        self.table = PyTable()
        self.fig_control_window = PyFigControlWindow()
        self.left_column = PyLeftColumn(self.table, self.fig_control_window)

        # 拖动鼠标改变窗口大小相关
        self.table_fig_dragging = False

        self.table_fig_timer = QTimer(self)  # 创建计时器
        self.table_fig_timer.setInterval(1)  # 设置更新间隔为10毫秒
        self.table_fig_timer.timeout.connect(self.updatePositions)  # 连接计时器超时信号到更新函数

        # 右边栏
        self.right_column = PyRightColumn(self.fig_control_window.layout)

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
        # 添加弹性空间
        self.central_widget_layout.addStretch(0)
        self.central_widget_layout.addLayout(self.left_layout)


        self.setCentralWidget(self.central_widget)

        # 右侧布局：画布区域
        self.dock_font = QDockWidget("字体", self)  # 创建停靠控件
        self.dock_font.setFixedWidth(650)
        self.dock_font.setFixedHeight(400)
        # 设置背景颜色
        self.dock_font.setStyleSheet("background-color: #f0f0f0;")
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_font)  # 主窗口中添加停靠控件
        self.dock_font.setFeatures(QDockWidget.NoDockWidgetFeatures)  # 设置停靠控件的特征
        self.dock_font.setFeatures(QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable)

        fw = QWidget()  # 创建悬停控件上的控件
        self.dock_font.setWidget(fw)  # 设置悬停控件上的控件
        fv = QVBoxLayout(fw)  # 在控件上添加布局
        fv.setContentsMargins(0, 0, 0, 0)  # 设置布局的上、右、下、左边距都为0
        fv.setSpacing(0)  # 设置布局中控件间的间隔为0

        self.fontComboBox = QFontComboBox()
        self.sizeComboBox = QComboBox()  # 创建下拉框
        for i in range(5, 50):
            self.sizeComboBox.addItem(str(i))
        fv.addWidget(self.fontComboBox)  # 布局中添加控件
        fv.addWidget(self.sizeComboBox)  # 布局中添加控件


    def mousePressEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self.is_in_draggable_area(event.position().toPoint().x()):
                self.table_fig_dragging = True
                self.table_fig_drag_position = event.position().toPoint().x()

    def mouseMoveEvent(self, event):
        x_pos = event.position().toPoint().x()
        if self.is_in_draggable_area(x_pos):
            self.central_widget.setCursor(Qt.SizeHorCursor)  # 改变光标为水平拉伸光标
        else:
            self.central_widget.unsetCursor()  # 改变光标为默认光标

        if self.table_fig_dragging:
            self.table_fig_drag_position = x_pos
            if not self.table_fig_timer.isActive():
                self.table_fig_timer.start()


    def mouseReleaseEvent(self, event):
        self.table_fig_dragging = False
        self.table_fig_timer.stop()
        self.updatePositions()
        self.unsetCursor()  # 还原到默认光标


    def updatePositions(self):
        if self.table_fig_dragging:
            #
            x_table = self.table.x()
            sum_widht = self.table.width() + self.fig_control_window.width()
            x_now = self.table_fig_drag_position

            # 设置新宽度
            if 30 < x_now - x_table and 30 < sum_widht - self.table.width():
                    new_table_width = x_now - x_table
                    new_fig_control_window_width = sum_widht - new_table_width
                    self.table.setFixedWidth(new_table_width)
                    self.fig_control_window.setFixedWidth(new_fig_control_window_width)
            elif 30 < x_now - x_table and x_now <= x_table + self.table.width() and  sum_widht - self.table.width() <= 30:
                new_table_width = x_now - x_table
                new_fig_control_window_width = sum_widht - new_table_width
                self.table.setFixedWidth(new_table_width)
                self.fig_control_window.setFixedWidth(new_fig_control_window_width)

            self.update()  # 请求重绘窗口

    def is_in_draggable_area(self, x):
        # 扩大可拖动边界的宽度
        boundary_width = 5  # 可根据需要调整
        left_boundary = self.table.geometry().right() - boundary_width
        right_boundary = self.fig_control_window.geometry().left() + boundary_width
        return left_boundary <= x <= right_boundary


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
