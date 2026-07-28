from typing import Any, Optional

from Qt_core import *
from code.database import ColumnRef, TableRepository, validate_component_name
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from code.widgets.fig_control_window.figure_inspector import (
    FigureInspectorHost,
    FigureInspectorPanel,
)
from code.widgets.common_widget.py_empty_state import PyEmptyState
from code.widgets.common_widget.min_widget.color_library import ColorLibrary

from code.widgets import qss_func
import matplotlib

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

    def __init__(
        self,
        figure_inspector_host: FigureInspectorHost | None = None,
        repository: TableRepository | None = None,
        color_library: ColorLibrary | None = None,
    ):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = qss_func.qss_loader(qss_path)
        self.setStyleSheet(qss_file)

        self.figure_inspector_host = figure_inspector_host
        if repository is None:
            raise ValueError("PyFigureWindow requires a TableRepository.")
        self.repository = repository
        self.color_library = color_library or ColorLibrary(parent=self)
        self.current_canva: Optional[PyFigureCanvas] = None
        self.canvas = {}
        self.table = None

        self.current_figure_inspector: Optional[FigureInspectorPanel] = None

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
                   create_table=True, project_path=None, component_tree=None):
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
            color_library=self.color_library,
            component_tree=component_tree,
        )
        self.canvas['canva' + str(len(self.canvas) + 1)] = canva

        figure_inspector = (
            self.figure_inspector_host.add_figure_inspector()
        )
        canva.set_figure_inspector(figure_inspector)

        self.tabwindow.addTab(canva, project_name)

        self.tabwindow.setCurrentWidget(canva)
        self._update_empty_state()

    def change_current_canvas(self):
        self._update_empty_state()
        self.current_canva = self.tabwindow.currentWidget()
        if self.current_canva is None:
            self.current_figure_inspector = None
            if self.figure_inspector_host is not None:
                self.figure_inspector_host.show_empty_state()
            if self.table is not None:
                self.table.switch_to_table(None)
            return
        self.current_figure_inspector = (
            self.figure_inspector_host.show_figure_inspector(
                self.tabwindow.currentIndex()
            )
        )
        project_id = getattr(self.current_canva, "project_id", None)
        if self.table is not None:
            self.table.switch_to_table(project_id)

    def get_current_canvas_axes_colorselector(self):
        canvas = self.current_canva
        if canvas is None or canvas.current_axes_component_id is None:
            raise ValueError("Select an axes before choosing a chart color.")
        return canvas.axes_commands.cycle_state(
            canvas.current_axes_component_id
        )

    def commit_current_canvas_color(self, selection) -> bool:
        canvas = self.current_canva
        if canvas is None or canvas.current_axes_component_id is None:
            raise ValueError("Select an axes before committing a chart color.")
        result = canvas.axes_commands.commit_color_selection(
            canvas.current_axes_component_id,
            selection,
        )
        return canvas.message_presenter.present(result)

    def clear_figures(self):
        while self.tabwindow.count():
            widget = self.tabwindow.widget(0)
            self.tabwindow.removeTab(0)
            if hasattr(widget, "cancel_pending_draw"):
                widget.cancel_pending_draw()
            widget.deleteLater()
        self.canvas.clear()
        self.current_canva = None
        self.current_figure_inspector = None
        self._update_empty_state()
        if self.figure_inspector_host is not None:
            self.figure_inspector_host.clear_figure_inspectors()

    def remove_project(self, project_name: str):
        for index in range(self.tabwindow.count()):
            canvas = self.tabwindow.widget(index)
            if getattr(canvas, "project_name", None) != project_name:
                continue
            self.tabwindow.removeTab(index)
            if hasattr(canvas, "cancel_pending_draw"):
                canvas.cancel_pending_draw()
            canvas.deleteLater()
            if self.figure_inspector_host is not None:
                self.figure_inspector_host.remove_figure_inspector(index)
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
                labels.extend(
                    snapshot.role.value.replace("_", " ").title()
                    for snapshot in snapshots
                )
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

    def load_project_figure_snapshot(
        self,
        figure: dict[str, Any],
        project_name: str,
        project_path: str | None = None,
    ):
        root_id = figure["root_component_id"]
        root = next(
            component
            for component in figure["components"]
            if component["id"] == root_id
        )
        properties = root["properties"]
        size_inches = properties.get("size_inches") or [6.4, 4.8]
        self.add_figure(
            width=float(size_inches[0]),
            height=float(size_inches[1]),
            dpi=float(properties.get("dpi", 100)),
            style=properties.get("style") or "default",
            canva_name=project_name,
            create_table=False,
            project_path=project_path,
            component_tree=figure,
        )
        canvas = self.current_canva
        if canvas is not None:
            canvas.restore_component_tree(figure)
        return canvas

    def load_figure_snapshot(self, figures: list[dict[str, Any]]):
        self.clear_figures()
        for figure in figures:
            root_id = figure["root_component_id"]
            root = next(
                component
                for component in figure["components"]
                if component["id"] == root_id
            )
            name = (
                root.get("properties", {}).get("name")
                or self._default_project_name()
            )
            self.load_project_figure_snapshot(figure, name)
