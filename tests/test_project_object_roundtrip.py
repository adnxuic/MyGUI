import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from Qt_core import QApplication
from code.database.interpolate_func import interpolate_dict
from code.database.py_database import PyDatabase
from code.project_io import restore_project_snapshot, save_project_snapshot
from code.widgets.title_bar.titlebar_dialog.py_element_dialog import PyTextDialog
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
