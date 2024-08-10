from Qt_core import *

from code.database.py_database import PyDatabase

import numpy as np
from numpy import ndarray

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
from matplotlib.style import use

from numpy import (sin, cos, tan, pi,
                   exp, log,
                   sinh, cosh, tanh, arcsin, arccos, arctan, arcsinh)


class PyCurveModify:
    def __init__(self, fig, axe: Axes, x_start: float, x_stop: float, style, line: Line2D, expression: str):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.x_start, self.x_stop = x_start, x_stop

        self.expression = expression

        self.legend = axe.legend()

        self.line = line

    def redraw(self):
        self.fig.canvas.draw()

    def update_x_start(self, x_start: float):
        self.x_start = x_start
        x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
        y = eval(self.expression)
        self.line.set_data(x, y)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

    def update_x_stop(self, x_stop: float):
        self.x_stop = x_stop
        x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
        y = eval(self.expression)
        self.line.set_data(x, y)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

    def update_expression(self, expression: str):
        self.expression = expression
        try:
            func = eval(f"lambda x: {expression}")
            x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
            y = func(x)
            self.line.set_ydata(y)
            self.axe.relim()
            self.axe.autoscale_view()
            self.redraw()
        except Exception:
            pass

    def update_style(self, style: str):
        self.line.set_linestyle(style)
        self.redraw()


class PyPlotModify:
    def __init__(self, fig, axe: Axes, style=None, line: Line2D = None, x_data_name: str = None,
                 y_data_name: str = None):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.line = line

        self.current_x_data_name = x_data_name
        self.current_y_data_name = y_data_name

        # 数据和映射连接
        PyDatabase.data_connect(x_data_name, id_num=id(line), xy='x', connection_func=self.update_x_data)
        PyDatabase.data_connect(y_data_name, id_num=id(line), xy='y', connection_func=self.update_y_data)

    def redraw(self):
        self.fig.canvas.draw()

    def update_x_data(self, x_data: ndarray):
        # 如果数据长度不一致，则需要重新设置数据
        if len(x_data) == len(self.line.get_ydata()):
            self.line.set_xdata(x_data)
            # 重新计算坐标轴范围
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            y_data = np.zeros_like(x_data)
            self.line.set_data(x_data, y_data)

        self.redraw()

    def update_y_data(self, y_data: ndarray):
        # 如果数据长度不一致，则需要重新设置数据
        if len(y_data) == len(self.line.get_xdata()):
            self.line.set_ydata(y_data)
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            x_data = np.linspace(0, len(y_data), len(y_data))
            self.line.set_data(x_data, y_data)

        self.redraw()


class PyScatterModify:
    def __init__(self, fig, axe: Axes, style=None, scatter: PathCollection = None, x_data_name: str = None,
                 y_data_name: str = None):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.scatter = scatter

        self.current_x_data_name = x_data_name
        self.current_y_data_name = y_data_name

        # 数据和映射连接
        PyDatabase.data_connect(x_data_name, id_num=id(scatter), xy='x', connection_func=self.update_x_data)
        PyDatabase.data_connect(y_data_name, id_num=id(scatter), xy='y', connection_func=self.update_y_data)

    def redraw(self):
        self.fig.canvas.draw()

    def update_x_data(self, x_data: ndarray):
        # 如果数据长度不一致，则需要重新设置数据
        if len(x_data) == len(self.scatter.get_offsets()):
            self.scatter.set_offsets(np.c_[x_data, self.scatter.get_offsets()[:, 1]])
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            y_data = np.zeros_like(x_data)
            self.scatter.set_offsets(np.c_[x_data, y_data])

        self.redraw()

    def update_y_data(self, y_data: ndarray):
        # 如果数据长度不一致，则需要重新设置数据
        if len(y_data) == len(self.scatter.get_offsets()):
            self.scatter.set_offsets(np.c_[self.scatter.get_offsets()[:, 0], y_data])
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            x_data = np.zeros_like(y_data)
            self.scatter.set_offsets(np.c_[x_data, y_data])

        self.redraw()
