"""Compose the custom application title bar."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QStackedLayout, QVBoxLayout

from mygui.widgets import qss_func
from mygui.widgets.table.py_table import PyTable
from mygui.widgets.title_bar.py_title_button import ChangeButton
from mygui.widgets.title_bar.py_title_menu import (
    MenuBar,
    SelectorChartMenuBar,
    SelectorElementMenuBar,
    SelectorLayoutMenuBar,
    SelectorMenuBar,
    SelectorStyleMenuBar,
)


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTitleBar(QFrame):
    """Full-width application command bar beneath the native title bar."""

    def __init__(
        self,
        parent=None,
        figure_window=None,
        fig_control_window=None,
        table: PyTable | None = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.figure_window = figure_window
        self.setObjectName("title_bar")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.sublayout = QHBoxLayout()
        self.sublayout.setContentsMargins(0, 0, 0, 0)
        self.sublayout.setSpacing(0)
        self.stacklayout_top = QStackedLayout()
        self.stacklayout_bottom = QStackedLayout()
        self.stacklayout_top.setContentsMargins(0, 0, 0, 0)
        self.stacklayout_bottom.setContentsMargins(0, 0, 0, 0)

        self.selector_style_bar = SelectorStyleMenuBar(
            figure_window=figure_window,
            fig_control_window=fig_control_window,
        )
        self.selector_layout_bar = SelectorLayoutMenuBar(
            figure_window=figure_window,
            fig_control_window=fig_control_window,
        )
        self.selector_chart_bar = SelectorChartMenuBar(figure_window=figure_window)
        self.selector_element_bar = SelectorElementMenuBar(figure_window=figure_window)

        for selector in (
            self.selector_style_bar,
            self.selector_layout_bar,
            self.selector_chart_bar,
            self.selector_element_bar,
        ):
            self.stacklayout_bottom.addWidget(selector)

        self.selector_menu_bar = SelectorMenuBar(
            self.stacklayout_bottom,
            figure_window=figure_window,
        )
        self.menu_bar = MenuBar(table, figure_window)
        self.stacklayout_top.addWidget(self.selector_menu_bar)
        self.stacklayout_top.addWidget(self.menu_bar)

        self.change_button = ChangeButton("change_button")
        self.change_button.toggled.connect(self.the_button_was_toggled)
        self.sublayout.addWidget(self.change_button)
        self.sublayout.addLayout(self.stacklayout_top)
        self.sublayout.addStretch(1)

        self.layout.addLayout(self.sublayout)
        self.layout.addLayout(self.stacklayout_bottom)

    def the_button_was_toggled(self, checked):
        """Synchronize the button appearance after its checked state changes."""

        self.stacklayout_top.setCurrentIndex(1 if checked else 0)

    def show_style_selector(self):
        """Return focus to the existing Style project-creation workflow."""
        self.change_button.setChecked(False)
        self.selector_menu_bar.style_button.setChecked(True)
        self.stacklayout_top.setCurrentIndex(0)
        self.stacklayout_bottom.setCurrentIndex(0)
        self.selector_menu_bar.style_button.setFocus(Qt.OtherFocusReason)
