import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QCoreApplication, QEvent

from code.database import ColumnRef
from code.database.interpolate_func import interpolate_dict
from code.figuremodify.style_base.color_models import PaletteDefinition, builtin_palettes
from code.widgets.title_bar.titlebar_dialog.py_chart_dialog import PyCurveDialog
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
        axes_modify = self.canvas.current_axes_mod
        self.assertEqual(self.canvas.project_fits[0]["color"], "#663399")
        self.assertEqual(len(axes_modify._live_color_targets()), 5)

        legend = self.canvas.current_axes.legend(loc="upper left")
        legend.set_visible(False)
        palette = next(p for p in builtin_palettes() if len(p.colors) >= 5)
        with patch.object(self.canvas.fig.canvas, "draw_idle") as draw_idle:
            self.assertTrue(axes_modify.change_all_color(palette))
            self.assertEqual(draw_idle.call_count, 1)

        self.assertFalse(self.canvas.current_axes.get_legend().get_visible())
        colors = [getter() for _target, _setter, getter, _sync in axes_modify._live_color_targets()]
        self.assertEqual(colors, list(palette.colors[:5]))
        self.assertEqual(axes_modify.color_selector.next_index, 5 % len(palette.colors))

    def test_delete_and_dependency_restore_rebuild_safe_color_targets(self):
        self._add_all_chart_types()
        axes_modify = self.canvas.current_axes_mod
        snapshots = self.canvas.dependent_records({self.x_ref})
        self.canvas.remove_data_dependents(snapshots)
        self.assertEqual(len(axes_modify._live_color_targets()), 1)
        self.canvas.restore_data_dependents(snapshots)
        self.assertEqual(len(axes_modify._live_color_targets()), 5)
        palette = builtin_palettes()[0]
        self.assertTrue(axes_modify.change_all_color(palette))

    def test_creation_cancel_and_failure_do_not_commit_cycle_or_recent(self):
        state = self.canvas.current_axes_mod.color_selector
        palette = PaletteDefinition("test:dialog", "Dialog", ("red", "blue"))
        state.activate(palette)

        cancelled = PyCurveDialog("Curve", self.window.figure_window)
        self.assertEqual(cancelled.color_input.color(), "#FF0000")
        cancelled.reject()
        self.assertEqual(state.next_index, 0)
        self.assertEqual(self.window.color_library.recent_colors, [])
        cancelled.deleteLater()

        failed = PyCurveDialog("Curve", self.window.figure_window)
        failed.expression_edit.setText("__import__('os')")
        with patch("code.widgets.title_bar.titlebar_dialog.py_chart_dialog.QMessageBox.warning"):
            failed.accept()
        self.assertEqual(state.next_index, 0)
        self.assertEqual(self.window.color_library.recent_colors, [])
        failed.close()
        failed.deleteLater()

        created = PyCurveDialog("Curve", self.window.figure_window)
        created.accept()
        self.assertEqual(state.next_index, 1)
        self.assertEqual(self.window.color_library.recent_colors, ["#FF0000"])
        created.close()
        created.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_batch_failure_rolls_back_artist_and_widget_colors(self):
        class FakeModifier:
            def __init__(self, color, fail_color=None):
                self.color = color
                self.fail_color = fail_color

            def update_color(self, color, *, redraw=True, refresh_legend=True):
                if color == self.fail_color:
                    raise RuntimeError("synthetic failure")
                self.color = color

            def get_color(self):
                return self.color

            def is_color_target_active(self):
                return True

        class FakeWidget:
            def __init__(self, color):
                self.color = color

            def set_color(self, color, *, emit=False):
                self.color = color

        first = FakeModifier("#010101")
        second = FakeModifier("#020202", fail_color="#0000FF")
        first_widget = FakeWidget(first.color)
        second_widget = FakeWidget(second.color)
        axes_modify = self.canvas.current_axes_mod
        axes_modify.register_color_target(first, first_widget)
        axes_modify.register_color_target(second, second_widget)
        palette = PaletteDefinition("test:rollback", "Rollback", ("red", "blue"))

        self.assertFalse(axes_modify.change_all_color(palette))
        self.assertEqual(first.color, "#010101")
        self.assertEqual(second.color, "#020202")
        self.assertEqual(first_widget.color, "#010101")
        self.assertEqual(second_widget.color, "#020202")
        self.assertIsNone(axes_modify.color_selector.active_palette)


if __name__ == "__main__":
    unittest.main()
