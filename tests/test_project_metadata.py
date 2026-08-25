import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
from mygui.database import TableRepository
from mygui.widgets.figure_canvas.project_metadata import ProjectMetadataService


class ProjectMetadataServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.repository = TableRepository()
        self.doc = self.repository.create_project("ProjectAlpha")
        self.project_id = self.doc.id
        self.mock_figure_window = mock.MagicMock()
        self.mock_canvas = QWidget()
        self.mock_canvas.project_id = self.project_id
        self.mock_canvas.root_component_id = "root_fig_1"
        self.mock_controller = mock.MagicMock()
        self.mock_registry = mock.MagicMock()
        self.mock_registry.get.return_value = self.mock_controller
        self.mock_canvas.component_registry = self.mock_registry
        self.mock_figure_window.canvas = {self.project_id: self.mock_canvas}
        self.tabwindow = QTabWidget()
        self.tabwindow.addTab(self.mock_canvas, "ProjectAlpha")
        self.mock_figure_window.tabwindow = self.tabwindow
        self.service = ProjectMetadataService(self.mock_figure_window, self.repository)

    def tearDown(self):
        self.tabwindow.deleteLater()
        self.mock_canvas.deleteLater()
        self.app.processEvents()

    def test_rename_idempotent_when_name_unchanged(self):
        """rename returns early without performing mutations when new_name equals current name."""
        self.service.rename(self.project_id, "ProjectAlpha")
        self.mock_controller.set_property.assert_not_called()

    def test_rename_rejects_duplicate_project_name(self):
        """rename raises ValueError when target name is taken by another project."""
        self.repository.create_project("ProjectBeta")
        with self.assertRaisesRegex(ValueError, "Project already exists: ProjectBeta"):
            self.service.rename(self.project_id, "ProjectBeta")

    def test_rename_rejects_unknown_figure_project(self):
        """rename raises KeyError when project is in repository but canvas is missing."""
        orphan = self.repository.create_project("OrphanProject")
        with self.assertRaisesRegex(KeyError, "Unknown Figure project"):
            self.service.rename(orphan.id, "NewName")

    def test_rename_raises_when_controller_mutation_fails(self):
        """rename raises ValueError with message when controller rejects name change."""
        self.mock_controller.set_property.return_value = SimpleNamespace(
            ok=False, message="Controller rejected name"
        )
        with self.assertRaisesRegex(ValueError, "Controller rejected name"):
            self.service.rename(self.project_id, "ProjectRenamed")

        self.mock_controller.set_property.return_value = SimpleNamespace(
            ok=False, message=None
        )
        with self.assertRaisesRegex(ValueError, "Could not rename project."):
            self.service.rename(self.project_id, "ProjectRenamed")

    def test_rename_success_calls_controller(self):
        """rename invokes set_property('name', new_name) on root controller."""
        self.mock_controller.set_property.return_value = SimpleNamespace(ok=True, message=None)
        self.service.rename(self.project_id, "ProjectGamma")
        self.mock_controller.set_property.assert_called_once_with("name", "ProjectGamma")

    def test_apply_controller_name_rejects_duplicate_and_unknown_project(self):
        """apply_controller_name checks duplicate project name and canvas existence."""
        self.repository.create_project("ProjectBeta")
        with self.assertRaisesRegex(ValueError, "Project already exists: ProjectBeta"):
            self.service.apply_controller_name(self.project_id, "ProjectBeta")

        orphan = self.repository.create_project("OrphanProject")
        with self.assertRaisesRegex(KeyError, "Unknown Figure project"):
            self.service.apply_controller_name(orphan.id, "NewOrphanName")

    def test_apply_controller_name_rejects_missing_tab(self):
        """apply_controller_name raises RuntimeError when canvas is not in tabwindow."""
        self.tabwindow.clear()
        with self.assertRaisesRegex(RuntimeError, "Project Tab is unavailable."):
            self.service.apply_controller_name(self.project_id, "ProjectGamma")

    def test_apply_controller_name_success_updates_project_and_tab(self):
        """apply_controller_name updates repository project name and Qt Tab title."""
        self.service.apply_controller_name(self.project_id, "ProjectGamma")
        self.assertEqual(self.doc.name, "ProjectGamma")
        self.assertEqual(self.tabwindow.tabText(0), "ProjectGamma")

    def test_apply_controller_name_rolls_back_tab_text_on_mutate_exception(self):
        """apply_controller_name restores previous tab title if repository mutation raises."""
        self.assertEqual(self.tabwindow.tabText(0), "ProjectAlpha")
        with mock.patch.object(self.repository, "mutate", side_effect=RuntimeError("Mutate boom")):
            with self.assertRaisesRegex(RuntimeError, "Mutate boom"):
                self.service.apply_controller_name(self.project_id, "ProjectGamma")
        self.assertEqual(self.tabwindow.tabText(0), "ProjectAlpha")

    def test_apply_controller_name_handles_double_fault_in_tab_text_rollback(self):
        """apply_controller_name suppresses exception in rollback if setTabText also raises."""
        with mock.patch.object(self.repository, "mutate", side_effect=RuntimeError("Mutate boom")):
            with mock.patch.object(self.tabwindow, "setTabText", side_effect=RuntimeError("Tab boom")):
                with self.assertRaisesRegex(RuntimeError, "Mutate boom"):
                    self.service.apply_controller_name(self.project_id, "ProjectGamma")


if __name__ == "__main__":
    unittest.main()
