"""Provide reusable color and palette selection widgets."""

from __future__ import annotations


from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from .color_choice_dialogs import ColorPickerDialog, CustomPaletteDialog
from mygui.widgets.ui_components import UiRole, UiVariant, apply_elided_text, style_button
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

_SWATCH_GAP = 8


def _positive_px(explicit: int, hinted: int, *, what: str) -> int:
    """Return a real pixel length. Invalid Qt hints are not a size of 0."""

    if explicit > 0:
        return explicit
    if hinted > 0:
        return hinted
    raise RuntimeError(f"{what} has no positive pixel size.")


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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._swatch_host = QWidget(self)
        self._swatch_row = QHBoxLayout(self._swatch_host)
        self._swatch_row.setContentsMargins(0, 0, 0, 0)
        self._swatch_row.setSpacing(_SWATCH_GAP)
        self.color_display = ColorSwatch(self._selection.color, self._swatch_host)
        self._swatch_row.addWidget(self.color_display)
        self._swatch_row.addStretch(1)
        self._held_swatch_stretch = None
        self.favorite_button = QPushButton("☆", self._swatch_host)
        self.favorite_button.setFixedWidth(34)
        self.favorite_button.setToolTip("Toggle favorite color")
        self.favorite_button.setAccessibleName("Toggle favorite color")
        style_button(
            self.favorite_button,
            variant=UiVariant.GHOST,
            role=UiRole.BUTTON,
        )
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self._swatch_row.addWidget(self.favorite_button)
        layout.addWidget(self._swatch_host)

        self.color_button = QPushButton("Choose color…", self)
        self.color_button.setAccessibleName("Open color picker")
        style_button(self.color_button, variant=UiVariant.OUTLINE)
        self.color_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.color_button.setMinimumWidth(1)
        self.color_button.clicked.connect(self.showColorDialog)
        layout.addWidget(self.color_button)

        self.rgb_label = QLabel(self)
        self.rgb_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.rgb_label.setWordWrap(False)
        self.rgb_label.setMinimumWidth(1)
        self.rgb_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.rgb_label)
        if not self.allow_favorite:
            self.favorite_button.hide()
            self.favorite_button.setEnabled(False)

        if callable(connect_signal):
            self.colorChanged.connect(connect_signal)
        self.color_library.changed.connect(self._sync_favorite)
        self._sync_display()
        self._adapt_swatch_row()

    def _column_min_height(self, host_height: int) -> int:
        layout = self.layout()
        spacing = layout.spacing() if layout is not None else 4
        if spacing < 0:
            spacing = 4
        margins = self.contentsMargins()
        button_h = _positive_px(
            self.color_button.minimumSize().height(),
            self.color_button.sizeHint().height(),
            what="color button height",
        )
        label_hint = self.rgb_label.sizeHint().height()
        label_h = label_hint if label_hint > 0 else self.rgb_label.fontMetrics().height()
        if label_h <= 0:
            raise RuntimeError("color label height has no positive pixel size.")
        return (
            host_height
            + button_h
            + label_h
            + 2 * spacing
            + margins.top()
            + margins.bottom()
        )

    def minimumSizeHint(self) -> QSize:
        """Keep the swatch readable so QFormLayout can wrap the field."""

        swatch = self._swatch_size()
        row = swatch.width()
        if self._favorite_in_layout():
            favorite = self._favorite_size()
            row = swatch.width() + _SWATCH_GAP + favorite.width()
        column = self._column_min_height(swatch.height())
        hint = super().minimumSizeHint()
        return QSize(row, max(hint.height() if hint.height() > 0 else 0, column))

    def sizeHint(self) -> QSize:
        minimum = self.minimumSizeHint()
        hint = super().sizeHint()
        return QSize(
            max(hint.width(), minimum.width()),
            max(hint.height(), minimum.height()),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adapt_swatch_row()
        apply_elided_text(self.rgb_label, color_rgba_text(self._selection.color), padding=0)

    def _swatch_size(self) -> QSize:
        size = self.color_display.minimumSize()
        if size.width() <= 0 or size.height() <= 0:
            raise RuntimeError(
                "ColorSwatch minimumSize() must be the explicit 52×52 constraint."
            )
        return size

    def _favorite_in_layout(self) -> bool:
        return bool(self.allow_favorite) and not self.favorite_button.isHidden()

    def _favorite_size(self) -> QSize:
        explicit = self.favorite_button.minimumSize()
        hint = self.favorite_button.sizeHint()
        return QSize(
            _positive_px(
                explicit.width(),
                hint.width(),
                what="favorite button width",
            ),
            _positive_px(
                explicit.height(),
                hint.height(),
                what="favorite button height",
            ),
        )

    def _swatch_stretch_index(self) -> int | None:
        for index in range(self._swatch_row.count()):
            item = self._swatch_row.itemAt(index)
            if item is not None and item.spacerItem() is not None:
                return index
        return None

    def _remove_swatch_stretch(self) -> None:
        index = self._swatch_stretch_index()
        if index is None:
            return
        self._held_swatch_stretch = self._swatch_row.takeAt(index)

    def _ensure_swatch_stretch(self) -> None:
        if self._swatch_stretch_index() is not None:
            return
        insert_at = min(1, self._swatch_row.count())
        held = self._held_swatch_stretch
        if held is not None:
            self._swatch_row.insertItem(insert_at, held)
            self._held_swatch_stretch = None
            return
        self._swatch_row.insertStretch(insert_at, 1)

    def _adapt_swatch_row(self) -> None:
        swatch = self._swatch_size()
        available = self.width()
        stacked = (
            self._favorite_in_layout()
            and available > 0
            and available < swatch.width()
        )
        if stacked:
            favorite = self._favorite_size()
            row_height = swatch.height() + _SWATCH_GAP + favorite.height()
            direction = QBoxLayout.Direction.TopToBottom
            self._remove_swatch_stretch()
        else:
            row_height = swatch.height()
            direction = QBoxLayout.Direction.LeftToRight
            self._ensure_swatch_stretch()
        if row_height <= 0:
            raise RuntimeError("ColorChoiceWidget swatch host height must be positive.")
        if self._swatch_row.direction() != direction:
            self._swatch_row.setDirection(direction)
        if self._swatch_host.minimumHeight() != row_height:
            self._swatch_host.setMinimumHeight(row_height)
        if self._swatch_host.maximumHeight() != row_height:
            self._swatch_host.setMaximumHeight(row_height)
        column = self._column_min_height(swatch.height())
        if column <= 0:
            raise RuntimeError("ColorChoiceWidget column height must be positive.")
        if self.minimumHeight() != column:
            self.setMinimumHeight(column)

    def _sync_display(self):
        text = color_rgba_text(self._selection.color)
        self.color_display.set_color(self._selection.color)
        self.rgb_label.setAccessibleName(text)
        self.color_button.setToolTip(text)
        apply_elided_text(self.rgb_label, text, padding=0)
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
