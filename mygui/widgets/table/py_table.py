"""Manage project tables and their sheet tabs."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout

from mygui.database import TableChangeSet, TableRepository, validate_component_name
from mygui.widgets import qss_func
from mygui.widgets.table.py_subtable import PySubTable


current_path = os.path.dirname(os.path.abspath(__file__))
qss_path = os.path.join(current_path, "style.qss")


class PyTable(QFrame):
    """Provide the py table Qt widget."""

    def __init__(self, repository: TableRepository):
        super().__init__()
        self.repository = repository
        self._figure_window = None
        self._subtables: dict[str, PySubTable] = {}
        self._current_project_id: str | None = None

        self.setObjectName("table")
        self.setStyleSheet(qss_func.qss_loader(qss_path))
        self.setMinimumWidth(240)

        self.stack = QStackedWidget(self)
        self.empty_label = QLabel("Create or open a project to edit table data.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setMargin(16)
        self.empty_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.empty_label.setObjectName("empty_table_placeholder")
        self.stack.addWidget(self.empty_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    @property
    def current_project_id(self) -> str | None:
        """Return the current project id."""

        return self._current_project_id

    @property
    def current_table_name(self) -> str | None:
        """Return the current table name."""

        if self._current_project_id is None:
            return None
        return self.repository.project(self._current_project_id).name

    def set_figure_window(self, figure_window):
        """Set figure window."""

        self._figure_window = figure_window

    def _dependency_handler(self, refs, reason):
        if self._figure_window is None or not hasattr(self._figure_window, "prepare_dependency_cascade"):
            return None
        return self._figure_window.prepare_dependency_cascade(refs, reason)

    def has_table(self, table_name: str) -> bool:
        """Return whether this object has table."""

        return self.repository.project_by_name(table_name, required=False) is not None

    def table_names(self) -> list[str]:
        """Return the available table names."""

        return [project.name for project in self.repository.projects.values()]

    def current_subtable(self) -> PySubTable | None:
        """Return the current subtable."""

        if self._current_project_id is None:
            return None
        return self._subtables.get(self._current_project_id)

    def create_project_table(self, table_name: str, first_sheet_name: str = "Sheet1",
                             switch: bool = True, *,
                             publish: bool = True) -> PySubTable:
        """Create project table."""

        table_name = validate_component_name(table_name, "Project name")
        first_sheet_name = validate_component_name(first_sheet_name, "Sheet name")
        previous_project_id = self._current_project_id
        project = self.repository.create_project(
            table_name,
            first_sheet_name,
            publish=False,
        )
        try:
            subtable = self._add_project_widget(project.id)
            if switch:
                self.switch_to_table(project.id)
        except Exception:
            self._remove_project_widget(project.id)
            self.repository.remove_project(project.id, publish=False)
            self.switch_to_table(
                previous_project_id
                if previous_project_id in self._subtables
                else None
            )
            raise
        if publish:
            self.repository.publish_project_added(project.id)
        return subtable

    def _add_project_widget(self, project_id: str) -> PySubTable:
        subtable = None
        try:
            subtable = PySubTable(
                self.repository,
                project_id,
                self._dependency_handler,
            )
            index = self.stack.addWidget(subtable)
            if index < 0:
                raise RuntimeError("Could not add the project table widget.")
            self._subtables[project_id] = subtable
            return subtable
        except Exception:
            if subtable is not None:
                self.stack.removeWidget(subtable)
                subtable.dispose()
                subtable.setParent(None)
                subtable.deleteLater()
            raise

    def _remove_project_widget(self, project_id: str) -> None:
        subtable = self._subtables.pop(project_id, None)
        if subtable is None:
            return
        self.stack.removeWidget(subtable)
        subtable.dispose()
        subtable.setParent(None)
        subtable.deleteLater()

    def switch_to_table(self, table: str | None):
        """Select the requested project table."""

        if table is None:
            self._current_project_id = None
            self.stack.setCurrentWidget(self.empty_label)
            return
        if table in self._subtables:
            project_id = table
        else:
            project = self.repository.project_by_name(table, required=False)
            if project is None:
                raise KeyError(f"Unknown project table: {table}")
            project_id = project.id
        self._current_project_id = project_id
        self.stack.setCurrentWidget(self._subtables[project_id])

    def rename_project_table(self, old_name: str, new_name: str):
        """Rename project table."""

        new_name = validate_component_name(new_name, "Project name")
        project = self.repository.project_by_name(old_name)
        existing = self.repository.project_by_name(new_name, required=False)
        if existing is not None and existing.id != project.id:
            raise ValueError(f"Project already exists: {new_name}")
        project.name = new_name
        self.repository.record_change(TableChangeSet(
            project.id, metadata_changed=True, reason="rename-project"
        ))

    def remove_project_table(self, table: str, *, publish: bool = True):
        """Remove project table."""

        project = self.repository.projects.get(table) or self.repository.project_by_name(table, required=False)
        if project is None:
            return
        project_id = project.id
        self._remove_project_widget(project_id)
        self.repository.remove_project(project_id, publish=publish)
        if self._current_project_id == project_id:
            self.switch_to_table(next(iter(self._subtables), None))

    def clear_tables(self):
        """Clear tables."""

        for subtable in self._subtables.values():
            self.stack.removeWidget(subtable)
            subtable.dispose()
            subtable.deleteLater()
        self._subtables.clear()
        self.repository.clear()
        self.switch_to_table(None)

    def load_project_table_snapshot(
        self,
        table_snapshot: dict,
        *,
        publish: bool = True,
    ) -> PySubTable:
        """Load project table snapshot."""

        previous_project_id = self._current_project_id
        project = self.repository.restore_snapshot(
            table_snapshot,
            publish=False,
        )
        try:
            subtable = self._add_project_widget(project.id)
            self.switch_to_table(project.id)
        except Exception:
            self._remove_project_widget(project.id)
            self.repository.remove_project(project.id, publish=False)
            self.switch_to_table(
                previous_project_id
                if previous_project_id in self._subtables
                else None
            )
            raise
        if publish:
            self.repository.publish_project_added(project.id)
        return subtable
