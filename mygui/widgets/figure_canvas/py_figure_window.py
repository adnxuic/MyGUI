"""Manage the tabbed collection of application figures."""

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QFrame,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from mygui import status_messages
from mygui.database import ColumnRef, TableRepository, validate_component_name
from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
from mygui.widgets.figure_canvas.project_metadata import ProjectMetadataService
from mygui.widgets.fig_control_window.figure_inspector import (
    FigureInspectorHost,
    FigureInspectorPanel,
)
from mygui.widgets.common_widget.py_empty_state import PyEmptyState
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.resources import load_qss_resource


class _ProjectHistoryShortcutFilter(QObject):
    """Route project history keys while preserving native text editing."""

    def __init__(self, figure_window: "PyFigureWindow") -> None:
        super().__init__(figure_window)
        self.figure_window = figure_window

    @staticmethod
    def _inside_spin_box(widget: QWidget) -> bool:
        current = widget
        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                return True
            current = current.parentWidget()
        return False

    @classmethod
    def _native_text_history_available(
        cls,
        widget: QWidget,
        *,
        redo: bool,
    ) -> bool:
        if cls._inside_spin_box(widget):
            return False
        if isinstance(widget, QLineEdit):
            available = (
                widget.isRedoAvailable()
                if redo
                else widget.isUndoAvailable()
            )
            return widget.isModified() and available
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            document = widget.document()
            available = (
                document.isRedoAvailable()
                if redo
                else document.isUndoAvailable()
            )
            return document.isModified() and available
        return False

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.KeyPress:
            return False
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if not control or bool(modifiers & Qt.KeyboardModifier.AltModifier):
            return False
        key = event.key()
        redo = key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift)
        if key != Qt.Key.Key_Z and not redo:
            return False

        application = QApplication.instance()
        focus = application.focusWidget() if application is not None else None
        if focus is not None and focus.window() is not self.figure_window.window():
            return False
        if focus is not None and self._native_text_history_available(
            focus,
            redo=redo,
        ):
            return False

        canvas = self.figure_window.current_canva
        if canvas is None:
            return False
        if redo:
            canvas.figure_history.redo()
        else:
            canvas.figure_history.undo()
        event.accept()
        return True

class FigureTabWidget(QTabWidget):
    """Provide the figure tab widget Qt widget."""

    def __init__(self, figure_window, parent=None):
        super().__init__(parent)
        self.figure_window = figure_window
        tab_bar = self.tabBar()
        tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        """Show the menu for the exact tab under the pointer."""

        tab_index = self.tabBar().tabAt(position)
        if tab_index < 0:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Rename Project")
        menu.addSeparator()
        close_action = menu.addAction("Close Project")
        action = menu.exec(self.tabBar().mapToGlobal(position))
        if action == rename_action:
            self.figure_window.rename_project_from_tab(tab_index)
        elif action == close_action:
            self.figure_window.projectCloseRequested.emit(tab_index)


