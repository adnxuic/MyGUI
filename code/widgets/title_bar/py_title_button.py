from Qt_core import *
from code.widgets import qss_func
import os


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class changebutton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setIcon(QIcon("pictures/icons/menu.svg"))
        self.setObjectName("change_button")
        self.setCheckable(True)
        self.setIconSize(QSize(30, 30))

        self.clicked.connect(self.change)

        self.rotated = False


    def change(self):
        if self.rotated:
            angle = 0
            color = QColor(255, 255, 255)
        else:
            angle = 90
            color = QColor(0, 0, 0)

        # 旋转图标
        pixmap = QPixmap("pictures/icons/menu.svg")
        transform = QTransform().rotate(angle)
        rotated_pixmap = pixmap.transformed(transform)

        # 改变颜色
        painter = QPainter()
        painter.begin(rotated_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(rotated_pixmap.rect(), color)
        painter.end()

        self.setIcon(QIcon(rotated_pixmap))
        self.rotated = not self.rotated

class menubutton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setText(button_name) # 设置按钮的文字
        self.setObjectName("menu_button")

class selectbutton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setText(button_name)
        self.setObjectName("select_button")

