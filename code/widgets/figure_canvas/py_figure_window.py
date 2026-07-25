import sys
from typing import Any, Optional

from Qt_core import *
from code import status_messages
from code.database import ColumnRef, TableRepository, validate_component_name
from code.database.interpolate_func import interpolate_dict
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from code.widgets.fig_control_window.py_fig_modify_window import PyFigModWidget
from code.widgets.common_widget.py_empty_state import PyEmptyState

from code.widgets import qss_func
import matplotlib
import numpy as np

import os

current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")

matplotlib.use("QtAgg")


class FigureTabWidget(QTabWidget):
    def __init__(self, figure_window, parent=None):
        super().__init__(parent)
        self.figure_window = figure_window

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            clicked_tab_index = self.tabBar().tabAt(event.position().toPoint())
            if clicked_tab_index != -1:
                self.show_context_menu(event.globalPosition().toPoint(), clicked_tab_index)
        super().mousePressEvent(event)

    def show_context_menu(self, position, tab_index):
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        action = menu.exec(position)
        if action == rename_action:
            self.figure_window.rename_project_from_tab(tab_index)


class PyFigureWindow(QFrame):
    requestStyleSelector = Signal()

    def __init__(self, fig_modify_window=None, repository: TableRepository | None = None):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.fig_modify_window = fig_modify_window
        if repository is None:
            raise ValueError("PyFigureWindow requires a TableRepository.")
        self.repository = repository
        self.current_canva: Optional[PyFigureCanvas] = None
        self.canvas = {}
        self.table = None

        self.current_fig_modify_widget: Optional[PyFigModWidget] = None

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.content_stack = QStackedWidget(self)

        self.empty_state = PyEmptyState(
            "No project",
            "Choose a style from the command bar to create a project and start charting.",
            "Show styles",
            self.content_stack,
        )
        self.empty_state.setObjectName("figure_empty_state")
        self.empty_state_label = self.empty_state.detail_label
        self.empty_state.primaryRequested.connect(self.requestStyleSelector)

        self.tabwindow = FigureTabWidget(self)
        self.tabwindow.currentChanged.connect(self.change_current_canvas)

        self.content_stack.addWidget(self.empty_state)
        self.content_stack.addWidget(self.tabwindow)
        self.content_stack.setCurrentWidget(self.empty_state)
        self.layout.addWidget(self.content_stack)
        self.setLayout(self.layout)

    def _update_empty_state(self):
        if self.tabwindow.count() == 0:
            self.content_stack.setCurrentWidget(self.empty_state)
        else:
            self.content_stack.setCurrentWidget(self.tabwindow)

    def set_table(self, table):
        self.table = table
        if hasattr(table, "set_figure_window"):
            table.set_figure_window(self)
        self.change_current_canvas()

    def _default_project_name(self) -> str:
        index = 1
        while self.has_project_name(f"Project{index}"):
            index += 1
        return f"Project{index}"

    def has_project_name(self, name: str) -> bool:
        for index in range(self.tabwindow.count()):
            canvas = self.tabwindow.widget(index)
            if getattr(canvas, "project_name", None) == name:
                return True
        return False

    def add_figure(self, width=None, height=None, dpi=None, style=None, canva_name=None,
                   create_table=True, project_path=None):
        project_name = validate_component_name(canva_name or self._default_project_name(), "Project name")
        if self.has_project_name(project_name):
            raise ValueError(f"Project already exists: {project_name}")
        if self.table is not None and create_table:
            self.table.create_project_table(project_name)
        project = self.repository.project_by_name(project_name)

        canva = PyFigureCanvas(
            self,
            width=width,
            height=height,
            dpi=dpi,
            style=style,
            repository=self.repository,
            project_id=project.id,
            project_name=project_name,
            project_path=project_path,
        )
        self.canvas['canva' + str(len(self.canvas) + 1)] = canva

        figmod_widget = self.fig_modify_window.add_figmod_widget()

        canva.setFigModifyWidget(figmod_widget)

        self.tabwindow.addTab(canva, project_name)

        self.tabwindow.setCurrentWidget(canva)
        self._update_empty_state()

    def change_current_canvas(self):
        self._update_empty_state()
        self.current_canva = self.tabwindow.currentWidget()
        if self.current_canva is None:
            self.current_fig_modify_widget = None
            if self.fig_modify_window is not None and hasattr(self.fig_modify_window, "empty_state"):
                self.fig_modify_window.stacklayout.setCurrentWidget(
                    self.fig_modify_window.empty_state
                )
            if self.table is not None:
                self.table.switch_to_table(None)
            return
        inspector_index = self.tabwindow.currentIndex()
        if hasattr(self.fig_modify_window, "empty_state"):
            inspector_index += 1
        self.fig_modify_window.stacklayout.setCurrentIndex(inspector_index)
        self.current_fig_modify_widget = self.fig_modify_window.stacklayout.currentWidget()
        project_id = getattr(self.current_canva, "project_id", None)
        if self.table is not None:
            self.table.switch_to_table(project_id)

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
        self._update_empty_state()
        if hasattr(self.fig_modify_window, "clear_figmod_widgets"):
            self.fig_modify_window.clear_figmod_widgets()

    def remove_project(self, project_name: str):
        for index in range(self.tabwindow.count()):
            canvas = self.tabwindow.widget(index)
            if getattr(canvas, "project_name", None) != project_name:
                continue
            self.tabwindow.removeTab(index)
            if hasattr(canvas, "cancel_pending_draw"):
                canvas.cancel_pending_draw()
            canvas.deleteLater()
            inspector_index = index + (1 if hasattr(self.fig_modify_window, "empty_state") else 0)
            if self.fig_modify_window is not None and inspector_index < self.fig_modify_window.stacklayout.count():
                widget = self.fig_modify_window.stacklayout.widget(inspector_index)
                self.fig_modify_window.stacklayout.removeWidget(widget)
                widget.deleteLater()
            self.canvas = {
                key: value
                for key, value in self.canvas.items()
                if value is not canvas
            }
            self.change_current_canvas()
            return

    def cancel_pending_draws(self):
        for index in range(self.tabwindow.count()):
            widget = self.tabwindow.widget(index)
            if hasattr(widget, "cancel_pending_draw"):
                widget.cancel_pending_draw()

    def prepare_dependency_cascade(self, refs: list[ColumnRef], reason: str):
        target_refs = set(refs)
        captured = []
        total = 0
        labels = []
        for index in range(self.tabwindow.count()):
            canvas = self.tabwindow.widget(index)
            if not isinstance(canvas, PyFigureCanvas) or canvas.project_id not in {ref.project_id for ref in refs}:
                continue
            snapshots = canvas.dependent_records(target_refs)
            if snapshots:
                captured.append((canvas, snapshots))
                total += len(snapshots)
                labels.extend(snapshot["kind"].title() for snapshot in snapshots)
        if not captured:
            if reason == "delete-sheet" and QMessageBox.question(
                self,
                "Delete Sheet",
                "Delete the selected sheet?",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return False
            return (lambda: None, lambda: None)
        summary = ", ".join(labels[:8])
        if len(labels) > 8:
            summary += f", and {len(labels) - 8} more"
        action = "change the column type" if reason == "type" else "delete the selected data"
        response = QMessageBox.question(
            self,
            "Dependent Objects",
            f"This operation will remove {total} dependent objects ({summary}).\n\nContinue and {action}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return False

        def redo():
            for canvas, snapshots in captured:
                canvas.remove_data_dependents(snapshots)

        def undo():
            for canvas, snapshots in captured:
                canvas.restore_data_dependents(snapshots)

        return redo, undo

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

    def rename_project_from_tab(self, tab_index: int):
        if tab_index < 0 or tab_index >= self.tabwindow.count():
            return
        old_name = self.tabwindow.tabText(tab_index)
        new_name, ok = QInputDialog.getText(self, "Rename Project", "Project name:", text=old_name)
        if not ok:
            return
        try:
            self.rename_project(tab_index, new_name)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Project", str(exc))

    def rename_project(self, tab_index: int, new_name: str):
        new_name = validate_component_name(new_name, "Project name")
        canvas = self.tabwindow.widget(tab_index)
        if canvas is None:
            raise IndexError(f"Invalid project index: {tab_index}")
        old_name = canvas.project_name
        if old_name == new_name:
            return
        if self.has_project_name(new_name):
            raise ValueError(f"Project already exists: {new_name}")
        if self.table is not None:
            self.table.rename_project_table(old_name, new_name)
        canvas.set_project_name(new_name)
        self.tabwindow.setTabText(tab_index, new_name)

    @staticmethod
    def _select_project_axes(canvas: PyFigureCanvas, record: dict[str, Any]) -> bool:
        if not canvas.fig.axes:
            return False
        axes_index = int(record.get("axes_index", 0))
        if axes_index < 0 or axes_index >= len(canvas.fig.axes):
            return False
        canvas.set_current_axes_by_index(axes_index)
        return True

    def _project_data_pair(self, record: dict[str, Any], chart_label: str, line_mode: bool = False):
        try:
            x_ref = ColumnRef.from_dict(record.get("x_ref"))
            y_ref = ColumnRef.from_dict(record.get("y_ref"))
        except ValueError as exc:
            status_messages.show_warning(
                f"{chart_label} skipped during project restore; invalid data reference: {exc}"
            )
            return None
        if not self.repository.has_ref(x_ref) or not self.repository.has_ref(y_ref):
            status_messages.show_warning(
                f"{chart_label} skipped during project restore; data source is missing."
            )
            return None
        try:
            pair = self.repository.line_pair(x_ref, y_ref) if line_mode else self.repository.valid_pair(x_ref, y_ref)
        except ValueError as exc:
            status_messages.show_warning(
                f"{chart_label} skipped during project restore: {exc}"
            )
            return None
        if not pair.valid_mask.any():
            status_messages.show_warning(f"{chart_label} skipped during project restore; no valid row pairs.")
            return None
        if pair.missing_count:
            status_messages.show_warning(
                f"{chart_label}: filtered or masked {pair.missing_count} rows with missing values."
            )
        return x_ref, y_ref, pair.x, pair.y

    def _populate_canvas_from_snapshot(self, canvas: PyFigureCanvas, figure: dict[str, Any]):
        axes_layouts = figure.get("axes_layouts") or []
        if not axes_layouts and figure.get("axes_count"):
            axes_layouts = [{"nrows": int(figure["axes_count"]), "ncols": 1}]

        for layout in axes_layouts:
            canvas.add_axes(
                nrows=int(layout.get("nrows", 1)),
                ncols=int(layout.get("ncols", 1)),
                record_project=True,
            )

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
            data_pair = self._project_data_pair(plot, "Plot", line_mode=True)
            if data_pair is None:
                continue
            x_ref, y_ref, x_data, y_data = data_pair
            canvas.add_plot(
                x=x_data,
                y=y_data,
                style=plot.get("style", "-"),
                size=float(plot.get("size", 2.0)),
                color=plot.get("color", "black"),
                label=plot.get("label", ""),
                x_ref=x_ref,
                y_ref=y_ref,
                object_id=plot.get("object_id"),
                record_project=True,
            )

        for scatter in figure.get("scatters", []):
            if not self._select_project_axes(canvas, scatter):
                continue
            data_pair = self._project_data_pair(scatter, "Scatter")
            if data_pair is None:
                continue
            x_ref, y_ref, x_data, y_data = data_pair
            canvas.add_scatter(
                x=x_data,
                y=y_data,
                size=float(scatter.get("size", 20.0)),
                color=scatter.get("color", "black"),
                marker=scatter.get("marker", "o"),
                label=scatter.get("label", ""),
                x_ref=x_ref,
                y_ref=y_ref,
                object_id=scatter.get("object_id"),
                record_project=True,
            )

        for interpolate in figure.get("interpolates", []):
            if not self._select_project_axes(canvas, interpolate):
                continue
            method = interpolate.get("method")
            if method not in interpolate_dict:
                continue
            data_pair = self._project_data_pair(interpolate, "Interpolation")
            if data_pair is None:
                continue
            x_ref, y_ref, x_data, y_data = data_pair
            canvas.add_interpolate_curve(
                x=x_data,
                y=y_data,
                x_ref=x_ref,
                y_ref=y_ref,
                object_id=interpolate.get("object_id"),
                method=method,
                k=int(interpolate.get("k", 3)),
                samples=int(interpolate.get("samples", 1000)),
                lam=interpolate.get("lam"),
                lam_auto=bool(interpolate.get("lam_auto", True)),
                color=interpolate.get("color", "black"),
                label=interpolate.get("label", "interpolate"),
                record_project=True,
            )

        for fit in figure.get("fits", []):
            if not self._select_project_axes(canvas, fit):
                continue
            data_pair = self._project_data_pair(fit, "Fit")
            if data_pair is None:
                continue
            x_ref, y_ref, x_data, y_data = data_pair
            canvas.add_fit_curve(
                x=x_data,
                y=y_data,
                color=fit.get("color", "black"),
                label=fit.get("label", "fitting"),
                x_ref=x_ref,
                y_ref=y_ref,
                object_id=fit.get("object_id"),
                engine=fit.get("engine", "Python"),
                record_project=True,
                fit_type=fit.get("fit_type"),
                fit_options=fit.get("fit_options"),
                fit_result=fit.get("fit_result"),
                expression=fit.get("expression", ""),
                x_start=float(fit.get("x_start", 0.0)),
                x_stop=float(fit.get("x_stop", 1.0)),
                style=fit.get("style", "solid"),
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

        canvas.apply_axes_snapshot(figure.get("axes", []))

    def load_project_figure_snapshot(self, figure: dict[str, Any], project_name: str,
                                     project_path: str | None = None):
        size_inches = figure.get("size_inches") or [6.4, 4.8]
        self.add_figure(
            width=float(size_inches[0]),
            height=float(size_inches[1]),
            dpi=float(figure.get("dpi", 100)),
            style=figure.get("style") or "default",
            canva_name=project_name,
            create_table=False,
            project_path=project_path,
        )
        canvas = self.current_canva
        if canvas is not None:
            self._populate_canvas_from_snapshot(canvas, figure)
        return canvas

    def load_figure_snapshot(self, figures: list[dict[str, Any]]):
        self.clear_figures()
        for figure in figures:
            name = figure.get("name") or self._default_project_name()
            self.load_project_figure_snapshot(figure, name)
