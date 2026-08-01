import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QDialog, QObject, QSettings, Qt

from code.widgets.fig_control_window.figure_inspector import (
    AxesInspectorPanel,
    FigureInspectorPanel,
)
from code.widgets.left_column import ExplorerMode
from code.widgets.theme import CONTROL_SIZES
from code.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class GuiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _show(self, window, width=1280, height=720):
        window.resize(width, height)
        window.showNormal()
        self.app.processEvents()
        self.app.processEvents()

    def _close(self, window):
        window.close()
        window.deleteLater()
        self.app.processEvents()

    @staticmethod
    def _icon_lightness(button):
        image = button.icon().pixmap(24, 24).toImage()
        lightness = []
        for x in range(image.width()):
            for y in range(image.height()):
                color = image.pixelColor(x, y)
                if color.alpha() > 0:
                    lightness.append(color.lightness())
        return sum(lightness) / len(lightness)

    @staticmethod
    def _icon_opaque_colors(button):
        image = button.icon().pixmap(24, 24).toImage()
        return [
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 127
        ]

    def test_constructor_builds_native_single_shell_without_showing_it(self):
        existing_dialogs = sum(
            isinstance(widget, QDialog)
            for widget in self.app.topLevelWidgets()
        )
        window = MainWindow()
        try:
            self.assertFalse(window.isVisible())
            self.assertFalse(bool(window.windowFlags() & Qt.FramelessWindowHint))
            self.assertFalse(window.testAttribute(Qt.WA_TranslucentBackground))
            self.assertEqual(window.windowTitle(), "MyGUI")
            self.assertIs(window.title_bar.parentWidget(), window.central_widget)
            self.assertIs(window.bottom_bar.parentWidget(), window.central_widget)
            self.assertIs(window.workspace_splitter.parentWidget(), window.central_widget)
            self.assertEqual(
                sum(isinstance(widget, QDialog) for widget in self.app.topLevelWidgets()),
                existing_dialogs,
            )
            self.assertIsNone(window.title_bar.findChild(QObject, "minimize_button"))
            self.assertIsNone(window.title_bar.findChild(QObject, "close_button"))
        finally:
            self._close(window)

    def test_responsive_geometry_keeps_full_width_shell_and_visible_canvas(self):
        for width, height in (
            (960, 600),
            (1280, 720),
            (1366, 768),
            (1920, 1080),
            (2560, 1440),
        ):
            with self.subTest(size=(width, height)):
                window = MainWindow()
                self._show(window, width, height)
                try:
                    central_width = window.central_widget.width()
                    self.assertEqual(window.title_bar.width(), central_width)
                    self.assertEqual(window.bottom_bar.width(), central_width)
                    self.assertEqual(window.title_bar.y(), 0)
                    self.assertEqual(
                        window.workspace_splitter.y(), window.title_bar.height()
                    )
                    self.assertEqual(
                        window.bottom_bar.y(),
                        window.workspace_splitter.y() + window.workspace_splitter.height(),
                    )
                    self.assertGreaterEqual(window.figure_window.width(), 400)
                    self.assertGreater(window.workspace_splitter.height(), 0)
                    self.assertLessEqual(
                        window.figure_window.geometry().right(),
                        window.workspace_splitter.rect().right(),
                    )
                finally:
                    self._close(window)

    def test_switching_optional_pages_does_not_resize_the_shell(self):
        window = MainWindow()
        self._show(window)
        try:
            original = (window.size(), window.workspace_splitter.geometry())
            window.right_column.tex_button.setChecked(True)
            self.app.processEvents()
            self.assertEqual((window.size(), window.workspace_splitter.geometry()), original)
            window.right_column.matlab_button.setChecked(True)
            self.app.processEvents()
            self.assertEqual((window.size(), window.workspace_splitter.geometry()), original)
            self.assertTrue(all(area.widgetResizable() for area in window.fig_control_window.scroll_areas))
        finally:
            self._close(window)

    def test_activity_rails_fill_cells_and_preserve_icon_colors(self):
        window = MainWindow()
        self._show(window)
        try:
            rail_size = CONTROL_SIZES["activity_rail"]
            self.assertEqual(window.left_column.width(), rail_size)
            self.assertEqual(window.right_column.width(), rail_size)

            buttons = (
                window.left_column.table_button,
                window.left_column.components_button,
                window.left_column.setting_button,
                window.right_column.tex_button,
                window.right_column.matlab_button,
            )
            for button in buttons:
                self.assertEqual(button.width(), rail_size)
                self.assertEqual(button.height(), rail_size)
                self.assertEqual(button.x(), 0)

            self.assertGreater(
                self._icon_lightness(window.left_column.table_button), 200
            )
            self.assertLess(
                self._icon_lightness(window.left_column.components_button),
                100,
            )
            self.assertLess(
                self._icon_lightness(window.left_column.setting_button), 100
            )
            tex_colors = self._icon_opaque_colors(window.right_column.tex_button)
            matlab_colors = self._icon_opaque_colors(
                window.right_column.matlab_button
            )
            self.assertTrue(
                any(
                    color.blue() > color.red() and color.blue() > color.green()
                    for color in tex_colors
                )
            )
            self.assertTrue(
                any(
                    color.red() > 180
                    and color.green() > 100
                    and color.blue() < 150
                    for color in matlab_colors
                )
            )
            self.assertTrue(
                any(
                    color.green() > color.red()
                    and color.blue() > color.red()
                    for color in matlab_colors
                )
            )
            tex_icon_key = window.right_column.tex_button.icon().cacheKey()
            matlab_icon_key = window.right_column.matlab_button.icon().cacheKey()

            window.left_column.table_button.click()
            window.right_column.tex_button.setChecked(True)
            self.app.processEvents()
            self.assertLess(
                self._icon_lightness(window.left_column.table_button), 100
            )
            self.assertLess(
                self._icon_lightness(window.left_column.components_button),
                100,
            )
            self.assertEqual(
                window.right_column.tex_button.icon().cacheKey(), tex_icon_key
            )
            self.assertEqual(
                window.right_column.matlab_button.icon().cacheKey(), matlab_icon_key
            )

            window.right_column.matlab_button.setChecked(True)
            self.app.processEvents()
            self.assertEqual(
                window.right_column.tex_button.icon().cacheKey(), tex_icon_key
            )
            self.assertEqual(
                window.right_column.matlab_button.icon().cacheKey(), matlab_icon_key
            )
        finally:
            self._close(window)

    def test_empty_states_follow_project_and_axes_lifecycle(self):
        window = MainWindow()
        self._show(window)
        try:
            figure_window = window.figure_window
            inspector = window.fig_control_window.figure_inspector_host
            self.assertTrue(window.table.empty_label.wordWrap())
            self.assertIs(figure_window.content_stack.currentWidget(), figure_window.empty_state)
            self.assertIsNone(inspector.current_figure_inspector())
            window.title_bar.change_button.setChecked(True)
            figure_window.empty_state.primary_button.click()
            self.app.processEvents()
            self.assertFalse(window.title_bar.change_button.isChecked())
            self.assertTrue(window.title_bar.selector_menu_bar.style_button.isChecked())
            self.assertEqual(window.title_bar.stacklayout_bottom.currentIndex(), 0)

            figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="LayoutTest",
            )
            self.app.processEvents()
            self.assertIs(figure_window.content_stack.currentWidget(), figure_window.tabwindow)
            self.assertIsInstance(
                inspector.current_figure_inspector(),
                FigureInspectorPanel,
            )
            self.assertIs(
                figure_window.current_figure_inspector.current_panel(),
                figure_window.current_figure_inspector.root_inspector,
            )
            self.assertEqual(
                figure_window.current_canva.current_component_id,
                figure_window.current_canva.root_component_id,
            )

            figure_window.current_canva.add_axes()
            self.app.processEvents()
            self.assertIsInstance(
                figure_window.current_figure_inspector.current_panel(),
                AxesInspectorPanel,
            )
            axes_widget = figure_window.current_figure_inspector.axes_inspector(
                figure_window.current_canva.current_axes_component_id
            )
            self.assertIsNotNone(axes_widget)
            self.assertEqual(
                axes_widget.current_component_id(),
                figure_window.current_canva.current_axes_component_id,
            )

            figure_window.clear_figures()
            self.app.processEvents()
            self.assertIs(figure_window.content_stack.currentWidget(), figure_window.empty_state)
            self.assertIsNone(inspector.current_figure_inspector())
        finally:
            self._close(window)

    def test_figure_inspector_host_tracks_project_removal_by_tab_index(self):
        window = MainWindow()
        self._show(window)
        try:
            figure_window = window.figure_window
            host = window.fig_control_window.figure_inspector_host
            figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="First",
            )
            first_inspector = host.current_figure_inspector()
            figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="Second",
            )
            second_inspector = host.current_figure_inspector()
            self.assertIsNot(first_inspector, second_inspector)

            figure_window.tabwindow.setCurrentIndex(0)
            self.app.processEvents()
            self.assertIs(host.current_figure_inspector(), first_inspector)

            figure_window.remove_project("First")
            self.app.processEvents()
            self.assertEqual(figure_window.tabwindow.count(), 1)
            self.assertIs(
                figure_window.current_figure_inspector,
                second_inspector,
            )
            self.assertIs(host.current_figure_inspector(), second_inspector)

            figure_window.remove_project("Second")
            self.app.processEvents()
            self.assertEqual(figure_window.tabwindow.count(), 0)
            self.assertIsNone(host.current_figure_inspector())
        finally:
            self._close(window)

    def test_opening_project_does_not_replace_workbench_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir, "layout-isolation.mygui.json")
            source = MainWindow()
            source.figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="SavedProject",
            )
            save_project_snapshot(project_path, source.figure_window)
            self._close(source)

            target = MainWindow()
            self._show(target)
            target.workspace_splitter.setSizes([620, 660])
            target.explorer_control_splitter.setSizes([330, 260])
            self.app.processEvents()
            outer_sizes = target.workspace_splitter.sizes()
            inner_sizes = target.explorer_control_splitter.sizes()
            try:
                restore_project_snapshot(
                    project_path,
                    table=target.table,
                    figure_window=target.figure_window,
                )
                self.app.processEvents()
                self.assertEqual(target.workspace_splitter.sizes(), outer_sizes)
                self.assertEqual(
                    target.explorer_control_splitter.sizes(),
                    inner_sizes,
                )
            finally:
                self._close(target)


class GuiLayoutSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _settings(self, path: Path):
        return QSettings(str(path), QSettings.IniFormat)

    def _show(self, window):
        window.resize(1280, 720)
        window.showNormal()
        self.app.processEvents()
        self.app.processEvents()

    def _close(self, window):
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_splitters_and_explorer_mode_roundtrip_then_reset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "layout.ini")
            first = MainWindow(settings=self._settings(path))
            self._show(first)
            first.workspace_splitter.setSizes([640, 640])
            first.explorer_control_splitter.setSizes([330, 260])
            self.app.processEvents()
            saved_outer = first.workspace_splitter.sizes()
            saved_inner = first.explorer_control_splitter.sizes()
            first.left_column.components_button.click()
            first.left_column.components_button.click()
            self.app.processEvents()
            self._close(first)

            settings = self._settings(path)
            second = MainWindow(settings=settings)
            self._show(second)
            try:
                self.assertFalse(second.left_column.table_button.isChecked())
                self.assertFalse(
                    second.left_column.components_button.isChecked()
                )
                self.assertFalse(second.left_explorer.isVisible())
                self.assertIs(
                    second._explorer_mode,
                    ExplorerMode.COMPONENTS,
                )
                self.assertEqual(second.workspace_splitter.sizes(), saved_outer)
                self.assertEqual(
                    second._last_visible_explorer_sizes,
                    saved_inner,
                )

                second.reset_workspace_layout()
                self.app.processEvents()
                self.assertTrue(second.left_column.table_button.isChecked())
                self.assertTrue(second.left_explorer.isVisible())
                self.assertIs(second._explorer_mode, ExplorerMode.TABLE)
                settings.beginGroup(second.WORKSPACE_SETTINGS_GROUP)
                try:
                    self.assertIsNone(settings.value("version"))
                finally:
                    settings.endGroup()
            finally:
                self._close(second)

    def test_malformed_or_old_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "layout.ini")
            settings = self._settings(path)
            settings.beginGroup(MainWindow.WORKSPACE_SETTINGS_GROUP)
            settings.setValue("version", MainWindow.WORKSPACE_SETTINGS_VERSION)
            settings.setValue("outerSplitterSizes", "not-sizes")
            settings.setValue("innerSplitterSizes", [1, 2, 3])
            settings.setValue("tableVisible", False)
            settings.endGroup()
            settings.sync()

            window = MainWindow(settings=self._settings(path))
            window.resize(1280, 720)
            window.showNormal()
            self.app.processEvents()
            self.app.processEvents()
            try:
                self.assertFalse(window._workspace_layout_restored)
                self.assertTrue(window.left_column.table_button.isChecked())
                self.assertGreaterEqual(window.figure_window.width(), 400)
            finally:
                self._close(window)

    def test_v1_table_visibility_migrates_to_v2_explorer_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "layout.ini")
            settings = self._settings(path)
            settings.beginGroup(MainWindow.WORKSPACE_SETTINGS_GROUP)
            settings.setValue("version", 1)
            settings.setValue("outerSplitterSizes", [640, 640])
            settings.setValue("innerSplitterSizes", [330, 260])
            settings.setValue("tableVisible", False)
            settings.endGroup()
            settings.sync()

            window = MainWindow(settings=self._settings(path))
            self._show(window)
            try:
                self.assertTrue(window._workspace_layout_restored)
                self.assertIs(window._explorer_mode, ExplorerMode.TABLE)
                self.assertFalse(window._explorer_visible)
                self.assertFalse(window.left_explorer.isVisible())
            finally:
                self._close(window)

            migrated = self._settings(path)
            migrated.beginGroup(MainWindow.WORKSPACE_SETTINGS_GROUP)
            try:
                self.assertEqual(
                    int(migrated.value("version")),
                    MainWindow.WORKSPACE_SETTINGS_VERSION,
                )
                self.assertEqual(
                    migrated.value("explorerMode"),
                    ExplorerMode.TABLE.value,
                )
                self.assertFalse(
                    MainWindow._setting_bool(
                        migrated.value("explorerVisible"),
                        True,
                    )
                )
            finally:
                migrated.endGroup()

    def test_extreme_splitter_ratio_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "layout.ini")
            settings = self._settings(path)
            settings.beginGroup(MainWindow.WORKSPACE_SETTINGS_GROUP)
            settings.setValue("version", MainWindow.WORKSPACE_SETTINGS_VERSION)
            settings.setValue("outerSplitterSizes", [99_999, 1])
            settings.setValue("innerSplitterSizes", [420, 240])
            settings.setValue("tableVisible", False)
            settings.endGroup()
            settings.sync()

            window = MainWindow(settings=self._settings(path))
            self._show(window)
            try:
                self.assertFalse(window._workspace_layout_restored)
                self.assertTrue(window.left_column.table_button.isChecked())
                self.assertGreaterEqual(window.figure_window.width(), 400)
            finally:
                self._close(window)


if __name__ == "__main__":
    unittest.main()
