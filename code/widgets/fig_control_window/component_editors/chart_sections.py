"""Edit function-curve and interpolation component options."""

from __future__ import annotations

import os

from Qt_core import *

from code.database import ColumnRef
from code.figuremodify.components import (
    FunctionCurveController,
    InterpolationController,
)
from code.widgets import qss_func
from code.widgets.common_widget.min_widget.color_library import ColorLibrary

from .common import DebouncedTextBinding, RangeEditor
from .context import EditorContext
from .inputs import InterpolationOptionsInput
from .inspector import EditorSection


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


class FunctionCurveSection(QFrame, EditorSection):
    """Provide the function curve section Qt widget."""

    TEXT_DEBOUNCE_MS = 250

    def __init__(
        self,
        controller: FunctionCurveController,
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
        state = _controller_state(controller)

        self.layout = QVBoxLayout()

        self.expression_box = QGroupBox("Expression", self)
        self.expression_box.setMinimumHeight(80)
        self.expression_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        self.expression_layout = QVBoxLayout()

        self.expression_input = QLineEdit(self)
        self.expression_input.setText(str(state.data["expression"]))
        self.expression_layout.addWidget(self.expression_input)
        self._expression_binding = DebouncedTextBinding(
            self.expression_input,
            self._update_expression,
            delay_ms=self.TEXT_DEBOUNCE_MS,
            result_presenter=lambda result: self.context.messages.present(
                result,
                success="Curve expression updated.",
            ),
            parent=self,
        )
        self.expression_box.setLayout(self.expression_layout)

        self.range_editor = RangeEditor(
            state.data["x_start"],
            state.data["x_stop"],
            lower_label="X Start:",
            upper_label="X Stop:",
            parent=self,
        )
        self.x_start_input = self.range_editor.minimum_input
        self.x_stop_input = self.range_editor.maximum_input
        self.range_editor.rangeChanged.connect(self._range_change)

        self.layout.addWidget(self.expression_box)
        self.layout.addWidget(self.range_editor)
        self.layout.addStretch()
        self.setLayout(self.layout)

    def expression_change(self):
        """Apply the expression change emitted by the corresponding control."""

        return self._expression_binding.flush()

    def _update_expression(self, expression: str):
        data = _controller_state(self.controller).data
        return self.context.function_curves.update(
            self.controller,
            expression,
            data["x_start"],
            data["x_stop"],
        )

    def _range_change(self, x_start, x_stop):
        data = _controller_state(self.controller).data
        if (
            float(x_start) == float(data["x_start"])
            and float(x_stop) == float(data["x_stop"])
        ):
            return True
        result = self.context.function_curves.update(
            self.controller,
            data["expression"],
            x_start,
            x_stop,
        )
        if not self.context.messages.present(
            result,
            success="Curve range updated.",
        ):
            data = _controller_state(self.controller).data
            self.range_editor.set_range(
                data["x_start"],
                data["x_stop"],
            )
            return False
        return True

    def x_start_change(self):
        """Apply the x start change emitted by the corresponding control."""

        return self._range_change(
            self.x_start_input.value(),
            self.x_stop_input.value(),
        )

    def x_stop_change(self):
        """Apply the x stop change emitted by the corresponding control."""

        return self._range_change(
            self.x_start_input.value(),
            self.x_stop_input.value(),
        )

    def sync_from_controller(self):
        """Refresh controls from authoritative Controller state."""

        state = _controller_state(self.controller)
        self._expression_binding.set_text(state.data["expression"])
        self.range_editor.set_range(
            state.data["x_start"],
            state.data["x_stop"],
        )

    def dispose(self):
        """Disconnect callbacks and release resources owned by this object."""

        self._expression_binding.cancel()


class InterpolationSection(QFrame, EditorSection):
    """Provide the interpolation section Qt widget."""

    def __init__(
        self,
        controller: InterpolationController,
        *,
        context: EditorContext,
        color_library: ColorLibrary | None = None,
        parent=None,
    ):
        super().__init__(parent)
        del color_library

        self.controller = controller
        self.context = context
        data = _controller_state(controller).data

        self.layout = QVBoxLayout()
        self.interpolat_box = QGroupBox("Interpolation")
        self.interpolat_layout = QVBoxLayout()

        self.options_input = InterpolationOptionsInput(
            method=data["method"],
            samples=int(data["samples"]),
            k=int(data["k"]),
            lam=data["lam"],
            lam_auto=bool(data["lam_auto"]),
            parent=self,
        )
        self.interpolat_input = self.options_input.method_input
        self.samples_input = self.options_input.samples_input
        self.k_widget = self.options_input.k_widget
        self.k_input = self.options_input.k_input
        self.lambda_widget = self.options_input.lambda_widget
        self.lambda_auto_input = self.options_input.lambda_auto_input
        self.lambda_value_input = self.options_input.lambda_value_input
        self.interpolat_layout.addWidget(self.options_input)

        self.interpolat_layout.addStretch()
        self.interpolat_box.setLayout(self.interpolat_layout)
        self.layout.addWidget(self.interpolat_box)
        self.layout.addStretch()
        self.setLayout(self.layout)

        self.options_input.optionsChanged.connect(self.interpolat_change)

    def _current_lambda(self, method: str):
        del method
        return self.options_input.lambda_options()

    def _update_option_visibility(self):
        self.options_input.update_option_visibility()

    def change_method(self):
        """Change method."""

        self._update_option_visibility()

    def lambda_auto_changed(self, checked: bool):
        """Apply the lambda auto changed emitted by the corresponding control."""

        self.lambda_value_input.setEnabled(not checked)
        self.interpolat_change()

    def interpolat_change(self):
        """Apply the interpolat change emitted by the corresponding control."""

        options = self.options_input.options()
        state = _controller_state(self.controller)
        x_ref = ColumnRef.from_dict(state.data["x_ref"])
        y_ref = ColumnRef.from_dict(state.data["y_ref"])
        result = self.context.interpolation.configure(
            self.controller,
            x_ref=x_ref,
            y_ref=y_ref,
            preprocess=state.data["preprocess"],
            **options,
        )
        if not self.context.messages.present(
            result,
            success="Interpolation curve updated.",
        ):
            data = _controller_state(self.controller).data
            self.options_input.set_options(
                method=data["method"],
                k=data["k"],
                samples=data["samples"],
                lam=data["lam"],
                lam_auto=data["lam_auto"],
            )
            return False
        return True

    def sync_from_controller(self):
        """Refresh controls from authoritative Controller state."""

        data = _controller_state(self.controller).data
        self.options_input.set_options(
            method=data["method"],
            k=data["k"],
            samples=data["samples"],
            lam=data["lam"],
            lam_auto=data["lam_auto"],
        )
