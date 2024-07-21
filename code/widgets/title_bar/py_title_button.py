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
    def __init__(self, button_name, icon_name=None, tooltip_text=None, tooltip_text_image_path=None, dialog=None):
        super().__init__()
        self.setText(button_name)
        self.setIcon(QIcon(icon_name))
        self.setObjectName("select_button")

        # 设置按钮的文本位于图标下方
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        # 在工具提示中添加文字和图片
        tooltip_text = f"<b>{tooltip_text}</b><br><img src='{tooltip_text_image_path}'>"
        self.setToolTip(tooltip_text)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.showTooltip)  # 连接到显示工具提示的槽
        self.timer.setInterval(1000)  # 设置定时器间隔为1000毫秒（一秒）

        # 链接对话框
        self.dialog = dialog
        self.clicked.connect(self.connect_dialog)

    def enterEvent(self, event):
        self.timer.stop()  # 停止定时器
        self.timer.start()  # 重新启动定时器
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.timer.stop()  # 鼠标离开时停止定时器
        QToolTip.hideText()  # 隐藏工具提示
        super().leaveEvent(event)

    def showTooltip(self):
        # 定时器触发后显示工具提示
        QToolTip.showText(self.mapToGlobal(QPoint(0, 0)), self.toolTip(), self)

    # 链接对话框
    def connect_dialog(self, dialog):
        self.dialog.exec()



class PullDownButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setObjectName("pull_down_button")
        self.setCheckable(True)
        self.setIcon(QIcon("pictures/icons/down.svg"))

        self.toggled.connect(self.the_button_was_toggled)
        self.clicked.connect(self.toggle_menu)

    # 连接菜单
    def connect_menu(self, connect_menu):
        self.connect_menu = connect_menu

    def the_button_was_toggled(self, checked):
        if not checked:
            angle = 0
        else:
            angle = 180

        # 旋转图标
        pixmap = QPixmap("pictures/icons/down.svg")
        transform = QTransform().rotate(angle)
        rotated_pixmap = pixmap.transformed(transform)

        self.setIcon(QIcon(rotated_pixmap))

    # 显示菜单
    def toggle_menu(self, checked):
        if checked:  # 如果按钮被设置为按下状态

            button_rect = self.rect() # 获取按钮的位置和尺寸
            global_position = self.mapToGlobal(button_rect.bottomLeft()) # 获取按钮的全局位置

            # 可以调整位置，比如使菜单向右偏移20像素
            adjusted_position = global_position + QPoint(-500, -8)

            # 显示菜单在计算后的位置
            self.connect_menu.exec(adjusted_position)
        else:  # 如果按钮被设置为未按下状态
            self.connect_menu.hide()
