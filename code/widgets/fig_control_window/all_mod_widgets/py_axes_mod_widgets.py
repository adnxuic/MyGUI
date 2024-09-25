from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.py_axes_modify import PyAxesModify
from code.figuremodify.style_base.color_base import color_combi_dict

from matplotlib.axes import Axes

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "axes_mod_style.qss")


class PyCommonModWidget(QFrame):
    def __init__(self, axe: Axes, axe_modify: PyAxesModify):
        super().__init__()

        self.setObjectName("common_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.axe = axe
        self.axe_modify = axe_modify

        self.layout = QVBoxLayout()

        # 颜色组合的选择
        self.color_layout = QHBoxLayout()
        self.color_layout.addWidget(QLabel("颜色组合:"))

        self.color_combi_button = QPushButton("选择颜色组合")
        self.color_combi_button.clicked.connect(self.showColorMenu)

        self.color_combi_menu = QMenu()
        for category, subcategories in color_combi_dict.items():
            if isinstance(subcategories, dict):
                submenu = self.color_combi_menu.addMenu(category)
                for subcategory in subcategories.keys():
                    self.addColorAction(submenu, category, subcategory)
            else:
                self.addColorAction(self.color_combi_menu, category)

        self.color_layout.addWidget(self.color_combi_button)

        self.layout.addLayout(self.color_layout)

        # 设置xy轴可见的范围
        self.xy_range_layout = QHBoxLayout()
        self.x_range_layout = QVBoxLayout()
        self.y_range_layout = QVBoxLayout()

        self.x_range_layout.addWidget(QLabel("X轴范围:"))
        self.x_min_input = QDoubleSpinBox(self)
        self.x_min_input.setRange(float("-inf"), float("inf"))
        self.x_min_input.setSingleStep(1)
        self.x_min_input.setValue(0)
        self.x_min_input.valueChanged.connect(self.set_x_range)

        self.x_max_input = QDoubleSpinBox(self)
        self.x_max_input.setRange(float("-inf"), float("inf"))
        self.x_max_input.setSingleStep(1)
        self.x_max_input.setValue(100)
        self.x_max_input.valueChanged.connect(self.set_x_range)

        self.x_range_layout.addWidget(self.x_min_input)
        self.x_range_layout.addWidget(self.x_max_input)

        self.y_range_layout.addWidget(QLabel("Y轴范围:"))
        self.y_min_input = QDoubleSpinBox(self)
        self.y_min_input.setRange(float("-inf"), float("inf"))
        self.y_min_input.setSingleStep(1)
        self.y_min_input.setValue(0)
        self.y_min_input.valueChanged.connect(self.set_y_range)

        self.y_max_input = QDoubleSpinBox(self)
        self.y_max_input.setRange(float("-inf"), float("inf"))
        self.y_max_input.setSingleStep(1)
        self.y_max_input.setValue(100)
        self.y_max_input.valueChanged.connect(self.set_y_range)

        self.y_range_layout.addWidget(self.y_min_input)
        self.y_range_layout.addWidget(self.y_max_input)

        self.xy_range_layout.addLayout(self.x_range_layout)
        self.xy_range_layout.addLayout(self.y_range_layout)

        self.layout.addLayout(self.xy_range_layout)
        
        
        # 添加弹性空间
        self.layout.addStretch()
        self.setLayout(self.layout)

        self.set_x_range()
        self.set_y_range()

    def showColorMenu(self):
        self.color_combi_menu.exec(self.color_combi_button.mapToGlobal(self.color_combi_button.rect().bottomLeft()))

    def addColorAction(self, menu, category, subcategory=None):
        if category == '单色':
            action = QAction(category, self)
            action.triggered.connect(lambda checked, c=category: self.update_combi_color(c))
        else:
            # Create a pixmap for the color combination
            pixmap = QPixmap(100, 20)  # Adjust size as needed
            painter = QPainter(pixmap)
            
            colors = color_combi_dict[category][subcategory]
            width = pixmap.width() / len(colors)
            for i, color in enumerate(colors):
                painter.fillRect(QRectF(i * width, 0, width, pixmap.height()), QColor(color))

            painter.end()

            action = QAction(pixmap, '', self)
            action.triggered.connect(lambda checked, c=category, s=subcategory: self.update_combi_color(c, s))
            
            action.setIconVisibleInMenu(True)
            
        menu.addAction(action)
    
    def update_combi_color(self, category, subcategory=None):
        self.axe_modify.change_all_color(category, subcategory)

    def set_x_range(self):
        x_min = self.x_min_input.value()
        x_max = self.x_max_input.value()
        self.axe_modify.set_x_range(x_min, x_max)

    def set_y_range(self):
        y_min = self.y_min_input.value()
        y_max = self.y_max_input.value()
        self.axe_modify.set_y_range(y_min, y_max)


class PyBottomSpineModWidget(QFrame):
    def __init__(self, axe: Axes, axe_modify: PyAxesModify):
        super().__init__()

        self.setObjectName("bottom_spine_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.axe = axe
        self.axe_modify = axe_modify

        self.layout = QVBoxLayout()

        # 设置脊柱位置
        self.spine_position_box = QGroupBox("脊柱设置")
        self.spine_position_box.setCheckable(True)
        # 连接信号槽
        self.spine_position_box.toggled.connect(self.set_spine_visible)

        self.spine_position_layout = QHBoxLayout()

        self.spine_position_input = QDoubleSpinBox()
        self.spine_position_input.setRange(0, 1)
        self.spine_position_input.setSingleStep(0.01)
        self.spine_position_input.setValue(0)
        self.spine_position_input.valueChanged.connect(self.set_bottom_spine_position)

        self.spine_label = QLabel("位置:")
        self.spine_label.setFixedWidth(40)

        self.spine_position_layout.addWidget(self.spine_label)
        self.spine_position_layout.addWidget(self.spine_position_input)

        self.spine_position_box.setLayout(self.spine_position_layout)

        self.layout.addWidget(self.spine_position_box)

        self.setLayout(self.layout)

    # 设置底脊可见性
    def set_spine_visible(self, visible):
        self.axe_modify.set_visible("bottom", visible)


    def set_bottom_spine_position(self):
        pos = self.spine_position_input.value()
        self.axe_modify.set_bottom_spine_position(pos)


class PyTopSpineModWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("top_spine_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)


class PyLeftSpineModWidget(QFrame):
    def __init__(self, axe: Axes, axe_modify: PyAxesModify):
        super().__init__()

        self.axe = axe
        self.axe_modify = axe_modify

        self.setObjectName("left_spine_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)


class PyRightSpineModWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("right_spine_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)


class PyAxeLegendModWidget(QFrame):
    def __init__(self, axe: Axes, axe_modify: PyAxesModify):
        super().__init__()
        self.axe = axe
        self.axe_modify = axe_modify

        self.setObjectName("axe_legend_mod_widget")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.layout = QVBoxLayout()

        # 下拉框选择图例位置
        self.legend_position_combobox = QComboBox()
        self.legend_position_combobox.setFixedSize(200, 30)
        self.legend_position_combobox.setFont(QFont("Times New Roman", 16))
        self.legend_position_combobox.addItems([
            "best",
            "upper right",
            "upper left",
            "lower left",
            "lower right",
            "right",
            "center left",
            "center right",
            "lower center",
            "upper center",
            "center"
        ])
        self.legend_position_combobox.setCurrentText("best")
        self.legend_position_combobox.currentTextChanged.connect(self.set_legend_position)
        # 精确选择图例位置
        self.legend_xy_layout = QHBoxLayout()
        self.legend_x_pos = QDoubleSpinBox()
        self.legend_x_pos.setRange(-1, 1)
        self.legend_x_pos.setSingleStep(0.01)
        self.legend_y_pos = QDoubleSpinBox()
        self.legend_y_pos.setRange(-1, 1)
        self.legend_y_pos.setSingleStep(0.01)

        # bbox = self.axe_modify.legend.get_window_extent().transformed(self.axe.transAxes.inverted())
        # x0, y0 = bbox.x0, bbox.y0
        # self.legend_x_pos.setValue(x0)
        # self.legend_y_pos.setValue(y0)

        self.legend_x_pos.textChanged.connect(self.set_legend_xy_position)
        self.legend_y_pos.textChanged.connect(self.set_legend_xy_position)

        x_label = QLabel("X:")
        y_label = QLabel("Y:")
        x_label.setFixedWidth(20)
        y_label.setFixedWidth(20)
        self.legend_xy_layout.addWidget(x_label)
        self.legend_xy_layout.addWidget(self.legend_x_pos)
        self.legend_xy_layout.addWidget(y_label)
        self.legend_xy_layout.addWidget(self.legend_y_pos)

        self.layout.addWidget(self.legend_position_combobox)
        self.layout.addLayout(self.legend_xy_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def set_legend_position(self):
        self.axe_modify.set_legend_position(self.legend_position_combobox.currentText())

        bbox = self.axe_modify.legend.get_window_extent().transformed(self.axe.transAxes.inverted())
        x0, y0 = bbox.x0, bbox.y0
        self.legend_x_pos.setValue(x0)
        self.legend_y_pos.setValue(y0)

    def set_legend_xy_position(self):
        pos = (self.legend_x_pos.value(), self.legend_y_pos.value())
        self.axe_modify.set_legend_position(pos)
