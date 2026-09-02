"""Configure and connect the optional MATLAB integration."""

from PySide6.QtWidgets import QFrame, QLabel, QMessageBox, QPushButton, QVBoxLayout

from mygui.application_theme import bind_widget_qss

from mygui import status_messages
from mygui.database import matlab_adapter
from mygui.widgets.fig_control_window.background_task import start_matlab_task

import time


class PyMatlabWindow(QFrame):
    """Provide the py matlab window Qt widget."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("matlab_window")

        bind_widget_qss(self, "mygui/widgets/fig_control_window/style.qss")

        self._connect_request_id = 0

        self.layout = QVBoxLayout()
        self.layout.setSpacing(8)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.setLayout(self.layout)

        if matlab_adapter.is_matlab_enabled():
            self._show_connected_description()
        else:
            self._show_connect_button()

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _show_connect_button(self):
        self._clear_layout()
        self.matlab_isconnect = QPushButton("Connect Matlab")
        self.matlab_isconnect.setMinimumSize(120, 30)
        self.matlab_isconnect.clicked.connect(self.matlab_connect_click)
        self.layout.addWidget(self.matlab_isconnect)
        self.layout.addStretch()

    def _show_connected_description(self):
        self._clear_layout()
        title = QLabel("Matlab Connected")
        title.setObjectName("matlab_connected_title")
        description = QLabel(
            "MATLAB fitting is now available from each fitting curve. "
            "Select a fitting curve, choose its X/Y data, then press the Matlab engine button."
        )
        description.setWordWrap(True)
        self.layout.addWidget(title)
        self.layout.addWidget(description)
        self.layout.addStretch()

    def matlab_connect_click(self):
        """Start or stop the optional MATLAB connection."""

        self._connect_request_id += 1
        request_id = self._connect_request_id
        started_at = time.monotonic()
        matlab_adapter.matlab_logger().info("MATLAB connect request started request_id=%s", request_id)
        self.matlab_isconnect.setEnabled(False)
        self.matlab_isconnect.setText("Connecting...")
        start_matlab_task(
            self,
            matlab_adapter.ensure_matlab_available_isolated,
            lambda status, rid=request_id, started=started_at: self._matlab_connect_succeeded(rid, started, status),
            lambda message, rid=request_id, started=started_at: self._matlab_connect_failed(rid, started, message),
        )

    def _matlab_connect_succeeded(self, request_id, started_at, _status):
        if request_id != self._connect_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale connect success ignored request_id=%s current_request_id=%s",
                request_id,
                self._connect_request_id,
            )
            return
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().info(
            "MATLAB connect request succeeded request_id=%s elapsed=%.3fs",
            request_id,
            elapsed,
        )
        matlab_adapter.set_matlab_enabled(True)
        self._show_connected_description()
        status_messages.show_success("MATLAB runtime connected.")

    def _matlab_connect_failed(self, request_id, started_at, message):
        if request_id != self._connect_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale connect failure ignored request_id=%s current_request_id=%s",
                request_id,
                self._connect_request_id,
            )
            return
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().warning(
            "MATLAB connect request failed request_id=%s elapsed=%.3fs message=%s",
            request_id,
            elapsed,
            message,
        )
        self.reset_to_connect_button()
        status_messages.show_error(message)
        QMessageBox.warning(self, "Connect Matlab", message)

    def reset_to_connect_button(self):
        """Reset to connect button."""

        matlab_adapter.set_matlab_enabled(False)
        self._show_connect_button()
