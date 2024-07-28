from Qt_core import *

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow
from code.widgets import qss_func

from code.database.py_database import databases, PyDatabase

import os
from typing import cast

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


# 曲线创建对话框
class PyCurveDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window=None):
        super().__init__()
        self.setObjectName("chart_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/curve.svg"))

        self.figure_window: PyFigureWindow = figure_window

        self.layout = QVBoxLayout()

        # 输入函数表达式
        self.expression_label = QLabel("函数表达式")
        self.expression_edit = QLineEdit()
        self.layout.addWidget(self.expression_label)
        self.layout.addWidget(self.expression_edit)

        # 选择线条样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # 选择颜色和颜色预览
        self.color_layout = QHBoxLayout()
        self.color_input = QPushButton('Choose Color', self)
        self.color_input.clicked.connect(self.choose_color)
        self.color_display = QFrame(self)
        self.color_display.setFixedSize(20, 20)
        self.color_display.setStyleSheet("background-color: #000000")  # 初始颜色为黑色
        self.layout.addWidget(QLabel('Color:'))
        self.color_layout.addWidget(self.color_display)
        self.color_layout.addWidget(self.color_input)
        self.layout.addLayout(self.color_layout)
        self.selected_color = '#000000'  # 默认黑色

        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # 确定和取消按钮
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.setLayout(self.layout)

    def choose_color(self):
        color = QColorDialog.getColor(self.selected_color)
        if color.isValid():
            self.selected_color = color.name()
            self.color_display.setStyleSheet(f"background-color: {self.selected_color}")

    def accept(self):
        self.figure_window.current_canva.add_curve(func_test=self.expression_edit.text(),
                                                   style=self.style_input.currentText(),
                                                   color=self.selected_color,
                                                   label=self.label_input.text())
        super().accept()

    def reject(self):
        super().reject()


# 折线图对话框
class PyPlotDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window=None):
        super().__init__()
        self.setObjectName("chart_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/plot.svg"))

        self.figure_window: PyFigureWindow = figure_window

        self.layout = QVBoxLayout()

        # 选择数据
        self.data_input = QComboBox(self)
        for key1, value1 in databases.items():
            for key2, value2 in value1.items():
                for key3, value3 in value2.data.items():
                    self.data_input.addItem(f"{key1}/{key2}/{key3}")

        self.layout.addWidget(QLabel('Data:'))
        self.layout.addWidget(self.data_input)


        # 选择线条样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # 确定和取消按钮
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.setLayout(self.layout)

    def accept(self):
        super().accept()

    def reject(self):
        super().reject()


class PyScatterDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window=None):
        super().__init__()
        self.setObjectName("chart_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/scatter.svg"))

        self.figure_window: PyFigureWindow = figure_window

        self.layout = QVBoxLayout()

        # 选择数据
        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        for key1, value1 in databases.items():
            for key2, value2 in value1.items():
                for key3, value3 in value2.data.items():
                    self.x_data_input.addItem(f"{key1}/{key2}/{key3}")
                    self.y_data_input.addItem(f"{key1}/{key2}/{key3}")

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.layout.addLayout(self.x_data_layout)
        self.layout.addLayout(self.y_data_layout)

        # 选择散点样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['o', 's', 'D', 'x', '+'])
        self.layout.addWidget(QLabel('Marker Style:'))
        self.layout.addWidget(self.style_input)


        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # 确定和取消按钮
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.setLayout(self.layout)

    def accept(self):
        super().accept()

    def reject(self):
        super().reject()


chart_dialog_dict = {
    'curve': PyCurveDialog,
    'plot': PyPlotDialog,
    'scatter': PyScatterDialog
}
