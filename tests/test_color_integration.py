import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QCoreApplication, QEvent

from code.database import ColumnRef
from code.database.interpolate_func import interpolate_dict
from code.figuremodify.components import (
    ComponentRole,
    DataPlotController,
)
from code.figuremodify.style_base.color_models import PaletteDefinition, builtin_palettes
from code.widgets.title_bar.titlebar_dialog.py_chart_dialog import (
    PyCurveDialog,
    PyPlotDialog,
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
        self.canvas.add_axes()
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
        snapshots = self.canvas.dependent_records({self.x_ref})
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
        with patch("code.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"):
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
