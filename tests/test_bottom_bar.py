import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QFrame, QStackedLayout, QWidget
from code import tex_config
from code import status_messages
from code.database import matlab_adapter
from code.widgets import qss_func
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar
from code.widgets.bottom_bar.py_message_bar import PyMessageBar
from code.widgets.bottom_bar.py_state_bar import FeatureIndicator, PyStateBar
from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.right_column.py_right_column import PyRightColumn
from code.widgets.theme import COLORS, CONTROL_SIZES
from code.widgets.title_bar.py_title_button import ChangeButton, PullDownButton


class ThemeQssTests(unittest.TestCase):
    @staticmethod
    def _relative_luminance(hex_color):
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))

    @classmethod
    def _contrast_ratio(cls, first, second):
        first_luminance = cls._relative_luminance(first)
        second_luminance = cls._relative_luminance(second)
        lighter = max(first_luminance, second_luminance)
        darker = min(first_luminance, second_luminance)
        return (lighter + 0.05) / (darker + 0.05)

    def _load_qss(self, source):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "test.qss")
            path.write_text(source, encoding="utf-8")
            return qss_func.qss_loader(path)

    def test_loader_replaces_shared_tokens_with_single_argument(self):
        rendered = self._load_qss(
            "QWidget { color: {{COLOR_ERROR}}; min-height: {{SIZE_BOTTOM_BAR}}px; }"
        )

        self.assertIn(COLORS["error"], rendered)
        self.assertIn(f'{CONTROL_SIZES["bottom_bar"]}px', rendered)
        self.assertNotIn("{{", rendered)

    def test_loader_rejects_unknown_token(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_COLOR"):
            self._load_qss("QWidget { color: {{UNKNOWN_COLOR}}; }")

    def test_loader_rejects_malformed_token(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            self._load_qss("QWidget { color: {{color_error}}; }")

    def test_status_text_colors_meet_wcag_contrast(self):
        background = COLORS["status_background"]
        for semantic_color in (
            "text_on_dark",
            "text_muted_on_dark",
            "success",
            "warning",
            "error",
        ):
            with self.subTest(color=semantic_color):
                self.assertGreaterEqual(
                    self._contrast_ratio(COLORS[semantic_color], background),
                    4.5,
                )


class MatlabEnabledStateTests(unittest.TestCase):
    def tearDown(self):
        matlab_adapter.clear_matlab_state_listeners()
        matlab_adapter.set_matlab_enabled(False, notify=False)

    def test_set_and_query_state(self):
        matlab_adapter.set_matlab_enabled(False, notify=False)
        self.assertFalse(matlab_adapter.is_matlab_enabled())
        matlab_adapter.set_matlab_enabled(True)
        self.assertTrue(matlab_adapter.is_matlab_enabled())

    def test_listener_notified_only_on_change(self):
        events = []
        matlab_adapter.set_matlab_enabled(False, notify=False)
        matlab_adapter.register_matlab_state_listener(events.append)

        matlab_adapter.set_matlab_enabled(True)
        matlab_adapter.set_matlab_enabled(True)  # no change -> no notify
        matlab_adapter.set_matlab_enabled(False)

        self.assertEqual(events, [True, False])

    def test_failing_listener_is_pruned(self):
        matlab_adapter.set_matlab_enabled(False, notify=False)

        def boom(_enabled):
            raise RuntimeError("dead listener")

        matlab_adapter.register_matlab_state_listener(boom)
        matlab_adapter.set_matlab_enabled(True)
        # A pruned listener must not raise on the next notification.
        matlab_adapter.set_matlab_enabled(False)


class StateBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        matlab_adapter.clear_matlab_state_listeners()
        matlab_adapter.set_matlab_enabled(False, notify=False)
        tex_config.clear_tex_state_listeners()
        tex_config.set_tex_enabled(False, notify=False)

    def _make_state_bar(self):
        indicators = (
            FeatureIndicator(
                name="matlab",
                label="MATLAB",
                is_enabled=matlab_adapter.is_matlab_enabled,
                register_listener=matlab_adapter.register_matlab_state_listener,
                unregister_listener=matlab_adapter.unregister_matlab_state_listener,
            ),
            FeatureIndicator(
                name="tex",
                label="TeX",
                is_enabled=tex_config.is_tex_enabled,
                register_listener=tex_config.register_tex_state_listener,
                unregister_listener=tex_config.unregister_tex_state_listener,
            ),
        )
        return PyStateBar(indicators)

    def test_initial_state_reflects_getters(self):
        matlab_adapter.set_matlab_enabled(True, notify=False)
        tex_config.set_tex_enabled(False, notify=False)
        bar = self._make_state_bar()
        try:
            self.assertEqual(bar._labels["matlab"].property("state"), "on")
            self.assertEqual(bar._labels["tex"].property("state"), "off")
            self.assertEqual(bar._labels["matlab"].text(), "\u25cf MATLAB On")
            self.assertEqual(bar._labels["tex"].text(), "\u25cb TeX Off")
            self.assertEqual(bar._labels["tex"].accessibleName(), "TeX: Off")
        finally:
            bar.cleanup()

    def test_listener_updates_indicator(self):
        matlab_adapter.set_matlab_enabled(False, notify=False)
        tex_config.set_tex_enabled(False, notify=False)
        bar = self._make_state_bar()
        try:
            matlab_adapter.set_matlab_enabled(True)
            tex_config.set_tex_enabled(True)
            self.assertEqual(bar._labels["matlab"].property("state"), "on")
            self.assertEqual(bar._labels["tex"].property("state"), "on")
        finally:
            bar.cleanup()

    def test_cleanup_unregisters_listeners(self):
        bar = self._make_state_bar()
        bar.cleanup()
        # No listeners remain after cleanup.
        self.assertEqual(matlab_adapter._MATLAB_STATE_LISTENERS, [])
        self.assertEqual(tex_config._TEX_STATE_LISTENERS, [])


class BottomBarMessageFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        status_messages.clear_status_handler()
        matlab_adapter.clear_matlab_state_listeners()
        matlab_adapter.set_matlab_enabled(False, notify=False)
        tex_config.clear_tex_state_listeners()
        tex_config.set_tex_enabled(False, notify=False)

    def test_status_messages_reach_message_bar(self):
        bottom_bar = PyBottomBar()
        try:
            status_messages.set_status_handler(bottom_bar.show_message)
            status_messages.show_error("boom")
            self.assertEqual(bottom_bar.message_bar.message_label.text(), "boom")
            self.assertEqual(bottom_bar.message_bar.property("level"), "error")
            status_messages.show_success("ok")
            self.assertEqual(bottom_bar.message_bar.message_label.text(), "ok")
            self.assertEqual(bottom_bar.message_bar.property("level"), "success")
            status_messages.show_warning("careful")
            self.assertEqual(bottom_bar.message_bar.message_label.text(), "careful")
            self.assertEqual(bottom_bar.message_bar.property("level"), "warning")
            self.assertEqual(bottom_bar.message_bar.message_label.styleSheet(), "")
        finally:
            bottom_bar.deleteLater()

    def test_unknown_message_level_falls_back_to_info(self):
        message_bar = PyMessageBar()
        try:
            message_bar.show_message("hello", "unexpected")
            self.assertEqual(message_bar.property("level"), "info")
            self.assertEqual(message_bar.message_label.property("level"), "info")
        finally:
            message_bar.deleteLater()


class IconButtonAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_activity_rail_icon_buttons_have_names_and_tooltips(self):
        table = QFrame()
        left_column = PyLeftColumn()

        stack = QStackedLayout()
        for _ in range(3):
            stack.addWidget(QWidget())
        right_column = PyRightColumn(stack)

        try:
            for button in (
                left_column.table_button,
                left_column.components_button,
                left_column.setting_button,
                right_column.tex_button,
                right_column.matlab_button,
            ):
                self.assertTrue(button.accessibleName())
                self.assertTrue(button.toolTip())
        finally:
            left_column.deleteLater()
            right_column.deleteLater()

    def test_title_icon_buttons_have_names_and_tooltips(self):
        for button in (ChangeButton("change_button"), PullDownButton()):
            try:
                self.assertTrue(button.accessibleName())
                self.assertTrue(button.toolTip())
            finally:
                button.deleteLater()


if __name__ == "__main__":
    unittest.main()
