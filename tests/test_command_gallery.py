import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QDialog, QFrame, QMainWindow, QToolButton

from code.widgets.left_column.py_left_column import PyLeftColumn
from code.widgets.left_column.py_setting_dialog import PySettingDialog
from code.widgets.theme import CONTROL_SIZES
from code.widgets.title_bar.py_title_menu import (
    SelectorChartMenuBar,
    SelectorElementMenuBar,
    SelectorLayoutMenuBar,
    SelectorStyleMenuBar,
)
from code.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyStyleDialog
from code.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyInAxesDialog,
    PyTextDialog,
    element_action_specs,
)
from code.widgets.common_widget.min_widget.color_library import ColorLibrary


class CommandGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_galleries_create_actions_without_eager_dialogs(self):
        existing_dialogs = {id(widget) for widget in self.app.topLevelWidgets() if isinstance(widget, QDialog)}
        bars = [
            SelectorStyleMenuBar(),
            SelectorLayoutMenuBar(),
            SelectorChartMenuBar(),
            SelectorElementMenuBar(),
        ]
        try:
            self.assertEqual([len(bar.action_dict) for bar in bars], [29, 5, 5, 2])
            created_dialogs = {
                id(widget) for widget in self.app.topLevelWidgets() if isinstance(widget, QDialog)
            }
            self.assertEqual(created_dialogs, existing_dialogs)
            self.assertTrue(all(action.dialog is None for bar in bars for action in bar.action_dict.values()))
        finally:
            for bar in bars:
                bar.deleteLater()

    def test_style_dialog_is_parented_and_reused_on_first_trigger(self):
        host = QMainWindow()
        bar = SelectorStyleMenuBar()
        host.setCentralWidget(bar)
        host.show()
        self.app.processEvents()
        action = bar.action_dict["default"]

        try:
            with patch.object(PyStyleDialog, "exec", return_value=0) as execute:
                action.trigger()
                first_dialog = action.dialog
                action.trigger()

            self.assertIsNotNone(first_dialog)
            self.assertIs(action.dialog, first_dialog)
            self.assertIs(first_dialog.parentWidget(), host)
            self.assertEqual(execute.call_count, 2)
        finally:
            host.close()
            self.app.processEvents()

    def test_text_creation_dialog_is_rebuilt_for_each_trigger(self):
        host = QMainWindow()
        bar = SelectorElementMenuBar()
        host.setCentralWidget(bar)
        action = bar.action_dict["Text"]
        try:
            with patch.object(PyTextDialog, "exec", return_value=0) as execute:
                action.trigger()
                action.trigger()

            self.assertEqual(execute.call_count, 2)
            self.assertIsNone(action.dialog)
        finally:
            host.close()
            self.app.processEvents()

    def test_in_axes_action_has_explicit_icon_and_rebuilds_dialog(self):
        figure_window = Mock()
        figure_window.current_canva = None
        figure_window.color_library = ColorLibrary()
        host = QMainWindow()
        bar = SelectorElementMenuBar(figure_window=figure_window)
        host.setCentralWidget(bar)
        action = bar.action_dict["in_axes"]
        try:
            self.assertEqual(
                element_action_specs["in_axes"].icon_path,
                "pictures/icons/element_images/in_axes.svg",
            )
            with patch.object(PyInAxesDialog, "exec", return_value=0) as execute:
                action.trigger()
                action.trigger()
            self.assertEqual(execute.call_count, 2)
            self.assertIsNone(action.dialog)
        finally:
            host.close()
            self.app.processEvents()

    def test_narrow_gallery_uses_qtoolbar_overflow(self):
        from main import MainWindow

        host = MainWindow()
        host.resize(960, 600)
        host.showNormal()
        self.app.processEvents()
        self.app.processEvents()
        bar = host.title_bar.selector_style_bar
        try:
            extension = bar.overflow_button
            self.assertIsNotNone(extension)
            self.assertTrue(extension.isVisible())
            self.assertGreaterEqual(extension.width(), 32)
            self.assertLessEqual(
                extension.geometry().right(),
                bar.toolbar.rect().right(),
            )
        finally:
            host.close()
            self.app.processEvents()

    def test_gallery_action_frame_stays_above_bottom_separator(self):
        from main import MainWindow

        host = MainWindow()
        host.resize(1280, 720)
        host.showNormal()
        self.app.processEvents()
        self.app.processEvents()
        bar = host.title_bar.selector_style_bar
        button = bar.toolbar.widgetForAction(bar.action_dict["default"])
        try:
            self.assertIsNotNone(button)
            self.assertGreaterEqual(button.geometry().top(), 0)
            self.assertLess(
                button.geometry().bottom(),
                bar.toolbar.rect().bottom(),
            )
        finally:
            host.close()
            self.app.processEvents()

    def test_command_selection_fills_the_fixed_top_row(self):
        from main import MainWindow

        window = MainWindow()
        window.resize(1280, 720)
        window.showNormal()
        self.app.processEvents()
        self.app.processEvents()
        try:
            top_row_height = CONTROL_SIZES["command_row"]
            self.assertEqual(window.title_bar.selector_menu_bar.height(), top_row_height)
            self.assertEqual(window.title_bar.change_button.height(), top_row_height)
            self.assertEqual(
                window.title_bar.selector_menu_bar.style_button.height(),
                top_row_height,
            )
            self.assertEqual(
                window.title_bar.selector_style_bar.y(),
                top_row_height,
            )

            window.title_bar.change_button.setChecked(True)
            self.app.processEvents()
            menu_bar = window.title_bar.menu_bar
            separator = menu_bar.separator
            self.assertEqual(menu_bar.height(), top_row_height)
            self.assertEqual(menu_bar.file_button.height(), top_row_height)
            self.assertEqual(menu_bar.edit_button.height(), top_row_height)
            self.assertEqual(separator.height(), 28)
            self.assertLessEqual(
                abs(separator.geometry().center().y() - menu_bar.rect().center().y()),
                1,
            )

            icon_image = menu_bar.file_button.icon().pixmap(22, 22).toImage()
            icon_lightness = [
                icon_image.pixelColor(x, y).lightness()
                for y in range(icon_image.height())
                for x in range(icon_image.width())
                if icon_image.pixelColor(x, y).alpha() > 0
            ]
            self.assertTrue(icon_lightness)
            self.assertGreater(sum(icon_lightness) / len(icon_lightness), 200)
        finally:
            window.close()
            self.app.processEvents()


class LazySettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_dialog_is_lazy_parented_and_can_reset_layout(self):
        host = QMainWindow()
        left_column = PyLeftColumn()
        host.setCentralWidget(left_column)
        reset_layout = Mock()
        left_column.set_reset_layout_callback(reset_layout)
        self.assertIsNone(left_column.setting_dialog)

        try:
            with patch.object(PySettingDialog, "exec", return_value=0):
                left_column.show_setting_dialog()
            dialog = left_column.setting_dialog
            self.assertIsNotNone(dialog)
            self.assertIs(dialog.parentWidget(), host)
            dialog.reset_layout_button.click()
            reset_layout.assert_called_once_with()
        finally:
            host.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
