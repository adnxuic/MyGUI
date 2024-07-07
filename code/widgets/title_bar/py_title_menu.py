from Qt_core import *
from code.widgets.title_bar.py_title_button import SelectMenuButton, MenuButton


class SelectorMenuBar(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QHBoxLayout(self)

        # 设置按钮组
        self.buttonGroup = QButtonGroup(self)
        self.buttonGroup.setExclusive(True)  # 设置互斥

        # 添加按钮
        style_button = SelectMenuButton('style', 'pictures/icons/style.svg')
        self.layout.addWidget(style_button)
        self.buttonGroup.addButton(style_button)

        layout_button = SelectMenuButton('layout', 'pictures/icons/layout.svg')
        self.layout.addWidget(layout_button)
        self.buttonGroup.addButton(layout_button)

        chart_button = SelectMenuButton('chart', 'pictures/icons/chart.svg')
        self.layout.addWidget(chart_button)
        self.buttonGroup.addButton(chart_button)


class MenuBar(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("menu_bar")
        self.layout = QHBoxLayout(self)

        # 创建触发文件菜单的按钮
        self.file_button = MenuButton('file', 'pictures/icons/file.svg', self)
        self.file_button.clicked.connect(lambda : self.show_menu(self.file_menu, self.file_button))
        self.layout.addWidget(self.file_button)

        # 添加分割线
        separator = QFrame(self)
        separator.setFrameShape(QFrame.VLine)  # 设置为垂直线类型
        separator.setFrameShadow(QFrame.Sunken)  # 给线一个凹陷的外观
        self.layout.addWidget(separator)

        # 创建触发编辑菜单的按钮
        self.edit_button = QPushButton('edit', self)
        self.edit_button.setObjectName('menu_button')
        self.edit_button.clicked.connect(lambda : self.show_menu(self.edit_menu, self.edit_button))
        self.layout.addWidget(self.edit_button)


        # 添加弹性空间
        spacer = QSpacerItem(10, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout.addItem(spacer)



        # 设置文件菜单
        self.file_menu = QMenu(self)
        self.file_menu.addAction('style')
        self.file_menu.addAction('layout')
        self.file_menu.addAction('chart')

        # 设置编辑菜单
        self.edit_menu = QMenu(self)
        self.edit_menu.addAction('copy')
        self.edit_menu.addAction('paste')
        self.edit_menu.addAction('cut')

    def show_menu(self, menu_name, button_name):
        menu_name.exec(button_name.mapToGlobal(button_name.rect().bottomLeft()))


class SelectorMenu(QFrame):
    def __init__(self):
        super().__init__()

        self.layout = QHBoxLayout(self)







