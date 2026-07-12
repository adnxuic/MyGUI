import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from Qt_core import QApplication, QGuiApplication, QInputDialog, QMessageBox, Qt

from code.database import ColumnRef
from main import MainWindow


class GuiDataFlowV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def add_project(self, name="ProjectA"):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name=name
        )
        canvas = self.window.figure_window.current_canva
        canvas.add_axes()
        view = self.window.table.current_subtable().get_table(0)
        model = view.table_model
        for row, (x, y) in enumerate([(1, 10), (2, 20), (3, 30)]):
            model.setData(model.index(row, 0), str(x), Qt.EditRole)
            model.setData(model.index(row, 1), str(y), Qt.EditRole)
        sheet = model.sheet
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[1].id)
        return canvas, view, x_ref, y_ref

    def test_startup_and_project_switching_use_repository_ids(self):
        self.assertEqual(self.window.table.table_names(), [])
        first, *_ = self.add_project("First")
        second, *_ = self.add_project("Second")
        self.window.figure_window.tabwindow.setCurrentWidget(first)
        self.app.processEvents()
        self.assertEqual(self.window.table.current_project_id, first.project_id)
        self.window.figure_window.tabwindow.setCurrentWidget(second)
        self.app.processEvents()
        self.assertEqual(self.window.table.current_table_name, "Second")

    def test_narrow_window_keeps_canvas_visible_and_table_near_default_width(self):
        self.window.showNormal()
        self.window.resize(1170, 800)
        self.app.processEvents()

        self.assertGreaterEqual(self.window.figure_window.width(), 400)
        self.assertGreaterEqual(self.window.table.width(), 240)
        self.assertLessEqual(self.window.table.width(), 460)
        self.assertGreaterEqual(self.window.fig_control_window.width(), 240)
        self.assertLessEqual(self.window.fig_control_window.width(), 480)
        left_width = self.window.left_layout.geometry().width()
        self.assertEqual(self.window.title_bar.width(), left_width)
        self.assertEqual(self.window.bottom_bar.width(), left_width)
        self.assertEqual(self.window.title_bar.selector_style_bar.width(), left_width)

    def test_one_cell_edit_refreshes_plot_and_draws_canvas_once(self):
        canvas, view, x_ref, y_ref = self.add_project()
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        line = canvas.fig.axes[0].lines[0]
        canvas.fig.canvas.draw_idle = Mock()

        view.table_model.setData(view.table_model.index(1, 1), "25", Qt.EditRole)

        np.testing.assert_allclose(line.get_ydata()[:3], [10, 25, 30])
        canvas.fig.canvas.draw_idle.assert_called_once()

    def test_missing_rows_break_lines_and_filter_scatter_pairs(self):
        canvas, view, x_ref, y_ref = self.add_project()
        view.table_model.setData(view.table_model.index(1, 0), "", Qt.EditRole)
        line_pair = self.window.repository.line_pair(x_ref, y_ref)
        valid_pair = self.window.repository.valid_pair(x_ref, y_ref)

        self.assertTrue(np.isnan(line_pair.x[1]))
        np.testing.assert_allclose(valid_pair.x, [1, 3])
        np.testing.assert_allclose(valid_pair.y, [10, 30])

        canvas.add_scatter(valid_pair.x, valid_pair.y, 20, "black", "o", "scatter", x_ref, y_ref)
        offsets = canvas.fig.axes[0].collections[0].get_offsets()
        self.assertEqual(len(offsets), 2)

    def test_column_rename_and_move_do_not_change_refs(self):
        _canvas, view, x_ref, _y_ref = self.add_project()
        sheet = view.table_model.sheet
        sheet.columns[0].name = "Time"
        sheet.move_column(0, 2)

        self.assertTrue(self.window.repository.has_ref(x_ref))
        self.assertTrue(self.window.repository.ref_label(x_ref).endswith("/Time"))

    def test_referenced_column_delete_cascades_and_undo_restores(self):
        canvas, view, x_ref, y_ref = self.add_project()
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        view.setCurrentIndex(view.table_model.index(0, 0))

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            view.delete_column()
        self.assertEqual(len(canvas.project_plots), 0)
        self.assertFalse(self.window.repository.has_ref(x_ref))

        self.window.repository.undo_stack(canvas.project_id).undo()
        self.assertTrue(self.window.repository.has_ref(x_ref))
        self.assertEqual(len(canvas.project_plots), 1)

    def test_incompatible_type_change_cascades_and_undo_restores(self):
        canvas, view, x_ref, y_ref = self.add_project()
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        view.setCurrentIndex(view.table_model.index(0, 0))

        with patch.object(QInputDialog, "getItem", return_value=("text", True)), \
                patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            view.change_column_type()
        self.assertEqual(view.table_model.sheet.column(x_ref.column_id).type.value, "text")
        self.assertEqual(len(canvas.project_plots), 0)

        self.window.repository.undo_stack(canvas.project_id).undo()
        self.assertEqual(view.table_model.sheet.column(x_ref.column_id).type.value, "number")
        self.assertEqual(len(canvas.project_plots), 1)

    def test_referenced_sheet_delete_cascades_and_undo_restores(self):
        canvas, _view, _x_ref, _y_ref = self.add_project()
        subtable = self.window.table.current_subtable()
        second = subtable.add_new_sheet("Second")
        model = second.table_model
        model.setData(model.index(0, 0), "1", Qt.EditRole)
        model.setData(model.index(0, 1), "10", Qt.EditRole)
        x_ref = ColumnRef(canvas.project_id, model.sheet.id, model.sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, model.sheet.id, model.sheet.columns[1].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2, "black", "sheet plot", x_ref, y_ref)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            subtable.delete_sheet(1)
        self.assertFalse(self.window.repository.has_ref(x_ref))
        self.assertEqual(len(canvas.project_plots), 0)

        self.window.repository.undo_stack(canvas.project_id).undo()
        self.assertTrue(self.window.repository.has_ref(x_ref))
        self.assertEqual(subtable.tabWidget.tabText(1), "Second")
        self.assertEqual(len(canvas.project_plots), 1)

    def test_crlf_paste_is_atomic_and_undoable(self):
        _canvas, view, _x_ref, _y_ref = self.add_project()
        view.setCurrentIndex(view.table_model.index(3, 0))
        QGuiApplication.clipboard().setText("4\t40\r\n5\t50\r\n")
        view.paste_items()

        self.assertEqual(view.table_model.data(view.table_model.index(4, 1)), "50")
        self.window.repository.undo_stack(view.project_id).undo()
        self.assertEqual(view.table_model.data(view.table_model.index(3, 0)), "")
        self.assertEqual(view.table_model.data(view.table_model.index(4, 1)), "")


if __name__ == "__main__":
    unittest.main()
