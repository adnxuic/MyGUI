from Qt_core import *
from code.widgets import qss_func
from code.widgets.common_widget.py_empty_state import PyEmptyState
from code.widgets.fig_control_window.all_mod_widgets.py_axes_mod_widgets import (
    PyCommonModWidget, PyBottomSpineModWidget, PyTopSpineModWidget, PyLeftSpineModWidget, PyRightSpineModWidget,
    PyAxeLegendModWidget
)

from code.figuremodify.py_axes_modify import PyAxesModify

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


# Adjust axes
class PyAxesModWindow(QFrame):
    """
    Axes adjustment panel.
    One panel per axes.
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

        self.common_mod_widget = PyCommonModWidget(axe, axe_modify)
        self.bottom_spine_mod_widget = PyBottomSpineModWidget(axe, axe_modify)
        self.top_spine_mod_widget = PyTopSpineModWidget()
        self.left_spine_mod_widget = PyLeftSpineModWidget(axe, axe_modify)
        self.right_spine_mod_widget = PyRightSpineModWidget()

        self.legend_mod_widget = PyAxeLegendModWidget(axe, axe_modify)

        self.scroll_pages = []
        for widget, title in (
            (self.common_mod_widget, "通用"),
            (self.bottom_spine_mod_widget, "底脊"),
            (self.top_spine_mod_widget, "顶脊"),
            (self.left_spine_mod_widget, "左脊"),
            (self.right_spine_mod_widget, "右脊"),
            (self.legend_mod_widget, "图例"),
        ):
            scroll_page = self._scrollable_page(widget)
            self.scroll_pages.append(scroll_page)
            self.toolbox.addItem(scroll_page, title)

        self.layout.addWidget(self.toolbox)
        self.setLayout(self.layout)

    @staticmethod
    def _scrollable_page(widget):
        """Keep long inspector sections usable without resizing the shell."""
        scroll_page = QScrollArea()
        scroll_page.setObjectName("inspector_section_scroll_area")
        scroll_page.setFrameShape(QFrame.NoFrame)
        scroll_page.setWidgetResizable(True)
        scroll_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll_page.setWidget(widget)
        return scroll_page

    def add_legend_mod_widget(self):
        pass


# Adjust curves
class PyChartModWindow(QFrame):
    """
    Curve adjustment panel.
    One panel per axes.
    Holds curve-type adjustment toolboxes.
    """

    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedWidget()
        self.empty_state = PyEmptyState(
            "No chart selected",
            "Add or select a chart object to edit its parameters.",
        )
        self.stacklayout.addWidget(self.empty_state)

        self.layout.addWidget(self.stacklayout)
        self.setLayout(self.layout)

    def add_box(self, box_name: str, btn: QPushButton):
        widget = PyModBox()
        self.boxs[box_name] = widget
        self.stacklayout.addWidget(widget)

        btn.clicked.connect(lambda: self.change_widget(widget))
        self.change_widget(widget)

    def change_widget(self, widget):
        self.stacklayout.setCurrentWidget(widget)


# Adjust elements
class PyElementModWindow(QFrame):
    def __init__(self, axe):
        super().__init__()

        self.axe = axe

        self.boxs = {}

        self.layout = QVBoxLayout()
        self.stacklayout = QStackedLayout()
        self.empty_state = PyEmptyState(
            "No element selected",
            "Add or select a figure element to edit its parameters.",
        )
        self.stacklayout.addWidget(self.empty_state)

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
    Adjustment toolbox.
    Holds multiple adjustment panels of the same type.
    """

    def __init__(self):
        super().__init__()
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.item_num = 0
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    def add_widget(self, widget, widget_name: str):
        self.addItem(widget, widget_name + str(self.item_num))
        self.item_num += 1

    def contextMenuEvent(self, event):
        widget = self.currentWidget()
        if widget is None or not callable(getattr(widget, "delete_object", None)):
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_widget(self.currentIndex())

    def delete_widget(self, index: int | None = None):
        if index is None:
            index = self.currentIndex()
        if index is None or index < 0 or index >= self.count():
            return
        widget = self.widget(index)
        delete_object = getattr(widget, "delete_object", None)
        if not callable(delete_object):
            return
        delete_object()
        self.removeItem(index)
        widget.setParent(None)
        widget.deleteLater()
