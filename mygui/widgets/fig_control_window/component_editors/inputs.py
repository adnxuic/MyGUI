"""Provide Controller-free inputs shared with component creation dialogs."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    TableChangeSet,
    TableRepository,
)
from mygui.figuremodify.matplotlib_adapter import available_colormap_names
from mygui.database.interpolate_func import (
    DEFAULT_INTERPOLATION_SAMPLES,
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    interpolate_dict,
    interpolation_uses_lambda,
    interpolation_uses_order,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    InAxesCreateSpec,
    ZoomInAxesCreateSpec,
    embedded_image_data,
)
from mygui.figuremodify.components.property_values import DEFAULT_NORM

from .common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
    LineStyleEditor,
    parse_number_sequence,
)


class ColorbarInput(QFrame):
    """Controller-free source and placement input for Colorbar creation."""

    def __init__(self, sources, *, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source_input = QComboBox(self)
        for component_id, label in sources:
            self.source_input.addItem(str(label), str(component_id))
        layout.addRow("Source:", self.source_input)

        self.location_input = QComboBox(self)
        self.location_input.addItems(("right", "left", "top", "bottom"))
        layout.addRow("Location:", self.location_input)
        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)

        self.fraction_input = FocusAwareDoubleSpinBox(self)
        self.fraction_input.setRange(0.001, 1.0)
        self.fraction_input.setDecimals(3)
        self.fraction_input.setSingleStep(0.01)
        self.fraction_input.setValue(0.15)
        layout.addRow("Fraction:", self.fraction_input)

        self.shrink_input = FocusAwareDoubleSpinBox(self)
        self.shrink_input.setRange(0.001, 1.0)
        self.shrink_input.setDecimals(3)
        self.shrink_input.setSingleStep(0.05)
        self.shrink_input.setValue(1.0)
        layout.addRow("Shrink:", self.shrink_input)

        self.aspect_input = FocusAwareDoubleSpinBox(self)
        self.aspect_input.setRange(0.001, 10000.0)
        self.aspect_input.setDecimals(3)
        self.aspect_input.setValue(20.0)
        layout.addRow("Aspect:", self.aspect_input)

        self.pad_input = FocusAwareDoubleSpinBox(self)
        self.pad_input.setRange(0.0, 1.0)
        self.pad_input.setDecimals(3)
        self.pad_input.setSingleStep(0.01)
        self.pad_input.setValue(0.05)
        layout.addRow("Pad:", self.pad_input)

    def has_source(self) -> bool:
        """Return whether creation has one eligible stable source id."""

        return self.source_input.count() > 0

    def source_component_id(self) -> str | None:
        """Return the selected stable source component id."""

        value = self.source_input.currentData(Qt.UserRole)
        return str(value) if value is not None else None

    def properties(self) -> dict[str, object]:
        """Return the complete user-selected Colorbar creation patch."""

        return {
            "location": self.location_input.currentText(),
            "label": self.label_input.text(),
            "fraction": float(self.fraction_input.value()),
            "shrink": float(self.shrink_input.value()),
            "aspect": float(self.aspect_input.value()),
            "pad": float(self.pad_input.value()),
        }


class ReferenceMarksInput(QFrame):
    """Controller-free typed input for Reflection Positions creation."""

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        defaults,
        parent=None,
    ):
        super().__init__(parent)
        if color_library is None:
            raise ValueError(
                "ReferenceMarksInput requires the application ColorLibrary."
            )
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label_input = QLineEdit(self)
        layout.addRow("Label:", self.label_input)

        self.positions_input = QLineEdit(self)
        self.positions_input.setPlaceholderText(
            "Comma or space separated values, e.g. 15.1876, 15.2256"
        )
        layout.addRow("Positions:", self.positions_input)

        self.baseline_input = FocusAwareDoubleSpinBox(self)
        self.baseline_input.setRange(0.0, 1.0)
        self.baseline_input.setDecimals(4)
        self.baseline_input.setSingleStep(0.005)
        self.baseline_input.setValue(0.08)
        layout.addRow("Baseline:", self.baseline_input)

        self.height_input = FocusAwareDoubleSpinBox(self)
        self.height_input.setRange(0.000000001, 1.0)
        self.height_input.setDecimals(9)
        self.height_input.setSingleStep(0.005)
        self.height_input.setValue(0.025)
        layout.addRow("Height:", self.height_input)

        self.color_input = ColorChoiceWidget(
            defaults.color,
            color_library=color_library,
            parent=self,
        )
        layout.addRow("Color:", self.color_input)

        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1000.0)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setSingleStep(0.1)
        self.linewidth_input.setValue(float(defaults.linewidth))
        layout.addRow("Line width:", self.linewidth_input)

    def positions(self) -> list[float]:
        """Return the typed ordered numeric sequence."""

        return [
            float(value)
            for value in parse_number_sequence(self.positions_input.text())
        ]

    def properties(self) -> dict[str, object]:
        """Return the Controller-free creation property patch."""

        return {
            "label": self.label_input.text(),
            "baseline": float(self.baseline_input.value()),
            "height": float(self.height_input.value()),
            "color": self.color_input.color(),
            "linewidth": float(self.linewidth_input.value()),
        }


class DataReferenceInput(QFrame):
    """Controller-free X/Y column selector shared by create and edit UIs."""

    refsChanged = Signal(object, object)

    def __init__(
        self,
        repository: TableRepository,
        project_id: str | None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.project_id = project_id
        self._disposed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.x_layout = QHBoxLayout()
        self.y_layout = QHBoxLayout()
        self.x_data_input = QComboBox(self)
        self.y_data_input = QComboBox(self)
        self.x_expression_input = QLineEdit("x", self)
        self.y_expression_input = QLineEdit("y", self)
        expression_tooltip = (
            "Safe preprocessing expression using the original x and y data. "
            "Examples: 1/x, log10(y), y/x."
        )
        self.x_expression_input.setToolTip(expression_tooltip)
        self.y_expression_input.setToolTip(expression_tooltip)
        self.x_expression_input.setMinimumWidth(90)
        self.y_expression_input.setMinimumWidth(90)
        self.x_layout.addWidget(QLabel("X Data:", self))
        self.x_layout.addWidget(self.x_data_input)
        self.x_layout.addWidget(QLabel("fx:", self))
        self.x_layout.addWidget(self.x_expression_input)
        self.y_layout.addWidget(QLabel("Y Data:", self))
        self.y_layout.addWidget(self.y_data_input)
        self.y_layout.addWidget(QLabel("fx:", self))
        self.y_layout.addWidget(self.y_expression_input)
        layout.addLayout(self.x_layout)
        layout.addLayout(self.y_layout)

        self.repository.transaction_committed.connect(
            self._repository_changed
        )
        self.x_data_input.currentIndexChanged.connect(
            self._emit_refs_changed
        )
        self.y_data_input.currentIndexChanged.connect(
            self._emit_refs_changed
        )
        self.update_data()

    def _repository_changed(self, changes: TableChangeSet) -> None:
        if self._disposed:
            return
        if (
            self.project_id is not None
            and self.project_id not in self.repository.projects
        ):
            self.dispose()
            return
        if (
            self.project_id is not None
            and changes.project_id == self.project_id
            and (changes.metadata_changed or changes.structure_changed)
        ):
            self.update_data()

    @staticmethod
    def _current_ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    def update_data(self) -> None:
        """Update data."""

        current_x = self.get_x_ref()
        current_y = self.get_y_ref()
        if self.project_id is None:
            x_refs: list[ColumnRef] = []
            y_refs: list[ColumnRef] = []
        else:
            x_refs = list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER, ColumnType.DATETIME},
                )
            )
            y_refs = list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER},
                )
            )
        self._populate(self.x_data_input, x_refs, current_x)
        self._populate(self.y_data_input, y_refs, current_y)

    def _populate(
        self,
        combo: QComboBox,
        refs: list[ColumnRef],
        current: ColumnRef | None,
    ) -> None:
        blocker = QSignalBlocker(combo)
        combo.clear()
        for ref in refs:
            combo.addItem(self.repository.ref_label(ref), ref)
        if current is not None:
            self._set_ref(combo, current)
        del blocker

    def get_x_ref(self) -> ColumnRef | None:
        """Return x ref."""

        return self._current_ref(self.x_data_input)

    def get_y_ref(self) -> ColumnRef | None:
        """Return y ref."""

        return self._current_ref(self.y_data_input)

    @staticmethod
    def _set_ref(combo: QComboBox, ref: ColumnRef | None) -> None:
        if ref is not None:
            for index in range(combo.count()):
                if combo.itemData(index, Qt.UserRole) == ref:
                    combo.setCurrentIndex(index)
                    return
        combo.setCurrentIndex(-1)

    def set_x_ref(self, ref: ColumnRef | None) -> None:
        """Set x ref."""

        blocker = QSignalBlocker(self.x_data_input)
        self._set_ref(self.x_data_input, ref)
        del blocker

    def set_y_ref(self, ref: ColumnRef | None) -> None:
        """Set y ref."""

        blocker = QSignalBlocker(self.y_data_input)
        self._set_ref(self.y_data_input, ref)
        del blocker

    def set_refs(
        self,
        x_ref: ColumnRef | None,
        y_ref: ColumnRef | None,
    ) -> None:
        """Set refs."""

        x_blocker = QSignalBlocker(self.x_data_input)
        y_blocker = QSignalBlocker(self.y_data_input)
        self._set_ref(self.x_data_input, x_ref)
        self._set_ref(self.y_data_input, y_ref)
        del x_blocker, y_blocker

    def preprocess_values(self) -> dict[str, str]:
        """Return the current unvalidated expression input values."""

        return {
            "x_expression": self.x_expression_input.text(),
            "y_expression": self.y_expression_input.text(),
        }

    def get_preprocess_spec(self) -> DataPreprocessSpec:
        """Return the validated preprocessing specification."""

        return DataPreprocessSpec.from_dict(self.preprocess_values())

    def set_preprocess(
        self,
        preprocess: DataPreprocessSpec | dict | None,
    ) -> None:
        """Synchronize expression controls without emitting edits."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        x_blocker = QSignalBlocker(self.x_expression_input)
        y_blocker = QSignalBlocker(self.y_expression_input)
        self.x_expression_input.setText(spec.x_expression)
        self.y_expression_input.setText(spec.y_expression)
        del x_blocker, y_blocker

    def refs_connect(self, x_callback, y_callback) -> None:
        """Refresh selectors after their data-reference source changes."""

        self.x_data_input.currentIndexChanged.connect(x_callback)
        self.y_data_input.currentIndexChanged.connect(y_callback)

    def expressions_connect(self, x_callback, y_callback) -> None:
        """Apply expressions only after the user finishes editing a field."""

        self.x_expression_input.editingFinished.connect(x_callback)
        self.y_expression_input.editingFinished.connect(y_callback)

    def dispose(self) -> None:
        """Disconnect callbacks and release resources owned by this object."""

        if self._disposed:
            return
        self._disposed = True
        try:
            self.repository.transaction_committed.disconnect(
                self._repository_changed
            )
        except (RuntimeError, TypeError):
            pass

    def closeEvent(self, event):
        """Handle Qt close events and release owned resources."""

        self.dispose()
        super().closeEvent(event)

    def _emit_refs_changed(self, *_args) -> None:
        self.refsChanged.emit(self.get_x_ref(), self.get_y_ref())


