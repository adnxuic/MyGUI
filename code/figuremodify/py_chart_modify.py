from Qt_core import *

from code.database.py_database import PyDatabase
from code import status_messages
from code.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES, interpolate_curve
from code.database.safe_expression import evaluate_curve_expression

import numpy as np
from numpy import ndarray
from typing import Any

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
from matplotlib.style import use


def _remove_project_record(project_collection: list[dict[str, Any]] | None,
                           project_record: dict[str, Any] | None):
    if project_collection is None or project_record is None:
        return
    try:
        project_collection.remove(project_record)
    except ValueError:
        pass


def _remove_artist(artist):
    if artist is None:
        return
    try:
        artist.remove()
    except ValueError:
        pass


class PyCurveModify:
    def __init__(self, fig, axe: Axes, x_start: float, x_stop: float, style,
                 line: Line2D, expression: str, label: str,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):

        self.style = style
        self.fig = fig
        self.axe = axe

        self.x_start, self.x_stop = x_start, x_stop

        self.expression = expression

        self.label = label

        self.line = line
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw()
    
    def update_legend(self):
        self.axe.legend().remove()
        self.axe.legend()

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.line)
        self.redraw()

    def update_x_start(self, x_start: float):
        self.x_start = x_start
        x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
        try:
            y = evaluate_curve_expression(self.expression, x)
        except ValueError:
            return
        self.update_project_record(x_start=float(x_start))
        self.line.set_data(x, y)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

    def update_x_stop(self, x_stop: float):
        self.x_stop = x_stop
        x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
        try:
            y = evaluate_curve_expression(self.expression, x)
        except ValueError:
            return
        self.update_project_record(x_stop=float(x_stop))
        self.line.set_data(x, y)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

    def update_expression(self, expression: str):
        try:
            x = np.linspace(self.x_start, self.x_stop, len(self.line.get_xdata()))
            y = evaluate_curve_expression(expression, x)
            self.line.set_ydata(y)
            self.expression = expression
            self.update_project_record(expression=expression)
            self.axe.relim()
            self.axe.autoscale_view()
            self.redraw()
        except ValueError:
            pass

    def update_all(self, x_start: float, x_stop: float, expression: str):
        try:
            x = np.linspace(x_start, x_stop, 1000)
            y = evaluate_curve_expression(expression, x)
            self.x_start, self.x_stop = x_start, x_stop
            self.expression = expression
            self.update_project_record(
                x_start=float(x_start),
                x_stop=float(x_stop),
                expression=expression,
            )
            self.line.set_data(x, y)
            self.axe.relim()
            self.axe.autoscale_view()
            self.redraw()
        except ValueError:
            pass

    def update_style(self, style: str):
        self.line.set_linestyle(style)
        self.update_project_record(style=self.line.get_linestyle())
        self.update_legend()
        self.redraw()

    def update_color(self, color: str):
        self.line.set_color(color)
        self.update_project_record(color=self.line.get_color())
        self.update_legend()
        self.redraw()

    def change_legend(self, label: str):
        try:
            self.line.set_label(label)
            self.label = label
            self.update_project_record(label=label)
            self.update_legend()
            self.redraw()
        except Exception:
            pass

