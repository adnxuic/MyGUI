"""Collect inputs for creating chart components."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mygui.widgets.figure_canvas.py_figure_window import PyFigureWindow
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from mygui.widgets.fig_control_window.component_editors import (
    DataReferenceInput,
    InterpolationOptionsInput,
    LineAppearanceInput,
    MultiSeriesDataReferenceInput,
    ScatterStyleEditor,
)
from mygui.resources import load_qss_resource

from mygui.database import (
    ColumnRef,
    DataPreprocessSpec,
    resolve_preprocessed_pair,
)
from mygui.figuremodify.style_base.creation_defaults import (
    resolve_component_creation_defaults,
)
from mygui import status_messages
from mygui.resources import icon_path

def _selected_ref(combo: QComboBox) -> ColumnRef | None:
    value = combo.currentData(Qt.UserRole)
    return value if isinstance(value, ColumnRef) else None


def _selected_pair(figure_window: PyFigureWindow, x_input: QComboBox, y_input: QComboBox,
                   preprocess=None, *, line_mode: bool = False):
    x_ref = _selected_ref(x_input)
    y_ref = _selected_ref(y_input)
    if x_ref is None or y_ref is None:
        raise ValueError("Please select X Data and Y Data.")
    spec = DataPreprocessSpec.from_dict(preprocess)
    pair = resolve_preprocessed_pair(
        figure_window.repository,
        x_ref,
        y_ref,
        spec,
        preserve_gaps=line_mode,
    )
    if not pair.valid_mask.any():
        raise ValueError(
            "X Data and Y Data have no valid row pairs after preprocessing."
        )
    return x_ref, y_ref, pair, spec


def _show_creation_result(name: str, pair) -> None:
    if pair.excluded_count:
        status_messages.show_warning(
            f"{name} created; preprocessing ignored or masked "
            f"{pair.excluded_count} rows."
        )
    else:
        status_messages.show_success(f"{name} created.")


def _show_batch_creation_result(name: str, result) -> None:
    count = len(result.component_ids)
    noun = "curve" if count == 1 else "curves"
    total_excluded = sum(result.excluded_counts)
    affected = sum(value > 0 for value in result.excluded_counts)
    if total_excluded:
        status_messages.show_warning(
            f"Created {count} {name} {noun}; preprocessing masked or "
            f"filtered {total_excluded} row pairs across {affected} {noun}."
        )
    else:
        status_messages.show_success(f"Created {count} {name} {noun}.")


def _update_batch_button(button: QPushButton, data_input) -> None:
    count = data_input.selected_count()
    button.setEnabled(count > 0)
    button.setText(f"Create ({count})")


def _new_color_input(figure_window: PyFigureWindow) -> ColorChoiceWidget:
    return ColorChoiceWidget(
        colorselector=figure_window.get_current_canvas_axes_colorselector(),
        color_library=figure_window.color_library,
        auto_record_recent=False,
    )


def _creation_defaults(figure_window: PyFigureWindow):
    canvas = getattr(figure_window, "current_canva", None)
    if canvas is None:
        return resolve_component_creation_defaults("default")
    return canvas.component_creation_defaults()


def _new_data_reference_input(
    figure_window: PyFigureWindow,
    parent=None,
) -> DataReferenceInput:
    canvas = figure_window.current_canva
    return DataReferenceInput(
        figure_window.repository,
        canvas.project_id if canvas is not None else None,
        parent=parent,
    )


def _new_multi_data_reference_input(
    figure_window: PyFigureWindow,
    parent=None,
) -> MultiSeriesDataReferenceInput:
    canvas = figure_window.current_canva
    return MultiSeriesDataReferenceInput(
        figure_window.repository,
        canvas.project_id if canvas is not None else None,
        parent=parent,
    )


def _new_line_appearance_input(
    figure_window: PyFigureWindow,
    *,
    parent=None,
    **kwargs,
) -> LineAppearanceInput:
    return LineAppearanceInput(
        colorselector=figure_window.get_current_canvas_axes_colorselector(),
        color_library=figure_window.color_library,
        parent=parent,
        **kwargs,
    )


def _commit_color_input(figure_window: PyFigureWindow, widget: ColorChoiceWidget) -> None:
    if figure_window.commit_current_canvas_color(
        widget.selection(),
        preview_cycle=widget.colorselector,
    ):
        figure_window.color_library.record_recent(widget.color())


# Curve creation dialog
class PyCurveDialog(QDialog):
    """Provide the py curve dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None, parent=None):
        super().__init__(parent)
        self.setObjectName("chart_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/curve.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)

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

        self.appearance_input = _new_line_appearance_input(
            figure_window,
            parent=self,
            label="x",
            style=self.creation_defaults.line.linestyle,
            linewidth=self.creation_defaults.line.linewidth,
            show_linewidth=False,
        )
        self.style_input = self.appearance_input.style_input
        self.color_input = self.appearance_input.color_input
        self.label_input = self.appearance_input.label_input
        self.layout.addWidget(self.appearance_input)

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
        """Validate the inputs and accept the dialog when they are usable."""

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
                                                       style=self.appearance_input.style(),
                                                       color=self.color_input.color(),
                                                       label=self.label_input.text(),
                                                       color_selection=self.color_input.selection(),
                                                       preview_cycle=self.color_input.colorselector)
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid Expression', str(exc))
            return
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        super().reject()


