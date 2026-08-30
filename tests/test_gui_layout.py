import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from mygui.figuremodify.components import ComponentRole
from mygui.widgets.fig_control_window.component_editors import (
    AxisScaleEditor,
    AxisTickSettingsSection,
    FontSpecEditor,
)
from mygui.widgets.fig_control_window.figure_inspector import (
    AxesInspectorPanel,
    FigureInspectorPanel,
)
from mygui.widgets.left_column import ExplorerMode
from mygui.widgets.theme import CONTROL_SIZES
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from mygui.application_settings import (
    ApplicationSettingsService,
    MemorySettingsDocumentPort,
    WORKSPACE_REMEMBER_LAYOUT,
    commit_succeeded,
)
from mygui.application_settings.storage import (
    LEGACY_WORKSPACE_GROUP,
    create_settings_backend,
)
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

    def test_component_switch_resets_shared_inspector_scroll_to_top_left(self):
        window = MainWindow()
        self._show(window, 960, 600)
        try:
            window.figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="ScrollReset",
            )
            canvas = window.figure_window.current_canva
            create_regular_axes(canvas)
            panel = canvas.figure_inspector
            title_id = canvas.component_registry.query(
                role=ComponentRole.TITLE
            )[0].component_id
            x_axis_id = canvas.component_registry.query(
                role=ComponentRole.X_AXIS
            )[0].component_id
            self.assertTrue(canvas.select_component(title_id))
            self.app.processEvents()

            area = window.fig_control_window.figure_inspector_scroll_area
            horizontal = area.horizontalScrollBar()
            vertical = area.verticalScrollBar()
            horizontal.setRange(0, 100)
            vertical.setRange(0, 100)
            horizontal.setValue(61)
            vertical.setValue(73)
            shown = QSignalSpy(panel.componentShown)

            self.assertTrue(canvas.select_component(x_axis_id))
            self.app.processEvents()
            self.app.processEvents()
            self.assertEqual(shown.count(), 1)
            self.assertEqual(shown.at(0)[0], x_axis_id)
            self.assertEqual(horizontal.value(), horizontal.minimum())
            self.assertEqual(vertical.value(), vertical.minimum())

            horizontal.setRange(0, 100)
            vertical.setRange(0, 100)
            horizontal.setValue(31)
            vertical.setValue(47)
            self.assertTrue(canvas.select_component(x_axis_id))
            self.app.processEvents()
            self.assertEqual(shown.count(), 1)
            self.assertEqual(horizontal.value(), 31)
            self.assertEqual(vertical.value(), 47)
        finally:
            window.close_without_prompt()
            self.app.processEvents()

    def test_production_axis_inspector_uses_readable_structured_editors(self):
        window = MainWindow()
        self._show(window, 960, 600)
        try:
            window.figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="AxisEditors",
            )
            canvas = window.figure_window.current_canva
            create_regular_axes(canvas)
            x_axis = canvas.component_registry.query(
                role=ComponentRole.X_AXIS
            )[0]
            self.assertTrue(canvas.select_component(x_axis.component_id))
            self.app.processEvents()

            inspector = canvas.component_editor_manager.editor(
                x_axis.component_id
            )
            section = inspector.section("properties")
            tick_section = inspector.section("ticks_labels")
            scale = section.editor("scale")
            offset_font = section.editor("offset_font")
            self.assertIsInstance(scale, AxisScaleEditor)
            self.assertIsInstance(tick_section, AxisTickSettingsSection)
            self.assertIsInstance(offset_font, FontSpecEditor)
            ticker_editors = [
                tick_section.editor(key)
                for key in (
                    "major_locator",
                    "major_formatter",
                    "minor_locator",
                    "minor_formatter",
                )
            ]
            self.assertTrue(
                all(editor is tick_section.configure_button for editor in ticker_editors)
            )
            self.assertEqual(scale.summary.text(), "Linear")
            self.assertEqual(
                tick_section.summary_label.text(),
                "Major: auto / scalar · Minor: null / null",
            )
            self.assertEqual(
                tick_section.configure_button.text(),
                "Configure Ticks & Labels…",
            )

            scale.set_value(
                {
                    "kind": "log",
                    "params": {
                        "base": 10.0,
                        "subs": None,
                        "nonpositive": "clip",
                    },
                },
                emit=True,
            )
            self.app.processEvents()
            self.assertEqual(x_axis.resolve_target().axes.get_xscale(), "log")
            self.assertEqual(scale.summary.text(), "Log")
        finally:
            window.close_without_prompt()
            self.app.processEvents()

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

            create_regular_axes(figure_window.current_canva)
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
            first_project_id = figure_window.current_canva.project_id
            figure_window.add_figure(
                width=4,
                height=3,
                dpi=100,
                style="default",
                canva_name="Second",
            )
            second_inspector = host.current_figure_inspector()
            second_project_id = figure_window.current_canva.project_id
            self.assertIsNot(first_inspector, second_inspector)

            figure_window.tabwindow.setCurrentIndex(0)
            self.app.processEvents()
            self.assertIs(host.current_figure_inspector(), first_inspector)

            figure_window.remove_project_by_id(first_project_id)
            self.app.processEvents()
            self.assertEqual(figure_window.tabwindow.count(), 1)
            self.assertIs(
                figure_window.current_figure_inspector,
                second_inspector,
            )
            self.assertIs(host.current_figure_inspector(), second_inspector)

            figure_window.remove_project_by_id(second_project_id)
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

    def _workspace_snapshot(self, path: Path):
        backend = create_settings_backend(file_path=path)
        service = ApplicationSettingsService(
            document=backend.application_settings_port()
        )
        return service.snapshot().workspace

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
            settings.beginGroup(LEGACY_WORKSPACE_GROUP)
            try:
                self.assertIsNone(settings.value("version"))
            finally:
                settings.endGroup()

            second = MainWindow(settings=self._settings(path))
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

                self.assertTrue(
                    second.reset_workspace_layout(confirmed=True)
                )
                self.app.processEvents()
                self.assertTrue(second.left_column.table_button.isChecked())
                self.assertTrue(second.left_explorer.isVisible())
                self.assertIs(second._explorer_mode, ExplorerMode.TABLE)
                stored = second.settings_service.snapshot().workspace.layout
                self.assertEqual(stored.explorer_mode.value, "table")
                self.assertTrue(stored.explorer_visible)
                self.assertNotEqual(
                    tuple(stored.outer_splitter_sizes),
                    tuple(saved_outer),
                )
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

            stored = self._workspace_snapshot(path).layout
            self.assertEqual(stored.explorer_mode.value, "table")
            self.assertFalse(stored.explorer_visible)

            legacy = self._settings(path)
            legacy.beginGroup(MainWindow.WORKSPACE_SETTINGS_GROUP)
            try:
                self.assertEqual(int(legacy.value("version")), 1)
            finally:
                legacy.endGroup()

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

    def test_remember_false_does_not_overwrite_stored_layout_on_close(self):
        document = MemorySettingsDocumentPort()
        first = MainWindow(settings_service=document)
        self._show(first)
        first.workspace_splitter.setSizes([640, 640])
        first.explorer_control_splitter.setSizes([330, 260])
        first.left_column.components_button.click()
        first.left_column.components_button.click()
        self.app.processEvents()
        saved = first._current_workspace_layout()
        self._close(first)
        self.assertGreaterEqual(document.commit_calls, 1)
        stored_before = dict(document.payload["workspace"]["layout"])

        second = MainWindow(settings_service=document)
        self._show(second)
        try:
            result = second.settings_service.commit_patch(
                second.settings_service.begin_session(),
                {WORKSPACE_REMEMBER_LAYOUT: False},
            )
            self.assertTrue(result.success)
            second.workspace_splitter.setSizes([500, 780])
            second.explorer_control_splitter.setSizes([200, 390])
            self.app.processEvents()
            commits_before_close = document.commit_calls
            self._close(second)
            self.assertEqual(document.commit_calls, commits_before_close)
            stored_after = document.payload["workspace"]["layout"]
            self.assertEqual(stored_after["outer_splitter_sizes"], stored_before["outer_splitter_sizes"])
            self.assertEqual(stored_after["explorer_mode"], saved.explorer_mode.value)
            self.assertFalse(document.payload["workspace"]["remember_layout"])
        finally:
            if second.isVisible():
                self._close(second)

    def test_reset_cancel_leaves_layout_unchanged(self):
        document = MemorySettingsDocumentPort()
        window = MainWindow(settings_service=document)
        self._show(window)
        try:
            window.workspace_splitter.setSizes([640, 640])
            self.app.processEvents()
            before = window.workspace_splitter.sizes()
            with patch.object(
                QMessageBox, "question", return_value=QMessageBox.No
            ):
                self.assertFalse(window.reset_workspace_layout())
            self.assertEqual(window.workspace_splitter.sizes(), before)
            self.assertIs(window._explorer_mode, ExplorerMode.TABLE)
        finally:
            self._close(window)

    def test_close_save_failure_does_not_block_exit(self):
        document = MemorySettingsDocumentPort()
        window = MainWindow(settings_service=document)
        self._show(window)
        window.workspace_splitter.setSizes([640, 640])
        self.app.processEvents()
        document.fail_commit = True
        with self.assertLogs("main", level="WARNING") as captured:
            closed = window.close()
        self.assertTrue(closed)
        window.deleteLater()
        self.app.processEvents()
        self.assertTrue(
            any("Workspace layout was not saved" in line for line in captured.output)
        )

    def test_reset_persist_failure_emits_one_error(self):
        document = MemorySettingsDocumentPort()
        window = MainWindow(settings_service=document)
        self._show(window)
        try:
            window.left_column.components_button.click()
            window.left_column.components_button.click()
            self.app.processEvents()
            self.assertFalse(window.left_explorer.isVisible())
            document.fail_commit = True
            with patch("main.status_messages.show_error", return_value=True) as show_error:
                self.assertFalse(window.reset_workspace_layout(confirmed=True))
            show_error.assert_called_once()
            self.assertIn(
                "Could not save the default workspace layout",
                show_error.call_args[0][0],
            )
            self.assertFalse(window.left_explorer.isVisible())
        finally:
            document.fail_commit = False
            self._close(window)

    def test_main_window_does_not_write_legacy_workspace_layout_group(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('beginGroup("workspaceLayout")', source)
        self.assertNotIn("beginGroup(self.WORKSPACE_SETTINGS_GROUP)", source)
        self.assertNotIn("beginGroup(cls.WORKSPACE_SETTINGS_GROUP)", source)

    def test_workspace_and_color_library_share_one_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "shared.ini")
            window = MainWindow(settings=self._settings(path))
            try:
                backend = window._settings_backend
                self.assertIsNotNone(backend)
                self.assertIsNotNone(window.settings_service)
                self.assertIs(
                    window.color_library._document,
                    backend.color_library_settings_port(),
                )
                self.assertIsNotNone(
                    window.figure_window.new_figure_defaults_provider
                )
                backend.mark_writes_forbidden()
                window.color_library.record_recent("#FF0000")
                self.assertEqual(window.color_library.recent_colors, [])
                result = window._workspace_layout_port.save_layout(
                    window._current_workspace_layout()
                )
                self.assertFalse(commit_succeeded(result))
            finally:
                self._close(window)

    def test_composition_root_injected_backend_is_shared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir, "injected.ini")
            backend = create_settings_backend(file_path=path)
            service = ApplicationSettingsService(
                document=backend.application_settings_port()
            )
            window = MainWindow(
                settings_backend=backend,
                settings_service=service,
            )
            try:
                self.assertIs(window._settings_backend, backend)
                self.assertIs(window.settings_service, service)
                self.assertIs(
                    window.color_library._document,
                    backend.color_library_settings_port(),
                )
            finally:
                self._close(window)


if __name__ == "__main__":
    unittest.main()