class PyPlotModify:
    def __init__(self, fig, axe: Axes, style=None, line: Line2D = None, x_data_name: str = None,
                 y_data_name: str = None, label: str = None,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.line = line

        self.label = label
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False

        self.current_x_data_name = x_data_name
        self.current_y_data_name = y_data_name

        # Data and mapping connection
        PyDatabase.data_connect(x_data_name, id_num=id(line), xy='x', connection_func=self.update_x_data)
        PyDatabase.data_connect(y_data_name, id_num=id(line), xy='y', connection_func=self.update_y_data)

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw()

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        PyDatabase.remove_data_connection(self.current_x_data_name, id(self.line), 'x')
        PyDatabase.remove_data_connection(self.current_y_data_name, id(self.line), 'y')
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.line)
        self.redraw()

    def update_x_data(self, x_data: ndarray):
        # Reset data when lengths do not match
        if len(x_data) == len(self.line.get_ydata()):
            self.line.set_xdata(x_data)
            # Recalculate axes limits
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            y_data = np.zeros_like(x_data)
            self.line.set_data(x_data, y_data)

        self.redraw()

    def update_y_data(self, y_data: ndarray):
        # Reset data when lengths do not match
        if len(y_data) == len(self.line.get_xdata()):
            self.line.set_ydata(y_data)
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            x_data = np.linspace(0, len(y_data), len(y_data))
            self.line.set_data(x_data, y_data)

        self.redraw()

    def update_color(self, color: str):
        self.line.set_color(color)
        self.update_project_record(color=self.line.get_color())
        self.redraw()

    def change_legend(self, label: str):
        try:
            self.line.set_label(label)
            self.label = label
            self.update_project_record(label=label)
            self.axe.legend().remove()
            self.axe.legend()
            self.redraw()
        except Exception:
            pass



class PyScatterModify:
    def __init__(self, fig, axe: Axes, style=None, scatter: PathCollection = None, x_data_name: str = None,
                 y_data_name: str = None, label: str = None,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.scatter = scatter

        self.current_x_data_name = x_data_name
        self.current_y_data_name = y_data_name

        self.label = label
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False

        # Data and mapping connection
        PyDatabase.data_connect(x_data_name, id_num=id(scatter), xy='x', connection_func=self.update_x_data)
        PyDatabase.data_connect(y_data_name, id_num=id(scatter), xy='y', connection_func=self.update_y_data)

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw()

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        PyDatabase.remove_data_connection(self.current_x_data_name, id(self.scatter), 'x')
        PyDatabase.remove_data_connection(self.current_y_data_name, id(self.scatter), 'y')
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.scatter)
        self.redraw()

    def update_x_data(self, x_data: ndarray):
        # Reset data when lengths do not match
        if len(x_data) == len(self.scatter.get_offsets()):
            self.scatter.set_offsets(np.c_[x_data, self.scatter.get_offsets()[:, 1]])
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            y_data = np.zeros_like(x_data)
            self.scatter.set_offsets(np.c_[x_data, y_data])

        self.redraw()

    def update_y_data(self, y_data: ndarray):
        # Reset data when lengths do not match
        if len(y_data) == len(self.scatter.get_offsets()):
            self.scatter.set_offsets(np.c_[self.scatter.get_offsets()[:, 0], y_data])
            self.axe.relim()
            self.axe.autoscale_view()
        else:
            x_data = np.zeros_like(y_data)
            self.scatter.set_offsets(np.c_[x_data, y_data])

        self.redraw()

    def update_color(self, color: str):
        self.scatter.set_facecolor(color)
        self.update_project_record(color=color)
        self.redraw()

    def change_legend(self, label: str):
        try:
            self.scatter.set_label(label)
            self.label = label
            self.update_project_record(label=label)
            self.axe.legend().remove()
            self.axe.legend()
            self.redraw()
        except Exception:
            pass


