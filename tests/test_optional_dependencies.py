from contextlib import contextmanager
import os
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from Qt_core import QApplication, QDialog, QPushButton, Qt
from code import tex_config
from code import status_messages
from code.database import ColumnRef, TableRepository, matlab_adapter, scipy_fit_adapter
from code.database.safe_expression import evaluate_curve_expression
from code.figuremodify.py_text_modify import PyTextModify, TextRenderError
from code.widgets.fig_control_window import py_matlab_window as matlab_window_module
from code.widgets.fig_control_window import py_fit_options_window as fit_options_module
from code.widgets.fig_control_window.all_mod_widgets.py_chart_mod_widgets import PyFitModWidget
from code.widgets.fig_control_window.all_mod_widgets.py_elements_mod_widgets import PyTextModWidget
from code.widgets.fig_control_window.py_fit_options_window import PyMatlabFitOptionsWidget
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

    def tearDown(self):
        tex_config.set_tex_enabled(False, notify=False)
        tex_config.clear_tex_state_listeners()
        mpl.rcParams['text.latex.preamble'] = mpl.rcParamsDefault['text.latex.preamble']
        status_messages.clear_status_handler()
        self.close_matlab_log_handlers()
        self.close_tex_log_handlers()

    def make_table_repository(self, with_data=False):
        repository = TableRepository()
        project = repository.create_project("Data")
        sheet = next(iter(project.sheets.values()))
        if with_data:
            sheet.set_block(0, 0, [[1, 2], [2, 4], [3, 6]])
        x_ref = ColumnRef(project.id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(project.id, sheet.id, sheet.columns[1].id)
        return repository, project, x_ref, y_ref

    def close_matlab_log_handlers(self):
        logger = matlab_adapter.logging.getLogger(matlab_adapter.LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def close_tex_log_handlers(self):
        logger = tex_config.logging.getLogger(tex_config.LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def flush_matlab_log_handlers(self):
        logger = matlab_adapter.matlab_logger()
        for handler in logger.handlers:
            handler.flush()

    def flush_tex_log_handlers(self):
        logger = tex_config.tex_logger()
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

    def test_tex_missing_engine_reports_status_and_keeps_usetex_disabled(self):
        window = PyTexWindow()
        status_events = []
        try:
            mpl.rcParams['text.usetex'] = True
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            with patch.object(PyTexWindow, "_has_tex_engine", return_value=False), \
                    patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                window.use_latex_engine(Qt.CheckState.Checked)

            self.assertFalse(window.is_latex)
            self.assertFalse(window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
            warning.assert_not_called()
            self.assertEqual(status_events[-1], ("No TeX executable was found on PATH.", "error"))
        finally:
            window.close()
            mpl.rcParams['text.usetex'] = False

    def test_tex_preamble_normalize_preserves_lines_and_skips_blanks(self):
        self.assertEqual(
            tex_config.normalize_preamble(
                "  \\usepackage{amsmath}\n\n\\usepackage{xcolor}  \r\n   "
            ),
            "\\usepackage{amsmath}\n\\usepackage{xcolor}",
        )

    def test_tex_render_probe_failure_warns_and_keeps_usetex_disabled(self):
        window = PyTexWindow()
        status_events = []
        try:
            mpl.rcParams['text.usetex'] = False
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            with patch.object(tex_config, "_LOG_TO_FILE", False), \
                    patch.object(tex_config, "_LOG_TO_STDERR", False), \
                    self.assertLogs(tex_config.LOGGER_NAME, level="INFO") as logs:
                with patch.object(PyTexWindow, "_has_tex_engine", return_value=True), \
                        patch(
                            "code.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value="render probe failed",
                        ) as validate_tex_runtime, \
                        patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                    window.latex_engine.setChecked(True)

            validate_tex_runtime.assert_called_once_with(tex_config.default_preamble_text())
            self.assertFalse(window.is_latex)
            self.assertFalse(window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
            warning.assert_not_called()
            self.assertEqual(status_events[-1], ("render probe failed", "error"))
            log_text = "\n".join(logs.output)
            self.assertIn("TeX enable request started", log_text)
            self.assertIn("TeX enable request failed", log_text)
        finally:
            window.close()

    def test_tex_enable_success_commits_usetex_and_normalized_preamble(self):
        window = PyTexWindow()
        status_events = []
        try:
            window.preamble_input.setPlainText("\\usepackage{amsmath}\n\n\\usepackage{xcolor}")
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            with patch.object(tex_config, "_LOG_TO_FILE", False), \
                    patch.object(tex_config, "_LOG_TO_STDERR", False), \
                    self.assertLogs(tex_config.LOGGER_NAME, level="INFO") as logs:
                with patch.object(PyTexWindow, "_has_tex_engine", return_value=True), \
                        patch(
                            "code.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value=None,
                        ) as validate_tex_runtime, \
                        patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                    window.latex_engine.setChecked(True)

            expected_preamble = "\\usepackage{amsmath}\n\\usepackage{xcolor}"
            validate_tex_runtime.assert_called_once_with(expected_preamble)
            self.assertTrue(window.is_latex)
            self.assertTrue(window.latex_engine.isChecked())
            self.assertTrue(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], expected_preamble)
            self.assertEqual(window.preamble_text, expected_preamble)
            warning.assert_not_called()
            self.assertEqual(
                status_events[-1],
                ("TeX runtime check passed; TeX rendering is enabled.", "success"),
            )
            log_text = "\n".join(logs.output)
            self.assertIn("TeX enable request started", log_text)
            self.assertIn("TeX enable request succeeded", log_text)
        finally:
            window.close()

    def test_tex_preamble_update_failure_preserves_old_rcparams(self):
        window = PyTexWindow()
        status_events = []
        try:
            old_preamble = "\\usepackage{old}"
            tex_config.set_tex_enabled(True, notify=False)
            mpl.rcParams['text.latex.preamble'] = old_preamble
            window.is_latex = True
            window.preamble_text = old_preamble
            window.preamble_input.setPlainText("\\usepackage{broken}")
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )

            with patch.object(tex_config, "_LOG_TO_FILE", False), \
                    patch.object(tex_config, "_LOG_TO_STDERR", False), \
                    self.assertLogs(tex_config.LOGGER_NAME, level="INFO") as logs:
                with patch.object(PyTexWindow, "_has_tex_engine", return_value=True), \
                        patch(
                            "code.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value="bad preamble",
                        ) as validate_tex_runtime, \
                        patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                    window.update_preamble()

            validate_tex_runtime.assert_called_once_with("\\usepackage{broken}")
            self.assertTrue(window.is_latex)
            self.assertTrue(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], old_preamble)
            self.assertEqual(window.preamble_text, old_preamble)
            warning.assert_not_called()
            self.assertEqual(status_events[-1], ("bad preamble", "error"))
            log_text = "\n".join(logs.output)
            self.assertIn("TeX preamble update request started", log_text)
            self.assertIn("TeX preamble update request failed", log_text)
        finally:
            window.close()

    def test_tex_preamble_update_while_disabled_skips_runtime_probe(self):
        window = PyTexWindow()
        try:
            window.is_latex = False
            window.preamble_input.setPlainText("\\usepackage{amsmath}\n\n\\usepackage{xcolor}")

            with patch(
                "code.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
            ) as validate_tex_runtime:
                window.update_preamble()

            expected_preamble = "\\usepackage{amsmath}\n\\usepackage{xcolor}"
            validate_tex_runtime.assert_not_called()
            self.assertFalse(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], expected_preamble)
            self.assertEqual(window.preamble_text, expected_preamble)
        finally:
            window.close()

    def test_tex_logging_writes_rotating_log_file(self):
        with self.temp_dir() as log_dir:
            with patch.dict(
                tex_config.os.environ,
                {
                    "MYGUI_TEX_LOG_DIR": log_dir,
                    "MYGUI_TEX_LOG_LEVEL": "DEBUG",
                },
            ):
                logger = tex_config.configure_tex_logging()
                logger.info("tex log smoke")
                for handler in logger.handlers:
                    handler.flush()

            log_path = Path(log_dir) / "tex.log"
            self.assertIn("tex log smoke", log_path.read_text(encoding="utf-8"))
            self.close_tex_log_handlers()

    def test_tex_panel_failure_path_does_not_block_main_window_startup(self):
        from main import MainWindow

        window = MainWindow()
        status_events = []
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            tex_window = window.fig_control_window.tex_window
            with patch.object(PyTexWindow, "_has_tex_engine", return_value=True), \
                    patch(
                        "code.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                        return_value="render probe failed",
                    ), patch("code.widgets.fig_control_window.py_tex_window.QMessageBox.warning") as warning:
                tex_window.latex_engine.setChecked(True)

            self.assertIsNotNone(window.fig_control_window.tex_window)
            self.assertFalse(tex_window.is_latex)
            self.assertFalse(tex_window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
            warning.assert_not_called()
            self.assertEqual(status_events[-1], ("render probe failed", "error"))
        finally:
            window.close()

    def test_tex_text_render_failure_restores_previous_text_and_project_record(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        project_record = {"text": "safe"}
        modifier = PyTextModify(figure, text=text, project_record=project_record)

        with patch.object(tex_config, "_LOG_TO_FILE", False), \
                patch.object(tex_config, "_LOG_TO_STDERR", False), \
                self.assertLogs(tex_config.LOGGER_NAME, level="WARNING") as logs:
            with patch.object(
                modifier,
                "redraw",
                side_effect=[RuntimeError("latex failed"), None],
            ):
                with self.assertRaisesRegex(TextRenderError, "keeping last valid text"):
                    modifier.set_text_content("$\\int$" + chr(0xFFE5))

        self.assertEqual(text.get_text(), "safe")
        self.assertEqual(project_record["text"], "safe")
        self.assertIn("TeX text render failed", "\n".join(logs.output))

    def test_text_redraw_reports_missing_glyph_warning_to_status_bar(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        modifier = PyTextModify(figure, text=text)
        status_events = []

        def draw_warning():
            warnings.warn(
                "Glyph 65509 (\\N{FULLWIDTH YEN SIGN}) missing from font(s) Times New Roman.",
                UserWarning,
            )

        status_messages.set_status_handler(
            lambda message, level: status_events.append((message, level))
        )

        with patch.object(tex_config, "_LOG_TO_FILE", False), \
                patch.object(tex_config, "_LOG_TO_STDERR", False), \
                self.assertLogs(tex_config.LOGGER_NAME, level="WARNING") as logs:
            with patch.object(figure.canvas, "draw", side_effect=draw_warning):
                modifier.redraw()

        self.assertEqual(status_events[-1][1], "error")
        self.assertIn("U+FFE5", status_events[-1][0])
        self.assertIn("Matplotlib text glyph warning", "\n".join(logs.output))

    def test_text_widget_reports_status_and_keeps_editor_when_tex_render_fails(self):
        class FakeText:
            def __init__(self):
                self.value = "safe"

            def get_fontfamily(self):
                return ["DejaVu Sans"]

            def get_fontsize(self):
                return 12

            def get_text(self):
                return self.value

            def get_position(self):
                return (0.5, 0.5)

        class FakeTextModify:
            def __init__(self):
                self.text = FakeText()

            def set_text_font(self, _font):
                pass

            def set_text_fontsize(self, _size):
                pass

            def set_text_content(self, _content):
                raise TextRenderError("Text render failed; keeping last valid text.")

            def get_text_usetex(self):
                return False

            def set_text_usetex(self, _use_tex):
                pass

            def set_xy_position(self, _x, _y):
                pass

        widget = PyTextModWidget(FakeTextModify())
        status_events = []
        bad_text = "$\\int$" + chr(0xFFE5)
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            widget.text_content.blockSignals(True)
            widget.text_content.setPlainText(bad_text)
            widget.text_content.blockSignals(False)

            with patch(
                "code.widgets.fig_control_window.all_mod_widgets.py_elements_mod_widgets.QMessageBox.warning"
            ) as warning:
                widget.set_text_content()

            warning.assert_not_called()
            self.assertEqual(widget.text_content.toPlainText(), bad_text)
            self.assertEqual(status_events[-1], ("Text render failed; keeping last valid text.", "error"))
        finally:
            widget.close()

    def test_text_widget_keeps_glyph_status_when_successful_render_warns(self):
        class FakeText:
            def __init__(self):
                self.value = "safe"

            def get_fontfamily(self):
                return ["DejaVu Sans"]

            def get_fontsize(self):
                return 12

            def get_text(self):
                return self.value

            def get_position(self):
                return (0.5, 0.5)

        class FakeTextModify:
            def __init__(self):
                self.text = FakeText()
                self.last_render_warning = None

            def set_text_font(self, _font):
                pass

            def set_text_fontsize(self, _size):
                pass

            def set_text_content(self, content):
                self.text.value = content
                self.last_render_warning = "Current font is missing glyph U+FFE5."
                status_messages.show_error(self.last_render_warning)

            def get_text_usetex(self):
                return False

            def set_text_usetex(self, _use_tex):
                pass

            def set_xy_position(self, _x, _y):
                pass

        widget = PyTextModWidget(FakeTextModify())
        status_events = []
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            widget.text_content.blockSignals(True)
            widget.text_content.setPlainText("plain")
            widget.text_content.blockSignals(False)

            widget.set_text_content()

            self.assertEqual(status_events[-1], ("Current font is missing glyph U+FFE5.", "error"))
        finally:
            widget.close()

    def test_text_widget_tex_button_disabled_when_global_tex_is_off(self):
        tex_config.set_tex_enabled(False, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        modifier = PyTextModify(figure, text=text, project_record={"text": "plain", "usetex": False})

        widget = PyTextModWidget(modifier)
        try:
            self.assertFalse(widget.tex_render.isEnabled())
            self.assertFalse(widget.tex_render.isChecked())
            self.assertFalse(text.get_usetex())
        finally:
            widget.close()

    def test_text_widget_tex_button_toggles_individual_text_rendering(self):
        tex_config.set_tex_enabled(False, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        tex_config.set_tex_enabled(True, notify=False)
        project_record = {"text": "plain", "usetex": False}
        modifier = PyTextModify(figure, text=text, project_record=project_record)
        status_events = []

        widget = PyTextModWidget(modifier)
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            self.assertTrue(widget.tex_render.isEnabled())
            self.assertFalse(widget.tex_render.isChecked())

            with patch.object(modifier, "redraw"):
                widget.tex_render.setChecked(True)

            self.assertTrue(text.get_usetex())
            self.assertTrue(project_record["usetex"])
            self.assertEqual(status_events[-1], ("Text TeX rendering enabled.", "success"))

            with patch.object(modifier, "redraw"):
                widget.tex_render.setChecked(False)

            self.assertFalse(text.get_usetex())
            self.assertFalse(project_record["usetex"])
        finally:
            widget.close()

    def test_global_tex_disable_unchecks_and_disables_text_tex_button(self):
        tex_config.set_tex_enabled(True, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        text.set_usetex(True)
        project_record = {"text": "plain", "usetex": True}
        modifier = PyTextModify(figure, text=text, project_record=project_record)

        widget = PyTextModWidget(modifier)
        try:
            self.assertTrue(widget.tex_render.isEnabled())
            self.assertTrue(widget.tex_render.isChecked())

            with patch.object(modifier, "redraw"):
                tex_config.set_tex_enabled(False)

            self.assertFalse(widget.tex_render.isEnabled())
            self.assertFalse(widget.tex_render.isChecked())
            self.assertFalse(text.get_usetex())
            self.assertFalse(project_record["usetex"])
        finally:
            widget.close()

    def test_new_text_defaults_to_tex_when_global_tex_is_enabled(self):
        from main import MainWindow

        window = MainWindow()
        try:
            window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="tex")
            canvas = window.figure_window.current_canva
            canvas.add_axes(nrows=1, ncols=1)
            tex_config.set_tex_enabled(True, notify=False)

            with patch.object(PyTextModify, "redraw"), patch.object(canvas, "redraw"):
                canvas.add_text(
                    x=0.2,
                    y=0.8,
                    text="plain",
                    fontfamily="DejaVu Sans",
                    fontsize=12,
                )

            text_artist = canvas.current_axes.texts[-1]
            all_mod_widget = canvas.fig_modify_widget.fine_all_mod_widget(canvas.current_axes)
            text_widget = all_mod_widget.element_mod_window.boxs["text_box"].widget(0)

            self.assertTrue(text_artist.get_usetex())
            self.assertTrue(canvas.project_texts[-1]["usetex"])
            self.assertTrue(text_widget.tex_render.isEnabled())
            self.assertTrue(text_widget.tex_render.isChecked())
        finally:
            window.close()

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

    def test_scipy_fitting_does_not_call_matlab_adapter(self):
        x = np.linspace(-2.0, 2.0, 9)
        y = 2.0 * x ** 2 + 1.0

        with patch.object(
            matlab_window_module.matlab_adapter,
            "fit_curve_isolated",
            side_effect=AssertionError("SciPy fitting should not call MATLAB"),
        ):
            result = scipy_fit_adapter.fit_curve(x, y, "poly2")

        self.assertEqual(result["engine"], "Python")
        self.assertEqual(result["fit_type"], "poly2")
        np.testing.assert_allclose(evaluate_curve_expression(result["value_expression"], x), y)

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

                self.assertEqual(window.layout.count(), 2)
                self.assertEqual(window.matlab_isconnect.text(), "Connect Matlab")
                self.assertFalse(hasattr(window, "data_choice_widget"))
                self.assertFalse(hasattr(window, "fit_type_window"))
                warning.assert_called_once()

            log_text = "\n".join(logs.output)
            self.assertIn("MATLAB connect request started request_id=1", log_text)
            self.assertIn("MATLAB connect request failed request_id=1", log_text)
        finally:
            window.close()

    def test_matlab_stale_connect_callbacks_do_not_update_ui(self):
        window = PyMatlabWindow()
        try:
            window._connect_request_id = 2
            window._show_connected_description = Mock()
            window.reset_to_connect_button = Mock()

            with patch.object(matlab_window_module.QMessageBox, "warning") as warning:
                window._matlab_connect_succeeded(1, time.monotonic(), matlab_adapter.MatlabStatus(True))
                window._matlab_connect_failed(1, time.monotonic(), "MATLAB runtime unavailable")

            window._show_connected_description.assert_not_called()
            window.reset_to_connect_button.assert_not_called()
            warning.assert_not_called()
        finally:
            window.close()

    def test_matlab_expression_extraction_failure_only_warns(self):
        fit_window = None
        with patch.object(
            fit_options_module.matlab_adapter,
            "get_func_info_isolated",
            side_effect=[
                {
                    "expression": "a*x+b",
                    "coefficients": ["a", "b"],
                    "options": matlab_adapter.default_fit_options("poly1", ["a", "b"]),
                },
                RuntimeError("MATLAB function metadata extraction failed: extraction failed"),
            ],
        ):
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                fit_window = PyMatlabFitOptionsWidget()
                try:
                    self.wait_until(lambda: fit_window.expression_input.toPlainText() == "a*x+b")
                    with patch.object(fit_options_module.QMessageBox, "warning") as warning:
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

    def test_matlab_fit_window_shows_method_specific_advanced_options(self):
        with patch.object(fit_options_module, "start_matlab_task", return_value=(None, None)):
            poly_window = PyMatlabFitOptionsWidget(fit_type_name="poly")
            gauss_window = PyMatlabFitOptionsWidget(fit_type_name="gauss")
            try:
                self.assertEqual(poly_window.option_metadata["Method"], "LinearLeastSquares")
                self.assertEqual(poly_window.coefficient_table.columnCount(), 3)
                self.assertNotIn("Algorithm", poly_window.option_widgets)

                self.assertEqual(gauss_window.option_metadata["Method"], "NonlinearLeastSquares")
                self.assertEqual(gauss_window.coefficient_table.columnCount(), 4)
                self.assertIn("Algorithm", gauss_window.option_widgets)
                self.assertEqual(gauss_window.coefficient_table.item(2, 2).text(), "0")
            finally:
                poly_window.close()
                gauss_window.close()

    def test_matlab_fit_window_parses_advanced_options_and_validates_startpoints(self):
        with patch.object(fit_options_module, "start_matlab_task", return_value=(None, None)):
            fit_window = PyMatlabFitOptionsWidget(fit_type_name="gauss")
            try:
                fit_window.advanced_option.setChecked(True)
                for row, value in enumerate(("0.1", "0.2", "0.3")):
                    fit_window.coefficient_table.item(row, 1).setText(value)
                fit_window.coefficient_table.item(0, 2).setText("-inf")
                fit_window.coefficient_table.item(1, 2).setText("-1e3")
                fit_window.coefficient_table.item(2, 2).setText("0")
                fit_window.coefficient_table.item(0, 3).setText("inf")
                fit_window.coefficient_table.item(1, 3).setText("1e3")
                fit_window.coefficient_table.item(2, 3).setText("inf")
                fit_window.option_widgets["TolFun"].setText("1e-7")

                fit_type, options = fit_window.fit_parameters()

                self.assertEqual(fit_type, "gauss1")
                self.assertEqual(options["StartPoint"], [0.1, 0.2, 0.3])
                self.assertEqual(options["Lower"][2], 0.0)
                self.assertTrue(np.isinf(options["Upper"][0]))
                self.assertEqual(options["TolFun"], 1e-7)

                fit_window.coefficient_table.item(1, 1).setText("")
                with self.assertRaisesRegex(ValueError, "StartPoint"):
                    fit_window.fit_parameters()

                fit_window.coefficient_table.item(1, 1).setText("0.2")
                fit_window.option_widgets["TolFun"].setText("bad")
                with self.assertRaisesRegex(ValueError, "TolFun"):
                    fit_window.fit_parameters()
            finally:
                fit_window.close()

    def test_matlab_fit_mod_widget_displays_structured_fit_result(self):
        class FakeLine:
            def get_linestyle(self):
                return "solid"

        class FakeCurveModify:
            def __init__(self):
                self.expression = ""
                self.x_start = 0.0
                self.x_stop = 1.0
                self.line = FakeLine()
                self.label = "fit"
                self.update_all = Mock()
                self.update_expression = Mock()
                self.update_x_start = Mock()
                self.update_x_stop = Mock()
                self.update_style = Mock()
                self.update_color = Mock()
                self.change_legend = Mock()

        repository, project, _x_ref, _y_ref = self.make_table_repository()
        widget = PyFitModWidget(FakeCurveModify(), repository, project.id, engine="Matlab")
        result = {
            "value_expression": "2.0*x**2+3.0",
            "show_expression": "2.0*x**2+3.0",
            "formula": "a*x^2+b",
            "fit_type": "poly1",
            "coefficients": [
                {"name": "a", "value": 2.0, "lower": 1.0, "upper": 3.0},
                {"name": "b", "value": 3.0, "lower": 2.0, "upper": 4.0},
            ],
            "goodness": {"sse": 0.2, "rsquare": 0.9, "dfe": 1, "adjrsquare": 0.7, "rmse": 0.4472},
            "confidence_level": 0.95,
        }
        try:
            widget.update_curve(result, 1.0, 3.0)

            self.assertEqual(widget.expression_input.toPlainText(), "2.0*x**2+3.0")
            self.assertEqual(widget.result_model_label.text(), "Model: poly1")
            self.assertEqual(widget.result_formula_input.toPlainText(), "a*x^2+b")
            self.assertEqual(widget.result_coeff_table.item(0, 0).text(), "a")
            self.assertEqual(widget.result_coeff_table.item(0, 1).text(), "2.0000")
            self.assertEqual(widget.result_goodness_table.item(1, 1).text(), "0.9000")
            widget.curve_modify.update_all.assert_called_once_with(1.0, 3.0, "2.0*x**2+3.0")
        finally:
            widget.close()

    def test_stale_fit_result_restores_dialog_button_without_updating_curve(self):
        class FakeLine:
            def get_linestyle(self):
                return "solid"

        class FakeCurveModify:
            def __init__(self):
                self.expression = ""
                self.x_start = 0.0
                self.x_stop = 1.0
                self.line = FakeLine()
                self.label = "fit"
                self.update_all = Mock()
                self.update_expression = Mock()
                self.update_x_start = Mock()
                self.update_x_stop = Mock()
                self.update_style = Mock()
                self.update_color = Mock()
                self.change_legend = Mock()

        repository, project, _x_ref, _y_ref = self.make_table_repository()
        widget = PyFitModWidget(FakeCurveModify(), repository, project.id)
        dialog = QDialog(widget)
        dialog.fit_button = QPushButton("Fit", dialog)
        dialog.fit_button.setEnabled(False)
        dialog.fit_button.setText("Fitting...")
        dialog._fit_request_id = 1
        widget._fit_request_id = 2
        result = {
            "value_expression": "x",
            "show_expression": "x",
            "formula": "x",
            "fit_type": "poly1",
            "coefficients": [],
            "goodness": {},
            "engine": "Python",
        }
        try:
            widget._fit_dialog_succeeded(lambda: dialog, 1, result, 0.0, 1.0, "Python")

            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertEqual(dialog.fit_button.text(), "Fit")
            self.assertEqual(widget.result_model_label.text(), "Model: -")
            widget.curve_modify.update_all.assert_not_called()

            widget._fit_dialog_succeeded(lambda: None, 2, result, 0.0, 1.0, "Python")
            widget.curve_modify.update_all.assert_not_called()
        finally:
            dialog.close()
            widget.close()

    def test_matlab_fitting_failure_only_warns(self):
        class FakeLine:
            def get_linestyle(self):
                return "solid"

        class FakeCurveModify:
            def __init__(self):
                self.expression = ""
                self.x_start = 0.0
                self.x_stop = 1.0
                self.line = FakeLine()
                self.label = "fit"
                self.update_all = Mock()
                self.update_expression = Mock()
                self.update_x_start = Mock()
                self.update_x_stop = Mock()
                self.update_style = Mock()
                self.update_color = Mock()
                self.change_legend = Mock()

        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget = PyFitModWidget(
            FakeCurveModify(),
            repository,
            project.id,
            x_ref=x_ref,
            y_ref=y_ref,
            engine="Matlab",
        )
        try:
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(
                    fit_options_module.matlab_adapter,
                    "get_func_info_isolated",
                    return_value=matlab_adapter.fallback_func_info("poly1"),
                ), patch.object(
                    matlab_adapter,
                    "fit_curve_isolated",
                    side_effect=RuntimeError("MATLAB fitting failed: fit failed"),
                ):
                    dialog = widget.open_fit_window("Matlab")
                    self.assertIsNotNone(dialog)
                    dialog.fit_options_widget.order_input.setCurrentText("poly1")
                    dialog.fit_button.click()
                    self.wait_until(lambda: any(level == "error" for _, level in messages))

            self.assertEqual(widget.result_model_label.text(), "Model: -")
            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertIn(("MATLAB fitting failed: fit failed", "error"), messages)

            log_text = "\n".join(logs.output)
            self.assertIn("Matlab fit request started request_id=1", log_text)
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_matlab_invalid_fit_parameters_warns_without_calling_matlab(self):
        class FakeLine:
            def get_linestyle(self):
                return "solid"

        class FakeCurveModify:
            def __init__(self):
                self.expression = ""
                self.x_start = 0.0
                self.x_stop = 1.0
                self.line = FakeLine()
                self.label = "fit"
                self.update_all = Mock()
                self.update_expression = Mock()
                self.update_x_start = Mock()
                self.update_x_stop = Mock()
                self.update_style = Mock()
                self.update_color = Mock()
                self.change_legend = Mock()

        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget = PyFitModWidget(
            FakeCurveModify(),
            repository,
            project.id,
            x_ref=x_ref,
            y_ref=y_ref,
            engine="Matlab",
        )
        try:
            with patch.object(
                fit_options_module.matlab_adapter,
                "get_func_info_isolated",
                return_value=matlab_adapter.fallback_func_info("poly1"),
            ), patch.object(matlab_adapter, "fit_curve_isolated") as fit_curve_isolated:
                dialog = widget.open_fit_window("Matlab")
                self.assertIsNotNone(dialog)
                dialog.fit_options_widget.advanced_option.setChecked(True)
                dialog.fit_options_widget.coefficient_table.item(0, 1).setText("bad")
                dialog.fit_button.click()

            self.assertIn(("p1 Lower must be a number.", "error"), messages)
            fit_curve_isolated.assert_not_called()
            self.assertTrue(dialog.fit_button.isEnabled())
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_adapter_get_func_exp_releases_runtime_on_success_and_failure(self):
        success_handle = Mock()
        success_handle.get_func.return_value = (
            "a*x+b",
            ["a", "b"],
            json.dumps(matlab_adapter.default_fit_options("poly1", ["a", "b"])),
        )
        success_package = SimpleNamespace(initialize=Mock(return_value=success_handle))
        with patch.object(matlab_adapter.importlib, "import_module", return_value=success_package):
            self.assertEqual(matlab_adapter.get_func_exp("poly1"), ("a*x+b", ["a", "b"]))
        success_handle.get_func.assert_called_once_with("poly1", nargout=3)
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
        success_handle.curve_fitting.return_value = (
            "a*x^2+b",
            ["a", "b"],
            [[2.0, 3.0]],
            json.dumps({"sse": 0.2, "rsquare": 0.9, "dfe": 1, "adjrsquare": 0.7, "rmse": 0.4472}),
            [[1.0, 2.0], [3.0, 4.0]],
            "{}",
        )
        success_package = SimpleNamespace(initialize=Mock(return_value=success_handle))

        def success_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return success_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=success_import):
            result = matlab_adapter.fit_curve([1.0], [2.0], "poly1")
            self.assertEqual(result["value_expression"], "2.0*x**2+3.0")
            self.assertEqual(result["coefficients"][0], {"name": "a", "value": 2.0, "lower": 1.0, "upper": 3.0})
            self.assertEqual(result["goodness"]["rsquare"], 0.9)
            self.assertEqual(result["confidence_level"], 0.95)
        success_call = success_handle.curve_fitting.call_args
        self.assertEqual(success_call.kwargs["nargout"], 6)
        self.assertEqual(len(success_call.args), 4)
        self.assertEqual(success_call.args[3], "")
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
                matlab_adapter.fit_curve([1.0], [2.0], "poly1")
        failure_handle.terminate.assert_called_once()

    def test_adapter_fit_curve_encodes_advanced_options_json(self):
        matlab_module = SimpleNamespace(
            double=Mock(side_effect=lambda values, size: ("double", list(values), size))
        )
        handle = Mock()
        handle.curve_fitting.return_value = (
            "a*x+b",
            ["a", "b"],
            [[2.0, 3.0]],
            json.dumps({"sse": 0, "rsquare": 1, "dfe": 1, "adjrsquare": 1, "rmse": 0}),
            [[1.0, 2.0], [3.0, 4.0]],
            "{}",
        )
        package = SimpleNamespace(initialize=Mock(return_value=handle))

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return package
            raise ImportError(name)

        fit_options = {
            "Normalize": "on",
            "TolFun": 1e-7,
            "Lower": [float("-inf"), 0.0],
            "Upper": [float("inf"), 10.0],
            "StartPoint": [0.1, 0.2],
        }
        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            matlab_adapter.fit_curve([1.0], [2.0], "gauss1", fit_options)

        options_json = handle.curve_fitting.call_args.args[3]
        payload = json.loads(options_json)
        self.assertEqual(payload["Normalize"], "on")
        self.assertEqual(payload["TolFun"], 1e-7)
        self.assertEqual(payload["Lower"], ["-Inf", 0.0])
        self.assertEqual(payload["Upper"], ["Inf", 10.0])
        self.assertEqual(payload["StartPoint"], [0.1, 0.2])

    def test_adapter_fit_result_converts_matlab_elementwise_formula(self):
        result = matlab_adapter._build_fit_result(
            "gauss1",
            "a1.*exp(-((x-b1)./c1).^2)",
            ["a1", "b1", "c1"],
            [[2.0, 3.0, 4.0]],
            json.dumps({"sse": 0, "rsquare": 1, "dfe": 1, "adjrsquare": 1, "rmse": 0}),
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        )

        self.assertEqual(result["value_expression"], "2.0*exp(-((x-3.0)/4.0)**2)")
        x = np.array([3.0, 7.0])
        y = evaluate_curve_expression(result["value_expression"], x)
        np.testing.assert_allclose(y, 2.0 * np.exp(-((x - 3.0) / 4.0) ** 2))

    def test_adapter_fit_curve_rejects_legacy_signature_error(self):
        matlab_module = SimpleNamespace(
            double=Mock(side_effect=lambda values, size: ("double", list(values), size))
        )
        legacy_handle = Mock()
        legacy_handle.curve_fitting.side_effect = RuntimeError(
            "An error occurred when evaluating the result from a function. Details: \u8f93\u5165\u53c2\u6570\u592a\u591a\u3002"
        )
        legacy_package = SimpleNamespace(initialize=Mock(return_value=legacy_handle))

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return legacy_package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "must be regenerated"):
                matlab_adapter.fit_curve([1.0], [5.0], "poly1")

        self.assertEqual(legacy_handle.curve_fitting.call_count, 1)
        call = legacy_handle.curve_fitting.call_args
        self.assertEqual(call.kwargs["nargout"], 6)
        self.assertEqual(len(call.args), 4)
        self.assertEqual(call.args[3], "")
        legacy_handle.terminate.assert_called_once()

    def test_adapter_fit_curve_replaces_overlapping_coefficient_names_safely(self):
        matlab_module = SimpleNamespace(
            double=Mock(side_effect=lambda values, size: ("double", list(values), size))
        )
        handle = Mock()
        handle.curve_fitting.return_value = (
            "p10*x+p1",
            ["p1", "p10"],
            [[2.0, 10.0]],
            json.dumps({"sse": 0, "rsquare": 1, "dfe": 1, "adjrsquare": 1, "rmse": 0}),
            [[None, None], [None, None]],
            "{}",
        )
        package = SimpleNamespace(initialize=Mock(return_value=handle))

        def fake_import(name):
            if name == "matlab":
                return matlab_module
            if name == matlab_adapter.CURVE_FITTING_PACKAGE:
                return package
            raise ImportError(name)

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=fake_import):
            result = matlab_adapter.fit_curve([1.0], [2.0], "poly9")
            self.assertEqual(result["value_expression"], "10.0*x+2.0")

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
                matlab_fitting_module.matlab_fitting([1.0], [2.0], "poly1")

        with patch.object(matlab_adapter.importlib, "import_module", side_effect=ImportError("missing matlab runtime")):
            with self.assertRaisesRegex(RuntimeError, "MATLAB package import failed"):
                get_func_exp_module.get_func_exp("poly1")


if __name__ == "__main__":
    unittest.main()
