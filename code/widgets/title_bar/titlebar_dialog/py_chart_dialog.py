from Qt_core import *

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from code.widgets import qss_func

from code.database.py_database import databases, PyDatabase
from code.database.interpolate_func import interpolate_dict

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


# 曲线创建对话框
class PyCurveDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None):
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
        self.expression_edit.setText("x")
        # 函数表达式变化时，图例标签也随之变化
        self.expression_edit.textChanged.connect(lambda: self.label_input.setText(self.expression_edit.text()))
        self.layout.addWidget(self.expression_label)
        self.layout.addWidget(self.expression_edit)

        # 输入x的范围
        self.x_range_label = QLabel("x的范围")
        self.x_range_layout = QHBoxLayout()
        self.x_start_input = QDoubleSpinBox(self)
        self.x_start_input.setValue(0)
        self.x_stop_input = QDoubleSpinBox(self)
        self.x_stop_input.setValue(100)
        # 设置上下限为无穷大
        self.x_start_input.setRange(float('-inf'), float('inf'))
        self.x_stop_input.setRange(float('-inf'), float('inf'))

        self.x_range_layout.addWidget(self.x_start_input)
        self.x_range_layout.addWidget(self.x_stop_input)
        self.layout.addWidget(self.x_range_label)
        self.layout.addLayout(self.x_range_layout)

        # 选择线条样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # 选择颜色和颜色预览
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.label_input.setText('x')
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
        # 如果current_canva为空，弹出警告
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        self.figure_window.current_canva.add_curve(func_text=self.expression_edit.text(),
                                                   x_start=self.x_start_input.value(),
                                                   x_stop=self.x_stop_input.value(),
                                                   style=self.style_input.currentText(),
                                                   color=self.color_input.get_color(),
                                                   label=self.label_input.text())
        super().accept()

    def reject(self):
        super().reject()


# 折线图对话框
class PyPlotDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None):
        super().__init__()
        self.setObjectName("chart_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/plot.svg"))

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

        # 选择大小
        self.size_input = QDoubleSpinBox(self)
        self.size_input.setRange(0.1, 10)
        self.size_input.setSingleStep(0.1)
        self.size_input.setValue(2)
        self.layout.addWidget(QLabel('Size:'))
        self.layout.addWidget(self.size_input)

        # 选择颜色和颜色预览
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # 选择线条样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.label_input.setText('plot')
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
        # 如果current_canva为空，弹出警告
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data = PyDatabase.get_data(self.x_data_input.currentText())
        y_data = PyDatabase.get_data(self.y_data_input.currentText())

        # 如果x_data和y_data长度不一致，弹出警告
        if len(x_data) != len(y_data):
            QMessageBox.warning(self, 'Warning', 'X Data and Y Data must have the same length!')
            return

        self.figure_window.current_canva.add_plot(x=x_data, y=y_data,
                                                  style=self.style_input.currentText(),
                                                  size=self.size_input.value(),
                                                  color=self.color_input.get_color(),
                                                  label=self.label_input.text(),
                                                  x_data_name=self.x_data_input.currentText(),
                                                  y_data_name=self.y_data_input.currentText())

        super().accept()

    def reject(self):
        super().reject()


# 散点图对话框
class PyScatterDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None):
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

        # 选择大小
        self.size_input = QSpinBox(self)
        self.size_input.setRange(0, 100)
        self.size_input.setValue(20)
        self.layout.addWidget(QLabel('Size:'))
        self.layout.addWidget(self.size_input)

        # 选择颜色和颜色预览
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # 选择散点样式
        self.style_input = QComboBox(self)
        self.style_input.addItems(['o', 's', 'D', 'x', '+'])
        self.layout.addWidget(QLabel('Marker Style:'))
        self.layout.addWidget(self.style_input)

        # 输入图例标签
        self.label_input = QLineEdit(self)
        self.label_input.setText('scatter')
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
        # 如果current_canva为空，弹出警告
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data = PyDatabase.get_data(self.x_data_input.currentText())
        y_data = PyDatabase.get_data(self.y_data_input.currentText())

        # 如果x_data和y_data长度不一致，弹出警告
        if len(x_data) != len(y_data):
            QMessageBox.warning(self, 'Warning', 'X Data and Y Data must have the same length!')
            return

        self.figure_window.current_canva.add_scatter(x=x_data, y=y_data,
                                                     size=self.size_input.value(),
                                                     color=self.color_input.get_color(),
                                                     marker=self.style_input.currentText(),
                                                     label=self.label_input.text(),
                                                     x_data_name=self.x_data_input.currentText(),
                                                     y_data_name=self.y_data_input.currentText())

        super().accept()

    def reject(self):
        super().reject()


class PyFitDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None):
        super().__init__()
        self.setObjectName("fit_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/fit.svg"))

        self.figure_window: PyFigureWindow = figure_window

        self.layout = QVBoxLayout()

        # 选择拟合的引擎：Python或Matlab
        self.engine_layout = QHBoxLayout()
        self.engine_label = QLabel("Engine:")
        self.python_button = QRadioButton("Python")
        self.matlab_button = QRadioButton("Matlab")
        self.python_button.setChecked(True)

        self.engine_layout.addWidget(self.python_button)
        self.engine_layout.addWidget(self.matlab_button)

        self.layout.addWidget(self.engine_label)
        self.layout.addLayout(self.engine_layout)

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
        # 如果选择matlab引擎
        if self.matlab_button.isChecked():
            self.figure_window.current_canva.add_fit_curve('matlab', [], [], 'r', 'fit')
            super().accept()
            return

        # 如果current_canva为空，弹出警告
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data = PyDatabase.get_data(self.x_data_input.currentText())
        y_data = PyDatabase.get_data(self.y_data_input.currentText())

        # 如果x_data和y_data长度不一致，弹出警告
        if len(x_data) != len(y_data):
            QMessageBox.warning(self, 'Warning', 'X Data and Y Data must have the same length!')
            return

        super().accept()

    def reject(self):
        super().reject()


class PyInterpolationDialog(QDialog):
    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None):
        super().__init__()
        self.setObjectName("interpolation_dialog")
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon("pictures/icons/chart_images/interpolation.svg"))

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

        # 选择插值方法
        self.method_input = QComboBox(self)
        self.method_input.addItems(interpolate_dict.keys())
        self.layout.addWidget(QLabel('Interpolation Method:'))
        self.layout.addWidget(self.method_input)

        # 阶数选择
        self.k_widget = QFrame()
        self.k_input = QSpinBox()
        self.k_input.setRange(1, 5)
        self.k_input.setValue(3)

        self.k_layout = QHBoxLayout()
        self.k_layout.addWidget(QLabel('阶数k:'))
        self.k_layout.addWidget(self.k_input)
        self.k_widget.setLayout(self.k_layout)

        # 如果不是选择B样条插值,则不显示阶数选择
        self.is_k_widget_added = False
        self.method_input.currentTextChanged.connect(self.change_method)

        # 确定和取消按钮
        self.button_bar = QFrame()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)

        self.button_bar.setLayout(self.button_layout)
        self.layout.addWidget(self.button_bar)

        self.setLayout(self.layout)

    def change_method(self):
        # 获取当前选择的插值方法
        current_method = self.method_input.currentText()

        # 如果选择的是B样条插值且阶数选择不存在，则添加阶数选择
        # 再倒数第二行添加阶数选择
        if current_method == "B样条插值" and self.is_k_widget_added is False:
            self.layout.insertWidget(self.layout.count() - 1, self.k_widget)
            self.is_k_widget_added = True

        # 如果选择的不是B样条插值且阶数选择存在，则删除阶数选择
        elif current_method != "B样条插值" and self.is_k_widget_added is True:
            self.layout.itemAt(self.layout.count() - 2).widget().setParent(None)
            self.is_k_widget_added = False

    def accept(self):
        # 如果current_canva为空，弹出警告
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # 如果current_axes为空，弹出警告
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data_name = self.x_data_input.currentText()
        y_data_name = self.y_data_input.currentText()

        x_data = PyDatabase.get_data(x_data_name)
        y_data = PyDatabase.get_data(y_data_name)

        # 如果x_data和y_data长度不一致，弹出警告
        if len(x_data) != len(y_data):
            QMessageBox.warning(self, 'Warning', 'X Data and Y Data must have the same length!')
            return

        method = self.method_input.currentText()
        if method == "B样条插值":
            k = self.k_input.value()
            self.figure_window.current_canva.add_interpolate_curve(x=x_data, y=y_data, x_name=x_data_name,
                                                                   y_name=y_data_name, method=method, k=k)
        else:
            self.figure_window.current_canva.add_interpolate_curve(x=x_data, y=y_data, x_name=x_data_name,
                                                                   y_name=y_data_name, method=method)

        super().accept()

    def reject(self):
        super().reject()


chart_dialog_dict = {
    'curve': PyCurveDialog,
    'plot': PyPlotDialog,
    'scatter': PyScatterDialog,
    'fit': PyFitDialog,
    'interpolation': PyInterpolationDialog
}
