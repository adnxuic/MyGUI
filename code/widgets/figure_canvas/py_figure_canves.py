import sys
from copy import deepcopy
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
from code.database import ColumnRef, TableChangeSet, TableRepository
from code.database.table_document import new_id
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
                 repository: TableRepository | None = None, project_id: str | None = None,
                 project_name: str | None = None, project_path: str | None = None):
        super().__init__()
        if repository is None or project_id is None:
            raise ValueError("PyFigureCanvas requires a repository and project id.")
        self.repository = repository
        self.project_id = project_id
        self.style = style
        self.project_name = project_name or ""
        self.project_table_name = self.project_name
        self.project_path = project_path
        with mpl.style.context(style):
            self.fig = Figure(figsize=(width, height), dpi=dpi)
        # QtAgg scales ``Figure.dpi`` to the active screen's device pixel
        # ratio.  Keep the user/project DPI separate so that moving the
        # window between screens cannot change exports or project files.
        self._document_dpi = float(self.fig.dpi)

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
        self._data_objects: dict[str, dict[str, Any]] = {}
        self.repository.transaction_committed.connect(self._table_changed)

        self.canva = FigureCanvasQTAgg(self.fig)
        size_inches = self.fig.get_size_inches()
        self.canva.setFixedSize(
            round(float(size_inches[0]) * self._document_dpi),
            round(float(size_inches[1]) * self._document_dpi),
        )

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

    @property
    def document_dpi(self) -> float:
        """The project/export DPI, independent of the screen pixel ratio."""
        return self._document_dpi

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
        try:
            self.repository.transaction_committed.disconnect(self._table_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)

    def _table_changed(self, changes: TableChangeSet):
        if changes.project_id != self.project_id:
            return
        refreshed = False
        errors = []
        collections = {
            "plot": self.project_plots,
            "scatter": self.project_scatters,
            "interpolate": self.project_interpolates,
            "fit": self.project_fits,
        }
        for object_id, entry in list(self._data_objects.items()):
            if entry.get("record") not in collections.get(entry.get("kind"), []):
                self._data_objects.pop(object_id, None)
                continue
            modify = entry.get("modify")
            refs = getattr(modify, "refs", set())
            if modify is None or not refs.intersection(changes.changed_columns):
                continue
            refresh = getattr(modify, "refresh_data_pair", None)
            if callable(refresh):
                try:
                    refresh(redraw=False)
                    refreshed = True
                except Exception as exc:
                    errors.append(str(exc))
        if refreshed:
            self.fig.canvas.draw_idle()
        if errors:
            suffix = f" ({len(errors)} failures)" if len(errors) > 1 else ""
            status_messages.show_error(f"Chart refresh failed{suffix}: {errors[0]}")

    def _register_data_object(self, object_id: str, kind: str, record: dict[str, Any],
                              widget, modify=None):
        self._data_objects[object_id] = {
            "kind": kind,
            "record": record,
            "widget": widget,
            "modify": modify,
        }

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
    def add_plot(self, x, y, style, size, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                 record_project=True, object_id: str | None = None):
        with mpl.style.context(self.style):
            line, = self.current_axes.plot(x, y, style, markersize=size, color=color, label=label)

        project_record = None
        if record_project:
            object_id = object_id or new_id()
            project_record = {
                "object_id": object_id,
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
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
        plot_modify = PyPlotModify(
            self.repository, self.fig, self.current_axes, self.style, line, x_ref, y_ref, label,
            project_record=project_record, project_collection=self.project_plots,
        )
        plot_mod_widget = PyPlotModWidget(
            plot_modify, self.repository, self.project_id, x_ref, y_ref, color
        )

        # Add visualization object
        self.current_axes_mod.add_vis_object(plot_mod_widget.get_colorupdate_func())

        plot_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['plot_box']
        plot_box.add_widget(plot_mod_widget, 'plot')
        if project_record is not None:
            self._register_data_object(object_id, "plot", project_record, plot_mod_widget, plot_modify)

        self.redraw()

    # Add scatter plot
    def add_scatter(self, x, y, size, color, marker, label, x_ref: ColumnRef, y_ref: ColumnRef,
                    record_project=True, object_id: str | None = None):
        with mpl.style.context(self.style):
            scatter = self.current_axes.scatter(x, y, s=size, c=color, marker=marker, label=label)

        project_record = None
        if record_project:
            object_id = object_id or new_id()
            project_record = {
                "object_id": object_id,
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
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
        scatter_modify = PyScatterModify(
            self.repository, self.fig, self.current_axes, self.style, scatter, x_ref, y_ref, label,
            project_record=project_record, project_collection=self.project_scatters,
        )
        scatter_mod_widget = PyScatterModWidget(
            scatter_modify, self.repository, self.project_id, x_ref, y_ref, color
        )

        # Add visualization object
        self.current_axes_mod.add_vis_object(scatter_mod_widget.get_colorupdate_func())

        scatter_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['scatter_box']
        scatter_box.add_widget(scatter_mod_widget, 'scatter')
        if project_record is not None:
            self._register_data_object(object_id, "scatter", project_record, scatter_mod_widget, scatter_modify)

        self.redraw()

    # Add fit curve
    def add_fit_curve(self, x, y, color, label, x_ref: ColumnRef, y_ref: ColumnRef,
                      engine: str = "Python", record_project=True, fit_type=None,
                      fit_options=None, fit_result=None, expression: str = "",
                      x_start: float | None = None, x_stop: float | None = None,
                      style: str = "solid", object_id: str | None = None):
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
            object_id = object_id or new_id()
            project_record = {
                "object_id": object_id,
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
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
            repository=self.repository,
            project_id=self.project_id,
            x_ref=x_ref,
            y_ref=y_ref,
            engine=engine,
            fit_type=fit_type,
            fit_options=fit_options,
            fit_result=fit_result,
        )

        fitting_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['fitting_box']
        fitting_box.add_widget(fitting_mod_widget, "fitting")
        fitting_box.setCurrentWidget(fitting_mod_widget)
        if project_record is not None:
            self._register_data_object(object_id, "fit", project_record, fitting_mod_widget)

        self.redraw()
        return line

    # Add interpolation curve
    def add_interpolate_curve(self, x, y, x_ref: ColumnRef, y_ref: ColumnRef, method, k=3, label='interpolate',
                              color='black', record_project=True,
                              samples=DEFAULT_INTERPOLATION_SAMPLES,
                              lam=None, lam_auto=True, object_id: str | None = None):
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
            object_id = object_id or new_id()
            project_record = {
                "object_id": object_id,
                "axes_index": int(self.fig.axes.index(self.current_axes)),
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
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
        interpolate_modify = PyInterpolateModify(
            self.repository, self.fig, self.current_axes, self.style, line, x_ref, y_ref, label,
            method=method, k=k, samples=samples, lam=lam, lam_auto=lam_auto,
            project_record=project_record, project_collection=self.project_interpolates,
        )
        interpolate_mod_widget = PyInterpolateWidget(
            interpolate_modify, self.repository, self.project_id, method, k, color,
            x_ref=x_ref, y_ref=y_ref, samples=samples, lam=lam, lam_auto=lam_auto,
        )

        # Add visualization object
        self.current_axes_mod.add_vis_object(interpolate_mod_widget.get_colorupdate_func())

        interpolate_box: PyModBox = all_mod_widget.cahrt_mod_window.boxs['interpolate_box']
        interpolate_box.add_widget(interpolate_mod_widget, 'interpolate')
        if project_record is not None:
            self._register_data_object(
                object_id, "interpolate", project_record, interpolate_mod_widget, interpolate_modify
            )

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
            save_dpi = self.document_dpi
        else:
            save_dpi = dpi
        with mpl.style.context(self.style):
            self.fig.savefig(filename, dpi=save_dpi)

    @staticmethod
    def _record_refs(record: dict[str, Any]) -> set[ColumnRef]:
        refs = set()
        for field in ("x_ref", "y_ref"):
            try:
                refs.add(ColumnRef.from_dict(record.get(field)))
            except ValueError:
                pass
        return refs

    def dependent_records(self, refs: set[ColumnRef]) -> list[dict[str, Any]]:
        snapshots = []
        collections = (
            ("plot", self.project_plots),
            ("scatter", self.project_scatters),
            ("interpolate", self.project_interpolates),
            ("fit", self.project_fits),
        )
        for kind, collection in collections:
            for record in collection:
                if self._record_refs(record).intersection(refs):
                    snapshots.append({"kind": kind, "record": deepcopy(record)})
        return snapshots

    def remove_data_dependents(self, snapshots: list[dict[str, Any]]) -> None:
        for snapshot in snapshots:
            object_id = snapshot["record"].get("object_id")
            entry = self._data_objects.pop(object_id, None)
            if entry is None:
                continue
            widget = entry.get("widget")
            if widget is not None:
                widget.delete_object()
                widget.deleteLater()
        self.fig.canvas.draw_idle()

    def restore_data_dependents(self, snapshots: list[dict[str, Any]]) -> None:
        for snapshot in snapshots:
            kind = snapshot["kind"]
            record = deepcopy(snapshot["record"])
            axes_index = int(record.get("axes_index", 0))
            if not 0 <= axes_index < len(self.fig.axes):
                continue
            self.set_current_axes_by_index(axes_index)
            try:
                x_ref = ColumnRef.from_dict(record["x_ref"])
                y_ref = ColumnRef.from_dict(record["y_ref"])
                pair = self.repository.line_pair(x_ref, y_ref) if kind == "plot" else self.repository.valid_pair(x_ref, y_ref)
            except (KeyError, ValueError):
                continue
            if kind == "plot":
                self.add_plot(
                    pair.x, pair.y, record.get("style", "-"), record.get("size", 2.0),
                    record.get("color", "black"), record.get("label", ""), x_ref, y_ref,
                    object_id=record.get("object_id"),
                )
            elif kind == "scatter":
                self.add_scatter(
                    pair.x, pair.y, record.get("size", 20.0), record.get("color", "black"),
                    record.get("marker", "o"), record.get("label", ""), x_ref, y_ref,
                    object_id=record.get("object_id"),
                )
            elif kind == "interpolate":
                self.add_interpolate_curve(
                    pair.x, pair.y, x_ref, y_ref, record.get("method"),
                    k=record.get("k", 3), label=record.get("label", "interpolate"),
                    color=record.get("color", "black"), samples=record.get("samples", 1000),
                    lam=record.get("lam"), lam_auto=record.get("lam_auto", True),
                    object_id=record.get("object_id"),
                )
            elif kind == "fit":
                self.add_fit_curve(
                    pair.x, pair.y, record.get("color", "black"), record.get("label", "fitting"),
                    x_ref, y_ref, engine=record.get("engine", "Python"),
                    fit_type=record.get("fit_type"), fit_options=record.get("fit_options"),
                    fit_result=record.get("fit_result"), expression=record.get("expression", ""),
                    x_start=record.get("x_start"), x_stop=record.get("x_stop"),
                    style=record.get("style", "solid"), object_id=record.get("object_id"),
                )

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
        self.project_name = name
        self.project_table_name = name

    def project_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.project_name,
            "style": self.style,
            "dpi": self.document_dpi,
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
