"""Configure the optional TeX rendering integration."""

from Qt_core import *
from code.widgets.qss_func import qss_loader
from code import tex_config
from code import status_messages

import matplotlib as mpl

import os
import time

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTexWindow(QFrame):
    """Provide the py tex window Qt widget."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("tex_window")

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        self.layout = QVBoxLayout()

        # 设置是否用latex引擎
        self.is_latex = False
        self.latex_engine = QCheckBox("Use Latex Engine")
        self.latex_engine.setChecked(False)
        self.latex_engine.checkStateChanged.connect(self.use_latex_engine)
        self.layout.addWidget(self.latex_engine)

        # 导言区，输入要导入的latex包
        self.preamble_box = QGroupBox("Preamble")
        self.preamble_layout = QVBoxLayout()
        self.preamble_box.setLayout(self.preamble_layout)

        # 设置默认导入的包
        self.preamble_text = tex_config.default_preamble_text()
        self.preamble_input = QPlainTextEdit()
        self.preamble_input.setPlainText(self.preamble_text)

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
            self.is_latex = False
            tex_config.set_tex_enabled(False)
            logger.info("TeX disable request succeeded")
            status_messages.show_message("TeX rendering disabled.", "info")
            return

        preamble = tex_config.normalize_preamble(self.preamble_input.toPlainText())
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        started_at = time.monotonic()
        logger.info("TeX enable request started preamble_line_count=%s", preamble_line_count)
        status_messages.show_message("Checking TeX runtime...", "info")
        error = self._validate_preamble(preamble)
        if error is not None:
            elapsed = time.monotonic() - started_at
            logger.warning("TeX enable request failed elapsed=%.3fs message=%s", elapsed, error)
            self._reject_latex(error)
            return

        self.preamble_text = preamble
        mpl.rcParams['text.latex.preamble'] = preamble
        self.is_latex = True
        tex_config.set_tex_enabled(True)
        elapsed = time.monotonic() - started_at
        logger.info(
            "TeX enable request succeeded elapsed=%.3fs preamble_line_count=%s",
            elapsed,
            preamble_line_count,
        )
        status_messages.show_success("TeX runtime check passed; TeX rendering is enabled.")

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
        self.is_latex = False
        tex_config.set_tex_enabled(False)
        status_messages.show_error(message)

    def update_preamble(self):
        """Update preamble."""

        preamble = tex_config.normalize_preamble(self.preamble_input.toPlainText())
        preamble_line_count = len(preamble.splitlines()) if preamble else 0
        started_at = time.monotonic()
        logger = tex_config.tex_logger()
        logger.info(
            "TeX preamble update request started enabled=%s preamble_line_count=%s",
            self.is_latex,
            preamble_line_count,
        )

        if self.is_latex:
            error = self._validate_preamble(preamble)
            if error is not None:
                elapsed = time.monotonic() - started_at
                logger.warning(
                    "TeX preamble update request failed elapsed=%.3fs message=%s",
                    elapsed,
                    error,
                )
                status_messages.show_error(error)
                return

        self.preamble_text = preamble
        mpl.rcParams['text.latex.preamble'] = preamble
        elapsed = time.monotonic() - started_at
        logger.info(
            "TeX preamble update request succeeded elapsed=%.3fs enabled=%s preamble_line_count=%s",
            elapsed,
            self.is_latex,
            preamble_line_count,
        )
        if self.is_latex:
            status_messages.show_success("TeX preamble updated and verified.")
        else:
            status_messages.show_message("TeX preamble updated.", "info")
