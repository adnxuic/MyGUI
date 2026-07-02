from Qt_core import *
from code.widgets.qss_func import qss_loader

import matplotlib as mpl

import os
import shutil

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTexWindow(QFrame):
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
        self.preamble_text = ''
        self.preamble_input = QPlainTextEdit()
        self.preamble_input.setPlainText(r"\usepackage{amsmath}")
        self.preamble_input.appendPlainText(r'\usepackage{newtxtext,newtxmath}')

        self.preamble_layout.addWidget(self.preamble_input)

        # 更新设置按钮
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_preamble)
        self.preamble_layout.addWidget(self.update_btn)

        self.layout.addWidget(self.preamble_box)
        self.setLayout(self.layout)

    def use_latex_engine(self, state):
        checked = state == Qt.Checked or state == Qt.CheckState.Checked
        if checked and not self._has_tex_engine():
            self.latex_engine.blockSignals(True)
            self.latex_engine.setChecked(False)
            self.latex_engine.blockSignals(False)
            self.is_latex = False
            mpl.rcParams['text.usetex'] = False
            QMessageBox.warning(self, "TeX Engine", "No TeX executable was found on PATH.")
            return

        if checked:
            self.is_latex = True
        else:
            self.is_latex = False

        mpl.rcParams['text.usetex'] = self.is_latex

    @staticmethod
    def _has_tex_engine() -> bool:
        return any(shutil.which(command) for command in ("latex", "pdflatex", "xelatex", "tectonic"))

    def update_preamble(self):
        # 清空导言区
        mpl.rcParams['text.latex.preamble'] = ''
        self.preamble_text = ''
        # 更新导言区,搜集每一行的内容
        for i in range(self.preamble_input.document().lineCount()):
            if not self.preamble_input.document().findBlockByLineNumber(i).text() == "":
                self.preamble_text += self.preamble_input.document().findBlockByLineNumber(i).text()

        mpl.rcParams['text.latex.preamble'] = self.preamble_text
