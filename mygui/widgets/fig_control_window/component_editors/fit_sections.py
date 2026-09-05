"""Edit fit inputs, actions, results, and display ranges."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.application_theme import bind_widget_qss, subscribe_theme_window
from mygui.figuremodify.components import FitCurveController, FitEngine
from mygui.widgets.ui_components import UiVariant, annotate_sections, set_busy_state, style_button
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from .common import RangeEditor
from .context import EditorContext, perform_editor_action
from .inspector import EditorSection
from .inspector_layout import (
    apply_expanding_field,
    configure_inspector_result_table,
    inspector_formula_height,
    labeled_form_row,
    set_inspector_table_text,
    size_inspector_result_table,
)
from .lifecycle import CallbackLifecycle

from mygui import status_messages
from mygui.database import ColumnRef, matlab_adapter, select_fit_input_pair
from mygui.widgets.fig_control_window.py_fit_options_window import (
    FitDataRangeWidget,
    PyMatlabFitOptionsWidget,
    PyScipyFitOptionsWidget,
)
import math
import weakref
from copy import deepcopy

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
        self.setObjectName("fit_domain_section")

        self.controller = controller
        self.context = context
        self.repository = context.repository
        state = _controller_state(controller)
        data = state.data
        self._disposed = False
        self._fit_dialogs = []
        self._lifecycle = CallbackLifecycle()

        self.layout = QVBoxLayout()

        self.engine_widget = QWidget(self)
        self.engine_layout = QHBoxLayout(self.engine_widget)
        self.engine_layout.setContentsMargins(0, 0, 0, 0)
        self.scipy_button = QPushButton("SciPy", self.engine_widget)
        style_button(self.scipy_button, variant=UiVariant.OUTLINE)
        apply_expanding_field(self.scipy_button)
        self.matlab_button = QPushButton("Matlab", self.engine_widget)
        style_button(self.matlab_button, variant=UiVariant.OUTLINE)
        apply_expanding_field(self.matlab_button)
        self.scipy_button.clicked.connect(
            lambda: self.open_fit_window(FitEngine.PYTHON)
        )
        self.matlab_button.clicked.connect(
            lambda: self.open_fit_window(FitEngine.MATLAB)
        )
        self.engine_layout.addWidget(
            labeled_form_row(
                "Engine:", buddy=self.scipy_button, parent=self.engine_widget
            )
        )
        self.engine_layout.addWidget(self.scipy_button)
        self.engine_layout.addWidget(self.matlab_button)
        self.engine_layout.addStretch()

        self._matlab_state_listener = self._matlab_enabled_changed

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
        self.result_formula_input.setFixedHeight(inspector_formula_height())

        self.result_coeff_table = QTableWidget(self)
        self.result_coeff_table.setColumnCount(4)
        self.result_coeff_table.setHorizontalHeaderLabels(["Coefficient", "Value", "Lower", "Upper"])
        self.result_coeff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        configure_inspector_result_table(self.result_coeff_table)

        self.result_goodness_table = QTableWidget(self)
        self.result_goodness_table.setColumnCount(2)
        self.result_goodness_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.result_goodness_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        configure_inspector_result_table(self.result_goodness_table)

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
        annotate_sections(self)
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
        try:
            matlab_adapter.register_matlab_state_listener(
                self._matlab_state_listener
            )
            self._lifecycle.add(
                lambda: matlab_adapter.unregister_matlab_state_listener(
                    self._matlab_state_listener
                )
            )
            lifecycle = self._lifecycle
            self.destroyed.connect(lambda *_args: lifecycle.close())
            self._matlab_enabled_changed(
                matlab_adapter.is_matlab_enabled()
            )
        except Exception:
            self._lifecycle.close()
            raise

    def expression_change(self):
        """Apply the expression change emitted by the corresponding control."""

        return True

    def _engine_display_name(self, engine: FitEngine | str) -> str:
        engine = FitEngine(engine)
        return "SciPy" if engine is FitEngine.PYTHON else engine.value

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
            pair = self.context.fitting.resolve_sources(self.controller)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        if pair.x.size == 0:
            raise ValueError(
                "X Data and Y Data have no valid row pairs after preprocessing."
            )
        x_values = pair.x.tolist()
        y_values = pair.y.tolist()
        return (
            self.repository.ref_label(x_ref),
            self.repository.ref_label(y_ref),
            x_values,
            y_values,
            min(x_values),
            max(x_values),
            pair.excluded_count,
        )

    def open_fit_window(self, engine: FitEngine | str):
        """Open fit window."""

        if self._disposed:
            return None
        try:
            engine = FitEngine(engine)
        except ValueError as exc:
            raise ValueError(
                f"Unsupported fitting engine: {engine}"
            ) from exc
        display_engine = self._engine_display_name(engine)
        if (
            engine is FitEngine.MATLAB
            and not matlab_adapter.is_matlab_enabled()
        ):
            status_messages.show_error("Connect MATLAB before using Matlab fitting.")
            return None
        try:
            (
                x_name,
                y_name,
                x_values,
                y_values,
                x_min,
                x_max,
                excluded_count,
            ) = self._current_fit_data()
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return None

        dialog = QDialog(self)
        dialog.setObjectName("fit_dialog")
        bind_widget_qss(
            dialog,
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss",
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setModal(False)
        dialog.setWindowTitle(f"{display_engine} Fit")

        dialog_layout = QVBoxLayout(dialog)
        fit_type_box = QGroupBox("Fit Type", dialog)
        fit_type_layout = QVBoxLayout()
        dialog.fit_type_input = QComboBox(dialog)
        options_widget_class = (
            PyScipyFitOptionsWidget
            if engine is FitEngine.PYTHON
            else PyMatlabFitOptionsWidget
        )
        fit_type_groups = options_widget_class.fit_type_groups()
        dialog.fit_type_input.addItems(list(fit_type_groups.keys()))
        fit_type_layout.addWidget(dialog.fit_type_input)
        fit_type_box.setLayout(fit_type_layout)
        dialog_layout.addWidget(fit_type_box)

        dialog.fit_range_widget = FitDataRangeWidget(dialog)
        dialog.fit_range_widget.set_available_range(x_min, x_max)
        dialog.fit_range_widget.set_range_spec(
            _controller_data(self.controller, "fit_input_range")
        )
        dialog_layout.addWidget(dialog.fit_range_widget)

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
        style_button(dialog.fit_button, variant=UiVariant.PRIMARY)
        dialog.close_button = QPushButton("Close", dialog)
        style_button(dialog.close_button, variant=UiVariant.OUTLINE)
        dialog.fit_button.clicked.connect(lambda: self._start_fit_from_dialog(dialog, engine))
        dialog.close_button.clicked.connect(dialog.close)
        button_layout.addWidget(dialog.fit_button)
        button_layout.addWidget(dialog.close_button)
        dialog_layout.addLayout(button_layout)
        annotate_sections(dialog)

        self._fit_dialogs.append(dialog)
        subscribe_theme_window(dialog)
        dialog.destroyed.connect(lambda *_args, target=dialog: self._forget_fit_dialog(target))
        dialog.show()
        return dialog

    def _forget_fit_dialog(self, dialog):
        try:
            self._fit_dialogs.remove(dialog)
        except ValueError:
            pass

    def _start_fit_from_dialog(self, dialog, engine: FitEngine):
        if self._disposed:
            return
        from mygui.widgets.fig_control_window.background_task import start_background_task

        display_engine = self._engine_display_name(engine)
        try:
            pair = self.context.fitting.resolve_sources(self.controller)
            range_spec = dialog.fit_range_widget.range_spec()
            selected = select_fit_input_pair(pair, range_spec, require_data=True)
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
        set_busy_state(dialog.fit_button, True, busy_text="Fitting…")
        if selected.excluded_count and pair.excluded_count:
            status_messages.show_warning(
                f"{display_engine} fitting started; preprocessing excluded "
                f"{pair.excluded_count} rows, range excluded {selected.excluded_count} rows."
            )
        elif selected.excluded_count:
            status_messages.show_warning(
                f"{display_engine} fitting started; range excluded "
                f"{selected.excluded_count} rows."
            )
        elif pair.excluded_count:
            status_messages.show_warning(
                f"{display_engine} fitting started; preprocessing excluded "
                f"{pair.excluded_count} rows."
            )
        else:
            status_messages.show_message(
                f"{display_engine} fitting started.",
                "info",
            )

        x_ref = ColumnRef.from_dict(self.controller.state.data["x_ref"])
        y_ref = ColumnRef.from_dict(self.controller.state.data["y_ref"])
        matlab_adapter.matlab_logger().info(
            "%s fit request started request_id=%s fit_type=%s x_data=%s y_data=%s x_len=%s y_len=%s",
            display_engine,
            request_id,
            fit_type_order,
            self.repository.ref_label(x_ref),
            self.repository.ref_label(y_ref),
            len(selected.x),
            len(selected.y),
        )
        from mygui.template_library.fit_execution import FitExecutionService

        fit_func = FitExecutionService().execute_arrays
        dialog_ref = weakref.ref(dialog)
        fit_options_record = deepcopy(fit_options)
        range_spec_record = range_spec.to_dict()
        start_background_task(
            self,
            fit_func,
            lambda result, rid=request_id, dref=dialog_ref, xmin=selected.x_start, xmax=selected.x_stop, rspec=range_spec_record: self._fit_dialog_succeeded(
                dref,
                rid,
                result,
                xmin,
                xmax,
                engine,
                fit_type_order,
                fit_options_record,
                fit_input_range=rspec,
            ),
            lambda message, rid=request_id, dref=dialog_ref: self._fit_dialog_failed(dref, rid, message, engine),
            selected.x,
            selected.y,
            fit_type_order,
            fit_options,
            logger=matlab_adapter.matlab_logger(),
            task_log_prefix=f"{display_engine} fit task",
            engine=engine,
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
                set_busy_state(dialog.fit_button, False)
        except RuntimeError:
            return False
        return True

    def _fit_dialog_succeeded(
        self,
        dialog_ref,
        request_id,
        result,
        x_min,
        x_max,
        engine: FitEngine,
        fit_type=None,
        fit_options=None,
        fit_input_range=None,
    ):
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
            fit_input_range=fit_input_range,
        ):
            status_messages.show_success(
                f"{self._engine_display_name(engine)} fitting completed."
            )

    def _fit_dialog_failed(self, dialog_ref, request_id, message, engine: FitEngine):
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
            return "N/A"
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
        set_inspector_table_text(
            table,
            row,
            column,
            self._format_result_number(value),
        )

    def _populate_fit_result(self, fit_result):
        state_engine = _controller_data(
            self.controller,
            "engine",
            FitEngine.PYTHON.value,
        )
        engine = fit_result.get("engine", state_engine)
        try:
            engine = FitEngine(engine)
        except ValueError:
            engine = state_engine
        self.result_engine_label.setText(
            f"Engine: {self._engine_display_name(engine)}"
        )
        self.result_model_label.setText(f"Model: {fit_result.get('fit_type', '-')}")
        self.result_formula_input.setPlainText(str(fit_result.get("formula", "")))

        coefficients = list(fit_result.get("coefficients") or [])
        self.result_coeff_table.setRowCount(len(coefficients))
        for row, coefficient in enumerate(coefficients):
            set_inspector_table_text(
                self.result_coeff_table,
                row,
                0,
                str(coefficient.get("name", "")),
            )
            self._set_table_item(self.result_coeff_table, row, 1, coefficient.get("value"))
            self._set_table_item(self.result_coeff_table, row, 2, coefficient.get("lower"))
            self._set_table_item(self.result_coeff_table, row, 3, coefficient.get("upper"))
        size_inspector_result_table(self.result_coeff_table)

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
            set_inspector_table_text(self.result_goodness_table, row, 0, label)
            self._set_table_item(self.result_goodness_table, row, 1, goodness.get(key))
        size_inspector_result_table(self.result_goodness_table)

    def update_curve(
        self,
        fit_result,
        *args,
        engine=None,
        fit_type=None,
        fit_options=None,
        fit_input_range=None,
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
        fit_input_range = (
            state_data.get("fit_input_range")
            if fit_input_range is None
            else fit_input_range
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
        result = perform_editor_action(self.context,
            "Apply Fit Result",
            lambda: self.context.fitting.apply_result(
                self.controller,
                engine=engine,
                fit_type=fit_type,
                fit_options=fit_options,
                fit_result=stored_result,
                expression=value_expression,
                x_start=x_start,
                x_stop=x_stop,
                fit_input_range=fit_input_range,
            ),
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
        result = perform_editor_action(self.context,
            "Change Fit Display Range",
            lambda: self.context.fitting.update_display_range(
                self.controller,
                x_start,
                x_stop,
            ),
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
        self._lifecycle.close()
        dialogs = tuple(self._fit_dialogs)
        self._fit_dialogs.clear()
        for dialog in dialogs:
            try:
                dialog.close()
            except RuntimeError:
                pass


class FitSectionProxy(QFrame, EditorSection):
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
