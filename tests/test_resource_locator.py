import ast
import os
import tempfile
import unittest
from pathlib import Path

from mygui.resources import (
    icon_path,
    load_json_resource,
    load_qss_resource,
    load_text_resource,
    resource_path,
)


class ResourceLocatorTests(unittest.TestCase):
    def test_resource_paths_are_absolute_and_reject_escape(self):
        icon = Path(icon_path("setting.svg"))
        self.assertTrue(icon.is_absolute())
        self.assertTrue(icon.is_file())
        with self.assertRaisesRegex(ValueError, "remain below"):
            resource_path("../outside.txt")

    def test_resources_resolve_outside_repository_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertTrue(Path(icon_path("chart_images/curve.svg")).is_file())
                self.assertIn(
                    "QFrame",
                    load_text_resource(
                        "mygui/widgets/figure_canvas/style.qss"
                    ),
                )
                self.assertNotIn(
                    "{{",
                    load_qss_resource(
                        "mygui/widgets/mainwindow_init/style.qss"
                    ),
                )
                self.assertIn(
                    "single",
                    load_json_resource(
                        "mygui/widgets/title_bar/available_layout.json"
                    ),
                )
            finally:
                os.chdir(original)

    def test_all_bundled_qss_and_json_resources_load(self):
        repository_root = Path(__file__).resolve().parents[1]
        for path in repository_root.joinpath("mygui").rglob("*.qss"):
            relative = path.relative_to(repository_root).as_posix()
            with self.subTest(resource=relative):
                self.assertIsInstance(load_qss_resource(relative), str)
        for path in repository_root.joinpath("mygui").rglob("*.json"):
            relative = path.relative_to(repository_root).as_posix()
            with self.subTest(resource=relative):
                self.assertIsNotNone(load_json_resource(relative))

    def test_main_window_uses_resources_and_one_color_library_outside_root(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from main import MainWindow
        from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
            PyCurveDialog,
        )

        application = QApplication.instance() or QApplication([])
        original = Path.cwd()
        window = None
        dialog = None
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                window = MainWindow()
                canvas = window.figure_window.add_figure(
                    width=6.4,
                    height=4.8,
                    dpi=100,
                    style="default",
                    canva_name="Resource Identity",
                )
                canvas.add_axes(1, 1)
                dialog = PyCurveDialog(
                    "Function Curve",
                    window.figure_window,
                )
                shared = window.color_library
                self.assertIs(window.figure_window.color_library, shared)
                self.assertIs(canvas.color_library, shared)
                self.assertIs(canvas.editor_context.color_library, shared)
                self.assertIs(
                    canvas.figure_inspector.root_inspector.context.color_library,
                    shared,
                )
                self.assertIs(dialog.color_input.color_library, shared)
            finally:
                os.chdir(original)
                if dialog is not None:
                    dialog.close()
                    dialog.deleteLater()
                if window is not None:
                    window.close()
                    window.deleteLater()
                application.processEvents()

    def test_production_python_has_no_root_relative_icon_literals(self):
        package_root = Path(__file__).resolve().parents[1] / "mygui"
        offenders = []
        for source_path in package_root.rglob("*.py"):
            if source_path.name == "resources.py":
                continue
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "pictures/icons/" in node.value
                ):
                    offenders.append(f"{source_path.name}:{node.lineno}")
        self.assertEqual(offenders, [])
