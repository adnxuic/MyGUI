import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from mygui.widgets.left_column.py_left_column import PyLeftColumn
from mygui.widgets.left_column.py_setting_dialog import PySettingDialog
from mygui.resources import icon_path
from mygui.widgets.theme import CONTROL_SIZES
from mygui.widgets.title_bar.py_title_menu import (
    SelectorChartMenuBar,
    SelectorElementMenuBar,
    SelectorLayoutMenuBar,
    SelectorStyleMenuBar,
)
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import PyStyleDialog
from mygui.widgets.title_bar.titlebar_dialog.axes_layout_input import (
    axes_layout_presets,
)
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyInAxesDialog,
    PyTextDialog,
    element_action_specs,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary


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
            self.assertEqual([len(bar.action_dict) for bar in bars], [30, 7, 9, 8])
            self.assertEqual(
                next(iter(bars[0].action_dict)),
                "Apply Template",
            )
            layout_bar = bars[1]
            presets = axes_layout_presets()
            self.assertEqual(
                tuple(layout_bar.action_dict),
                tuple(preset.label for preset in presets),
            )
            self.assertEqual(
                tuple(preset.icon for preset in presets),
                (
                    "single.svg",
                    "1_2.svg",
                    "2_1.svg",
                    "2_2.svg",
                    "3_3.svg",
                    "primary_right_y_icon.svg",
                    "main_plot_residual.svg",
                ),
            )
            self.assertEqual(
                tuple(action.text() for action in layout_bar.action_dict.values()),
                (
                    "Single",
                    "Horizontal",
                    "Vertical",
                    "2 × 2",
                    "3 × 3",
                    "Dual Y",
                    "Main + Residual",
                ),
            )
            self.assertTrue(
                all(
                    not layout_bar.action_dict[preset.label].icon().isNull()
                    for preset in presets
                )
            )
            self.assertFalse(
                Path("pictures/icons/layout_images/1_1.svg").exists()
            )
            for action in layout_bar.action_dict.values():
                button = layout_bar.toolbar.widgetForAction(action)
                self.assertEqual(button.objectName(), "layout_template_button")
                self.assertEqual(
                    (button.minimumWidth(), button.maximumWidth()),
                    (112, 112),
                )
                self.assertEqual(
                    (button.minimumHeight(), button.maximumHeight()),
                    (60, 60),
                )
                bounds = QRegion(
                    action.icon().pixmap(40, 40).mask()
                ).boundingRect()
                self.assertEqual(max(bounds.width(), bounds.height()), 34)
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

    def test_layout_gallery_buttons_remain_uniform_after_qss_polish(self):
        from main import MainWindow

        host = MainWindow()
        host.resize(1280, 720)
        host.showNormal()
        host.title_bar.stacklayout_bottom.setCurrentIndex(1)
        self.app.processEvents()
        self.app.processEvents()
        bar = host.title_bar.selector_layout_bar
        buttons = [
            bar.toolbar.widgetForAction(action)
            for action in bar.action_dict.values()
        ]
        try:
            self.assertTrue(all(button.isVisible() for button in buttons))
            self.assertEqual(
                {(button.width(), button.height()) for button in buttons},
                {(112, 60)},
            )
            self.assertEqual({button.geometry().top() for button in buttons}, {4})
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

    def test_layout_action_passes_the_semantic_preset_key(self):
        figure_window = Mock()
        figure_window.current_canva = None
        figure_window.color_library = ColorLibrary()
        host = QMainWindow()
        bar = SelectorLayoutMenuBar(figure_window=figure_window)
        host.setCentralWidget(bar)
        try:
            with patch(
                "mygui.widgets.title_bar.py_title_menu.PyLayoutDialog"
            ) as dialog_type:
                bar.action_dict["Horizontal Comparison"].trigger()

            dialog_type.assert_called_once_with(
                dialog_name="Horizontal Comparison",
                figure_window=figure_window,
                preset_key="horizontal_compare",
                parent=host,
            )
            dialog_type.return_value.exec.assert_called_once_with()
            dialog_type.return_value.deleteLater.assert_called_once_with()
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
                icon_path("element_images/in_axes.svg"),
            )
            with patch.object(PyInAxesDialog, "exec", return_value=0) as execute:
                action.trigger()
                action.trigger()
            self.assertEqual(execute.call_count, 2)
            self.assertIsNone(action.dialog)
        finally:
            host.close()
            self.app.processEvents()

    def test_reference_guide_actions_use_distinct_bundled_icons(self):
        line = element_action_specs["Add Reference Line"]
        band = element_action_specs["Add Reference Band"]
        self.assertEqual(
            line.icon_path,
            icon_path("element_images/reference_line.svg"),
        )
        self.assertEqual(
            band.icon_path,
            icon_path("element_images/reference_band.svg"),
        )
        self.assertNotEqual(line.icon_path, band.icon_path)

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

    def test_apply_template_action_icon_matches_theme_contrast(self):
        from mygui.application_theme import (
            AppearancePreferences,
            Density,
            FakeStyleHints,
            ThemeMode,
            ThemeService,
        )
        from mygui.application_theme.runtime import (
            reset_theme_runtime_for_tests,
        )
        from mygui.widgets.title_bar.py_title_menu import SelectorStyleMenuBar

        reset_theme_runtime_for_tests()
        hints = FakeStyleHints(Qt.ColorScheme.Light)
        theme = ThemeService(self.app, style_hints=hints)
        try:
            theme.apply_committed(
                AppearancePreferences(
                    mode=ThemeMode.LIGHT,
                    font_pt=9,
                    density=Density.STANDARD,
                )
            )
            bar = SelectorStyleMenuBar()
            apply_action = bar.action_dict["Apply Template"]
            image_light = apply_action.icon().pixmap(24, 24).toImage()
            lightness_values_light = [
                image_light.pixelColor(x, y).lightness()
                for y in range(image_light.height())
                for x in range(image_light.width())
                if image_light.pixelColor(x, y).alpha() > 0
            ]
            self.assertTrue(lightness_values_light)
            avg_lightness_light = sum(lightness_values_light) / len(lightness_values_light)
            self.assertLess(avg_lightness_light, 100)

            theme.apply_committed(
                AppearancePreferences(
                    mode=ThemeMode.DARK,
                    font_pt=9,
                    density=Density.STANDARD,
                )
            )
            self.app.processEvents()
            image_dark = apply_action.icon().pixmap(24, 24).toImage()
            lightness_values_dark = [
                image_dark.pixelColor(x, y).lightness()
                for y in range(image_dark.height())
                for x in range(image_dark.width())
                if image_dark.pixelColor(x, y).alpha() > 0
            ]
            self.assertTrue(lightness_values_dark)
            avg_lightness_dark = sum(lightness_values_dark) / len(lightness_values_dark)
            self.assertGreater(avg_lightness_dark, 200)
        finally:
            theme.shutdown()
            reset_theme_runtime_for_tests()


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
