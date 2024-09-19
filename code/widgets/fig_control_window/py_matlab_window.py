from Qt_core import *

from code.widgets.qss_func import qss_loader
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyFitMatlabModWidget
from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget

from code.database.py_database import databases, PyDatabase
from code.database.py_matlab_fit import fit_type
from code.database.matlab_func.get_func.get_func_exp import get_func_exp

import numpy as np

from typing import Optional
import os
import importlib

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyMatlabWindow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("matlab_window")

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        self.connect_widget: Optional[PyFitMatlabModWidget] = None

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 检测是否能连接matlab
        self.matlab_isconnect = QPushButton("isConnect Matlab")
        self.matlab_isconnect.setFixedWidth(150)
        self.matlab_isconnect.setFixedHeight(30)
        self.matlab_isconnect.clicked.connect(self.matlab_isconnect_click)
        self.layout.addWidget(self.matlab_isconnect)

        # 实现matalb的连接的按钮，连接之后才有后面的界面生成
        self.matlab_connect = QPushButton("Connect Matlab")
        self.matlab_connect.setFixedWidth(150)
        self.matlab_connect.setFixedHeight(30)
        self.matlab_connect.clicked.connect(self.matlab_connect_click)
        self.layout.addWidget(self.matlab_connect)

        self.setLayout(self.layout)

    def matlab_isconnect_click(self):
        try:
            importlib.import_module('matlab')
            # 弹出对话框，提示能够连接matlab
            QMessageBox.information(self, "Connect Matlab", "Matlab can be linked!")
        except ImportError:
            # 弹出对话框，提示不能连接matlab
            QMessageBox.warning(self, "Connect Matlab", "Matlab can't be linked!")

    def matlab_connect_click(self):
        try :
            from code.database.matlab_func.curve_fitting.matlab_fitting import matlab_fitting
            self.init()
        except ImportError:
            # 弹出对话框，提示不能连接matlab
            QMessageBox.warning(self, "Connect Matlab", "Matlab can't be linked!")

    def init(self):

        # 数据选择
        self.data_choice_widget = PyDataChoiceWidget()
        self.layout.addWidget(self.data_choice_widget)

        # 拟合类型
        self.fit_type = QGroupBox("Fit Type")
        self.fit_type_layout = QVBoxLayout()
        self.fit_type.setLayout(self.fit_type_layout)

        # 选择拟合类型
        self.fit_type_input = QComboBox()
        self.fit_type_input.setFixedWidth(150)
        self.fit_type_input.addItems(fit_type.keys())

        # 连接不同的布局
        self.fit_type_input.currentTextChanged.connect(self.fit_type_change)
        self.fit_type_layout.addWidget(self.fit_type_input)
        self.layout.addWidget(self.fit_type)

        # 默认布局为poly
        self.fit_type_window = PyFitWindow()
        self.layout.addWidget(self.fit_type_window)

        # 启动拟合按钮
        self.fit_button = QPushButton("Fit")
        self.fit_button.setFixedWidth(150)
        self.fit_button.setFixedHeight(30)
        self.fit_button.clicked.connect(self.fit_curve)
        self.layout.addWidget(self.fit_button)

    def set_connect_widget(self, connect_widget: PyFitMatlabModWidget):
        self.connect_widget = connect_widget

    def fit_type_change(self, text):
        # 删除旧的 fit_type_window
        self.layout.removeWidget(self.fit_type_window)
        self.fit_type_window.deleteLater()  # 确保旧的窗口被正确删除

        # 更新为新的 fit_type_window
        self.fit_type_window = PyFitWindow(fit_type_name=text)
        self.layout.insertWidget(self.layout.count() - 1, self.fit_type_window)  # 插入到倒数第二个位置

    def fit_curve(self):

        x_data = PyDatabase.get_data(self.data_choice_widget.get_x_data())
        y_data = PyDatabase.get_data(self.data_choice_widget.get_y_data())

        x_max = max(x_data)
        x_min = min(x_data)

        value_exp, show_exp = self.fit_type_window.fit_curve(x_data, y_data)

        self.connect_widget.update_curve(value_exp, show_exp, x_min, x_max)


