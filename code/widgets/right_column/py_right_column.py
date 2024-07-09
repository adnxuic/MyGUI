from Qt_core import *
from code.widgets.right_column.py_tex_window import PyTexWindow
from code.widgets.right_column.py_matlab_window import PyMatlabWindow

from code.widgets import qss_func

import os
current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class PyRightColumn(QFrame):
    def __init__(self, parent=None):
        super().__init__()

        self.parent = parent

        self.setObjectName("right_column")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        # 创建两个窗口
        self.tex_window = PyTexWindow(parent)
        self.matlab_window = PyMatlabWindow(parent)

        self.layout = QVBoxLayout(self)

        self.tex_button = QPushButton(QIcon("pictures/icons/tex.svg"), "")
        self.tex_button.setObjectName("tex_button")
        self.tex_button.setCheckable(True)
        self.tex_button.setChecked(False)
        self.tex_button.clicked.connect(self.tex_show)
        self.layout.addWidget(self.tex_button)

        self.matlab_button = QPushButton(QIcon("pictures/icons/matlab.svg"), "")
        self.matlab_button.setObjectName("matlab_button")
        self.matlab_button.setCheckable(True)
        self.matlab_button.setChecked(False)
        self.matlab_button.clicked.connect(self.matlab_show)
        self.layout.addWidget(self.matlab_button)


    def tex_show(self):
        self.tex_window.setVisible(not self.tex_window.isVisible())

    def matlab_show(self):
        self.matlab_window.setVisible(not self.matlab_window.isVisible())





