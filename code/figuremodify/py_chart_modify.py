from __future__ import annotations

from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D

from code import status_messages
from code.database import ColumnRef, TableRepository
from code.database.interpolate_func import DEFAULT_INTERPOLATION_SAMPLES, interpolate_curve
from code.database.safe_expression import evaluate_curve_expression


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
        self.fig.canvas.draw_idle()

    def update_legend(self):
        legend = self.axe.get_legend()
        if legend is not None:
            legend.remove()
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
        except ValueError:
            return
        self.line.set_ydata(y)
        self.expression = expression
        self.update_project_record(expression=expression)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

    def update_all(self, x_start: float, x_stop: float, expression: str):
        try:
            x = np.linspace(x_start, x_stop, 1000)
            y = evaluate_curve_expression(expression, x)
        except ValueError:
            return
        self.x_start, self.x_stop = x_start, x_stop
        self.expression = expression
        self.update_project_record(x_start=float(x_start), x_stop=float(x_stop), expression=expression)
        self.line.set_data(x, y)
        self.axe.relim()
        self.axe.autoscale_view()
        self.redraw()

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
        self.line.set_label(label)
        self.label = label
        self.update_project_record(label=label)
        self.update_legend()
        self.redraw()


class _DataModifyBase:
    chart_label = "Chart"

    def __init__(self, repository: TableRepository, fig, axe: Axes,
                 x_ref: ColumnRef, y_ref: ColumnRef, label: str,
                 project_record: dict[str, Any] | None,
                 project_collection: list[dict[str, Any]] | None):
        self.repository = repository
        self.fig = fig
        self.axe = axe
        self.current_x_ref = x_ref
        self.current_y_ref = y_ref
        self.label = label
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False

    @property
    def refs(self) -> set[ColumnRef]:
        return {self.current_x_ref, self.current_y_ref}

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.fig.canvas.draw_idle()

    def _valid_refs(self) -> bool:
        if self.repository.has_ref(self.current_x_ref) and self.repository.has_ref(self.current_y_ref):
            return True
        status_messages.show_error(f"{self.chart_label} data source was removed.")
        return False

    def set_x_ref(self, ref: ColumnRef | None) -> bool:
        if ref is None or not self.repository.has_ref(ref):
            return False
        self.current_x_ref = ref
        self.update_project_record(x_ref=ref.to_dict())
        return self.refresh_data_pair(redraw=True)

    def set_y_ref(self, ref: ColumnRef | None) -> bool:
        if ref is None or not self.repository.has_ref(ref):
            return False
        self.current_y_ref = ref
        self.update_project_record(y_ref=ref.to_dict())
        return self.refresh_data_pair(redraw=True)

    def _warn_missing(self, count: int):
        if count:
            status_messages.show_warning(f"{self.chart_label}: ignored or masked {count} rows with missing values.")


class PyPlotModify(_DataModifyBase):
    chart_label = "Plot"

    def __init__(self, repository: TableRepository, fig, axe: Axes, style=None,
                 line: Line2D | None = None, x_ref: ColumnRef | None = None,
                 y_ref: ColumnRef | None = None, label: str | None = None,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        super().__init__(repository, fig, axe, x_ref, y_ref, label or "", project_record, project_collection)
        self.style = style
        self.line = line

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.line)
        self.redraw()

    def refresh_data_pair(self, redraw: bool = True) -> bool:
        if not self._valid_refs():
            self.line.set_data([], [])
            if redraw:
                self.redraw()
            return False
        try:
            pair = self.repository.line_pair(self.current_x_ref, self.current_y_ref)
        except ValueError as exc:
            self.line.set_data([], [])
            status_messages.show_error(str(exc))
            if redraw:
                self.redraw()
            return False
        self.line.set_data(pair.x, pair.y)
        self._warn_missing(pair.missing_count)
        self.axe.relim()
        self.axe.autoscale_view()
        if redraw:
            self.redraw()
        return bool(pair.valid_mask.any())

    def update_color(self, color: str):
        self.line.set_color(color)
        self.update_project_record(color=self.line.get_color())
        self.redraw()

    def change_legend(self, label: str):
        self.line.set_label(label)
        self.label = label
        self.update_project_record(label=label)
        legend = self.axe.get_legend()
        if legend is not None:
            legend.remove()
        self.axe.legend()
        self.redraw()


