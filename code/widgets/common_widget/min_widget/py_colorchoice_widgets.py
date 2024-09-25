from Qt_core import *

from code.figuremodify.style_base.color_base import color_combi_dict


class ColorSelector:
    def __init__(self):
        self.current_color = '#000000'
        self.color_list_num = 1
        self.category = None
        self.subcategory = None

    def update_combination(self, category, subcategory=None, index=0):
        self.category = category
        self.subcategory = subcategory
        if category is None:
            self.current_color = '#000000'
            self.color_list_num = 1
        else:
            self.color_list_num = index + 1
            if subcategory is None:
                if self.color_list_num < len(color_combi_dict[self.category]):
                    self.current_color = color_combi_dict[self.category][self.color_list_num]
                    self.color_list_num += 1
                else:
                    self.update_combination(None, None)
            else:
                if self.color_list_num < len(color_combi_dict[self.category][self.subcategory]):
                    self.current_color = color_combi_dict[self.category][self.subcategory][self.color_list_num]
                    self.color_list_num += 1
                else:
                    self.update_combination(None, None)


    def get_color(self):
        color = self.current_color

        if self.category is not None:
            if self.subcategory is not None:
                if self.color_list_num < len(color_combi_dict[self.category][self.subcategory]):
                    self.current_color = color_combi_dict[self.category][self.subcategory][self.color_list_num]
                    self.color_list_num += 1
                else:
                    self.update_combination(None, None)
            else:
                if self.color_list_num < len(color_combi_dict[self.category]):
                    self.current_color = color_combi_dict[self.category][self.color_list_num]
                    self.color_list_num += 1
                else:
                    self.update_combination(None, None)

        return color


class ColorChoiceWidget(QFrame):
    def __init__(self, color = "#000000",connect_signal: callable = None, colorselector: ColorSelector = None):
        super().__init__()
        self.colorselector = colorselector

        if colorselector:
            self.current_color = colorselector.get_color()
        else:
            self.current_color = color

        self.layout = QHBoxLayout()
        self.connect_signal = connect_signal

        # Color display area
        self.color_display = QLabel()
        self.color_display.setFixedSize(50, 50)
        self.updateColorDisplay()
        self.layout.addWidget(self.color_display)

        # Color selection button
        self.sublayout = QVBoxLayout()

        self.color_menu = QMenu(self)
        self.color_button = QPushButton("选择颜色")
        self.color_button.clicked.connect(self.showColorMenu)
        self.sublayout.addWidget(self.color_button)

        # RGB code display
        self.rgb_label = QLabel()
        self.sublayout.addWidget(self.rgb_label)
        self.createColorMenu()

        self.layout.addLayout(self.sublayout)

        # 设置默认颜色
        self.updateColorDisplay()
        self.updateRGBLabel()
        if self.connect_signal:
            self.connect_signal(color)

        self.setLayout(self.layout)

    def createColorMenu(self):
        for category, subcategories in color_combi_dict.items():
            submenu = self.color_menu.addMenu(category)
            if isinstance(subcategories, dict):
                for subcategory, colors in subcategories.items():
                    subsubmenu = submenu.addMenu(subcategory)
                    for i, color in enumerate(colors):
                        self.addColorAction(subsubmenu, color, category, subcategory, i)
            else:
                for i, color in enumerate(subcategories):
                    self.addColorAction(submenu, color, category, i)

    def addColorAction(self, menu, color, category=None, subcategory=None, index=0):
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(color))
        icon = QIcon(pixmap)
        action = QAction(icon, color, self)
        action.triggered.connect(lambda checked, c=color,
                                        cat=category, subcat=subcategory,
                                        i=index: self.updateColor(c, cat, subcat, i))
        menu.addAction(action)

    def showColorMenu(self):
        self.color_menu.exec(self.color_button.mapToGlobal(self.color_button.rect().bottomLeft()))

    def updateColor(self, color, category=None, subcategory=None, index=0):
        self.current_color = color
        self.updateColorDisplay()
        self.updateRGBLabel()
        if self.connect_signal:
            self.connect_signal(color)
        if self.colorselector:
            self.colorselector.update_combination(category, subcategory, index)

    def updateColorDisplay(self):
        self.color_display.setStyleSheet(f"background-color: {self.current_color};")

    def updateRGBLabel(self):
        color = QColor(self.current_color)
        self.rgb_label.setText(f"RGB: ({color.red()}, {color.green()}, {color.blue()})")

    def get_color(self):
        return self.current_color
