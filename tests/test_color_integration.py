import os
import unittest
from unittest.mock import Mock, patch

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from mygui.database import ColumnRef, DataPreprocessSpec
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import (
    ComponentRole,
    DataPlotController,
)
from mygui.figuremodify.style_base.color_models import PaletteDefinition, builtin_palettes
from mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyCurveDialog,
    PyFitDialog,
    PyInterpolationDialog,
    PyPlotDialog,
    PyScatterDialog,
)
from mygui.widgets.title_bar.titlebar_dialog.py_element_dialog import (
    PyTextDialog,
)
from main import MainWindow


class ColorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="Colors"
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [[0, 1], [1, 2], [2, 3], [3, 5]])
        self.x_ref = ColumnRef(self.canvas.project_id, sheet.id, sheet.columns[0].id)
        self.y_ref = ColumnRef(self.canvas.project_id, sheet.id, sheet.columns[1].id)
        self.pair = self.window.repository.valid_pair(self.x_ref, self.y_ref)

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _add_all_chart_types(self):
        c = self.canvas
        p = self.pair
        c.add_curve("x", 0, 3, "-", "tab:blue", "curve")
        c.add_plot(p.x, p.y, "-", 2, "red", "plot", self.x_ref, self.y_ref)
        c.add_scatter(p.x, p.y, 20, "green", "o", "scatter", self.x_ref, self.y_ref)
        c.add_fit_curve(p.x, p.y, "#663399", "fit", self.x_ref, self.y_ref)
        c.add_interpolate_curve(
            p.x, p.y, self.x_ref, self.y_ref, list(interpolate_dict)[2], color="orange"
        )

    def test_fit_keeps_initial_color_and_all_five_types_join_batch(self):
        self._add_all_chart_types()
        axes_id = self.canvas.current_axes_component_id
        fit = self.canvas.component_registry.query(
            role=ComponentRole.FIT_CURVE
        )[0]
        self.assertEqual(
            fit.state.properties["color"].casefold(),
            "#663399",
        )
        targets = self.canvas.component_registry.query(
            capabilities={"color", "data"},
            parent_id=axes_id,
            recursive=True,
        )
        self.assertEqual(len(targets), 5)

        legend = self.canvas.current_axes.legend(loc="upper left")
        legend.set_visible(False)
        palette = next(p for p in builtin_palettes() if len(p.colors) >= 5)
        with patch.object(self.canvas.fig.canvas, "draw_idle") as draw_idle:
            result = self.canvas.axes_commands.apply_palette(
                axes_id,
                palette,
            )
            self.assertTrue(result.ok)
            self.assertEqual(draw_idle.call_count, 1)

        self.assertFalse(self.canvas.current_axes.get_legend().get_visible())
        colors = [
            controller.state.properties["color"]
            for controller in targets
        ]
        self.assertEqual(
            [color.casefold() for color in colors],
            [color.casefold() for color in palette.colors[:5]],
        )
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            5 % len(palette.colors),
        )

    def test_delete_and_dependency_restore_rebuild_safe_color_targets(self):
        self._add_all_chart_types()
        axes_id = self.canvas.current_axes_component_id
        original_axes_state = self.canvas.component_registry.get(
            axes_id
        ).state.clone()
        snapshots = self.canvas.dependent_records({self.x_ref})
        self.assertEqual(
            [state.id for state in snapshots.axes_states],
            [axes_id],
        )
        self.canvas.remove_data_dependents(snapshots)
        self.assertEqual(
            len(
                self.canvas.component_registry.query(
                    capabilities={"color", "data"},
                    parent_id=axes_id,
                    recursive=True,
                )
            ),
            1,
        )
        self.canvas.restore_data_dependents(snapshots)
        self.assertEqual(
            self.canvas.component_registry.get(axes_id).state.properties[
                "color_cycle"
            ],
            original_axes_state.properties["color_cycle"],
        )
        self.assertEqual(
            len(
                self.canvas.component_registry.query(
                    capabilities={"color", "data"},
                    parent_id=axes_id,
                    recursive=True,
                )
            ),
            5,
        )
        palette = builtin_palettes()[0]
        self.assertTrue(
            self.canvas.axes_commands.apply_palette(
                axes_id,
                palette,
            ).ok
        )

    def test_creation_cancel_and_failure_do_not_commit_cycle_or_recent(self):
        axes_id = self.canvas.current_axes_component_id
        state = self.canvas.axes_commands.cycle_state(axes_id)
        palette = PaletteDefinition("test:dialog", "Dialog", ("red", "blue"))
        state.activate(palette)
        self.canvas.current_axes_controller.set_property(
            "color_cycle",
            state.to_dict(),
        )
        self.canvas.component_registry.get(
            self.canvas.root_component_id
        ).set_property("style", "dark_background")

        cancelled = PyCurveDialog("Curve", self.window.figure_window)
        self.assertEqual(cancelled.color_input.color(), "#FF0000")
        cancelled.reject()
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.assertEqual(self.window.color_library.recent_colors, [])
        cancelled.deleteLater()

        failed = PyCurveDialog("Curve", self.window.figure_window)
        failed.expression_edit.setText("__import__('os')")
        with patch("mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"):
            failed.accept()
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            0,
        )
        self.assertEqual(self.window.color_library.recent_colors, [])
        failed.close()
        failed.deleteLater()

        created = PyCurveDialog("Curve", self.window.figure_window)
        created.accept()
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(axes_id).next_index,
            1,
        )
        self.assertEqual(self.window.color_library.recent_colors, ["#FF0000"])
        created.close()
        created.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_single_curve_color_commit_failure_rolls_back_component(self):
        axes_id = self.canvas.current_axes_component_id
        before_ids = {
            controller.component_id
            for controller in self.canvas.component_registry.query()
        }
        before_lines = tuple(self.canvas.current_axes.lines)
        before_cycle = self.canvas.component_registry.get(axes_id).state.properties[
            "color_cycle"
        ]
        dialog = PyCurveDialog("Curve", self.window.figure_window)
        try:
            rejected = Mock(ok=False, message="injected color commit failure")
            with (
                patch.object(
                    self.canvas.axes_commands,
                    "commit_color_selection",
                    return_value=rejected,
                ),
                patch(
                    "mygui.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"
                ),
            ):
                dialog.accept()

            self.assertEqual(
                {
                    controller.component_id
                    for controller in self.canvas.component_registry.query()
                },
                before_ids,
            )
            self.assertEqual(tuple(self.canvas.current_axes.lines), before_lines)
            self.assertEqual(
                self.canvas.component_registry.get(axes_id).state.properties[
                    "color_cycle"
                ],
                before_cycle,
            )
            self.assertEqual(self.window.color_library.recent_colors, [])
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_dependency_restore_failure_publishes_no_intermediate_events(self):
        self.canvas.add_plots(
            self.x_ref,
            (self.y_ref,),
            style="-",
            size=2.0,
            linewidth=None,
            preprocess=DataPreprocessSpec(),
            color_selection=self.canvas.creation_color_cycle().peek(),
        )
        controller = self.canvas.component_registry.query(
            role=ComponentRole.DATA_PLOT
        )[0]
        snapshots = self.canvas.dependent_records({self.x_ref})
        self.assertTrue(self.canvas.remove_data_dependents(snapshots))
        events = []
        unsubscribe = self.canvas.component_registry.subscribe(events.append)
        original = self.canvas.component_materializers.materialize

        def fail_after_materialize(state, transaction):
            original(state, transaction)
            raise RuntimeError("injected materializer failure")

        try:
            with patch.object(
                self.canvas.component_materializers,
                "materialize",
                side_effect=fail_after_materialize,
            ):
                with self.assertRaisesRegex(RuntimeError, "materializer failure"):
                    self.canvas.restore_data_dependents(snapshots)
        finally:
            unsubscribe()

        self.assertNotIn(controller.component_id, self.canvas.component_registry)
        self.assertEqual(events, [])

    def test_style_cycle_cancel_and_failure_leave_axes_state_null(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "ggplot").ok)
        axes_id = self.canvas.current_axes_component_id

        cancelled = PyCurveDialog("Curve", self.window.figure_window)
        self.assertEqual(cancelled.color_input.color(), "#E24A33")
        cancelled.reject()
        self.assertIsNone(
            self.canvas.axes_commands.cycle_state(
                axes_id
            ).active_palette
        )

        failed = PyCurveDialog("Curve", self.window.figure_window)
        failed.expression_edit.setText("__import__('os')")
        with patch(
            "mygui.widgets.title_bar.titlebar_dialog."
            "py_chart_dialog.QMessageBox.warning"
        ):
            failed.accept()
        self.assertIsNone(
            self.canvas.axes_commands.cycle_state(
                axes_id
            ).active_palette
        )

        cancelled.deleteLater()
        failed.close()
        failed.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_plot_dialog_uses_readable_controller_default_and_canonical_values(self):
        default_style = DataPlotController.default_properties()["linestyle"]

        default_dialog = PyPlotDialog("Plot", self.window.figure_window)
        self.assertEqual(default_dialog.style_input.currentText(), "Solid")
        self.assertEqual(default_dialog.style_input.currentData(), default_style)
        default_dialog.accept()

        dashed_dialog = PyPlotDialog("Plot", self.window.figure_window)
        dashed_index = dashed_dialog.style_input.findData("--")
        self.assertGreaterEqual(dashed_index, 0)
        dashed_dialog.style_input.setCurrentIndex(dashed_index)
        self.assertEqual(dashed_dialog.style_input.currentText(), "Dashed")
        dashed_dialog.accept()

        controllers = self.canvas.component_registry.query(
            role=ComponentRole.DATA_PLOT
        )
        self.assertEqual(len(controllers), 2)
        self.assertEqual(
            controllers[0].state.properties["linestyle"],
            default_style,
        )
        self.assertEqual(
            controllers[1].state.properties["linestyle"],
            "--",
        )
        self.assertEqual(
            controllers[0].resolve_target().get_linestyle(),
            default_style,
        )
        self.assertEqual(
            controllers[1].resolve_target().get_linestyle(),
            "--",
        )
        snapshot_by_id = {
            component["id"]: component
            for component in self.canvas.component_snapshot()["components"]
        }
        self.assertEqual(
            snapshot_by_id[controllers[0].component_id]["properties"][
                "linestyle"
            ],
            default_style,
        )
        self.assertEqual(
            snapshot_by_id[controllers[1].component_id]["properties"][
                "linestyle"
            ],
            "--",
        )

        default_dialog.deleteLater()
        dashed_dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_creation_dialog_defaults_follow_current_figure_style(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "fivethirtyeight").ok)

        curve = PyCurveDialog("Curve", self.window.figure_window)
        plot = PyPlotDialog("Plot", self.window.figure_window)
        scatter = PyScatterDialog("Scatter", self.window.figure_window)
        fit = PyFitDialog("Fit", self.window.figure_window)
        interpolation = PyInterpolationDialog(
            "Interpolation",
            self.window.figure_window,
        )
        text = PyTextDialog("Text", self.window.figure_window)
        dialogs = (curve, plot, scatter, fit, interpolation, text)
        try:
            for dialog in (curve, plot, scatter, fit, interpolation):
                self.assertEqual(dialog.color_input.color(), "#008FD5")
            self.assertEqual(curve.appearance_input.style(), "-")
            self.assertEqual(plot.appearance_input.linewidth(), 4.0)
            self.assertEqual(scatter.style_input.currentText(), "o")
            self.assertEqual(scatter.size_input.value(), 36.0)
            self.assertEqual(text.font_input.currentText(), "sans-serif")
            self.assertEqual(text.font_size_input.value(), 14.0)

            self.assertTrue(
                root.set_property("style", "seaborn-v0_8-poster").ok
            )
            poster = PyScatterDialog(
                "Scatter",
                self.window.figure_window,
            )
            try:
                self.assertAlmostEqual(
                    poster.size_input.value(),
                    125.44,
                    places=2,
                )
            finally:
                poster.close()
                poster.deleteLater()
        finally:
            for dialog in dialogs:
                dialog.close()
                dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_five_chart_dialogs_advance_style_cycle_and_sync_linewidth(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "fivethirtyeight").ok)

        dialog_factories = (
            lambda: PyCurveDialog("Curve", self.window.figure_window),
            lambda: PyPlotDialog("Plot", self.window.figure_window),
            lambda: PyScatterDialog("Scatter", self.window.figure_window),
            lambda: PyFitDialog("Fit", self.window.figure_window),
            lambda: PyInterpolationDialog(
                "Interpolation", self.window.figure_window
            ),
        )
        dialogs = []
        try:
            for factory in dialog_factories:
                dialog = factory()
                dialogs.append(dialog)
                dialog.accept()

            axes_id = self.canvas.current_axes_component_id
            controllers = self.canvas.component_registry.query(
                capabilities={"color", "data"},
                parent_id=axes_id,
                recursive=True,
            )
            defaults = self.canvas.component_creation_defaults()
            self.assertEqual(
                [
                    item.state.properties["color"].casefold()
                    for item in controllers
                ],
                [
                    color.casefold()
                    for color in defaults.chart_palette.colors[:5]
                ],
            )
            cycle = self.canvas.axes_commands.cycle_state(axes_id)
            self.assertEqual(
                cycle.active_palette.source,
                "matplotlib-style",
            )
            self.assertEqual(cycle.next_index, 5)

            plot = self.canvas.component_registry.query(
                role=ComponentRole.DATA_PLOT
            )[0]
            self.assertEqual(plot.state.properties["linewidth"], 4.0)
            self.assertEqual(plot.state.properties["markersize"], 6.0)
            self.assertEqual(plot.resolve_target().get_linewidth(), 4.0)
            editor = self.canvas.component_editor_manager.editor(
                plot.component_id
            )
            self.assertEqual(
                editor.section("appearance")
                .editor("linewidth")
                .value(),
                4.0,
            )
            scatter = self.canvas.component_registry.query(
                role=ComponentRole.SCATTER
            )[0]
            self.assertEqual(
                scatter.state.properties["linewidth"],
                defaults.scatter.linewidth,
            )
            self.assertEqual(
                scatter.state.properties["size"],
                defaults.scatter.size,
            )
        finally:
            for dialog in dialogs:
                dialog.close()
                dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_single_custom_color_does_not_advance_style_cycle(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "ggplot").ok)
        dialog = PyCurveDialog("Curve", self.window.figure_window)
        try:
            dialog.color_input.set_color("#123456")
            dialog.accept()
            cycle = self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            )
            self.assertEqual(
                cycle.active_palette.source,
                "matplotlib-style",
            )
            self.assertEqual(cycle.next_index, 0)

            next_dialog = PyCurveDialog(
                "Curve",
                self.window.figure_window,
            )
            try:
                self.assertEqual(
                    next_dialog.color_input.color(),
                    "#E24A33",
                )
            finally:
                next_dialog.close()
                next_dialog.deleteLater()
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_style_change_replaces_only_automatic_palette_for_new_charts(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "ggplot").ok)
        first_dialog = PyCurveDialog(
            "Curve",
            self.window.figure_window,
        )
        second_dialog = None
        try:
            first_dialog.accept()
            first = self.canvas.component_registry.query(
                role=ComponentRole.FUNCTION_CURVE
            )[0]
            first_color = first.state.properties["color"]

            self.assertTrue(
                root.set_property("style", "dark_background").ok
            )
            second_dialog = PyCurveDialog(
                "Curve",
                self.window.figure_window,
            )
            self.assertEqual(
                second_dialog.color_input.color(),
                "#FEFFB3",
            )
            second_dialog.accept()

            curves = self.canvas.component_registry.query(
                role=ComponentRole.FUNCTION_CURVE
            )
            self.assertEqual(curves[0].state.properties["color"], first_color)
            self.assertEqual(
                curves[1].state.properties["color"].casefold(),
                "#feffb3",
            )
            cycle = self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            )
            self.assertEqual(
                cycle.active_palette,
                self.canvas.component_creation_defaults().chart_palette,
            )
            self.assertEqual(cycle.next_index, 2)
        finally:
            first_dialog.close()
            first_dialog.deleteLater()
            if second_dialog is not None:
                second_dialog.close()
                second_dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_style_color_cycles_are_independent_per_axes(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "default").ok)
        first_axes_id = self.canvas.current_axes_component_id
        first_dialog = PyCurveDialog(
            "Curve",
            self.window.figure_window,
        )
        second_dialog = None
        next_first_dialog = None
        try:
            first_dialog.accept()
            create_regular_axes(self.canvas)
            second_axes_id = self.canvas.current_axes_component_id
            second_dialog = PyCurveDialog(
                "Curve",
                self.window.figure_window,
            )
            self.assertEqual(second_dialog.color_input.color(), "#1F77B4")
            second_dialog.accept()

            self.canvas.set_current_axes_by_index(0)
            next_first_dialog = PyCurveDialog(
                "Curve",
                self.window.figure_window,
            )
            self.assertEqual(
                next_first_dialog.color_input.color(),
                "#FF7F0E",
            )
            self.assertEqual(
                self.canvas.axes_commands.cycle_state(
                    first_axes_id
                ).next_index,
                1,
            )
            self.assertEqual(
                self.canvas.axes_commands.cycle_state(
                    second_axes_id
                ).next_index,
                1,
            )
        finally:
            first_dialog.close()
            first_dialog.deleteLater()
            for dialog in (second_dialog, next_first_dialog):
                if dialog is not None:
                    dialog.close()
                    dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_dark_background_text_inherits_style_and_syncs_state(self):
        root = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(root.set_property("style", "dark_background").ok)
        dialog = PyTextDialog("Text", self.window.figure_window)
        try:
            dialog.text_edit.setText("styled")
            dialog.accept()
            controller = self.canvas.component_registry.query(
                role=ComponentRole.TEXT
            )[0]
            self.assertEqual(
                controller.state.properties["color"].casefold(),
                "#ffffff",
            )
            self.assertEqual(
                controller.resolve_target().get_color(),
                "white",
            )
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_batch_failure_rolls_back_artist_and_widget_colors(self):
        self.canvas.add_curve(
            "x",
            0,
            3,
            "-",
            "#010101",
            "first",
            object_id="first",
        )
        self.canvas.add_curve(
            "x**2",
            0,
            3,
            "-",
            "#020202",
            "second",
            object_id="second",
        )
        first = self.canvas.component_registry.get("first")
        second = self.canvas.component_registry.get("second")
        first_widget = self.canvas.component_editor_manager.editor("first")
        second_widget = self.canvas.component_editor_manager.editor("second")
        original_write = second._write_property

        def fail_blue(target, spec, value):
            if (
                spec.key == "color"
                and str(value).casefold() == "#0000ff"
            ):
                raise RuntimeError("synthetic failure")
            return original_write(target, spec, value)

        second._write_property = fail_blue
        palette = PaletteDefinition("test:rollback", "Rollback", ("red", "blue"))
        try:
            result = self.canvas.axes_commands.apply_palette(
                self.canvas.current_axes_component_id,
                palette,
            )
            self.assertFalse(result.ok)
            self.assertEqual(first.state.properties["color"], "#010101")
            self.assertEqual(second.state.properties["color"], "#020202")
            self.assertEqual(
                first_widget.section("appearance").editor("color").color(),
                "#010101",
            )
            self.assertEqual(
                second_widget.section("appearance").editor("color").color(),
                "#020202",
            )
            self.assertIsNone(
                self.canvas.axes_commands.cycle_state(
                    self.canvas.current_axes_component_id
                ).active_palette
            )
        finally:
            second._write_property = original_write


if __name__ == "__main__":
    unittest.main()
