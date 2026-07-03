import os
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


class ProjectIoTests(unittest.TestCase):
    def setUp(self):
        PyDatabase.clear()

    def tearDown(self):
        PyDatabase.clear()

    def make_project_file(self):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        return temp_dir / "project_roundtrip.mygui.json"

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
            if project_file.exists():
                os.remove(project_file)

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
    "curves": []
  }]
}""",
            encoding="utf-8",
        )

        try:
            snapshot = load_project_file(project_file)

            self.assertEqual(snapshot["schema_version"], PROJECT_SCHEMA_VERSION)
            figure = snapshot["figures"][0]
            self.assertEqual(figure["plots"], [])
            self.assertEqual(figure["scatters"], [])
            self.assertEqual(figure["interpolates"], [])
            self.assertEqual(figure["texts"], [])
        finally:
            if project_file.exists():
                os.remove(project_file)


if __name__ == "__main__":
    unittest.main()
