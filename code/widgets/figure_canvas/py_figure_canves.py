import sys
from typing import Any, Optional
from Qt_core import *

from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget
from code.widgets.fig_control_window.all_mod_widgets.py_all_mod_widget import PyModBox
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyCurveModWidget, PyScatterModWidget, \
    PyPlotModWidget, PyFitModWidget, PyInterpolateWidget
from code.widgets.fig_control_window.all_mod_widgets.py_elements_mod_widgets import PyTextModWidget

from code.figuremodify.py_axes_modify import PyAxesModify
from code.figuremodify.py_chart_modify import PyCurveModify, PyScatterModify, PyPlotModify, PyInterpolateModify
from code.figuremodify.py_text_modify import PyTextModify, TextRenderError

from code import tex_config
from code import status_messages
from code.database.py_database import PyDatabase
from code.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES, interpolate_curve
from code.database.safe_expression import evaluate_curve_expression

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.style import use

import numpy as np
mpl.use("QtAgg")


class PyFigureCanvas(QWidget):
    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None,
                 project_name: str | None = None, project_path: str | None = None):
        super().__init__()
        self.style = style
        self.project_name = project_name or ""
        self.project_table_name = self.project_name
        self.project_path = project_path
        with mpl.style.context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)

        self.fig_modify_widget: Optional[PyFigModWidget] = None

        self.current_axes: Optional[Axes] = None
        self.current_axes_mod: Optional[PyAxesModify] = None
        self.axes_mods: list[PyAxesModify] = []
        self.project_axes_layouts: list[dict[str, int]] = []
        self.project_curves: list[dict[str, Any]] = []
        self.project_plots: list[dict[str, Any]] = []
        self.project_scatters: list[dict[str, Any]] = []
        self.project_interpolates: list[dict[str, Any]] = []
        self.project_fits: list[dict[str, Any]] = []
        self.project_texts: list[dict[str, Any]] = []

        self.canva = FigureCanvasQTAgg(self.fig)
        self.canva.setFixedSize(width * dpi, height * dpi)

        # Add scroll area
        self.scroArea = QScrollArea()
        self.scroArea.setWidget(self.canva)
        self.scroArea.setAlignment(Qt.AlignCenter)
        self.scroArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy
        self.scroArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Set scroll bar visibility policy

        layout = QVBoxLayout()

        toolbox = NavigationToolbar(self.canva, self)

        layout.addWidget(toolbox)
        layout.addWidget(self.scroArea)

        self.setLayout(layout)

    def setFigModifyWidget(self, fig_modify_widget):
        self.fig_modify_widget = fig_modify_widget

    def update_current_axes(self, axe, axe_mod):
        self.current_axes = axe
        self.current_axes_mod = axe_mod

    def set_current_axes_by_index(self, axes_index: int):
        if axes_index < 0 or axes_index >= len(self.fig.axes):
            raise IndexError(f"Invalid axes index: {axes_index}")
        self.update_current_axes(self.fig.axes[axes_index], self.axes_mods[axes_index])

    def redraw(self):
        self.fig.canvas.draw()

    def cancel_pending_draw(self):
        if hasattr(self.canva, "_draw_pending"):
            self.canva._draw_pending = False

    def closeEvent(self, event):
        self.cancel_pending_draw()
        super().closeEvent(event)

    # Add axes
    def add_axes(self, nrows=1, ncols=1, record_project=True):
        start_index = len(self.fig.axes)
        with mpl.style.context(self.style):
            for i in range(nrows * ncols):
                axe = self.fig.add_subplot(nrows, ncols, 1 + i)
                axe_mod = PyAxesModify(self.fig, axe, self.style)
                self.axes_mods.append(axe_mod)

                btn = self.fig_modify_widget.add_all_mod_widget(axe, axe_mod)
                btn.clicked.connect(lambda _, axe1=axe, axe_mod1=axe_mod:
                                    self.update_current_axes(axe1, axe_mod1))

                if i == 0:
                    self.update_current_axes(axe, axe_mod)

        if record_project:
            self.project_axes_layouts.append({
                "nrows": int(nrows),
                "ncols": int(ncols),
                "start_index": int(start_index),
                "count": int(nrows * ncols),
            })

        self.redraw()

    # Add custom curve
    def add_curve(self, func_text: str, x_start: float, x_stop: float, style, color, label: str,
                  record_project=True):

        x = np.linspace(x_start, x_stop, 1000)
        y = evaluate_curve_expression(func_text, x)
        with mpl.style.context(self.style):
            line, = self.current_axes.plot(x, y, ls=style, color=color, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "expression": func_text,
                "x_start": float(x_start),
                "x_stop": float(x_stop),
                "style": line.get_linestyle(),
                "color": line.get_color(),
                "label": label,
            }
            self.project_curves.append(project_record)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)

        # Add curve_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('curve_box') is None:
            all_mod_widget.add_chart_box('curve_box')

        # Add curve adjustment panel
        curve_mod_widget = PyCurveModWidget(
            PyCurveModify(self.fig, self.current_axes, x_start, x_stop, self.style, line, func_text, label,
                          project_record=project_record, project_collection=self.project_curves), color)

        # Add visualization object
        self.current_axes_mod.add_vis_object(curve_mod_widget.get_colorupdate_func())

        curve_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['curve_box']
        curve_box.add_widget(curve_mod_widget, 'cuvre')

        self.redraw()

    # Add line plot
    def add_plot(self, x, y, style, size, color, label, x_data_name: str, y_data_name: str,
                 record_project=True):
        with mpl.style.context(self.style):
            line, = self.current_axes.plot(x, y, style, markersize=size, color=color, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_data_name": x_data_name,
                "y_data_name": y_data_name,
                "style": style,
                "size": float(line.get_markersize()),
                "color": line.get_color(),
                "label": label,
            }
            self.project_plots.append(project_record)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add plot_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('plot_box') is None:
            all_mod_widget.add_chart_box('plot_box')
        # Add curve adjustment panel
        plot_mod_widget = PyPlotModWidget(
            PyPlotModify(self.fig, self.current_axes, self.style, line, x_data_name, y_data_name, label,
                         project_record=project_record, project_collection=self.project_plots),
            x_data_name, y_data_name, color)

        # Add visualization object
        self.current_axes_mod.add_vis_object(plot_mod_widget.get_colorupdate_func())

        plot_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['plot_box']
        plot_box.add_widget(plot_mod_widget, 'plot')

        self.redraw()

    # Add scatter plot
    def add_scatter(self, x, y, size, color, marker, label, x_data_name: str, y_data_name: str,
                    record_project=True):
        with mpl.style.context(self.style):
            scatter = self.current_axes.scatter(x, y, s=size, c=color, marker=marker, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_data_name": x_data_name,
                "y_data_name": y_data_name,
                "size": float(size),
                "color": color,
                "marker": marker,
                "label": label,
            }
            self.project_scatters.append(project_record)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add scatter_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('scatter_box') is None:
            all_mod_widget.add_chart_box('scatter_box')

        # Add scatter adjustment panel
        scatter_mod_widget = PyScatterModWidget(
            PyScatterModify(self.fig, self.current_axes, self.style, scatter, x_data_name, y_data_name, label,
                            project_record=project_record, project_collection=self.project_scatters),
            x_data_name, y_data_name, color)

        # Add visualization object
        self.current_axes_mod.add_vis_object(scatter_mod_widget.get_colorupdate_func())

        scatter_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['scatter_box']
        scatter_box.add_widget(scatter_mod_widget, 'scatter')

        self.redraw()

    # Add fit curve
    def add_fit_curve(self, x, y, color, label, x_data_name: str = "", y_data_name: str = "",
                      engine: str = "Python", record_project=True, fit_type=None,
                      fit_options=None, fit_result=None, expression: str = "",
                      x_start: float | None = None, x_stop: float | None = None,
                      style: str = "solid"):
        if engine not in {"Python", "Matlab"}:
            raise ValueError(f"Unsupported fitting engine: {engine}")

        x_array = np.asarray(x, dtype=float)
        y_array = np.asarray(y, dtype=float)
        if x_array.size:
            default_x_start = float(np.min(x_array))
            default_x_stop = float(np.max(x_array))
        else:
            default_x_start = 0.0
            default_x_stop = 1.0
        x_start = default_x_start if x_start is None else float(x_start)
        x_stop = default_x_stop if x_stop is None else float(x_stop)

        line_x = x_array
        line_y = y_array
        if expression:
            try:
                line_x = np.linspace(x_start, x_stop, 1000)
                line_y = evaluate_curve_expression(expression, line_x)
            except ValueError:
                status_messages.show_error("Saved fit expression could not be restored; showing source data.")
                expression = ""

        with mpl.style.context(self.style):
            line, = self.current_axes.plot(line_x, line_y, ls=style, color=color, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_data_name": x_data_name,
                "y_data_name": y_data_name,
                "engine": engine,
                "fit_type": fit_type,
                "fit_options": fit_options,
                "fit_result": fit_result,
                "expression": expression or "",
                "x_start": float(x_start),
                "x_stop": float(x_stop),
                "style": line.get_linestyle(),
                "color": line.get_color(),
                "label": label,
            }
            self.project_fits.append(project_record)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add fitting_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('fitting_box') is None:
            all_mod_widget.add_chart_box('fitting_box')

        # Add fit curve adjustment panel
        fitting_mod_widget = PyFitModWidget(
            PyCurveModify(
                self.fig,
                self.current_axes,
                x_start,
                x_stop,
                self.style,
                line,
                expression or "",
                label,
                project_record=project_record,
                project_collection=self.project_fits,
            ),
            x_data_name=x_data_name,
            y_data_name=y_data_name,
            engine=engine,
            fit_type=fit_type,
            fit_options=fit_options,
            fit_result=fit_result,
        )

        fitting_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['fitting_box']
        fitting_box.add_widget(fitting_mod_widget, "fitting")
        fitting_box.setCurrentWidget(fitting_mod_widget)

        self.redraw()
        return line

    # Add interpolation curve
    def add_interpolate_curve(self, x, y, x_name, y_name, method, k=3, label='interpolate',
                              color='black', record_project=True,
                              samples=DEFAULT_INTERPOLATION_SAMPLES,
                              lam=None, lam_auto=True):
        with mpl.style.context(self.style):
            try:
                x_new, y_new = interpolate_curve(
                    x,
                    y,
                    method,
                    k=k,
                    samples=samples,
                    lam=lam,
                    lam_auto=lam_auto,
                )
            except ValueError as exc:
                status_messages.show_error(str(exc))
                return None
            line, = self.current_axes.plot(x_new, y_new, color=color, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_data_name": x_name,
                "y_data_name": y_name,
                "method": method,
                "k": int(k),
                "samples": int(samples),
                "lam": None if lam is None else float(lam),
                "lam_auto": bool(lam_auto),
                "color": line.get_color(),
                "label": label,
            }
            self.project_interpolates.append(project_record)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add interpolate_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('interpolate_box') is None:
            all_mod_widget.add_chart_box('interpolate_box')

        # Add interpolation curve adjustment panel
        interpolate_mod_widget = PyInterpolateWidget(
            PyInterpolateModify(self.fig, self.current_axes, self.style, line, x_name, y_name, label,
                                method=method, k=k, samples=samples, lam=lam, lam_auto=lam_auto,
                                project_record=project_record,
                                project_collection=self.project_interpolates), method, k, color,
            x_data_name=x_name, y_data_name=y_name, samples=samples, lam=lam, lam_auto=lam_auto)

        # Add visualization object
        self.current_axes_mod.add_vis_object(interpolate_mod_widget.get_colorupdate_func())

        interpolate_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['interpolate_box']
        interpolate_box.add_widget(interpolate_mod_widget, 'interpolate')

        self.redraw()
        status_messages.show_success("Interpolation curve created.")
        return line

    # Add text
    @staticmethod
    def _resolve_text_usetex(usetex: bool | None) -> bool:
        if usetex is None:
            return tex_config.is_tex_enabled()
        return bool(usetex) and tex_config.is_tex_enabled()

    def add_text(self, x: float, y: float, text: str, fontfamily: str, fontsize: int,
                 usetex: bool | None = None, record_project=True):
        # with mpl.style.context(self.style):
        desired_usetex = self._resolve_text_usetex(usetex)
        text = self.current_axes.text(x, y, text, family=fontfamily, fontsize=fontsize,
                                      transform=self.current_axes.transAxes, usetex=False)
        project_record = None
        if record_project:
            project_record = {
                "scope": "axes",
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x": float(x),
                "y": float(y),
                "text": text.get_text(),
                "fontfamily": fontfamily,
                "fontsize": float(text.get_fontsize()),
                "usetex": False,
            }
            self.project_texts.append(project_record)
        # self.current_axes.transAxes is the axes coordinate transform

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add text_box to all_mod_widget if missing
        if all_mod_widget.element_mod_window.boxs.get('text_box') is None:
            all_mod_widget.add_element_box('text_box')
        # Add text adjustment panel
        text_modify = PyTextModify(self.fig, self.style, text,
                                   project_record=project_record,
                                   project_collection=self.project_texts)
        if desired_usetex:
            try:
                text_modify.set_text_usetex(True)
            except TextRenderError as exc:
                status_messages.show_error(str(exc))
        text_mod_widget = PyTextModWidget(text_modify)
        text_box: PyModBox = all_mod_widget.element_mod_window.boxs['text_box']
        text_box.add_widget(text_mod_widget, 'text')

        self.redraw()

    def add_global_text(self, x: float, y: float, text: str, fontfamily: str, fontsize: int,
                        usetex: bool | None = None,
                        record_project=True):
        desired_usetex = self._resolve_text_usetex(usetex)
        text = self.fig.text(x, y, text, family=fontfamily, fontsize=fontsize, usetex=False)
        project_record = None
        if record_project:
            project_record = {
                "scope": "figure",
                "x": float(x),
                "y": float(y),
                "text": text.get_text(),
                "fontfamily": fontfamily,
                "fontsize": float(text.get_fontsize()),
                "usetex": False,
            }
            self.project_texts.append(project_record)

        text_modify = PyTextModify(self.fig, self.style, text,
                                   project_record=project_record,
                                   project_collection=self.project_texts)
        if desired_usetex:
            try:
                text_modify.set_text_usetex(True)
            except TextRenderError as exc:
                status_messages.show_error(str(exc))

        if self.fig_modify_widget is not None:
            figure_mod_widget = getattr(self.fig_modify_widget, "figure_element_mod_widget", None)
            if figure_mod_widget is not None:
                if figure_mod_widget.element_mod_window.boxs.get('text_box') is None:
                    figure_mod_widget.add_element_box('text_box')
                text_mod_widget = PyTextModWidget(text_modify)
                text_box: PyModBox = figure_mod_widget.element_mod_window.boxs['text_box']
                text_box.add_widget(text_mod_widget, 'text')
                self.fig_modify_widget.stacklayout.setCurrentWidget(figure_mod_widget)

        self.redraw()

    def save(self, filename, dpi=None):
        if dpi is None:
            save_dpi = self.fig.dpi
        else:
            save_dpi = dpi
        with mpl.style.context(self.style):
            self.fig.savefig(filename, dpi=save_dpi)

    @staticmethod
    def _rewrite_data_name(data_name: str, old_table: str, new_table: str,
                           old_sheet: str | None = None, new_sheet: str | None = None) -> str:
        try:
            table_name, sheet_name, column_name = PyDatabase.split_data_name(data_name)
        except (KeyError, AttributeError):
            return data_name
        if table_name != old_table:
            return data_name
        if old_sheet is not None and sheet_name != old_sheet:
            return data_name
        return f"{new_table}/{new_sheet or sheet_name}/{column_name}"

    def rewrite_data_references(self, old_table: str, new_table: str,
                                old_sheet: str | None = None, new_sheet: str | None = None):
        for collection in (self.project_plots, self.project_scatters, self.project_interpolates, self.project_fits):
            for record in collection:
                for field in ("x_data_name", "y_data_name"):
                    if field in record:
                        record[field] = self._rewrite_data_name(
                            record[field],
                            old_table,
                            new_table,
                            old_sheet=old_sheet,
                            new_sheet=new_sheet,
                        )

        if self.fig_modify_widget is not None:
            from code.widgets.common_widget.min_widget.py_datachoice_widget import PyDataChoiceWidget

            for widget in self.fig_modify_widget.findChildren(PyDataChoiceWidget):
                old_x = widget.get_x_data()
                old_y = widget.get_y_data()
                new_x = self._rewrite_data_name(
                    old_x, old_table, new_table, old_sheet=old_sheet, new_sheet=new_sheet
                )
                new_y = self._rewrite_data_name(
                    old_y, old_table, new_table, old_sheet=old_sheet, new_sheet=new_sheet
                )
                if new_x != old_x:
                    widget.set_x_data(new_x)
                if new_y != old_y:
                    widget.set_y_data(new_y)

    @staticmethod
    def _json_position(position):
        if isinstance(position, (list, tuple)):
            return [PyFigureCanvas._json_position(value) for value in position]
        try:
            return float(position)
        except (TypeError, ValueError):
            return str(position)

    @staticmethod
    def _legend_location(legend):
        if legend is None:
            return None
        loc = getattr(legend, "_loc", None)
        if isinstance(loc, tuple):
            return [float(value) for value in loc]
        if isinstance(loc, list):
            return [float(value) for value in loc]
        if isinstance(loc, np.integer):
            return int(loc)
        if isinstance(loc, np.floating):
            return float(loc)
        return loc

    @staticmethod
    def _restore_location(location):
        if isinstance(location, list) and len(location) == 2:
            return (float(location[0]), float(location[1]))
        return location

    def axes_snapshot(self) -> list[dict[str, Any]]:
        axes_records: list[dict[str, Any]] = []
        for index, axe in enumerate(self.fig.axes):
            x_family = axe.xaxis.label.get_fontfamily()
            if isinstance(x_family, (list, tuple)):
                label_fontfamily = x_family[0] if x_family else ""
            else:
                label_fontfamily = str(x_family)

            legend = axe.get_legend()
            legend_record = None
            if legend is not None:
                legend_record = {
                    "visible": bool(legend.get_visible()),
                    "loc": self._legend_location(legend),
                }

            axes_records.append({
                "index": int(index),
                "xlim": [float(value) for value in axe.get_xlim()],
                "ylim": [float(value) for value in axe.get_ylim()],
                "xlabel": axe.get_xlabel(),
                "ylabel": axe.get_ylabel(),
                "label_fontfamily": label_fontfamily,
                "label_fontsize": float(axe.xaxis.label.get_fontsize()),
                "x_label_position": [float(value) for value in axe.xaxis.label.get_position()],
                "y_label_position": [float(value) for value in axe.yaxis.label.get_position()],
                "xaxis_visible": bool(axe.xaxis.get_visible()),
                "yaxis_visible": bool(axe.yaxis.get_visible()),
                "spines": {
                    name: {
                        "visible": bool(spine.get_visible()),
                        "position": self._json_position(spine.get_position()),
                    }
                    for name, spine in axe.spines.items()
                },
                "legend": legend_record,
            })
        return axes_records

    def apply_axes_snapshot(self, axes_records: list[dict[str, Any]] | None):
        if not axes_records:
            return
        for record in axes_records:
            try:
                axes_index = int(record.get("index", -1))
            except (TypeError, ValueError):
                continue
            if axes_index < 0 or axes_index >= len(self.fig.axes):
                continue
            axe = self.fig.axes[axes_index]

            xlim = record.get("xlim")
            if isinstance(xlim, list) and len(xlim) == 2:
                axe.set_xlim(float(xlim[0]), float(xlim[1]))
            ylim = record.get("ylim")
            if isinstance(ylim, list) and len(ylim) == 2:
                axe.set_ylim(float(ylim[0]), float(ylim[1]))

            axe.set_xlabel(str(record.get("xlabel", "")))
            axe.set_ylabel(str(record.get("ylabel", "")))
            label_fontfamily = record.get("label_fontfamily")
            if label_fontfamily:
                axe.xaxis.label.set_fontfamily(label_fontfamily)
                axe.yaxis.label.set_fontfamily(label_fontfamily)
            if "label_fontsize" in record:
                axe.xaxis.label.set_fontsize(float(record["label_fontsize"]))
                axe.yaxis.label.set_fontsize(float(record["label_fontsize"]))
            x_label_position = record.get("x_label_position")
            if isinstance(x_label_position, list) and len(x_label_position) == 2:
                axe.xaxis.set_label_coords(float(x_label_position[0]), float(x_label_position[1]))
            y_label_position = record.get("y_label_position")
            if isinstance(y_label_position, list) and len(y_label_position) == 2:
                axe.yaxis.set_label_coords(float(y_label_position[0]), float(y_label_position[1]))

            if "xaxis_visible" in record:
                axe.xaxis.set_visible(bool(record["xaxis_visible"]))
            if "yaxis_visible" in record:
                axe.yaxis.set_visible(bool(record["yaxis_visible"]))

            spines = record.get("spines")
            if isinstance(spines, dict):
                for spine_name, spine_state in spines.items():
                    if spine_name not in axe.spines or not isinstance(spine_state, dict):
                        continue
                    spine = axe.spines[spine_name]
                    if "visible" in spine_state:
                        spine.set_visible(bool(spine_state["visible"]))
                    position = spine_state.get("position")
                    if isinstance(position, list) and len(position) == 2:
                        spine.set_position((position[0], float(position[1])))

            legend_state = record.get("legend")
            existing_legend = axe.get_legend()
            if isinstance(legend_state, dict) and legend_state.get("visible", False):
                loc = self._restore_location(legend_state.get("loc", "best"))
                try:
                    axe.legend(loc=loc)
                except Exception:
                    axe.legend(loc="best")
            elif existing_legend is not None:
                existing_legend.remove()
        self.redraw()

    def set_project_name(self, name: str):
        old_table = self.project_table_name
        self.project_name = name
        self.project_table_name = name
        if old_table and old_table != name:
            self.rewrite_data_references(old_table, name)

    def project_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.project_name,
            "style": self.style,
            "dpi": float(self.fig.dpi),
            "size_inches": [float(value) for value in self.fig.get_size_inches()],
            "axes_count": len(self.fig.axes),
            "axes_layouts": [dict(layout) for layout in self.project_axes_layouts],
            "axes": self.axes_snapshot(),
            "curves": [dict(curve) for curve in self.project_curves],
            "plots": [dict(plot) for plot in self.project_plots],
            "scatters": [dict(scatter) for scatter in self.project_scatters],
            "interpolates": [dict(interpolate) for interpolate in self.project_interpolates],
            "fits": [dict(fit) for fit in self.project_fits],
            "texts": [dict(text) for text in self.project_texts],
        }
