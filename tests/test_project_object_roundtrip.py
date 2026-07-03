import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from Qt_core import QApplication
from code.database.interpolate_func import interpolate_dict
from code.database.py_database import PyDatabase
from code.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class ProjectObjectRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PyDatabase.clear()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        PyDatabase.clear()

    def make_project_file(self):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        return temp_dir / "project_object_roundtrip.mygui.json"

    def register_data(self):
        database = PyDatabase()
        PyDatabase.register_sheet("Data", "Sheet1", database)
        database.update_data(1, np.array([0.0, 1.0, 2.0, 3.0]))
        database.update_data(2, np.array([1.0, 2.0, 1.0, 3.0]))
        return "Data/Sheet1/1", "Data/Sheet1/2"

    def add_canvas_axes(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="objects")
        canvas = self.window.figure_window.current_canva
        canvas.add_axes(nrows=1, ncols=1)
        return canvas

    def test_plot_scatter_interpolate_and_text_save_load_roundtrip(self):
        x_name, y_name = self.register_data()
        x_data = PyDatabase.get_data(x_name)
        y_data = PyDatabase.get_data(y_name)
        canvas = self.add_canvas_axes()
        interpolate_method = next(iter(interpolate_dict.keys()))

        canvas.add_plot(
            x=x_data,
            y=y_data,
            style="-",
            size=3.0,
            color="#ff0000",
            label="saved plot",
            x_data_name=x_name,
            y_data_name=y_name,
        )
        canvas.add_scatter(
            x=x_data,
            y=y_data,
            size=25,
            color="#00ff00",
            marker="s",
            label="saved scatter",
            x_data_name=x_name,
            y_data_name=y_name,
        )
        canvas.add_interpolate_curve(
            x=x_data,
            y=y_data,
            x_name=x_name,
            y_name=y_name,
            method=interpolate_method,
            color="#0000ff",
            label="saved interpolate",
        )
        canvas.add_text(
            x=0.25,
            y=0.75,
            text="saved text",
            fontfamily="DejaVu Sans",
            fontsize=14,
        )

        project_file = self.make_project_file()
        loaded_window = None
        try:
            save_project_snapshot(project_file, self.window.figure_window)
            loaded_window = MainWindow()
            restore_project_snapshot(project_file, figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_canvas = loaded_window.figure_window.tabwindow.widget(0)
            loaded_axes = loaded_canvas.fig.axes[0]

            self.assertEqual(len(loaded_axes.lines), 2)
            self.assertEqual(len(loaded_axes.collections), 1)
            self.assertEqual(len(loaded_axes.texts), 1)

            np.testing.assert_allclose(loaded_axes.lines[0].get_xdata(), x_data)
            np.testing.assert_allclose(loaded_axes.lines[0].get_ydata(), y_data)
            np.testing.assert_allclose(loaded_axes.collections[0].get_offsets()[:, 0], x_data)
            np.testing.assert_allclose(loaded_axes.collections[0].get_offsets()[:, 1], y_data)

            self.assertEqual(loaded_axes.lines[0].get_label(), "saved plot")
            self.assertEqual(loaded_axes.collections[0].get_label(), "saved scatter")
            self.assertEqual(loaded_axes.lines[1].get_label(), "saved interpolate")
            self.assertEqual(loaded_axes.texts[0].get_text(), "saved text")
            self.assertEqual(loaded_axes.texts[0].get_position(), (0.25, 0.75))

            snapshot = loaded_canvas.project_snapshot()
            self.assertEqual(snapshot["plots"][0]["x_data_name"], x_name)
            self.assertEqual(snapshot["scatters"][0]["marker"], "s")
            self.assertEqual(snapshot["interpolates"][0]["method"], interpolate_method)
            self.assertEqual(snapshot["texts"][0]["fontsize"], 14.0)
        finally:
            if loaded_window is not None:
                loaded_window.close()
            if project_file.exists():
                os.remove(project_file)


if __name__ == "__main__":
    unittest.main()
