import sys
from typing import Any, Optional

from Qt_core import *
from code.database.py_database import PyDatabase
from code.database.interpolate_func import interpolate_dict
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget

from code.widgets import qss_func
import matplotlib

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

matplotlib.use("QtAgg")


class PyFigureWindow(QFrame):
    def __init__(self, fig_modify_window=None):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.fig_modify_window = fig_modify_window
        self.current_canva: Optional[PyFigureCanvas] = None
        self.canvas = {}

        self.current_fig_modify_widget: Optional[PyFigModWidget] = None

        self.layout = QVBoxLayout()
        self.tabwindow = QTabWidget()
        self.tabwindow.currentChanged.connect(self.change_current_canvas)

        self.layout.addWidget(self.tabwindow)
        self.setLayout(self.layout)

    def add_figure(self, width=None, height=None, dpi=None, style=None, canva_name=None):
        canva = PyFigureCanvas(self, width=width, height=height, dpi=dpi, style=style)
        self.canvas['canva' + str(len(self.canvas) + 1)] = canva

        figmod_widget = self.fig_modify_window.add_figmod_widget()

        canva.setFigModifyWidget(figmod_widget)

        if canva_name != '':
            self.tabwindow.addTab(canva, canva_name)
        else:
            self.tabwindow.addTab(canva, 'canva' + str(len(self.canvas) + 1))

        self.tabwindow.setCurrentWidget(canva)

    def change_current_canvas(self):
        self.current_canva = self.tabwindow.currentWidget()
        self.fig_modify_window.stacklayout.setCurrentIndex(self.tabwindow.currentIndex())
        self.current_fig_modify_widget = self.fig_modify_window.stacklayout.currentWidget()

    def get_current_canvas_axes_colorselector(self):
        return self.current_canva.current_axes_mod.color_selector

    def clear_figures(self):
        while self.tabwindow.count():
            widget = self.tabwindow.widget(0)
            self.tabwindow.removeTab(0)
            if hasattr(widget, "cancel_pending_draw"):
                widget.cancel_pending_draw()
            widget.deleteLater()
        self.canvas.clear()
        self.current_canva = None
        self.current_fig_modify_widget = None
        if hasattr(self.fig_modify_window, "clear_figmod_widgets"):
            self.fig_modify_window.clear_figmod_widgets()

    def cancel_pending_draws(self):
        for index in range(self.tabwindow.count()):
            widget = self.tabwindow.widget(index)
            if hasattr(widget, "cancel_pending_draw"):
                widget.cancel_pending_draw()

    def project_snapshot(self) -> list[dict[str, Any]]:
        canvases: list[dict[str, Any]] = []
        for index in range(self.tabwindow.count()):
            canvas = self.tabwindow.widget(index)
            if not hasattr(canvas, "project_snapshot"):
                continue
            snapshot = canvas.project_snapshot()
            snapshot["name"] = self.tabwindow.tabText(index)
            canvases.append(snapshot)
        return canvases

    @staticmethod
    def _select_project_axes(canvas: PyFigureCanvas, record: dict[str, Any]) -> bool:
        if not canvas.fig.axes:
            return False
        axes_index = int(record.get("axes_index", 0))
        if axes_index < 0 or axes_index >= len(canvas.fig.axes):
            return False
        canvas.set_current_axes_by_index(axes_index)
        return True

    @staticmethod
    def _project_data_pair(record: dict[str, Any]):
        x_data_name = record.get("x_data_name")
        y_data_name = record.get("y_data_name")
        if not PyDatabase.has_data(x_data_name) or not PyDatabase.has_data(y_data_name):
            return None
        return x_data_name, y_data_name, PyDatabase.get_data(x_data_name), PyDatabase.get_data(y_data_name)

    def load_figure_snapshot(self, figures: list[dict[str, Any]]):
        self.clear_figures()
        for figure in figures:
            size_inches = figure.get("size_inches") or [6.4, 4.8]
            width = float(size_inches[0])
            height = float(size_inches[1])
            dpi = int(float(figure.get("dpi", 100)))
            style = figure.get("style") or "default"
            name = figure.get("name") or style

            self.add_figure(width=width, height=height, dpi=dpi, style=style, canva_name=name)
            canvas = self.current_canva
            if canvas is None:
                continue

            axes_layouts = figure.get("axes_layouts") or []
            if not axes_layouts and figure.get("axes_count"):
                axes_layouts = [{"nrows": int(figure["axes_count"]), "ncols": 1}]

            for layout in axes_layouts:
                nrows = int(layout.get("nrows", 1))
                ncols = int(layout.get("ncols", 1))
                canvas.add_axes(nrows=nrows, ncols=ncols, record_project=True)

            for curve in figure.get("curves", []):
                if not canvas.fig.axes:
                    continue
                axes_index = int(curve.get("axes_index", 0))
                if axes_index >= len(canvas.fig.axes):
                    continue
                canvas.set_current_axes_by_index(axes_index)
                canvas.add_curve(
                    func_text=curve.get("expression", "x"),
                    x_start=float(curve.get("x_start", 0.0)),
                    x_stop=float(curve.get("x_stop", 100.0)),
                    style=curve.get("style", "-"),
                    color=curve.get("color", "black"),
                    label=curve.get("label", ""),
                    record_project=True,
                )

            for plot in figure.get("plots", []):
                if not self._select_project_axes(canvas, plot):
                    continue
                data_pair = self._project_data_pair(plot)
                if data_pair is None:
                    continue
                x_data_name, y_data_name, x_data, y_data = data_pair
                canvas.add_plot(
                    x=x_data,
                    y=y_data,
                    style=plot.get("style", "-"),
                    size=float(plot.get("size", 2.0)),
                    color=plot.get("color", "black"),
                    label=plot.get("label", ""),
                    x_data_name=x_data_name,
                    y_data_name=y_data_name,
                    record_project=True,
                )

            for scatter in figure.get("scatters", []):
                if not self._select_project_axes(canvas, scatter):
                    continue
                data_pair = self._project_data_pair(scatter)
                if data_pair is None:
                    continue
                x_data_name, y_data_name, x_data, y_data = data_pair
                canvas.add_scatter(
                    x=x_data,
                    y=y_data,
                    size=float(scatter.get("size", 20.0)),
                    color=scatter.get("color", "black"),
                    marker=scatter.get("marker", "o"),
                    label=scatter.get("label", ""),
                    x_data_name=x_data_name,
                    y_data_name=y_data_name,
                    record_project=True,
                )

            for interpolate in figure.get("interpolates", []):
                if not self._select_project_axes(canvas, interpolate):
                    continue
                method = interpolate.get("method")
                if method not in interpolate_dict:
                    continue
                data_pair = self._project_data_pair(interpolate)
                if data_pair is None:
                    continue
                x_data_name, y_data_name, x_data, y_data = data_pair
                canvas.add_interpolate_curve(
                    x=x_data,
                    y=y_data,
                    x_name=x_data_name,
                    y_name=y_data_name,
                    method=method,
                    k=int(interpolate.get("k", 3)),
                    color=interpolate.get("color", "black"),
                    label=interpolate.get("label", "interpolate"),
                    record_project=True,
                )

            for text in figure.get("texts", []):
                if text.get("scope", "axes") == "figure":
                    canvas.add_global_text(
                        x=float(text.get("x", 0.5)),
                        y=float(text.get("y", 0.5)),
                        text=text.get("text", ""),
                        fontfamily=text.get("fontfamily", "Times New Roman"),
                        fontsize=int(float(text.get("fontsize", 20))),
                        usetex=bool(text.get("usetex", False)),
                        record_project=True,
                    )
                    continue
                if not self._select_project_axes(canvas, text):
                    continue
                canvas.add_text(
                    x=float(text.get("x", 0.5)),
                    y=float(text.get("y", 0.5)),
                    text=text.get("text", ""),
                    fontfamily=text.get("fontfamily", "Times New Roman"),
                    fontsize=int(float(text.get("fontsize", 20))),
                    usetex=bool(text.get("usetex", False)),
                    record_project=True,
                )
