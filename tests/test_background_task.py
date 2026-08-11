import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from mygui.widgets.fig_control_window.background_task import (
    cancel_background_tasks,
    drain_background_tasks,
    start_background_task,
)


class BackgroundTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        cancel_background_tasks()
        self.assertTrue(drain_background_tasks(2000))
        self.app.processEvents()

    def _wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(predicate())

    def test_success_callback_runs_on_ui_thread(self):
        owner = QWidget()
        callback = []
        ui_thread_id = threading.get_ident()
        try:
            start_background_task(
                owner,
                lambda: 42,
                lambda result: callback.append((result, threading.get_ident())),
                self.fail,
            )
            self._wait_until(lambda: bool(callback))
            self.assertEqual(callback, [(42, ui_thread_id)])
        finally:
            owner.deleteLater()

    def test_failure_callback_runs_on_ui_thread(self):
        owner = QWidget()
        callback = []
        ui_thread_id = threading.get_ident()

        def fail():
            raise RuntimeError("expected failure")

        try:
            start_background_task(
                owner,
                fail,
                self.fail,
                lambda message: callback.append((message, threading.get_ident())),
            )
            self._wait_until(lambda: bool(callback))
            self.assertEqual(callback, [("expected failure", ui_thread_id)])
        finally:
            owner.deleteLater()

    def test_cancellation_suppresses_callback(self):
        owner = QWidget()
        release = threading.Event()
        callback = []
        try:
            start_background_task(
                owner,
                lambda: (release.wait(1), "done")[1],
                callback.append,
                callback.append,
            )
            self.assertEqual(cancel_background_tasks(owner), 1)
            release.set()
            self._wait_until(lambda: drain_background_tasks(50))
            self.app.processEvents()
            self.assertEqual(callback, [])
        finally:
            owner.deleteLater()

    def test_sequential_tasks_reuse_bridge_without_lifecycle_race(self):
        owner = QWidget()
        callback = []
        try:
            for value in range(20):
                start_background_task(
                    owner,
                    lambda current=value: current,
                    callback.append,
                    self.fail,
                )
                self._wait_until(lambda: len(callback) == value + 1)
            self.assertEqual(callback, list(range(20)))
        finally:
            owner.deleteLater()


if __name__ == "__main__":
    unittest.main()
