from Qt_core import *

from code.widgets import qss_func
from code.widgets.title_bar.py_title_button import ChangeButton, SelectMenuButton, StaticSelectButton
from code.widgets.title_bar.py_title_menu import (MenuBar, SelectorMenuBar, ControlBar,
                                                  SelectorStyleMenuBar, SelectorLayoutMenuBar, SelectorChartMenuBar,
                                                  SelectorElementMenuBar)
from code.widgets.table.py_table import PyTable
from code.widgets.figure_canvas.py_figure_window import PyFigureWindow

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTitleBar(QFrame):
    def __init__(self, parent=None, figure_window=None, fig_control_window=None, table: PyTable = None):
        super().__init__()
        self.parent = parent

        self.move = False
        self.start_pos = None

        # 样式设置
        self.setObjectName("title_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        # 设置布局
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.sublayout = QHBoxLayout()
        self.sublayout.setSpacing(0)
        self.stacklayout_top = QStackedLayout()
        self.stacklayout_bottom = QStackedLayout()

        # 下方堆叠布局选择按钮
        self.figure_window = figure_window

        self.selector_style_bar = SelectorStyleMenuBar(figure_window=self.figure_window,
                                                       fig_control_window=fig_control_window)
        self.selector_layout_bar = SelectorLayoutMenuBar(figure_window=self.figure_window,
                                                         fig_control_window=fig_control_window)
        self.selector_chart_bar = SelectorChartMenuBar(figure_window=self.figure_window)
        self.selector_element_bar = SelectorElementMenuBar(figure_window=self.figure_window)

        self.stacklayout_bottom.addWidget(self.selector_style_bar)
        self.stacklayout_bottom.addWidget(self.selector_layout_bar)
        self.stacklayout_bottom.addWidget(self.selector_chart_bar)
        self.stacklayout_bottom.addWidget(self.selector_element_bar)

        # 上方堆叠布局添加菜单栏
        self.stacklayout_top.addWidget(SelectorMenuBar(self.stacklayout_bottom))
        self.stacklayout_top.addWidget(MenuBar(table, self.figure_window))

        # 添加布局元素
        # 选择更改按钮
        self.change_button = ChangeButton('change_button')
        self.change_button.toggled.connect(self.the_button_was_toggled)
        self.sublayout.addWidget(self.change_button)

        # 添加堆叠布局
        self.sublayout.addLayout(self.stacklayout_top)

        # 添加弹性空间
        sub_spacer = QSpacerItem(0, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.sublayout.addItem(sub_spacer)

        # 添加最小化按钮
        minmize_button = QPushButton(QIcon("pictures/icons/minimize.svg"), "")
        minmize_button.setObjectName("minimize_button")
        minmize_button.clicked.connect(self.parent.showMinimized)
        self.sublayout.addWidget(minmize_button)

        # 添加最大化按钮

        # 添加关闭按钮
        button_close = QPushButton(QIcon("pictures/icons/close.svg"), "")
        button_close.setObjectName("close_button")
        button_close.clicked.connect(self.parent.close)
        self.sublayout.addWidget(button_close)

        # 添加上方布局
        self.layout.addLayout(self.sublayout)

        # 下方选择栏
        self.layout.addLayout(self.stacklayout_bottom)

        # 设置标题栏整体布局
        self.setLayout(self.layout)

    def the_button_was_toggled(self, checked):
        if checked:
            self.stacklayout_top.setCurrentIndex(1)
        else:
            self.stacklayout_top.setCurrentIndex(0)

    # 鼠标按下事件
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.move = True
            self.start_pos = event.globalPos()

    # 鼠标移动事件
    def mouseMoveEvent(self, event):
        if self.move:
            delta = event.globalPos() - self.start_pos
            self.parent.move(self.parent.pos() + delta)
            self.start_pos = event.globalPos()

    # 鼠标释放事件
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.move = False
