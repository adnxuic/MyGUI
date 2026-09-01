"""Project navigation toolbar history boundaries and cross-project Undo."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)

from main import MainWindow
from mygui.widgets.figure_canvas.canvas_toolbar import (
    ProjectNavigationToolbar,
    history_command,
)
from tests.axes_helpers import create_regular_axes


class _RecordingHistory:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.started = True

    def perform(self, text, operation, *, scan_all=False):
        self.calls.append(("perform", str(text), bool(scan_all)))
        return operation()

    def begin_interaction(self, text) -> bool:
        self.calls.append(("begin", str(text)))
        return self.started

    def end_interaction(self) -> None:
        self.calls.append(("end",))

    def cancel_interaction(self) -> None:
        self.calls.append(("cancel",))


class _ExportHost(QWidget):
    exportRequested = Signal(object)


class HistoryCommandDecoratorTests(unittest.TestCase):
    def test_decorator_calls_method_when_history_is_missing(self):
        class Host:
            figure_history = None

            @history_command("Do Work")
            def go(self):
                return 7

        self.assertEqual(Host().go(), 7)

    def test_decorator_records_one_history_boundary(self):
        history = _RecordingHistory()

        class Host:
            def __init__(self):
                self.figure_history = history

            @history_command("Do Work", scan_all=True)
            def go(self):
                return 8

        self.assertEqual(Host().go(), 8)
        self.assertEqual(history.calls, [("perform", "Do Work", True)])


class ProjectNavigationToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.add_subplot(111)
        self.axes.plot([0, 1], [0, 1])
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.history = _RecordingHistory()
        self.host = _ExportHost()
        self.toolbar = ProjectNavigationToolbar(
            self.canvas,
            self.host,
            self.history,
        )

    def tearDown(self):
        self.toolbar.deleteLater()
        self.host.deleteLater()
        self.canvas.deleteLater()
        self.app.processEvents()

    def test_home_back_and_forward_use_scan_all_history(self):
        cases = (
            ("home", "Reset Figure View"),
            ("back", "Back Figure View"),
            ("forward", "Forward Figure View"),
        )
        for method_name, text in cases:
            with self.subTest(method=method_name):
                self.history.calls.clear()
                with mock.patch.object(
                    NavigationToolbar,
                    method_name,
                    return_value=method_name,
                ):
                    result = getattr(self.toolbar, method_name)()
                self.assertEqual(result, method_name)
                self.assertEqual(
                    self.history.calls,
                    [("perform", text, True)],
                )

    def test_save_figure_emits_host_export_request(self):
        received = []
        self.host.exportRequested.connect(received.append)
        self.toolbar.save_figure()
        self.assertEqual(received, [self.host])

    def test_apply_theme_icons_rebuilds_named_actions(self):
        action = QAction("Home", self.toolbar)
        self.toolbar._actions = {"home": action}
        icon = QIcon()
        with mock.patch.object(self.toolbar, "_icon", return_value=icon) as make_icon:
            self.toolbar.apply_theme_icons(object(), object())
        make_icon.assert_called_with("home.png")
        self.assertEqual(action.icon().cacheKey(), icon.cacheKey())

    def test_apply_theme_icons_returns_when_actions_are_missing(self):
        self.toolbar._actions = {}
        self.toolbar.apply_theme_icons(None, None)
        self.toolbar._actions = None
        self.toolbar.apply_theme_icons(None, None)

    def test_press_pan_commits_release_and_cancels_when_inactive(self):
        event = object()

        def start_pan(toolbar, _event):
            toolbar._pan_info = object()
            return "started"

        with mock.patch.object(NavigationToolbar, "press_pan", start_pan):
            self.assertEqual(self.toolbar.press_pan(event), "started")
        self.assertIn(("begin", "Pan Figure View"), self.history.calls)

        def finish_pan(toolbar, _event):
            toolbar._pan_info = None
            return "finished"

        with mock.patch.object(NavigationToolbar, "release_pan", finish_pan):
            self.assertEqual(self.toolbar.release_pan(event), "finished")
        self.assertIn(("end",), self.history.calls)

        self.history.calls.clear()

        def ignore_pan(toolbar, _event):
            toolbar._pan_info = None
            return None

        with mock.patch.object(NavigationToolbar, "press_pan", ignore_pan):
            self.toolbar.press_pan(event)
        self.assertIn(("cancel",), self.history.calls)

    def test_pan_zoom_history_is_not_a_second_component_state_store(self):
        self.assertFalse(hasattr(self.toolbar, "current_component_id"))
        event = object()

        def start_pan(toolbar, _event):
            toolbar._pan_info = object()
            return "started"

        with mock.patch.object(NavigationToolbar, "press_pan", start_pan):
            self.toolbar.press_pan(event)
        self.assertIn(("begin", "Pan Figure View"), self.history.calls)
        self.assertNotIn("apply_state", [call[0] for call in self.history.calls])

    def test_press_zoom_commits_release_and_cancels_when_inactive(self):
        event = object()

        def start_zoom(toolbar, _event):
            toolbar._zoom_info = object()
            return "started"

        with mock.patch.object(NavigationToolbar, "press_zoom", start_zoom):
            self.assertEqual(self.toolbar.press_zoom(event), "started")
        self.assertIn(("begin", "Zoom Figure View"), self.history.calls)

        def finish_zoom(toolbar, _event):
            toolbar._zoom_info = None
            return "finished"

        with mock.patch.object(NavigationToolbar, "release_zoom", finish_zoom):
            self.assertEqual(self.toolbar.release_zoom(event), "finished")
        self.assertIn(("end",), self.history.calls)

        self.history.calls.clear()

        def ignore_zoom(toolbar, _event):
            toolbar._zoom_info = None
            return None

        with mock.patch.object(NavigationToolbar, "press_zoom", ignore_zoom):
            self.toolbar.press_zoom(event)
        self.assertIn(("cancel",), self.history.calls)

    def test_pan_and_zoom_exceptions_cancel_started_interactions(self):
        event = object()
        with mock.patch.object(
            NavigationToolbar,
            "press_pan",
            side_effect=RuntimeError("pan failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pan failed"):
                self.toolbar.press_pan(event)
        self.assertIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        self.toolbar._pan_info = object()
        with mock.patch.object(
            NavigationToolbar,
            "release_pan",
            side_effect=RuntimeError("release pan failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "release pan failed"):
                self.toolbar.release_pan(event)
        self.assertIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        with mock.patch.object(
            NavigationToolbar,
            "press_zoom",
            side_effect=RuntimeError("zoom failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "zoom failed"):
                self.toolbar.press_zoom(event)
        self.assertIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        self.toolbar._zoom_info = object()
        with mock.patch.object(
            NavigationToolbar,
            "release_zoom",
            side_effect=RuntimeError("release zoom failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "release zoom failed"):
                self.toolbar.release_zoom(event)
        self.assertIn(("cancel",), self.history.calls)

    def test_pan_exception_does_not_cancel_when_begin_was_rejected(self):
        self.history.started = False
        with mock.patch.object(
            NavigationToolbar,
            "press_pan",
            side_effect=RuntimeError("ignored"),
        ):
            with self.assertRaisesRegex(RuntimeError, "ignored"):
                self.toolbar.press_pan(object())
        self.assertNotIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        with mock.patch.object(
            NavigationToolbar,
            "press_zoom",
            side_effect=RuntimeError("ignored zoom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "ignored zoom"):
                self.toolbar.press_zoom(object())
        self.assertNotIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        self.history.started = True
        self.toolbar._pan_info = None
        with mock.patch.object(
            NavigationToolbar,
            "release_pan",
            side_effect=RuntimeError("inactive pan"),
        ):
            with self.assertRaisesRegex(RuntimeError, "inactive pan"):
                self.toolbar.release_pan(object())
        self.assertNotIn(("cancel",), self.history.calls)

        self.history.calls.clear()
        self.toolbar._zoom_info = None
        with mock.patch.object(
            NavigationToolbar,
            "release_zoom",
            side_effect=RuntimeError("inactive zoom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "inactive zoom"):
                self.toolbar.release_zoom(object())
        self.assertNotIn(("cancel",), self.history.calls)

    def _parameter_dialog(self, buttons):
        dialog = QDialog(self.toolbar)
        box = QDialogButtonBox(buttons)
        layout = QVBoxLayout(dialog)
        layout.addWidget(box)
        dialog.bbox = box
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        return dialog

    def test_edit_parameters_apply_ok_and_cancel_bind_history_once(self):
        dialog = self._parameter_dialog(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )

        def open_dialog(toolbar):
            toolbar._fedit_dialog = dialog
            return "opened"

        with mock.patch.object(NavigationToolbar, "edit_parameters", open_dialog):
            self.assertEqual(self.toolbar.edit_parameters(), "opened")
            self.assertEqual(self.toolbar.edit_parameters(), "opened")

        apply_button = dialog.bbox.button(QDialogButtonBox.StandardButton.Apply)
        ok_button = dialog.bbox.button(QDialogButtonBox.StandardButton.Ok)
        apply_button.pressed.emit()
        apply_button.clicked.emit()
        ok_button.pressed.emit()
        dialog.accepted.emit()
        dialog.rejected.emit()
        self.app.processEvents()
        self.assertEqual(
            self.history.calls.count(("begin", "Customize Figure")),
            2,
        )
        self.assertEqual(self.history.calls.count(("end",)), 2)
        self.assertEqual(self.history.calls.count(("cancel",)), 1)
        dialog.deleteLater()

    def test_edit_parameters_without_dialog_or_buttons_is_a_no_op(self):
        with mock.patch.object(
            NavigationToolbar,
            "edit_parameters",
            return_value="plain",
        ):
            self.assertEqual(self.toolbar.edit_parameters(), "plain")
        self.assertEqual(self.history.calls, [])

        dialog = self._parameter_dialog(QDialogButtonBox.StandardButton.Close)

        def open_dialog(toolbar):
            toolbar._fedit_dialog = dialog
            return "opened"

        with mock.patch.object(NavigationToolbar, "edit_parameters", open_dialog):
            self.assertEqual(self.toolbar.edit_parameters(), "opened")
        self.assertEqual(self.history.calls, [])
        dialog.deleteLater()


class CrossProjectToolbarHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.first = self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ToolbarOne",
        )
        create_regular_axes(self.first)
        self.second = self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="ToolbarTwo",
        )
        create_regular_axes(self.second)
        self.first_stack = self.window.repository.undo_stack(self.first.project_id)
        self.second_stack = self.window.repository.undo_stack(self.second.project_id)
        self.first_stack.clear()
        self.second_stack.clear()

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    def test_home_and_pan_history_stay_on_the_owning_project(self):
        first_axes = self.first.current_axes
        self.assertTrue(
            self.first.figure_history.begin_interaction("Pan Figure View")
        )
        first_axes.set_xlim(2.0, 8.0)
        self.first.figure_history.end_interaction()
        self.app.processEvents()
        self.assertGreaterEqual(self.first_stack.count(), 1)
        self.assertEqual(self.second_stack.count(), 0)

        self.first.navigation_toolbar.home()
        self.app.processEvents()
        self.assertEqual(self.second_stack.count(), 0)

        event = SimpleNamespace(inaxes=first_axes, button=1, x=10, y=10)
        with mock.patch.object(
            NavigationToolbar,
            "press_pan",
            lambda toolbar, _event: setattr(toolbar, "_pan_info", object()) or "ok",
        ):
            self.first.navigation_toolbar.press_pan(event)
        first_axes.set_xlim(3.0, 9.0)
        with mock.patch.object(
            NavigationToolbar,
            "release_pan",
            lambda toolbar, _event: setattr(toolbar, "_pan_info", None) or "ok",
        ):
            self.first.navigation_toolbar.release_pan(event)
        self.app.processEvents()
        self.assertGreaterEqual(self.first_stack.count(), 1)
        self.assertEqual(self.second_stack.count(), 0)
        first_count = self.first_stack.count()
        self.first_stack.undo()
        self.assertEqual(self.second_stack.count(), 0)
        self.assertEqual(self.first_stack.count(), first_count)
        self.assertNotEqual(tuple(first_axes.get_xlim()), (3.0, 9.0))


if __name__ == "__main__":
    unittest.main()