class ScatterMappingInput(QFrame):
    """Controller-free optional color and points-squared mapping input."""

    mappingChanged = Signal()

    def __init__(
        self,
        repository: TableRepository,
        project_id: str | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.project_id = project_id
        self._disposed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        color_row = QHBoxLayout()
        self.color_enabled = QCheckBox("Map color", self)
        self.color_ref_input = QComboBox(self)
        self.cmap_input = QComboBox(self)
        self.cmap_input.addItems(available_colormap_names())
        self.cmap_input.setCurrentText("viridis")
        self.color_nonfinite_input = QComboBox(self)
        self.color_nonfinite_input.addItem("Drop non-finite", "drop")
        self.color_nonfinite_input.addItem("Use bad color", "bad")
        color_row.addWidget(self.color_enabled)
        color_row.addWidget(self.color_ref_input, 1)
        color_row.addWidget(QLabel("Map:", self))
        color_row.addWidget(self.cmap_input)
        color_row.addWidget(self.color_nonfinite_input)
        layout.addLayout(color_row)

        size_row = QHBoxLayout()
        self.size_enabled = QCheckBox("Map size", self)
        self.size_ref_input = QComboBox(self)
        self.size_min_input = FocusAwareDoubleSpinBox(self)
        self.size_max_input = FocusAwareDoubleSpinBox(self)
        for widget, value in (
            (self.size_min_input, 12.0),
            (self.size_max_input, 120.0),
        ):
            widget.setRange(0.0, 1_000_000.0)
            widget.setDecimals(2)
            widget.setValue(value)
            widget.setSuffix(" pt²")
        size_row.addWidget(self.size_enabled)
        size_row.addWidget(self.size_ref_input, 1)
        size_row.addWidget(QLabel("Output:", self))
        size_row.addWidget(self.size_min_input)
        size_row.addWidget(self.size_max_input)
        layout.addLayout(size_row)

        self.repository.transaction_committed.connect(
            self._repository_changed
        )
        for widget in (self.color_enabled, self.size_enabled):
            widget.toggled.connect(self._sync_enabled)
            widget.toggled.connect(self.mappingChanged)
        self.update_data()
        self._sync_enabled()

    @staticmethod
    def _ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    def update_data(self) -> None:
        """Refresh numeric references while retaining stable selections."""

        current = (
            self.color_ref(),
            self.size_ref(),
        )
        refs = (
            []
            if self.project_id is None
            else list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER},
                )
            )
        )
        for combo, selected in zip(
            (self.color_ref_input, self.size_ref_input),
            current,
        ):
            blocker = QSignalBlocker(combo)
            combo.clear()
            combo.addItem("Select a numeric column", None)
            target = 0
            for ref in refs:
                combo.addItem(self.repository.ref_label(ref), ref)
                if ref == selected:
                    target = combo.count() - 1
            combo.setCurrentIndex(target)
            del blocker

    def _repository_changed(self, changes: TableChangeSet) -> None:
        if (
            not self._disposed
            and changes.project_id == self.project_id
            and (changes.structure_changed or changes.metadata_changed)
        ):
            self.update_data()

    def _sync_enabled(self, *_args) -> None:
        color = self.color_enabled.isChecked()
        size = self.size_enabled.isChecked()
        for widget in (
            self.color_ref_input,
            self.cmap_input,
            self.color_nonfinite_input,
        ):
            widget.setEnabled(color)
        for widget in (
            self.size_ref_input,
            self.size_min_input,
            self.size_max_input,
        ):
            widget.setEnabled(size)

    def color_ref(self) -> ColumnRef | None:
        """Return the selected color column only when mapping is enabled."""

        return self._ref(self.color_ref_input) if self.color_enabled.isChecked() else None

    def size_ref(self) -> ColumnRef | None:
        """Return the selected size column only when mapping is enabled."""

        return self._ref(self.size_ref_input) if self.size_enabled.isChecked() else None

    def color_mapping(self) -> dict[str, object]:
        """Return the complete safe colormap specification."""

        if self.color_enabled.isChecked() and self.color_ref() is None:
            raise ValueError("Select a numeric column for Scatter color mapping.")
        return {
            "enabled": self.color_enabled.isChecked(),
            "cmap": self.cmap_input.currentText(),
            "norm": dict(DEFAULT_NORM),
            "bad": "#00000000",
            "under": None,
            "over": None,
            "nonfinite": self.color_nonfinite_input.currentData(),
        }

    def size_mapping(self) -> dict[str, object]:
        """Return the complete points-squared mapping specification."""

        if self.size_enabled.isChecked() and self.size_ref() is None:
            raise ValueError("Select a numeric column for Scatter size mapping.")
        minimum = self.size_min_input.value()
        maximum = self.size_max_input.value()
        if minimum > maximum:
            raise ValueError("Scatter size output minimum exceeds maximum.")
        return {
            "enabled": self.size_enabled.isChecked(),
            "input": None,
            "output": [minimum, maximum],
            "clamp": True,
        }

    def dispose(self) -> None:
        """Detach repository callbacks idempotently."""

        if self._disposed:
            return
        self._disposed = True
        try:
            self.repository.transaction_committed.disconnect(
                self._repository_changed
            )
        except (RuntimeError, TypeError):
            pass


