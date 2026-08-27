from contextlib import contextmanager
import os
import json
import subprocess
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

from tests.axes_helpers import create_regular_axes
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from mygui import tex_config
from mygui import status_messages
from mygui.database import ColumnRef, TableRepository, matlab_adapter, scipy_fit_adapter
from mygui.database.safe_expression import evaluate_curve_expression
from mygui.figuremodify.component_services import FitService, TextRenderService
from mygui.figuremodify.components import (
    ComponentBatchChange,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    FitCurveController,
    FitEngine,
    TextController,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.fig_control_window.component_editors import (
    ComponentEditorManager,
    EditorRegistry,
    MessagePresenter,
    register_production_profiles,
)
from mygui.widgets.fig_control_window import py_matlab_window as matlab_window_module
from mygui.widgets.fig_control_window import py_fit_options_window as fit_options_module
from mygui.widgets.fig_control_window.py_fit_options_window import PyMatlabFitOptionsWidget
from mygui.widgets.fig_control_window.py_matlab_window import PyMatlabWindow
from mygui.widgets.fig_control_window.py_tex_window import PyTexWindow


def make_text_controller(figure, text_artist):
    registry = ComponentRegistry()
    controller = TextController(
        ComponentState(
            id="text",
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
            order=0,
            selector={"object_id": "text", "scope": "figure"},
            properties={},
        )
    )
    registry.register(controller, target=text_artist, require_parent=False)
    controller.sync_from_target()
    service = TextRenderService(registry)
    editor_registry = EditorRegistry()
    register_production_profiles(editor_registry)
    manager = ComponentEditorManager(registry, editor_registry)
    context = SimpleNamespace(
        registry=registry,
        text_rendering=service,
        messages=MessagePresenter(),
        color_library=ColorLibrary(),
        editor_manager=manager,
    )
    return controller, service, context


def register_text_render_service(service):
    """Attach the same Canvas-owned TeX refresh adapter used in production."""

    def listener(change):
        result = service.apply_tex_availability(
            change.after.enabled,
            force=change.preamble_changed and change.after.enabled,
        )
        return None if result.committed else result.message

    tex_config.register_tex_render_listener(listener)
    return listener


def make_fit_editor(
    repository,
    project_id,
    x_ref,
    y_ref,
    *,
    engine="Python",
    fit_result=None,
):
    figure = Figure()
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    line, = axes.plot([0.0, 1.0], [0.0, 1.0], label="fit")
    registry = ComponentRegistry()
    controller = FitCurveController(
        ComponentState(
            id="fit",
            kind=ComponentKind.LINE,
            role=ComponentRole.FIT_CURVE,
            order=0,
            selector={"object_id": "fit"},
            properties={"label": "fit"},
            data={
                "x_ref": x_ref.to_dict(),
                "y_ref": y_ref.to_dict(),
                "engine": engine,
                "fit_type": None,
                "fit_options": None,
                "fit_result": fit_result,
                "expression": "",
                "x_start": 0.0,
                "x_stop": 1.0,
            },
        )
    )
    registry.register(controller, target=line, require_parent=False)
    library = ColorLibrary()
    context = SimpleNamespace(
        repository=repository,
        registry=registry,
        fitting=FitService(repository, registry),
        messages=MessagePresenter(),
        color_library=library,
    )
    editor_registry = EditorRegistry()
    register_production_profiles(editor_registry)
    context.editor_manager = ComponentEditorManager(
        registry,
        editor_registry,
    )
    widget = context.editor_manager.create(
        controller,
        context=context,
    )
    return widget, widget.section("actions").domain, controller, line


class OptionalDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        tex_config.set_tex_enabled(False, notify=False)
        tex_config.clear_tex_runtime_listeners()
        tex_config.configure_tex_runtime(
            preamble=tex_config.default_preamble_text(),
            notify=False,
        )
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
            with patch.object(PyTexWindow, "_has_tex_engine", return_value=False):
                window.use_latex_engine(Qt.CheckState.Checked)
                self.wait_until(
                    lambda: bool(status_events)
                    and status_events[-1][1] == "error"
                )

            self.assertFalse(tex_config.is_tex_enabled())
            self.assertFalse(window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
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

    def test_tex_runtime_update_separates_availability_and_render_events(self):
        tex_config.configure_tex_runtime(
            enabled=False,
            preamble="\\usepackage{old}",
            notify=False,
        )
        availability = []
        renders = []

        def render_listener(change):
            renders.append(change)
            return "first Figure used safe fallback"

        tex_config.register_tex_availability_listener(availability.append)
        tex_config.register_tex_render_listener(render_listener)
        update = tex_config.configure_tex_runtime(
            enabled=True,
            preamble=" \\usepackage{amsmath} \n\n \\usepackage{xcolor} ",
        )

        self.assertTrue(update.change.enabled_changed)
        self.assertTrue(update.change.preamble_changed)
        self.assertEqual(availability, [True])
        self.assertEqual(renders, [update.change])
        self.assertEqual(update.warnings, ("first Figure used safe fallback",))
        self.assertEqual(
            tex_config.read_tex_runtime(),
            tex_config.TexRuntimeState(
                True,
                "\\usepackage{amsmath}\n\\usepackage{xcolor}",
            ),
        )

    def test_tex_runtime_assignment_failure_restores_both_rcparams(self):
        tex_config.configure_tex_runtime(
            enabled=False,
            preamble="\\usepackage{old}",
            notify=False,
        )
        before = tex_config.read_tex_runtime()
        rcparams_type = type(mpl.rcParams)
        original_setitem = rcparams_type.__setitem__
        failed = False

        def fail_enabled_once(target, key, value):
            nonlocal failed
            if key == "text.usetex" and bool(value) and not failed:
                failed = True
                raise RuntimeError("injected rcParams failure")
            return original_setitem(target, key, value)

        with patch.object(rcparams_type, "__setitem__", new=fail_enabled_once):
            with self.assertRaisesRegex(RuntimeError, "rcParams failure"):
                tex_config.configure_tex_runtime(
                    enabled=True,
                    preamble="\\usepackage{new}",
                )

        self.assertEqual(tex_config.read_tex_runtime(), before)

    def test_tex_startup_disables_external_flag_and_preserves_preamble(self):
        tex_config.configure_tex_runtime(
            enabled=True,
            preamble="\\usepackage{external}",
            notify=False,
        )

        update = tex_config.initialize_tex_runtime()

        self.assertTrue(update.change.enabled_changed)
        self.assertEqual(
            tex_config.read_tex_runtime(),
            tex_config.TexRuntimeState(False, "\\usepackage{external}"),
        )

    def test_enabled_preamble_change_forces_canvas_render_refresh(self):
        from main import MainWindow

        window = MainWindow()
        try:
            canvas = window.figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="tex-preamble-refresh",
            )
            tex_config.configure_tex_runtime(
                enabled=True,
                preamble="\\usepackage{old}",
                notify=False,
            )
            committed = ComponentBatchChange((), True)
            with patch.object(
                canvas.text_render_service,
                "apply_tex_availability",
                return_value=committed,
            ) as apply_availability:
                update = tex_config.configure_tex_runtime(
                    preamble="\\usepackage{new}",
                )

            self.assertEqual(update.warnings, ())
            apply_availability.assert_called_once_with(True, force=True)
        finally:
            window.close()

    def test_tex_panel_combines_multiple_canvas_refresh_warnings(self):
        tex_config.configure_tex_runtime(
            enabled=True,
            preamble="\\usepackage{old}",
            notify=False,
        )
        window = PyTexWindow()
        status_events = []
        tex_config.register_tex_render_listener(lambda _change: "Figure A fallback")
        tex_config.register_tex_render_listener(lambda _change: "Figure B fallback")
        status_messages.set_status_handler(
            lambda message, level: status_events.append((message, level))
        )
        try:
            window._commit_preamble("\\usepackage{new}", time.monotonic())

            self.assertEqual(len(status_events), 1)
            self.assertEqual(status_events[0][1], "warning")
            self.assertIn("Figure A fallback", status_events[0][0])
            self.assertIn("Figure B fallback", status_events[0][0])
        finally:
            window.close()

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
                            "mygui.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value="render probe failed",
                        ) as validate_tex_runtime:
                    window.latex_engine.setChecked(True)
                    self.wait_until(
                        lambda: bool(status_events)
                        and status_events[-1] == ("render probe failed", "error")
                    )

            validate_tex_runtime.assert_called_once_with(tex_config.default_preamble_text())
            self.assertFalse(tex_config.is_tex_enabled())
            self.assertFalse(window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
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
                            "mygui.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value=None,
                        ) as validate_tex_runtime:
                    window.latex_engine.setChecked(True)
                    self.wait_until(tex_config.is_tex_enabled)

            expected_preamble = "\\usepackage{amsmath}\n\\usepackage{xcolor}"
            validate_tex_runtime.assert_called_once_with(expected_preamble)
            self.assertTrue(tex_config.is_tex_enabled())
            self.assertTrue(window.latex_engine.isChecked())
            self.assertTrue(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], expected_preamble)
            self.assertEqual(
                tex_config.read_tex_runtime().preamble,
                expected_preamble,
            )
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
            tex_config.configure_tex_runtime(
                enabled=True,
                preamble=old_preamble,
                notify=False,
            )
            window.preamble_input.setPlainText("\\usepackage{broken}")
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )

            with patch.object(tex_config, "_LOG_TO_FILE", False), \
                    patch.object(tex_config, "_LOG_TO_STDERR", False), \
                    self.assertLogs(tex_config.LOGGER_NAME, level="INFO") as logs:
                with patch.object(PyTexWindow, "_has_tex_engine", return_value=True), \
                        patch(
                            "mygui.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                            return_value="bad preamble",
                        ) as validate_tex_runtime:
                    window.update_preamble()
                    self.wait_until(
                        lambda: bool(status_events)
                        and status_events[-1] == ("bad preamble", "error")
                    )

            validate_tex_runtime.assert_called_once_with("\\usepackage{broken}")
            self.assertTrue(tex_config.is_tex_enabled())
            self.assertTrue(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], old_preamble)
            self.assertEqual(tex_config.read_tex_runtime().preamble, old_preamble)
            self.assertEqual(status_events[-1], ("bad preamble", "error"))
            log_text = "\n".join(logs.output)
            self.assertIn("TeX preamble update request started", log_text)
            self.assertIn("TeX preamble update request failed", log_text)
        finally:
            window.close()

    def test_tex_preamble_update_while_disabled_skips_runtime_probe(self):
        window = PyTexWindow()
        try:
            tex_config.set_tex_enabled(False, notify=False)
            window.preamble_input.setPlainText("\\usepackage{amsmath}\n\n\\usepackage{xcolor}")

            with patch(
                "mygui.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
            ) as validate_tex_runtime:
                window.update_preamble()

            expected_preamble = "\\usepackage{amsmath}\n\\usepackage{xcolor}"
            validate_tex_runtime.assert_not_called()
            self.assertFalse(mpl.rcParams['text.usetex'])
            self.assertEqual(mpl.rcParams['text.latex.preamble'], expected_preamble)
            self.assertEqual(
                tex_config.read_tex_runtime().preamble,
                expected_preamble,
            )
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
                        "mygui.widgets.fig_control_window.py_tex_window.tex_config.validate_tex_runtime",
                        return_value="render probe failed",
                    ):
                tex_window.latex_engine.setChecked(True)
                self.wait_until(
                    lambda: bool(status_events)
                    and status_events[-1] == ("render probe failed", "error")
                )

            self.assertIsNotNone(window.fig_control_window.tex_window)
            self.assertFalse(tex_config.is_tex_enabled())
            self.assertFalse(tex_window.latex_engine.isChecked())
            self.assertFalse(mpl.rcParams['text.usetex'])
            self.assertEqual(status_events[-1], ("render probe failed", "error"))
        finally:
            window.close()

    def test_tex_text_render_failure_restores_previous_controller_state(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        controller, service, _context = make_text_controller(figure, text)

        with patch.object(tex_config, "_LOG_TO_FILE", False), \
                patch.object(tex_config, "_LOG_TO_STDERR", False), \
                self.assertLogs(tex_config.LOGGER_NAME, level="WARNING") as logs:
            with patch.object(
                figure.canvas,
                "draw",
                side_effect=RuntimeError("latex failed"),
            ):
                result = service.apply(
                    controller,
                    {"text": "$\\int$" + chr(0xFFE5)},
                )

        self.assertFalse(result.ok)
        self.assertEqual(text.get_text(), "safe")
        self.assertEqual(controller.state.properties["text"], "safe")
        self.assertIn("Text render failed", "\n".join(logs.output))

    def test_text_render_rejects_missing_glyph_and_reports_error(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        controller, service, context = make_text_controller(figure, text)
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
                result = service.apply(
                    controller,
                    {"text": "plain"},
                )
                context.messages.present(result)

        self.assertFalse(result.ok)
        self.assertEqual(text.get_text(), "safe")
        self.assertEqual(controller.state.properties["text"], "safe")
        self.assertEqual(status_events[-1][1], "error")
        self.assertIn("U+FFE5", status_events[-1][0])
        self.assertIn("Matplotlib text glyph warning", "\n".join(logs.output))

    def test_text_widget_reports_status_and_rolls_back_editor_when_tex_render_fails(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        controller, _service, context = make_text_controller(figure, text)
        widget = context.editor_manager.create(controller, context=context)
        content = widget.section("content")
        status_events = []
        bad_text = "$\\int$" + chr(0xFFE5)
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            content.text_content.blockSignals(True)
            content.text_content.setPlainText(bad_text)
            content.text_content.blockSignals(False)

            with patch.object(
                figure.canvas,
                "draw",
                side_effect=RuntimeError("latex failed"),
            ):
                content.set_text_content()

            self.assertEqual(content.text_content.toPlainText(), "safe")
            self.assertEqual(content._text_binding.delay_ms, 250)
            self.assertEqual(status_events[-1][1], "error")
            self.assertIn("keeping the last valid text", status_events[-1][0])
        finally:
            widget.close()
            context.editor_manager.close()

    def test_text_widget_rolls_back_when_render_reports_missing_glyph(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "safe")
        controller, _service, context = make_text_controller(figure, text)
        widget = context.editor_manager.create(controller, context=context)
        content = widget.section("content")
        status_events = []

        def draw_warning():
            warnings.warn(
                "Glyph 65509 missing from font(s) DejaVu Sans.",
                UserWarning,
            )

        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            content.text_content.blockSignals(True)
            content.text_content.setPlainText("plain")
            content.text_content.blockSignals(False)

            with patch.object(
                figure.canvas,
                "draw",
                side_effect=draw_warning,
            ):
                committed = content.set_text_content()

            self.assertFalse(committed)
            self.assertEqual(content.text_content.toPlainText(), "safe")
            self.assertEqual(text.get_text(), "safe")
            self.assertEqual(controller.state.properties["text"], "safe")
            self.assertEqual(len(status_events), 1)
            self.assertEqual(status_events[-1][1], "error")
            self.assertIn("U+FFE5", status_events[-1][0])
        finally:
            widget.close()
            context.editor_manager.close()

    def test_text_widget_reports_real_mathtext_chinese_glyph_logs(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(
            0.5,
            0.5,
            "safe",
            fontfamily="DejaVu Sans",
        )
        controller, _service, context = make_text_controller(figure, text)
        widget = context.editor_manager.create(controller, context=context)
        content = widget.section("content")
        status_events = []
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            content.text_content.blockSignals(True)
            content.text_content.setPlainText("$\\int$￥都为")
            content.text_content.blockSignals(False)

            self.assertFalse(content.set_text_content())

            self.assertEqual(content.text_content.toPlainText(), "safe")
            self.assertEqual(text.get_text(), "safe")
            self.assertEqual(controller.state.properties["text"], "safe")
            self.assertEqual(len(status_events), 1)
            self.assertEqual(status_events[-1][1], "error")
            self.assertIn("U+FFE5", status_events[-1][0])
            self.assertIn("U+90FD", status_events[-1][0])
            self.assertIn("U+4E3A", status_events[-1][0])
            self.assertTrue(
                all(level != "success" for _message, level in status_events)
            )
        finally:
            widget.close()
            context.editor_manager.close()

    def test_text_widget_tex_button_disabled_when_global_tex_is_off(self):
        tex_config.set_tex_enabled(False, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        controller, _service, context = make_text_controller(figure, text)
        widget = context.editor_manager.create(controller, context=context)
        render = widget.section("render")
        try:
            self.assertFalse(render.tex_render.isEnabled())
            self.assertFalse(render.tex_render.isChecked())
            self.assertFalse(text.get_usetex())
        finally:
            widget.close()
            context.editor_manager.close()

    def test_text_widget_tex_button_toggles_individual_text_rendering(self):
        tex_config.set_tex_enabled(False, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        tex_config.set_tex_enabled(True, notify=False)
        controller, _service, context = make_text_controller(figure, text)
        status_events = []

        widget = context.editor_manager.create(controller, context=context)
        render = widget.section("render")
        try:
            status_messages.set_status_handler(
                lambda message, level: status_events.append((message, level))
            )
            self.assertTrue(render.tex_render.isEnabled())
            self.assertFalse(render.tex_render.isChecked())

            with patch.object(figure.canvas, "draw"):
                render.tex_render.setChecked(True)

            self.assertTrue(text.get_usetex())
            self.assertTrue(controller.state.properties["usetex"])
            self.assertEqual(status_events[-1], ("Text TeX rendering enabled.", "success"))

            with patch.object(figure.canvas, "draw"):
                render.tex_render.setChecked(False)

            self.assertFalse(text.get_usetex())
            self.assertFalse(controller.state.properties["usetex"])
        finally:
            widget.close()
            context.editor_manager.close()

    def test_global_tex_disable_preserves_requested_text_tex_mode(self):
        tex_config.set_tex_enabled(True, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        text.set_usetex(True)
        controller, service, context = make_text_controller(figure, text)
        controller.set_property("usetex", True)
        listener = register_text_render_service(service)

        widget = context.editor_manager.create(controller, context=context)
        render = widget.section("render")
        try:
            self.assertTrue(render.tex_render.isEnabled())
            self.assertTrue(render.tex_render.isChecked())

            with patch.object(figure.canvas, "draw"):
                tex_config.set_tex_enabled(False)

            self.assertFalse(render.tex_render.isEnabled())
            self.assertTrue(render.tex_render.isChecked())
            self.assertFalse(text.get_usetex())
            self.assertTrue(controller.state.properties["usetex"])

            with patch.object(figure.canvas, "draw"):
                tex_config.set_tex_enabled(True)
            self.assertTrue(render.tex_render.isEnabled())
            self.assertTrue(render.tex_render.isChecked())
            self.assertTrue(text.get_usetex())
            self.assertTrue(controller.state.properties["usetex"])
        finally:
            tex_config.unregister_tex_render_listener(listener)
            widget.close()
            context.editor_manager.close()

    def test_tex_reenable_probe_failure_keeps_safe_effective_state(self):
        tex_config.set_tex_enabled(True, notify=False)
        figure = Figure()
        FigureCanvasAgg(figure)
        text = figure.text(0.5, 0.5, "plain")
        text.set_usetex(True)
        controller, service, context = make_text_controller(figure, text)
        controller.set_property("usetex", True)
        listener = register_text_render_service(service)
        widget = context.editor_manager.create(controller, context=context)
        render = widget.section("render")
        try:
            tex_config.set_tex_enabled(False)
            self.assertFalse(text.get_usetex())
            with patch.object(
                figure.canvas,
                "draw",
                side_effect=RuntimeError("injected TeX render probe failure"),
            ):
                update = tex_config.set_tex_enabled(True)

            self.assertTrue(controller.state.properties["usetex"])
            self.assertFalse(text.get_usetex())
            self.assertFalse(service.effective_usetex(controller.component_id))
            self.assertTrue(render.tex_render.isChecked())
            self.assertEqual(len(update.warnings), 1)
            self.assertIn("render probe failed", update.warnings[0])
        finally:
            tex_config.unregister_tex_render_listener(listener)
            widget.close()
            context.editor_manager.close()

    def test_new_text_defaults_to_tex_when_global_tex_is_enabled(self):
        from main import MainWindow

        window = MainWindow()
        try:
            window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="tex")
            canvas = window.figure_window.current_canva
            create_regular_axes(canvas, nrows=1, ncols=1)
            tex_config.set_tex_enabled(True, notify=False)

            with patch.object(canvas.fig.canvas, "draw"), patch.object(canvas, "redraw"):
                canvas.add_text(
                    x=0.2,
                    y=0.8,
                    text="plain",
                    fontfamily="DejaVu Sans",
                    fontsize=12,
                )

            text_artist = canvas.current_axes.texts[-1]
            axes_inspector = canvas.figure_inspector.axes_inspector(
                canvas.current_axes_component_id
            )
            text_widget = axes_inspector.inspector(text_artist.get_gid())
            controller = canvas.component_registry.get(
                text_artist.get_gid()
            )

            self.assertTrue(text_artist.get_usetex())
            self.assertTrue(controller.state.properties["usetex"])
            render = text_widget.section("render")
            self.assertTrue(render.tex_render.isEnabled())
            self.assertTrue(render.tex_render.isChecked())
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
                self.assertIsNone(options["Upper"][0])
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

    def test_matlab_fit_section_displays_structured_fit_result(self):
        repository, project, x_ref, y_ref = self.make_table_repository()
        widget, fit, controller, line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
            engine="Matlab",
        )
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
            fit.update_curve(result, 1.0, 3.0)

            self.assertEqual(fit.expression_input.toPlainText(), "2.0*x**2+3.0")
            self.assertEqual(fit.result_model_label.text(), "Model: poly1")
            self.assertEqual(fit.result_formula_input.toPlainText(), "a*x^2+b")
            self.assertEqual(fit.result_coeff_table.item(0, 0).text(), "a")
            self.assertEqual(fit.result_coeff_table.item(0, 1).text(), "2.0000")
            self.assertEqual(fit.result_goodness_table.item(1, 1).text(), "0.9000")
            self.assertEqual(
                controller.state.data["expression"],
                "2.0*x**2+3.0",
            )
            self.assertEqual(controller.state.data["x_start"], 1.0)
            self.assertEqual(controller.state.data["x_stop"], 3.0)
            self.assertEqual(len(line.get_xdata()), 1000)
        finally:
            widget.close()
            fit.context.editor_manager.close()

    def test_fit_inspector_dispose_cancels_request_and_closes_dialog(self):
        repository, project, x_ref, y_ref = self.make_table_repository(
            with_data=True
        )
        widget, fit, controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
        )
        request_id = fit.context.fitting.next_request(
            controller.component_id
        )
        dialog = fit.open_fit_window("Python")
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isVisible())

        fit.context.editor_manager.close()
        fit.context.editor_manager.close()

        self.assertTrue(widget._disposed)
        self.assertTrue(fit._disposed)
        self.assertFalse(dialog.isVisible())
        self.assertFalse(
            fit.context.fitting.request_is_current(
                controller.component_id,
                request_id,
            )
        )
        widget.close()

    def test_stale_fit_result_restores_dialog_button_without_updating_curve(self):
        repository, project, x_ref, y_ref = self.make_table_repository()
        widget, fit, controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
        )
        dialog = QDialog(widget)
        dialog.fit_button = QPushButton("Fit", dialog)
        dialog.fit_button.setEnabled(False)
        dialog.fit_button.setText("Fitting...")
        request_id = fit.context.fitting.next_request(
            controller.component_id
        )
        dialog._fit_request_id = request_id
        fit.context.fitting.next_request(controller.component_id)
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
            fit._fit_dialog_succeeded(
                lambda: dialog,
                request_id,
                result,
                0.0,
                1.0,
                "Python",
            )

            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertEqual(dialog.fit_button.text(), "Fit")
            self.assertEqual(fit.result_model_label.text(), "Model: -")
            self.assertEqual(controller.state.data["expression"], "")

            fit._fit_dialog_succeeded(
                lambda: None,
                request_id + 1,
                result,
                0.0,
                1.0,
                "Python",
            )
        finally:
            dialog.close()
            widget.close()
            fit.context.editor_manager.close()

    def test_fit_execution_service_matlab_modes(self):
        from mygui.template_library.fit_execution import FitExecutionService

        service = FitExecutionService()
        x = [0.0, 1.0, 2.0]
        y = [0.0, 2.0, 4.0]

        # Mode A: unavailable -> raises RuntimeError, fit_curve_isolated NOT called
        with patch.object(
            matlab_adapter,
            "matlab_status",
            return_value=matlab_adapter.MatlabStatus(
                False, "MATLAB runtime unavailable: missing runtime"
            ),
        ) as status_mock, patch.object(
            matlab_adapter, "fit_curve_isolated"
        ) as fit_mock:
            with self.assertRaisesRegex(
                RuntimeError, "MATLAB runtime unavailable: missing runtime"
            ):
                service.execute_arrays(x, y, "poly1", None, engine=FitEngine.MATLAB)
            status_mock.assert_called_once()
            fit_mock.assert_not_called()

        # Mode B: available + fitting failure -> fit_curve_isolated called, raises RuntimeError
        with patch.object(
            matlab_adapter,
            "matlab_status",
            return_value=matlab_adapter.MatlabStatus(True),
        ) as status_mock, patch.object(
            matlab_adapter,
            "fit_curve_isolated",
            side_effect=RuntimeError("MATLAB fitting failed: solver diverged"),
        ) as fit_mock:
            with self.assertRaisesRegex(
                RuntimeError, "MATLAB fitting failed: solver diverged"
            ):
                service.execute_arrays(x, y, "poly1", None, engine=FitEngine.MATLAB)
            status_mock.assert_called_once()
            fit_mock.assert_called_once()

        # Mode C: available + fitting success -> returns normalized result
        fake_result = {
            "value_expression": "2.0*x",
            "show_expression": "2.0*x",
            "formula": "p1*x",
            "fit_type": "poly1",
            "coefficients": [{"name": "p1", "value": 2.0, "lower": 1.0, "upper": 3.0}],
            "goodness": {"sse": 0.0, "rsquare": 1.0, "dfe": 2, "adjrsquare": 1.0, "rmse": 0.0},
            "confidence_level": 0.95,
            "engine": "Matlab",
        }
        with patch.object(
            matlab_adapter,
            "matlab_status",
            return_value=matlab_adapter.MatlabStatus(True),
        ) as status_mock, patch.object(
            matlab_adapter,
            "fit_curve_isolated",
            return_value=fake_result,
        ) as fit_mock:
            result = service.execute_arrays(x, y, "poly1", None, engine=FitEngine.MATLAB)
            status_mock.assert_called_once()
            fit_mock.assert_called_once()
            self.assertEqual(result["value_expression"], "2.0*x")
            self.assertEqual(result["fit_type"], "poly1")

    def test_matlab_runtime_unavailable_only_warns(self):
        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget, fit, _controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
            engine="Matlab",
        )
        try:
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(
                    matlab_adapter,
                    "matlab_status",
                    return_value=matlab_adapter.MatlabStatus(
                        False,
                        "MATLAB runtime unavailable: test runtime missing",
                    ),
                ) as matlab_status, patch.object(
                    fit_options_module.matlab_adapter,
                    "get_func_info_isolated",
                    return_value=matlab_adapter.fallback_func_info("poly1"),
                ), patch.object(
                    matlab_adapter,
                    "fit_curve_isolated",
                ) as fit_curve_isolated:
                    dialog = fit.open_fit_window("Matlab")
                    self.assertIsNotNone(dialog)
                    dialog.fit_options_widget.order_input.setCurrentText("poly1")
                    dialog.fit_button.click()
                    self.wait_until(lambda: any(level == "error" for _, level in messages))

            self.assertEqual(fit.result_model_label.text(), "Model: -")
            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertIn(
                ("MATLAB runtime unavailable: test runtime missing", "error"),
                messages,
            )
            fit_curve_isolated.assert_not_called()
            matlab_status.assert_called_once()

            log_text = "\n".join(logs.output)
            self.assertIn("Matlab fit request started request_id=1", log_text)
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            fit.context.editor_manager.close()
            matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_matlab_fitting_failure_only_warns(self):
        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget, fit, _controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
            engine="Matlab",
        )
        try:
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(
                    matlab_adapter,
                    "matlab_status",
                    return_value=matlab_adapter.MatlabStatus(True),
                ) as matlab_status, patch.object(
                    fit_options_module.matlab_adapter,
                    "get_func_info_isolated",
                    return_value=matlab_adapter.fallback_func_info("poly1"),
                ), patch.object(
                    matlab_adapter,
                    "fit_curve_isolated",
                    side_effect=RuntimeError("MATLAB fitting failed: fit failed"),
                ) as fit_curve_isolated:
                    dialog = fit.open_fit_window("Matlab")
                    self.assertIsNotNone(dialog)
                    dialog.fit_options_widget.order_input.setCurrentText("poly1")
                    dialog.fit_button.click()
                    self.wait_until(lambda: any(level == "error" for _, level in messages))

            self.assertEqual(fit.result_model_label.text(), "Model: -")
            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertIn(("MATLAB fitting failed: fit failed", "error"), messages)
            fit_curve_isolated.assert_called_once()
            matlab_status.assert_called_once()

            log_text = "\n".join(logs.output)
            self.assertIn("Matlab fit request started request_id=1", log_text)
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            fit.context.editor_manager.close()
            matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_matlab_fitting_success_updates_curve_and_dialog(self):
        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget, fit, controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
            engine="Matlab",
        )
        fake_result = {
            "value_expression": "2.0*x + 1.0",
            "show_expression": "2.0*x + 1.0",
            "formula": "p1*x + p2",
            "fit_type": "poly1",
            "coefficients": [
                {"name": "p1", "value": 2.0, "lower": 1.0, "upper": 3.0},
                {"name": "p2", "value": 1.0, "lower": 0.0, "upper": 2.0},
            ],
            "goodness": {"sse": 0.0, "rsquare": 1.0, "dfe": 1, "adjrsquare": 1.0, "rmse": 0.0},
            "confidence_level": 0.95,
            "engine": "Matlab",
        }
        try:
            with patch.object(matlab_adapter, "_LOG_TO_FILE", False), \
                    patch.object(matlab_adapter, "_LOG_TO_STDERR", False), \
                    self.assertLogs(matlab_adapter.LOGGER_NAME, level="INFO") as logs:
                with patch.object(
                    matlab_adapter,
                    "matlab_status",
                    return_value=matlab_adapter.MatlabStatus(True),
                ) as matlab_status, patch.object(
                    fit_options_module.matlab_adapter,
                    "get_func_info_isolated",
                    return_value=matlab_adapter.fallback_func_info("poly1"),
                ), patch.object(
                    matlab_adapter,
                    "fit_curve_isolated",
                    return_value=fake_result,
                ) as fit_curve_isolated:
                    dialog = fit.open_fit_window("Matlab")
                    self.assertIsNotNone(dialog)
                    dialog.fit_options_widget.order_input.setCurrentText("poly1")
                    dialog.fit_button.click()
                    self.wait_until(lambda: any(level == "success" for _, level in messages))

            self.assertEqual(fit.result_model_label.text(), "Model: poly1")
            self.assertEqual(fit.expression_input.toPlainText(), "2.0*x + 1.0")
            self.assertEqual(controller.state.data["expression"], "2.0*x + 1.0")
            self.assertTrue(dialog.fit_button.isEnabled())
            self.assertIn(("Matlab fitting completed.", "success"), messages)
            fit_curve_isolated.assert_called_once()
            matlab_status.assert_called_once()

            log_text = "\n".join(logs.output)
            self.assertIn("Matlab fit request started request_id=1", log_text)
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            fit.context.editor_manager.close()
            matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_matlab_invalid_fit_parameters_warns_without_calling_matlab(self):
        repository, project, x_ref, y_ref = self.make_table_repository(with_data=True)
        matlab_adapter.set_matlab_enabled(True, notify=False)

        messages = []
        status_messages.set_status_handler(lambda message, level: messages.append((message, level)))
        widget, fit, _controller, _line = make_fit_editor(
            repository,
            project.id,
            x_ref,
            y_ref,
            engine="Matlab",
        )
        try:
            with patch.object(
                fit_options_module.matlab_adapter,
                "get_func_info_isolated",
                return_value=matlab_adapter.fallback_func_info("poly1"),
            ), patch.object(matlab_adapter, "fit_curve_isolated") as fit_curve_isolated:
                dialog = fit.open_fit_window("Matlab")
                self.assertIsNotNone(dialog)
                self.wait_until(
                    lambda: dialog.fit_options_widget.order_input.isEnabled()
                )
                dialog.fit_options_widget.advanced_option.setChecked(True)
                dialog.fit_options_widget.coefficient_table.item(0, 1).setText("bad")
                dialog.fit_button.click()

            self.assertIn(("p1 Lower must be a number or infinity.", "error"), messages)
            fit_curve_isolated.assert_not_called()
            self.assertTrue(dialog.fit_button.isEnabled())
        finally:
            if "dialog" in locals() and dialog is not None:
                dialog.close()
            widget.close()
            fit.context.editor_manager.close()
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
        with self.temp_dir() as cache_dir:
            with patch.dict(
                matlab_adapter.os.environ,
                {"MYGUI_MATLAB_MCR_CACHE_ROOT": cache_dir},
            ), patch.object(
                matlab_adapter,
                "_run_isolated_process",
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

        with self.temp_dir() as cache_dir, patch.dict(
            matlab_adapter.os.environ,
            {
                "MYGUI_MATLAB_MCR_CACHE_ROOT": str(
                    Path(cache_dir) / "runtime" / "test"
                )
            },
            clear=True,
        ):
            with patch.object(matlab_adapter, "_run_isolated_process", side_effect=fake_run):
                self.assertTrue(matlab_adapter.ensure_matlab_available_isolated(timeout=1).available)

        self.assertTrue(Path(captured["cache_root"]).is_relative_to(cache_dir))
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
                    "MYGUI_MATLAB_MCR_CACHE_ROOT": str(Path(log_dir) / "cache"),
                },
            ):
                with patch.object(matlab_adapter, "_run_isolated_process", side_effect=fake_run):
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
                    "MYGUI_MATLAB_MCR_CACHE_ROOT": str(Path(log_dir) / "cache"),
                },
            ):
                with patch.object(matlab_adapter, "_run_isolated_process", side_effect=fake_run):
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
                    "MYGUI_MATLAB_MCR_CACHE_ROOT": str(Path(log_dir) / "cache"),
                },
            ):
                with patch.object(matlab_adapter, "_run_isolated_process", side_effect=fake_run):
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

    def test_validate_tex_runtime_branches(self):
        from mygui.bounded_process import ProcessOutputLimitExceeded

        # No executable branch
        with patch.object(tex_config, "has_tex_engine", return_value=False):
            err = tex_config.validate_tex_runtime(r"\usepackage{amsmath}")
            self.assertIn("No TeX executable", err)

        # TimeoutExpired branch
        with patch.object(tex_config, "has_tex_engine", return_value=True), \
                patch.object(tex_config, "run_bounded_process", side_effect=subprocess.TimeoutExpired(["tex"], 15)):
            err = tex_config.validate_tex_runtime(r"\usepackage{amsmath}")
            self.assertIn("timed out", err)

        # Output limit exceeded branch
        with patch.object(tex_config, "has_tex_engine", return_value=True), \
                patch.object(tex_config, "run_bounded_process", side_effect=ProcessOutputLimitExceeded("Too much output")):
            err = tex_config.validate_tex_runtime(r"\usepackage{amsmath}")
            self.assertIn("too much output", err.lower())


        # Non-zero returncode branch
        fake_result = SimpleNamespace(returncode=1, stderr=b"! LaTeX Error: File not found.\n")
        with patch.object(tex_config, "has_tex_engine", return_value=True), \
                patch.object(tex_config, "run_bounded_process", return_value=fake_result):
            err = tex_config.validate_tex_runtime(r"\usepackage{amsmath}")
            self.assertIn("LaTeX Error", err)

        # Success branch
        fake_success = SimpleNamespace(returncode=0, stderr=b"")
        with patch.object(tex_config, "has_tex_engine", return_value=True), \
                patch.object(tex_config, "run_bounded_process", return_value=fake_success):
            err = tex_config.validate_tex_runtime(r"\usepackage{amsmath}")
            self.assertIsNone(err)

    def test_tex_config_listener_exceptions_and_environment_timeouts(self):
        # Listener raising exception
        def failing_render_listener(change):
            raise RuntimeError("Render listener exploded")

        def failing_avail_listener(enabled):
            raise RuntimeError("Availability listener exploded")

        tex_config.register_tex_render_listener(failing_render_listener)
        tex_config.register_tex_availability_listener(failing_avail_listener)

        # Should not raise exception and should auto-detach
        update = tex_config.configure_tex_runtime(enabled=True, notify=True)
        self.assertTrue(update.change.after.enabled)

        # Timeout from environment
        with patch.dict(os.environ, {"MYGUI_TEX_TIMEOUT_SECONDS": "25.5"}):
            self.assertEqual(tex_config._timeout_from_environment(), 25.5)
        with patch.dict(os.environ, {"MYGUI_TEX_TIMEOUT_SECONDS": "invalid_num"}):
            self.assertEqual(tex_config._timeout_from_environment(), 15.0)



if __name__ == "__main__":
    unittest.main()

