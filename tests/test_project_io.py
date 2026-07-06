import os
import json
import unittest
from pathlib import Path

import numpy as np

from code.database.py_database import PyDatabase
from code.project_io import PROJECT_SCHEMA_VERSION, load_project_file, restore_project_snapshot, save_project_snapshot


class FakeFigureWindow:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or []
        self.loaded = None

    def project_snapshot(self):
        return self.snapshot

    def load_figure_snapshot(self, figures):
        self.loaded = figures


@unittest.skip("legacy workspace-level project schema tests; v3 uses one canvas and one table")
class ProjectIoTests(unittest.TestCase):
    def setUp(self):
        PyDatabase.clear()

    def tearDown(self):
        PyDatabase.clear()

    def make_project_file(self):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        return temp_dir / "project_roundtrip.mygui.json"

    def write_project(self, snapshot: dict):
        project_file = self.make_project_file()
        project_file.write_text(json.dumps(snapshot), encoding="utf-8")
        return project_file

    def remove_project_file(self, project_file):
        if project_file.exists():
            try:
                os.remove(project_file)
            except PermissionError:
                pass

    def test_save_and_restore_project_round_trip(self):
        database = PyDatabase()
        PyDatabase.register_sheet("Data", "SheetA", database)
        database.update_data(1, np.array([1.0, 2.0]))
        database.update_data(2, np.array([3.0, 4.0]))

        figure_snapshot = [{
            "name": "default",
            "style": "default",
            "dpi": 100.0,
            "size_inches": [6.4, 4.8],
            "axes_count": 1,
            "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
            "curves": [{
                "axes_index": 0,
                "expression": "sin(x)",
                "x_start": 0.0,
                "x_stop": 3.14,
                "style": "-",
                "color": "black",
                "label": "sin",
            }],
            "plots": [],
            "scatters": [],
            "interpolates": [],
            "texts": [],
        }]
        project_file = self.make_project_file()

        try:
            save_project_snapshot(project_file, FakeFigureWindow(figure_snapshot))
            PyDatabase.clear()
            loaded_figure = FakeFigureWindow()

            snapshot = restore_project_snapshot(project_file, figure_window=loaded_figure)

            np.testing.assert_allclose(PyDatabase.get_data("Data/SheetA/1"), np.array([1.0, 2.0]))
            np.testing.assert_allclose(PyDatabase.get_data("Data/SheetA/2"), np.array([3.0, 4.0]))
            self.assertEqual(snapshot["figures"], figure_snapshot)
            self.assertEqual(loaded_figure.loaded, figure_snapshot)
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_migrates_v1_figure_object_collections(self):
        project_file = self.make_project_file()
        project_file.write_text(
            """{
  "schema": "mygui-project",
  "schema_version": 1,
  "tables": {},
  "figures": [{
    "name": "legacy",
    "style": "default",
    "dpi": 100.0,
    "size_inches": [6.4, 4.8],
    "axes_count": 1,
    "axes_layouts": [],
    "curves": [{
      "axes_index": 0,
      "expression": "x",
      "x_start": 0.0,
      "x_stop": 1.0
    }]
  }]
}""",
            encoding="utf-8",
        )

        try:
            snapshot = load_project_file(project_file)

            self.assertEqual(snapshot["schema_version"], PROJECT_SCHEMA_VERSION)
            figure = snapshot["figures"][0]
            self.assertEqual(figure["curves"][0]["expression"], "x")
            self.assertEqual(figure["plots"], [])
            self.assertEqual(figure["scatters"], [])
            self.assertEqual(figure["interpolates"], [])
            self.assertEqual(figure["texts"], [])
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_accepts_utf8_bom_before_schema_migration(self):
        project_file = Path(__file__).with_name("fixtures") / "utf8_bom_project_v1.mygui.json"
        snapshot = load_project_file(project_file)

        self.assertEqual(snapshot["schema_version"], PROJECT_SCHEMA_VERSION)
        figure = snapshot["figures"][0]
        self.assertEqual(figure["name"], "bom-legacy")
        self.assertEqual(figure["plots"], [])
        self.assertEqual(figure["scatters"], [])
        self.assertEqual(figure["interpolates"], [])
        self.assertEqual(figure["texts"], [])

    def test_load_project_file_rejects_missing_plot_data_source(self):
        project_file = self.write_project({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "tables": {},
            "figures": [{
                "name": "bad-data",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
                "curves": [],
                "plots": [{
                    "axes_index": 0,
                    "x_data_name": "Data/Sheet1/1",
                    "y_data_name": "Data/Sheet1/2",
                }],
                "scatters": [],
                "interpolates": [],
                "texts": [],
            }],
        })

        try:
            with self.assertRaisesRegex(ValueError, "Missing data source.*Data/Sheet1/1"):
                load_project_file(project_file)
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_rejects_unknown_interpolate_method(self):
        project_file = self.write_project({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "tables": {
                "Data": {
                    "Sheet1": {
                        "1": [0.0, 1.0, 2.0],
                        "2": [1.0, 2.0, 3.0],
                    }
                }
            },
            "figures": [{
                "name": "bad-interpolate",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
                "curves": [],
                "plots": [],
                "scatters": [],
                "interpolates": [{
                    "axes_index": 0,
                    "x_data_name": "Data/Sheet1/1",
                    "y_data_name": "Data/Sheet1/2",
                    "method": "unknown-method",
                }],
                "texts": [],
            }],
        })

        try:
            with self.assertRaisesRegex(ValueError, "Unknown interpolation method.*unknown-method"):
                load_project_file(project_file)
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_accepts_interpolate_parameters(self):
        project_file = self.write_project({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "tables": {
                "Data": {
                    "Sheet1": {
                        "1": [0.0, 1.0, 2.0, 3.0, 4.0],
                        "2": [1.0, 2.0, 3.0, 2.0, 1.0],
                    }
                }
            },
            "figures": [{
                "name": "interpolate-params",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
                "curves": [],
                "plots": [],
                "scatters": [],
                "interpolates": [{
                    "axes_index": 0,
                    "x_data_name": "Data/Sheet1/1",
                    "y_data_name": "Data/Sheet1/2",
                    "method": "平滑样条",
                    "k": 3,
                    "samples": 250,
                    "lam": 0.25,
                    "lam_auto": False,
                }],
                "texts": [],
            }],
        })

        try:
            snapshot = load_project_file(project_file)

            interpolate = snapshot["figures"][0]["interpolates"][0]
            self.assertEqual(interpolate["samples"], 250)
            self.assertEqual(interpolate["lam"], 0.25)
            self.assertFalse(interpolate["lam_auto"])
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_rejects_invalid_interpolate_parameters(self):
        project_file = self.write_project({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "tables": {
                "Data": {
                    "Sheet1": {
                        "1": [0.0, 1.0, 2.0],
                        "2": [1.0, 2.0, 3.0],
                    }
                }
            },
            "figures": [{
                "name": "bad-interpolate-params",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
                "curves": [],
                "plots": [],
                "scatters": [],
                "interpolates": [{
                    "axes_index": 0,
                    "x_data_name": "Data/Sheet1/1",
                    "y_data_name": "Data/Sheet1/2",
                    "method": "线性插值",
                    "samples": 1,
                }],
                "texts": [],
            }],
        })

        try:
            with self.assertRaisesRegex(ValueError, "samples"):
                load_project_file(project_file)
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_rejects_invalid_axes_index(self):
        project_file = self.write_project({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "tables": {},
            "figures": [{
                "name": "bad-axes",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1, "start_index": 0, "count": 1}],
                "curves": [],
                "plots": [],
                "scatters": [],
                "interpolates": [],
                "texts": [{
                    "axes_index": 2,
                    "x": 0.5,
                    "y": 0.5,
                    "text": "outside",
                }],
            }],
        })

        try:
            with self.assertRaisesRegex(ValueError, r"axes_index.*outside axes_count 1"):
                load_project_file(project_file)
        finally:
            self.remove_project_file(project_file)

    def test_load_project_file_accepts_figure_text_without_axes_index(self):
        project_file = Path(__file__).with_name("fixtures") / "figure_text_without_axes.mygui.json"
        snapshot = load_project_file(project_file)

        text_record = snapshot["figures"][0]["texts"][0]
        self.assertEqual(text_record["scope"], "figure")
        self.assertFalse(text_record["usetex"])
        self.assertNotIn("axes_index", text_record)


