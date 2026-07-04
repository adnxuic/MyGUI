import os
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEST_TMP_DIR = Path(__file__).with_name("_tmp")
_TEST_TMP_DIR.mkdir(exist_ok=True)
os.environ["TEMP"] = str(_TEST_TMP_DIR)
os.environ["TMP"] = str(_TEST_TMP_DIR)
tempfile.tempdir = str(_TEST_TMP_DIR)

import numpy as np

from Qt_core import QApplication
from code.database.py_database import PyDatabase, databases
from code.excel_io import import_excel_into_table
from code.widgets.title_bar.titlebar_dialog.py_chart_dialog import PyFitDialog, PyPlotDialog, PyScatterDialog
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
        filename = _TEST_TMP_DIR / "gui_data_flow.xlsx"
        with zipfile.ZipFile(filename, "w") as workbook:
            workbook.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
            )
            workbook.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            workbook.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
            )
            workbook.writestr(
                "xl/workbook.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
            )
            workbook.writestr(
                "xl/styles.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium9" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>""",
            )
            workbook.writestr(
                "xl/worksheets/sheet1.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>10</v></c></row>
    <row r="2"><c r="A2"><v>2</v></c><c r="B2"><v>20</v></c></row>
    <row r="3"><c r="A3"><v>3</v></c><c r="B3"><v>30</v></c></row>
  </sheetData>
</worksheet>""",
            )
        return filename

    def add_canvas_axes(self):
        self.window.figure_window.add_figure(width=6.4, height=4.8, dpi=100, style="default", canva_name="smoke")
        canvas = self.window.figure_window.current_canva
        canvas.add_axes(nrows=1, ncols=1)
        return canvas

    def test_excel_import_can_create_plot_and_scatter_dialog_charts_then_switch_sources(self):
        filename = self.make_workbook_file()
        import_excel_into_table(filename, self.window.table)

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

    def test_matlab_fit_dialog_creates_connectable_fitting_curve(self):
        database = PyDatabase()
        PyDatabase.register_sheet("Data", "Sheet1", database)
        database.update_data(1, np.array([1.0, 2.0, 3.0]))
        database.update_data(2, np.array([2.0, 4.0, 6.0]))

        canvas = self.add_canvas_axes()
        dialog = PyFitDialog("fit", self.window.figure_window)
        dialog.matlab_button.setChecked(True)
        dialog.x_data_input.setCurrentText("Data/Sheet1/1")
        dialog.y_data_input.setCurrentText("Data/Sheet1/2")
        dialog.accept()
        self.app.processEvents()

        axes = canvas.current_axes
        self.assertEqual(len(axes.lines), 1)
        all_mod_widget = canvas.fig_modify_widget.fine_all_mod_widget(axes)
        fitting_box = all_mod_widget.cahrt_mod_window.boxs["fitting_box"]
        fitting_widget = fitting_box.widget(0)
        self.assertIs(self.window.fig_control_window.matlab_window.connect_widget, fitting_widget)

    def test_switching_multiple_canvases_and_axes_updates_current_references(self):
        self.window.figure_window.add_figure(width=4, height=3, dpi=80, style="default", canva_name="first")
        first_canvas = self.window.figure_window.current_canva
        first_canvas.add_axes(nrows=1, ncols=1)
        first_axes = first_canvas.current_axes

        self.window.figure_window.add_figure(width=5, height=4, dpi=80, style="default", canva_name="second")
        second_canvas = self.window.figure_window.current_canva
        second_canvas.add_axes(nrows=1, ncols=2)

        second_axes_button = None
        axes_btn_layout = second_canvas.fig_modify_widget.axes_btn_bar_layout
        for index in range(axes_btn_layout.count()):
            button = axes_btn_layout.itemAt(index).widget()
            if button is not None and button.text() == "axe2":
                second_axes_button = button
                break
        self.assertIsNotNone(second_axes_button)
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
