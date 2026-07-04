import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication
from code import tex_config
from code import status_messages
from code.database import matlab_adapter
from code.widgets.bottom_bar.py_bottom_bar import PyBottomBar
from code.widgets.bottom_bar.py_state_bar import FeatureIndicator, PyStateBar


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
            status_messages.show_success("ok")
            self.assertEqual(bottom_bar.message_bar.message_label.text(), "ok")
        finally:
            bottom_bar.deleteLater()


if __name__ == "__main__":
    unittest.main()