# Line plot dialog
class PyPlotDialog(QDialog):
    """Provide the py plot dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None, parent=None):
        super().__init__(parent)
        self.setObjectName("chart_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/plot.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)

        self.layout = QVBoxLayout()

        self.data_reference_input = _new_multi_data_reference_input(
            self.figure_window,
            parent=self,
        )
        self.x_data_input = self.data_reference_input.x_data_input
        self.y_data_input = self.data_reference_input.y_data_input
        self.x_data_layout = self.data_reference_input.x_layout
        self.y_data_layout = self.data_reference_input.y_layout
        self.layout.addWidget(self.data_reference_input)

        self.appearance_input = _new_line_appearance_input(
            figure_window,
            parent=self,
            label="plot",
            style=self.creation_defaults.line.linestyle,
            linewidth=self.creation_defaults.line.linewidth,
            show_label=False,
        )
        self.line_style_editor = self.appearance_input.line_style_editor
        self.style_input = self.appearance_input.style_input
        self.linewidth_input = self.appearance_input.linewidth_input
        # Compatibility name retained for tests and callers that inspected
        # the former dialog field directly.
        self.size_input = self.linewidth_input
        self.linewidth_input.setRange(0.0, 1_000_000.0)
        self.linewidth_input.setSingleStep(0.1)
        self.color_input = self.appearance_input.color_input
        self.label_input = self.appearance_input.label_input
        self.layout.addWidget(self.appearance_input)

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

        self.data_reference_input.refsChanged.connect(
            lambda _x, _ys: _update_batch_button(
                self.ok_button, self.data_reference_input
            )
        )
        _update_batch_button(self.ok_button, self.data_reference_input)

        self.setLayout(self.layout)

    def accept(self):
        # Warn if current canvas is empty
        """Validate the inputs and accept the dialog when they are usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        try:
            result = self.figure_window.current_canva.add_plots(
                self.data_reference_input.get_x_ref(),
                self.data_reference_input.get_y_refs(),
                style=self.line_style_editor.style(),
                size=self.creation_defaults.line.markersize,
                linewidth=self.linewidth_input.value(),
                preprocess=self.data_reference_input.preprocess_values(),
                color_selection=self.color_input.selection(),
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            return

        _show_batch_creation_result("Plot", result)
        self.data_reference_input.dispose()
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        self.data_reference_input.dispose()
        super().reject()

    def closeEvent(self, event):
        """Dispose the batch selector when the dialog window closes."""

        self.data_reference_input.dispose()
        super().closeEvent(event)


# Scatter plot dialog
class PyScatterDialog(QDialog):
    """Provide the py scatter dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None, parent=None):
        super().__init__(parent)
        self.setObjectName("chart_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/scatter.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)

        self.layout = QVBoxLayout()

        self.data_reference_input = _new_multi_data_reference_input(
            self.figure_window,
            parent=self,
        )
        self.x_data_input = self.data_reference_input.x_data_input
        self.y_data_input = self.data_reference_input.y_data_input
        self.x_data_layout = self.data_reference_input.x_layout
        self.y_data_layout = self.data_reference_input.y_layout
        self.layout.addWidget(self.data_reference_input)

        self.scatter_style_editor = ScatterStyleEditor(
            marker=self.creation_defaults.scatter.marker,
            size=self.creation_defaults.scatter.size,
            parent=self,
        )
        self.size_input = self.scatter_style_editor.size_input
        self.style_input = self.scatter_style_editor.marker_input
        self.layout.addWidget(self.scatter_style_editor)

        # Color selection and preview
        self.color_input = _new_color_input(figure_window)
        self.layout.addWidget(QLabel('Color:'))
        self.layout.addWidget(self.color_input)

        # Compatibility-only hidden label input; batch labels come from Y.
        self.label_input = QLineEdit(self)
        self.label_input.setText('scatter')
        self.label_input.hide()

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

        self.data_reference_input.refsChanged.connect(
            lambda _x, _ys: _update_batch_button(
                self.ok_button, self.data_reference_input
            )
        )
        _update_batch_button(self.ok_button, self.data_reference_input)

        self.setLayout(self.layout)

    def accept(self):
        # Warn if current canvas is empty
        """Validate the inputs and accept the dialog when they are usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        try:
            result = self.figure_window.current_canva.add_scatters(
                self.data_reference_input.get_x_ref(),
                self.data_reference_input.get_y_refs(),
                size=self.size_input.value(),
                marker=self.scatter_style_editor.marker(),
                preprocess=self.data_reference_input.preprocess_values(),
                color_selection=self.color_input.selection(),
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            return

        _show_batch_creation_result("Scatter", result)
        self.data_reference_input.dispose()
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        self.data_reference_input.dispose()
        super().reject()

    def closeEvent(self, event):
        """Dispose the batch selector when the dialog window closes."""

        self.data_reference_input.dispose()
        super().closeEvent(event)


class PyFitDialog(QDialog):
    """Provide the py fit dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None, parent=None):
        super().__init__(parent)
        self.setObjectName("fit_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/fit.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)

        self.layout = QVBoxLayout()

        self.data_reference_input = _new_data_reference_input(
            self.figure_window,
            parent=self,
        )
        self.x_data_input = self.data_reference_input.x_data_input
        self.y_data_input = self.data_reference_input.y_data_input
        self.x_data_layout = self.data_reference_input.x_layout
        self.y_data_layout = self.data_reference_input.y_layout
        self.layout.addWidget(self.data_reference_input)

        self.appearance_input = _new_line_appearance_input(
            figure_window,
            parent=self,
            style=self.creation_defaults.line.linestyle,
            linewidth=self.creation_defaults.line.linewidth,
            show_label=False,
            show_style=False,
            show_linewidth=False,
        )
        self.color_input = self.appearance_input.color_input
        self.layout.addWidget(self.appearance_input)

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
        """Validate the inputs and accept the dialog when they are usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        try:
            x_ref, y_ref, pair, preprocess = _selected_pair(
                self.figure_window,
                self.x_data_input,
                self.y_data_input,
                self.data_reference_input.preprocess_values(),
            )
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return

        self.figure_window.current_canva.add_fit_curve(
            x=pair.x,
            y=pair.y,
            color=self.color_input.color(),
            label='fitting',
            x_ref=x_ref,
            y_ref=y_ref,
            preprocess=preprocess,
            color_selection=self.color_input.selection(),
            preview_cycle=self.color_input.colorselector,
        )

        _show_creation_result("Fit curve", pair)
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        super().reject()


class PyInterpolationDialog(QDialog):
    """Provide the py interpolation dialog Qt widget."""

    def __init__(self, dialog_name=None, figure_window: PyFigureWindow = None, parent=None):
        super().__init__(parent)
        self.setObjectName("interpolation_dialog")
        qss_file = load_qss_resource(
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
        )
        self.setStyleSheet(qss_file)

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/interpolation.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)

        self.layout = QVBoxLayout()

        self.data_reference_input = _new_multi_data_reference_input(
            self.figure_window,
            parent=self,
        )
        self.x_data_input = self.data_reference_input.x_data_input
        self.y_data_input = self.data_reference_input.y_data_input
        self.x_data_layout = self.data_reference_input.x_layout
        self.y_data_layout = self.data_reference_input.y_layout
        self.layout.addWidget(self.data_reference_input)

        self.appearance_input = _new_line_appearance_input(
            figure_window,
            parent=self,
            style=self.creation_defaults.line.linestyle,
            linewidth=self.creation_defaults.line.linewidth,
            show_label=False,
            show_style=False,
            show_linewidth=False,
        )
        self.color_input = self.appearance_input.color_input
        self.layout.addWidget(self.appearance_input)

        self.options_input = InterpolationOptionsInput(parent=self)
        self.method_input = self.options_input.method_input
        self.samples_input = self.options_input.samples_input
        self.k_widget = self.options_input.k_widget
        self.k_input = self.options_input.k_input
        self.lambda_widget = self.options_input.lambda_widget
        self.lambda_auto_input = self.options_input.lambda_auto_input
        self.lambda_value_input = self.options_input.lambda_value_input
        self.layout.addWidget(self.options_input)

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

        self.data_reference_input.refsChanged.connect(
            lambda _x, _ys: _update_batch_button(
                self.ok_button, self.data_reference_input
            )
        )
        _update_batch_button(self.ok_button, self.data_reference_input)

        self.setLayout(self.layout)

    def change_method(self):
        """Change method."""

        self.options_input.update_option_visibility()

    def lambda_auto_changed(self, checked: bool):
        """Apply the lambda auto changed emitted by the corresponding control."""

        self.lambda_value_input.setEnabled(not checked)

    def _lambda_options(self, method: str):
        del method
        return self.options_input.lambda_options()

    def accept(self):
        # Warn if current canvas is empty
        """Validate the inputs and accept the dialog when they are usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, 'Warning', 'Please add an axes first!')
            return

        # Warn if current axes is empty
        if self.figure_window.current_canva.current_axes is None:
            QMessageBox.warning(self, 'Warning', 'Please select an axes first!')
            return

        options = self.options_input.options()
        try:
            result = self.figure_window.current_canva.add_interpolate_curves(
                self.data_reference_input.get_x_ref(),
                self.data_reference_input.get_y_refs(),
                preprocess=self.data_reference_input.preprocess_values(),
                color_selection=self.color_input.selection(),
                **options,
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            return

        _show_batch_creation_result("Interpolation", result)
        self.data_reference_input.dispose()
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        self.data_reference_input.dispose()
        super().reject()

    def closeEvent(self, event):
        """Dispose the batch selector when the dialog window closes."""

        self.data_reference_input.dispose()
        super().closeEvent(event)


chart_dialog_dict = {
    'curve': PyCurveDialog,
    'plot': PyPlotDialog,
    'scatter': PyScatterDialog,
    'fit': PyFitDialog,
    'interpolation': PyInterpolationDialog
}
