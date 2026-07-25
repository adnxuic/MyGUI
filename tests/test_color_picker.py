import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QAction, QApplication, QCoreApplication, QEvent

from code.figuremodify.style_base.color_models import ColorCycleState, PaletteDefinition
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
    ColorPickerDialog,
)


class ColorPickerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_initialization_is_silent_and_does_not_create_actions(self):
        emissions = []
        widget = ColorChoiceWidget("tab:blue", connect_signal=emissions.append)
        self.assertEqual(widget.color(), "#1F77B4")
        self.assertEqual(emissions, [])
        self.assertEqual(len(widget.findChildren(QAction)), 0)
        widget.deleteLater()

    def test_set_color_emits_at_most_once_when_requested(self):
        widget = ColorChoiceWidget("black")
        emissions = []
        widget.colorChanged.connect(emissions.append)
        widget.set_color("red", emit=True)
        widget.set_color("#FF0000", emit=True)
        self.assertEqual(emissions, ["#FF0000"])
        widget.deleteLater()

    def test_cycle_preview_is_not_committed_by_widget_construction(self):
        palette = PaletteDefinition("test", "Test", ("red", "blue"))
        state = ColorCycleState(palette)
        widget = ColorChoiceWidget(colorselector=state)
        self.assertEqual(widget.color(), "#FF0000")
        self.assertEqual(state.next_index, 0)
        widget.deleteLater()

    def test_dialog_is_bounded_and_exposes_accessible_controls(self):
        dialog = ColorPickerDialog(ColorLibrary(), mode=ColorPickerDialog.COLOR_MODE)
        self.assertGreaterEqual(dialog.minimumWidth(), 500)
        self.assertLessEqual(dialog.minimumHeight(), 700)
        self.assertTrue(dialog.hex_input.accessibleName())
        self.assertEqual((dialog.opacity_input.minimum(), dialog.opacity_input.maximum()), (0, 100))
        self.assertEqual(dialog.all_model.rowCount(), 296)
        self.assertIsNone(dialog.all_model.selections[0].palette)
        self.assertEqual(dialog.palette_model.rowCount(), 77)
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
