import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolBar, QWidget

from main import MainWindow


class CanvasPopoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(1600, 900)
        self.window.showNormal()
        self._process_events()

    def tearDown(self):
        if self.window is not None:
            self.window.close_without_prompt()
            self.window.deleteLater()
        self._process_events()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self._process_events()

    def _process_events(self):
        self.app.processEvents()
        self.app.processEvents()

    def _add_canvas(self, name="Popout", width=4, height=3):
        canvas = self.window.figure_window.add_figure(
            width=width,
            height=height,
            dpi=100,
            style="default",
            canva_name=name,
        )
        self._process_events()
        return canvas

    def test_toolbar_action_is_last_accessible_and_right_aligned(self):
        canvas = self._add_canvas()
        toolbar = canvas.navigation_toolbar
        action = canvas.popout_action
        button = toolbar.widgetForAction(action)
        spacer = toolbar.findChild(QWidget, "figure_toolbar_spacer")

        self.assertIs(toolbar.actions()[-1], action)
        self.assertEqual(action.objectName(), "figure_popout_action")
        self.assertEqual(action.toolTip(), "Open canvas in large window")
        self.assertFalse(action.icon().isNull())
        self.assertIsNotNone(button)
        self.assertEqual(button.accessibleName(), "Open canvas in large window")
        self.assertEqual(button.objectName(), "figure_popout_button")
        self.assertIsNotNone(spacer)
        self.assertEqual(
            spacer.sizePolicy().horizontalPolicy(),
            QSizePolicy.Expanding,
        )
        self.assertGreater(button.x(), spacer.x())
        self.assertLessEqual(
            toolbar.contentsRect().right() - button.geometry().right(),
            8,
        )

    def test_open_and_close_moves_the_unique_live_canvas_without_state_changes(self):
        canvas = self._add_canvas()
        figure = canvas.fig
        qt_canvas = canvas.canva
        scroll_area = canvas.scroArea
        component_snapshot = canvas.component_snapshot()
        size_inches = tuple(float(value) for value in figure.get_size_inches())
        runtime_dpi = float(figure.dpi)
        document_dpi = canvas.document_dpi
        undo_index = canvas.repository.undo_stack(canvas.project_id).index()
        scroll_position = (
            scroll_area.horizontalScrollBar().value(),
            scroll_area.verticalScrollBar().value(),
        )
        self.window.figure_window.mark_canvas_clean(canvas)

        canvas.popout_action.trigger()
        self._process_events()

        popout = canvas._canvas_popout_window
        self.assertIsNotNone(popout)
        self.assertTrue(popout.isVisible())
        self.assertTrue(popout.isMaximized())
        self.assertFalse(popout.isModal())
        self.assertIsNone(popout.parentWidget())
        self.assertIsNone(popout.windowHandle().transientParent())
        self.assertIn(popout, self.app.topLevelWidgets())
        self.assertGreaterEqual(popout.frameGeometry().width(), 640)
        self.assertGreaterEqual(popout.frameGeometry().height(), 480)
        self.assertEqual(popout.windowTitle(), "Popout — Canvas")
        self.assertIs(popout.layout().itemAt(0).widget(), scroll_area)
        self.assertIs(
            canvas._canvas_content_stack.currentWidget(),
            canvas._canvas_popout_placeholder,
        )
        self.assertEqual(popout.findChildren(QToolBar), [])
        self.assertTrue(scroll_area.isVisible())
        self.assertTrue(qt_canvas.isVisible())
        self.assertFalse(popout.sizeHint().isEmpty())
        self.assertTrue(canvas._canvas_popout_placeholder.isVisible())
        self.assertIs(figure.canvas, qt_canvas)
        self.assertIs(scroll_area.widget(), qt_canvas)
        self.assertEqual(canvas.component_snapshot(), component_snapshot)
        self.assertEqual(
            tuple(float(value) for value in figure.get_size_inches()),
            size_inches,
        )
        self.assertEqual(float(figure.dpi), runtime_dpi)
        self.assertEqual(canvas.document_dpi, document_dpi)
        self.assertEqual(
            canvas.repository.undo_stack(canvas.project_id).index(),
            undo_index,
        )
        self.assertFalse(self.window.figure_window.is_canvas_dirty(canvas))

        popout.close()
        self._process_events()

        self.assertIsNone(canvas._canvas_popout_window)
        self.assertIs(
            canvas._canvas_content_stack.currentWidget(),
            scroll_area,
        )
        self.assertIs(scroll_area.widget(), qt_canvas)
        self.assertIs(figure.canvas, qt_canvas)
        self.assertTrue(scroll_area.isVisible())
        self.assertTrue(qt_canvas.isVisible())
        self.assertFalse(canvas._canvas_popout_placeholder.isVisible())
        self.assertEqual(
            (
                scroll_area.horizontalScrollBar().value(),
                scroll_area.verticalScrollBar().value(),
            ),
            scroll_position,
        )
        self.assertEqual(canvas.component_snapshot(), component_snapshot)
        self.assertFalse(self.window.figure_window.is_canvas_dirty(canvas))

    def test_escape_closes_the_window_from_the_focused_canvas(self):
        canvas = self._add_canvas()
        canvas.open_canvas_window()
        self._process_events()
        popout = canvas._canvas_popout_window
        self.assertIs(popout.focusWidget(), canvas.canva)

        QTest.keyClick(canvas.canva, Qt.Key_Escape)
        self._process_events()

        self.assertIsNone(canvas._canvas_popout_window)
        self.assertFalse(
            any(
                widget.objectName() == "figure_popout_window"
                and widget.isVisible()
                for widget in self.app.topLevelWidgets()
            )
        )
        self.assertIs(
            canvas._canvas_content_stack.currentWidget(),
            canvas.scroArea,
        )
        self.assertTrue(canvas.scroArea.isVisible())
        self.assertTrue(canvas.canva.isVisible())

    def test_dialog_rejection_returns_the_canvas_to_its_project_tab(self):
        canvas = self._add_canvas()
        canvas.open_canvas_window()
        self._process_events()
        popout = canvas._canvas_popout_window

        popout.reject()
        self._process_events()

        self.assertFalse(popout.isVisible())
        self.assertIsNone(canvas._canvas_popout_window)
        self.assertIs(
            canvas._canvas_content_stack.currentWidget(),
            canvas.scroArea,
        )
        self.assertTrue(canvas.scroArea.isVisible())
        self.assertTrue(canvas.canva.isVisible())
        self.assertIs(canvas.scroArea.widget(), canvas.canva)

    def test_scroll_position_survives_a_canvas_larger_than_the_viewport(self):
        canvas = self._add_canvas("Scrolled", width=20, height=15)
        horizontal = canvas.scroArea.horizontalScrollBar()
        vertical = canvas.scroArea.verticalScrollBar()
        self.assertGreater(horizontal.maximum(), 0)
        self.assertGreater(vertical.maximum(), 0)
        horizontal.setValue(horizontal.maximum() // 3)
        vertical.setValue(vertical.maximum() // 3)
        self._process_events()
        scroll_position = (horizontal.value(), vertical.value())

        canvas.open_canvas_window()
        self._process_events()
        canvas._canvas_popout_window.close()
        self._process_events()

        self.assertEqual(
            (horizontal.value(), vertical.value()),
            scroll_position,
        )

    def test_repeated_open_reuses_window_and_projects_can_pop_out_independently(self):
        first = self._add_canvas("First")
        first.open_canvas_window()
        self._process_events()
        first_window = first._canvas_popout_window

        first.open_canvas_window()
        self._process_events()
        self.assertIs(first._canvas_popout_window, first_window)

        second = self._add_canvas("Second")
        second.open_canvas_window()
        self._process_events()
        second_window = second._canvas_popout_window

        self.assertIsNotNone(first_window)
        self.assertIsNotNone(second_window)
        self.assertIsNot(first_window, second_window)
        self.assertTrue(first_window.isVisible())
        self.assertTrue(second_window.isVisible())
        self.window.figure_window.rename_project(first.project_id, "Renamed")
        self._process_events()
        self.assertEqual(first_window.windowTitle(), "Renamed — Canvas")
        self.assertEqual(second_window.windowTitle(), "Second — Canvas")

    def test_project_and_application_close_release_popout_windows(self):
        first = self._add_canvas("First")
        first.open_canvas_window()
        self._process_events()
        first_window = first._canvas_popout_window

        first_index = self.window.figure_window.tabwindow.indexOf(first)
        self.assertTrue(self.window.figure_window.close_project_at(first_index))
        self.assertIsNone(first._canvas_popout_window)
        self.assertFalse(first_window.isVisible())
        self.assertIs(
            first._canvas_content_stack.currentWidget(),
            first.scroArea,
        )
        self._process_events()
        self.assertFalse(
            any(
                widget.objectName() == "figure_popout_window"
                and widget.windowTitle() == "First — Canvas"
                for widget in self.app.topLevelWidgets()
            )
        )

        second = self._add_canvas("Second")
        second.open_canvas_window()
        self._process_events()
        second_window = second._canvas_popout_window

        closing_window = self.window
        self.assertTrue(closing_window.close_without_prompt())
        self.assertIsNone(second._canvas_popout_window)
        self.assertFalse(second_window.isVisible())
        self._process_events()
        self.assertFalse(
            any(
                widget.objectName() == "figure_popout_window"
                and widget.windowTitle() == "Second — Canvas"
                for widget in self.app.topLevelWidgets()
            )
        )
        closing_window.deleteLater()
        self.window = None


if __name__ == "__main__":
    unittest.main()
