"""Edit fit inputs, actions, results, and display ranges."""

from __future__ import annotations

from Qt_core import *

from code.widgets import qss_func
from code.figuremodify.components import FitCurveController
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from .common import RangeEditor
from .context import EditorContext

from code import status_messages
from code.database import ColumnRef, matlab_adapter
import math
import os
import weakref
from copy import deepcopy

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.normpath(
    os.path.join(
        current_path,
        "..",
        "all_mod_widgets",
        "chart_mod_style.qss",
    )
)


def _controller_state(controller):
    return controller.read_state()


def _controller_data(controller, key: str, fallback=None):
    return _controller_state(controller).data.get(key, fallback)


class FitDomainSection(QFrame):
    """Provide the fit domain section Qt widget."""

    def __init__(
        self,
        controller: FitCurveController,
        *,
        context: EditorContext,
        color_library: ColorLibrary | None = None,
        parent=None,
    ):
        super().__init__(parent)
        del color_library

        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.controller = controller
        self.context = context
        self.repository = context.repository
        state = _controller_state(controller)
        data = state.data
        self._disposed = False
        self._fit_dialogs = []

        self.layout = QVBoxLayout()

        self.engine_widget = QWidget(self)
        self.engine_layout = QHBoxLayout(self.engine_widget)
        self.engine_layout.setContentsMargins(0, 0, 0, 0)
        self.scipy_button = QPushButton("SciPy", self.engine_widget)
        self.matlab_button = QPushButton("Matlab", self.engine_widget)
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
        self.expression_input.setPlainText(str(data["expression"]))
        self.expression_layout.addWidget(self.expression_input)

        self.expression_box.setLayout(self.expression_layout)

        self.result_box = QGroupBox("Fit Result", self)
        self.result_layout = QVBoxLayout()
        self.result_engine_label = QLabel(
            f"Engine: {self._engine_display_name(data['engine'])}"
        )
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

        self.range_editor = RangeEditor(
            data["x_start"],
            data["x_stop"],
            lower_label="X Start:",
            upper_label="X Stop:",
            parent=self,
        )
        self.x_start_input = self.range_editor.minimum_input
        self.x_stop_input = self.range_editor.maximum_input
        self.range_editor.rangeChanged.connect(self._range_change)

        self.layout.addWidget(self.engine_widget)
        self.layout.addWidget(self.expression_box)
        self.layout.addWidget(self.result_box)
        self.layout.addWidget(self.range_editor)

        # Add stretch spacer
        self.layout.addStretch()

        self.setLayout(self.layout)
        if isinstance(data["fit_result"], dict):
            self._populate_fit_result(data["fit_result"])
            show_expression = str(
                data["fit_result"].get(
                    "show_expression",
                    data["expression"],
                )
            )
            self.expression_input.blockSignals(True)
            self.expression_input.setPlainText(show_expression)
            self.expression_input.blockSignals(False)

    def expression_change(self):
        """Apply the expression change emitted by the corresponding control."""

        return True

    def _engine_display_name(self, engine: str) -> str:
        return "SciPy" if engine == "Python" else engine

    def _matlab_enabled_changed(self, enabled: bool):
        if self._disposed:
            return
        self.matlab_button.setEnabled(bool(enabled))
        if enabled:
            self.matlab_button.setToolTip("")
        else:
            self.matlab_button.setToolTip("Connect MATLAB from the Matlab panel first.")

    def _current_fit_data(self):
        state = _controller_state(self.controller)
        x_ref = ColumnRef.from_dict(state.data["x_ref"])
        y_ref = ColumnRef.from_dict(state.data["y_ref"])
        try:
            pair = self.repository.valid_pair(x_ref, y_ref)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        if pair.x.size == 0:
            raise ValueError("X Data and Y Data have no valid row pairs.")
        if pair.missing_count:
            status_messages.show_warning(f"Fit ignored {pair.missing_count} rows with missing values.")
        x_values = pair.x.tolist()
        y_values = pair.y.tolist()
        return (
            self.repository.ref_label(x_ref),
            self.repository.ref_label(y_ref),
            x_values,
            y_values,
            min(x_values),
            max(x_values),
        )

    def open_fit_window(self, engine: str):
        """Open fit window."""

        if self._disposed:
            return None
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
        if self._disposed:
            return
        from code.database import scipy_fit_adapter
        from code.widgets.fig_control_window.background_task import start_background_task

        display_engine = self._engine_display_name(engine)
        try:
            x_name, y_name, x_values, y_values, x_min, x_max = self._current_fit_data()
            fit_type_order, fit_options = dialog.fit_options_widget.fit_parameters()
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return

        request_id = self.context.fitting.next_request(
            self.controller.component_id
        )
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
        fit_options_record = deepcopy(fit_options)
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
                fit_type_order,
                fit_options_record,
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

    def _fit_dialog_succeeded(self, dialog_ref, request_id, result, x_min, x_max, engine: str,
                              fit_type=None, fit_options=None):
        if self._disposed:
            return
        if not self._restore_dialog_fit_button(dialog_ref, request_id):
            return
        if not self.context.fitting.request_is_current(
            self.controller.component_id,
            request_id,
        ):
            return
        if self.update_curve(
            result,
            x_min,
            x_max,
            engine=engine,
            fit_type=fit_type,
            fit_options=fit_options,
        ):
            status_messages.show_success(
                f"{self._engine_display_name(engine)} fitting completed."
            )

    def _fit_dialog_failed(self, dialog_ref, request_id, message, engine: str):
        if self._disposed:
            return
        if not self._restore_dialog_fit_button(dialog_ref, request_id):
            return
        if not self.context.fitting.request_is_current(
            self.controller.component_id,
            request_id,
        ):
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
        state_engine = _controller_data(
            self.controller,
            "engine",
            "Python",
        )
        engine = fit_result.get("engine", state_engine)
        if engine not in {"Python", "Matlab"}:
            engine = state_engine
        self.result_engine_label.setText(
            f"Engine: {self._engine_display_name(engine)}"
        )
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

    def update_curve(
        self,
        fit_result,
        *args,
        engine=None,
        fit_type=None,
        fit_options=None,
    ):
        """Update curve."""

        state_data = _controller_state(self.controller).data
        engine = engine or state_data["engine"]
        fit_type = (
            state_data["fit_type"]
            if fit_type is None
            else fit_type
        )
        fit_options = (
            state_data["fit_options"]
            if fit_options is None
            else fit_options
        )
        if isinstance(fit_result, dict):
            if len(args) < 2:
                raise TypeError("update_curve requires x_start and x_stop")
            x_start, x_stop = args[0], args[1]
            stored_result = deepcopy(fit_result)
            fit_type = stored_result.get("fit_type", fit_type)
            value_expression = stored_result.get(
                "value_expression",
                "",
            )
            show_expression = stored_result.get(
                "show_expression",
                value_expression,
            )
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
            stored_result = None
        result = self.context.fitting.apply_result(
            self.controller,
            engine=engine,
            fit_type=fit_type,
            fit_options=fit_options,
            fit_result=stored_result,
            expression=value_expression,
            x_start=x_start,
            x_stop=x_stop,
        )
        if not self.context.messages.present(result):
            self.sync_from_controller()
            return False
        blocker = QSignalBlocker(self.expression_input)
        self.expression_input.setPlainText(str(show_expression))
        del blocker
        self.range_editor.set_range(x_start, x_stop)
        if isinstance(stored_result, dict):
            self._populate_fit_result(stored_result)
        return True

    def x_start_change(self):
        """Apply the x start change emitted by the corresponding control."""

        return self._range_change(self.x_start_input.value(), self.x_stop_input.value())

    def x_stop_change(self):
        """Apply the x stop change emitted by the corresponding control."""

        return self._range_change(self.x_start_input.value(), self.x_stop_input.value())

    def _range_change(self, x_start, x_stop):
        data = _controller_state(self.controller).data
        if (
            float(x_start) == float(data["x_start"])
            and float(x_stop) == float(data["x_stop"])
        ):
            return True
        result = self.context.fitting.update_display_range(
            self.controller,
            x_start,
            x_stop,
        )
        if not self.context.messages.present(
            result,
            success="Fit display range updated.",
        ):
            data = _controller_state(self.controller).data
            self.range_editor.set_range(
                data["x_start"],
                data["x_stop"],
            )
            return False
        return True

    def sync_from_controller(self):
        """Refresh controls from authoritative Controller state."""

        state = _controller_state(self.controller)
        data = state.data
        fit_result = data.get("fit_result")
        show_expression = data.get("expression", "")
        if isinstance(fit_result, dict):
            show_expression = fit_result.get(
                "show_expression",
                show_expression,
            )
            self._populate_fit_result(fit_result)
        blocker = QSignalBlocker(self.expression_input)
        self.expression_input.setPlainText(str(show_expression))
        del blocker
        self.range_editor.set_range(
            data["x_start"],
            data["x_stop"],
        )

    def dispose(self):
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        self.context.fitting.cancel(self.controller.component_id)
        matlab_adapter.unregister_matlab_state_listener(
            self._matlab_state_listener
        )
        dialogs = tuple(self._fit_dialogs)
        self._fit_dialogs.clear()
        for dialog in dialogs:
            try:
                dialog.close()
            except RuntimeError:
                pass


