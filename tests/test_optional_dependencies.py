from contextlib import contextmanager
import os
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib as mpl
import numpy as np

from Qt_core import QApplication, Qt
from code.database import matlab_adapter
from code.database.py_database import PyDatabase
from code.widgets.fig_control_window import py_matlab_window as matlab_window_module
from code.widgets.fig_control_window.py_matlab_window import PyFitWindow, PyMatlabWindow
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

    def tearDown(self):
        PyDatabase.clear()
        self.close_matlab_log_handlers()

    def close_matlab_log_handlers(self):
        logger = matlab_adapter.logging.getLogger(matlab_adapter.LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def flush_matlab_log_handlers(self):
        logger = matlab_adapter.matlab_logger()
        for handler in logger.handlers:
            handler.flush()

    @contextmanager
    def temp_dir(self):
        temp_root = Path(__file__).resolve().parent / "_tmp"
        temp_root.mkdir(exist_ok=True)
        yield tempfile.mkdtemp(dir=temp_root)

    def wait_until(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous GUI update.")

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

    def test_matlab_import_failure_does_not_block_main_window_startup(self):
        from main import MainWindow

        with patch.object(
            matlab_adapter,
            "ensure_matlab_available",
            side_effect=RuntimeError("MATLAB runtime unavailable: missing matlab"),
        ) as ensure_available, patch.object(
            matlab_adapter,
            "ensure_matlab_available_isolated",
            side_effect=AssertionError("MATLAB connect should be lazy"),
        ) as ensure_available_isolated, patch.object(
            matlab_adapter,
            "get_func_exp",
            side_effect=AssertionError("MATLAB expression extraction should be lazy"),
        ) as get_func_exp, patch.object(
            matlab_adapter,
            "get_func_exp_isolated",
            side_effect=AssertionError("MATLAB expression extraction should be lazy"),
        ) as get_func_exp_isolated:
            window = MainWindow()
            try:
                self.assertIsNotNone(window.fig_control_window.matlab_window)
                ensure_available.assert_not_called()
                ensure_available_isolated.assert_not_called()
                get_func_exp.assert_not_called()
                get_func_exp_isolated.assert_not_called()
            finally:
                window.close()

    def test_matlab_sources_directory_does_not_satisfy_runtime_import(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "matlab_sources").is_dir())
        fake_matlab = SimpleNamespace(__path__=[str(root / "matlab_sources")])

        with patch.object(matlab_adapter.importlib, "import_module", return_value=fake_matlab):
            with self.assertRaisesRegex(RuntimeError, "MATLAB runtime unavailable"):
                matlab_adapter.ensure_matlab_available()

    def test_matlab_connect_smoke_check_imports_packages_without_initializing_by_default(self):
        matlab_module = SimpleNamespace(double=Mock())
        get_func_package = SimpleNamespace(initialize=Mock())
        curve_fitting_package = SimpleNamespace(initialize=Mock())

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.GET_FUNC_PACKAGE:
                return get_func_package
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return curve_fitting_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            self.assertTrue(matlab_adapter.check_matlab_connection().available)

        get_func_package.initialize.assert_not_called()
        curve_fitting_package.initialize.assert_not_called()

    def test_matlab_connect_smoke_check_can_initialize_and_release_packages(self):
        matlab_module = SimpleNamespace(double=Mock())
        get_func_handle = Mock()
        curve_fitting_handle = Mock()
        get_func_package = SimpleNamespace(initialize=Mock(return_value=get_func_handle))
        curve_fitting_package = SimpleNamespace(initialize=Mock(return_value=curve_fitting_handle))

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.GET_FUNC_PACKAGE:
                return get_func_package
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return curve_fitting_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            self.assertTrue(matlab_adapter.check_matlab_connection(initialize_packages=True).available)

        get_func_package.initialize.assert_called_once()
        curve_fitting_package.initialize.assert_called_once()
        get_func_handle.terminate.assert_called_once()
        curve_fitting_handle.terminate.assert_called_once()

    def test_matlab_connect_failure_warns_without_initializing_fit_ui(self):
        window = PyMatlabWindow()
        try:
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(matlab_window_module.QMessageBox, "warning") as warning, \
                        patch.object(
                            matlab_window_module.matlab_adapter,
                            "ensure_matlab_available_isolated",
                            side_effect=RuntimeError("MATLAB runtime unavailable: missing matlab"),
                        ):
                    window.matlab_connect_click()
                    self.wait_until(lambda: warning.called)

                self.assertEqual(window.layout.count(), 1)
                self.assertEqual(window.matlab_isconnect.text(), "Connect Matlab")
                self.assertIsNone(window.connect_widget)
                warning.assert_called_once()

            log_text = "\n".join(logs.output)
            self.assertIn("MATLAB connect request started request_id=1", log_text)
            self.assertIn("MATLAB connect request failed request_id=1", log_text)
        finally:
            window.close()

    def test_matlab_expression_extraction_failure_only_warns(self):
        fit_window = None
        with patch.object(
            matlab_window_module.matlab_adapter,
            "get_func_exp_isolated",
            side_effect=[
                ("a*x+b", ["a", "b"]),
                RuntimeError("MATLAB function extraction failed: extraction failed"),
            ],
        ):
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                fit_window = PyFitWindow()
                try:
                    self.wait_until(lambda: fit_window.expression_input.toPlainText() == "a*x+b")
                    with patch.object(matlab_window_module.QMessageBox, "warning") as warning:
                        fit_window.expression_change("poly2")
                        self.wait_until(lambda: warning.called)

                    self.assertEqual(fit_window.expression_input.toPlainText(), "a*x+b")
                    warning.assert_called_once()
                finally:
                    fit_window.close()

            log_text = "\n".join(logs.output)
            self.assertIn("MATLAB expression request started request_id=1", log_text)
            self.assertIn("MATLAB expression request succeeded request_id=1", log_text)
            self.assertIn("MATLAB expression request failed request_id=2", log_text)

    def test_matlab_fitting_failure_only_warns(self):
        database = PyDatabase()
        PyDatabase.register_sheet("Data", "Sheet1", database)
        database.update_data(1, np.array([1.0, 2.0, 3.0]))
        database.update_data(2, np.array([2.0, 4.0, 6.0]))

        window = PyMatlabWindow()
        try:
            window.data_choice_widget = Mock()
            window.data_choice_widget.get_x_data.return_value = "Data/Sheet1/1"
            window.data_choice_widget.get_y_data.return_value = "Data/Sheet1/2"
            window.fit_type_window = Mock()
            window.fit_type_window.fit_parameters.return_value = ("poly1", True, None, None, None)
            window.connect_widget = Mock()
            window.fit_button = Mock()

            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(
                    matlab_window_module.matlab_adapter,
                    "fit_curve_isolated",
                    side_effect=RuntimeError("MATLAB fitting failed: fit failed"),
                ), patch.object(matlab_window_module.QMessageBox, "warning") as warning:
                    window.fit_curve()
                    self.wait_until(lambda: warning.called)

            warning.assert_called_once()
            window.connect_widget.update_curve.assert_not_called()

            log_text = "\n".join(logs.output)
            self.assertIn("MATLAB fit request started request_id=1", log_text)
            self.assertIn("MATLAB fit request failed request_id=1", log_text)
        finally:
            window.close()

    def test_adapter_get_func_exp_releases_runtime_on_success_and_failure(self):
        success_handle = Mock()
        success_handle.get_func.return_value = ("a*x+b", ["a", "b"])
        success_package = SimpleNamespace(initialize=Mock(return_value=success_handle))
        with patch.object(matlab_adapter.importlib, "import_module", return_value=success_package):
            self.assertEqual(matlab_adapter.get_func_exp("poly1"), ("a*x+b", ["a", "b"]))
        success_handle.terminate.assert_called_once()

        failure_handle = Mock()
        failure_handle.get_func.side_effect = ValueError("bad expression")
        failure_package = SimpleNamespace(initialize=Mock(return_value=failure_handle))
        with patch.object(matlab_adapter.importlib, "import_module", return_value=failure_package):
            with self.assertRaisesRegex(RuntimeError, "MATLAB function extraction failed"):
                matlab_adapter.get_func_exp("poly2")
        failure_handle.terminate.assert_called_once()

    def test_adapter_get_func_exp_uses_fallback_when_runtime_initialization_fails(self):
        package = SimpleNamespace(initialize=Mock(side_effect=RuntimeError("mcr failed")))

        with patch.object(matlab_adapter.importlib, "import_module", return_value=package):
            self.assertEqual(matlab_adapter.get_func_exp("poly2"), ("p1*x^2 + p2*x + p3", ["p1", "p2", "p3"]))
            self.assertEqual(
                matlab_adapter.get_func_exp("rat12"),
                ("(p1*x + p2)/(x^2 + q1*x + q2)", ["p1", "p2", "q1", "q2"]),
            )

    def test_adapter_get_func_exp_does_not_hide_package_import_failure(self):
        with patch.object(matlab_adapter.importlib, "import_module", side_effect=ImportError("missing package")):
            with self.assertRaisesRegex(RuntimeError, "MATLAB package import failed"):
                matlab_adapter.get_func_exp("poly1")

    def test_adapter_isolated_connect_timeout_raises_runtime_error(self):
        with patch.object(
            matlab_adapter.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=1),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "MATLAB runtime unavailable: timed out after 1 seconds",
            ):
                matlab_adapter.ensure_matlab_available_isolated(timeout=1)

    def test_adapter_isolated_calls_use_private_mcr_cache(self):
        captured = {}

        def fake_run(*args, **kwargs):
            cache_root = kwargs["env"].get("MCR_CACHE_ROOT")
            captured["cache_root"] = cache_root
            self.assertEqual(kwargs["env"].get("TEMP"), cache_root)
            self.assertEqual(kwargs["env"].get("TMP"), cache_root)
            self.assertTrue(Path(cache_root).exists())
            result = {"ok": True, "result": {"available": True, "message": ""}}
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout=matlab_adapter._RESULT_PREFIX + json.dumps(result) + "\n",
                stderr="",
            )

        with patch.dict(matlab_adapter.os.environ, {}, clear=True):
            with patch.object(matlab_adapter.subprocess, "run", side_effect=fake_run):
                self.assertTrue(matlab_adapter.ensure_matlab_available_isolated(timeout=1).available)

        self.assertTrue(Path(captured["cache_root"]).is_relative_to(matlab_adapter._MCR_CACHE_PARENT))
        self.assertIn("runtime", Path(captured["cache_root"]).parts)

    def test_adapter_mcr_cache_key_changes_when_package_inputs_change(self):
        with self.temp_dir() as temp_dir:
            first = Path(temp_dir) / "first.ctf"
            second = Path(temp_dir) / "second.py"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            with patch.object(matlab_adapter, "_cache_input_paths", return_value=[first, second]):
                first_key = matlab_adapter._mcr_cache_key()
                self.assertEqual(first_key, matlab_adapter._mcr_cache_key())
                first.write_text("changed", encoding="utf-8")
                self.assertNotEqual(first_key, matlab_adapter._mcr_cache_key())

    def test_adapter_logging_writes_rotating_log_file(self):
        with self.temp_dir() as log_dir:
            with patch.dict(
                matlab_adapter.os.environ,
                {
                    "MYGUI_MATLAB_LOG_DIR": log_dir,
                    "MYGUI_MATLAB_LOG_LEVEL": "DEBUG",
                },
            ):
                logger = matlab_adapter.configure_matlab_logging()
                logger.info("adapter log smoke")
                for handler in logger.handlers:
                    handler.flush()

            log_path = Path(log_dir) / "matlab.log"
            self.assertIn("adapter log smoke", log_path.read_text(encoding="utf-8"))
            self.close_matlab_log_handlers()

    def test_adapter_isolated_suppresses_plain_child_stderr_at_info_level(self):
        def fake_run(*args, **kwargs):
            result = {"ok": True, "result": {"available": True, "message": ""}}
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout=matlab_adapter._RESULT_PREFIX + json.dumps(result) + "\n",
                stderr="child diagnostic line\n",
            )

        with self.temp_dir() as log_dir:
            with patch.dict(
                matlab_adapter.os.environ,
                {
                    "MYGUI_MATLAB_LOG_DIR": log_dir,
                    "MYGUI_MATLAB_LOG_LEVEL": "INFO",
                },
            ):
                with patch.object(matlab_adapter.subprocess, "run", side_effect=fake_run):
                    self.assertTrue(matlab_adapter.ensure_matlab_available_isolated(timeout=1).available)
                self.flush_matlab_log_handlers()

            log_text = (Path(log_dir) / "matlab.log").read_text(encoding="utf-8")
            self.assertNotIn("child diagnostic line", log_text)
            self.close_matlab_log_handlers()

    def test_adapter_isolated_logs_plain_child_stderr_at_debug_level(self):
        def fake_run(*args, **kwargs):
            result = {"ok": True, "result": {"available": True, "message": ""}}
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout=matlab_adapter._RESULT_PREFIX + json.dumps(result) + "\n",
                stderr="child diagnostic line\n",
            )

        with self.temp_dir() as log_dir:
            with patch.dict(
                matlab_adapter.os.environ,
                {
                    "MYGUI_MATLAB_LOG_DIR": log_dir,
                    "MYGUI_MATLAB_LOG_LEVEL": "DEBUG",
                },
            ):
                with patch.object(matlab_adapter.subprocess, "run", side_effect=fake_run):
                    self.assertTrue(matlab_adapter.ensure_matlab_available_isolated(timeout=1).available)
                self.flush_matlab_log_handlers()

            log_text = (Path(log_dir) / "matlab.log").read_text(encoding="utf-8")
            self.assertIn("child diagnostic line", log_text)
            self.close_matlab_log_handlers()

    def test_adapter_isolated_logs_warning_child_stderr_at_info_level(self):
        def fake_run(*args, **kwargs):
            result = {"ok": True, "result": {"available": True, "message": ""}}
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout=matlab_adapter._RESULT_PREFIX + json.dumps(result) + "\n",
                stderr="WARNING child diagnostic line\n",
            )

        with self.temp_dir() as log_dir:
            with patch.dict(
                matlab_adapter.os.environ,
                {
                    "MYGUI_MATLAB_LOG_DIR": log_dir,
                    "MYGUI_MATLAB_LOG_LEVEL": "INFO",
                },
            ):
                with patch.object(matlab_adapter.subprocess, "run", side_effect=fake_run):
                    self.assertTrue(matlab_adapter.ensure_matlab_available_isolated(timeout=1).available)
                self.flush_matlab_log_handlers()

            log_text = (Path(log_dir) / "matlab.log").read_text(encoding="utf-8")
            self.assertIn("WARNING child diagnostic line", log_text)
            self.close_matlab_log_handlers()

    def test_adapter_fit_curve_releases_runtime_on_success_and_failure(self):
        matlab_module = SimpleNamespace(
            double=Mock(side_effect=lambda values, size: ("double", list(values), size))
        )

        success_handle = Mock()
        success_handle.curve_fitting.return_value = ("a*x^2+b", ["a", "b"], [[2.0, 3.0]], object())
        success_package = SimpleNamespace(initialize=Mock(return_value=success_handle))

        def success_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return success_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=success_import):
            self.assertEqual(
                matlab_adapter.fit_curve([1.0], [2.0], "poly1", True),
                ("2.0*x**2+3.0", "2.0*x**2+3.0"),
            )
        success_handle.terminate.assert_called_once()

        failure_handle = Mock()
        failure_handle.curve_fitting.side_effect = ValueError("fit failed")
        failure_package = SimpleNamespace(initialize=Mock(return_value=failure_handle))

        def failure_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return failure_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=failure_import):
            with self.assertRaisesRegex(RuntimeError, "MATLAB fitting failed"):
                matlab_adapter.fit_curve([1.0], [2.0], "poly1", True)
        failure_handle.terminate.assert_called_once()

    def test_adapter_fit_curve_replaces_overlapping_coefficient_names_safely(self):
        matlab_module = SimpleNamespace(
            double=Mock(side_effect=lambda values, size: ("double", list(values), size))
        )
        handle = Mock()
        handle.curve_fitting.return_value = ("p10*x+p1", ["p1", "p10"], [[2.0, 10.0]], object())
        package = SimpleNamespace(initialize=Mock(return_value=handle))

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            self.assertEqual(
                matlab_adapter.fit_curve([1.0], [2.0], "poly9", True),
                ("10.0*x+2.0", "10.0*x+2.0"),
            )

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

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=ImportError("missing matlab")):
            with self.assertRaisesRegex(RuntimeError, "MATLAB runtime unavailable"):
                matlab_fitting_module.matlab_fitting([1.0], [2.0], "poly1", True)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=ImportError("missing matlab runtime")):
            with self.assertRaisesRegex(RuntimeError, "MATLAB package import failed"):
                get_func_exp_module.get_func_exp("poly1")


if __name__ == "__main__":
    unittest.main()
