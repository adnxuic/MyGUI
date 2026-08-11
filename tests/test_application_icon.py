import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mygui.resources import resource_path
from main import (
    APP_ICON_PATH,
    WINDOWS_APP_USER_MODEL_ID,
    MainWindow,
    configure_application_icon,
    configure_windows_taskbar_identity,
)


class ApplicationIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous_icon = self.app.windowIcon()
        self.app.setWindowIcon(QIcon())

    def tearDown(self):
        self.app.setWindowIcon(self.previous_icon)

    def test_configured_icon_exists_and_loads(self):
        self.assertEqual(
            APP_ICON_PATH,
            resource_path("pictures/icons/app_icon.ico"),
        )
        self.assertTrue(APP_ICON_PATH.is_file())

        icon = configure_application_icon(self.app)

        self.assertFalse(icon.isNull())
        self.assertFalse(self.app.windowIcon().isNull())

    def test_main_window_has_explicit_application_icon(self):
        window = MainWindow()
        try:
            self.assertFalse(window.windowIcon().isNull())
        finally:
            window.close_without_prompt()
            window.deleteLater()
            self.app.processEvents()

    @patch("main.ctypes")
    @patch("main.sys.platform", "win32")
    def test_windows_taskbar_identity_is_configured_before_startup(
        self,
        ctypes_mock,
    ):
        setter = (
            ctypes_mock.windll.shell32
            .SetCurrentProcessExplicitAppUserModelID
        )
        setter.return_value = 0

        configured = configure_windows_taskbar_identity()

        self.assertTrue(configured)
        setter.assert_called_once_with(WINDOWS_APP_USER_MODEL_ID)

    @patch("main.sys.platform", "linux")
    def test_taskbar_identity_is_ignored_outside_windows(self):
        self.assertFalse(configure_windows_taskbar_identity())


if __name__ == "__main__":
    unittest.main()
