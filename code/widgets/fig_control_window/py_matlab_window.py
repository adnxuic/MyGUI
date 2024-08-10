from Qt_core import *

from code.widgets.qss_func import qss_loader

from code.database.py_matlab_fit import fit_type
from code.database.matlab_func.get_func.get_func_exp import get_func_exp

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyMatlabWindow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setObjectName("matlab_window")

        qss_path = os.path.join(current_path, "style.qss")
        self.setStyleSheet(qss_loader(qss_path))

        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 数据选择
        self.data_selection = QGroupBox("Data Selection")
        self.data_selection_layout = QVBoxLayout()
        self.data_selection.setLayout(self.data_selection_layout)

        self.x_layout = QHBoxLayout()
        self.x_data = QComboBox()
        self.x_data.setFixedWidth(150)
        self.x_layout.addWidget(QLabel("X Data:"))
        self.x_layout.addWidget(self.x_data)

        self.y_layout = QHBoxLayout()
        self.y_data = QComboBox()
        self.y_data.setFixedWidth(150)
        self.y_layout.addWidget(QLabel("Y Data:"))
        self.y_layout.addWidget(self.y_data)

        self.data_selection_layout.addLayout(self.x_layout)
        self.data_selection_layout.addLayout(self.y_layout)

        self.layout.addWidget(self.data_selection)


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
        self.fit_type_window = PyPolyFitWindow()
        self.layout.addWidget(self.fit_type_window)

        self.setLayout(self.layout)

    def fit_type_change(self, text):
        # 如果layout中有子控件，就删除
        if self.layout.count() == 3:
            item = self.layout.takeAt(2)
            item.widget().deleteLater()
        # 添加新的控件
        if text == 'poly':
            self.fit_type_window = PyPolyFitWindow()
            self.layout.addWidget(self.fit_type_window)


class PyPolyFitWindow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        # self.setObjectName("poly_fit_window")
        #
        # qss_path = os.path.join(current_path, "style.qss")
        # self.setStyleSheet(qss_loader(qss_path))

        self.layout = QVBoxLayout()

        # 拟合选项
        self.fit_option = QGroupBox("Fit Option")

        self.fit_option_layout = QVBoxLayout()
        self.fit_option_layout.setSpacing(0)
        self.fit_option_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_option.setLayout(self.fit_option_layout)

        # 阶数
        self.order_layout = QHBoxLayout()
        self.order_input = QComboBox()
        items_list = fit_type['poly']
        self.order_input.addItems(items_list)
        self.order_layout.addWidget(QLabel("Order:"))
        self.order_layout.addWidget(self.order_input)

        # 函数表达式
        self.expression_input = QPlainTextEdit()
        # 设置默认值和不可编辑
        self.expression_input.setPlainText(get_func_exp(self.order_input.currentText()))
        self.expression_input.setReadOnly(True)

        # 连接不同的表达式
        self.order_input.currentTextChanged.connect(self.expression_change)

        self.fit_option_layout.addLayout(self.order_layout)
        self.fit_option_layout.addWidget(QLabel("Expression:"))
        self.fit_option_layout.addWidget(self.expression_input)

        self.layout.addWidget(self.fit_option)
        self.setLayout(self.layout)

    def expression_change(self, text):
        self.expression_input.setPlainText(get_func_exp(text))







