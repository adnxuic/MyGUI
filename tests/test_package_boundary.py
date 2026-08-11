import importlib
import sys
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

    def test_importing_widget_theme_does_not_load_legacy_main_window(self):
        sys.modules.pop("mygui.widgets.mainwindow_setting", None)

        importlib.import_module("mygui.widgets.theme")

        self.assertNotIn("mygui.widgets.mainwindow_setting", sys.modules)

