from Qt_core import *
from code.widgets import qss_func
from code.widgets.title_bar.button import menubutton, selectbutton
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTitleBar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("title_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QGridLayout(self)

        # 添加按钮
        # 上方按钮
        button00 = menubutton('button00')
        self.layout.addWidget(button00, 0, 0)

        # 下方按钮
        button10 = selectbutton('button10')
        self.layout.addWidget(button10, 1, 0)