class PyScatterModify(_DataModifyBase):
    chart_label = "Scatter"

    def __init__(self, repository: TableRepository, fig, axe: Axes, style=None,
                 scatter: PathCollection | None = None, x_ref: ColumnRef | None = None,
                 y_ref: ColumnRef | None = None, label: str | None = None,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        super().__init__(repository, fig, axe, x_ref, y_ref, label or "", project_record, project_collection)
        self.style = style
        self.scatter = scatter

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.scatter)
        self.redraw()

    def refresh_data_pair(self, redraw: bool = True) -> bool:
        if not self._valid_refs():
            self.scatter.set_offsets(np.empty((0, 2)))
            if redraw:
                self.redraw()
            return False
        try:
            pair = self.repository.valid_pair(self.current_x_ref, self.current_y_ref)
        except ValueError as exc:
            self.scatter.set_offsets(np.empty((0, 2)))
            status_messages.show_error(str(exc))
            if redraw:
                self.redraw()
            return False
        self.scatter.set_offsets(np.column_stack((pair.x, pair.y)) if pair.x.size else np.empty((0, 2)))
        self._warn_missing(pair.missing_count)
        self.axe.relim()
        self.axe.autoscale_view()
        if redraw:
            self.redraw()
        return bool(pair.x.size)

    def update_color(self, color: str):
        self.scatter.set_facecolor(color)
        self.update_project_record(color=color)
        self.redraw()

    def change_legend(self, label: str):
        self.scatter.set_label(label)
        self.label = label
        self.update_project_record(label=label)
        legend = self.axe.get_legend()
        if legend is not None:
            legend.remove()
        self.axe.legend()
        self.redraw()


class PyInterpolateModify(_DataModifyBase):
    chart_label = "Interpolation"

    def __init__(self, repository: TableRepository, fig, axe: Axes, style=None,
                 line: Line2D | None = None, x_ref: ColumnRef | None = None,
                 y_ref: ColumnRef | None = None, label: str | None = None,
                 method: str | None = None, k: int = 3,
                 samples: int = DEFAULT_INTERPOLATION_SAMPLES,
                 lam: float | None = None, lam_auto: bool = True,
                 project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        super().__init__(repository, fig, axe, x_ref, y_ref, label or "", project_record, project_collection)
        self.style = style
        self.line = line
        self.method = method
        self.k = int(k)
        self.samples = int(samples)
        self.lam = lam
        self.lam_auto = bool(lam_auto)

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        _remove_project_record(self.project_collection, self.project_record)
        _remove_artist(self.line)
        self.redraw()

    def _apply_interpolation(self, method: str, k: int, samples: int,
                             lam: float | None, lam_auto: bool,
                             notify_success: bool = False, redraw: bool = True) -> bool:
        if not self._valid_refs():
            self.line.set_data([], [])
            if redraw:
                self.redraw()
            return False
        try:
            pair = self.repository.valid_pair(self.current_x_ref, self.current_y_ref)
            if pair.x.size == 0:
                raise ValueError("Interpolation has no valid X/Y row pairs.")
            x_new, y_new = interpolate_curve(
                pair.x, pair.y, method, k=k, samples=samples, lam=lam, lam_auto=lam_auto
            )
        except ValueError as exc:
            self.line.set_data([], [])
            status_messages.show_error(str(exc))
            if redraw:
                self.redraw()
            return False
        self.line.set_data(x_new, y_new)
        self._warn_missing(pair.missing_count)
        self.method = method
        self.k = int(k)
        self.samples = int(samples)
        self.lam = lam
        self.lam_auto = bool(lam_auto)
        self.update_project_record(
            method=method, k=int(k), samples=int(samples),
            lam=None if lam is None else float(lam), lam_auto=bool(lam_auto),
        )
        self.axe.relim()
        self.axe.autoscale_view()
        if redraw:
            self.redraw()
        if notify_success:
            status_messages.show_success("Interpolation curve updated.")
        return True

    def refresh_data_pair(self, redraw: bool = True) -> bool:
        if self.method is None:
            return False
        return self._apply_interpolation(
            self.method, self.k, self.samples, self.lam, self.lam_auto, redraw=redraw
        )

    def update_interpolate(self, method: str, k=3, samples: int | None = None,
                           lam: float | None = None, lam_auto: bool | None = None):
        target_samples = self.samples if samples is None else int(samples)
        target_lam_auto = self.lam_auto if lam_auto is None else bool(lam_auto)
        target_lam = self.lam if lam is None and not target_lam_auto else lam
        return self._apply_interpolation(
            method, int(k), target_samples, target_lam, target_lam_auto, notify_success=True
        )

    def set_x_ref(self, ref: ColumnRef | None) -> bool:
        if ref is None or not self.repository.has_ref(ref):
            return False
        self.current_x_ref = ref
        self.update_project_record(x_ref=ref.to_dict())
        return self.refresh_data_pair()

    def set_y_ref(self, ref: ColumnRef | None) -> bool:
        if ref is None or not self.repository.has_ref(ref):
            return False
        self.current_y_ref = ref
        self.update_project_record(y_ref=ref.to_dict())
        return self.refresh_data_pair()

    def update_color(self, color: str):
        self.line.set_color(color)
        self.update_project_record(color=self.line.get_color())
        self.redraw()

    def change_legend(self, label: str):
        self.line.set_label(label)
        self.label = label
        self.update_project_record(label=label)
        legend = self.axe.get_legend()
        if legend is not None:
            legend.remove()
        self.axe.legend()
        self.redraw()
