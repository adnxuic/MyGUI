"""Coordinate project metadata across Repository, Figure, and Qt projections."""

from __future__ import annotations

from typing import Protocol

from mygui.database import (
    TableChangeSet,
    TableRepository,
    validate_component_name,
)


class ProjectMetadataPort(Protocol):
    """Minimal Canvas-facing project metadata transaction contract."""

    def apply_controller_name(self, project_id: str, new_name: str) -> None:
        """Apply one Controller-originated project name atomically."""


class ProjectMetadataService:
    """Keep repository names authoritative while projections stay atomic."""

    def __init__(self, figure_window, repository: TableRepository) -> None:
        self.figure_window = figure_window
        self.repository = repository

    def rename(self, project_id: str, new_name: str) -> None:
        """Rename one project by stable ID through its Figure Controller."""

        project_id = str(project_id)
        new_name = validate_component_name(new_name, "Project name")
        project = self.repository.project(project_id)
        if project.name == new_name:
            return
        existing = self.repository.project_by_name(new_name, required=False)
        if existing is not None and existing.id != project_id:
            raise ValueError(f"Project already exists: {new_name}")
        canvas = self.figure_window.canvas.get(project_id)
        if canvas is None:
            raise KeyError(f"Unknown Figure project: {project_id}")
        controller = canvas.component_registry.get(canvas.root_component_id)
        # The Controller callback performs the repository/Tab projection
        # inside this outer transaction. Publication occurs only after the
        # Controller mutation and redraw-sensitive updates both succeed.
        with self.repository.transaction(project_id, rollback=True):
            change = controller.set_property("name", new_name)
            if not change.ok:
                raise ValueError(change.message or "Could not rename project.")

    def apply_controller_name(self, project_id: str, new_name: str) -> None:
        """Project an in-flight Figure Controller name into repository and Tab."""

        project_id = str(project_id)
        new_name = validate_component_name(new_name, "Project name")
        project = self.repository.project(project_id)
        existing = self.repository.project_by_name(new_name, required=False)
        if existing is not None and existing.id != project_id:
            raise ValueError(f"Project already exists: {new_name}")
        canvas = self.figure_window.canvas.get(project_id)
        if canvas is None:
            raise KeyError(f"Unknown Figure project: {project_id}")
        index = self.figure_window.tabwindow.indexOf(canvas)
        if index < 0:
            raise RuntimeError("Project Tab is unavailable.")
        previous_tab_name = self.figure_window.tabwindow.tabText(index)
        changes = TableChangeSet(
            project_id,
            metadata_changed=True,
            reason="rename-project",
        )
        try:
            with self.repository.mutate(changes):
                project.name = new_name
                self.figure_window.tabwindow.setTabText(index, new_name)
        except Exception:
            try:
                self.figure_window.tabwindow.setTabText(
                    index,
                    previous_tab_name,
                )
            except Exception:
                pass
            raise
