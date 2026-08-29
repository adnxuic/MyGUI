"""Collect inputs for creating one table-driven Error Bar component."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.application_theme import bind_widget_qss
from mygui.figuremodify.style_base.color_models import ColorSelection
from mygui.figuremodify.style_base.creation_preferences import (
    is_override,
    resolve_errorbar_appearance,
)
from mygui.resources import icon_path
from mygui.widgets.fig_control_window.component_editors import (
    ErrorBarDataInput,
    LinePatternEditor,
    ScatterStyleEditor,
)
from mygui.widgets.fig_control_window.component_editors.common import (
    FocusAwareDoubleSpinBox,
)
from mygui.widgets.figure_canvas.py_figure_window import PyFigureWindow
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    _creation_defaults,
    _new_line_appearance_input,
    _palette_selection,
    _settings_snapshot,
)


def _new_errorbar_data_input(
    figure_window: PyFigureWindow,
    parent=None,
) -> ErrorBarDataInput:
    canvas = figure_window.current_canva
    return ErrorBarDataInput(
        figure_window.repository,
        canvas.project_id if canvas is not None else None,
        parent=parent,
    )


def _errorbar_dialog_plan(figure_window: PyFigureWindow):
    """Freeze Components defaults and the palette cursor at dialog open."""

    style = _creation_defaults(figure_window)
    settings = _settings_snapshot(figure_window)
    resolved = resolve_errorbar_appearance(
        style.line,
        style.error_bar,
        settings,
        palette_selection=_palette_selection(figure_window),
    )
    color_setting = None if settings is None else settings.line.color
    color_selection = (
        ColorSelection(resolved.color) if is_override(color_setting) else None
    )
    return resolved, color_selection


class _ErrorBarStyleGroup(QWidget):
    """Grouped Data/Line/Marker/Error Bars/Advanced creation controls."""

    def __init__(
        self,
        resolved,
        *,
        color_library,
        appearance_input,
        marker_editor,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        line_group = QGroupBox("Line", self)
        line_layout = QVBoxLayout(line_group)
        line_layout.addWidget(appearance_input)
        line_form = QFormLayout()
        line_layout.addLayout(line_form)

        # --- Line ---
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setDecimals(2)
        self.linewidth_input.setRange(0.0, 1_000_000.0)
        self.linewidth_input.setSingleStep(0.1)
        self.linewidth_input.setValue(float(resolved.linewidth))
        line_form.addRow(QLabel("Line width:", line_group), self.linewidth_input)

        self.drawstyle_input = _StringCombo(
            ("default", "steps", "steps-pre", "steps-mid", "steps-post"),
            resolved.drawstyle,
            self,
        )
        line_form.addRow(QLabel("Draw style:", line_group), self.drawstyle_input)

        self.antialiased_input = _BoolCheck(bool(resolved.antialiased), self)
        line_form.addRow(QLabel("Antialiased:", line_group), self.antialiased_input)
        layout.addWidget(line_group)

        # --- Marker ---
        marker_group = QGroupBox("Marker", self)
        marker_layout = QVBoxLayout(marker_group)
        marker_layout.addWidget(marker_editor)
        marker_form = QFormLayout()
        marker_layout.addLayout(marker_form)
        self.markeredgewidth_input = FocusAwareDoubleSpinBox(self)
        self.markeredgewidth_input.setDecimals(2)
        self.markeredgewidth_input.setRange(0.0, 1_000_000.0)
        self.markeredgewidth_input.setSingleStep(0.1)
        self.markeredgewidth_input.setValue(float(resolved.markeredgewidth))
        marker_form.addRow(
            QLabel("Marker edge width:", marker_group),
            self.markeredgewidth_input,
        )

        self.markerfacecoloralt_input = _OptionalColorChoiceInput(
            resolved.markerfacecoloralt,
            color_library=color_library,
            parent=marker_group,
        )
        marker_form.addRow(
            QLabel("Alternate marker face:", marker_group),
            self.markerfacecoloralt_input,
        )

        self.fillstyle_input = _StringCombo(
            ("full", "left", "right", "bottom", "top", "none"),
            resolved.fillstyle,
            self,
        )
        marker_form.addRow(QLabel("Fill style:", marker_group), self.fillstyle_input)
        layout.addWidget(marker_group)

        # --- Error Bars ---
        error_group = QGroupBox("Error Bars", self)
        error_form = QFormLayout(error_group)
        self.ecolor_input = ColorChoiceWidget(
            resolved.ecolor,
            color_library=color_library,
            auto_record_recent=False,
            parent=error_group,
        )
        error_form.addRow(QLabel("Error color:", error_group), self.ecolor_input)

        self.elinewidth_input = FocusAwareDoubleSpinBox(self)
        self.elinewidth_input.setDecimals(2)
        self.elinewidth_input.setRange(0.0, 1_000_000.0)
        self.elinewidth_input.setSingleStep(0.1)
        self.elinewidth_input.setValue(float(resolved.elinewidth))
        error_form.addRow(QLabel("Error line width:", error_group), self.elinewidth_input)

        self.capsize_input = FocusAwareDoubleSpinBox(self)
        self.capsize_input.setDecimals(2)
        self.capsize_input.setRange(0.0, 1_000_000.0)
        self.capsize_input.setSingleStep(0.5)
        self.capsize_input.setValue(float(resolved.capsize))
        error_form.addRow(QLabel("Cap size:", error_group), self.capsize_input)

        self.capthick_input = FocusAwareDoubleSpinBox(self)
        self.capthick_input.setDecimals(2)
        self.capthick_input.setRange(0.0, 1_000_000.0)
        self.capthick_input.setSingleStep(0.1)
        self.capthick_input.setValue(float(resolved.capthick))
        error_form.addRow(QLabel("Cap thickness:", error_group), self.capthick_input)

        self.error_linestyle_input = LinePatternEditor(parent=self)
        self.error_linestyle_input.set_value(resolved.error_linestyle)
        error_form.addRow(QLabel("Error line style:", error_group), self.error_linestyle_input)

        self.error_capstyle_input = _OptionalCombo(
            ("butt", "projecting", "round"),
            resolved.error_capstyle,
            "Style default",
            self,
        )
        error_form.addRow(QLabel("Error cap style:", error_group), self.error_capstyle_input)

        self.error_antialiased_input = _BoolCheck(
            bool(resolved.error_antialiased), self
        )
        error_form.addRow(
            QLabel("Error antialiased:", error_group),
            self.error_antialiased_input,
        )

        self.errorevery_start_input = FocusAwareDoubleSpinBox(self)
        self.errorevery_start_input.setDecimals(0)
        self.errorevery_start_input.setRange(0.0, 1_000_000_000.0)
        self.errorevery_input = FocusAwareDoubleSpinBox(self)
        self.errorevery_input.setDecimals(0)
        self.errorevery_input.setRange(1.0, 1_000_000_000.0)
        spec = resolved.errorevery or {"kind": "all"}
        if spec.get("kind") == "stride":
            self.errorevery_start_input.setValue(float(spec["start"]))
            self.errorevery_input.setValue(float(spec["step"]))
        else:
            self.errorevery_start_input.setValue(0.0)
            self.errorevery_input.setValue(1.0)
        every_row = QHBoxLayout()
        every_row.addWidget(QLabel("start", self))
        every_row.addWidget(self.errorevery_start_input)
        every_row.addWidget(QLabel("step", self))
        every_row.addWidget(self.errorevery_input)
        every_row.addStretch(1)
        error_form.addRow(QLabel("Error every:", error_group), every_row)

        self.barsabove_input = _BoolCheck(bool(resolved.barsabove), self)
        error_form.addRow(
            QLabel("Draw errors above data:", error_group),
            self.barsabove_input,
        )
        layout.addWidget(error_group)

        # --- Advanced ---
        advanced_group = QGroupBox("Advanced", self)
        advanced_form = QFormLayout(advanced_group)
        limit_tooltip = (
            "Matplotlib semantics: enabling a switch replaces the matching "
            "caps with a one-sided limit arrow (lolims draws an upward "
            "arrow, uplims downward; xlolims a rightward arrow, xuplims "
            "leftward)."
        )
        self.lolims_input = _BoolCheck(bool(resolved.lolims), self)
        self.lolims_input.setToolTip(limit_tooltip)
        self.uplims_input = _BoolCheck(bool(resolved.uplims), self)
        self.uplims_input.setToolTip(limit_tooltip)
        self.xlolims_input = _BoolCheck(bool(resolved.xlolims), self)
        self.xlolims_input.setToolTip(limit_tooltip)
        self.xuplims_input = _BoolCheck(bool(resolved.xuplims), self)
        self.xuplims_input.setToolTip(limit_tooltip)
        advanced_form.addRow(QLabel("Y lower-limit arrows (lolims):", advanced_group), self.lolims_input)
        advanced_form.addRow(QLabel("Y upper-limit arrows (uplims):", advanced_group), self.uplims_input)
        advanced_form.addRow(QLabel("X lower-limit arrows (xlolims):", advanced_group), self.xlolims_input)
        advanced_form.addRow(QLabel("X upper-limit arrows (xuplims):", advanced_group), self.xuplims_input)
        layout.addWidget(advanced_group)

    # Value surface -----------------------------------------------------
    def values(self) -> dict:
        every_start = int(self.errorevery_start_input.value())
        every_step = int(self.errorevery_input.value())
        return {
            "linewidth": float(self.linewidth_input.value()),
            "markeredgewidth": float(self.markeredgewidth_input.value()),
            "markerfacecoloralt": self.markerfacecoloralt_input.value(),
            "fillstyle": self.fillstyle_input.value(),
            "drawstyle": self.drawstyle_input.value(),
            "antialiased": self.antialiased_input.value(),
            "ecolor": self.ecolor_input.color(),
            "elinewidth": float(self.elinewidth_input.value()),
            "capsize": float(self.capsize_input.value()),
            "capthick": float(self.capthick_input.value()),
            "error_linestyle": self.error_linestyle_input.value(),
            "error_capstyle": self.error_capstyle_input.value(),
            "error_antialiased": self.error_antialiased_input.value(),
            "errorevery": (
                {"kind": "all"}
                if every_start == 0 and every_step == 1
                else {"kind": "stride", "start": every_start, "step": every_step}
            ),
            "lolims": self.lolims_input.value(),
            "uplims": self.uplims_input.value(),
            "xlolims": self.xlolims_input.value(),
            "xuplims": self.xuplims_input.value(),
            "barsabove": self.barsabove_input.value(),
        }


class _StringCombo(QComboBox):
    def __init__(self, choices, current, parent=None):
        super().__init__(parent)
        for choice in choices:
            self.addItem(str(choice), choice)
        self.setCurrentText(str(current))

    def value(self) -> str:
        return str(self.currentData())


class _OptionalCombo(QComboBox):
    def __init__(self, choices, current, none_label, parent=None):
        super().__init__(parent)
        self.addItem(none_label, None)
        for choice in choices:
            self.addItem(str(choice), choice)
        if current is None:
            self.setCurrentIndex(0)
        else:
            index = self.findData(str(current))
            self.setCurrentIndex(max(0, index))

    def value(self):
        return self.currentData()


class _BoolCheck(QCheckBox):
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setChecked(bool(current))

    def value(self) -> bool:
        return self.isChecked()


class _OptionalColorChoiceInput(QWidget):
    """Controller-free optional color backed by the shared ColorLibrary."""

    def __init__(self, current, *, color_library, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled_input = QCheckBox("Set", self)
        is_set = str(current).casefold() != "none"
        self.color_input = ColorChoiceWidget(
            current if is_set else "#000000",
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        self.enabled_input.setChecked(is_set)
        self.color_input.setEnabled(is_set)
        self.enabled_input.toggled.connect(self.color_input.setEnabled)
        layout.addWidget(self.enabled_input)
        layout.addWidget(self.color_input, 1)

    def value(self) -> str:
        return self.color_input.color() if self.enabled_input.isChecked() else "none"


class PyErrorBarDialog(QDialog):
    """Provide the py error bar dialog Qt widget."""

    def __init__(
        self,
        dialog_name=None,
        figure_window: PyFigureWindow = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("chart_dialog")
        bind_widget_qss(
            self,
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss",
        )

        self.setWindowTitle(dialog_name)
        self.setWindowIcon(QIcon(icon_path("chart_images/errorbar.svg")))

        self.figure_window: PyFigureWindow = figure_window
        self.creation_defaults = _creation_defaults(figure_window)
        self._resolved_errorbar, errorbar_color_selection = (
            _errorbar_dialog_plan(figure_window)
        )

        self.layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("errorbar_dialog_scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_widget = QWidget(self.scroll_area)
        self.content_layout = QVBoxLayout(self.content_widget)

        self.data_group = QGroupBox("Data", self.content_widget)
        data_layout = QVBoxLayout(self.data_group)
        self.data_reference_input = _new_errorbar_data_input(
            self.figure_window,
            parent=self.data_group,
        )
        self.x_data_input = self.data_reference_input.x_data_input
        self.y_data_input = self.data_reference_input.y_data_input
        self.x_error_input = self.data_reference_input.x_error_input
        self.y_error_input = self.data_reference_input.y_error_input
        data_layout.addWidget(self.data_reference_input)
        self.content_layout.addWidget(self.data_group)

        self.appearance_input = _new_line_appearance_input(
            figure_window,
            parent=self.content_widget,
            label="errorbar",
            style=self._resolved_errorbar.linestyle,
            linewidth=self._resolved_errorbar.linewidth,
            show_label=True,
            show_linewidth=False,
            color_selection=errorbar_color_selection,
        )
        self.line_style_editor = self.appearance_input.line_style_editor
        self.style_input = self.appearance_input.style_input
        self.color_input = self.appearance_input.color_input
        self.label_input = self.appearance_input.label_input
        self.marker_editor = ScatterStyleEditor(
            marker=self._resolved_errorbar.marker,
            size=self._resolved_errorbar.markersize,
            parent=self.content_widget,
        )
        self.marker_input = self.marker_editor.marker_input
        self.markersize_input = self.marker_editor.size_input
        self.style_group = _ErrorBarStyleGroup(
            self._resolved_errorbar,
            color_library=figure_window.color_library,
            appearance_input=self.appearance_input,
            marker_editor=self.marker_editor,
            parent=self.content_widget,
        )
        self.content_layout.addWidget(self.style_group)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll_area, 1)

        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.setMinimumWidth(680)
        self.resize(760, 720)

    def accept(self):
        """Validate the inputs and create one Error Bar when usable."""

        if self.figure_window.current_canva is None:
            QMessageBox.warning(self, "Warning", "Please add an axes first!")
            return
        if not self.figure_window.current_canva.has_current_axes:
            QMessageBox.warning(self, "Warning", "Please select an axes first!")
            return
        spec_error = self.data_reference_input.spec_error()
        if spec_error is not None:
            # An incomplete error draft is a visible draft, not a silent
            # none; keep the dialog open so the user can finish it.
            QMessageBox.warning(self, "Warning", spec_error)
            return

        values = self.style_group.values()
        try:
            runtime = self.figure_window.current_canva.add_errorbar(
                self.data_reference_input.get_x_ref(),
                self.data_reference_input.get_y_ref(),
                self.label_input.text(),
                xerr=self.data_reference_input.xerr_spec(),
                yerr=self.data_reference_input.yerr_spec(),
                preprocess=self.data_reference_input.preprocess_values(),
                color_selection=self.color_input.selection(),
                linestyle=self.line_style_editor.style(),
                linewidth=values["linewidth"],
                marker=self.marker_editor.marker(),
                markersize=self.markersize_input.value(),
                markeredgewidth=values["markeredgewidth"],
                markerfacecoloralt=values["markerfacecoloralt"],
                fillstyle=values["fillstyle"],
                drawstyle=values["drawstyle"],
                antialiased=values["antialiased"],
                ecolor=values["ecolor"],
                elinewidth=values["elinewidth"],
                capsize=values["capsize"],
                capthick=values["capthick"],
                error_linestyle=values["error_linestyle"],
                error_capstyle=values["error_capstyle"],
                error_antialiased=values["error_antialiased"],
                errorevery=values["errorevery"],
                lolims=values["lolims"],
                uplims=values["uplims"],
                xlolims=values["xlolims"],
                xuplims=values["xuplims"],
                barsabove=values["barsabove"],
            )
        except Exception as exc:
            status_messages.show_error(str(exc))
            return
        del runtime
        self.figure_window.color_library.record_recent(self.color_input.color())
        self.figure_window.color_library.record_recent(values["ecolor"])
        alternate = values["markerfacecoloralt"]
        if str(alternate).casefold() != "none":
            self.figure_window.color_library.record_recent(alternate)
        status_messages.show_success("Error Bar created.")
        self.data_reference_input.dispose()
        super().accept()

    def reject(self):
        """Reject the dialog without applying its pending inputs."""

        self.data_reference_input.dispose()
        super().reject()

    def closeEvent(self, event):
        """Dispose the repository-bound inputs when the dialog closes."""

        self.data_reference_input.dispose()
        super().closeEvent(event)
