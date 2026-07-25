import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication

from code.database import ColumnRef
from code.database.interpolate_func import interpolate_dict
from code.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class ProjectObjectRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "objects.mygui.json"
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def test_data_objects_and_text_roundtrip_with_stable_ids(self):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ProjectA"
        )
        canvas = self.window.figure_window.current_canva
        canvas.add_axes()
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [[0, 1], [1, 2], [2, 4], [3, 8]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        canvas.add_plot(line_pair.x, line_pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        canvas.add_scatter(valid_pair.x, valid_pair.y, 20, "red", "o", "scatter", x_ref, y_ref)
        canvas.add_curve("x", 0, 3, "-", "green", "curve")
        linear_method = list(interpolate_dict)[2]
        canvas.add_interpolate_curve(
            valid_pair.x, valid_pair.y, x_ref, y_ref, linear_method, samples=64, label="interpolate"
        )
        canvas.add_fit_curve(
            valid_pair.x, valid_pair.y, "blue", "fit", x_ref, y_ref,
            fit_type="poly2", expression="x**2", x_start=0, x_stop=3,
            fit_result={"formula": "x**2", "coefficients": [], "goodness": {}},
        )
        canvas.add_text(0.25, 0.75, "axes text", "DejaVu Sans", 12, record_project=True)
        canvas.add_global_text(0.5, 0.5, "figure text", "DejaVu Sans", 14, record_project=True)

        object_ids = {
            record["object_id"]
            for collection in (canvas.project_plots, canvas.project_scatters,
                               canvas.project_interpolates, canvas.project_fits)
            for record in collection
        }
        save_project_snapshot(self.path, self.window.figure_window)

        loaded = MainWindow()
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            restored = loaded.figure_window.current_canva
            restored_ids = {
                record["object_id"]
                for collection in (restored.project_plots, restored.project_scatters,
                                   restored.project_interpolates, restored.project_fits)
                for record in collection
            }
            self.assertEqual(restored_ids, object_ids)
            self.assertEqual(len(restored.project_plots), 1)
            self.assertEqual(len(restored.project_scatters), 1)
            self.assertEqual(len(restored.project_interpolates), 1)
            self.assertEqual(len(restored.project_fits), 1)
            self.assertEqual(restored.project_fits[0]["color"], "#0000FF")
            restored_order = [
                target.order
                for target, _setter, _getter, _sync
                in restored.current_axes_mod._live_color_targets()
            ]
            self.assertEqual(restored_order, [0, 1, 2, 3, 4])
            self.assertEqual(len(restored.project_texts), 2)
        finally:
            loaded.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
