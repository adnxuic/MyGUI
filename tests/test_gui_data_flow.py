import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import openpyxl

from Qt_core import QApplication
from code.database.py_database import PyDatabase, databases
from code.excel_io import import_excel_into_table
from code.widgets.title_bar.titlebar_dialog.py_chart_dialog import PyPlotDialog, PyScatterDialog
from main import MainWindow


class GuiDataFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PyDatabase.clear()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        PyDatabase.clear()

    def make_workbook_file(self):
        temp_dir = Path(__file__).with_name("_tmp")
        temp_dir.mkdir(exist_ok=True)
        filename = temp_dir / "gui_data_flow.xlsx"

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append([1, 10])
        sheet.append([2, 20])
        sheet.append([3, 30])
        workbook.save(filename)
        workbook.close()
        return filename

    def add_canvas_axes(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="smoke")
        canvas = self.window.figure_window.current_canva
        canvas.add_axes(nrows=1, ncols=1)
        return canvas

    def test_excel_import_can_create_plot_and_scatter_dialog_charts_then_switch_sources(self):
        filename = self.make_workbook_file()
        try:
            import_excel_into_table(filename, self.window.table)
        finally:
            os.remove(filename)

        canvas = self.add_canvas_axes()
        x_name = "Table2/Sheet1/1"
        y_name = "Table2/Sheet1/2"

        plot_dialog = PyPlotDialog("plot", self.window.figure_window)
        plot_dialog.x_data_input.setCurrentText(x_name)
        plot_dialog.y_data_input.setCurrentText(y_name)
        plot_dialog.accept()

        scatter_dialog = PyScatterDialog("scatter", self.window.figure_window)
        scatter_dialog.x_data_input.setCurrentText(x_name)
        scatter_dialog.y_data_input.setCurrentText(y_name)
        scatter_dialog.accept()

        axes = canvas.current_axes
        self.assertEqual(len(axes.lines), 1)
        self.assertEqual(len(axes.collections), 1)

        replacement = PyDatabase()
        PyDatabase.register_sheet("Replacement", "Sheet1", replacement)
        replacement.update_data(1, np.array([10.0, 20.0, 30.0]))
        replacement.update_data(2, np.array([100.0, 200.0, 300.0]))
        PyDatabase.unregister_table("Table2")
        self.assertFalse(PyDatabase.has_data(x_name))

        all_mod_widget = canvas.fig_modify_widget.fine_all_mod_widget(axes)
        plot_widget = all_mod_widget.cahrt_mod_window.boxs["plot_box"].widget(0)
        scatter_widget = all_mod_widget.cahrt_mod_window.boxs["scatter_box"].widget(0)

        plot_widget.data_choice_widget.update_data()
        scatter_widget.data_choice_widget.update_data()
        plot_widget.data_choice_widget.set_x_data("Replacement/Sheet1/1")
        plot_widget.data_choice_widget.set_y_data("Replacement/Sheet1/2")
        scatter_widget.data_choice_widget.set_x_data("Replacement/Sheet1/1")
        scatter_widget.data_choice_widget.set_y_data("Replacement/Sheet1/2")
        plot_widget.x_data_change()
        plot_widget.y_data_change()
        scatter_widget.x_data_change()
        scatter_widget.y_data_change()
        self.app.processEvents()

        np.testing.assert_allclose(axes.lines[0].get_xdata(), np.array([10.0, 20.0, 30.0]))
        np.testing.assert_allclose(axes.lines[0].get_ydata(), np.array([100.0, 200.0, 300.0]))
        np.testing.assert_allclose(axes.collections[0].get_offsets()[:, 0], np.array([10.0, 20.0, 30.0]))
        np.testing.assert_allclose(axes.collections[0].get_offsets()[:, 1], np.array([100.0, 200.0, 300.0]))

        callbacks = databases["Replacement"]["Sheet1"].data
        self.assertIn(id(axes.lines[0]), callbacks["1"][1])
        self.assertIn(id(axes.collections[0]), callbacks["1"][1])

    def test_switching_multiple_canvases_and_axes_updates_current_references(self):
        self.window.figure_window.add_figure(width=4, height=3, dpi=80, style="default", canva_name="first")
        first_canvas = self.window.figure_window.current_canva
        first_canvas.add_axes(nrows=1, ncols=1)
        first_axes = first_canvas.current_axes

        self.window.figure_window.add_figure(width=5, height=4, dpi=80, style="default", canva_name="second")
        second_canvas = self.window.figure_window.current_canva
        second_canvas.add_axes(nrows=1, ncols=2)

        second_axes_button = second_canvas.fig_modify_widget.axes_btn_bar_layout.itemAt(1).widget()
        second_axes_button.click()
        self.app.processEvents()

        self.assertIs(second_canvas.current_axes, second_canvas.fig.axes[1])
        self.assertIs(second_canvas.current_axes_mod, second_canvas.axes_mods[1])

        self.window.figure_window.tabwindow.setCurrentIndex(0)
        self.app.processEvents()

        self.assertIs(self.window.figure_window.current_canva, first_canvas)
        self.assertIs(self.window.figure_window.current_fig_modify_widget, first_canvas.fig_modify_widget)
        self.assertIs(first_canvas.current_axes, first_axes)

        self.window.figure_window.tabwindow.setCurrentIndex(1)
        self.app.processEvents()

        self.assertIs(self.window.figure_window.current_canva, second_canvas)
        self.assertIs(self.window.figure_window.current_fig_modify_widget, second_canvas.fig_modify_widget)
        self.assertIs(second_canvas.current_axes, second_canvas.fig.axes[1])


if __name__ == "__main__":
    unittest.main()
