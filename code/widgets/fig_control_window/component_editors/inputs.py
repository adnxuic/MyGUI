"""Provide Controller-free inputs shared with component creation dialogs."""

from __future__ import annotations

from Qt_core import *

from code.database import ColumnRef, ColumnType, TableChangeSet, TableRepository
from code.database.interpolate_func import (
    DEFAULT_INTERPOLATION_SAMPLES,
    MAX_INTERPOLATION_SAMPLES,
    MIN_INTERPOLATION_SAMPLES,
    interpolate_dict,
    interpolation_uses_lambda,
    interpolation_uses_order,
)
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)

from .common import LineStyleEditor


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
        self.x_layout.addWidget(QLabel("X Data:", self))
        self.x_layout.addWidget(self.x_data_input)
        self.y_layout.addWidget(QLabel("Y Data:", self))
        self.y_layout.addWidget(self.y_data_input)
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

    def refs_connect(self, x_callback, y_callback) -> None:
        """Refresh selectors after their data-reference source changes."""

        self.x_data_input.currentIndexChanged.connect(x_callback)
        self.y_data_input.currentIndexChanged.connect(y_callback)

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
        self.samples_input = QSpinBox(self)
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
        self.k_input = QSpinBox(self.k_widget)
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
        self.lambda_value_input = QDoubleSpinBox(self.lambda_widget)
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
