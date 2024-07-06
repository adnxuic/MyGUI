import sys
import os


from code.widgets import MainWindow_Setting


from Qt_core import *


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = MainWindow_Setting()
        self.ui.setup_ui(self)

        # self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
