import unittest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from Qt_core import QApplication
from code.database.interpolate_func import interpolate_dict
from code.database.py_database import PyDatabase, databases
from main import MainWindow


class ChartLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PyDatabase.clear()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        PyDatabase.clear()

    def register_data(self, table_name="Data", sheet_name="Sheet1"):
        database = PyDatabase()
        PyDatabase.register_sheet(table_name, sheet_name, database)
        database.update_data(1, np.array([0.0, 1.0, 2.0, 3.0]))
        database.update_data(2, np.array([1.0, 2.0, 1.0, 3.0]))
        return database, f"{table_name}/{sheet_name}/1", f"{table_name}/{sheet_name}/2"

    def add_canvas_axes(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default",
                                             canva_name="lifecycle")
        canvas = self.window.figure_window.current_canva
        canvas.add_axes(nrows=1, ncols=1)
        return canvas

    def add_objects(self, canvas, x_name, y_name):
        x_data = PyDatabase.get_data(x_name)
        y_data = PyDatabase.get_data(y_name)
        method = next(iter(interpolate_dict.keys()))

        canvas.add_plot(
            x=x_data,
            y=y_data,
            style="-",
            size=3.0,
            color="#ff0000",
            label="plot",
            x_data_name=x_name,
            y_data_name=y_name,
        )
        canvas.add_scatter(
            x=x_data,
            y=y_data,
            size=20,
            color="#00ff00",
            marker="o",
            label="scatter",
            x_data_name=x_name,
            y_data_name=y_name,
        )
        canvas.add_interpolate_curve(
            x=x_data,
            y=y_data,
            x_name=x_name,
            y_name=y_name,
            method=method,
            color="#0000ff",
            label="interpolate",
        )
        canvas.add_text(
            x=0.2,
            y=0.8,
            text="label",
            fontfamily="DejaVu Sans",
            fontsize=12,
        )
        return method

    def get_mod_widgets(self, canvas):
        all_mod_widget = canvas.fig_modify_widget.fine_all_mod_widget(canvas.current_axes)
        return {
            "plot": all_mod_widget.cahrt_mod_window.boxs["plot_box"].widget(0),
            "scatter": all_mod_widget.cahrt_mod_window.boxs["scatter_box"].widget(0),
            "interpolate": all_mod_widget.cahrt_mod_window.boxs["interpolate_box"].widget(0),
            "text": all_mod_widget.element_mod_window.boxs["text_box"].widget(0),
            "plot_box": all_mod_widget.cahrt_mod_window.boxs["plot_box"],
            "scatter_box": all_mod_widget.cahrt_mod_window.boxs["scatter_box"],
            "interpolate_box": all_mod_widget.cahrt_mod_window.boxs["interpolate_box"],
            "text_box": all_mod_widget.element_mod_window.boxs["text_box"],
        }

    def assert_column_callbacks_empty(self, database):
        self.assertEqual(database.data["1"][1], {})
        self.assertEqual(database.data["2"][1], {})

    def test_delete_chart_objects_removes_artists_project_records_and_callbacks(self):
        database, x_name, y_name = self.register_data()
        canvas = self.add_canvas_axes()
        self.add_objects(canvas, x_name, y_name)
        axes = canvas.current_axes
        widgets = self.get_mod_widgets(canvas)

        plot_line = widgets["plot"].curve_modify.line
        scatter_artist = widgets["scatter"].curve_modify.scatter
        interpolate_line = widgets["interpolate"].modify.line
        text_artist = widgets["text"].text_modify.text
        plot_id = id(plot_line)
        scatter_id = id(scatter_artist)
        interpolate_id = id(interpolate_line)

        self.assertIn(plot_id, database.data["1"][1])
        self.assertIn(scatter_id, database.data["1"][1])
        self.assertIn(interpolate_id, database.data["1"][1])

        widgets["plot_box"].delete_widget(0)
        self.app.processEvents()
        self.assertNotIn(plot_line, axes.lines)
        self.assertEqual(canvas.project_plots, [])
        self.assertNotIn(plot_id, database.data["1"][1])
        self.assertNotIn(plot_id, database.data["2"][1])

        widgets["scatter_box"].delete_widget(0)
        self.app.processEvents()
        self.assertNotIn(scatter_artist, axes.collections)
        self.assertEqual(canvas.project_scatters, [])
        self.assertNotIn(scatter_id, database.data["1"][1])
        self.assertNotIn(scatter_id, database.data["2"][1])

        widgets["interpolate_box"].delete_widget(0)
        self.app.processEvents()
        self.assertNotIn(interpolate_line, axes.lines)
        self.assertEqual(canvas.project_interpolates, [])
        self.assertNotIn(interpolate_id, database.data["1"][1])
        self.assertNotIn(interpolate_id, database.data["2"][1])

        widgets["text_box"].delete_widget(0)
        self.app.processEvents()
        self.assertNotIn(text_artist, axes.texts)
        self.assertEqual(canvas.project_texts, [])
        self.assert_column_callbacks_empty(database)

    def test_unregister_sheet_clears_callbacks_and_existing_widgets_can_reconnect(self):
        old_database, x_name, y_name = self.register_data()
        canvas = self.add_canvas_axes()
        self.add_objects(canvas, x_name, y_name)
        widgets = self.get_mod_widgets(canvas)
        plot_id = id(widgets["plot"].curve_modify.line)
        scatter_id = id(widgets["scatter"].curve_modify.scatter)

        self.assertIn(plot_id, old_database.data["1"][1])
        self.assertIn(scatter_id, old_database.data["1"][1])

        PyDatabase.unregister_sheet("Data", "Sheet1")
        self.assertFalse(PyDatabase.has_data(x_name))
        self.assert_column_callbacks_empty(old_database)

        new_database, new_x_name, new_y_name = self.register_data("Replacement", "Sheet1")
        for widget in (widgets["plot"], widgets["scatter"]):
            widget.data_choice_widget.update_data()
            widget.data_choice_widget.set_x_data(new_x_name)
            widget.data_choice_widget.set_y_data(new_y_name)
            widget.x_data_change()
            widget.y_data_change()
        self.app.processEvents()

        self.assertIn(plot_id, new_database.data["1"][1])
        self.assertIn(plot_id, new_database.data["2"][1])
        self.assertIn(scatter_id, new_database.data["1"][1])
        self.assertIn(scatter_id, new_database.data["2"][1])
        self.assert_column_callbacks_empty(old_database)

    def test_unregister_table_clears_callbacks_and_interpolate_widget_still_edits(self):
        old_database, x_name, y_name = self.register_data()
        canvas = self.add_canvas_axes()
        method = self.add_objects(canvas, x_name, y_name)
        widgets = self.get_mod_widgets(canvas)
        interpolate_widget = widgets["interpolate"]
        interpolate_id = id(interpolate_widget.modify.line)

        self.assertIn(interpolate_id, old_database.data["1"][1])

        PyDatabase.unregister_table("Data")
        self.assertNotIn("Data", databases)
        self.assert_column_callbacks_empty(old_database)

        interpolate_widget.color_change("#123456")
        interpolate_widget.legend_input.setText("after table delete")
        interpolate_widget.modify.update_interpolate(method, 3)
        self.app.processEvents()

        self.assertEqual(interpolate_widget.modify.line.get_color(), "#123456")
        self.assertEqual(interpolate_widget.modify.line.get_label(), "after table delete")
        self.assert_column_callbacks_empty(old_database)


if __name__ == "__main__":
    unittest.main()