class _CheckableColumnComboBox(QComboBox):
    """Compact multi-select combo box backed by checkable model items."""

    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("Select Y data...")
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
        self.setMaxVisibleItems(12)

        model = QStandardItemModel(self)
        self.setModel(model)
        model.itemChanged.connect(self._item_changed)
        self.view().viewport().installEventFilter(self)
        self._refresh_summary()

    def eventFilter(self, watched, event):
        """Toggle check states without closing the combo popup."""

        if watched is self.view().viewport():
            if event.type() == QEvent.MouseButtonRelease:
                index = self.view().indexAt(event.position().toPoint())
                if index.isValid():
                    self._toggle_index(index)
                    return True
            if (
                event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter)
            ):
                index = self.view().currentIndex()
                if index.isValid():
                    self._toggle_index(index)
                    return True
        return super().eventFilter(watched, event)

    def _toggle_index(self, index: QModelIndex) -> None:
        item = self.model().itemFromIndex(index)
        if item is None:
            return
        item.setCheckState(
            Qt.Unchecked
            if item.checkState() == Qt.Checked
            else Qt.Checked
        )

    def replace_items(
        self,
        entries: list[tuple[str, ColumnRef]],
        selected,
    ) -> None:
        """Replace choices and restore checked values without partial signals."""

        selected_values = set(selected)
        model = self.model()
        blocker = QSignalBlocker(model)
        model.clear()
        for label, ref in entries:
            item = QStandardItem(label)
            item.setData(ref, Qt.UserRole)
            item.setFlags(
                Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
                | Qt.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.Checked if ref in selected_values else Qt.Unchecked
            )
            model.appendRow(item)
        del blocker
        self.setCurrentIndex(-1)
        self._refresh_summary()

    def checked_data(self) -> tuple[ColumnRef, ...]:
        """Return checked references in display order."""

        values: list[ColumnRef] = []
        model = self.model()
        for row in range(model.rowCount()):
            item = model.item(row)
            value = item.data(Qt.UserRole)
            if item.checkState() == Qt.Checked and isinstance(value, ColumnRef):
                values.append(value)
        return tuple(values)

    def set_checked_data(self, selected, *, emit: bool = True) -> None:
        """Replace the checked selection and emit one aggregate change."""

        selected_values = set(selected)
        model = self.model()
        blocker = QSignalBlocker(model)
        for row in range(model.rowCount()):
            item = model.item(row)
            item.setCheckState(
                Qt.Checked
                if item.data(Qt.UserRole) in selected_values
                else Qt.Unchecked
            )
        del blocker
        self._refresh_summary()
        if emit:
            self.selectionChanged.emit()

    def select_all(self) -> None:
        """Check every available item."""

        model = self.model()
        self.set_checked_data(
            item.data(Qt.UserRole)
            for row in range(model.rowCount())
            if (item := model.item(row)) is not None
        )

    def clear_selection(self) -> None:
        """Clear every checked item."""

        self.set_checked_data(())

    def _item_changed(self, _item: QStandardItem) -> None:
        self._refresh_summary()
        self.selectionChanged.emit()

    def _refresh_summary(self) -> None:
        model = self.model()
        labels = [
            model.item(row).text()
            for row in range(model.rowCount())
            if model.item(row).checkState() == Qt.Checked
        ]
        if not labels:
            summary = ""
        elif len(labels) == 1:
            summary = labels[0]
        else:
            summary = f"{len(labels)} Y columns selected"
        self.lineEdit().setText(summary)
        self.setToolTip("\n".join(labels))


