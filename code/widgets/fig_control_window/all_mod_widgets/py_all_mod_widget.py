from Qt_core import *
from code.widgets import qss_func
from code.widgets.fig_control_window.all_mod_widgets.py_axes_mod_widgets import (
    PyBottomSpineModWidget, PyTopSpineModWidget, PyLeftSpineModWidget, PyRightSpineModWidget,
    PyAxeLegendModWidget
)
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyFitMatlabModWidget
from code.widgets.fig_control_window.py_matlab_window import PyMatlabWindow

from code.figuremodify.py_axes_modify import PyAxesModify

from typing import Optional
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


# 调整坐标系
class PyAxesModWindow(QFrame):
    """
    坐标系调整窗口
    一个坐标系对应一个
    """

    def __init__(self, axe, axe_modify: PyAxesModify):
        super().__init__()
        self.axe = axe
        self.axe_modify = axe_modify

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.toolbox = QToolBox()

        self.bottom_spine_mod_widget = PyBottomSpineModWidget(axe, axe_modify)
        self.top_spine_mod_widget = PyTopSpineModWidget()
        self.left_spine_mod_widget = PyLeftSpineModWidget(axe, axe_modify)
        self.right_spine_mod_widget = PyRightSpineModWidget()

        self.legend_mod_widget = PyAxeLegendModWidget(axe, axe_modify)

        self.toolbox.addItem(self.bottom_spine_mod_widget, "底脊")
        self.toolbox.addItem(self.top_spine_mod_widget, "顶脊")
        self.toolbox.addItem(self.left_spine_mod_widget, "左脊")
        self.toolbox.addItem(self.right_spine_mod_widget, "右脊")

        self.toolbox.addItem(self.legend_mod_widget, "图例")

        self.layout.addWidget(self.toolbox)
        self.setLayout(self.layout)

    def add_legend_mod_widget(self):
        pass


# 调整曲线
class PyChartModWindow(QFrame):
    """
    曲线调整窗口
    一个坐标系对应一个
    用来容纳不同类的曲线调整箱
    """

    def __init__(self, axe, matlab_widget):
        super().__init__()

        self.axe = axe
        self.matlab_widget = matlab_widget

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedWidget()

        self.layout.addWidget(self.stacklayout)
        self.setLayout(self.layout)

    def add_box(self, box_name: str, btn: QPushButton):
        widget = PyModBox(self.matlab_widget)
        self.boxs[box_name] = widget
        self.stacklayout.addWidget(widget)

        btn.clicked.connect(lambda: self.change_widget(widget))
        self.change_widget(widget)

    def change_widget(self, widget):
        self.stacklayout.setCurrentWidget(widget)


# 调整元素
class PyElementModWindow(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedLayout()

        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)

    def add_box(self, box_name: str, btn: QPushButton):
        widget = PyModBox()
        self.boxs[box_name] = widget
        self.stacklayout.addWidget(widget)

        btn.clicked.connect(lambda: self.change_widget(widget))
        self.change_widget(widget)

    def change_widget(self, widget):
        self.stacklayout.setCurrentWidget(widget)


class PyModBox(QToolBox):
    """
    调整箱
    用来容纳同类的多条调整窗口
    """

    def __init__(self, matlab_widget=None):
        super().__init__()
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        if matlab_widget is not None:
            self.matlab_widget: Optional[PyMatlabWindow] = matlab_widget

        self.item_num = 0

        # 标签改变时，如果是matlab窗口，调用change_matlab_widget
        self.currentChanged.connect(self.change_widget)

    def add_widget(self, widget, widget_name: str):
        self.addItem(widget, widget_name + str(self.item_num))
        self.item_num += 1

    def change_widget(self):
        widget = self.currentWidget()
        # 如果是matlab窗口，调用change_matlab_widget
        if isinstance(widget, PyFitMatlabModWidget):
            self.matlab_widget.set_connect_widget(widget)
        else:
            return