class PyInterpolateModify:
    def __init__(self, fig, axe: Axes, style=None, line: Line2D = None, x_data_name: str = None,
                 y_data_name: str = None, label: str = None, method: str | None = None, k: int = 3,
                 samples: int = DEFAULT_INTERPOLATION_SAMPLES,
                 lam: float | None = None, lam_auto: bool = True,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        self.style = style
        self.fig = fig
        self.axe = axe

        self.line = line

        self.current_x_data_name = x_data_name
        self.current_y_data_name = y_data_name

        self.x_data = PyDatabase.get_data(x_data_name)
        self.y_data = PyDatabase.get_data(y_data_name)

        self.label = label
        self.method = method
        self.k = k
        self.samples = int(samples)
        self.lam = lam
        self.lam_auto = bool(lam_auto)
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False

        # Data and mapping connection
        PyDatabase.data_connect(x_data_name, id_num=id(line), xy='x', connection_func=self.update_x_data)
        PyDatabase.data_connect(y_data_name, id_num=id(line), xy='y', connection_func=self.update_y_data)

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw()

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        PyDatabase.remove_data_connection(self.current_x_data_name, id(self.line), 'x')
        PyDatabase.remove_data_connection(self.current_y_data_name, id(self.line), 'y')
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.line)
        self.redraw()

    def update_x_data(self, x_data: ndarray):
        self.x_data = x_data
        self.refresh_interpolation(notify_success=False)

    def update_y_data(self, y_data: ndarray):
        self.y_data = y_data
        self.refresh_interpolation(notify_success=False)

    def _apply_interpolation(self, interpolate_name: str, k: int, samples: int,
                             lam: float | None, lam_auto: bool,
                             notify_success: bool = False) -> bool:
        try:
            x_new, y_new = interpolate_curve(
                self.x_data,
                self.y_data,
                interpolate_name,
                k=k,
                samples=samples,
                lam=lam,
                lam_auto=lam_auto,
            )
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return False
        self.line.set_data(x_new, y_new)
        self.method = interpolate_name
        self.k = int(k)
        self.samples = int(samples)
        self.lam = lam
        self.lam_auto = bool(lam_auto)
        self.update_project_record(
            method=interpolate_name,
            k=int(k),
            samples=int(samples),
            lam=None if lam is None else float(lam),
            lam_auto=bool(lam_auto),
        )
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()
        if notify_success:
            status_messages.show_success("Interpolation curve updated.")
        return True

    def refresh_interpolation(self, notify_success: bool = False) -> bool:
        if self.method is None:
            return False
        return self._apply_interpolation(
            self.method,
            self.k,
            self.samples,
            self.lam,
            self.lam_auto,
            notify_success=notify_success,
        )

    def update_interpolate(self, interpolate_name: str, k=3, samples: int | None = None,
                           lam: float | None = None, lam_auto: bool | None = None):
        target_samples = self.samples if samples is None else int(samples)
        target_lam_auto = self.lam_auto if lam_auto is None else bool(lam_auto)
        target_lam = self.lam if lam is None and not target_lam_auto else lam
        return self._apply_interpolation(
            interpolate_name,
            int(k),
            target_samples,
            target_lam,
            target_lam_auto,
            notify_success=True,
        )

    def set_x_data_name(self, data_name: str) -> bool:
        if not PyDatabase.has_data(data_name):
            return False
        self.x_data = PyDatabase.get_data(data_name)
        changed = PyDatabase.change_data_connection(
            self.current_x_data_name,
            data_name,
            id(self.line),
            'x',
        )
        if not changed:
            PyDatabase.data_connect(data_name, id(self.line), 'x', self.update_x_data)
        self.current_x_data_name = data_name
        self.update_project_record(x_data_name=data_name)
        return self.refresh_interpolation(notify_success=True)

    def set_y_data_name(self, data_name: str) -> bool:
        if not PyDatabase.has_data(data_name):
            return False
        self.y_data = PyDatabase.get_data(data_name)
        changed = PyDatabase.change_data_connection(
            self.current_y_data_name,
            data_name,
            id(self.line),
            'y',
        )
        if not changed:
            PyDatabase.data_connect(data_name, id(self.line), 'y', self.update_y_data)
        self.current_y_data_name = data_name
        self.update_project_record(y_data_name=data_name)
        return self.refresh_interpolation(notify_success=True)

    def update_color(self, color: str):
        self.line.set_color(color)
        self.update_project_record(color=self.line.get_color())
        self.redraw()

    def change_legend(self, label: str):
        try:
            self.line.set_label(label)
            self.label = label
            self.update_project_record(label=label)
            self.axe.legend().remove()
            self.axe.legend()
            self.redraw()
        except Exception:
            pass


