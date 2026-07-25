import os

from Qt_core import *

from code.widgets import qss_func
from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWindow
from code.widgets.fig_control_window.py_matlab_window import PyMatlabWindow
from code.widgets.fig_control_window.py_tex_window import PyTexWindow


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyFigControlWindow(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("fig_control_window")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.setMouseTracking(True)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.matlab_window = PyMatlabWindow()
        self.figmod_window = PyFigModWindow()
        self.tex_window = PyTexWindow()

        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.scroll_areas = []
        for page in (self.figmod_window, self.tex_window, self.matlab_window):
            scroll_area = self._scroll_page(page)
            self.scroll_areas.append(scroll_area)
            self.layout.addWidget(scroll_area)
        self.layout.setCurrentIndex(0)

    @staticmethod
    def _scroll_page(page):
        scroll_area = QScrollArea()
        scroll_area.setObjectName("inspector_scroll_area")
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll_area.setWidget(page)
        return scroll_area
