"""Color conversion helpers, swatches, and picker list models."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QWidget,
)

from mygui.figuremodify.style_base.color_models import (
    ColorSelection,
    PaletteDefinition,
    normalize_color,
)
from mygui.widgets.theme import COLORS

def color_to_qcolor(value) -> QColor:
    """Return the color to qcolor."""

    color = normalize_color(value)
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    alpha = int(color[7:9], 16) if len(color) == 9 else 255
    return QColor(red, green, blue, alpha)


def qcolor_to_color(value: QColor) -> str:
    """Return the qcolor to color."""

    if not isinstance(value, QColor) or not value.isValid():
        raise ValueError("Invalid Qt color.")
    color = f"#{value.red():02X}{value.green():02X}{value.blue():02X}"
    if value.alpha() < 255:
        color += f"{value.alpha():02X}"
    return color


def color_rgba_text(value) -> str:
    """Return the color rgba text."""

    color = color_to_qcolor(value)
    opacity = round(color.alphaF() * 100)
    return (
        f"{normalize_color(value)} · "
        f"RGBA({color.red()}, {color.green()}, {color.blue()}, {opacity}%)"
    )


def _paint_checkerboard(painter: QPainter, rect: QRect, cell_size: int = 6) -> None:
    light = QColor("#FFFFFF")
    dark = QColor("#D1D5DB")
    for y in range(rect.top(), rect.bottom() + 1, cell_size):
        for x in range(rect.left(), rect.right() + 1, cell_size):
            color = light if ((x - rect.left()) // cell_size + (y - rect.top()) // cell_size) % 2 == 0 else dark
            painter.fillRect(
                QRect(x, y, min(cell_size, rect.right() - x + 1), min(cell_size, rect.bottom() - y + 1)),
                color,
            )


class ColorSwatch(QWidget):
    """Provide the color swatch Qt widget."""

    def __init__(self, color="#000000", parent=None):
        super().__init__(parent)
        self._color = normalize_color(color)
        self.setFixedSize(52, 52)
        self.setFocusPolicy(Qt.ClickFocus)
        self._sync_accessibility()

    def color(self) -> str:
        """Return the selected color."""

        return self._color

    def set_color(self, color) -> None:
        """Set color."""

        self._color = normalize_color(color)
        self._sync_accessibility()
        self.update()

    def _sync_accessibility(self) -> None:
        text = f"当前颜色 {color_rgba_text(self._color)}"
        self.setAccessibleName(text)
        self.setToolTip(text)

    def paintEvent(self, _event):
        """Paint the widget's custom appearance."""

        painter = QPainter(self)
        rect = self.rect().adjusted(1, 1, -1, -1)
        _paint_checkerboard(painter, rect)
        painter.fillRect(rect, color_to_qcolor(self._color))
        border = QColor(COLORS["focus"] if self.hasFocus() else COLORS["text_primary"])
        painter.setPen(QPen(border, 2 if self.hasFocus() else 1))
        painter.drawRect(rect)

    def focusInEvent(self, event):
        """Update editing state when the widget gains focus."""

        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        """Commit pending input when the widget loses focus."""

        self.update()
        super().focusOutEvent(event)


class ColorGridModel(QAbstractListModel):
    """Expose color grid data through Qt's model API."""

    def __init__(self, selections: Iterable[ColorSelection] = (), parent=None):
        super().__init__(parent)
        self.selections = list(selections)

    def set_selections(self, selections: Iterable[ColorSelection]) -> None:
        """Set selections."""

        self.beginResetModel()
        self.selections = list(selections)
        self.endResetModel()

    def rowCount(self, _parent=QModelIndex()):
        """Return the number of rows exposed by the Qt model."""

        return len(self.selections)

    def data(self, index, role=Qt.DisplayRole):
        """Return data for the requested Qt model role."""

        if not index.isValid() or not 0 <= index.row() < len(self.selections):
            return None
        selection = self.selections[index.row()]
        if role == Qt.DisplayRole:
            return selection.color
        if role == Qt.ToolTipRole:
            return color_rgba_text(selection.color)
        if role == Qt.AccessibleTextRole:
            return color_rgba_text(selection.color)
        if role == Qt.UserRole:
            return selection
        return None