class MultiSeriesDataReferenceInput(QFrame):
    """Controller-free shared-X and multi-Y selector for chart creation."""

    refsChanged = Signal(object, object)

    def __init__(
        self,
        repository: TableRepository,
        project_id: str | None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.project_id = project_id
        self._disposed = False
        self._initialized = False
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.x_layout = QHBoxLayout()
        self.x_data_input = QComboBox(self)
        self.x_expression_input = QLineEdit("x", self)
        self.x_expression_input.setPlaceholderText("e.g. x, 1/x")
        self.x_expression_input.setMinimumWidth(90)
        self.x_layout.addWidget(QLabel("X Data:", self))
        self.x_layout.addWidget(self.x_data_input, 1)
        self.x_layout.addWidget(QLabel("X fx:", self))
        self.x_layout.addWidget(self.x_expression_input, 1)
        layout.addLayout(self.x_layout)

        self.y_layout = QHBoxLayout()
        self.y_data_input = _CheckableColumnComboBox(self)
        self.y_data_input.setObjectName("multi_series_y_combo")
        self.y_expression_input = QLineEdit("y", self)
        self.y_expression_input.setPlaceholderText("e.g. y, log10(y)")
        self.y_expression_input.setMinimumWidth(90)
        self.y_layout.addWidget(QLabel("Y Data:", self))
        self.y_layout.addWidget(self.y_data_input, 1)
        self.y_layout.addWidget(QLabel("Y fx:", self))
        self.y_layout.addWidget(self.y_expression_input, 1)
        layout.addLayout(self.y_layout)

        expression_tooltip = (
            "Safe preprocessing expression using each original X/Y pair. "
            "Examples: 1/x, log10(y), y/x."
        )
        self.x_expression_input.setToolTip(expression_tooltip)
        self.y_expression_input.setToolTip(expression_tooltip)

        self.repository.transaction_committed.connect(
            self._repository_changed
        )
        self.x_data_input.currentIndexChanged.connect(
            self._emit_refs_changed
        )
        self.y_data_input.selectionChanged.connect(
            self._emit_refs_changed
        )
        self.update_data()

    def _repository_changed(self, changes: TableChangeSet) -> None:
        if self._disposed:
            return
        if (
            self.project_id is not None
            and self.project_id not in self.repository.projects
        ):
            self.dispose()
            return
        if (
            self.project_id is not None
            and changes.project_id == self.project_id
            and (changes.metadata_changed or changes.structure_changed)
        ):
            self.update_data()

    @staticmethod
    def _current_ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    @staticmethod
    def _set_combo_ref(combo: QComboBox, ref: ColumnRef | None) -> None:
        if ref is not None:
            for index in range(combo.count()):
                if combo.itemData(index, Qt.UserRole) == ref:
                    combo.setCurrentIndex(index)
                    return
        combo.setCurrentIndex(-1)

    def update_data(self) -> None:
        """Refresh available references while retaining stable selections."""

        current_x = self.get_x_ref()
        selected_y = set(self.get_y_refs())
        if self.project_id is None:
            x_refs: list[ColumnRef] = []
            y_refs: list[ColumnRef] = []
        else:
            x_refs = list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER, ColumnType.DATETIME},
                )
            )
            y_refs = list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER},
                )
            )

        x_blocker = QSignalBlocker(self.x_data_input)
        self.x_data_input.clear()
        for ref in x_refs:
            self.x_data_input.addItem(self.repository.ref_label(ref), ref)
        if current_x is not None and current_x in x_refs:
            self._set_combo_ref(self.x_data_input, current_x)
        elif x_refs:
            self.x_data_input.setCurrentIndex(0)
        del x_blocker

        if not self._initialized and not selected_y and y_refs:
            selected_x = self.get_x_ref()
            default_y = next(
                (ref for ref in y_refs if ref != selected_x),
                y_refs[0],
            )
            selected_y = {default_y}
        self.y_data_input.replace_items(
            [(self.repository.ref_label(ref), ref) for ref in y_refs],
            selected_y,
        )
        self._initialized = True
        self._emit_refs_changed()

    def clear_all(self) -> None:
        """Clear every Y selection."""

        self.y_data_input.clear_selection()

    def get_x_ref(self) -> ColumnRef | None:
        """Return the shared X reference."""

        return self._current_ref(self.x_data_input)

    def get_y_refs(self) -> tuple[ColumnRef, ...]:
        """Return checked Y references in repository/display order."""

        return self.y_data_input.checked_data()

    def selected_count(self) -> int:
        """Return the number of checked Y references."""

        return len(self.get_y_refs())

    def set_x_ref(self, ref: ColumnRef | None) -> None:
        """Set the shared X reference without recursively emitting signals."""

        blocker = QSignalBlocker(self.x_data_input)
        self._set_combo_ref(self.x_data_input, ref)
        del blocker

    def set_y_refs(self, refs) -> None:
        """Set checked Y references without recursively emitting signals."""

        self.y_data_input.set_checked_data(refs, emit=False)

    def set_refs(self, x_ref: ColumnRef | None, y_refs) -> None:
        """Synchronize the complete shared-X/multi-Y selection."""

        self.set_x_ref(x_ref)
        self.set_y_refs(y_refs)

    def preprocess_values(self) -> dict[str, str]:
        """Return the current unvalidated shared expressions."""

        return {
            "x_expression": self.x_expression_input.text(),
            "y_expression": self.y_expression_input.text(),
        }

    def get_preprocess_spec(self) -> DataPreprocessSpec:
        """Return the validated shared preprocessing specification."""

        return DataPreprocessSpec.from_dict(self.preprocess_values())

    def set_preprocess(
        self,
        preprocess: DataPreprocessSpec | dict | None,
    ) -> None:
        """Synchronize shared expressions without emitting edits."""

        spec = DataPreprocessSpec.from_dict(preprocess)
        x_blocker = QSignalBlocker(self.x_expression_input)
        y_blocker = QSignalBlocker(self.y_expression_input)
        self.x_expression_input.setText(spec.x_expression)
        self.y_expression_input.setText(spec.y_expression)
        del x_blocker, y_blocker

    def _update_selected_count(self) -> None:
        self.y_data_input._refresh_summary()

    def _emit_refs_changed(self, *_args) -> None:
        self._update_selected_count()
        self.refsChanged.emit(self.get_x_ref(), self.get_y_refs())

    def dispose(self) -> None:
        """Disconnect Repository callbacks and release owned resources."""

        if self._disposed:
            return
        self._disposed = True
        try:
            self.repository.transaction_committed.disconnect(
                self._repository_changed
            )
        except (RuntimeError, TypeError):
            pass

    def closeEvent(self, event):
        """Handle Qt close events and release Repository callbacks."""

        self.dispose()
        super().closeEvent(event)


