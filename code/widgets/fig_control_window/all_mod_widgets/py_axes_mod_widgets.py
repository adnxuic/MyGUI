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
        self.color_combi_button.clicked.connect(self.show_color_menu)

        self.color_combi_menu = QMenu()
        for category, subcategories in color_combi_dict.items():
            if isinstance(subcategories, dict):
                submenu = self.color_combi_menu.addMenu(category)
                for subcategory in subcategories.keys():
                    self.add_color_action(submenu, category, subcategory)
            else:
                self.add_color_action(self.color_combi_menu, category)

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

        # 设置xy轴标题
        # xy轴标题框
        self.xy_title_box = QGroupBox("标题设置")
        self.xy_title_box.setCheckable(False)
        self.xy_title_layout = QVBoxLayout()

        #设置xy轴标题字体
        # 下拉框选择字体
        self.font_combobox = QComboBox()
        self.font_combobox.setFont(QFont("Times New Roman", 16))
        self.font_combobox.addItems([
            "Times New Roman",
            "SimSun",])
        self.font_combobox.setCurrentText("Times New Roman")
        self.font_combobox.currentTextChanged.connect(self.set_xy_font)
        self.xy_title_layout.addWidget(self.font_combobox)

        # 设置xy轴标题字体大小
        self.xy_font_size_input = QSpinBox()
        self.xy_font_size_input.setRange(1, 100)
        self.xy_font_size_input.setValue(12)
        self.xy_font_size_input.setSingleStep(1)
        self.xy_font_size_input.valueChanged.connect(self.set_xy_font_size)
        self.xy_title_layout.addWidget(self.xy_font_size_input)

        # 添加xy轴的名称
        self.xy_name_layout = QHBoxLayout()

        self.x_name_input = QLineEdit()
        self.x_name_input.setPlaceholderText("X轴名称")
        self.x_name_input.textChanged.connect(self.set_x_name)
        self.y_name_input = QLineEdit()
        self.y_name_input.setPlaceholderText("Y轴名称")
        self.y_name_input.textChanged.connect(self.set_y_name)

        self.xy_name_layout.addWidget(self.x_name_input)
        self.xy_name_layout.addWidget(self.y_name_input)
        self.xy_title_layout.addLayout(self.xy_name_layout)

        # xy轴标题位置
        self.xy_title_position_layout = QVBoxLayout()

        self.x_title_position_layout = QHBoxLayout()
        self.y_title_position_layout = QHBoxLayout()

        self.xy_title_position_layout.addWidget(QLabel("X轴标题位置:"))
        self.x_title_xposition_input = QDoubleSpinBox()
        self.x_title_xposition_input.setSingleStep(0.01)
        self.x_title_xposition_input.valueChanged.connect(self.set_xy_title_xposition)
        self.x_title_position_layout.addWidget(self.x_title_xposition_input)

        self.x_title_yposition_input = QDoubleSpinBox()
        self.x_title_yposition_input.setSingleStep(0.01)
        self.x_title_yposition_input.valueChanged.connect(self.set_xy_title_xposition)
        self.x_title_position_layout.addWidget(self.x_title_yposition_input)
        self.xy_title_position_layout.addLayout(self.x_title_position_layout)

        self.xy_title_position_layout.addWidget(QLabel("Y轴标题位置:"))
        self.y_title_xposition_input = QDoubleSpinBox()
        self.y_title_xposition_input.setSingleStep(0.01)
        self.y_title_xposition_input.valueChanged.connect(self.set_xy_title_xposition)
        self.y_title_position_layout.addWidget(self.y_title_xposition_input)

        self.y_title_yposition_input = QDoubleSpinBox()
        self.y_title_yposition_input.setSingleStep(0.01)
        self.y_title_yposition_input.valueChanged.connect(self.set_xy_title_xposition)
        self.y_title_position_layout.addWidget(self.y_title_yposition_input)
        self.xy_title_position_layout.addLayout(self.y_title_position_layout)

        self.xy_title_layout.addLayout(self.xy_title_position_layout)

        self.xy_title_box.setLayout(self.xy_title_layout)
        self.layout.addWidget(self.xy_title_box)
        
        # 添加弹性空间
        self.layout.addStretch()
        self.setLayout(self.layout)

        # self.set_x_range()
        # self.set_y_range()


    def show_color_menu(self):
        self.color_combi_menu.exec(self.color_combi_button.mapToGlobal(self.color_combi_button.rect().bottomLeft()))

    def add_color_action(self, menu, category, subcategory=None):
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

    def set_xy_font(self):
        font = self.font_combobox.currentText()
        self.axe_modify.set_xylabel_font(font)

    def set_x_name(self):
        name = self.x_name_input.text()
        self.axe_modify.set_x_label(name)

    def set_y_name(self):
        name = self.y_name_input.text()
        self.axe_modify.set_y_label(name)
        self.update_xy_title_position()

    def set_xy_font_size(self):
        size = self.xy_font_size_input.value()
        self.axe_modify.set_xylabel_fontsize(size)
        self.update_xy_title_position()

    def set_xy_title_xposition(self):
        x_xpos = self.x_title_xposition_input.value()
        x_ypos = self.x_title_yposition_input.value()
        y_xpos = self.y_title_xposition_input.value()
        y_ypos = self.y_title_yposition_input.value()
        self.axe_modify.set_xy_title_position(x_xpos, x_ypos, y_xpos, y_ypos)

    def update_xy_title_position(self):
        x_pos = self.axe.xaxis.get_label().get_position()
        y_pos = self.axe.yaxis.get_label().get_position()

        # self.x_title_xposition_input.setValue(x_pos[0])
        # self.x_title_yposition_input.setValue(x_pos[1])
        # self.y_title_xposition_input.setValue(y_pos[0])
        # self.y_title_yposition_input.setValue(y_pos[1])
        print(x_pos, y_pos)


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
