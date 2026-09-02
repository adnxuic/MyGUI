import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from mygui.widgets.left_column.py_left_column import PyLeftColumn
from mygui.widgets.left_column.py_setting_dialog import PySettingDialog
from mygui.application_theme import current_density_metrics
from mygui.widgets.title_bar.style_gallery import (
    HIDDEN_STYLE_NAMES,
    LAYOUT_BUTTON_MIN_WIDTH,
    style_toolbar_label,
)
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
from mygui.resources import icon_path
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
            self.assertEqual([len(bar.action_dict) for bar in bars], [27, 7, 9, 8])
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
                self.assertEqual(button.minimumWidth(), LAYOUT_BUTTON_MIN_WIDTH)
                gallery_height = current_density_metrics().gallery
                self.assertEqual(button.maximumHeight(), gallery_height)
                self.assertEqual(action.toolTip(), action._accessible_name)
                self.assertEqual(button.accessibleName(), action.toolTip())
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
            gallery_height = current_density_metrics().gallery
            heights = {button.height() for button in buttons}
            self.assertTrue(
                all(button.width() >= LAYOUT_BUTTON_MIN_WIDTH for button in buttons)
            )
            self.assertTrue(
                all(
                    button.minimumWidth() >= LAYOUT_BUTTON_MIN_WIDTH
                    for button in buttons
                )
            )
            self.assertTrue(all(h <= gallery_height for h in heights))
            self.assertTrue(all(h >= gallery_height - 12 for h in heights))
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
            top_row_height = current_density_metrics().command
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

    def test_style_gallery_hides_internal_styles_and_uses_short_labels(self):
        from PySide6.QtGui import QFontMetrics

        bar = SelectorStyleMenuBar()
        try:
            for name in HIDDEN_STYLE_NAMES:
                self.assertNotIn(name, bar.action_dict)
                self.assertIn(name, bar.available_styles_dict)
            dark_palette = bar.action_dict["seaborn-v0_8-dark-palette"]
            self.assertEqual(dark_palette.text(), "Dark Palette")
            self.assertEqual(dark_palette.toolTip(), "seaborn-v0_8-dark-palette")
            metrics = QFontMetrics(bar.font())
            for name, action in bar.action_dict.items():
                if name == "Apply Template":
                    continue
                button = bar.toolbar.widgetForAction(action)
                self.assertEqual(action.text(), style_toolbar_label(name))
                self.assertEqual(action.toolTip(), name)
                self.assertEqual(button.accessibleName(), name)
                self.assertLessEqual(
                    metrics.horizontalAdvance(action.text()),
                    max(button.sizeHint().width(), 1),
                )
        finally:
            bar.deleteLater()

    def test_hidden_matplotlib_styles_remain_restorable(self):
        from mygui.figuremodify.components.controllers._helpers import (
            _figure_style,
        )
        from mygui.figuremodify.matplotlib_adapter import available_style_names

        names = set(available_style_names())
        for style_name in HIDDEN_STYLE_NAMES:
            self.assertIn(style_name, names)
            self.assertEqual(_figure_style(style_name), style_name)

    def test_gallery_density_bands_keep_compact_heights_and_icons(self):
        from mygui.application_theme import Density
        from mygui.application_theme.metrics import DENSITY_BANDS

        self.assertEqual(
            tuple(DENSITY_BANDS[item].gallery for item in Density),
            (54, 60, 72),
        )
        self.assertEqual(
            tuple(DENSITY_BANDS[item].gallery_icon for item in Density),
            (28, 32, 36),
        )


class CreationDialogCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_chart_and_element_dialogs_construct_and_keep_session_errors(self):
        from main import MainWindow
        from mygui import status_messages
        from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
            PyContourDialog,
            PyCurveDialog,
            PyFitDialog,
            PyHeatmapDialog,
            PyInterpolationDialog,
            PyPlotDialog,
            PyPseudocolorDialog,
            PyScatterDialog,
            _show_batch_creation_result,
            _show_creation_result,
        )
        from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
            PyAnnotationDialog,
            PyColorbarDialog,
            PyReferenceBandDialog,
            PyReferenceLineDialog,
            PyReferenceMarksDialog,
            PySecondaryAxisDialog,
        )
        from tests.axes_helpers import create_regular_axes

        window = MainWindow()
        window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="DialogCoverage",
        )
        canvas = window.figure_window.current_canva
        create_regular_axes(canvas)
        dialogs = []
        try:
            dialogs = [
                PyAnnotationDialog("Annotation", window.figure_window),
                PyColorbarDialog("Colorbar", window.figure_window),
                PyInAxesDialog("in_axes", window.figure_window),
                PySecondaryAxisDialog("Secondary Axis", window.figure_window),
                PyReferenceLineDialog("Reference Line", window.figure_window),
                PyReferenceBandDialog("Reference Band", window.figure_window),
                PyTextDialog("Text", window.figure_window),
                PyPlotDialog("Plot", window.figure_window),
                PyCurveDialog("Curve", window.figure_window),
                PyPseudocolorDialog("Pseudocolor", window.figure_window),
                PyHeatmapDialog("Heatmap", window.figure_window),
                PyContourDialog("Contour", window.figure_window),
            ]
            for dialog in dialogs:
                dialog.reject()

            shown = []
            bare = MainWindow()
            try:
                bare.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="NoAxes",
                )
                missing_axes = [
                    PyAnnotationDialog("Annotation", bare.figure_window),
                    PyColorbarDialog("Colorbar", bare.figure_window),
                ]
                with patch.object(status_messages, "show_warning", shown.append):
                    for dialog in missing_axes:
                        dialog.accept()
                self.assertTrue(shown)
                for dialog in missing_axes:
                    dialog.close()
            finally:
                bare.close()
                self.app.processEvents()

            with patch.object(canvas, "add_annotation_from_input", side_effect=ValueError("boom")):
                with patch.object(status_messages, "show_error") as error:
                    dialog = PyAnnotationDialog("Annotation", window.figure_window)
                    dialog.accept()
                    dialog.close()
                error.assert_called_once()
                self.assertEqual(error.call_args[0][0], "boom")

            text = PyTextDialog("Text", window.figure_window)
            text.text_edit.setText("hello")
            text.accept()
            text.close()
            text.global_button.setChecked(True)
            text = PyTextDialog("Text", window.figure_window)
            text.global_button.setChecked(True)
            text.text_edit.setText("figure text")
            text.accept()
            text.close()

            annotation = PyAnnotationDialog("Annotation", window.figure_window)
            with patch.object(canvas, "add_annotation_from_input", return_value="ann"):
                annotation.accept()
            annotation.close()

            in_axes = PyInAxesDialog("in_axes", window.figure_window)
            with patch.object(canvas, "add_in_axes", return_value="inset"):
                in_axes.accept()
            in_axes.close()

            secondary = PySecondaryAxisDialog("Secondary Axis", window.figure_window)
            with patch.object(canvas, "add_secondary_axis", return_value="sec"):
                secondary.accept()
            secondary.close()

            line = PyReferenceLineDialog("Reference Line", window.figure_window)
            with patch.object(canvas, "add_reference_line", return_value="line"):
                line.accept()
            line.close()

            band = PyReferenceBandDialog("Reference Band", window.figure_window)
            with patch.object(canvas, "add_reference_band", return_value="band"):
                band.accept()
            band.close()

            plot = PyPlotDialog("Plot", window.figure_window)
            with patch.object(canvas, "add_plots", return_value=SimpleNamespace(
                component_ids=("p1",),
                excluded_counts=(0,),
            )):
                plot.accept()
            plot.close()

            curve = PyCurveDialog("Curve", window.figure_window)
            with patch.object(canvas, "add_curve", return_value="curve"):
                curve.accept()
            curve.close()

            from mygui.widgets.title_bar.titlebar_dialog.creation_dialog_support import (
                creation_defaults,
                palette_selection,
                settings_snapshot,
            )

            scatter = PyScatterDialog("Scatter", window.figure_window)
            with patch.object(canvas, "add_scatters", return_value=SimpleNamespace(
                component_ids=("s1", "s2"),
                excluded_counts=(1, 0),
            )):
                scatter.accept()
            scatter.reject()
            scatter.close()

            fit = PyFitDialog("Fit", window.figure_window)
            with patch(
                "mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"
            ), patch.object(canvas, "add_fit_curve", return_value="fit"):
                fit.accept()
            fit.reject()
            fit.close()

            interpolation = PyInterpolationDialog(
                "Interpolation", window.figure_window
            )
            with patch.object(
                canvas,
                "add_interpolate_curves",
                return_value=SimpleNamespace(
                    component_ids=("i1",),
                    excluded_counts=(0,),
                ),
            ):
                interpolation.accept()
            interpolation.reject()
            interpolation.close()

            for dialog_type, adder in (
                (PyPseudocolorDialog, "add_pseudocolor"),
                (PyHeatmapDialog, "add_heatmap"),
                (PyContourDialog, "add_contour"),
            ):
                field = dialog_type(dialog_type.DISPLAY_NAME, window.figure_window)
                with patch(
                    "mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"
                ), patch.object(
                    field.data_reference_input, "get_x_ref", return_value="x"
                ), patch.object(
                    field.data_reference_input, "get_y_ref", return_value="y"
                ), patch.object(
                    field.data_reference_input, "get_z_ref", return_value="z"
                ), patch.object(canvas, adder, return_value="field"):
                    field.accept()
                missing = dialog_type(dialog_type.DISPLAY_NAME, window.figure_window)
                with patch(
                    "mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"
                ) as warning:
                    missing.accept()
                    warning.assert_called()
                missing.reject()
                missing.close()

            marks = PyReferenceMarksDialog(
                "Reflection Positions", window.figure_window
            )
            with patch.object(
                canvas, "add_reference_marks", return_value="marks"
            ):
                marks.accept()
            marks.close()

            colorbar = PyColorbarDialog("Colorbar", window.figure_window)
            with patch.object(
                colorbar.input, "source_component_id", return_value="src"
            ), patch.object(canvas, "add_colorbar", return_value="cb"):
                colorbar.accept()
            colorbar.close()
            _show_creation_result("Plot", SimpleNamespace(excluded_count=0))
            _show_creation_result("Plot", SimpleNamespace(excluded_count=2))
            _show_batch_creation_result(
                "Plot",
                SimpleNamespace(component_ids=("a",), excluded_counts=(0,)),
            )
            _show_batch_creation_result(
                "Plot",
                SimpleNamespace(component_ids=("a", "b"), excluded_counts=(1, 0)),
            )
            self.assertIsNotNone(creation_defaults(window.figure_window))
            self.assertIsNotNone(palette_selection(window.figure_window))
            settings_snapshot(window.figure_window)
        finally:
            for dialog in dialogs:
                dialog.close()
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