class PyFigureWindow(QFrame):
    """Provide the py figure window Qt widget."""

    requestStyleSelector = Signal()
    projectCloseRequested = Signal(int)
    figureExportRequested = Signal(object)

    def __init__(
        self,
        figure_inspector_host: FigureInspectorHost | None = None,
        repository: TableRepository | None = None,
        color_library: ColorLibrary | None = None,
        component_tree_host=None,
    ):
        super().__init__()

        self.setObjectName('figure_window')
        qss_file = load_qss_resource(
            "mygui/widgets/figure_canvas/style.qss"
        )
        self.setStyleSheet(qss_file)

        self.figure_inspector_host = figure_inspector_host
        self.component_tree_host = component_tree_host
        if repository is None:
            raise ValueError("PyFigureWindow requires a TableRepository.")
        self.repository = repository
        if color_library is None:
            raise ValueError("PyFigureWindow requires the shared ColorLibrary.")
        self.color_library = color_library
        self.current_canva: Optional[PyFigureCanvas] = None
        self.canvas = {}
        self._clean_fingerprints: dict[str, str] = {}
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
        self.project_metadata = ProjectMetadataService(self, self.repository)
        self._history_shortcut_filter = _ProjectHistoryShortcutFilter(self)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self._history_shortcut_filter)

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
        """Set table."""

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
        """Return whether this object has project name."""

        normalized = str(name).strip().casefold()
        return any(
            self.repository.project(project_id).name.casefold() == normalized
            for project_id in self.canvas
            if project_id in self.repository.projects
        )

    def add_figure(self, width=None, height=None, dpi=None, style=None, canva_name=None,
                   create_table=True, project_path=None, component_tree=None):
        """Add figure."""

        project_name = validate_component_name(canva_name or self._default_project_name(), "Project name")
        if self.has_project_name(project_name):
            raise ValueError(f"Project already exists: {project_name}")
        created_project_id = None
        if self.table is not None and create_table:
            self.table.create_project_table(project_name, publish=False)
            created_project_id = self.repository.project_by_name(
                project_name
            ).id
        project = self.repository.project_by_name(project_name)
        canva = None
        figure_inspector = None
        inspector_added = False
        try:
            canva = PyFigureCanvas(
                self,
                width=width,
                height=height,
                dpi=dpi,
                style=style,
                repository=self.repository,
                project_id=project.id,
                project_metadata=self.project_metadata,
                project_path=project_path,
                color_library=self.color_library,
                component_tree=component_tree,
            )
            canva.exportRequested.connect(self.figureExportRequested)
            figure_inspector = self.figure_inspector_host.add_figure_inspector(
                canva.component_registry.get(canva.root_component_id),
                canva.editor_context,
                publish=False,
            )
            canva.set_figure_inspector(figure_inspector)
            if component_tree is not None:
                canva.restore_component_tree(component_tree)
            self.figure_inspector_host.publish_figure_inspector(
                figure_inspector
            )
            inspector_added = True

            blocked = self.tabwindow.blockSignals(True)
            try:
                added_index = self.tabwindow.addTab(canva, project_name)
                if added_index < 0:
                    raise RuntimeError("Could not add the Figure project tab.")
                self.canvas[project.id] = canva
                self.tabwindow.setCurrentWidget(canva)
            finally:
                self.tabwindow.blockSignals(blocked)
            self.change_current_canvas()
            self._update_empty_state()
            if created_project_id is not None:
                self.repository.publish_project_added(created_project_id)
        except Exception as primary_error:
            cleanup_errors = []

            def cleanup(action):
                try:
                    action()
                except Exception as cleanup_error:
                    cleanup_errors.append(cleanup_error)

            cleanup(lambda: self.canvas.pop(project.id, None))
            if canva is not None:
                index = self.tabwindow.indexOf(canva)
                if index >= 0:
                    cleanup(lambda: self.tabwindow.removeTab(index))
            if inspector_added:
                cleanup(
                    lambda: self.figure_inspector_host.remove_figure_inspector_panel(
                        figure_inspector
                    )
                )
            elif figure_inspector is not None:
                cleanup(figure_inspector.dispose)
                cleanup(lambda: figure_inspector.setParent(None))
                cleanup(figure_inspector.deleteLater)
            if canva is not None:
                cleanup(canva.dispose)
                cleanup(lambda: canva.setParent(None))
                cleanup(canva.deleteLater)
            if created_project_id is not None and self.table is not None:
                cleanup(
                    lambda: self.table.remove_project_table(
                        created_project_id,
                        publish=False,
                    )
                )
            cleanup(self.change_current_canvas)
            cleanup(self._update_empty_state)
            if cleanup_errors:
                raise RuntimeError(
                    f"{primary_error} Project publication rollback was incomplete: "
                    + "; ".join(str(error) for error in cleanup_errors)
                ) from primary_error
            raise
        return canva

    @staticmethod
    def _snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
        from mygui.project_io import project_fingerprint

        return project_fingerprint(snapshot)

    def mark_canvas_clean(
        self,
        canvas: PyFigureCanvas,
        *,
        snapshot: dict[str, Any] | None = None,
        fingerprint: str | None = None,
    ) -> None:
        """Record the current persisted state as the clean baseline."""

        if fingerprint is None and snapshot is None:
            from mygui.project_io import project_snapshot

            snapshot = project_snapshot(self, canvas=canvas)
        if fingerprint is None:
            fingerprint = self._snapshot_fingerprint(snapshot)
        self.repository.undo_stack(canvas.project_id).setClean()
        self._clean_fingerprints[canvas.project_id] = fingerprint

    def is_canvas_dirty(self, canvas: PyFigureCanvas) -> bool:
        """Return whether a canvas differs from its latest load/save state."""

        baseline = self._clean_fingerprints.get(canvas.project_id)
        if baseline is None:
            return True
        try:
            from mygui.project_io import project_snapshot

            current = project_snapshot(self, canvas=canvas)
            return self._snapshot_fingerprint(current) != baseline
        except Exception:
            # Snapshot failures must never silently permit data loss.
            return True

    def canvases(self) -> tuple[PyFigureCanvas, ...]:
        """Return project canvases in tab order."""

        return tuple(
            self.tabwindow.widget(index)
            for index in range(self.tabwindow.count())
        )

    def change_current_canvas(self):
        """Change current canvas."""

        self._update_empty_state()
        self.current_canva = self.tabwindow.currentWidget()
        if self.current_canva is None:
            self.current_figure_inspector = None
            if self.figure_inspector_host is not None:
                self.figure_inspector_host.show_empty_state()
            if self.component_tree_host is not None:
                self.component_tree_host.set_canvas(None)
            if self.table is not None:
                self.table.switch_to_table(None)
            return
        self.current_figure_inspector = (
            self.figure_inspector_host.show_figure_inspector(
                self.tabwindow.currentIndex()
            )
        )
        project_id = getattr(self.current_canva, "project_id", None)
        if self.component_tree_host is not None:
            self.component_tree_host.set_canvas(self.current_canva)
        if self.table is not None:
            self.table.switch_to_table(project_id)

    def get_current_canvas_axes_colorselector(self):
        """Return current canvas axes colorselector."""

        canvas = self.current_canva
        if canvas is None or canvas.current_axes_component_id is None:
            raise ValueError("Select an axes before choosing a chart color.")
        return canvas.creation_color_cycle()

    def commit_current_canvas_color(
        self,
        selection,
        *,
        preview_cycle=None,
    ) -> bool:
        """Commit current canvas color."""

        canvas = self.current_canva
        if canvas is None or canvas.current_axes_component_id is None:
            raise ValueError("Select an axes before committing a chart color.")
        result = canvas.figure_history.perform(
            "Choose Chart Color",
            lambda: canvas.axes_commands.commit_color_selection(
                canvas.current_axes_component_id,
                selection,
                preview_cycle=preview_cycle,
            ),
        )
        return canvas.message_presenter.present(result)

    def clear_figures(self):
        """Clear figures."""

        project_ids = [
            str(self.tabwindow.widget(index).project_id)
            for index in range(self.tabwindow.count())
            if getattr(self.tabwindow.widget(index), "project_id", None)
            is not None
        ]
        while self.tabwindow.count():
            widget = self.tabwindow.widget(0)
            self.tabwindow.removeTab(0)
            if hasattr(widget, "dispose"):
                widget.dispose()
            widget.deleteLater()
        self.canvas.clear()
        self._clean_fingerprints.clear()
        self.current_canva = None
        self.current_figure_inspector = None
        self._update_empty_state()
        if self.component_tree_host is not None:
            self.component_tree_host.set_canvas(None)
            for project_id in project_ids:
                self.component_tree_host.forget_project(project_id)
        if self.figure_inspector_host is not None:
            self.figure_inspector_host.clear_figure_inspectors()

    def remove_project_by_id(self, project_id: str) -> bool:
        """Remove one Figure-side project by its stable repository id."""

        canvas = self.canvas.get(project_id)
        if canvas is None:
            return False
        index = self.tabwindow.indexOf(canvas)
        if index < 0:
            return False
        return self.remove_project_at(index)

    def remove_project_at(self, index: int) -> bool:
        """Remove one Figure-side project without prompting or table cleanup."""

        if index < 0 or index >= self.tabwindow.count():
            return False
        canvas = self.tabwindow.widget(index)
        project_id = getattr(canvas, "project_id", None)
        if hasattr(canvas, "dispose"):
            canvas.dispose()
        was_blocked = self.tabwindow.blockSignals(True)
        try:
            self.tabwindow.removeTab(index)
            if self.figure_inspector_host is not None:
                self.figure_inspector_host.remove_figure_inspector(index)
        finally:
            self.tabwindow.blockSignals(was_blocked)
        if project_id is not None:
            self.canvas.pop(project_id, None)
            self._clean_fingerprints.pop(project_id, None)
        canvas.deleteLater()
        self.change_current_canvas()
        if project_id is not None and self.component_tree_host is not None:
            self.component_tree_host.forget_project(project_id)
        return True

    def close_project_at(self, index: int) -> bool:
        """Remove a complete project from Figure, Table, and Repository state."""

        if index < 0 or index >= self.tabwindow.count():
            return False
        canvas = self.tabwindow.widget(index)
        project_id = canvas.project_id
        if not self.remove_project_at(index):
            return False
        if self.table is not None:
            self.table.remove_project_table(project_id)
        self.change_current_canvas()
        return True

    def prepare_dependency_cascade(self, refs: list[ColumnRef], reason: str):
        """Capture dependent components before deleting table data."""

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
            prepared = []
            try:
                for canvas, snapshots in captured:
                    prepared.append(
                        (
                            canvas,
                            snapshots,
                            canvas.prepare_data_dependents(snapshots),
                        )
                    )
            except Exception as exc:
                status_messages.show_error(str(exc))
                return False
            committed = []
            for canvas, snapshots, request in prepared:
                if canvas.remove_data_dependents(snapshots, request):
                    committed.append((canvas, snapshots))
                    continue
                rollback_errors = []
                for committed_canvas, committed_snapshots in reversed(committed):
                    try:
                        committed_canvas.restore_data_dependents(
                            committed_snapshots
                        )
                    except Exception as exc:
                        rollback_errors.append(str(exc))
                if rollback_errors:
                    status_messages.show_error(
                        "Dependent deletion failed and cross-canvas rollback "
                        "was incomplete: " + "; ".join(rollback_errors)
                    )
                return False
            return True

        def undo():
            restored = []
            try:
                for canvas, snapshots in captured:
                    canvas.restore_data_dependents(snapshots)
                    restored.append((canvas, snapshots))
            except Exception:
                rollback_errors = []
                for restored_canvas, restored_snapshots in reversed(restored):
                    try:
                        request = restored_canvas.prepare_data_dependents(
                            restored_snapshots
                        )
                        if not restored_canvas.remove_data_dependents(
                            restored_snapshots,
                            request,
                        ):
                            rollback_errors.append(
                                "restored dependent removal was rejected"
                            )
                    except Exception as rollback_error:
                        rollback_errors.append(str(rollback_error))
                if rollback_errors:
                    status_messages.show_error(
                        "Dependent restore failed and rollback was incomplete: "
                        + "; ".join(rollback_errors)
                    )
                raise
            return True

        return redo, undo

    def rename_project_from_tab(self, tab_index: int):
        """Rename project from tab."""

        if tab_index < 0 or tab_index >= self.tabwindow.count():
            return
        old_name = self.tabwindow.tabText(tab_index)
        new_name, ok = QInputDialog.getText(self, "Rename Project", "Project name:", text=old_name)
        if not ok:
            return
        try:
            canvas = self.tabwindow.widget(tab_index)
            if not isinstance(canvas, PyFigureCanvas):
                raise IndexError(f"Invalid project index: {tab_index}")
            self.rename_project(canvas.project_id, new_name)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Project", str(exc))

    def rename_project(self, project_id: str, new_name: str):
        """Rename project."""

        canvas = self.canvas.get(str(project_id))
        if canvas is None:
            raise KeyError(f"Unknown Figure project: {project_id}")
        return canvas.figure_history.perform(
            "Rename Project",
            lambda: self.project_metadata.rename(project_id, new_name),
        )

    def load_project_figure_snapshot(
        self,
        figure: dict[str, Any],
        project_name: str,
        project_path: str | None = None,
    ):
        """Load project figure snapshot."""

        root_id = figure["root_component_id"]
        root = next(
            component
            for component in figure["components"]
            if component["id"] == root_id
        )
        properties = root["properties"]
        size_inches = properties.get("size_inches") or [6.4, 4.8]
        return self.add_figure(
            width=float(size_inches[0]),
            height=float(size_inches[1]),
            dpi=float(properties.get("dpi", 100)),
            style=properties.get("style") or "default",
            canva_name=project_name,
            create_table=False,
            project_path=project_path,
            component_tree=figure,
        )
