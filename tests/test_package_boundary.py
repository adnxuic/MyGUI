import ast
import importlib
import unittest
from pathlib import Path


class PackageBoundaryTests(unittest.TestCase):
    def test_stdlib_code_and_pdb_are_not_shadowed(self):
        stdlib_code = importlib.import_module("code")
        pdb = importlib.import_module("pdb")

        self.assertTrue(hasattr(stdlib_code, "InteractiveInterpreter"))
        self.assertIs(pdb.code, stdlib_code)
        self.assertNotIn(
            str(Path(__file__).resolve().parents[1] / "mygui"),
            str(Path(stdlib_code.__file__).resolve()),
        )

    def test_retired_widget_bootstrap_modules_are_absent(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "mygui/widgets/mainwindow_setting.py",
            "mygui/widgets/json_func.py",
            "mygui/widgets/qss_func.py",
            "mygui/widgets/mainwindow_init/setting.json",
            "mygui/widgets/title_bar/py_pull_down_menu.py",
        ):
            self.assertFalse(root.joinpath(relative).exists(), relative)

    def test_table_repository_is_created_only_in_composition_root(self):
        root = Path(__file__).resolve().parents[1]
        calls = []
        sources = [root / "main.py", *root.joinpath("mygui").rglob("*.py")]
        for source in sources:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "TableRepository"
                ):
                    calls.append(source.relative_to(root).as_posix())
        self.assertEqual(calls, ["main.py"])
