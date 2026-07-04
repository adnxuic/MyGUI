from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.py_chart_modify import PyCurveModify, PyScatterModify, PyPlotModify, PyInterpolateModify
from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget

from code.database.py_database import PyDatabase
from code.database.interpolate_func import interpolate_dict

import math
import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "chart_mod_style.qss")


class PyCurveModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify, color: str):
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
        self.style_layout = QVBoxLayout()

        # 线条的颜色
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.style_layout.addWidget(self.color_choice)

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

        # 图例
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)


        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def get_colorupdate_func(self):
        return self.color_choice.updateColor

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

    def color_change(self, color: str):
        self.curve_modify.update_color(color)

    def legend_change(self):
        current_legend = self.legend_input.text()
        self.curve_modify.change_legend(current_legend)


class PyPlotModWidget(QFrame):
    def __init__(self, curve_modify: PyPlotModify, x_data_name: str, y_data_name: str, color: str):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = curve_modify

        self.layout = QVBoxLayout()

        self.data_choice_widget = PyDataChoiceWidget()
        self.data_choice_widget.set_x_data(x_data_name)
        self.data_choice_widget.set_y_data(y_data_name)
        self.data_choice_widget.text_connect(self.x_data_change, self.y_data_change)

        self.layout.addWidget(self.data_choice_widget)

        # 线条的颜色
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # 图例
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def get_colorupdate_func(self):
        return self.color_choice.updateColor

    def delete_object(self):
        self.curve_modify.delete_object()

    def x_data_change(self):
        data_name = self.data_choice_widget.get_x_data()
        if not PyDatabase.has_data(data_name):
            return
        current_x_data = PyDatabase.get_data(data_name)
        # 更新x轴数据
        self.curve_modify.update_x_data(current_x_data)
        # 更新映射连接
        changed = PyDatabase.change_data_connection(self.curve_modify.current_x_data_name, data_name,
                                                    id(self.curve_modify.line), 'x')
        if not changed:
            PyDatabase.data_connect(data_name, id(self.curve_modify.line), 'x', self.curve_modify.update_x_data)
        self.curve_modify.current_x_data_name = data_name
        self.curve_modify.update_project_record(x_data_name=data_name)

    def y_data_change(self):
        data_name = self.data_choice_widget.get_y_data()
        if not PyDatabase.has_data(data_name):
            return
        current_y_data = PyDatabase.get_data(data_name)
        # 更新y轴数据
        self.curve_modify.update_y_data(current_y_data)
        # 更新映射连接
        changed = PyDatabase.change_data_connection(self.curve_modify.current_y_data_name, data_name,
                                                    id(self.curve_modify.line), 'y')
        if not changed:
            PyDatabase.data_connect(data_name, id(self.curve_modify.line), 'y', self.curve_modify.update_y_data)
        self.curve_modify.current_y_data_name = data_name
        self.curve_modify.update_project_record(y_data_name=data_name)

    def color_change(self, color: str):
        self.curve_modify.update_color(color)

    def legend_change(self):
        current_legend = self.legend_input.text()
        self.curve_modify.change_legend(current_legend)


