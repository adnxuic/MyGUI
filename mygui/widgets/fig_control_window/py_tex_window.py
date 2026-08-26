"""Configure the optional TeX rendering integration."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QGroupBox, QPlainTextEdit, QPushButton, QVBoxLayout
from mygui.application_theme import bind_widget_qss
from mygui.widgets.fig_control_window.background_task import (
    cancel_background_tasks,
    start_background_task,
)
from mygui import tex_config
from mygui import status_messages

import time

class PyTexWindow(QFrame):
    """Provide the py tex window Qt widget."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("tex_window")
        self._validation_request_id = 0

        bind_widget_qss(self, "mygui/widgets/fig_control_window/style.qss")

        self.layout = QVBoxLayout()

        runtime = tex_config.read_tex_runtime()

        # 设置是否用latex引擎
        self.latex_engine = QCheckBox("Use Latex Engine")
        self.latex_engine.setChecked(runtime.enabled)
        self.latex_engine.checkStateChanged.connect(self.use_latex_engine)
        self.layout.addWidget(self.latex_engine)

        # 导言区，输入要导入的latex包
        self.preamble_box = QGroupBox("Preamble")
        self.preamble_layout = QVBoxLayout()
        self.preamble_box.setLayout(self.preamble_layout)

        # 设置默认导入的包
        self.preamble_input = QPlainTextEdit()
        self.preamble_input.setPlainText(runtime.preamble)

        self.preamble_layout.addWidget(self.preamble_input)

        # 更新设置按钮
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_preamble)
        self.preamble_layout.addWidget(self.update_btn)

        self.layout.addWidget(self.preamble_box)
        self.setLayout(self.layout)

    def use_latex_engine(self, state):
        """Apply the selected TeX engine setting."""

        checked = state == Qt.Checked or state == Qt.CheckState.Checked
        logger = tex_config.tex_logger()
        if not checked:
            self._validation_request_id += 1
            cancel_background_tasks(self)
            self._set_validation_busy(False)
            update = tex_config.configure_tex_runtime(enabled=False)
            logger.info("TeX disable request succeeded")
            if update.warnings:
                status_messages.show_warning("; ".join(update.warnings))
            else:
                status_messages.show_message("TeX rendering disabled.", "info")
            return

        preamble = tex_config.normalize_preamble(self.preamble_input.toPlainText())
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        started_at = time.monotonic()
        logger.info("TeX enable request started preamble_line_count=%s", preamble_line_count)
        status_messages.show_message("Checking TeX runtime...", "info")
        self._validation_request_id += 1
        request_id = self._validation_request_id
        self._set_validation_busy(True)
        start_background_task(
            self,
            self._validate_preamble,
            lambda error, rid=request_id: self._finish_enable_request(
                rid,
                preamble,
                started_at,
                error,
            ),
            lambda message, rid=request_id: self._finish_enable_request(
                rid,
                preamble,
                started_at,
                message,
            ),
            preamble,
            logger=logger,
            task_log_prefix="TeX validation task",
        )

    def _set_validation_busy(self, busy: bool) -> None:
        self.latex_engine.setEnabled(not busy)
        self.update_btn.setEnabled(not busy)

    def _finish_enable_request(
        self,
        request_id: int,
        preamble: str,
        started_at: float,
        error: str | None,
    ) -> None:
        if request_id != self._validation_request_id:
            return
        self._set_validation_busy(False)
        logger = tex_config.tex_logger()
        if error is not None:
            elapsed = time.monotonic() - started_at
            logger.warning("TeX enable request failed elapsed=%.3fs message=%s", elapsed, error)
            self._reject_latex(error)
            return

        update = tex_config.configure_tex_runtime(
            enabled=True,
            preamble=preamble,
        )
        elapsed = time.monotonic() - started_at
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        logger.info(
            "TeX enable request succeeded elapsed=%.3fs preamble_line_count=%s",
            elapsed,
            preamble_line_count,
        )
        if update.warnings:
            status_messages.show_warning("; ".join(update.warnings))
        else:
            status_messages.show_success(
                "TeX runtime check passed; TeX rendering is enabled."
            )

    @staticmethod
    def _has_tex_engine() -> bool:
        return tex_config.has_tex_engine()

    def _validate_preamble(self, preamble: str) -> str | None:
        if not self._has_tex_engine():
            return "No TeX executable was found on PATH."
        return tex_config.validate_tex_runtime(preamble)

    def _reject_latex(self, message: str):
        self.latex_engine.blockSignals(True)
        self.latex_engine.setChecked(False)
        self.latex_engine.blockSignals(False)
        tex_config.configure_tex_runtime(enabled=False)
        status_messages.show_error(message)

    def update_preamble(self):
        """Update preamble."""

        preamble = tex_config.normalize_preamble(self.preamble_input.toPlainText())
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        started_at = time.monotonic()
        logger = tex_config.tex_logger()
        logger.info(
            "TeX preamble update request started enabled=%s preamble_line_count=%s",
            tex_config.is_tex_enabled(),
            preamble_line_count,
        )

        if tex_config.is_tex_enabled():
            self._validation_request_id += 1
            request_id = self._validation_request_id
            self._set_validation_busy(True)
            status_messages.show_message("Checking TeX preamble...", "info")
            start_background_task(
                self,
                self._validate_preamble,
                lambda error, rid=request_id: self._finish_preamble_request(
                    rid,
                    preamble,
                    started_at,
                    error,
                ),
                lambda message, rid=request_id: self._finish_preamble_request(
                    rid,
                    preamble,
                    started_at,
                    message,
                ),
                preamble,
                logger=logger,
                task_log_prefix="TeX validation task",
            )
            return

        self._commit_preamble(preamble, started_at)

    def _finish_preamble_request(
        self,
        request_id: int,
        preamble: str,
        started_at: float,
        error: str | None,
    ) -> None:
        if request_id != self._validation_request_id:
            return
        self._set_validation_busy(False)
        if error is not None:
            elapsed = time.monotonic() - started_at
            tex_config.tex_logger().warning(
                "TeX preamble update request failed elapsed=%.3fs message=%s",
                elapsed,
                error,
            )
            status_messages.show_error(error)
            return
        self._commit_preamble(preamble, started_at)

    def _commit_preamble(self, preamble: str, started_at: float) -> None:
        logger = tex_config.tex_logger()

        update = tex_config.configure_tex_runtime(preamble=preamble)
        enabled = update.change.after.enabled
        elapsed = time.monotonic() - started_at
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        logger.info(
            "TeX preamble update request succeeded elapsed=%.3fs enabled=%s preamble_line_count=%s",
            elapsed,
            enabled,
            preamble_line_count,
        )
        if update.warnings:
            status_messages.show_warning("; ".join(update.warnings))
        elif enabled:
            status_messages.show_success("TeX preamble updated and verified.")
        else:
            status_messages.show_message("TeX preamble updated.", "info")

    def closeEvent(self, event):
        self._validation_request_id += 1
        cancel_background_tasks(self)
        super().closeEvent(event)