class PyFitWindow(QFrame):
    def __init__(self, parent=None, fit_type_name='poly'):
        super().__init__(parent)

        self.setMouseTracking(True)
        # self.setObjectName("poly_fit_window")
        #
        # qss_path = os.path.join(current_path, "style.qss")
        # self.setStyleSheet(qss_loader(qss_path))

        self.connect_widget: Optional[PyFitMatlabModWidget] = None

        self.layout = QVBoxLayout()

        self.fit_type = fit_type_name

        # 拟合选项
        self.fit_option = QGroupBox("Fit Option")

        self.fit_option_layout = QVBoxLayout()
        self.fit_option_layout.setSpacing(0)
        self.fit_option_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_option.setLayout(self.fit_option_layout)

        # 阶数
        self.order_layout = QHBoxLayout()
        self.order_input = QComboBox()
        items_list = fit_type[fit_type_name]
        self.order_input.addItems(items_list)
        self.order_layout.addWidget(QLabel("Order:"))
        self.order_layout.addWidget(self.order_input)

        # 获取函数表达式和系数
        self.func_exp, self.func_coefs = get_func_exp(self.order_input.currentText())
        # 函数表达式
        self.expression_input = QPlainTextEdit()
        # 设置默认值和不可编辑
        self.expression_input.setPlainText(self.func_exp)
        self.expression_input.setReadOnly(True)

        # 连接不同的表达式
        self.order_input.currentTextChanged.connect(self.expression_change)

        self.fit_option_layout.addLayout(self.order_layout)
        self.fit_option_layout.addWidget(QLabel("Expression:"))
        self.fit_option_layout.addWidget(self.expression_input)

        # 高级选项
        self.advanced_option = QGroupBox("Advanced Option")
        self.advanced_option_layout = QVBoxLayout()
        self.advanced_option.setLayout(self.advanced_option_layout)
        # 设置是否显示高级选项，默认不显示
        self.advanced_option.setCheckable(True)
        self.advanced_option.setChecked(False)

        # 系数的上下限
        self.coeff_up_limit = []
        self.coeff_down_limit = []

        self.coefficient_table = QTableWidget()

        if fit_type_name == 'poly' or fit_type_name == 'log':
            self.coefficient_table.setColumnCount(3)
            self.coefficient_table.setHorizontalHeaderLabels(['系数', '上限', '下限'])
        else:
            self.start_point = []
            self.coefficient_table.setColumnCount(4)
            self.coefficient_table.setHorizontalHeaderLabels(['系数', '上限', '下限', '起点'])

        # 设置系数名称，且不可编辑
        self.coefficient_table.setRowCount(len(self.func_coefs))
        for i, coef in enumerate(self.func_coefs):
            self.coefficient_table.setItem(i, 0, QTableWidgetItem(coef))
            self.coefficient_table.item(i, 0).setFlags(Qt.ItemIsEnabled)

        # 上下限设置为正负无穷, 起点设置为[0,1]随机数
        for i in range(len(self.func_coefs)):
            self.coefficient_table.setItem(i, 1, QTableWidgetItem('inf'))
            self.coefficient_table.setItem(i, 2, QTableWidgetItem('-inf'))

            if fit_type_name != 'poly' and fit_type_name != 'log':
                num = np.random.rand(1)
                # 展示前4位
                self.coefficient_table.setItem(i, 3, QTableWidgetItem(str(num[0])[:4]))

        self.advanced_option_layout.addWidget(self.coefficient_table)

        self.layout.addWidget(self.fit_option)
        self.layout.addWidget(self.advanced_option)
        self.setLayout(self.layout)


    def expression_change(self, text):
        self.func_exp, self.func_coefs = get_func_exp(text)
        # 设置表达式
        self.expression_input.setPlainText(self.func_exp)
        # 设置系数
        self.coefficient_table.setRowCount(len(self.func_coefs))
        for i, coef in enumerate(self.func_coefs):
            self.coefficient_table.setItem(i, 0, QTableWidgetItem(coef))
            self.coefficient_table.item(i, 0).setFlags(Qt.ItemIsEnabled)
        # 上下限设置为正负无穷
        for i in range(len(self.func_coefs)):
            self.coefficient_table.setItem(i, 1, QTableWidgetItem('inf'))
            self.coefficient_table.setItem(i, 2, QTableWidgetItem('-inf'))

            if self.fit_type != 'poly' and self.fit_type != 'log':
                num = np.random.rand(1)
                # 展示前4位
                self.coefficient_table.setItem(i, 3, QTableWidgetItem(str(num[0])[:4]))

    # 获得上下限
    def get_coef_limit(self):
        # 清空上下限
        self.coeff_up_limit.clear()
        self.coeff_down_limit.clear()

        for i in range(self.coefficient_table.rowCount()):
            up = self.coefficient_table.item(i, 1).text()
            down = self.coefficient_table.item(i, 2).text()
            self.coeff_up_limit.append(float(up))
            self.coeff_down_limit.append(float(down))

        if self.fit_type != 'poly' and self.fit_type != 'log':
            for i in range(self.coefficient_table.rowCount()):
                start = self.coefficient_table.item(i, 3).text()
                self.start_point.append(float(start))

    def fit_curve(self, x, y):
        from code.database.matlab_func.curve_fitting.matlab_fitting import matlab_fitting
        '''
        拟合曲线
        :param x:
        :param y:
        :return: exp的matlab表达式
        '''

        if self.advanced_option.isChecked():
            isdefault = False
            self.get_coef_limit()
        else:
            isdefault = True

        # if self.fit_type != 'poly' and self.fit_type != 'log':
        #     print(self.start_point)

        fit_type_order = self.order_input.currentText()

        value_exp, show_exp = matlab_fitting(x, y, fit_type_order, isdefault)

        return value_exp, show_exp







