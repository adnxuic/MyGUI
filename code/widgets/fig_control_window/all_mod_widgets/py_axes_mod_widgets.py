from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.py_axes_modify import PyAxesModify

from matplotlib.axes import Axes

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "axes_mod_style.qss")


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
