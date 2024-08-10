from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.py_chart_modify import PyCurveModify, PyScatterModify, PyPlotModify

from code.database.py_database import databases, PyDatabase

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "chart_mod_style.qss")


class PyCurveModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = curve_modify

        self.layout = QVBoxLayout()

        # 函数表达式
        self.expression_box = QGroupBox('Expression', self)
        self.expression_box.setFixedSize(180, 80)
        self.expression_layout = QVBoxLayout()

        self.expression_input = QLineEdit(self)
        self.expression_input.setText(curve_modify.expression)
        self.expression_input.textChanged.connect(self.expression_change)
        self.expression_layout.addWidget(self.expression_input)

        self.expression_box.setLayout(self.expression_layout)

        # 添加x轴起始点和终止点
        self.x_start_layout = QHBoxLayout()
        self.x_stop_layout = QHBoxLayout()
        self.x_start_input = QDoubleSpinBox(self)
        self.x_start_input.setFixedWidth(120)
        self.x_start_input.setRange(float('-inf'), float('inf'))
        self.x_start_input.setSingleStep(1)
        self.x_start_input.setValue(curve_modify.x_start)
        self.x_start_input.valueChanged.connect(self.x_start_change)
        self.x_stop_input = QDoubleSpinBox(self)
        self.x_stop_input.setFixedWidth(120)
        self.x_stop_input.setRange(float('-inf'), float('inf'))
        self.x_stop_input.setSingleStep(1)
        self.x_stop_input.setValue(curve_modify.x_stop)
        self.x_stop_input.valueChanged.connect(self.x_stop_change)

        self.x_start_layout.addWidget(QLabel('X Start:'))
        self.x_start_layout.addWidget(self.x_start_input)
        self.x_start_layout.addStretch()
        self.x_stop_layout.addWidget(QLabel('X Stop:'))
        self.x_stop_layout.addWidget(self.x_stop_input)
        self.x_stop_layout.addStretch()

        # 线条的样式
        self.style_box = QGroupBox('Style', self)
        self.style_box.setFixedSize(180, 80)
        self.style_layout = QVBoxLayout()

        # 线条的形状
        self.style_input = QComboBox(self)
        self.style_input.addItem('solid')
        self.style_input.addItem('dashed')
        self.style_input.addItem('dashdot')
        self.style_input.addItem('dotted')
        self.style_input.setCurrentText(curve_modify.line.get_linestyle())
        self.style_input.currentTextChanged.connect(self.style_change)

        self.style_layout.addWidget(self.style_input)
        self.style_box.setLayout(self.style_layout)

        self.layout.addWidget(self.expression_box)
        self.layout.addLayout(self.x_start_layout)
        self.layout.addLayout(self.x_stop_layout)
        self.layout.addWidget(self.style_box)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def expression_change(self):
        current_expression = self.expression_input.text()
        self.curve_modify.update_expression(current_expression)

    def x_start_change(self):
        current_x_start = self.x_start_input.value()
        self.curve_modify.update_x_start(current_x_start)

    def x_stop_change(self):
        current_x_stop = self.x_stop_input.value()
        self.curve_modify.update_x_stop(current_x_stop)

    def style_change(self):
        current_style = self.style_input.currentText()
        self.curve_modify.update_style(current_style)


class PyPlotModWidget(QFrame):
    def __init__(self, curve_modify: PyPlotModify, x_data_name: str, y_data_name: str):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = curve_modify

        self.layout = QVBoxLayout()

        self.databox = QGroupBox('Data', self)
        self.databox.setFixedSize(200, 80)
        self.databox_layout = QVBoxLayout()

        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        for key1, value1 in databases.items():
            for key2, value2 in value1.items():
                for key3, value3 in value2.data.items():
                    self.x_data_input.addItem(f"{key1}/{key2}/{key3}")
                    self.y_data_input.addItem(f"{key1}/{key2}/{key3}")

        self.x_data_input.setCurrentText(x_data_name)
        self.y_data_input.setCurrentText(y_data_name)

        self.x_data_input.currentTextChanged.connect(self.x_data_change)
        self.y_data_input.currentTextChanged.connect(self.y_data_change)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.databox_layout.addLayout(self.x_data_layout)
        self.databox_layout.addLayout(self.y_data_layout)

        self.databox.setLayout(self.databox_layout)

        self.setLayout(self.layout)

    def x_data_change(self):
        current_x_data = PyDatabase.get_data(self.x_data_input.currentText())
        # 更新x轴数据
        self.curve_modify.update_x_data(current_x_data)
        # 更新映射连接
        PyDatabase.change_data_connection(self.curve_modify.current_x_data_name, self.x_data_input.currentText(),
                                          id(self.curve_modify.line), 'x')
        self.curve_modify.current_x_data_name = self.x_data_input.currentText()

    def y_data_change(self):
        current_y_data = PyDatabase.get_data(self.y_data_input.currentText())
        # 更新y轴数据
        self.curve_modify.update_y_data(current_y_data)
        # 更新映射连接
        PyDatabase.change_data_connection(self.curve_modify.current_y_data_name, self.y_data_input.currentText(),
                                          id(self.curve_modify.line), 'y')
        self.curve_modify.current_y_data_name = self.y_data_input.currentText()


class PyScatterModWidget(QFrame):
    def __init__(self, scatter_modify: PyScatterModify, x_data_name: str, y_data_name: str):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = scatter_modify

        self.layout = QVBoxLayout()

        self.databox = QGroupBox('Data', self)
        self.databox.setFixedSize(200, 80)
        self.databox_layout = QVBoxLayout()

        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        for key1, value1 in databases.items():
            for key2, value2 in value1.items():
                for key3, value3 in value2.data.items():
                    self.x_data_input.addItem(f"{key1}/{key2}/{key3}")
                    self.y_data_input.addItem(f"{key1}/{key2}/{key3}")

        self.x_data_input.setCurrentText(x_data_name)
        self.y_data_input.setCurrentText(y_data_name)

        self.x_data_input.currentTextChanged.connect(self.x_data_change)
        self.y_data_input.currentTextChanged.connect(self.y_data_change)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.databox_layout.addLayout(self.x_data_layout)
        self.databox_layout.addLayout(self.y_data_layout)

        self.databox.setLayout(self.databox_layout)

        self.setLayout(self.layout)

    def x_data_change(self):
        current_x_data = PyDatabase.get_data(self.x_data_input.currentText())
        # 更新x轴数据
        self.curve_modify.update_x_data(current_x_data)
        # 更新映射连接
        PyDatabase.change_data_connection(self.curve_modify.current_x_data_name, self.x_data_input.currentText(),
                                          id(self.curve_modify.scatter), 'x')
        self.curve_modify.current_x_data_name = self.x_data_input.currentText()

    def y_data_change(self):
        current_y_data = PyDatabase.get_data(self.y_data_input.currentText())
        # 更新y轴数据
        self.curve_modify.update_y_data(current_y_data)
        # 更新映射连接
        PyDatabase.change_data_connection(self.curve_modify.current_y_data_name, self.y_data_input.currentText(),
                                          id(self.curve_modify.scatter), 'y')
        self.curve_modify.current_y_data_name = self.y_data_input.currentText()
