from Qt_core import *

from code.widgets.figure_canvas.py_figure_window import PyFigureWindow
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from code.widgets import qss_func

from code.database.py_database import databases, PyDatabase
from code.database.interpolate_func import interpolate_dict

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "dialog_style.qss")


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

        # Interpolation method selection
        self.method_input = QComboBox(self)
        self.method_input.addItems(interpolate_dict.keys())
        self.layout.addWidget(QLabel('Interpolation Method:'))
        self.layout.addWidget(self.method_input)

        # Order selection
        self.k_widget = QFrame()
        self.k_input = QSpinBox()
        self.k_input.setRange(1, 5)
        self.k_input.setValue(3)

        self.k_layout = QHBoxLayout()
        self.k_layout.addWidget(QLabel('阶数k:'))
        self.k_layout.addWidget(self.k_input)
        self.k_widget.setLayout(self.k_layout)

        # Hide order selection unless B-spline interpolation is selected
        self.is_k_widget_added = False
        self.method_input.currentTextChanged.connect(self.change_method)

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
        # Get currently selected interpolation method
        current_method = self.method_input.currentText()

        # Add order selection when B-spline is selected and widget is absent
        # Insert order selection before the last row
        if current_method == "B样条插值" and self.is_k_widget_added is False:
            self.layout.insertWidget(self.layout.count() - 1, self.k_widget)
            self.is_k_widget_added = True

        # Remove order selection when B-spline is not selected
        elif current_method != "B样条插值" and self.is_k_widget_added is True:
            self.layout.itemAt(self.layout.count() - 2).widget().setParent(None)
            self.is_k_widget_added = False

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

        x_data = PyDatabase.get_data(x_data_name)
        y_data = PyDatabase.get_data(y_data_name)

        # Warn if x_data and y_data lengths differ
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