class FitSectionProxy(QFrame):
    """Place one view of a shared fit coordinator into an Inspector section."""

    PARTS = {"actions", "result", "range"}

    def __init__(
        self,
        controller: FitCurveController,
        *,
        context: EditorContext,
        part: str,
        parent=None,
    ):
        if part not in self.PARTS:
            raise ValueError(f"Unsupported fit section: {part}")
        super().__init__(parent)
        self.part = part
        owner = parent
        domain = owner.__dict__.get("_fit_domain_coordinator")
        if domain is None:
            domain = FitDomainSection(
                controller,
                context=context,
                parent=owner,
            )
            domain.setVisible(False)
            owner.__dict__["_fit_domain_coordinator"] = domain
        self.domain = domain

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if part == "actions":
            domain.layout.removeWidget(domain.engine_widget)
            layout.addWidget(domain.engine_widget)
        elif part == "result":
            domain.layout.removeWidget(domain.expression_box)
            domain.layout.removeWidget(domain.result_box)
            layout.addWidget(domain.expression_box)
            layout.addWidget(domain.result_box)
        else:
            domain.layout.removeWidget(domain.range_editor)
            layout.addWidget(domain.range_editor)

    def sync_from_controller(self):
        """Refresh controls from authoritative Controller state."""

        if self.part == "actions":
            self.domain.sync_from_controller()

    def dispose(self):
        """Disconnect callbacks and release resources owned by this object."""

        if self.part == "actions":
            self.domain.dispose()

class FitActionsSection(FitSectionProxy):
    """Edit the fit actions properties of a component."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(
            controller,
            context=context,
            part="actions",
            parent=parent,
        )


class FitResultSection(FitSectionProxy):
    """Edit the fit result properties of a component."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(
            controller,
            context=context,
            part="result",
            parent=parent,
        )


class FitDisplayRangeSection(FitSectionProxy):
    """Edit the fit display range properties of a component."""

    def __init__(self, controller, *, context, parent=None):
        super().__init__(
            controller,
            context=context,
            part="range",
            parent=parent,
        )
