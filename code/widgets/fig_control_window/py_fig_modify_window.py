from Qt_core import *
from typing import Optional

from code.widgets.qss_func import qss_loader
from code.widgets.common_widget.py_empty_state import PyEmptyState
from code.widgets.fig_control_window.all_mod_widgets.py_all_mod_widget import (
    PyAxesModWindow, PyChartModWindow, PyElementModWindow)
from code.figuremodify.py_axes_modify import PyAxesModify


import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyAllModWidget(QFrame):
    """
    所有元素的修改窗口
    一个坐标系对应一个
    """

    def __init__(self, axe, axe_modify: PyAxesModify):
        super().__init__()

        self.setObjectName('all_mod_widget')

        self.setMouseTracking(True)

        self.layout = QVBoxLayout()

        self.axe = axe

        self.btn_bars = []
        self.curve_btn_bar = QFrame()
        self.element_btn_bar = QFrame()
        self.btn_bars.append(self.curve_btn_bar)
        self.btn_bars.append(self.element_btn_bar)

        self.curve_btn_bar_layout = QHBoxLayout()
        self.element_btn_bar_layout = QHBoxLayout()

        self.axes_mod_window = PyAxesModWindow(axe, axe_modify)
        self.cahrt_mod_window = PyChartModWindow(axe)
        self.element_mod_window = PyElementModWindow(axe)

        self.stackwidget = QStackedWidget()

        self.stackwidget.addWidget(self.axes_mod_window)
        self.stackwidget.addWidget(self.cahrt_mod_window)
        self.stackwidget.addWidget(self.element_mod_window)

        self.curve_btn_bar.setLayout(self.curve_btn_bar_layout)
        self.element_btn_bar.setLayout(self.element_btn_bar_layout)

        self.layout.addWidget(self.stackwidget)
        self.layout.addWidget(self.curve_btn_bar)
        self.layout.addWidget(self.element_btn_bar)

        self.setLayout(self.layout)

    def change_stackwidget(self, index):
        self.stackwidget.setCurrentIndex(index)

    def updateLayout(self, active_index):
        # Clear current layout
        for i in reversed(range(self.layout.count())):
            self.layout.itemAt(i).widget().setParent(None)

        # Rebuild layout
        for i, btn_bar in enumerate(self.btn_bars):
            if i == active_index:
                self.layout.addWidget(self.stackwidget)

            self.layout.addWidget(btn_bar)

        if active_index == len(self.btn_bars):
            self.layout.addWidget(self.stackwidget)

    def add_chart_box(self, btn_name: str):
        """
        调用curve_mod_window的add_box方法
        添加一个新的图表修改窗口
        按钮名和工具箱名相同
        """
        btn = QPushButton(btn_name)

        btn.clicked.connect(lambda: self.change_stackwidget(1))
        self.cahrt_mod_window.add_box(btn_name, btn)
        btn.clicked.connect(lambda: self.updateLayout(1))

        self.curve_btn_bar_layout.addWidget(btn)

    def add_element_box(self, btn_name: str):
        """
        调用element_mod_window的add_box方法
        添加一个新的曲线元素修改窗口
        按钮名和工具箱名相同
        """
        btn = QPushButton(btn_name)

        btn.clicked.connect(lambda: self.change_stackwidget(2))
        self.element_mod_window.add_box(btn_name, btn)
        btn.clicked.connect(lambda: self.updateLayout(2))

        self.element_btn_bar_layout.addWidget(btn)




class PyFigureElementModWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()
        self.element_btn_bar = QFrame()
        self.element_btn_bar_layout = QHBoxLayout()
        self.element_mod_window = PyElementModWindow(None)

        self.element_btn_bar.setLayout(self.element_btn_bar_layout)
        self.layout.addWidget(self.element_btn_bar)
        self.layout.addWidget(self.element_mod_window)
        self.setLayout(self.layout)

    def add_element_box(self, btn_name: str):
        btn = QPushButton(btn_name)
        self.element_mod_window.add_box(btn_name, btn)
        self.element_btn_bar_layout.addWidget(btn)


class PyFigModWidget(QFrame):
    """
    画布修改窗口
    一个画布关联一个
    """

    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_Widget')

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.axes_btn_bar = QFrame()
        self.axes_btn_bar_layout = QHBoxLayout()

        self.stacklayout = QStackedLayout()

        self.axes_btn_bar.setLayout(self.axes_btn_bar_layout)

        self.layout.addWidget(self.axes_btn_bar)
        self.layout.addLayout(self.stacklayout)
        self.setLayout(self.layout)

        self.axes_count = 0
        self.no_axes_state = PyEmptyState(
            "No axes",
            "Choose a layout from the command bar before adding charts or axes elements.",
        )
        self.figure_element_mod_widget = PyFigureElementModWidget()
        self.stacklayout.addWidget(self.no_axes_state)
        self.stacklayout.addWidget(self.figure_element_mod_widget)

        figure_btn = QPushButton('figure')
        figure_btn.clicked.connect(lambda: self.stacklayout.setCurrentWidget(self.figure_element_mod_widget))
        self.axes_btn_bar_layout.addWidget(figure_btn)

    def add_all_mod_widget(self, axe, axe_modify: PyAxesModify):
        """
        添加坐标系中所有元素的修改窗口
        返回按钮以便切换窗口是改变画布的当前坐标系
        """
        all_mod_widget = PyAllModWidget(axe, axe_modify)
        self.stacklayout.addWidget(all_mod_widget)
        self.stacklayout.setCurrentIndex(self.stacklayout.count() - 1)

        self.axes_count += 1
        btn_name = 'axe' + str(self.axes_count)
        btn = QPushButton(btn_name)
        btn.clicked.connect(lambda: self.change_all_mod_widget(all_mod_widget))
        btn.clicked.connect(lambda: all_mod_widget.change_stackwidget(0))
        btn.clicked.connect(lambda: all_mod_widget.updateLayout(0))

        self.axes_btn_bar_layout.addWidget(btn)

        return btn

    def change_all_mod_widget(self, all_mod_widget):
        self.stacklayout.setCurrentWidget(all_mod_widget)

    def fine_all_mod_widget(self, axe) -> Optional[PyAllModWidget]:
        """
        通过坐标系找到对应的修改窗口
        """
        for i in range(self.stacklayout.count()):
            widget = self.stacklayout.widget(i)
            if isinstance(widget, PyAllModWidget) and widget.axe == axe:
                return widget
        return None


class PyFigModWindow(QFrame):
    """
    总画布修改窗口
    整个窗口的布局只有一个
    与matlab窗口和Tex窗口并列
    """

    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setObjectName('fig_modify_window')

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        # Stacked layout
        self.stacklayout = QStackedLayout()
        self.stacklayout.setSpacing(0)
        self.stacklayout.setContentsMargins(0, 0, 0, 0)

        self.empty_state = PyEmptyState(
            "No project",
            "Choose a style to create a project and open its inspector.",
        )
        self.stacklayout.addWidget(self.empty_state)

        self.setLayout(self.stacklayout)

    def add_figmod_widget(self):
        figmod_widget = PyFigModWidget()
        self.stacklayout.addWidget(figmod_widget)
        self.stacklayout.setCurrentIndex(self.stacklayout.count() - 1)

        return figmod_widget

    def clear_figmod_widgets(self):
        for index in range(self.stacklayout.count() - 1, -1, -1):
            widget = self.stacklayout.widget(index)
            if widget is self.empty_state:
                continue
            self.stacklayout.removeWidget(widget)
            widget.deleteLater()
        self.stacklayout.setCurrentWidget(self.empty_state)