class LineAppearanceInput(QFrame):
    """Unbound line appearance input for chart creation dialogs."""

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        colorselector=None,
        label: str = "",
        style: str = "-",
        linewidth: float = 2.0,
        show_label: bool = True,
        show_style: bool = True,
        show_linewidth: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_style_editor = LineStyleEditor(
            style,
            linewidth,
            show_size=show_linewidth,
            size_label="Line width:",
            parent=self,
        )
        self.style_input = self.line_style_editor.style_combo
        self.linewidth_input = self.line_style_editor.size_input
        self.line_style_editor.setVisible(show_style or show_linewidth)
        self.style_input.setVisible(show_style)
        for label_widget in self.line_style_editor.findChildren(QLabel):
            if label_widget.text() == "Line style:":
                label_widget.setVisible(show_style)
        layout.addWidget(self.line_style_editor)

        self.color_input = ColorChoiceWidget(
            colorselector=colorselector,
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        layout.addWidget(QLabel("Color:", self))
        layout.addWidget(self.color_input)

        self.label_widget = QWidget(self)
        label_layout = QVBoxLayout(self.label_widget)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.addWidget(QLabel("Label:", self.label_widget))
        self.label_input = QLineEdit(str(label), self.label_widget)
        label_layout.addWidget(self.label_input)
        self.label_widget.setVisible(show_label)
        layout.addWidget(self.label_widget)

    def style(self) -> str:
        """Return the selected style."""

        return self.line_style_editor.style()

    def linewidth(self) -> float:
        """Return the linewidth."""

        return self.line_style_editor.size()

    def color(self) -> str:
        """Return the selected color."""

        return self.color_input.color()

    def label(self) -> str:
        """Return the current display label."""

        return self.label_input.text()


class InAxesInput(QFrame):
    """Controller-free combined Zoom/Image inset creation input."""

    IMAGE_FILTER = (
        "Raster images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;"
        "All files (*)"
    )

    def __init__(
        self,
        *,
        color_library: ColorLibrary,
        defaults,
        parent=None,
    ):
        super().__init__(parent)
        self._image_data: dict[str, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Position in parent Axes (normalized):", self))
        bounds_row = QHBoxLayout()
        self.bounds_inputs = []
        for label, value in zip(
            ("X", "Y", "Width", "Height"),
            (0.60, 0.60, 0.35, 0.35),
        ):
            bounds_row.addWidget(QLabel(f"{label}:", self))
            editor = FocusAwareDoubleSpinBox(self)
            editor.setRange(-10.0, 10.0)
            editor.setDecimals(4)
            editor.setSingleStep(0.01)
            editor.setValue(value)
            bounds_row.addWidget(editor)
            self.bounds_inputs.append(editor)
        layout.addLayout(bounds_row)

        common_row = QHBoxLayout()
        self.visible_input = QCheckBox("Visible", self)
        self.visible_input.setChecked(True)
        self.frame_input = QCheckBox("Frame", self)
        self.frame_input.setChecked(True)
        self.zorder_input = FocusAwareDoubleSpinBox(self)
        self.zorder_input.setRange(-1e6, 1e6)
        self.zorder_input.setValue(5.0)
        common_row.addWidget(self.visible_input)
        common_row.addWidget(self.frame_input)
        common_row.addWidget(QLabel("Z order:", self))
        common_row.addWidget(self.zorder_input)
        layout.addLayout(common_row)

        frame_row = QHBoxLayout()
        self.facecolor_input = ColorChoiceWidget(
            defaults.facecolor,
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        self.edgecolor_input = ColorChoiceWidget(
            defaults.edgecolor,
            color_library=color_library,
            auto_record_recent=False,
            parent=self,
        )
        self.linewidth_input = FocusAwareDoubleSpinBox(self)
        self.linewidth_input.setRange(0.0, 1e6)
        self.linewidth_input.setDecimals(3)
        self.linewidth_input.setValue(float(defaults.linewidth))
        frame_row.addWidget(QLabel("Background:", self))
        frame_row.addWidget(self.facecolor_input)
        frame_row.addWidget(QLabel("Border:", self))
        frame_row.addWidget(self.edgecolor_input)
        frame_row.addWidget(QLabel("Width:", self))
        frame_row.addWidget(self.linewidth_input)
        layout.addLayout(frame_row)

        self.mode_tabs = QTabWidget(self)
        self.zoom_page = QWidget(self.mode_tabs)
        self.image_page = QWidget(self.mode_tabs)
        self.mode_tabs.addTab(self.zoom_page, "Zoom")
        self.mode_tabs.addTab(self.image_page, "Image")
        layout.addWidget(self.mode_tabs)
        self._build_zoom_page(defaults, color_library)
        self._build_image_page(defaults)

    @staticmethod
    def _range_row(parent, label: str, values=(0.0, 1.0)):
        row = QHBoxLayout()
        row.addWidget(QLabel(label, parent))
        inputs = []
        for value in values:
            editor = FocusAwareDoubleSpinBox(parent)
            editor.setRange(-1e300, 1e300)
            editor.setDecimals(6)
            editor.setSingleStep(0.1)
            editor.setValue(value)
            row.addWidget(editor)
            inputs.append(editor)
        return row, tuple(inputs)

    def _build_zoom_page(self, defaults, color_library) -> None:
        layout = QVBoxLayout(self.zoom_page)
        x_row, self.xlim_inputs = self._range_row(
            self.zoom_page,
            "X range:",
        )
        y_row, self.ylim_inputs = self._range_row(
            self.zoom_page,
            "Y range:",
        )
        layout.addLayout(x_row)
        layout.addLayout(y_row)
        flags = QHBoxLayout()
        self.ticks_input = QCheckBox("Show ticks", self.zoom_page)
        self.region_input = QCheckBox("Show region", self.zoom_page)
        self.connectors_input = QCheckBox("Show connectors", self.zoom_page)
        for widget in (
            self.ticks_input,
            self.region_input,
            self.connectors_input,
        ):
            widget.setChecked(True)
            flags.addWidget(widget)
        layout.addLayout(flags)
        indicator_row = QHBoxLayout()
        self.indicator_color_input = ColorChoiceWidget(
            defaults.indicator_color,
            color_library=color_library,
            auto_record_recent=False,
            parent=self.zoom_page,
        )
        self.indicator_style_input = LineStyleEditor(
            defaults.indicator_linestyle,
            defaults.indicator_linewidth,
            parent=self.zoom_page,
        )
        self.indicator_alpha_input = FocusAwareDoubleSpinBox(self.zoom_page)
        self.indicator_alpha_input.setRange(0.0, 1.0)
        self.indicator_alpha_input.setSingleStep(0.05)
        self.indicator_alpha_input.setValue(0.5)
        indicator_row.addWidget(QLabel("Indicator:", self.zoom_page))
        indicator_row.addWidget(self.indicator_color_input)
        indicator_row.addWidget(self.indicator_style_input, 1)
        indicator_row.addWidget(QLabel("Opacity:", self.zoom_page))
        indicator_row.addWidget(self.indicator_alpha_input)
        layout.addLayout(indicator_row)

    def _build_image_page(self, defaults) -> None:
        layout = QVBoxLayout(self.image_page)
        source_row = QHBoxLayout()
        self.image_path_input = QLineEdit(self.image_page)
        self.image_path_input.setReadOnly(True)
        self.image_button = QPushButton("Choose image…", self.image_page)
        self.image_button.clicked.connect(self.choose_image)
        source_row.addWidget(self.image_path_input, 1)
        source_row.addWidget(self.image_button)
        layout.addLayout(source_row)
        self.image_preview = QLabel("No image selected", self.image_page)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(120)
        layout.addWidget(self.image_preview)
        display_row = QHBoxLayout()
        self.opacity_input = FocusAwareDoubleSpinBox(self.image_page)
        self.opacity_input.setRange(0.0, 1.0)
        self.opacity_input.setSingleStep(0.05)
        self.opacity_input.setValue(1.0)
        self.fit_mode_input = QComboBox(self.image_page)
        self.fit_mode_input.addItems(("contain", "stretch"))
        self.interpolation_input = QComboBox(self.image_page)
        self.interpolation_input.addItems(("nearest", "bilinear", "bicubic"))
        self.interpolation_input.setCurrentText(defaults.image_interpolation)
        display_row.addWidget(QLabel("Opacity:", self.image_page))
        display_row.addWidget(self.opacity_input)
        display_row.addWidget(QLabel("Fit:", self.image_page))
        display_row.addWidget(self.fit_mode_input)
        display_row.addWidget(QLabel("Interpolation:", self.image_page))
        display_row.addWidget(self.interpolation_input)
        layout.addLayout(display_row)

    def choose_image(self) -> bool:
        """Choose and preflight an embedded raster image."""

        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose inset image",
            "",
            self.IMAGE_FILTER,
        )
        if not filename:
            return False
        try:
            data = embedded_image_data(filename)
            image = QImage.fromData(
                QByteArray.fromBase64(
                    data["payload_base64"].encode("ascii")
                )
            )
            if image.isNull():
                raise ValueError("The selected image could not be previewed.")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return False
        self._image_data = data
        self.image_path_input.setText(filename)
        pixmap = QPixmap.fromImage(image)
        self.image_preview.setPixmap(
            pixmap.scaled(
                320,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def bounds(self) -> tuple[float, float, float, float]:
        """Return normalized parent-Axes bounds."""

        return tuple(float(editor.value()) for editor in self.bounds_inputs)

    def spec(self) -> InAxesCreateSpec:
        """Build the selected mode's immutable creation specification."""

        common = {
            "bounds": self.bounds(),
            "facecolor": self.facecolor_input.color(),
            "edgecolor": self.edgecolor_input.color(),
            "linewidth": float(self.linewidth_input.value()),
            "visible": self.visible_input.isChecked(),
            "zorder": float(self.zorder_input.value()),
            "frameon": self.frame_input.isChecked(),
        }
        if self.mode_tabs.currentWidget() is self.zoom_page:
            return ZoomInAxesCreateSpec(
                xlim=tuple(editor.value() for editor in self.xlim_inputs),
                ylim=tuple(editor.value() for editor in self.ylim_inputs),
                ticks_visible=self.ticks_input.isChecked(),
                region_visible=self.region_input.isChecked(),
                connectors_visible=self.connectors_input.isChecked(),
                indicator_color=self.indicator_color_input.color(),
                indicator_linestyle=self.indicator_style_input.style(),
                indicator_linewidth=self.indicator_style_input.size(),
                indicator_alpha=float(self.indicator_alpha_input.value()),
                **common,
            )
        if self._image_data is None:
            raise ValueError("Choose a PNG, JPEG, BMP, or TIFF image first.")
        return ImageInAxesCreateSpec(
            filename=self._image_data["filename"],
            mime_type=self._image_data["mime_type"],
            payload_base64=self._image_data["payload_base64"],
            opacity=float(self.opacity_input.value()),
            fit_mode=self.fit_mode_input.currentText(),
            interpolation=self.interpolation_input.currentText(),
            **common,
        )


class InterpolationOptionsInput(QFrame):
    """Controller-free interpolation parameters with signal-safe syncing."""

    optionsChanged = Signal()

    def __init__(
        self,
        *,
        method: str | None = None,
        samples: int = DEFAULT_INTERPOLATION_SAMPLES,
        k: int = 3,
        lam: float | None = None,
        lam_auto: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.method_input = QComboBox(self)
        self.method_input.addItems(interpolate_dict.keys())
        layout.addWidget(QLabel("Interpolation Method:", self))
        layout.addWidget(self.method_input)

        samples_row = QHBoxLayout()
        samples_row.addWidget(QLabel("Samples:", self))
        self.samples_input = FocusAwareSpinBox(self)
        self.samples_input.setRange(
            MIN_INTERPOLATION_SAMPLES,
            MAX_INTERPOLATION_SAMPLES,
        )
        samples_row.addWidget(self.samples_input)
        layout.addLayout(samples_row)

        self.k_widget = QFrame(self)
        k_layout = QHBoxLayout(self.k_widget)
        k_layout.setContentsMargins(0, 0, 0, 0)
        k_layout.addWidget(QLabel("Order k:", self.k_widget))
        self.k_input = FocusAwareSpinBox(self.k_widget)
        self.k_input.setRange(1, 5)
        k_layout.addWidget(self.k_input)
        layout.addWidget(self.k_widget)

        self.lambda_widget = QFrame(self)
        lambda_layout = QVBoxLayout(self.lambda_widget)
        lambda_layout.setContentsMargins(0, 0, 0, 0)
        self.lambda_auto_input = QCheckBox(
            "Auto lambda",
            self.lambda_widget,
        )
        lambda_layout.addWidget(self.lambda_auto_input)
        lambda_row = QHBoxLayout()
        lambda_row.addWidget(QLabel("Lambda:", self.lambda_widget))
        self.lambda_value_input = FocusAwareDoubleSpinBox(self.lambda_widget)
        self.lambda_value_input.setRange(0.0, 1e12)
        self.lambda_value_input.setDecimals(6)
        self.lambda_value_input.setSingleStep(0.1)
        lambda_row.addWidget(self.lambda_value_input)
        lambda_layout.addLayout(lambda_row)
        layout.addWidget(self.lambda_widget)

        self.method_input.currentTextChanged.connect(self._method_changed)
        self.samples_input.valueChanged.connect(self.optionsChanged)
        self.k_input.valueChanged.connect(self.optionsChanged)
        self.lambda_auto_input.toggled.connect(self._lambda_auto_changed)
        self.lambda_value_input.valueChanged.connect(self.optionsChanged)
        self.set_options(
            method=method or next(iter(interpolate_dict)),
            samples=samples,
            k=k,
            lam=lam,
            lam_auto=lam_auto,
        )

    def _method_changed(self, *_args) -> None:
        self.update_option_visibility()
        self.optionsChanged.emit()

    def _lambda_auto_changed(self, checked: bool) -> None:
        self.lambda_value_input.setEnabled(not bool(checked))
        self.optionsChanged.emit()

    def update_option_visibility(self) -> None:
        """Update option visibility."""

        method = self.method()
        self.k_widget.setVisible(interpolation_uses_order(method))
        self.lambda_widget.setVisible(interpolation_uses_lambda(method))

    def method(self) -> str:
        """Return the method."""

        return self.method_input.currentText()

    def lambda_options(self) -> tuple[float | None, bool]:
        """Return the lambda options."""

        if not interpolation_uses_lambda(self.method()):
            return None, True
        if self.lambda_auto_input.isChecked():
            return None, True
        return float(self.lambda_value_input.value()), False

    def options(self) -> dict:
        """Return the options."""

        lam, lam_auto = self.lambda_options()
        return {
            "method": self.method(),
            "samples": int(self.samples_input.value()),
            "k": int(self.k_input.value()),
            "lam": lam,
            "lam_auto": lam_auto,
        }

    def set_options(
        self,
        *,
        method: str,
        samples: int,
        k: int,
        lam: float | None,
        lam_auto: bool,
    ) -> None:
        """Set options."""

        controls = (
            self.method_input,
            self.samples_input,
            self.k_input,
            self.lambda_auto_input,
            self.lambda_value_input,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.method_input.setCurrentText(str(method))
        self.samples_input.setValue(int(samples))
        self.k_input.setValue(int(k))
        self.lambda_auto_input.setChecked(bool(lam_auto))
        self.lambda_value_input.setValue(
            1.0 if lam is None else float(lam)
        )
        self.lambda_value_input.setEnabled(not bool(lam_auto))
        self.update_option_visibility()
        del blockers