if __name__ == "__main__":
    unittest.main()


class FakeV3Canvas:
    def __init__(self, name="ProjectA", figure=None):
        self.project_name = name
        self.project_table_name = name
        self.project_path = None
        self._figure = figure or {
            "name": name,
            "style": "default",
            "dpi": 100.0,
            "size_inches": [6.4, 4.8],
            "axes_count": 0,
            "axes_layouts": [],
            "curves": [],
            "plots": [],
            "scatters": [],
            "interpolates": [],
            "texts": [],
        }

    def project_snapshot(self):
        return dict(self._figure)


class FakeV3FigureWindow:
    def __init__(self, canvas=None):
        self.current_canva = canvas or FakeV3Canvas()
        self.loaded = []
        self.names = set()
        if self.current_canva is not None:
            self.names.add(self.current_canva.project_name)

    def has_project_name(self, name):
        return name in self.names and (
            self.current_canva is None or name != self.current_canva.project_name
        )

    def load_project_figure_snapshot(self, figure, project_name, project_path=None):
        self.loaded.append((figure, project_name, project_path))
        self.names.add(project_name)


class ProjectIoV3Tests(unittest.TestCase):
    def setUp(self):
        PyDatabase.clear()
        self.temp_dir = Path(__file__).with_name("_tmp")
        self.temp_dir.mkdir(exist_ok=True)

    def tearDown(self):
        PyDatabase.clear()

    def project_file(self, name="project_v3.mygui.json"):
        return self.temp_dir / name

    def register_project_table(self, name="ProjectA"):
        database = PyDatabase()
        PyDatabase.register_sheet(name, "Sheet1", database)
        database.update_data(1, np.array([1.0, 2.0]))
        database.update_data(2, np.array([3.0, 4.0]))

    def test_save_and_load_v3_single_canvas_single_table(self):
        self.register_project_table()
        project_file = self.project_file()

        save_project_snapshot(project_file, FakeV3FigureWindow(FakeV3Canvas("ProjectA")))
        snapshot = load_project_file(project_file)

        self.assertEqual(snapshot["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(snapshot["name"], "ProjectA")
        self.assertEqual(snapshot["table"]["name"], "ProjectA")
        self.assertEqual(snapshot["figure"]["name"], "ProjectA")
        self.assertEqual(snapshot["table"]["sheets"]["Sheet1"]["1"], [1.0, 2.0])

    def test_restore_v3_appends_single_project_to_database_and_figure_window(self):
        self.register_project_table()
        project_file = self.project_file("restore_v3.mygui.json")
        save_project_snapshot(project_file, FakeV3FigureWindow(FakeV3Canvas("ProjectA")))
        PyDatabase.clear()
        loaded_window = FakeV3FigureWindow(canvas=None)

        restore_project_snapshot(project_file, figure_window=loaded_window)

        np.testing.assert_allclose(PyDatabase.get_data("ProjectA/Sheet1/1"), np.array([1.0, 2.0]))
        self.assertEqual(loaded_window.loaded[0][1], "ProjectA")

    def test_load_rejects_legacy_schema(self):
        project_file = self.project_file("legacy_v2.mygui.json")
        project_file.write_text(json.dumps({
            "schema": "mygui-project",
            "schema_version": 2,
            "tables": {},
            "figures": [],
        }), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Unsupported project schema version"):
            load_project_file(project_file)

    def test_load_rejects_cross_table_data_reference(self):
        project_file = self.project_file("bad_cross_table.mygui.json")
        project_file.write_text(json.dumps({
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": "ProjectA",
            "table": {
                "name": "ProjectA",
                "sheets": {"Sheet1": {"1": [1.0], "2": [2.0]}},
            },
            "figure": {
                "name": "ProjectA",
                "style": "default",
                "dpi": 100.0,
                "size_inches": [6.4, 4.8],
                "axes_count": 1,
                "axes_layouts": [{"nrows": 1, "ncols": 1}],
                "curves": [],
                "plots": [{
                    "axes_index": 0,
                    "x_data_name": "Other/Sheet1/1",
                    "y_data_name": "ProjectA/Sheet1/2",
                }],
                "scatters": [],
                "interpolates": [],
                "texts": [],
            },
        }), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Missing data source"):
            load_project_file(project_file)

    def v3_snapshot(self, figure_overrides=None):
        figure = {
            "name": "ProjectA",
            "style": "default",
            "dpi": 100.0,
            "size_inches": [6.4, 4.8],
            "axes_count": 1,
            "axes_layouts": [{"nrows": 1, "ncols": 1}],
            "axes": [],
            "curves": [],
            "plots": [],
            "scatters": [],
            "interpolates": [],
            "fits": [],
            "texts": [],
        }
        if figure_overrides:
            figure.update(figure_overrides)
        return {
            "schema": "mygui-project",
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": "ProjectA",
            "table": {
                "name": "ProjectA",
                "sheets": {"Sheet1": {"1": [1.0, 2.0], "2": [2.0, 5.0]}},
            },
            "figure": figure,
        }

    def test_load_accepts_v3_fit_and_axes_records(self):
        project_file = self.project_file("fit_axes_ok.mygui.json")
        project_file.write_text(json.dumps(self.v3_snapshot({
            "axes": [{
                "index": 0,
                "xlim": [0.0, 3.0],
                "ylim": [-1.0, 6.0],
                "xlabel": "x",
                "ylabel": "y",
                "label_fontfamily": "DejaVu Sans",
                "label_fontsize": 13.0,
                "x_label_position": [0.5, -0.1],
                "y_label_position": [-0.1, 0.5],
                "xaxis_visible": True,
                "yaxis_visible": True,
                "spines": {"bottom": {"visible": True, "position": ["axes", 0.2]}},
                "legend": {"visible": True, "loc": "upper left"},
            }],
            "fits": [{
                "axes_index": 0,
                "x_data_name": "ProjectA/Sheet1/1",
                "y_data_name": "ProjectA/Sheet1/2",
                "engine": "Python",
                "fit_type": "poly1",
                "fit_options": None,
                "fit_result": {
                    "value_expression": "1.0*x+1.0",
                    "show_expression": "1.0*x+1.0",
                    "formula": "p1*x + p2",
                    "fit_type": "poly1",
                    "coefficients": [{"name": "p1", "value": 1.0, "lower": 0.0, "upper": 2.0}],
                    "goodness": {"sse": 0.0, "rsquare": 1.0, "dfe": 1.0, "adjrsquare": 1.0, "rmse": 0.0},
                    "confidence_level": 0.95,
                    "engine": "Python",
                },
                "expression": "1.0*x+1.0",
                "x_start": 1.0,
                "x_stop": 2.0,
                "style": "-",
                "color": "black",
                "label": "fit",
            }],
        })), encoding="utf-8")

        snapshot = load_project_file(project_file)

        self.assertEqual(snapshot["figure"]["fits"][0]["fit_type"], "poly1")
        self.assertEqual(snapshot["figure"]["axes"][0]["xlabel"], "x")

    def test_load_rejects_cross_table_fit_reference(self):
        project_file = self.project_file("bad_fit_cross_table.mygui.json")
        project_file.write_text(json.dumps(self.v3_snapshot({
            "fits": [{
                "axes_index": 0,
                "x_data_name": "Other/Sheet1/1",
                "y_data_name": "ProjectA/Sheet1/2",
                "engine": "Python",
                "fit_type": None,
                "fit_options": None,
                "fit_result": None,
                "expression": "",
                "x_start": 1.0,
                "x_stop": 2.0,
                "style": "-",
                "color": "black",
                "label": "fit",
            }],
        })), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Missing data source"):
            load_project_file(project_file)

    def test_load_rejects_invalid_fit_engine(self):
        project_file = self.project_file("bad_fit_engine.mygui.json")
        project_file.write_text(json.dumps(self.v3_snapshot({
            "fits": [{
                "axes_index": 0,
                "x_data_name": "ProjectA/Sheet1/1",
                "y_data_name": "ProjectA/Sheet1/2",
                "engine": "BadEngine",
                "fit_type": None,
                "fit_options": None,
                "fit_result": None,
                "expression": "",
                "x_start": 1.0,
                "x_stop": 2.0,
                "style": "-",
                "color": "black",
                "label": "fit",
            }],
        })), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid project field .*engine"):
            load_project_file(project_file)

    def test_load_rejects_invalid_axes_state(self):
        project_file = self.project_file("bad_axes_state.mygui.json")
        project_file.write_text(json.dumps(self.v3_snapshot({
            "axes": [{
                "index": 1,
                "xlim": [0.0, 0.0],
            }],
        })), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "figure.axes\\[0\\].index"):
            load_project_file(project_file)

        project_file.write_text(json.dumps(self.v3_snapshot({
            "axes": [{
                "index": 0,
                "xlim": [0.0, 0.0],
            }],
        })), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "figure.axes\\[0\\].xlim"):
            load_project_file(project_file)
