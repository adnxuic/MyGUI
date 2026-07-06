import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEST_TMP_DIR = Path(__file__).with_name("_tmp")
_TEST_TMP_DIR.mkdir(exist_ok=True)
os.environ["TEMP"] = str(_TEST_TMP_DIR)
os.environ["TMP"] = str(_TEST_TMP_DIR)
tempfile.tempdir = str(_TEST_TMP_DIR)

import numpy as np

from Qt_core import QApplication
from code.database.py_database import PyDatabase
from code.project_io import restore_project_snapshot, save_project_snapshot
from code.widgets.title_bar.titlebar_dialog.py_element_dialog import PyTextDialog
from main import MainWindow


@unittest.skip("legacy workspace-level project object tests; v3 uses one canvas and one table")
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
        interpolate_method = "B样条插值"

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
            k=2,
            samples=128,
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
            self.assertEqual(len(loaded_axes.lines[1].get_xdata()), 128)
            self.assertEqual(loaded_axes.texts[0].get_text(), "saved text")
            self.assertEqual(loaded_axes.texts[0].get_position(), (0.25, 0.75))

            snapshot = loaded_canvas.project_snapshot()
            self.assertEqual(snapshot["plots"][0]["x_data_name"], x_name)
            self.assertEqual(snapshot["scatters"][0]["marker"], "s")
            self.assertEqual(snapshot["interpolates"][0]["method"], interpolate_method)
            self.assertEqual(snapshot["interpolates"][0]["k"], 2)
            self.assertEqual(snapshot["interpolates"][0]["samples"], 128)
            self.assertIsNone(snapshot["interpolates"][0]["lam"])
            self.assertTrue(snapshot["interpolates"][0]["lam_auto"])
            self.assertEqual(snapshot["texts"][0]["fontsize"], 14.0)
            self.assertFalse(snapshot["texts"][0]["usetex"])
        finally:
            if loaded_window is not None:
                loaded_window.close()
            if project_file.exists():
                try:
                    os.remove(project_file)
                except PermissionError:
                    pass

    def test_global_text_dialog_save_load_edit_and_delete(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="global")
        canvas = self.window.figure_window.current_canva

        dialog = PyTextDialog(dialog_name="Text", figure_window=self.window.figure_window)
        dialog.global_button.setChecked(True)
        dialog.text_edit.setText("global text")
        dialog.x_input.setValue(0.35)
        dialog.y_input.setValue(0.82)
        dialog.font_input.setCurrentText("DejaVu Sans")
        dialog.font_size_input.setValue(18)
        dialog.accept()
        self.app.processEvents()

        self.assertEqual(len(canvas.fig.texts), 1)
        self.assertEqual(len(canvas.fig.axes), 0)
        self.assertEqual(canvas.project_texts[0]["scope"], "figure")
        self.assertNotIn("axes_index", canvas.project_texts[0])

        project_file = self.make_project_file()
        loaded_window = None
        try:
            save_project_snapshot(project_file, self.window.figure_window)
            loaded_window = MainWindow()
            restore_project_snapshot(project_file, figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_canvas = loaded_window.figure_window.tabwindow.widget(0)
            loaded_text = loaded_canvas.fig.texts[0]

            self.assertEqual(len(loaded_canvas.fig.texts), 1)
            self.assertEqual(len(loaded_canvas.fig.axes), 0)
            self.assertEqual(loaded_text.get_text(), "global text")
            self.assertEqual(loaded_text.get_position(), (0.35, 0.82))
            self.assertEqual(loaded_canvas.project_texts[0]["scope"], "figure")
            self.assertNotIn("axes_index", loaded_canvas.project_texts[0])

            figure_mod_widget = loaded_canvas.fig_modify_widget.figure_element_mod_widget
            text_box = figure_mod_widget.element_mod_window.boxs["text_box"]
            text_widget = text_box.widget(0)
            self.assertIs(figure_mod_widget.layout.itemAt(0).widget(), figure_mod_widget.element_btn_bar)
            self.assertIs(figure_mod_widget.layout.itemAt(1).widget(), figure_mod_widget.element_mod_window)

            text_widget.text_content.setPlainText("edited global")
            text_widget.font_input.setCurrentText("DejaVu Serif")
            text_widget.font_size_input.setValue(22)
            text_widget.text_x_pos.setValue(0.4)
            text_widget.text_y_pos.setValue(0.6)
            text_widget.set_text_content()
            text_widget.set_xy_position()
            self.app.processEvents()

            self.assertEqual(loaded_text.get_text(), "edited global")
            self.assertEqual(loaded_text.get_position(), (0.4, 0.6))
            self.assertIn("DejaVu Serif", loaded_text.get_fontfamily())
            self.assertEqual(loaded_text.get_fontsize(), 22.0)
            self.assertEqual(loaded_canvas.project_texts[0]["text"], "edited global")
            self.assertEqual(loaded_canvas.project_texts[0]["fontfamily"], "DejaVu Serif")
            self.assertEqual(loaded_canvas.project_texts[0]["x"], 0.4)
            self.assertEqual(loaded_canvas.project_texts[0]["y"], 0.6)
            self.assertEqual(loaded_canvas.project_texts[0]["fontsize"], 22.0)
            self.assertFalse(loaded_canvas.project_texts[0]["usetex"])

            text_box.delete_widget(0)
            self.app.processEvents()

            self.assertNotIn(loaded_text, loaded_canvas.fig.texts)
            self.assertEqual(loaded_canvas.project_texts, [])
        finally:
            if loaded_window is not None:
                loaded_window.close()
            if project_file.exists():
                try:
                    os.remove(project_file)
                except PermissionError:
                    pass


if __name__ == "__main__":
    unittest.main()


class ProjectObjectRoundTripV3Tests(unittest.TestCase):
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
        return temp_dir / "project_object_roundtrip_v3.mygui.json"

    def test_plot_scatter_and_text_save_load_v3_roundtrip(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default",
                                             canva_name="ProjectA")
        canvas = self.window.figure_window.current_canva
        subtable = self.window.table.current_subtable()
        table_view = subtable.get_table(0)
        for row, (x_value, y_value) in enumerate([(0, 1), (1, 2), (2, 1), (3, 3)]):
            table_view.model.setData(table_view.model.index(row, 0), str(x_value))
            table_view.model.setData(table_view.model.index(row, 1), str(y_value))
        self.window.table.save_current_table_to_database()

        x_name = "ProjectA/Sheet1/1"
        y_name = "ProjectA/Sheet1/2"
        x_data = PyDatabase.get_data(x_name)
        y_data = PyDatabase.get_data(y_name)
        canvas.add_axes(nrows=1, ncols=1)
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
        canvas.add_text(
            x=0.25,
            y=0.75,
            text="saved text",
            fontfamily="DejaVu Sans",
            fontsize=14,
        )

        project_file = self.make_project_file()
        save_project_snapshot(project_file, self.window.figure_window)
        loaded_window = MainWindow()
        try:
            restore_project_snapshot(project_file, table=loaded_window.table,
                                     figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_canvas = loaded_window.figure_window.tabwindow.widget(0)
            loaded_axes = loaded_canvas.fig.axes[0]
            self.assertEqual(loaded_canvas.project_name, "ProjectA")
            self.assertEqual(loaded_window.table.table_names(), ["ProjectA"])
            self.assertEqual(len(loaded_axes.lines), 1)
            self.assertEqual(len(loaded_axes.collections), 1)
            self.assertEqual(len(loaded_axes.texts), 1)
            self.assertEqual(loaded_axes.lines[0].get_label(), "saved plot")
            self.assertEqual(loaded_axes.collections[0].get_label(), "saved scatter")
            self.assertEqual(loaded_axes.texts[0].get_text(), "saved text")
        finally:
            loaded_window.close()

    def add_project_with_numeric_data(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default",
                                             canva_name="ProjectA")
        canvas = self.window.figure_window.current_canva
        subtable = self.window.table.current_subtable()
        table_view = subtable.get_table(0)
        values = [(0, 1), (1, 4), (2, 9), (3, 16)]
        for row, (x_value, y_value) in enumerate(values):
            table_view.model.setData(table_view.model.index(row, 0), str(x_value))
            table_view.model.setData(table_view.model.index(row, 1), str(y_value))
        self.window.table.save_current_table_to_database()
        canvas.add_axes(nrows=1, ncols=1)
        return canvas, "ProjectA/Sheet1/1", "ProjectA/Sheet1/2"

    def fit_widget_for(self, canvas):
        axes = canvas.fig.axes[0]
        all_mod_widget = canvas.fig_modify_widget.fine_all_mod_widget(axes)
        fitting_box = all_mod_widget.cahrt_mod_window.boxs["fitting_box"]
        return fitting_box.widget(0)

    def test_scipy_fit_save_load_v3_roundtrip(self):
        from code.database import scipy_fit_adapter

        canvas, x_name, y_name = self.add_project_with_numeric_data()
        x_data = PyDatabase.get_data(x_name)
        y_data = PyDatabase.get_data(y_name)
        canvas.add_fit_curve(
            x=x_data,
            y=y_data,
            color="#123456",
            label="saved fit",
            x_data_name=x_name,
            y_data_name=y_name,
            engine="Python",
        )
        fit_widget = self.fit_widget_for(canvas)
        fit_result = scipy_fit_adapter.fit_curve(x_data, y_data, "poly2")
        fit_widget.fit_type = "poly2"
        fit_widget.fit_options = None
        fit_widget.update_curve(fit_result, float(np.min(x_data)), float(np.max(x_data)))

        project_file = self.make_project_file()
        save_project_snapshot(project_file, self.window.figure_window)
        loaded_window = MainWindow()
        try:
            restore_project_snapshot(project_file, table=loaded_window.table,
                                     figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_canvas = loaded_window.figure_window.tabwindow.widget(0)
            loaded_axes = loaded_canvas.fig.axes[0]
            loaded_fit_widget = self.fit_widget_for(loaded_canvas)
            fit_record = loaded_canvas.project_snapshot()["fits"][0]

            self.assertEqual(len(loaded_axes.lines), 1)
            self.assertEqual(loaded_axes.lines[0].get_label(), "saved fit")
            self.assertEqual(fit_record["fit_type"], "poly2")
            self.assertIsNotNone(fit_record["fit_result"])
            self.assertEqual(loaded_fit_widget.result_model_label.text(), "Model: poly2")
            self.assertEqual(loaded_fit_widget.result_coeff_table.rowCount(), 3)
        finally:
            loaded_window.close()

    def test_unrun_fit_placeholder_save_load_v3_roundtrip(self):
        canvas, x_name, y_name = self.add_project_with_numeric_data()
        canvas.add_fit_curve(
            x=PyDatabase.get_data(x_name),
            y=PyDatabase.get_data(y_name),
            color="black",
            label="placeholder fit",
            x_data_name=x_name,
            y_data_name=y_name,
            engine="Python",
        )

        project_file = self.make_project_file()
        save_project_snapshot(project_file, self.window.figure_window)
        loaded_window = MainWindow()
        try:
            restore_project_snapshot(project_file, table=loaded_window.table,
                                     figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_canvas = loaded_window.figure_window.tabwindow.widget(0)
            loaded_fit = loaded_canvas.project_snapshot()["fits"][0]
            loaded_fit_widget = self.fit_widget_for(loaded_canvas)

            self.assertIsNone(loaded_fit["fit_result"])
            self.assertEqual(loaded_fit["expression"], "")
            self.assertEqual(loaded_fit_widget.result_model_label.text(), "Model: -")
        finally:
            loaded_window.close()

    def test_axes_state_save_load_v3_roundtrip(self):
        canvas, x_name, y_name = self.add_project_with_numeric_data()
        axes = canvas.fig.axes[0]
        canvas.add_plot(
            x=PyDatabase.get_data(x_name),
            y=PyDatabase.get_data(y_name),
            style="-",
            size=2.0,
            color="black",
            label="axis source",
            x_data_name=x_name,
            y_data_name=y_name,
        )
        axes.set_xlim(-1.0, 4.0)
        axes.set_ylim(-2.0, 20.0)
        axes.set_xlabel("Time")
        axes.set_ylabel("Signal")
        axes.xaxis.label.set_fontfamily("DejaVu Sans")
        axes.yaxis.label.set_fontfamily("DejaVu Sans")
        axes.xaxis.label.set_fontsize(15)
        axes.yaxis.label.set_fontsize(15)
        axes.xaxis.set_label_coords(0.4, -0.2)
        axes.yaxis.set_label_coords(-0.15, 0.6)
        axes.xaxis.set_visible(False)
        axes.spines["bottom"].set_visible(False)
        axes.spines["bottom"].set_position(("axes", 0.2))
        axes.legend(loc="upper left")

        project_file = self.make_project_file()
        save_project_snapshot(project_file, self.window.figure_window)
        loaded_window = MainWindow()
        try:
            restore_project_snapshot(project_file, table=loaded_window.table,
                                     figure_window=loaded_window.figure_window)
            self.app.processEvents()

            loaded_axes = loaded_window.figure_window.tabwindow.widget(0).fig.axes[0]

            self.assertAlmostEqual(loaded_axes.get_xlim()[0], -1.0)
            self.assertAlmostEqual(loaded_axes.get_xlim()[1], 4.0)
            self.assertAlmostEqual(loaded_axes.get_ylim()[0], -2.0)
            self.assertAlmostEqual(loaded_axes.get_ylim()[1], 20.0)
            self.assertEqual(loaded_axes.get_xlabel(), "Time")
            self.assertEqual(loaded_axes.get_ylabel(), "Signal")
            self.assertEqual(loaded_axes.xaxis.label.get_fontfamily()[0], "DejaVu Sans")
            self.assertEqual(float(loaded_axes.xaxis.label.get_fontsize()), 15.0)
            self.assertFalse(loaded_axes.xaxis.get_visible())
            self.assertFalse(loaded_axes.spines["bottom"].get_visible())
            self.assertEqual(loaded_axes.spines["bottom"].get_position(), ("axes", 0.2))
            self.assertIsNotNone(loaded_axes.get_legend())
        finally:
            loaded_window.close()
