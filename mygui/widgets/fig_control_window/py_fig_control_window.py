"""Host the component inspector beside the active figure."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QStackedLayout

from mygui.resources import load_qss_resource
from mygui.widgets.fig_control_window.figure_inspector import (
    FigureInspectorHost,
)
from mygui.widgets.fig_control_window.py_matlab_window import PyMatlabWindow
from mygui.widgets.fig_control_window.py_tex_window import PyTexWindow


class PyFigControlWindow(QFrame):
    """Provide the py fig control window Qt widget."""

    def __init__(self):
        super().__init__()
        self.setObjectName("fig_control_window")
        self.setStyleSheet(
            load_qss_resource(
                "mygui/widgets/fig_control_window/style.qss"
            )
        )
        self.setMouseTracking(True)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.matlab_window = PyMatlabWindow()
        self.figure_inspector_host = FigureInspectorHost()
        self.tex_window = PyTexWindow()

        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.scroll_areas = []
        for page in (
            self.figure_inspector_host,
            self.tex_window,
            self.matlab_window,
        ):
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
