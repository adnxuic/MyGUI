from Qt_core import *
from code.widgets import qss_func
import os


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

class ChangeButton(QPushButton):
    def __init__(self, button_name):
        super().__init__()
        self.setIcon(QIcon("pictures/icons/menu_change.svg"))
        self.setObjectName("change_button")
        self.setCheckable(True)

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
        pixmap = QPixmap("pictures/icons/menu_change.svg")
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


class SelectMenuButton(QPushButton):
    def __init__(self, button_name, IconName=None):
        super().__init__()
        self.setObjectName("select_menu_button")
        self.setText(button_name) # 设置按钮的文字
        self.IconName = IconName
        self.setIcon(QIcon(IconName))

        self.setCheckable(True)
        # 连接按钮状态改变信号到槽函数
        self.toggled.connect(self.the_button_was_toggled)



    def the_button_was_toggled(self, checked):
        if not checked:
            color = QColor(255, 255, 255)
        else:
            color = QColor(0, 0, 0)

        # 改变颜色
        pixmap = QPixmap(self.IconName)
        painter = QPainter()
        painter.begin(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()

        self.setIcon(QIcon(pixmap))


class MenuButton(QPushButton):
    def __init__(self, button_name, IconName=None, parent=None):
        super().__init__()
        self.parent = parent
        self.setObjectName("menu_button")
        self.setText(button_name) # 设置按钮的文字
        self.IconName = IconName
        self.setIcon(QIcon(IconName))



class SelectButton(QToolButton):
    def __init__(self, button_name, icon_name=None):
        super().__init__()
        self.setText(button_name)
        self.setIcon(QIcon(icon_name))
        self.setObjectName("select_button")

        # 设置按钮的文本位于图标下方
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)