class PyScatterModWidget(QFrame):
    def __init__(self, scatter_modify: PyScatterModify, x_data_name: str, y_data_name: str, color: str):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = scatter_modify

        self.layout = QVBoxLayout()

        self.data_choice_widget = PyDataChoiceWidget()
        self.data_choice_widget.set_x_data(x_data_name)
        self.data_choice_widget.set_y_data(y_data_name)
        self.data_choice_widget.text_connect(self.x_data_change, self.y_data_change)

        self.layout.addWidget(self.data_choice_widget)

        # 线条的颜色
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # 图例
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(scatter_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def get_colorupdate_func(self):
        return self.color_choice.updateColor

    def delete_object(self):
        self.curve_modify.delete_object()

    def x_data_change(self):
        data_name = self.data_choice_widget.get_x_data()
        if not PyDatabase.has_data(data_name):
            return
        current_x_data = PyDatabase.get_data(data_name)
        # 更新x轴数据
        self.curve_modify.update_x_data(current_x_data)
        # 更新映射连接
        changed = PyDatabase.change_data_connection(self.curve_modify.current_x_data_name, data_name,
                                                    id(self.curve_modify.scatter), 'x')
        if not changed:
            PyDatabase.data_connect(data_name, id(self.curve_modify.scatter), 'x', self.curve_modify.update_x_data)
        self.curve_modify.current_x_data_name = data_name
        self.curve_modify.update_project_record(x_data_name=data_name)

    def y_data_change(self):
        data_name = self.data_choice_widget.get_y_data()
        if not PyDatabase.has_data(data_name):
            return
        current_y_data = PyDatabase.get_data(data_name)
        # 更新y轴数据
        self.curve_modify.update_y_data(current_y_data)
        # 更新映射连接
        changed = PyDatabase.change_data_connection(self.curve_modify.current_y_data_name, data_name,
                                                    id(self.curve_modify.scatter), 'y')
        if not changed:
            PyDatabase.data_connect(data_name, id(self.curve_modify.scatter), 'y', self.curve_modify.update_y_data)
        self.curve_modify.current_y_data_name = data_name
        self.curve_modify.update_project_record(y_data_name=data_name)

    def color_change(self, color: str):
        self.curve_modify.update_color(color)

    def legend_change(self):
        current_legend = self.legend_input.text()
        self.curve_modify.change_legend(current_legend)


class PyFitMatlabModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.   curve_modify = curve_modify

        self.layout = QVBoxLayout()

        # 函数表达式
        self.expression_box = QGroupBox('Expression', self)
        self.expression_layout = QVBoxLayout()

        self.expression_input = QPlainTextEdit(self)
        # 设置是否可以编辑
        self.expression_input.setReadOnly(True)
        self.expression_input.setPlainText(curve_modify.expression)
        self.expression_input.textChanged.connect(self.expression_change)
        self.expression_layout.addWidget(self.expression_input)

        self.expression_box.setLayout(self.expression_layout)

        self.result_box = QGroupBox("Fit Result", self)
        self.result_layout = QVBoxLayout()
        self.result_model_label = QLabel("Model: -")
        self.result_formula_input = QPlainTextEdit(self)
        self.result_formula_input.setReadOnly(True)
        self.result_formula_input.setFixedHeight(55)

        self.result_coeff_table = QTableWidget(self)
        self.result_coeff_table.setColumnCount(4)
        self.result_coeff_table.setHorizontalHeaderLabels(["Coefficient", "Value", "Lower", "Upper"])
        self.result_coeff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_coeff_table.horizontalHeader().setStretchLastSection(True)

        self.result_goodness_table = QTableWidget(self)
        self.result_goodness_table.setColumnCount(2)
        self.result_goodness_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.result_goodness_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_goodness_table.horizontalHeader().setStretchLastSection(True)

        self.result_layout.addWidget(self.result_model_label)
        self.result_layout.addWidget(QLabel("Formula:"))
        self.result_layout.addWidget(self.result_formula_input)
        self.result_layout.addWidget(QLabel("Coefficients and 95% Confidence Bounds:"))
        self.result_layout.addWidget(self.result_coeff_table)
        self.result_layout.addWidget(QLabel("Goodness of Fit:"))
        self.result_layout.addWidget(self.result_goodness_table)
        self.result_box.setLayout(self.result_layout)

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
        self.layout.addWidget(self.result_box)
        self.layout.addLayout(self.x_start_layout)
        self.layout.addLayout(self.x_stop_layout)
        self.layout.addWidget(self.style_box)

        # 线条的颜色
        self.color_choice = ColorChoiceWidget(connect_signal=self.color_change)
        self.layout.addWidget(self.color_choice)

        # 图例
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def expression_change(self):
        current_expression = self.expression_input.toPlainText()
        self.curve_modify.update_expression(current_expression)

    def _format_result_number(self, value):
        if value is None:
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if math.isnan(number):
            return "NaN"
        if math.isinf(number):
            return "Inf" if number > 0 else "-Inf"
        if number != 0 and (abs(number) < 1e-4 or abs(number) >= 1e6):
            return f"{number:.4g}"
        return f"{number:.4f}"

    def _set_table_item(self, table, row, column, value):
        item = QTableWidgetItem(self._format_result_number(value))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        table.setItem(row, column, item)

    def _populate_fit_result(self, fit_result):
        self.result_model_label.setText(f"Model: {fit_result.get('fit_type', '-')}")
        self.result_formula_input.setPlainText(str(fit_result.get("formula", "")))

        coefficients = list(fit_result.get("coefficients") or [])
        self.result_coeff_table.setRowCount(len(coefficients))
        for row, coefficient in enumerate(coefficients):
            name_item = QTableWidgetItem(str(coefficient.get("name", "")))
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.result_coeff_table.setItem(row, 0, name_item)
            self._set_table_item(self.result_coeff_table, row, 1, coefficient.get("value"))
            self._set_table_item(self.result_coeff_table, row, 2, coefficient.get("lower"))
            self._set_table_item(self.result_coeff_table, row, 3, coefficient.get("upper"))

        goodness = fit_result.get("goodness") or {}
        labels = [
            ("SSE", "sse"),
            ("R Square", "rsquare"),
            ("DFE", "dfe"),
            ("Adjusted R Square", "adjrsquare"),
            ("RMSE", "rmse"),
        ]
        self.result_goodness_table.setRowCount(len(labels))
        for row, (label, key) in enumerate(labels):
            label_item = QTableWidgetItem(label)
            label_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.result_goodness_table.setItem(row, 0, label_item)
            self._set_table_item(self.result_goodness_table, row, 1, goodness.get(key))

    def update_curve(self, fit_result, *args):
        if isinstance(fit_result, dict):
            if len(args) < 2:
                raise TypeError("update_curve requires x_start and x_stop")
            x_start, x_stop = args[0], args[1]
            value_expression = fit_result.get("value_expression", "")
            show_expression = fit_result.get("show_expression", value_expression)
            self._populate_fit_result(fit_result)
        else:
            if len(args) == 3:
                show_expression, x_start, x_stop = args
            elif len(args) >= 2:
                x_start, x_stop = args[0], args[1]
                show_expression = str(fit_result)
            else:
                raise TypeError("update_curve requires x_start and x_stop")
            value_expression = str(fit_result)
            self._populate_fit_result({
                "fit_type": "-",
                "formula": show_expression,
                "coefficients": [],
                "goodness": {},
            })
        self.expression_input.setPlainText(show_expression)
        self.x_start_input.setValue(x_start)
        self.x_stop_input.setValue(x_stop)

        self.curve_modify.update_all(x_start, x_stop, value_expression)

    def x_start_change(self):
        current_x_start = self.x_start_input.value()
        self.curve_modify.update_x_start(current_x_start)

    def x_stop_change(self):
        current_x_stop = self.x_stop_input.value()
        self.curve_modify.update_x_stop(current_x_stop)

    def style_change(self):
        current_style = self.style_input.currentText()
        self.curve_modify.update_style(current_style)

    def color_change(self, color: str):
        self.curve_modify.update_color(color)

    def legend_change(self):
        current_legend = self.legend_input.text()
        self.curve_modify.change_legend(current_legend)


class PyInterpolateWidget(QFrame):
    def __init__(self, curve_modify: PyInterpolateModify, init_interpolat: str, init_k: int,
                 color: str = "#000000"):
        super().__init__()

        self.modify = curve_modify

        self.layout = QVBoxLayout()

        # 插值方式
        self.interpolat_box = QGroupBox('Interpolation')
        self.interpolat_layout = QVBoxLayout()

        self.interpolat_input = QComboBox(self)
        self.interpolat_input.addItems(interpolate_dict.keys())

        self.interpolat_layout.addWidget(self.interpolat_input)
        # 添加弹性空间
        self.interpolat_layout.addStretch()

        # 阶数选择
        self.k_widget = QFrame()
        self.k_input = QSpinBox()
        self.k_input.setRange(1, 5)
        self.k_input.setValue(init_k)
        self.k_input.valueChanged.connect(self.interpolat_change)

        self.k_layout = QHBoxLayout()
        self.k_layout.addWidget(QLabel('阶数k:'))
        self.k_layout.addWidget(self.k_input)
        self.k_widget.setLayout(self.k_layout)

        # 如果不是选择B样条插值,则不显示阶数选择
        self.is_k_widget_added = False
        self.interpolat_input.currentTextChanged.connect(self.change_method)
        self.interpolat_input.setCurrentText(init_interpolat)
        self.interpolat_input.currentTextChanged.connect(self.interpolat_change)

        self.interpolat_box.setLayout(self.interpolat_layout)

        self.layout.addWidget(self.interpolat_box)

        # 线条的颜色
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # 图例
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # 添加弹性空间
        self.layout.addStretch()

        self.setLayout(self.layout)

    def get_colorupdate_func(self):
        return self.color_choice.updateColor

    def delete_object(self):
        self.modify.delete_object()

    def change_method(self):
        # 获取当前选择的插值方法
        current_method = self.interpolat_input.currentText()

        # 如果选择的是B样条插值且阶数选择不存在，则添加阶数选择
        # 再倒数第二行添加阶数选择
        if current_method == "B样条插值" and self.is_k_widget_added is False:
            self.interpolat_layout.insertWidget(self.interpolat_layout.count() - 1, self.k_widget)
            self.is_k_widget_added = True

        # 如果选择的不是B样条插值且阶数选择存在，则删除阶数选择
        elif current_method != "B样条插值" and self.is_k_widget_added is True:
            self.interpolat_layout.itemAt(self.interpolat_layout.count() - 2).widget().setParent(None)
            self.is_k_widget_added = False

    def interpolat_change(self):
        current_interpolat = self.interpolat_input.currentText()
        k = self.k_input.value()
        self.modify.update_interpolate(current_interpolat, k)

    def color_change(self, color: str):
        self.modify.update_color(color)

    def legend_change(self):
        current_legend = self.legend_input.text()
        self.modify.change_legend(current_legend)
