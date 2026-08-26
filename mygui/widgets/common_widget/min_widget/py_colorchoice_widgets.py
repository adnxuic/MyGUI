"""Provide reusable color and palette selection widgets."""

from __future__ import annotations


from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from mygui import status_messages
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from .color_choice_dialogs import ColorPickerDialog, CustomPaletteDialog
from .color_choice_model import (
    ColorGridDelegate,
    ColorGridModel,
    ColorSwatch,
    PaletteDelegate,
    PaletteListModel,
    color_rgba_text,
    color_to_qcolor,
    qcolor_to_color,
)

class ColorChoiceWidget(QFrame):
    """Provide the color choice widget Qt widget."""

    colorChanged = Signal(str)

    def __init__(
        self,
        color="#000000",
        connect_signal=None,
        colorselector: ColorCycleState | None = None,
        color_library: ColorLibrary | None = None,
        parent=None,
        *,
        selection: ColorSelection | None = None,
        auto_record_recent: bool = True,
        allow_favorite: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("color_choice_widget")
        if color_library is None:
            raise ValueError(
                "ColorChoiceWidget requires the shared ColorLibrary."
            )
        self.color_library = color_library
        self.colorselector = colorselector
        if selection is None and colorselector is not None:
            selection = colorselector.peek()
        self._selection = selection or ColorSelection(color)
        self.auto_record_recent = bool(auto_record_recent)
        self.allow_favorite = bool(allow_favorite)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.color_display = ColorSwatch(self._selection.color, self)
        layout.addWidget(self.color_display)

        controls = QVBoxLayout()
        self.color_button = QPushButton("Choose color…", self)
        self.color_button.setAccessibleName("Open color picker")
        self.color_button.clicked.connect(self.showColorDialog)
        controls.addWidget(self.color_button)

        self.rgb_label = QLabel(self)
        self.rgb_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.rgb_label.setWordWrap(True)
        controls.addWidget(self.rgb_label)
        layout.addLayout(controls, 1)

        self.favorite_button = QPushButton("☆", self)
        self.favorite_button.setFixedWidth(34)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        layout.addWidget(self.favorite_button)
        if not self.allow_favorite:
            self.favorite_button.hide()
            self.favorite_button.setEnabled(False)

        if callable(connect_signal):
            self.colorChanged.connect(connect_signal)
        self.color_library.changed.connect(self._sync_favorite)
        self._sync_display()

    def _sync_display(self):
        text = color_rgba_text(self._selection.color)
        self.color_display.set_color(self._selection.color)
        self.rgb_label.setText(text)
        self.rgb_label.setAccessibleName(text)
        self.color_button.setToolTip(text)
        self._sync_favorite()

    def _sync_favorite(self):
        favorite = self.color_library.is_favorite_color(self._selection.color)
        self.favorite_button.setText("★" if favorite else "☆")
        self.favorite_button.setToolTip(
            "Remove current color from favorites"
            if favorite
            else "Add current color to favorites"
        )
        self.favorite_button.setAccessibleName(self.favorite_button.toolTip())

    def _toggle_favorite(self):
        if not self.allow_favorite:
            return
        self.color_library.toggle_favorite_color(self._selection.color)

    def showColorDialog(self):
        """Show color dialog."""

        dialog = ColorPickerDialog(
            self.color_library,
            self._selection,
            mode=ColorPickerDialog.COLOR_MODE,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.set_selection(
                dialog.selection(),
                emit=True,
                record_recent=self.auto_record_recent,
            )

    def set_selection(
        self,
        selection: ColorSelection,
        *,
        emit: bool = False,
        record_recent: bool = False,
    ) -> bool:
        """Set selection."""

        if not isinstance(selection, ColorSelection):
            raise TypeError("selection must be a ColorSelection.")
        changed = selection.color != self._selection.color
        self._selection = selection
        self._sync_display()
        if record_recent:
            self.color_library.record_recent(selection.color)
        if emit and changed:
            self.colorChanged.emit(selection.color)
        return changed

    def set_color(self, color, *, emit: bool = False, record_recent: bool = False) -> bool:
        """Set color."""

        try:
            selection = ColorSelection(color)
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return False
        return self.set_selection(
            selection,
            emit=emit,
            record_recent=record_recent,
        )

    def color(self) -> str:
        """Return the selected color."""

        return self._selection.color

    def selection(self) -> ColorSelection:
        """Return the current color selection."""

        return self._selection


def choose_palette(
    parent,
    color_library: ColorLibrary,
    initial_palette: PaletteDefinition | None = None,
) -> PaletteDefinition | None:
    """Choose palette."""

    selection = None
    if initial_palette is not None:
        selection = ColorSelection(initial_palette.colors[0], initial_palette, 0)
    dialog = ColorPickerDialog(
        color_library,
        selection,
        mode=ColorPickerDialog.PALETTE_MODE,
        parent=parent,
    )
    return dialog.selected_palette() if dialog.exec() == QDialog.Accepted else None

__all__ = [
    "ColorChoiceWidget",
    "ColorGridDelegate",
    "ColorGridModel",
    "ColorPickerDialog",
    "ColorSwatch",
    "CustomPaletteDialog",
    "PaletteDelegate",
    "PaletteListModel",
    "choose_palette",
    "color_rgba_text",
    "color_to_qcolor",
    "qcolor_to_color",
]
