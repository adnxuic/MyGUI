import os
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib as mpl

from Qt_core import QApplication, Qt
from code.widgets.fig_control_window import py_matlab_window as matlab_window_module
from code.widgets.fig_control_window.py_matlab_window import PyMatlabWindow
from code.widgets.fig_control_window.py_tex_window import PyTexWindow


def load_module_from_file(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class OptionalDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tex_missing_engine_warns_and_keeps_usetex_disabled(self):
        window = PyTexWindow()
        try:
            mpl.rcParams['text.usetex'] = True
            with patch.object(PyTexWindow, "_has_tex_engine", return_value=False), \
                    patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                window.use_latex_engine(Qt.CheckState.Checked)

            self.assertFalse(window.is_latex)
            self.assertFalse(window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
            warning.assert_called_once()
        finally:
            window.close()
            mpl.rcParams['text.usetex'] = False

    def test_matlab_connect_failure_warns_without_initializing_fit_ui(self):
        window = PyMatlabWindow()
        try:
            with patch.object(matlab_window_module.QMessageBox, "warning") as warning:
                with patch.object(
                    matlab_window_module.importlib,
                    "import_module",
                    side_effect=ImportError("missing matlab"),
                ):
                    window.matlab_connect_click()

            self.assertEqual(window.layout.count(), 1)
            self.assertEqual(window.matlab_isconnect.text(), "Connect Matlab")
            self.assertIsNone(window.connect_widget)
            warning.assert_called_once()
        finally:
            window.close()

    def test_matlab_helpers_raise_runtime_errors_instead_of_exiting(self):
        root = Path(__file__).resolve().parents[1]
        matlab_fitting_module = load_module_from_file(
            "matlab_fitting_under_test",
            root / "code" / "database" / "matlab_func" / "curve_fitting" / "matlab_fitting.py",
        )
        get_func_exp_module = load_module_from_file(
            "get_func_exp_under_test",
            root / "code" / "database" / "matlab_func" / "get_func" / "get_func_exp.py",
        )

        with patch(
            "matlab_fitting_under_test.importlib.import_module",
            side_effect=ImportError("missing matlab"),
        ):
            with self.assertRaises(RuntimeError):
                matlab_fitting_module.matlab_fitting([1.0], [2.0], "poly1", True)

        with patch(
            "get_func_exp_under_test.importlib.import_module",
            side_effect=ImportError("missing matlab runtime"),
        ):
            with self.assertRaises(RuntimeError):
                get_func_exp_module.get_func_exp("poly1")


if __name__ == "__main__":
    unittest.main()