class PaletteListModel(QAbstractListModel):
    """Expose palette list data through Qt's model API."""

    def __init__(self, palettes: Iterable[PaletteDefinition] = (), library=None, parent=None):
        super().__init__(parent)
        self.palettes = list(palettes)
        self.library = library

    def set_palettes(self, palettes: Iterable[PaletteDefinition]) -> None:
        """Set palettes."""

        self.beginResetModel()
        self.palettes = list(palettes)
        self.endResetModel()

    def rowCount(self, _parent=QModelIndex()):
        """Return the number of rows exposed by the Qt model."""

        return len(self.palettes)

    def data(self, index, role=Qt.DisplayRole):
        """Return data for the requested Qt model role."""

        if not index.isValid() or not 0 <= index.row() < len(self.palettes):
            return None
        palette = self.palettes[index.row()]
        if role == Qt.DisplayRole:
            favorite = "★ " if self.library and self.library.is_favorite_palette(palette.id) else ""
            return f"{favorite}{palette.display_name} · {len(palette.colors)} 色"
        if role == Qt.ToolTipRole:
            return f"{palette.display_name}\n{' / '.join(palette.colors)}"
        if role == Qt.AccessibleTextRole:
            return f"{palette.display_name}，{len(palette.colors)} 色"
        if role == Qt.UserRole:
            return palette
        return None


class ColorGridDelegate(QStyledItemDelegate):
    """Render and edit color grid values in Qt item views."""

    def sizeHint(self, _option, _index):
        """Return the preferred size used by Qt layout and item views."""

        return QSize(82, 58)

    def paint(self, painter, option, index):
        """Paint the item represented by the Qt delegate index."""

        selection = index.data(Qt.UserRole)
        if not isinstance(selection, ColorSelection):
            return
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        swatch = QRect(option.rect.left() + 6, option.rect.top() + 4, option.rect.width() - 12, 30)
        _paint_checkerboard(painter, swatch)
        painter.fillRect(swatch, color_to_qcolor(selection.color))
        painter.setPen(QPen(QColor(COLORS["text_primary"]), 1))
        painter.drawRect(swatch)
        text_color = option.palette.highlightedText().color() if option.state & QStyle.State_Selected else QColor(
            COLORS["text_primary"]
        )
        painter.setPen(text_color)
        painter.drawText(
            option.rect.adjusted(2, 36, -2, -2),
            Qt.AlignHCenter | Qt.AlignTop,
            selection.color,
        )
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor(COLORS["focus"]), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        painter.restore()


class PaletteDelegate(QStyledItemDelegate):
    """Render and edit palette values in Qt item views."""

    def sizeHint(self, _option, _index):
        """Return the preferred size used by Qt layout and item views."""

        return QSize(420, 54)

    def paint(self, painter, option, index):
        """Paint the item represented by the Qt delegate index."""

        palette = index.data(Qt.UserRole)
        if not isinstance(palette, PaletteDefinition):
            return
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        text_rect = option.rect.adjusted(8, 3, -8, -28)
        text_color = option.palette.highlightedText().color() if option.state & QStyle.State_Selected else QColor(
            COLORS["text_primary"]
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole))
        strip = option.rect.adjusted(8, 29, -8, -6)
        segment_width = strip.width() / len(palette.colors)
        for color_index, color in enumerate(palette.colors):
            left = round(strip.left() + color_index * segment_width)
            right = round(strip.left() + (color_index + 1) * segment_width)
            segment = QRect(left, strip.top(), max(1, right - left), strip.height())
            _paint_checkerboard(painter, segment, 4)
            painter.fillRect(segment, color_to_qcolor(color))
        painter.setPen(QPen(QColor(COLORS["text_primary"]), 1))
        painter.drawRect(strip)
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor(COLORS["focus"]), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        painter.restore()


def _configure_color_view(view: QListView) -> None:
    view.setViewMode(QListView.IconMode)
    view.setResizeMode(QListView.Adjust)
    view.setMovement(QListView.Static)
    view.setWrapping(True)
    view.setUniformItemSizes(True)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setItemDelegate(ColorGridDelegate(view))
    view.setAccessibleName("颜色网格")
