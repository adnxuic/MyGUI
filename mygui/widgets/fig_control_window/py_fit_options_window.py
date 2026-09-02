"""Collect and apply MATLAB or SciPy curve-fitting options."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from typing import Any

from mygui.database import FitInputRangeSpec, matlab_adapter, scipy_fit_adapter
from mygui.widgets.fig_control_window.background_task import start_matlab_task

import numpy as np
import time


class FitDataRangeWidget(QGroupBox):
    """Provide the 'Fit Data Range' selection controls for fit dialogs."""

    def __init__(self, parent=None):
        super().__init__("Fit Data Range", parent)
        self._available_min: float | None = None
        self._available_max: float | None = None

        layout = QVBoxLayout(self)
        self.use_all_checkbox = QCheckBox("Use all preprocessed data", self)
        self.use_all_checkbox.setChecked(True)
        layout.addWidget(self.use_all_checkbox)

        self.available_label = QLabel("Available X: -", self)
        layout.addWidget(self.available_label)

        bounds_layout = QHBoxLayout()
        bounds_layout.addWidget(QLabel("Minimum X:", self))
        self.minimum_input = QLineEdit(self)
        bounds_layout.addWidget(self.minimum_input)
        bounds_layout.addWidget(QLabel("Maximum X:", self))
        self.maximum_input = QLineEdit(self)
        bounds_layout.addWidget(self.maximum_input)
        layout.addLayout(bounds_layout)

        self.use_all_checkbox.toggled.connect(self._on_use_all_toggled)
        self._update_inputs_enabled()

    def _on_use_all_toggled(self, checked: bool) -> None:
        self._update_inputs_enabled()
        if not checked:
            if not self.minimum_input.text().strip() and self._available_min is not None:
                self.minimum_input.setText(f"{self._available_min:g}")
            if not self.maximum_input.text().strip() and self._available_max is not None:
                self.maximum_input.setText(f"{self._available_max:g}")

    def _update_inputs_enabled(self) -> None:
        enabled = not self.use_all_checkbox.isChecked()
        self.minimum_input.setEnabled(enabled)
        self.maximum_input.setEnabled(enabled)

    def set_available_range(self, x_min: float, x_max: float) -> None:
        self._available_min = float(x_min)
        self._available_max = float(x_max)
        self.available_label.setText(f"Available X: {self._available_min:g} to {self._available_max:g}")

    def set_range_spec(self, spec: Any) -> None:
        spec_obj = FitInputRangeSpec.from_dict(spec)
        if spec_obj.is_bounded:
            self.use_all_checkbox.setChecked(False)
            self.minimum_input.setText(f"{spec_obj.minimum:g}")
            self.maximum_input.setText(f"{spec_obj.maximum:g}")
        else:
            self.use_all_checkbox.setChecked(True)
            self.minimum_input.clear()
            self.maximum_input.clear()
        self._update_inputs_enabled()

    def range_spec(self) -> FitInputRangeSpec:
        if self.use_all_checkbox.isChecked():
            return FitInputRangeSpec(kind="all")
        min_text = self.minimum_input.text().strip()
        max_text = self.maximum_input.text().strip()
        if not min_text:
            raise ValueError("Fit input range minimum must not be empty.")
        if not max_text:
            raise ValueError("Fit input range maximum must not be empty.")
        try:
            min_val = float(min_text)
        except ValueError as exc:
            raise ValueError("Fit input range minimum must be a finite number.") from exc
        try:
            max_val = float(max_text)
        except ValueError as exc:
            raise ValueError("Fit input range maximum must be a finite number.") from exc
        if not np.isfinite(min_val):
            raise ValueError("Fit input range minimum must be a finite number.")
        if not np.isfinite(max_val):
            raise ValueError("Fit input range maximum must be a finite number.")
        return FitInputRangeSpec(kind="bounded", minimum=min_val, maximum=max_val)


class _FitOptionsWidgetBase(QFrame):
    engine = "Fit"
    engine_label = "Fit"

    def __init__(self, parent=None, fit_type_name='poly'):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.layout = QVBoxLayout()

        self.fit_type = fit_type_name
        self._expression_request_id = 0

        self.fit_option = QGroupBox("Fit Option")

        self.fit_option_layout = QVBoxLayout()
        self.fit_option_layout.setSpacing(0)
        self.fit_option_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_option.setLayout(self.fit_option_layout)

        self.order_layout = QHBoxLayout()
        self.order_input = QComboBox()
        items_list = self.fit_type_groups()[fit_type_name]
        self.order_input.addItems(items_list)
        self.order_layout.addWidget(QLabel("Order:"))
        self.order_layout.addWidget(self.order_input)

        self.func_exp = ""
        self.func_coefs = []
        self.expression_input = QPlainTextEdit()
        self.expression_input.setPlainText(self.loading_expression_text())
        self.expression_input.setReadOnly(True)

        self.order_input.currentTextChanged.connect(self.expression_change)

        self.fit_option_layout.addLayout(self.order_layout)
        self.fit_option_layout.addWidget(QLabel("Expression:"))
        self.fit_option_layout.addWidget(self.expression_input)

        self.advanced_option = QGroupBox("Advanced Option")
        self.advanced_option_layout = QVBoxLayout()
        self.advanced_option.setLayout(self.advanced_option_layout)
        self.advanced_option.setCheckable(True)
        self.advanced_option.setChecked(False)

        self.coeff_up_limit = []
        self.coeff_down_limit = []
        self.start_point = []
        self.option_widgets = {}
        self.option_metadata = {}
        self.option_form = QFormLayout()
        self.advanced_option_layout.addLayout(self.option_form)

        self.coefficient_table = QTableWidget()
        self.coefficient_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.coefficient_table.horizontalHeader().setStretchLastSection(True)

        self.coefficient_table.setColumnCount(3)
        self.coefficient_table.setHorizontalHeaderLabels(["Coefficient", "Lower", "Upper"])

        self.advanced_option_layout.addWidget(QLabel("Coefficient Constraints:"))
        self.advanced_option_layout.addWidget(self.coefficient_table)

        self.layout.addWidget(self.fit_option)
        self.layout.addWidget(self.advanced_option)
        self.setLayout(self.layout)
        self._apply_fit_info(self.fallback_fit_info(self.order_input.currentText()))
        self.load_expression(self.order_input.currentText())

    @classmethod
    def fit_type_groups(cls):
        """Fit type groups using the selected model and options."""

        raise NotImplementedError

    def fallback_fit_info(self, fit_type: str):
        """Handle the fallback fit info action."""

        raise NotImplementedError

    def default_method(self, fit_type: str):
        """Return the default method."""

        raise NotImplementedError

    def default_fit_options(self, fit_type: str, coefficients):
        """Return the default fit options."""

        raise NotImplementedError

    def loading_expression_text(self):
        """Handle the loading expression text action."""

        return f"Loading {self.engine_label} expression..."

    def _has_start_point(self, method: str) -> bool:
        return method == "NonlinearLeastSquares"

    def _clear_form_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _option_text(self, value, default=""):
        if value is None:
            return default
        return str(value)

    def _option_float_text(self, value, default=""):
        if value is None:
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if np.isnan(number):
            return default
        if np.isposinf(number):
            return "inf"
        if np.isneginf(number):
            return "-inf"
        return f"{number:g}"

    def _combo_option(self, values, current):
        combo = QComboBox()
        combo.addItems(values)
        if current in values:
            combo.setCurrentText(current)
        return combo

    def _line_option(self, value):
        line = QLineEdit()
        line.setText(self._option_float_text(value))
        return line

    def _add_option_row(self, name, widget):
        self.option_widgets[name] = widget
        self.option_form.addRow(QLabel(f"{name}:"), widget)

    def _rebuild_option_widgets(self):
        self._clear_form_layout(self.option_form)
        self.option_widgets = {}
        method = self.option_metadata.get("Method", self.default_method(self.order_input.currentText()))

        method_label = QLabel(method)
        method_label.setObjectName("fit_method")
        self._add_option_row("Method", method_label)
        self._add_engine_option_widgets(method)

    def _add_engine_option_widgets(self, method: str):
        raise NotImplementedError

    def _apply_fit_info(self, info):
        if not isinstance(info, dict):
            expression, coefficients = info
            coefficients = list(coefficients)
            info = {
                "expression": expression,
                "coefficients": coefficients,
                "options": self.default_fit_options(self.order_input.currentText(), coefficients),
            }
        self.func_exp = str(info.get("expression", ""))
        self.func_coefs = [str(coef) for coef in info.get("coefficients", [])]
        self.option_metadata = dict(info.get("options") or {})
        self.option_metadata.setdefault(
            "Method",
            self.default_method(self.order_input.currentText()),
        )
        self.expression_input.setPlainText(self.func_exp)
        self._rebuild_option_widgets()
        self._set_coefficients(self.func_coefs)

    def _list_option(self, name, length, default):
        values = list(self.option_metadata.get(name) or [])
        values.extend([default] * max(0, length - len(values)))
        return values[:length]

    def load_expression(self, text):
        """Load expression."""

        raise NotImplementedError

    def _set_coefficients(self, coefficients):
        method = self.option_metadata.get("Method", self.default_method(self.order_input.currentText()))
        has_start = self._has_start_point(method)
        if has_start:
            self.coefficient_table.setColumnCount(4)
            self.coefficient_table.setHorizontalHeaderLabels(["Coefficient", "Start", "Lower", "Upper"])
        else:
            self.coefficient_table.setColumnCount(3)
            self.coefficient_table.setHorizontalHeaderLabels(["Coefficient", "Lower", "Upper"])

        lower_values = self._list_option("Lower", len(coefficients), "-inf")
        upper_values = self._list_option("Upper", len(coefficients), "inf")
        start_values = self._list_option("StartPoint", len(coefficients), None)
        self.coefficient_table.setRowCount(len(coefficients))
        for i, coef in enumerate(coefficients):
            self.coefficient_table.setItem(i, 0, QTableWidgetItem(coef))
            self.coefficient_table.item(i, 0).setFlags(Qt.ItemIsEnabled)
            if has_start:
                self.coefficient_table.setItem(i, 1, QTableWidgetItem(self._option_float_text(start_values[i])))
                self.coefficient_table.setItem(i, 2, QTableWidgetItem(self._option_float_text(lower_values[i], "-inf")))
                self.coefficient_table.setItem(i, 3, QTableWidgetItem(self._option_float_text(upper_values[i], "inf")))
            else:
                self.coefficient_table.setItem(i, 1, QTableWidgetItem(self._option_float_text(lower_values[i], "-inf")))
                self.coefficient_table.setItem(i, 2, QTableWidgetItem(self._option_float_text(upper_values[i], "inf")))

    def expression_change(self, text):
        """Apply the expression change emitted by the corresponding control."""

        self.load_expression(text)

    def _parse_float_text(self, text, field_name):
        text = str(text).strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty.")
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a number.") from exc
        if not np.isfinite(number):
            raise ValueError(f"{field_name} must be finite.")
        return number

    def _parse_optional_float_text(self, text, field_name):
        text = str(text).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a number.") from exc
        if not np.isfinite(number):
            raise ValueError(f"{field_name} must be finite.")
        return number

    def _parse_bound_text(self, text, field_name, *, lower):
        text = str(text).strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty.")
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a number or infinity.") from exc
        if np.isnan(number):
            raise ValueError(f"{field_name} must not be NaN.")
        if np.isinf(number):
            if (lower and number < 0) or (not lower and number > 0):
                return None
            raise ValueError(f"{field_name} uses the wrong infinity direction.")
        return number

    def _coefficient_cell_text(self, row, column):
        item = self.coefficient_table.item(row, column)
        return "" if item is None else item.text()

    def _option_widget_value(self, name):
        widget = self.option_widgets.get(name)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QLineEdit):
            return self._parse_float_text(widget.text(), name)
        if isinstance(widget, QLabel):
            return widget.text()
        return None

    def get_coef_limit(self):
        """Return coef limit."""

        self.coeff_up_limit.clear()
        self.coeff_down_limit.clear()
        self.start_point.clear()
        method = self.option_metadata.get("Method", self.default_method(self.order_input.currentText()))
        has_start = self._has_start_point(method)

        for i in range(self.coefficient_table.rowCount()):
            coefficient = self._coefficient_cell_text(i, 0) or f"coefficient {i + 1}"
            if has_start:
                start = self._parse_optional_float_text(self._coefficient_cell_text(i, 1), f"{coefficient} Start")
                lower = self._parse_bound_text(
                    self._coefficient_cell_text(i, 2),
                    f"{coefficient} Lower",
                    lower=True,
                )
                upper = self._parse_bound_text(
                    self._coefficient_cell_text(i, 3),
                    f"{coefficient} Upper",
                    lower=False,
                )
                self.start_point.append(start)
            else:
                lower = self._parse_bound_text(
                    self._coefficient_cell_text(i, 1),
                    f"{coefficient} Lower",
                    lower=True,
                )
                upper = self._parse_bound_text(
                    self._coefficient_cell_text(i, 2),
                    f"{coefficient} Upper",
                    lower=False,
                )
            self.coeff_down_limit.append(lower)
            self.coeff_up_limit.append(upper)

        if has_start:
            has_any_start = any(value is not None for value in self.start_point)
            has_blank_start = any(value is None for value in self.start_point)
            if has_any_start and has_blank_start:
                raise ValueError("StartPoint must be either fully specified or left fully blank.")

    def fit_parameters(self):
        """Fit parameters using the selected model and options."""

        fit_type_order = self.order_input.currentText()
        if not fit_type_order:
            raise ValueError(f"Please select a {self.engine_label} fit type first.")

        if not self.advanced_option.isChecked():
            return fit_type_order, None

        return self._advanced_fit_parameters(fit_type_order)

    def _advanced_fit_parameters(self, fit_type_order):
        raise NotImplementedError

    def fit_curve(self, x, y):
        """Fit curve using the selected model and options."""

        raise NotImplementedError


class PyMatlabFitOptionsWidget(_FitOptionsWidgetBase):
    """Provide the py matlab fit options widget Qt widget."""

    engine = "Matlab"
    engine_label = "Matlab"

    def __init__(self, parent=None, fit_type_name='poly'):
        super().__init__(parent=parent, fit_type_name=fit_type_name)

    @classmethod
    def fit_type_groups(cls):
        """Fit type groups using the selected model and options."""

        return matlab_adapter.FIT_TYPES

    def fallback_fit_info(self, fit_type: str):
        """Return fit metadata when an optional backend is unavailable."""

        return matlab_adapter.fallback_func_info(fit_type)

    def default_method(self, fit_type: str):
        """Return the default method."""

        return matlab_adapter.fit_method_for_name(fit_type)

    def default_fit_options(self, fit_type: str, coefficients):
        """Return the default fit options."""

        return matlab_adapter.default_fit_options(fit_type, list(coefficients))

    def _add_engine_option_widgets(self, method: str):
        self._add_option_row(
            "Normalize",
            self._combo_option(["off", "on"], self._option_text(self.option_metadata.get("Normalize"), "off")),
        )
        self._add_option_row(
            "Robust",
            self._combo_option(["Off", "LAR", "Bisquare"], self._option_text(self.option_metadata.get("Robust"), "Off")),
        )
        self._add_option_row("TolCon", self._line_option(self.option_metadata.get("TolCon", 1e-6)))

        if method == "NonlinearLeastSquares":
            self._add_option_row(
                "Algorithm",
                self._combo_option(
                    list(matlab_adapter.NONLINEAR_ALGORITHMS),
                    self._option_text(self.option_metadata.get("Algorithm"), "Trust-Region"),
                ),
            )
            for name, default in (
                ("DiffMinChange", 1e-8),
                ("DiffMaxChange", 0.1),
                ("MaxFunEvals", 600),
                ("MaxIter", 400),
                ("TolFun", 1e-6),
                ("TolX", 1e-6),
            ):
                self._add_option_row(name, self._line_option(self.option_metadata.get(name, default)))

    def load_expression(self, text):
        """Load expression."""

        self._expression_request_id += 1
        request_id = self._expression_request_id
        started_at = time.monotonic()
        matlab_adapter.matlab_logger().info(
            "MATLAB expression request started request_id=%s func_name=%s",
            request_id,
            text,
        )
        self.order_input.setEnabled(False)
        self.expression_input.setPlainText(self.loading_expression_text())
        start_matlab_task(
            self,
            matlab_adapter.get_func_info_isolated,
            lambda result, rid=request_id, started=started_at: self._expression_loaded(rid, started, result),
            lambda message, rid=request_id, started=started_at: self._expression_failed(rid, started, message),
            text,
        )

    def _expression_loaded(self, request_id, started_at, result):
        if request_id != self._expression_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale expression success ignored request_id=%s current_request_id=%s",
                request_id,
                self._expression_request_id,
            )
            return
        self.order_input.setEnabled(True)
        self._apply_fit_info(result)
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().info(
            "MATLAB expression request succeeded request_id=%s elapsed=%.3fs coefficient_count=%s",
            request_id,
            elapsed,
            len(self.func_coefs),
        )

    def _expression_failed(self, request_id, started_at, message):
        if request_id != self._expression_request_id:
            matlab_adapter.matlab_logger().debug(
                "MATLAB stale expression failure ignored request_id=%s current_request_id=%s",
                request_id,
                self._expression_request_id,
            )
            return
        self.order_input.setEnabled(True)
        if not self.func_exp:
            self.expression_input.setPlainText("MATLAB expression unavailable")
            self.coefficient_table.setRowCount(0)
        else:
            self.expression_input.setPlainText(self.func_exp)
            self._set_coefficients(self.func_coefs)
        elapsed = time.monotonic() - started_at
        matlab_adapter.matlab_logger().warning(
            "MATLAB expression request failed request_id=%s elapsed=%.3fs message=%s",
            request_id,
            elapsed,
            message,
        )
        QMessageBox.warning(self, "Matlab Fit", message)

    def _advanced_fit_parameters(self, fit_type_order):
        self.get_coef_limit()
        method = self.option_metadata.get("Method", self.default_method(fit_type_order))
        start_point = None
        if self._has_start_point(method) and any(value is not None for value in self.start_point):
            start_point = [float(value) for value in self.start_point if value is not None]

        fit_options = {
            "Method": method,
            "Normalize": self._option_widget_value("Normalize"),
            "Robust": self._option_widget_value("Robust"),
            "TolCon": self._option_widget_value("TolCon"),
            "Lower": list(self.coeff_down_limit),
            "Upper": list(self.coeff_up_limit),
        }
        if start_point is not None:
            fit_options["StartPoint"] = start_point
        if self._has_start_point(method):
            for name in (
                "Algorithm",
                "DiffMinChange",
                "DiffMaxChange",
                "MaxFunEvals",
                "MaxIter",
                "TolFun",
                "TolX",
            ):
                fit_options[name] = self._option_widget_value(name)

        return fit_type_order, fit_options

    def fit_curve(self, x, y):
        """Fit curve using the selected model and options."""

        fit_type_order, fit_options = self.fit_parameters()
        return matlab_adapter.fit_curve_isolated(
            x,
            y,
            fit_type_order,
            fit_options,
        )


class PyScipyFitOptionsWidget(_FitOptionsWidgetBase):
    """Provide the py scipy fit options widget Qt widget."""

    engine = "Python"
    engine_label = "SciPy"

    def __init__(self, parent=None, fit_type_name='poly'):
        super().__init__(parent=parent, fit_type_name=fit_type_name)

    @classmethod
    def fit_type_groups(cls):
        """Fit type groups using the selected model and options."""

        return scipy_fit_adapter.FIT_TYPES

    def fallback_fit_info(self, fit_type: str):
        """Return fit metadata when an optional backend is unavailable."""

        return scipy_fit_adapter.get_func_info(fit_type)

    def default_method(self, fit_type: str):
        """Return the default method."""

        return scipy_fit_adapter.default_fit_options(fit_type)["Method"]

    def default_fit_options(self, fit_type: str, coefficients):
        """Return the default fit options."""

        return scipy_fit_adapter.default_fit_options(fit_type)

    def _add_engine_option_widgets(self, method: str):
        if method == scipy_fit_adapter.LINEAR_METHOD:
            self._add_option_row("Tol", self._line_option(self.option_metadata.get("Tol", 1e-10)))
            self._add_option_row("MaxIter", self._line_option(self.option_metadata.get("MaxIter")))
            return

        self._add_option_row(
            "OptimizerMethod",
            self._combo_option(
                list(scipy_fit_adapter.SCIPY_NONLINEAR_METHODS),
                self._option_text(self.option_metadata.get("OptimizerMethod"), "trf"),
            ),
        )
        self._add_option_row(
            "Loss",
            self._combo_option(
                list(scipy_fit_adapter.SCIPY_LOSSES),
                self._option_text(self.option_metadata.get("Loss"), "linear"),
            ),
        )
        for name, default in (
            ("FScale", 1.0),
            ("MaxNfev", None),
            ("FTol", 1e-8),
            ("XTol", 1e-8),
            ("GTol", 1e-8),
            ("DiffStep", None),
            ("XScale", 1.0),
        ):
            self._add_option_row(name, self._line_option(self.option_metadata.get(name, default)))

    def load_expression(self, text):
        """Load expression."""

        self._apply_fit_info(scipy_fit_adapter.get_func_info(text))
        self.order_input.setEnabled(True)

    def _option_widget_value(self, name):
        widget = self.option_widgets.get(name)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QLabel):
            return widget.text()
        if not isinstance(widget, QLineEdit):
            return None
        text = widget.text().strip()
        if not text:
            return None
        if name == "XScale" and text.lower() == "jac":
            return "jac"
        if name in {"MaxNfev", "MaxIter"}:
            try:
                return int(text)
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer.") from exc
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be a number.") from exc
        if not np.isfinite(number):
            raise ValueError(f"{name} must be finite.")
        return number

    def _advanced_fit_parameters(self, fit_type_order):
        self.get_coef_limit()
        method = self.option_metadata.get("Method", self.default_method(fit_type_order))
        fit_options = {
            "Method": method,
            "Lower": list(self.coeff_down_limit),
            "Upper": list(self.coeff_up_limit),
        }
        if self._has_start_point(method) and any(value is not None for value in self.start_point):
            fit_options["StartPoint"] = [float(value) for value in self.start_point if value is not None]

        if method == scipy_fit_adapter.LINEAR_METHOD:
            for name in ("Tol", "MaxIter"):
                value = self._option_widget_value(name)
                if value is not None:
                    fit_options[name] = value
        else:
            for name in (
                "OptimizerMethod",
                "Loss",
                "FScale",
                "MaxNfev",
                "FTol",
                "XTol",
                "GTol",
                "DiffStep",
                "XScale",
            ):
                value = self._option_widget_value(name)
                if value is not None:
                    fit_options[name] = value

        return fit_type_order, fit_options

    def fit_curve(self, x, y):
        """Fit curve using the selected model and options."""

        fit_type_order, fit_options = self.fit_parameters()
        return scipy_fit_adapter.fit_curve(
            x,
            y,
            fit_type_order,
            fit_options,
        )
