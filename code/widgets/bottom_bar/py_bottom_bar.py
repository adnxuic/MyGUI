"""Compose the application's message and state bars."""

from Qt_core import *
from code.widgets import qss_func
from code.widgets.bottom_bar.py_message_bar import PyMessageBar
from code.widgets.bottom_bar.py_state_bar import FeatureIndicator, PyStateBar

from code import tex_config
from code.database import matlab_adapter

import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


def _feature_indicators():
    """Central, extensible registry of State Bar features.

    Add a new FeatureIndicator here to surface another optional feature's
    enabled state; no other change is required.
    """
    return (
        FeatureIndicator(
            name="matlab",
            label="MATLAB",
            is_enabled=matlab_adapter.is_matlab_enabled,
            register_listener=matlab_adapter.register_matlab_state_listener,
            unregister_listener=matlab_adapter.unregister_matlab_state_listener,
        ),
        FeatureIndicator(
            name="tex",
            label="TeX",
            is_enabled=tex_config.is_tex_enabled,
            register_listener=tex_config.register_tex_state_listener,
            unregister_listener=tex_config.unregister_tex_state_listener,
        ),
    )


class PyBottomBar(QFrame):
    """Provide the py bottom bar Qt widget."""

    def __init__(self):
        super().__init__()

        self.setObjectName("bottom_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setSpacing(10)

        self.message_bar = PyMessageBar()
        self.layout.addWidget(self.message_bar, stretch=1)

        self.state_bar = PyStateBar(_feature_indicators())
        self.layout.addWidget(self.state_bar, stretch=0)

        self.destroyed.connect(self.state_bar.cleanup)

    def show_message(self, message, level="info"):
        """Show message."""

        self.message_bar.show_message(message, level)

    def show_error(self, message):
        """Show error."""

        self.message_bar.show_error(message)

    def show_success(self, message):
        """Show success."""

        self.message_bar.show_success(message)

    def show_warning(self, message):
        """Show warning."""

        self.message_bar.show_warning(message)

    def clear_message(self):
        """Clear the current Message Bar text and reset its level."""

        self.message_bar.clear_message()
