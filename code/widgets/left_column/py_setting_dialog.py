from Qt_core import *
from code.widgets import qss_func
import os


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "setting_dialog_style.qss")

class PySettingDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setObjectName("setting_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle("设置")
        self.setWindowIcon(QIcon("pictures/icons/setting.svg"))


