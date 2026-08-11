"""Provide reusable color and palette selection widgets."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
    PaletteSource,
    all_single_colors,
    normalize_color,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
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


class CustomPaletteDialog(QDialog):
    """Provide the custom palette dialog Qt widget."""

    def __init__(self, library: ColorLibrary, palette: PaletteDefinition | None = None, parent=None):
        super().__init__(parent)
        self.library = library
        self.palette = palette
        self.result_palette: PaletteDefinition | None = None
        self.setWindowTitle("编辑自定义配色" if palette else "新建自定义配色")
        self.resize(420, 420)

        layout = QVBoxLayout(self)
        self.name_input = QLineEdit(palette.name if palette else "", self)
        self.name_input.setPlaceholderText("配色名称")
        self.name_input.setAccessibleName("自定义配色名称")
        layout.addWidget(QLabel("名称：", self))
        layout.addWidget(self.name_input)

        self.color_list = QListWidget(self)
        self.color_list.setAccessibleName("自定义配色颜色列表")
        self.color_list.itemDoubleClicked.connect(lambda *_args: self.edit_color())
        layout.addWidget(self.color_list)

        row = QHBoxLayout()
        self.add_button = QPushButton("添加颜色", self)
        self.edit_button = QPushButton("编辑颜色", self)
        self.remove_button = QPushButton("移除", self)
        self.up_button = QPushButton("上移", self)
        self.down_button = QPushButton("下移", self)
        for button in (
            self.add_button,
            self.edit_button,
            self.remove_button,
            self.up_button,
            self.down_button,
        ):
            row.addWidget(button)
        layout.addLayout(row)

        self.add_button.clicked.connect(self.add_color)
        self.edit_button.clicked.connect(self.edit_color)
        self.remove_button.clicked.connect(self.remove_color)
        self.up_button.clicked.connect(lambda: self.move_color(-1))
        self.down_button.clicked.connect(lambda: self.move_color(1))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        initial_colors = palette.colors if palette else ("#1F77B4", "#FF7F0E")
        for color in initial_colors:
            self._append_color(color)

    def _append_color(self, color) -> None:
        normalized = normalize_color(color)
        item = QListWidgetItem(color_rgba_text(normalized))
        item.setData(Qt.UserRole, normalized)
        item.setToolTip(color_rgba_text(normalized))
        self.color_list.addItem(item)

    def _choose_color(self, initial) -> str | None:
        selected = QColorDialog.getColor(
            color_to_qcolor(initial),
            self,
            "选择颜色",
            QColorDialog.ShowAlphaChannel,
        )
        return qcolor_to_color(selected) if selected.isValid() else None

    def add_color(self):
        """Add color."""

        if self.color_list.count() >= 12:
            status_messages.show_warning("自定义配色最多包含 12 个颜色。")
            return
        color = self._choose_color("#000000")
        if color is not None:
            self._append_color(color)

    def edit_color(self):
        """Open the editor for a custom palette color."""

        item = self.color_list.currentItem()
        if item is None:
            return
        color = self._choose_color(item.data(Qt.UserRole))
        if color is not None:
            item.setData(Qt.UserRole, color)
            item.setText(color_rgba_text(color))
            item.setToolTip(color_rgba_text(color))

    def remove_color(self):
        """Remove color."""

        row = self.color_list.currentRow()
        if row >= 0:
            self.color_list.takeItem(row)

    def move_color(self, offset: int):
        """Move color."""

        row = self.color_list.currentRow()
        target = row + int(offset)
        if row < 0 or not 0 <= target < self.color_list.count():
            return
        item = self.color_list.takeItem(row)
        self.color_list.insertItem(target, item)
        self.color_list.setCurrentRow(target)

    def _save_and_accept(self):
        colors = [
            self.color_list.item(index).data(Qt.UserRole)
            for index in range(self.color_list.count())
        ]
        try:
            if self.palette is None:
                self.result_palette = self.library.create_custom_palette(
                    self.name_input.text(), colors
                )
            else:
                self.result_palette = self.library.update_custom_palette(
                    self.palette.id, self.name_input.text(), colors
                )
        except ValueError as exc:
            status_messages.show_error(str(exc))
            QMessageBox.warning(self, "无效配色", str(exc))
            return
        status_messages.show_success(f"已保存自定义配色“{self.result_palette.name}”。")
        self.accept()


class ColorPickerDialog(QDialog):
    """Provide the color picker dialog Qt widget."""

    COLOR_MODE = "color"
    PALETTE_MODE = "palette"

    def __init__(
        self,
        library: ColorLibrary,
        selection: ColorSelection | None = None,
        *,
        mode: str = COLOR_MODE,
        parent=None,
    ):
        super().__init__(parent)
        if mode not in {self.COLOR_MODE, self.PALETTE_MODE}:
            raise ValueError(f"Unsupported color picker mode: {mode}")
        self.library = library
        self.mode = mode
        self._selection = selection or ColorSelection("#000000")
        self._selected_palette: PaletteDefinition | None = self._selection.palette
        self._syncing_opacity = False
        self.setObjectName("color_picker_dialog")
        self.setWindowTitle("选择配色" if mode == self.PALETTE_MODE else "选择颜色")
        self.resize(700, 570)
        self.setMinimumSize(560, 440)

        layout = QVBoxLayout(self)
        if self.library.consume_load_warning():
            status_messages.show_warning("部分颜色库设置无效，已忽略并保留可用项目。")

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        self.recent_model = ColorGridModel(parent=self)
        self.favorite_model = ColorGridModel(parent=self)
        self.all_model = ColorGridModel(parent=self)
        self.palette_model = PaletteListModel(library=self.library, parent=self)
        self.palette_color_model = ColorGridModel(parent=self)

        if mode == self.COLOR_MODE:
            self.recent_view = self._add_color_tab("最近", self.recent_model)
            self.favorite_view = self._add_color_tab("收藏", self.favorite_model)
            all_page = QWidget(self)
            all_layout = QVBoxLayout(all_page)
            self.search_input = QLineEdit(all_page)
            self.search_input.setPlaceholderText("搜索 HEX，例如 #1F77B4")
            self.search_input.setAccessibleName("搜索颜色")
            self.search_input.textChanged.connect(self._filter_all_colors)
            all_layout.addWidget(self.search_input)
            self.all_view = QListView(all_page)
            _configure_color_view(self.all_view)
            self.all_view.setModel(self.all_model)
            self._connect_color_view(self.all_view)
            all_layout.addWidget(self.all_view)
            self.tabs.addTab(all_page, "全部颜色")

        self.palette_page = QWidget(self)
        palette_layout = QVBoxLayout(self.palette_page)
        self.palette_filter = QComboBox(self.palette_page)
        self.palette_filter.addItems(("全部配色", "收藏配色", "内置配色", "自定义配色"))
        self.palette_filter.setAccessibleName("配色分类")
        self.palette_filter.currentIndexChanged.connect(self._refresh_models)
        palette_layout.addWidget(self.palette_filter)
        self.palette_view = QListView(self.palette_page)
        self.palette_view.setModel(self.palette_model)
        self.palette_view.setItemDelegate(PaletteDelegate(self.palette_view))
        self.palette_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.palette_view.setAccessibleName("配色组合列表")
        self.palette_view.clicked.connect(self._palette_selected)
        self.palette_view.doubleClicked.connect(self._palette_double_clicked)
        self.palette_view.activated.connect(self._palette_double_clicked)
        palette_layout.addWidget(self.palette_view, 2)

        self.palette_colors_view = QListView(self.palette_page)
        _configure_color_view(self.palette_colors_view)
        self.palette_colors_view.setModel(self.palette_color_model)
        self._connect_color_view(self.palette_colors_view)
        self.palette_colors_view.setMaximumHeight(140)
        self.palette_colors_view.setVisible(mode == self.COLOR_MODE)
        palette_layout.addWidget(self.palette_colors_view, 1)

        palette_buttons = QHBoxLayout()
        self.favorite_palette_button = QPushButton("收藏配色", self.palette_page)
        self.new_palette_button = QPushButton("新建配色", self.palette_page)
        self.edit_palette_button = QPushButton("编辑配色", self.palette_page)
        self.delete_palette_button = QPushButton("删除配色", self.palette_page)
        palette_buttons.addWidget(self.favorite_palette_button)
        palette_buttons.addStretch()
        palette_buttons.addWidget(self.new_palette_button)
        palette_buttons.addWidget(self.edit_palette_button)
        palette_buttons.addWidget(self.delete_palette_button)
        palette_layout.addLayout(palette_buttons)
        self.tabs.addTab(self.palette_page, "配色组合")

        self.favorite_palette_button.clicked.connect(self._toggle_palette_favorite)
        self.new_palette_button.clicked.connect(self._new_palette)
        self.edit_palette_button.clicked.connect(self._edit_palette)
        self.delete_palette_button.clicked.connect(self._delete_palette)

        if mode == self.COLOR_MODE:
            current_row = QHBoxLayout()
            self.preview = ColorSwatch(self._selection.color, self)
            current_row.addWidget(self.preview)
            current_controls = QVBoxLayout()
            self.hex_input = QLineEdit(self._selection.color, self)
            self.hex_input.setAccessibleName("颜色十六进制值")
            self.hex_input.editingFinished.connect(self._hex_edited)
            current_controls.addWidget(self.hex_input)
            rgba_row = QHBoxLayout()
            self.rgba_inputs = []
            for label_text in ("R", "G", "B"):
                rgba_row.addWidget(QLabel(label_text, self))
                channel_input = QSpinBox(self)
                channel_input.setRange(0, 255)
                channel_input.setAccessibleName(f"{label_text} 颜色通道")
                channel_input.valueChanged.connect(self._rgba_changed)
                self.rgba_inputs.append(channel_input)
                rgba_row.addWidget(channel_input)
            current_controls.addLayout(rgba_row)
            opacity_row = QHBoxLayout()
            opacity_row.addWidget(QLabel("不透明度：", self))
            self.opacity_input = QSpinBox(self)
            self.opacity_input.setRange(0, 100)
            self.opacity_input.setSuffix("%")
            self.opacity_input.valueChanged.connect(self._opacity_changed)
            opacity_row.addWidget(self.opacity_input)
            self.custom_color_button = QPushButton("自定义颜色…", self)
            self.custom_color_button.clicked.connect(self._choose_custom_color)
            opacity_row.addWidget(self.custom_color_button)
            self.copy_color_button = QPushButton("复制", self)
            self.copy_color_button.setAccessibleName("复制当前颜色")
            self.copy_color_button.clicked.connect(self._copy_color)
            opacity_row.addWidget(self.copy_color_button)
            current_controls.addLayout(opacity_row)
            current_row.addLayout(current_controls, 1)
            self.favorite_color_button = QPushButton(self)
            self.favorite_color_button.clicked.connect(self._toggle_color_favorite)
            current_row.addWidget(self.favorite_color_button)
            layout.addLayout(current_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._accept_current)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.library.changed.connect(self._refresh_models)
        self._refresh_models()
        if mode == self.COLOR_MODE:
            self._sync_current_controls()

    def _add_color_tab(self, title: str, model: ColorGridModel) -> QListView:
        view = QListView(self)
        _configure_color_view(view)
        view.setModel(model)
        self._connect_color_view(view)
        self.tabs.addTab(view, title)
        return view

    def _connect_color_view(self, view: QListView) -> None:
        view.clicked.connect(self._color_selected)
        view.doubleClicked.connect(self._color_double_clicked)
        view.activated.connect(self._color_double_clicked)

    def _all_color_selections(self) -> list[ColorSelection]:
        return [ColorSelection(color) for color in all_single_colors()]

    def _refresh_models(self):
        if self.mode == self.COLOR_MODE:
            self.recent_model.set_selections(
                ColorSelection(color) for color in self.library.recent_colors
            )
            self.favorite_model.set_selections(
                ColorSelection(color) for color in self.library.favorite_colors
            )
            self._filter_all_colors(self.search_input.text())
        palettes = self.library.palettes()
        palette_filter = self.palette_filter.currentIndex()
        if palette_filter == 1:
            favorite_ids = set(self.library.favorite_palette_ids)
            palettes = tuple(palette for palette in palettes if palette.id in favorite_ids)
        elif palette_filter == 2:
            palettes = tuple(
                palette
                for palette in palettes
                if palette.source is PaletteSource.BUILTIN
            )
        elif palette_filter == 3:
            palettes = tuple(
                palette
                for palette in palettes
                if palette.source is PaletteSource.CUSTOM
            )
        self.palette_model.set_palettes(palettes)
        if self._selected_palette is not None:
            current = self.library.palette(self._selected_palette.id)
            if current is not None:
                self._selected_palette = current
            self._show_palette_colors(self._selected_palette)
        self._sync_palette_buttons()
        if self.mode == self.COLOR_MODE:
            self._sync_current_controls()

    def _filter_all_colors(self, query: str):
        query = str(query).strip().upper()
        selections = self._all_color_selections()
        if query:
            selections = [selection for selection in selections if query in selection.color]
        self.all_model.set_selections(selections)

    def _color_selected(self, index: QModelIndex):
        selection = index.data(Qt.UserRole)
        if isinstance(selection, ColorSelection):
            self._selection = selection
            self._sync_current_controls()

    def _color_double_clicked(self, index: QModelIndex):
        self._color_selected(index)
        if self.mode == self.COLOR_MODE:
            self.accept()

    def _palette_selected(self, index: QModelIndex):
        palette = index.data(Qt.UserRole)
        if not isinstance(palette, PaletteDefinition):
            return
        self._selected_palette = palette
        self._show_palette_colors(palette)
        self._sync_palette_buttons()

    def _palette_double_clicked(self, index: QModelIndex):
        self._palette_selected(index)
        if self.mode == self.PALETTE_MODE and self._selected_palette is not None:
            self.accept()

    def _show_palette_colors(self, palette: PaletteDefinition):
        self.palette_color_model.set_selections(
            ColorSelection(color, palette, index)
            for index, color in enumerate(palette.colors)
        )

    def _sync_current_controls(self):
        if self.mode != self.COLOR_MODE:
            return
        color = color_to_qcolor(self._selection.color)
        self.preview.set_color(self._selection.color)
        self.hex_input.setText(self._selection.color)
        self._syncing_opacity = True
        for channel_input, value in zip(
            self.rgba_inputs, (color.red(), color.green(), color.blue())
        ):
            channel_input.setValue(value)
        self.opacity_input.setValue(round(color.alphaF() * 100))
        self._syncing_opacity = False
        favorite = self.library.is_favorite_color(self._selection.color)
        self.favorite_color_button.setText("取消收藏" if favorite else "收藏颜色")
        self.favorite_color_button.setAccessibleName(
            ("取消收藏颜色 " if favorite else "收藏颜色 ") + self._selection.color
        )

    def _sync_palette_buttons(self):
        palette = self._selected_palette
        has_palette = palette is not None
        is_custom = bool(
            palette and palette.source is PaletteSource.CUSTOM
        )
        self.favorite_palette_button.setEnabled(has_palette)
        self.edit_palette_button.setEnabled(is_custom)
        self.delete_palette_button.setEnabled(is_custom)
        if palette:
            favorite = self.library.is_favorite_palette(palette.id)
            self.favorite_palette_button.setText("取消收藏配色" if favorite else "收藏配色")

    def _hex_edited(self):
        try:
            self._selection = ColorSelection(self.hex_input.text())
        except ValueError as exc:
            status_messages.show_error(str(exc))
            self._sync_current_controls()
            return
        self._sync_current_controls()

    def _opacity_changed(self, opacity: int):
        if self._syncing_opacity:
            return
        color = color_to_qcolor(self._selection.color)
        color.setAlpha(round(int(opacity) * 255 / 100))
        self._selection = ColorSelection(qcolor_to_color(color))
        self._sync_current_controls()

    def _rgba_changed(self):
        if self._syncing_opacity:
            return
        red, green, blue = (widget.value() for widget in self.rgba_inputs)
        alpha = round(self.opacity_input.value() * 255 / 100)
        self._selection = ColorSelection(qcolor_to_color(QColor(red, green, blue, alpha)))
        self._sync_current_controls()

    def _copy_color(self):
        QApplication.clipboard().setText(self._selection.color)
        status_messages.show_success(f"已复制颜色 {self._selection.color}。")

    def _choose_custom_color(self):
        selected = QColorDialog.getColor(
            color_to_qcolor(self._selection.color),
            self,
            "选择自定义颜色",
            QColorDialog.ShowAlphaChannel,
        )
        if selected.isValid():
            self._selection = ColorSelection(qcolor_to_color(selected))
            self._sync_current_controls()

    def _toggle_color_favorite(self):
        self.library.toggle_favorite_color(self._selection.color)

    def _toggle_palette_favorite(self):
        if self._selected_palette is not None:
            self.library.toggle_favorite_palette(self._selected_palette.id)

    def _new_palette(self):
        dialog = CustomPaletteDialog(self.library, parent=self)
        if dialog.exec() == QDialog.Accepted and dialog.result_palette is not None:
            self._selected_palette = dialog.result_palette
            self._refresh_models()

    def _edit_palette(self):
        if (
            self._selected_palette is None
            or self._selected_palette.source is not PaletteSource.CUSTOM
        ):
            return
        dialog = CustomPaletteDialog(self.library, self._selected_palette, self)
        if dialog.exec() == QDialog.Accepted and dialog.result_palette is not None:
            self._selected_palette = dialog.result_palette
            self._refresh_models()

    def _delete_palette(self):
        palette = self._selected_palette
        if palette is None or palette.source is not PaletteSource.CUSTOM:
            return
        answer = QMessageBox.question(
            self,
            "删除自定义配色",
            f"确定从应用颜色库删除“{palette.name}”吗？已有图表和项目快照不会改变。",
        )
        if answer != QMessageBox.Yes:
            return
        if self.library.delete_custom_palette(palette.id):
            status_messages.show_success(f"已删除自定义配色“{palette.name}”。")
        self._selected_palette = None
        self.palette_color_model.set_selections(())
        self._refresh_models()

    def _accept_current(self):
        if self.mode == self.PALETTE_MODE and self._selected_palette is None:
            status_messages.show_warning("请先选择一个配色组合。")
            return
        self.accept()

    def selection(self) -> ColorSelection:
        """Return the current color selection."""

        return self._selection

    def selected_palette(self) -> PaletteDefinition | None:
        """Return the selected palette."""

        return self._selected_palette


class ColorSelector(ColorCycleState):
    """Compatibility name for the former per-axes selector."""

    def get_color(self):
        """Return color."""

        return self.peek().color


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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.color_display = ColorSwatch(self._selection.color, self)
        layout.addWidget(self.color_display)

        controls = QVBoxLayout()
        self.color_button = QPushButton("选择颜色…", self)
        self.color_button.setAccessibleName("打开颜色选择器")
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
        self.favorite_button.setToolTip("取消收藏当前颜色" if favorite else "收藏当前颜色")
        self.favorite_button.setAccessibleName(self.favorite_button.toolTip())

    def _toggle_favorite(self):
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
