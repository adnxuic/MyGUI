from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.py_chart_modify import PyCurveModify, PyScatterModify, PyPlotModify, PyInterpolateModify
from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget

from code import status_messages
from code.database import matlab_adapter
from code.database.py_database import PyDatabase
from code.database.interpolate_func import interpolate_dict

import math
import os
import weakref

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "chart_mod_style.qss")


class PyCurveModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify, color: str):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.curve_modify = curve_modify

        self.layout = QVBoxLayout()

        # Function expression
        self.expression_box = QGroupBox('Expression', self)
        self.expression_box.setFixedSize(180, 80)
        self.expression_layout = QVBoxLayout()

        self.expression_input = QLineEdit(self)
        self.expression_input.setText(curve_modify.expression)
        self.expression_input.textChanged.connect(self.expression_change)
        self.expression_layout.addWidget(self.expression_input)

        self.expression_box.setLayout(self.expression_layout)

        # Add x-axis start and end points
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

        # Line style
        self.style_box = QGroupBox('Style', self)
        self.style_layout = QVBoxLayout()

        # Line color
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.style_layout.addWidget(self.color_choice)

        # Line marker
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

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)


        # Add stretch spacer
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

        # Line color
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # Add stretch spacer
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
        # Update x-axis data
        self.curve_modify.update_x_data(current_x_data)
        # Update mapping connection
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
        # Update y-axis data
        self.curve_modify.update_y_data(current_y_data)
        # Update mapping connection
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

        # Line color
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(scatter_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # Add stretch spacer
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
        # Update x-axis data
        self.curve_modify.update_x_data(current_x_data)
        # Update mapping connection
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
        # Update y-axis data
        self.curve_modify.update_y_data(current_y_data)
        # Update mapping connection
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


class PyFitModWidget(QFrame):
    def __init__(self, curve_modify: PyCurveModify, x_data_name: str = "", y_data_name: str = "",
                 engine: str = "Python"):
        super().__init__()

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.engine = engine
        self.x_data_name = x_data_name
        self.y_data_name = y_data_name
        self.curve_modify = curve_modify
        self._fit_dialogs = []
        self._fit_request_id = 0

        self.layout = QVBoxLayout()

        self.data_choice_widget = PyDataChoiceWidget()
        if x_data_name:
            self.data_choice_widget.set_x_data(x_data_name)
        if y_data_name:
            self.data_choice_widget.set_y_data(y_data_name)
        self.data_choice_widget.text_connect(self.x_data_change, self.y_data_change)

        self.engine_layout = QHBoxLayout()
        self.scipy_button = QPushButton("SciPy")
        self.matlab_button = QPushButton("Matlab")
        self.scipy_button.clicked.connect(lambda: self.open_fit_window("Python"))
        self.matlab_button.clicked.connect(lambda: self.open_fit_window("Matlab"))
        self.engine_layout.addWidget(QLabel("Engine:"))
        self.engine_layout.addWidget(self.scipy_button)
        self.engine_layout.addWidget(self.matlab_button)
        self.engine_layout.addStretch()

        self._matlab_state_listener = self._matlab_enabled_changed
        matlab_adapter.register_matlab_state_listener(self._matlab_state_listener)
        matlab_state_listener = self._matlab_state_listener
        self.destroyed.connect(lambda *_args, listener=matlab_state_listener: (
            matlab_adapter.unregister_matlab_state_listener(listener)
        ))
        self._matlab_enabled_changed(matlab_adapter.is_matlab_enabled())

        # Function expression
        self.expression_box = QGroupBox('Expression', self)
        self.expression_layout = QVBoxLayout()

        self.expression_input = QPlainTextEdit(self)
        # Set whether editing is allowed
        self.expression_input.setReadOnly(True)
        self.expression_input.setPlainText(curve_modify.expression)
        self.expression_input.textChanged.connect(self.expression_change)
        self.expression_layout.addWidget(self.expression_input)

        self.expression_box.setLayout(self.expression_layout)

        self.result_box = QGroupBox("Fit Result", self)
        self.result_layout = QVBoxLayout()
        self.result_engine_label = QLabel(f"Engine: {self._engine_display_name(self.engine)}")
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

        self.result_layout.addWidget(self.result_engine_label)
        self.result_layout.addWidget(self.result_model_label)
        self.result_layout.addWidget(QLabel("Formula:"))
        self.result_layout.addWidget(self.result_formula_input)
        self.result_layout.addWidget(QLabel("Coefficients and 95% Confidence Bounds:"))
        self.result_layout.addWidget(self.result_coeff_table)
        self.result_layout.addWidget(QLabel("Goodness of Fit:"))
        self.result_layout.addWidget(self.result_goodness_table)
        self.result_box.setLayout(self.result_layout)

        # Add x-axis start and end points
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

        # Line style
        self.style_box = QGroupBox('Style', self)
        self.style_box.setFixedSize(180, 80)
        self.style_layout = QVBoxLayout()

        # Line marker
        self.style_input = QComboBox(self)
        self.style_input.addItem('solid')
        self.style_input.addItem('dashed')
        self.style_input.addItem('dashdot')
        self.style_input.addItem('dotted')
        self.style_input.setCurrentText(curve_modify.line.get_linestyle())
        self.style_input.currentTextChanged.connect(self.style_change)

        self.style_layout.addWidget(self.style_input)
        self.style_box.setLayout(self.style_layout)

        self.layout.addWidget(self.data_choice_widget)
        self.layout.addLayout(self.engine_layout)
        self.layout.addWidget(self.expression_box)
        self.layout.addWidget(self.result_box)
        self.layout.addLayout(self.x_start_layout)
        self.layout.addLayout(self.x_stop_layout)
        self.layout.addWidget(self.style_box)

        # Line color
        self.color_choice = ColorChoiceWidget(connect_signal=self.color_change)
        self.layout.addWidget(self.color_choice)

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # Add stretch spacer
        self.layout.addStretch()

        self.setLayout(self.layout)

    def expression_change(self):
        current_expression = self.expression_input.toPlainText()
        self.curve_modify.update_expression(current_expression)

    def _engine_display_name(self, engine: str) -> str:
        return "SciPy" if engine == "Python" else engine

    def _matlab_enabled_changed(self, enabled: bool):
        self.matlab_button.setEnabled(bool(enabled))
        if enabled:
            self.matlab_button.setToolTip("")
        else:
            self.matlab_button.setToolTip("Connect MATLAB from the Matlab panel first.")

    def delete_object(self):
        self.curve_modify.delete_object()

    def x_data_change(self, *_args):
        self.x_data_name = self.data_choice_widget.get_x_data()

    def y_data_change(self, *_args):
        self.y_data_name = self.data_choice_widget.get_y_data()

    def _current_fit_data(self):
        self.x_data_change()
        self.y_data_change()
        x_name = self.x_data_name
        y_name = self.y_data_name
        if not x_name or not y_name:
            raise ValueError("Please select X Data and Y Data.")

        try:
            x_data = PyDatabase.get_data(x_name)
            y_data = PyDatabase.get_data(y_name)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        if len(x_data) == 0 or len(y_data) == 0:
            raise ValueError("X Data and Y Data must not be empty.")
        if len(x_data) != len(y_data):
            raise ValueError("X Data and Y Data must have the same length.")

        try:
            x_values = [float(value) for value in x_data]
            y_values = [float(value) for value in y_data]
        except (TypeError, ValueError) as exc:
            raise ValueError("X Data and Y Data must contain only numbers.") from exc

        return x_name, y_name, x_values, y_values, min(x_values), max(x_values)

    def open_fit_window(self, engine: str):
        if engine not in {"Python", "Matlab"}:
            raise ValueError(f"Unsupported fitting engine: {engine}")
        display_engine = self._engine_display_name(engine)
        if engine == "Matlab" and not matlab_adapter.is_matlab_enabled():
            status_messages.show_error("Connect MATLAB before using Matlab fitting.")
            return None
        try:
            self._current_fit_data()
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return None

        from code.widgets.fig_control_window.py_fit_options_window import (
            PyMatlabFitOptionsWidget,
            PyScipyFitOptionsWidget,
        )

        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setModal(False)
        dialog.setWindowTitle(f"{display_engine} Fit")

        dialog_layout = QVBoxLayout(dialog)
        fit_type_box = QGroupBox("Fit Type", dialog)
        fit_type_layout = QVBoxLayout()
        dialog.fit_type_input = QComboBox(dialog)
        options_widget_class = PyScipyFitOptionsWidget if engine == "Python" else PyMatlabFitOptionsWidget
        fit_type_groups = options_widget_class.fit_type_groups()
        dialog.fit_type_input.addItems(list(fit_type_groups.keys()))
        fit_type_layout.addWidget(dialog.fit_type_input)
        fit_type_box.setLayout(fit_type_layout)
        dialog_layout.addWidget(fit_type_box)

        dialog.fit_options_layout = QVBoxLayout()
        dialog.fit_options_widget = options_widget_class(
            fit_type_name=dialog.fit_type_input.currentText(),
        )
        dialog.fit_options_layout.addWidget(dialog.fit_options_widget)
        dialog_layout.addLayout(dialog.fit_options_layout)

        def replace_fit_options(text):
            try:
                new_widget = options_widget_class(fit_type_name=text)
            except Exception as exc:
                status_messages.show_error(str(exc))
                return
            old_widget = dialog.fit_options_widget
            dialog.fit_options_layout.removeWidget(old_widget)
            old_widget.setParent(None)
            old_widget.deleteLater()
            dialog.fit_options_widget = new_widget
            dialog.fit_options_layout.addWidget(new_widget)

        dialog.fit_type_input.currentTextChanged.connect(replace_fit_options)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        dialog.fit_button = QPushButton("Fit", dialog)
        dialog.close_button = QPushButton("Close", dialog)
        dialog.fit_button.clicked.connect(lambda: self._start_fit_from_dialog(dialog, engine))
        dialog.close_button.clicked.connect(dialog.close)
        button_layout.addWidget(dialog.fit_button)
        button_layout.addWidget(dialog.close_button)
        dialog_layout.addLayout(button_layout)

        self._fit_dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_args, target=dialog: self._forget_fit_dialog(target))
        dialog.show()
        return dialog

    def _forget_fit_dialog(self, dialog):
        try:
            self._fit_dialogs.remove(dialog)
        except ValueError:
            pass

    def _start_fit_from_dialog(self, dialog, engine: str):
        from code.database import scipy_fit_adapter
        from code.widgets.fig_control_window.background_task import start_background_task

        display_engine = self._engine_display_name(engine)
        try:
            x_name, y_name, x_values, y_values, x_min, x_max = self._current_fit_data()
            fit_type_order, fit_options = dialog.fit_options_widget.fit_parameters()
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return

        self._fit_request_id += 1
        request_id = self._fit_request_id
        try:
            dialog._fit_request_id = request_id
        except RuntimeError:
            pass
        dialog.fit_button.setEnabled(False)
        dialog.fit_button.setText("Fitting...")
        status_messages.show_message(f"{display_engine} fitting started.", "info")

        matlab_adapter.matlab_logger().info(
            "%s fit request started request_id=%s fit_type=%s x_data=%s y_data=%s x_len=%s y_len=%s",
            display_engine,
            request_id,
            fit_type_order,
            x_name,
            y_name,
            len(x_values),
            len(y_values),
        )
        fit_func = matlab_adapter.fit_curve_isolated if engine == "Matlab" else scipy_fit_adapter.fit_curve
        dialog_ref = weakref.ref(dialog)
        start_background_task(
            self,
            fit_func,
            lambda result, rid=request_id, dref=dialog_ref, xmin=x_min, xmax=x_max: self._fit_dialog_succeeded(
                dref,
                rid,
                result,
                xmin,
                xmax,
                engine,
            ),
            lambda message, rid=request_id, dref=dialog_ref: self._fit_dialog_failed(dref, rid, message, engine),
            x_values,
            y_values,
            fit_type_order,
            fit_options,
            logger=matlab_adapter.matlab_logger(),
            task_log_prefix=f"{display_engine} fit task",
        )

    def _dialog_for_request(self, dialog_ref, request_id):
        dialog = dialog_ref()
        if dialog is None:
            return None
        try:
            if request_id != getattr(dialog, "_fit_request_id", None):
                return None
        except RuntimeError:
            return None
        return dialog

    def _restore_dialog_fit_button(self, dialog_ref, request_id):
        dialog = self._dialog_for_request(dialog_ref, request_id)
        if dialog is None:
            return False
        try:
            if hasattr(dialog, "fit_button"):
                dialog.fit_button.setEnabled(True)
                dialog.fit_button.setText("Fit")
        except RuntimeError:
            return False
        return True

    def _fit_dialog_succeeded(self, dialog_ref, request_id, result, x_min, x_max, engine: str):
        if not self._restore_dialog_fit_button(dialog_ref, request_id):
            return
        if request_id != self._fit_request_id:
            return
        self.engine = engine
        self.update_curve(result, x_min, x_max)
        status_messages.show_success(f"{self._engine_display_name(engine)} fitting completed.")

    def _fit_dialog_failed(self, dialog_ref, request_id, message, engine: str):
        if not self._restore_dialog_fit_button(dialog_ref, request_id):
            return
        if request_id != self._fit_request_id:
            return
        status_messages.show_error(str(message))

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
        engine = fit_result.get("engine", self.engine)
        self.engine = engine if engine in {"Python", "Matlab"} else self.engine
        self.result_engine_label.setText(f"Engine: {self._engine_display_name(self.engine)}")
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

        # Interpolation method
        self.interpolat_box = QGroupBox('Interpolation')
        self.interpolat_layout = QVBoxLayout()

        self.interpolat_input = QComboBox(self)
        self.interpolat_input.addItems(interpolate_dict.keys())

        self.interpolat_layout.addWidget(self.interpolat_input)
        # Add stretch spacer
        self.interpolat_layout.addStretch()

        # Order selection
        self.k_widget = QFrame()
        self.k_input = QSpinBox()
        self.k_input.setRange(1, 5)
        self.k_input.setValue(init_k)
        self.k_input.valueChanged.connect(self.interpolat_change)

        self.k_layout = QHBoxLayout()
        self.k_layout.addWidget(QLabel('阶数k:'))
        self.k_layout.addWidget(self.k_input)
        self.k_widget.setLayout(self.k_layout)

        # Hide order selection unless B-spline interpolation is selected
        self.is_k_widget_added = False
        self.interpolat_input.currentTextChanged.connect(self.change_method)
        self.interpolat_input.setCurrentText(init_interpolat)
        self.interpolat_input.currentTextChanged.connect(self.interpolat_change)

        self.interpolat_box.setLayout(self.interpolat_layout)

        self.layout.addWidget(self.interpolat_box)

        # Line color
        self.color_choice = ColorChoiceWidget(color, self.color_change)
        self.layout.addWidget(self.color_choice)

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_input = QLineEdit(self)
        self.legend_input.setPlaceholderText('Legend')
        self.legend_input.textChanged.connect(self.legend_change)
        self.legend_input.setText(curve_modify.label)
        self.legend_layout.addWidget(QLabel('Legend:'))
        self.legend_layout.addWidget(self.legend_input)
        self.layout.addLayout(self.legend_layout)

        # Add stretch spacer
        self.layout.addStretch()

        self.setLayout(self.layout)

    def get_colorupdate_func(self):
        return self.color_choice.updateColor

    def delete_object(self):
        self.modify.delete_object()

    def change_method(self):
        # Get currently selected interpolation method
        current_method = self.interpolat_input.currentText()

        # Add order selection when B-spline is selected and widget is absent
        # Insert order selection before the last row
        if current_method == "B样条插值" and self.is_k_widget_added is False:
            self.interpolat_layout.insertWidget(self.interpolat_layout.count() - 1, self.k_widget)
            self.is_k_widget_added = True

        # Remove order selection when B-spline is not selected
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
