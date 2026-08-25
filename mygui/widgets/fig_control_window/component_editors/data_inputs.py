"""Table-backed data and scatter-mapping creation inputs."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)
from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    TableChangeSet,
    TableRepository,
)
from mygui.figuremodify.matplotlib_adapter import available_colormap_names
from mygui.figuremodify.components.property_values import DEFAULT_NORM

from .common import (
    FocusAwareDoubleSpinBox,
)

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
