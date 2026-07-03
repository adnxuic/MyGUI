import sys
from typing import Any, Optional
from Qt_core import *

from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget
from code.widgets.fig_control_window.all_mod_widgets.py_all_mod_widget import PyModBox
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyCurveModWidget, PyScatterModWidget, \
    PyPlotModWidget, PyFitMatlabModWidget, PyInterpolateWidget
from code.widgets.fig_control_window.all_mod_widgets.py_elements_mod_widgets import PyTextModWidget

from code.figuremodify.py_axes_modify import PyAxesModify
from code.figuremodify.py_chart_modify import PyCurveModify, PyScatterModify, PyPlotModify, PyInterpolateModify
from code.figuremodify.py_text_modify import PyTextModify

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


#
# mpl.rcParams['text.usetex'] = True
# preamble = r'\usepackage{amsmath,amssymb,amsthm}'
# mpl.rcParams['text.latex.preamble'] = preamble


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

        # 添加滚动条
        self.scroArea = QScrollArea()
        self.scroArea.setWidget(self.canva)
        self.scroArea.setAlignment(Qt.AlignCenter)
        self.scroArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 设置显示策略
        self.scroArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 设置显示策略

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

    # 添加坐标系
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

    # 添加自定义曲线
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

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)

        # 如果all_mod_widget中没有curve_box，则添加一个
        if all_mod_widget.cahrt_mod_window.boxs.get('curve_box') is None:
            all_mod_widget.add_chart_box('curve_box')

        # 添加曲线调整窗口
        curve_mod_widget = PyCurveModWidget(
            PyCurveModify(self.fig, self.current_axes, x_start, x_stop, self.style, line, func_text, label,
                          project_record=project_record), color)

        # 添加可视化对象
        self.current_axes_mod.add_vis_object(curve_mod_widget.get_colorupdate_func())

        curve_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['curve_box']
        curve_box.add_widget(curve_mod_widget, 'cuvre')

        self.redraw()

    # 添加折线图
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

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # 如果all_mod_widget中没有plot_box，则添加一个
        if all_mod_widget.cahrt_mod_window.boxs.get('plot_box') is None:
            all_mod_widget.add_chart_box('plot_box')
        # 添加曲线调整窗口
        plot_mod_widget = PyPlotModWidget(
            PyPlotModify(self.fig, self.current_axes, self.style, line, x_data_name, y_data_name, label,
                         project_record=project_record, project_collection=self.project_plots),
            x_data_name, y_data_name, color)

        # 添加可视化对象
        self.current_axes_mod.add_vis_object(plot_mod_widget.get_colorupdate_func())

        plot_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['plot_box']
        plot_box.add_widget(plot_mod_widget, 'plot')

        self.redraw()

    # 添加散点图
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

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # 如果all_mod_widget中没有scatter_box，则添加一个
        if all_mod_widget.cahrt_mod_window.boxs.get('scatter_box') is None:
            all_mod_widget.add_chart_box('scatter_box')

        # 添加散点调整窗口
        scatter_mod_widget = PyScatterModWidget(
            PyScatterModify(self.fig, self.current_axes, self.style, scatter, x_data_name, y_data_name, label,
                            project_record=project_record, project_collection=self.project_scatters),
            x_data_name, y_data_name, color)

        # 添加可视化对象
        self.current_axes_mod.add_vis_object(scatter_mod_widget.get_colorupdate_func())

        scatter_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['scatter_box']
        scatter_box.add_widget(scatter_mod_widget, 'scatter')

        self.redraw()

    # 添加拟合曲线
    def add_fit_curve(self, engine: str, x, y, color, label):
        with mpl.style.context(self.style):
            if engine == 'Python':
                line, = self.current_axes.plot(x, y, color=color, label=label)
            else:
                line, = self.current_axes.plot(x, y, color=color, label=label)

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # 如果all_mod_widget中没有fitting_box，则添加一个
        if all_mod_widget.cahrt_mod_window.boxs.get('fitting_box') is None:
            all_mod_widget.add_chart_box('fitting_box')

        # 添加拟合曲线调整窗口
        if engine == 'Python':
            fitting_mod_widget = None
        else:
            fitting_mod_widget = PyFitMatlabModWidget(
                PyCurveModify(self.fig, self.current_axes, 0, 0, self.style, line, '', label))

        fitting_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['fitting_box']
        fitting_box.add_widget(fitting_mod_widget, engine + 'fitting')

        self.redraw()

    # 添加插值曲线
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

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # 如果all_mod_widget中没有interpolate_box，则添加一个
        if all_mod_widget.cahrt_mod_window.boxs.get('interpolate_box') is None:
            all_mod_widget.add_chart_box('interpolate_box')

        # 添加插值曲线调整窗口
        interpolate_mod_widget = PyInterpolateWidget(
            PyInterpolateModify(self.fig, self.current_axes, self.style, line, x_name, y_name, label,
                                method=method, k=k, project_record=project_record,
                                project_collection=self.project_interpolates), method, k, color)

        # 添加可视化对象
        self.current_axes_mod.add_vis_object(interpolate_mod_widget.get_colorupdate_func())

        interpolate_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['interpolate_box']
        interpolate_box.add_widget(interpolate_mod_widget, 'interpolate')

        self.redraw()

    # 添加文本
    def add_text(self, x: float, y: float, text: str, fontfamily: str, fontsize: int, record_project=True):
        # with mpl.style.context(self.style):
        text = self.current_axes.text(x, y, text, family=fontfamily, fontsize=fontsize,
                                      transform=self.current_axes.transAxes)
        project_record = None
        if record_project:
            project_record = {
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x": float(x),
                "y": float(y),
                "text": text.get_text(),
                "fontfamily": fontfamily,
                "fontsize": float(text.get_fontsize()),
            }
            self.project_texts.append(project_record)
        # self.current_axes.transAxes是坐标系的坐标变换

        # 获取当前坐标系的所有修改窗口
        all_mod_widget = self.fig_modify_widget.fine_all_mod_widget(self.current_axes)
        # 如果all_mod_widget中没有text_box，则添加一个
        if all_mod_widget.element_mod_window.boxs.get('text_box') is None:
            all_mod_widget.add_element_box('text_box')
        # 添加文本调整窗口
        text_mod_widget = PyTextModWidget(PyTextModify(self.fig, self.style, text,
                                                       project_record=project_record,
                                                       project_collection=self.project_texts))
        text_box: PyModBox = all_mod_widget.element_mod_window.boxs['text_box']
        text_box.add_widget(text_mod_widget, 'text')

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
