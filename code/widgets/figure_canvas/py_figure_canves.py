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
from code.database.interpolate_func import interpolate_dict
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
    def __init__(self, parent=None, width=4, height=3, dpi=200, style=None):
        super().__init__()
        self.style = style
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
                      engine: str = "Python"):
        if engine not in {"Python", "Matlab"}:
            raise ValueError(f"Unsupported fitting engine: {engine}")

        with mpl.style.context(self.style):
            line, = self.current_axes.plot(x, y, color=color, label=label)

        # Get modification panels for current axes
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # Add fitting_box to all_mod_widget if missing
        if all_mod_widget.cahrt_mod_window.boxs.get('fitting_box') is None:
            all_mod_widget.add_chart_box('fitting_box')

        # Add fit curve adjustment panel
        x_start = float(np.min(x))
        x_stop = float(np.max(x))
        fitting_mod_widget = PyFitModWidget(
            PyCurveModify(self.fig, self.current_axes, x_start, x_stop, self.style, line, '', label),
            x_data_name=x_data_name,
            y_data_name=y_data_name,
            engine=engine,
        )

        fitting_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['fitting_box']
        fitting_box.add_widget(fitting_mod_widget, "fitting")
        fitting_box.setCurrentWidget(fitting_mod_widget)

        self.redraw()

    # Add interpolation curve
    def add_interpolate_curve(self, x, y, x_name, y_name, method, k=3, label='interpolate',
                              color='black', record_project=True):
        with mpl.style.context(self.style):
            if method == "B样条插值":
                x_new, y_new = interpolate_dict[method](x, y, k=k)
            else:
                x_new, y_new = interpolate_dict[method](x, y)
            line, = self.current_axes.plot(x_new, y_new, color=color, label=label)

        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_data_name": x_name,
                "y_data_name": y_name,
                "method": method,
                "k": int(k),
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
                                method=method, k=k, project_record=project_record,
                                project_collection=self.project_interpolates), method, k, color)

        # Add visualization object
        self.current_axes_mod.add_vis_object(interpolate_mod_widget.get_colorupdate_func())

        interpolate_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['interpolate_box']
        interpolate_box.add_widget(interpolate_mod_widget, 'interpolate')

        self.redraw()

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

    def project_snapshot(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "dpi": float(self.fig.dpi),
            "size_inches": [float(value) for value in self.fig.get_size_inches()],
            "axes_count": len(self.fig.axes),
            "axes_layouts": [dict(layout) for layout in self.project_axes_layouts],
            "curves": [dict(curve) for curve in self.project_curves],
            "plots": [dict(plot) for plot in self.project_plots],
            "scatters": [dict(scatter) for scatter in self.project_scatters],
            "interpolates": [dict(interpolate) for interpolate in self.project_interpolates],
            "texts": [dict(text) for text in self.project_texts],
        }
