"""Host the component inspector beside the active figure."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QStackedLayout

from mygui.application_theme import bind_widget_qss
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
        bind_widget_qss(self, "mygui/widgets/fig_control_window/style.qss")
        self.setMouseTracking(True)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.matlab_window = PyMatlabWindow()
        self.figure_inspector_host = FigureInspectorHost()
        self.tex_window = PyTexWindow()

        self.layout = QStackedLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.figure_inspector_scroll_area = self._scroll_page(
            self.figure_inspector_host
        )
        self.scroll_areas = [
            self.figure_inspector_scroll_area,
            self._scroll_page(self.tex_window),
            self._scroll_page(self.matlab_window),
        ]
        for scroll_area in self.scroll_areas:
            self.layout.addWidget(scroll_area)
        self.figure_inspector_host.componentShown.connect(
            self.reset_figure_inspector_scroll
        )
        self.layout.setCurrentIndex(0)

    def reset_figure_inspector_scroll(self, *_args) -> None:
        """Return the shared Figure Inspector viewport to its top-left."""

        QTimer.singleShot(0, self._reset_figure_inspector_scroll_now)

    def _reset_figure_inspector_scroll_now(self) -> None:
        area = self.figure_inspector_scroll_area
        horizontal = area.horizontalScrollBar()
        vertical = area.verticalScrollBar()
        horizontal.setValue(horizontal.minimum())
        vertical.setValue(vertical.minimum())

    @staticmethod
    def _scroll_page(page):
        scroll_area = QScrollArea()
        scroll_area.setObjectName("inspector_scroll_area")
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll_area.setWidget(page)
        return scroll_area
