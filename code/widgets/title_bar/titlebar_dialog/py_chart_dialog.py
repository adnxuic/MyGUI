from Qt_core import *

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from code.widgets import qss_func

from code.database.py_database import databases, PyDatabase
from code import status_messages
from code.database.interpolate_func import (
    DEFAULT_INTERPOLATION_SAMPLES,
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    interpolate_dict,
    interpolation_uses_lambda,
    interpolation_uses_order,
)

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


def _add_current_table_data_names(x_input: QComboBox, y_input: QComboBox,
                                  figure_window: PyFigureWindow | None):
    table_name = None
    if figure_window is not None and figure_window.current_canva is not None:
        table_name = figure_window.current_canva.project_table_name
    for data_name in PyDatabase.iter_data_names(table_name):
        x_input.addItem(data_name)
        y_input.addItem(data_name)


# Curve creation dialog
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

        # Function expression input
        self.expression_label = QLabel("函数表达式")
        self.expression_edit = QLineEdit()
        self.expression_edit.setText("x")
        # Update legend label when expression changes
        self.expression_edit.textChanged.connect(lambda: self.label_input.setText(self.expression_edit.text()))
        self.layout.addWidget(self.expression_label)
        self.layout.addWidget(self.expression_edit)

        # X range input
        self.x_range_label = QLabel("x的范围")
        self.x_range_layout = QHBoxLayout()
        self.x_start_input = QDoubleSpinBox(self)
        self.x_start_input.setValue(0)
        self.x_stop_input = QDoubleSpinBox(self)
        self.x_stop_input.setValue(100)
        # Set bounds to infinity
        self.x_start_input.setRange(float('-inf'), float('inf'))
        self.x_stop_input.setRange(float('-inf'), float('inf'))

        self.x_range_layout.addWidget(self.x_start_input)
        self.x_range_layout.addWidget(self.x_stop_input)
        self.layout.addWidget(self.x_range_label)
        self.layout.addLayout(self.x_range_layout)

        # Line style selection
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # Color selection and preview
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # Legend label input
        self.label_input = QLineEdit(self)
        self.label_input.setText('x')
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # OK and Cancel buttons
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
        # Warn if current canvas is empty
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        try:
            self.figure_window.current_canva.add_curve(func_text=self.expression_edit.text(),
                                                       x_start=self.x_start_input.value(),
                                                       x_stop=self.x_stop_input.value(),
                                                       style=self.style_input.currentText(),
                                                       color=self.color_input.get_color(),
                                                       label=self.label_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid Expression', str(exc))
            return
        super().accept()

    def reject(self):
        super().reject()


# Line plot dialog
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

        # Data selection
        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        _add_current_table_data_names(self.x_data_input, self.y_data_input, self.figure_window)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.layout.addLayout(self.x_data_layout)
        self.layout.addLayout(self.y_data_layout)

        # Size selection
        self.size_input = QDoubleSpinBox(self)
        self.size_input.setRange(0.1, 10)
        self.size_input.setSingleStep(0.1)
        self.size_input.setValue(2)
        self.layout.addWidget(QLabel('Size:'))
        self.layout.addWidget(self.size_input)

        # Color selection and preview
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # Line style selection
        self.style_input = QComboBox(self)
        self.style_input.addItems(['-', '--', '-.', ':'])
        self.layout.addWidget(QLabel('Line Style:'))
        self.layout.addWidget(self.style_input)

        # Legend label input
        self.label_input = QLineEdit(self)
        self.label_input.setText('plot')
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # OK and Cancel buttons
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
        # Warn if current canvas is empty
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data = PyDatabase.get_data(self.x_data_input.currentText())
        y_data = PyDatabase.get_data(self.y_data_input.currentText())

        # Warn if x_data and y_data lengths differ
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


# Scatter plot dialog
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

        # Data selection
        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        _add_current_table_data_names(self.x_data_input, self.y_data_input, self.figure_window)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.layout.addLayout(self.x_data_layout)
        self.layout.addLayout(self.y_data_layout)

        # Size selection
        self.size_input = QSpinBox(self)
        self.size_input.setRange(0, 100)
        self.size_input.setValue(20)
        self.layout.addWidget(QLabel('Size:'))
        self.layout.addWidget(self.size_input)

        # Color selection and preview
        self.color_input = ColorChoiceWidget(colorselector=figure_window.get_current_canvas_axes_colorselector())
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # Scatter marker selection
        self.style_input = QComboBox(self)
        self.style_input.addItems(['o', 's', 'D', 'x', '+'])
        self.layout.addWidget(QLabel('Marker Style:'))
        self.layout.addWidget(self.style_input)

        # Legend label input
        self.label_input = QLineEdit(self)
        self.label_input.setText('scatter')
        self.layout.addWidget(QLabel('Label:'))
        self.layout.addWidget(self.label_input)

        # OK and Cancel buttons
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
        # Warn if current canvas is empty
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data = PyDatabase.get_data(self.x_data_input.currentText())
        y_data = PyDatabase.get_data(self.y_data_input.currentText())

        # Warn if x_data and y_data lengths differ
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

        # Data selection
        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        _add_current_table_data_names(self.x_data_input, self.y_data_input, self.figure_window)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.layout.addLayout(self.x_data_layout)
        self.layout.addLayout(self.y_data_layout)

        # OK and Cancel buttons
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
        # Warn if current canvas is empty
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        try:
            x_data = PyDatabase.get_data(self.x_data_input.currentText())
            y_data = PyDatabase.get_data(self.y_data_input.currentText())
        except KeyError as exc:
            QMessageBox.warning(self, 'Warning', str(exc))
            return

        # Warn if x_data and y_data lengths differ
        if len(x_data) != len(y_data):
            QMessageBox.warning(self, 'Warning', 'X Data and Y Data must have the same length!')
            return

        self.figure_window.current_canva.add_fit_curve(
            x=x_data,
            y=y_data,
            color='black',
            label='fitting',
            x_data_name=self.x_data_input.currentText(),
            y_data_name=self.y_data_input.currentText(),
        )

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

        # Data selection
        self.x_data_input = QComboBox(self)
        self.x_data_layout = QHBoxLayout()
        self.y_data_input = QComboBox(self)
        self.y_data_layout = QHBoxLayout()

        _add_current_table_data_names(self.x_data_input, self.y_data_input, self.figure_window)

        self.x_data_layout.addWidget(QLabel('X Data:'))
        self.x_data_layout.addWidget(self.x_data_input)
        self.y_data_layout.addWidget(QLabel('Y Data:'))
        self.y_data_layout.addWidget(self.y_data_input)
        self.layout.addLayout(self.x_data_layout)
        self.layout.addLayout(self.y_data_layout)

        # Interpolation method selection
        self.method_input = QComboBox(self)
        self.method_input.addItems(interpolate_dict.keys())
        self.layout.addWidget(QLabel('Interpolation Method:'))
        self.layout.addWidget(self.method_input)

        self.samples_layout = QHBoxLayout()
        self.samples_input = QSpinBox()
        self.samples_input.setRange(MIN_INTERPOLATION_SAMPLES, MAX_INTERPOLATION_SAMPLES)
        self.samples_input.setValue(DEFAULT_INTERPOLATION_SAMPLES)
        self.samples_layout.addWidget(QLabel('Samples:'))
        self.samples_layout.addWidget(self.samples_input)
        self.layout.addLayout(self.samples_layout)

        self.k_widget = QFrame()
        self.k_input = QSpinBox()
        self.k_input.setRange(1, 5)
        self.k_input.setValue(3)
        self.k_layout = QHBoxLayout()
        self.k_layout.addWidget(QLabel('阶数k:'))
        self.k_layout.addWidget(self.k_input)
        self.k_widget.setLayout(self.k_layout)
        self.layout.addWidget(self.k_widget)

        self.lambda_widget = QFrame()
        self.lambda_layout = QVBoxLayout()
        self.lambda_auto_input = QCheckBox("Auto lambda")
        self.lambda_auto_input.setChecked(True)
        self.lambda_value_input = QDoubleSpinBox()
        self.lambda_value_input.setRange(0.0, 1e12)
        self.lambda_value_input.setDecimals(6)
        self.lambda_value_input.setSingleStep(0.1)
        self.lambda_value_input.setValue(1.0)
        self.lambda_value_input.setEnabled(False)
        self.lambda_layout.addWidget(self.lambda_auto_input)
        self.lambda_row = QHBoxLayout()
        self.lambda_row.addWidget(QLabel('Lambda:'))
        self.lambda_row.addWidget(self.lambda_value_input)
        self.lambda_layout.addLayout(self.lambda_row)
        self.lambda_widget.setLayout(self.lambda_layout)
        self.layout.addWidget(self.lambda_widget)

        self.method_input.currentTextChanged.connect(self.change_method)
        self.lambda_auto_input.toggled.connect(self.lambda_auto_changed)
        self.change_method()

        # OK and Cancel buttons
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
        current_method = self.method_input.currentText()
        self.k_widget.setVisible(interpolation_uses_order(current_method))
        self.lambda_widget.setVisible(interpolation_uses_lambda(current_method))

    def lambda_auto_changed(self, checked: bool):
        self.lambda_value_input.setEnabled(not checked)

    def _lambda_options(self, method: str):
        if not interpolation_uses_lambda(method):
            return None, True
        if self.lambda_auto_input.isChecked():
            return None, True
        return self.lambda_value_input.value(), False

    def accept(self):
        # Warn if current canvas is empty
        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        x_data_name = self.x_data_input.currentText()
        y_data_name = self.y_data_input.currentText()

        try:
            x_data = PyDatabase.get_data(x_data_name)
            y_data = PyDatabase.get_data(y_data_name)
        except KeyError as exc:
            status_messages.show_error(str(exc))
            return

        # Warn if x_data and y_data lengths differ
        if len(x_data) != len(y_data):
            status_messages.show_error('X Data and Y Data must have the same length!')
            return

        method = self.method_input.currentText()
        lam, lam_auto = self._lambda_options(method)
        line = self.figure_window.current_canva.add_interpolate_curve(
            x=x_data,
            y=y_data,
            x_name=x_data_name,
            y_name=y_data_name,
            method=method,
            k=self.k_input.value(),
            samples=self.samples_input.value(),
            lam=lam,
            lam_auto=lam_auto,
        )
        if line is None:
            return

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
