import ast
import os
import tempfile
import unittest
from pathlib import Path

from mygui.resources import icon_path, resource_path


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
            finally:
                os.chdir(original)

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
