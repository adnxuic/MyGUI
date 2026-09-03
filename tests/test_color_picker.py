from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QModelIndex,
    QRect,
    QSize,
    Qt,
    qInstallMessageHandler,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QColorDialog,
    QDialog,
    QStyle,
    QStyleOptionViewItem,
    QWidget,
)

from mygui import status_messages
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
)

from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
    ColorGridDelegate,
    ColorGridModel,
    ColorPickerDialog,
    ColorSwatch,
    CustomPaletteDialog,
    PaletteDelegate,
    PaletteListModel,
    choose_palette,
    color_rgba_text,
    color_to_qcolor,
    qcolor_to_color,
)
from mygui.widgets.common_widget.min_widget import color_choice_dialogs


@contextmanager
def _capture_negative_size_warnings():
    captured: list[str] = []

    def handler(mode, context, message):
        text = str(message)
        if "Negative sizes" in text:
            captured.append(text)
        if callable(previous):
            previous(mode, context, message)

    previous = qInstallMessageHandler(handler)
    try:
        yield captured
    finally:
        qInstallMessageHandler(previous)


class ColorPickerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.messages = []
        status_messages.set_status_handler(lambda message, level: self.messages.append((message, level)))

    def tearDown(self):
        status_messages.clear_status_handler()
        self.app.processEvents()

    def test_color_conversion_utilities_and_text_formatting(self):
        # 6-char hex
        qcolor_rgb = color_to_qcolor("#FF0000")
        self.assertEqual(qcolor_rgb.red(), 255)
        self.assertEqual(qcolor_rgb.green(), 0)
        self.assertEqual(qcolor_rgb.blue(), 0)
        self.assertEqual(qcolor_rgb.alpha(), 255)

        # 8-char hex
        qcolor_rgba = color_to_qcolor("#00FF0080")
        self.assertEqual(qcolor_rgba.red(), 0)
        self.assertEqual(qcolor_rgba.green(), 255)
        self.assertEqual(qcolor_rgba.blue(), 0)
        self.assertEqual(qcolor_rgba.alpha(), 128)

        # QColor to color string
        self.assertEqual(qcolor_to_color(QColor(255, 0, 0, 255)), "#FF0000")
        self.assertEqual(qcolor_to_color(QColor(0, 255, 0, 128)), "#00FF0080")

        # Invalid QColor error
        with self.assertRaisesRegex(ValueError, "Invalid Qt color"):
            qcolor_to_color(QColor())
        with self.assertRaisesRegex(ValueError, "Invalid Qt color"):
            qcolor_to_color(None)

        # color_rgba_text
        text = color_rgba_text("#1F77B4")
        self.assertIn("#1F77B4", text)
        self.assertIn("RGBA(31, 119, 180, 100%)", text)

    def test_color_swatch_lifecycle_and_focus(self):
        swatch = ColorSwatch("#1F77B4")
        self.assertEqual(swatch.color(), "#1F77B4")
        swatch.set_color("#FF7F0E")
        self.assertEqual(swatch.color(), "#FF7F0E")
        self.assertIn("FF7F0E", swatch.accessibleName())
        self.assertIn("FF7F0E", swatch.toolTip())

        pixmap = QPixmap(52, 52)
        painter = QPainter(pixmap)
        try:
            swatch.paintEvent(None)
        finally:
            painter.end()

        # Focus in and out events
        from PySide6.QtGui import QFocusEvent
        swatch.focusInEvent(QFocusEvent(QEvent.FocusIn))
        swatch.focusOutEvent(QFocusEvent(QEvent.FocusOut))
        self.assertEqual(swatch.minimumSize(), QSize(52, 52))
        self.assertLess(swatch.minimumSizeHint().width(), 0)
        self.assertLess(swatch.minimumSizeHint().height(), 0)
        swatch.deleteLater()


    def test_color_and_palette_list_models_and_delegates(self):
        # ColorGridModel
        selections = [ColorSelection("#1F77B4"), ColorSelection("#FF7F0E80")]
        grid_model = ColorGridModel(selections)
        self.assertEqual(grid_model.rowCount(), 2)
        self.assertEqual(grid_model.data(grid_model.index(0, 0), Qt.DisplayRole), "#1F77B4")
        self.assertIn("RGBA", grid_model.data(grid_model.index(0, 0), Qt.ToolTipRole))
        self.assertIn("RGBA", grid_model.data(grid_model.index(0, 0), Qt.AccessibleTextRole))
        self.assertEqual(grid_model.data(grid_model.index(0, 0), Qt.UserRole), selections[0])
        self.assertIsNone(grid_model.data(QModelIndex()))
        self.assertIsNone(grid_model.data(grid_model.index(99, 0)))

        grid_model.set_selections([ColorSelection("#000000")])
        self.assertEqual(grid_model.rowCount(), 1)

        # PaletteListModel
        library = ColorLibrary()
        palettes = [
            PaletteDefinition("pal1", "Palette One", ("#1F77B4", "#FF7F0E")),
            PaletteDefinition("pal2", "Palette Two", ("#2CA02C", "#D62728")),
        ]
        palette_model = PaletteListModel(palettes, library=library)
        self.assertEqual(palette_model.rowCount(), 2)
        self.assertIn("Palette One", palette_model.data(palette_model.index(0, 0), Qt.DisplayRole))
        self.assertIn("Palette One", palette_model.data(palette_model.index(0, 0), Qt.ToolTipRole))
        self.assertIn("Palette One", palette_model.data(palette_model.index(0, 0), Qt.AccessibleTextRole))
        self.assertEqual(palette_model.data(palette_model.index(0, 0), Qt.UserRole), palettes[0])
        self.assertIsNone(palette_model.data(QModelIndex()))
        self.assertIsNone(palette_model.data(palette_model.index(99, 0)))

        # Favorite star in PaletteListModel
        builtin_id = library.palettes()[0].id
        palette_model = PaletteListModel([library.palette(builtin_id)], library=library)
        library.toggle_favorite_palette(builtin_id)
        self.assertTrue(palette_model.data(palette_model.index(0, 0), Qt.DisplayRole).startswith("★"))

        # ColorGridDelegate
        grid_delegate = ColorGridDelegate()
        self.assertEqual(grid_delegate.sizeHint(None, None), QSize(82, 58))
        pixmap = QPixmap(100, 100)
        painter = QPainter(pixmap)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 82, 58)
        option.state = QStyle.State_Selected | QStyle.State_HasFocus
        grid_delegate.paint(painter, option, grid_model.index(0, 0))

        # PaletteDelegate
        palette_delegate = PaletteDelegate()
        self.assertEqual(palette_delegate.sizeHint(None, None), QSize(420, 54))
        option.rect = QRect(0, 0, 420, 54)
        palette_delegate.paint(painter, option, palette_model.index(0, 0))
        painter.end()

    def test_custom_palette_dialog_crud_and_reordering(self):
        library = ColorLibrary()
        dialog = CustomPaletteDialog(library, parent=None)

        # Max 12 colors warning limit
        for _ in range(10):
            dialog._append_color("#123456")
        self.assertEqual(dialog.color_list.count(), 12)
        dialog.add_color()
        self.assertTrue(any("at most 12 colors" in msg for msg, _ in self.messages))

        # Add color with mock dialog
        dialog.color_list.clear()
        with patch.object(QColorDialog, "getColor", return_value=QColor(255, 0, 0, 255)):
            dialog.add_color()
        self.assertEqual(dialog.color_list.count(), 1)
        self.assertEqual(dialog.color_list.item(0).data(Qt.UserRole), "#FF0000")

        # Edit color (none selected vs selected)
        dialog.color_list.setCurrentRow(-1)
        dialog.edit_color()  # no-op
        dialog.color_list.setCurrentRow(0)
        with patch.object(QColorDialog, "getColor", return_value=QColor(0, 255, 0, 255)):
            dialog.edit_color()
        self.assertEqual(dialog.color_list.item(0).data(Qt.UserRole), "#00FF00")

        # Move color up/down
        with patch.object(QColorDialog, "getColor", return_value=QColor(0, 0, 255, 255)):
            dialog.add_color()
        self.assertEqual(dialog.color_list.count(), 2)
        dialog.color_list.setCurrentRow(0)
        dialog.move_color(-1)  # clamped at 0
        self.assertEqual(dialog.color_list.currentRow(), 0)
        dialog.move_color(1)  # moved down to 1
        self.assertEqual(dialog.color_list.currentRow(), 1)
        self.assertEqual(dialog.color_list.item(0).data(Qt.UserRole), "#0000FF")

        # Remove color
        dialog.remove_color()
        self.assertEqual(dialog.color_list.count(), 1)

        # Save and accept: empty name failure
        dialog.name_input.setText("")
        with patch("mygui.widgets.common_widget.min_widget.color_choice_dialogs.present_warning"):
            dialog._save_and_accept()
        self.assertIsNone(dialog.result_palette)

        # Save and accept: valid custom palette
        dialog.name_input.setText("CustomPaletteTest")
        dialog._append_color("#AABBCC")
        dialog._save_and_accept()
        self.assertIsNotNone(dialog.result_palette)
        self.assertEqual(dialog.result_palette.name, "CustomPaletteTest")

        # Edit existing palette
        edit_dialog = CustomPaletteDialog(library, palette=dialog.result_palette)
        edit_dialog.name_input.setText("CustomPaletteTestUpdated")
        edit_dialog._save_and_accept()
        self.assertEqual(edit_dialog.result_palette.name, "CustomPaletteTestUpdated")
        dialog.deleteLater()
        edit_dialog.deleteLater()

    def test_color_picker_dialog_filtering_and_modes(self):
        library = ColorLibrary()
        with self.assertRaisesRegex(ValueError, "Unsupported color picker mode"):
            ColorPickerDialog(library, mode="invalid_mode")

        # COLOR_MODE dialog
        dialog = ColorPickerDialog(library, mode=ColorPickerDialog.COLOR_MODE)
        self.assertEqual(dialog.tabs.count(), 4)  # Recent, Favorites, All Colors, Palettes

        # Search filter
        dialog.search_input.setText("FF")
        self.assertGreater(dialog.all_model.rowCount(), 0)
        self.assertTrue(all("FF" in sel.color for sel in dialog.all_model.selections))

        # Palette filter combobox
        dialog.palette_filter.setCurrentIndex(1)  # Favorite
        dialog.palette_filter.setCurrentIndex(2)  # Builtin
        dialog.palette_filter.setCurrentIndex(3)  # Custom
        dialog.palette_filter.setCurrentIndex(0)  # All

        # Color selection and double click
        dialog._color_selected(dialog.all_model.index(0, 0))
        with patch.object(dialog, "accept") as mock_accept:
            dialog._color_double_clicked(dialog.all_model.index(0, 0))
            mock_accept.assert_called_once()

        # Palette selection and double click in COLOR_MODE vs PALETTE_MODE
        dialog._palette_selected(dialog.palette_model.index(0, 0))
        self.assertIsNotNone(dialog.selected_palette())
        self.assertGreater(dialog.palette_color_model.rowCount(), 0)

        dialog.close()
        dialog.deleteLater()

        # PALETTE_MODE dialog
        palette_dialog = ColorPickerDialog(library, mode=ColorPickerDialog.PALETTE_MODE)
        self.assertEqual(palette_dialog.tabs.count(), 1)  # Palettes only
        palette_dialog._selected_palette = None
        palette_dialog._accept_current()
        self.assertTrue(any("Select a palette first." in msg for msg, _ in self.messages))

        palette_dialog._palette_selected(palette_dialog.palette_model.index(0, 0))
        with patch.object(palette_dialog, "accept") as mock_accept:
            palette_dialog._palette_double_clicked(palette_dialog.palette_model.index(0, 0))
            mock_accept.assert_called_once()
        palette_dialog.close()
        palette_dialog.deleteLater()

    def test_color_picker_dialog_hex_rgba_opacity_sync_and_actions(self):
        library = ColorLibrary()
        dialog = ColorPickerDialog(library, mode=ColorPickerDialog.COLOR_MODE)

        # Valid hex edit
        dialog.hex_input.setText("#00FF00")
        dialog._hex_edited()
        self.assertEqual(dialog.selection().color, "#00FF00")

        # Invalid hex edit reports error and reverts
        dialog.hex_input.setText("not-a-color")
        dialog._hex_edited()
        self.assertTrue(any("invalid" in msg.lower() for msg, _ in self.messages))
        self.assertEqual(dialog.selection().color, "#00FF00")

        # Opacity changed
        dialog.opacity_input.setValue(50)
        self.assertIn("80", dialog.selection().color)

        # RGBA changed
        dialog.rgba_inputs[0].setValue(200)
        self.assertEqual(dialog.selection().color[1:3], "C8")

        # Copy color
        dialog._copy_color()
        self.assertEqual(QApplication.clipboard().text(), dialog.selection().color)

        # Custom color button
        with patch.object(QColorDialog, "getColor", return_value=QColor(10, 20, 30, 255)):
            dialog._choose_custom_color()
        self.assertEqual(dialog.selection().color, "#0A141E")

        # Toggle color & palette favorite
        dialog._toggle_color_favorite()
        self.assertTrue(library.is_favorite_color(dialog.selection().color))
        dialog._toggle_color_favorite()
        self.assertFalse(library.is_favorite_color(dialog.selection().color))

        dialog._palette_selected(dialog.palette_model.index(0, 0))
        pal_id = dialog.selected_palette().id
        dialog._toggle_palette_favorite()
        self.assertTrue(library.is_favorite_palette(pal_id))

        # Palette creation, edit and deletion
        with patch.object(CustomPaletteDialog, "exec", return_value=QDialog.Accepted):
            with patch.object(CustomPaletteDialog, "_save_and_accept"):
                pass

        # Delete palette with English Yes/No confirmation
        custom_pal = library.create_custom_palette("ToDelete", ("#111111", "#222222"))
        dialog._selected_palette = custom_pal
        with patch.object(color_choice_dialogs, "ask_yes_no", return_value=True):
            dialog._delete_palette()
        self.assertIsNone(dialog.selected_palette())

        dialog.close()
        dialog.deleteLater()

    def test_swatch_host_keeps_explicit_height_without_negative_sizes(self):
        library = ColorLibrary()
        hidden_host = QWidget()
        with _capture_negative_size_warnings() as warnings:
            widget = ColorChoiceWidget(
                "black",
                color_library=library,
                parent=hidden_host,
            )
            self.assertFalse(widget.isVisible())
            self.assertGreaterEqual(widget._swatch_host.minimumHeight(), 52)

            hidden_host.show()
            self.app.processEvents()
            self.assertGreaterEqual(widget._swatch_host.minimumHeight(), 52)

            last_height = None
            for width in (40, 200, 40, 80, 200, 40):
                widget.resize(width, 160)
                widget._adapt_swatch_row()
                self.app.processEvents()
                last_height = widget._swatch_host.minimumHeight()
                self.assertGreaterEqual(last_height, 52)
            widget._adapt_swatch_row()
            self.assertEqual(widget._swatch_host.minimumHeight(), last_height)

            widget.resize(40, 160)
            widget._adapt_swatch_row()
            self.app.processEvents()
            self.assertEqual(
                widget._swatch_row.direction(),
                QBoxLayout.Direction.TopToBottom,
            )
            self.assertGreater(widget._swatch_host.minimumHeight(), 52)
            self.assertFalse(
                widget._swatch_host.geometry().intersects(widget.color_button.geometry())
            )

            widget.resize(240, 160)
            widget._adapt_swatch_row()
            self.app.processEvents()
            self.assertEqual(
                widget._swatch_row.direction(),
                QBoxLayout.Direction.LeftToRight,
            )
            self.assertEqual(widget._swatch_host.minimumHeight(), 52)
            self.assertFalse(
                widget._swatch_host.geometry().intersects(widget.color_button.geometry())
            )

            without_favorite = ColorChoiceWidget(
                "black",
                color_library=library,
                allow_favorite=False,
            )
            without_favorite.resize(40, 160)
            without_favorite._adapt_swatch_row()
            self.app.processEvents()
            self.assertTrue(without_favorite.favorite_button.isHidden())
            self.assertEqual(
                without_favorite._swatch_row.direction(),
                QBoxLayout.Direction.LeftToRight,
            )
            self.assertEqual(without_favorite._swatch_host.minimumHeight(), 52)
            without_favorite.resize(240, 160)
            without_favorite._adapt_swatch_row()
            self.app.processEvents()
            self.assertEqual(
                without_favorite._swatch_row.direction(),
                QBoxLayout.Direction.LeftToRight,
            )
            self.assertEqual(without_favorite._swatch_host.minimumHeight(), 52)
            without_favorite.deleteLater()
        self.assertEqual(warnings, [])
        widget.deleteLater()
        hidden_host.deleteLater()

    def test_initialization_is_silent_and_does_not_create_actions(self):
        emissions = []
        library = ColorLibrary()
        widget = ColorChoiceWidget(
            "tab:blue",
            connect_signal=emissions.append,
            color_library=library,
        )
        self.assertEqual(widget.color(), "#1F77B4")
        self.assertEqual(widget.color_button.text(), "Choose color…")
        self.assertEqual(widget.color_button.accessibleName(), "Open color picker")
        self.assertEqual(emissions, [])
        self.assertEqual(len(widget.findChildren(QAction)), 0)
        widget.deleteLater()

    def test_set_color_emits_at_most_once_when_requested(self):
        widget = ColorChoiceWidget("black", color_library=ColorLibrary())
        emissions = []
        widget.colorChanged.connect(emissions.append)
        widget.set_color("red", emit=True)
        widget.set_color("#FF0000", emit=True)
        self.assertEqual(emissions, ["#FF0000"])
        widget.deleteLater()

    def test_color_choice_widget_full_interaction(self):
        library = ColorLibrary()
        widget = ColorChoiceWidget("black", color_library=library)

        # Invalid type for set_selection
        with self.assertRaisesRegex(TypeError, "must be a ColorSelection"):
            widget.set_selection("not_a_selection")

        # Invalid color string for set_color
        self.assertFalse(widget.set_color("invalid_hex_code"))
        self.assertTrue(any("invalid" in msg.lower() for msg, _ in self.messages))


        # Favorite toggle
        widget._toggle_favorite()
        self.assertTrue(library.is_favorite_color(widget.color()))

        # showColorDialog with mock accept
        with patch.object(ColorPickerDialog, "exec", return_value=QDialog.Accepted), \
                patch.object(ColorPickerDialog, "selection", return_value=ColorSelection("#123456")):
            widget.showColorDialog()
        self.assertEqual(widget.color(), "#123456")
        self.assertEqual(widget.selection().color, "#123456")
        widget.deleteLater()

    def test_cycle_preview_is_not_committed_by_widget_construction(self):
        palette = PaletteDefinition("test", "Test", ("red", "blue"))
        state = ColorCycleState(palette)
        widget = ColorChoiceWidget(
            colorselector=state,
            color_library=ColorLibrary(),
        )
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

    def test_widget_rejects_missing_application_library(self):
        with self.assertRaisesRegex(ValueError, "shared ColorLibrary"):
            ColorChoiceWidget("black")

    def test_choose_palette_helper(self):
        library = ColorLibrary()
        palette = PaletteDefinition("test_helper", "Test Helper", ("#111111", "#222222"))
        with patch.object(ColorPickerDialog, "exec", return_value=QDialog.Accepted), \
                patch.object(ColorPickerDialog, "selected_palette", return_value=palette):
            result = choose_palette(None, library, initial_palette=palette)
            self.assertEqual(result, palette)

        with patch.object(ColorPickerDialog, "exec", return_value=QDialog.Rejected):
            result = choose_palette(None, library, initial_palette=palette)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

