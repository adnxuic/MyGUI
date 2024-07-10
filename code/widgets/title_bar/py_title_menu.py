from Qt_core import *
from code.widgets.title_bar.py_title_button import SelectMenuButton, MenuButton, SelectButton


class SelectorMenuBar(QFrame):
    def __init__(self, stacklayout_bottom = None):
        super().__init__()

        self.setObjectName("selector_menu_bar")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stacklayout_bottom = stacklayout_bottom

        # 设置按钮组
        self.buttonGroup = QButtonGroup(self)
        self.buttonGroup.setExclusive(True)  # 设置互斥

        # 添加按钮
        self.style_button = SelectMenuButton('style', 'pictures/icons/style.svg')
        self.style_button.setChecked(True)
        self.style_button.toggled.connect(self.the_button_was_toggled)
        self.layout.addWidget(self.style_button)
        self.buttonGroup.addButton(self.style_button)

        self.layout_button = SelectMenuButton('layout', 'pictures/icons/layout.svg')
        self.layout_button.toggled.connect(self.the_button_was_toggled)
        self.layout.addWidget(self.layout_button)
        self.buttonGroup.addButton(self.layout_button)

        self.chart_button = SelectMenuButton('chart', 'pictures/icons/chart.svg')
        self.chart_button.toggled.connect(self.the_button_was_toggled)
        self.layout.addWidget(self.chart_button)
        self.buttonGroup.addButton(self.chart_button)


    def the_button_was_toggled(self, checked):
        if not checked:
            return

        if self.style_button.isChecked():
            self.stacklayout_bottom.setCurrentIndex(0)
        elif self.layout_button.isChecked():
            self.stacklayout_bottom.setCurrentIndex(1)
        elif self.chart_button.isChecked():
            self.stacklayout_bottom.setCurrentIndex(2)


class MenuBar(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("menu_bar")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 4)

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


class ControlBar(QFrame):
    def __init__(self, parent=None):
        super().__init__()
        # 设置对象名称
        self.setObjectName("control_bar")
        # 设置布局
        self.layout = QHBoxLayout(self)

        self.parent = parent

        # 添加弹性空间
        spacer = QSpacerItem(10, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout.addItem(spacer)

        # 添加最小化按钮
        minmize_button = QPushButton(QIcon("pictures/icons/minimize.svg"), "")
        minmize_button.setObjectName("minimize_button")
        minmize_button.clicked.connect(self.parent.showMinimized)
        self.layout.addWidget(minmize_button)



        # 添加最大化按钮


        # 添加关闭按钮
        button_close = QPushButton(QIcon("pictures/icons/close.svg"), "")
        button_close.setObjectName("close_button")
        button_close.clicked.connect(self.parent.close)
        self.layout.addWidget(button_close)


class SelectorStyleMenu(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("selector_menu")

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.layout.setContentsMargins(0, 0, 0, 20)

        self.curve_button = SelectButton('curve', 'pictures/icons/curve.svg')
        self.layout.addWidget(self.curve_button)

        self.setLayout(self.layout)



class SelectorLayoutMenu(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("selector_menu")

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 20)

        self.setLayout(self.layout)


class SelectorChartMenu(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("selector_menu")

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 20)

        self.curve_button = SelectButton('curve', 'pictures/icons/curve.svg')


        self.layout.addWidget(self.curve_button)
        self.setLayout(self.layout)







