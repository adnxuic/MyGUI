from Qt_core import *

from code.widgets import qss_func
from code.widgets.title_bar.py_title_button import changebutton, menubutton, selectbutton
from code.widgets.title_bar.py_selector_bar import PySelectorBar

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent

        self.setObjectName("title_bar")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout(self)
        self.sublayout = QHBoxLayout()

        # 添加按钮
        # 选择按钮
        self.change_button = changebutton('change_button')

        self.sublayout.addWidget(self.change_button)
        #

        button01 = menubutton('button01')
        self.sublayout.addWidget(button01)

        button02 = menubutton('button02')
        self.sublayout.addWidget(button02)

        button03 = menubutton('button03')
        self.sublayout.addWidget(button03)

        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.sublayout.addItem(spacer)


        # 关闭按钮
        button_close = QPushButton(QIcon("pictures/icons/close.svg"), "")
        button_close.setObjectName("close_button")
        button_close.clicked.connect(self.parent.close)
        self.sublayout.addWidget(button_close)

        # 添加上方布局
        self.layout.addLayout(self.sublayout)

        # 下方选择栏
        selector_bar = PySelectorBar()
        self.layout.addWidget(selector_bar)




    # 移动窗口事件
    # def moveWindow(self, event):
    #     if self.parent.isMaximized():
    #         curso_x = self.parent.pos().x()
    #         curso_y = self.parent.pos().y() - QCursor.pos().y()
    #         self.parent.move(curso_x, curso_y)
    #
    #     if event.button() == Qt.LeftButton:
    #         self.parent.move(self.parent.pos() + event.globalPos() - self.parent.dragPos)
    #         self.parent.dragPos = event.globalPos()
    #         event.accept()


