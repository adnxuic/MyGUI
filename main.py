import sys
import os


from code.widgets import MainWindow_Setting

from Qt_core import *


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 设置窗口为无边框
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.ui = MainWindow_Setting()
        self.ui.setup_ui(self)
        self.showMaximized()  # 最大化窗口

        self.hide_grips = True  # 隐藏窗口


    # def mousePressEvent(self, event):
    #     # SET DRAG POS WINDOW
    #     # 设置窗口拖动位置
    #     self.dragPos = event.globalPosition().toPoint()



if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
