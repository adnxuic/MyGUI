from Qt_core import *
from code.widgets import qss_func
import os


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class menubutton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setText(button_name) # 设置按钮的文字
        self.setObjectName("menu_button")
        qss_file = qss_func.qss_loader(qss_path)
        # self.setStyleSheet(qss_file)



class selectbutton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setText(button_name)
        self.setObjectName("select_button")
        qss_file = qss_func.qss_loader(qss_path)
        # self.setStyleSheet(qss_file)
