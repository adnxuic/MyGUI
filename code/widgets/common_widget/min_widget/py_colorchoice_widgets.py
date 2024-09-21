from Qt_core import *

from code.figuremodify.style_base.color_base import color_combi_dict


class ColorChoiceWidget(QFrame):
    def __init__(self, connect_signal: callable):
        super().__init__()
        self.current_color = "#000000"
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
        self.updateColor("#000000")

        self.setLayout(self.layout)


    def createColorMenu(self):
        for category, subcategories in color_combi_dict.items():
            submenu = self.color_menu.addMenu(category)
            if isinstance(subcategories, dict):
                for subcategory, colors in subcategories.items():
                    subsubmenu = submenu.addMenu(subcategory)
                    for color in colors:
                        self.addColorAction(subsubmenu, color)
            else:
                for color in subcategories:
                    self.addColorAction(submenu, color)

    def addColorAction(self, menu, color):
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(color))
        icon = QIcon(pixmap)
        action = QAction(icon, color, self)
        action.triggered.connect(lambda checked, c=color: self.updateColor(c))
        menu.addAction(action)

    def showColorMenu(self):
        self.color_menu.exec(self.color_button.mapToGlobal(self.color_button.rect().bottomLeft()))

    def updateColor(self, color):
        self.current_color = color
        self.updateColorDisplay()
        self.updateRGBLabel()
        self.connect_signal(self.current_color)

    def updateColorDisplay(self):
        self.color_display.setStyleSheet(f"background-color: {self.current_color};")

    def updateRGBLabel(self):
        color = QColor(self.current_color)
        self.rgb_label.setText(f"RGB: ({color.red()}, {color.green()}, {color.blue()})")