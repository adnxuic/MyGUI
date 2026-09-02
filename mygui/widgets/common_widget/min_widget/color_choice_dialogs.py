"""Palette editor and color/palette picker dialogs."""

from __future__ import annotations


from PySide6.QtCore import QModelIndex, QSignalBlocker, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.widgets.english_buttons import (
    apply_english_dialog_buttons,
    ask_yes_no,
)
from mygui.figuremodify.style_base.color_models import (
    ColorSelection,
    PaletteDefinition,
    PaletteSource,
    all_single_colors,
    normalize_color,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from .color_choice_model import (
    ColorGridModel,
    ColorSwatch,
    PaletteDelegate,
    PaletteListModel,
    _configure_color_view,
    color_rgba_text,
    color_to_qcolor,
    qcolor_to_color,
)

class CustomPaletteDialog(QDialog):
    """Provide the custom palette dialog Qt widget."""

    def __init__(self, library: ColorLibrary, palette: PaletteDefinition | None = None, parent=None):
        super().__init__(parent)
        self.library = library
        self.palette = palette
        self.result_palette: PaletteDefinition | None = None
        self.setWindowTitle("Edit Custom Palette" if palette else "New Custom Palette")
        self.resize(420, 420)

        layout = QVBoxLayout(self)
        self.name_input = QLineEdit(palette.name if palette else "", self)
        self.name_input.setPlaceholderText("Palette name")
        self.name_input.setAccessibleName("Custom palette name")
        layout.addWidget(QLabel("Name", self))
        layout.addWidget(self.name_input)

        self.color_list = QListWidget(self)
        self.color_list.setAccessibleName("Custom palette colors")
        self.color_list.itemDoubleClicked.connect(lambda *_args: self.edit_color())
        layout.addWidget(self.color_list)

        row = QHBoxLayout()
        self.add_button = QPushButton("Add Color", self)
        self.edit_button = QPushButton("Edit Color", self)
        self.remove_button = QPushButton("Remove", self)
        self.up_button = QPushButton("Move Up", self)
        self.down_button = QPushButton("Move Down", self)
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
        apply_english_dialog_buttons(buttons)
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
            "Choose Color",
            QColorDialog.ShowAlphaChannel,
        )
        return qcolor_to_color(selected) if selected.isValid() else None

    def add_color(self):
        """Add color."""

        if self.color_list.count() >= 12:
            status_messages.show_warning("A custom palette can contain at most 12 colors.")
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
            QMessageBox.warning(self, "Invalid Palette", str(exc))
            return
        status_messages.show_success(
            f'Saved custom palette "{self.result_palette.name}".'
        )
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
        self.setWindowTitle(
            "Choose Palette" if mode == self.PALETTE_MODE else "Choose Color"
        )
        self.resize(700, 570)
        self.setMinimumSize(560, 440)

        layout = QVBoxLayout(self)
        if self.library.consume_load_warning():
            status_messages.show_warning(
                "Some color library settings were invalid and have been ignored."
            )

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        self.recent_model = ColorGridModel(parent=self)
        self.favorite_model = ColorGridModel(parent=self)
        self.all_model = ColorGridModel(parent=self)
        self.palette_model = PaletteListModel(library=self.library, parent=self)
        self.palette_color_model = ColorGridModel(parent=self)

        if mode == self.COLOR_MODE:
            self.recent_view = self._add_color_tab("Recent", self.recent_model)
            self.favorite_view = self._add_color_tab("Favorites", self.favorite_model)
            all_page = QWidget(self)
            all_layout = QVBoxLayout(all_page)
            self.search_input = QLineEdit(all_page)
            self.search_input.setPlaceholderText("Search HEX, for example #1F77B4")
            self.search_input.setAccessibleName("Search colors")
            self.search_input.textChanged.connect(self._filter_all_colors)
            all_layout.addWidget(self.search_input)
            self.all_view = QListView(all_page)
            _configure_color_view(self.all_view)
            self.all_view.setModel(self.all_model)
            self._connect_color_view(self.all_view)
            all_layout.addWidget(self.all_view)
            self.tabs.addTab(all_page, "All Colors")

        self.palette_page = QWidget(self)
        palette_layout = QVBoxLayout(self.palette_page)
        self.palette_filter = QComboBox(self.palette_page)
        self.palette_filter.addItems(
            ("All Palettes", "Favorite Palettes", "Built-in Palettes", "Custom Palettes")
        )
        self.palette_filter.setAccessibleName("Palette category")
        self.palette_filter.currentIndexChanged.connect(self._refresh_models)
        palette_layout.addWidget(self.palette_filter)
        self.palette_view = QListView(self.palette_page)
        self.palette_view.setModel(self.palette_model)
        self.palette_view.setItemDelegate(PaletteDelegate(self.palette_view))
        self.palette_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.palette_view.setAccessibleName("Palette list")
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
        self.favorite_palette_button = QPushButton("Favorite Palette", self.palette_page)
        self.new_palette_button = QPushButton("New Palette", self.palette_page)
        self.edit_palette_button = QPushButton("Edit Palette", self.palette_page)
        self.delete_palette_button = QPushButton("Delete Palette", self.palette_page)
        palette_buttons.addWidget(self.favorite_palette_button)
        palette_buttons.addStretch()
        palette_buttons.addWidget(self.new_palette_button)
        palette_buttons.addWidget(self.edit_palette_button)
        palette_buttons.addWidget(self.delete_palette_button)
        palette_layout.addLayout(palette_buttons)
        self.tabs.addTab(self.palette_page, "Palettes")

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
            self.hex_input.setAccessibleName("Color hexadecimal value")
            self.hex_input.editingFinished.connect(self._hex_edited)
            current_controls.addWidget(self.hex_input)
            rgba_row = QHBoxLayout()
            self.rgba_inputs = []
            for label_text in ("R", "G", "B"):
                rgba_row.addWidget(QLabel(label_text, self))
                channel_input = QSpinBox(self)
                channel_input.setRange(0, 255)
                channel_input.setAccessibleName(f"{label_text} color channel")
                channel_input.valueChanged.connect(self._rgba_changed)
                self.rgba_inputs.append(channel_input)
                rgba_row.addWidget(channel_input)
            current_controls.addLayout(rgba_row)
            opacity_row = QHBoxLayout()
            opacity_row.addWidget(QLabel("Opacity", self))
            self.opacity_input = QSpinBox(self)
            self.opacity_input.setRange(0, 100)
            self.opacity_input.setSuffix("%")
            self.opacity_input.valueChanged.connect(self._opacity_changed)
            opacity_row.addWidget(self.opacity_input)
            self.custom_color_button = QPushButton("Custom Color…", self)
            self.custom_color_button.clicked.connect(self._choose_custom_color)
            opacity_row.addWidget(self.custom_color_button)
            self.copy_color_button = QPushButton("Copy", self)
            self.copy_color_button.setAccessibleName("Copy current color")
            self.copy_color_button.clicked.connect(self._copy_color)
            opacity_row.addWidget(self.copy_color_button)
            current_controls.addLayout(opacity_row)
            current_row.addLayout(current_controls, 1)
            self.favorite_color_button = QPushButton(self)
            self.favorite_color_button.clicked.connect(self._toggle_color_favorite)
            current_row.addWidget(self.favorite_color_button)
            layout.addLayout(current_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        apply_english_dialog_buttons(self.buttons)
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
        blockers = [
            QSignalBlocker(self.hex_input),
            QSignalBlocker(self.opacity_input),
            *[QSignalBlocker(widget) for widget in self.rgba_inputs],
        ]
        self.hex_input.setText(self._selection.color)
        for channel_input, value in zip(
            self.rgba_inputs, (color.red(), color.green(), color.blue()), strict=True
        ):
            channel_input.setValue(value)
        self.opacity_input.setValue(round(color.alphaF() * 100))
        del blockers
        favorite = self.library.is_favorite_color(self._selection.color)
        self.favorite_color_button.setText(
            "Unfavorite" if favorite else "Favorite Color"
        )
        self.favorite_color_button.setAccessibleName(
            ("Unfavorite color " if favorite else "Favorite color ")
            + self._selection.color
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
            self.favorite_palette_button.setText(
                "Unfavorite Palette" if favorite else "Favorite Palette"
            )

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
        status_messages.show_success(f"Copied color {self._selection.color}.")

    def _choose_custom_color(self):
        selected = QColorDialog.getColor(
            color_to_qcolor(self._selection.color),
            self,
            "Choose Custom Color",
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
        if not ask_yes_no(
            self,
            "Delete Custom Palette",
            (
                f'Delete "{palette.name}" from the application color library? '
                "Existing charts and project snapshots will not change."
            ),
        ):
            return
        if self.library.delete_custom_palette(palette.id):
            status_messages.show_success(f'Deleted custom palette "{palette.name}".')
        self._selected_palette = None
        self.palette_color_model.set_selections(())
        self._refresh_models()

    def _accept_current(self):
        if self.mode == self.PALETTE_MODE and self._selected_palette is None:
            status_messages.show_warning("Select a palette first.")
            return
        self.accept()

    def selection(self) -> ColorSelection:
        """Return the current color selection."""

        return self._selection

    def selected_palette(self) -> PaletteDefinition | None:
        """Return the selected palette."""

        return self._selected_palette
