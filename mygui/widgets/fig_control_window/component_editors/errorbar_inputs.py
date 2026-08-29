"""Controller-free Error Bar data and error-spec creation inputs."""

from __future__ import annotations

from contextlib import ExitStack

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
)
from mygui.database import ColumnRef, ColumnType, TableChangeSet, TableRepository
from mygui.figuremodify.components.property_values import DEFAULT_ERROR_SPEC

from .data_inputs import DataReferenceInput


class ErrorSpecInput(QFrame):
    """Closed None/Constant/Symmetric/Asymmetric error-magnitude input."""

    specChanged = Signal()

    _MODE_NONE = "none"
    _MODE_CONSTANT = "constant"
    _MODE_SYMMETRIC = "symmetric_ref"
    _MODE_ASYMMETRIC = "asymmetric_ref"

    def __init__(
        self,
        repository: TableRepository,
        project_id: str | None,
        *,
        label: str,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.project_id = project_id
        self._disposed = False
        self._label = str(label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel(f"{label}:", self))
        self.mode_input = QComboBox(self)
        self.mode_input.addItem("None", self._MODE_NONE)
        self.mode_input.addItem("Constant", self._MODE_CONSTANT)
        self.mode_input.addItem("Symmetric Column", self._MODE_SYMMETRIC)
        self.mode_input.addItem("Asymmetric Columns", self._MODE_ASYMMETRIC)
        mode_layout.addWidget(self.mode_input)
        mode_layout.addStretch(1)
        layout.addLayout(mode_layout)

        self.page_stack = QStackedWidget(self)
        self.none_page = QFrame(self.page_stack)

        self.constant_page = QFrame(self.page_stack)
        constant_layout = QHBoxLayout(self.constant_page)
        constant_layout.setContentsMargins(0, 0, 0, 0)
        constant_layout.addWidget(QLabel("Minus:", self.constant_page))
        self.minus_input = QDoubleSpinBox(self.constant_page)
        self.minus_input.setDecimals(4)
        self.minus_input.setMinimum(0.0)
        self.minus_input.setMaximum(1e12)
        constant_layout.addWidget(self.minus_input)
        constant_layout.addWidget(QLabel("Plus:", self.constant_page))
        self.plus_input = QDoubleSpinBox(self.constant_page)
        self.plus_input.setDecimals(4)
        self.plus_input.setMinimum(0.0)
        self.plus_input.setMaximum(1e12)
        constant_layout.addWidget(self.plus_input)

        self.symmetric_page = QFrame(self.page_stack)
        symmetric_layout = QHBoxLayout(self.symmetric_page)
        symmetric_layout.setContentsMargins(0, 0, 0, 0)
        symmetric_layout.addWidget(QLabel("Column:", self.symmetric_page))
        self.symmetric_input = QComboBox(self.symmetric_page)
        symmetric_layout.addWidget(self.symmetric_input)

        self.asymmetric_page = QFrame(self.page_stack)
        asymmetric_layout = QHBoxLayout(self.asymmetric_page)
        asymmetric_layout.setContentsMargins(0, 0, 0, 0)
        asymmetric_layout.addWidget(QLabel("Minus Column:", self.asymmetric_page))
        self.asymmetric_minus_input = QComboBox(self.asymmetric_page)
        asymmetric_layout.addWidget(self.asymmetric_minus_input)
        asymmetric_layout.addWidget(QLabel("Plus Column:", self.asymmetric_page))
        self.asymmetric_plus_input = QComboBox(self.asymmetric_page)
        asymmetric_layout.addWidget(self.asymmetric_plus_input)
        for page in (
            self.none_page,
            self.constant_page,
            self.symmetric_page,
            self.asymmetric_page,
        ):
            self.page_stack.addWidget(page)
        layout.addWidget(self.page_stack)

        self.repository.transaction_committed.connect(
            self._repository_changed
        )
        self.mode_input.currentIndexChanged.connect(self._mode_changed)
        self.minus_input.valueChanged.connect(self._value_changed)
        self.plus_input.valueChanged.connect(self._value_changed)
        self.symmetric_input.currentIndexChanged.connect(self._value_changed)
        self.asymmetric_minus_input.currentIndexChanged.connect(
            self._value_changed
        )
        self.asymmetric_plus_input.currentIndexChanged.connect(
            self._value_changed
        )
        self._refresh_columns()
        self.set_value(dict(DEFAULT_ERROR_SPEC))

    # ------------------------------------------------------------------
    # Value contract
    # ------------------------------------------------------------------
    def spec_error(self) -> str | None:
        """Return why the current draft is not submittable, or ``None``.

        A mode switch never downgrades to ``none``: an incomplete Symmetric
        or Asymmetric draft stays an explicit, visible draft that blocks
        Apply until the user completes or abandons it.
        """

        mode = self.mode_input.currentData()
        if mode == self._MODE_SYMMETRIC:
            if self._current_ref(self.symmetric_input) is None:
                return f"{self._label}: select one numeric error column."
        elif mode == self._MODE_ASYMMETRIC:
            missing = [
                name
                for name, combo in (
                    ("minus", self.asymmetric_minus_input),
                    ("plus", self.asymmetric_plus_input),
                )
                if self._current_ref(combo) is None
            ]
            if missing:
                return (
                    f"{self._label}: select the "
                    f"{' and '.join(missing)} error column(s)."
                )
        return None

    def value(self) -> dict:
        """Return the closed normalized spec, raising on incomplete drafts."""

        error = self.spec_error()
        if error is not None:
            raise ValueError(error)
        mode = self.mode_input.currentData()
        if mode == self._MODE_CONSTANT:
            return {
                "kind": "constant",
                "minus": float(self.minus_input.value()),
                "plus": float(self.plus_input.value()),
            }
        if mode == self._MODE_SYMMETRIC:
            ref = self._current_ref(self.symmetric_input)
            return {"kind": "symmetric_ref", "ref": ref.to_dict()}
        if mode == self._MODE_ASYMMETRIC:
            minus = self._current_ref(self.asymmetric_minus_input)
            plus = self._current_ref(self.asymmetric_plus_input)
            return {
                "kind": "asymmetric_ref",
                "minus_ref": minus.to_dict(),
                "plus_ref": plus.to_dict(),
            }
        return dict(DEFAULT_ERROR_SPEC)

    def set_value(self, spec: dict | None, *, emit: bool = False) -> None:
        """Synchronize controls from one spec without emitting edits."""

        from mygui.figuremodify.components.property_values import (
            normalize_error_spec,
        )

        normalized = normalize_error_spec(
            spec if spec is not None else dict(DEFAULT_ERROR_SPEC)
        )
        kind = normalized["kind"]
        mode_index = {
            self._MODE_NONE: 0,
            self._MODE_CONSTANT: 1,
            self._MODE_SYMMETRIC: 2,
            self._MODE_ASYMMETRIC: 3,
        }[kind]
        # Programmatic synchronization must never emit user-edit signals;
        # otherwise one Controller commit re-enters the section and submits
        # again with stale control values.
        controls = (
            self.mode_input,
            self.minus_input,
            self.plus_input,
            self.symmetric_input,
            self.asymmetric_minus_input,
            self.asymmetric_plus_input,
        )
        with ExitStack() as stack:
            for control in controls:
                stack.enter_context(QSignalBlocker(control))
            self.mode_input.setCurrentIndex(mode_index)
            self._sync_mode_pages()
            if kind == "constant":
                self.minus_input.setValue(float(normalized["minus"]))
                self.plus_input.setValue(float(normalized["plus"]))
            elif kind == "symmetric_ref":
                self._set_ref(
                    self.symmetric_input,
                    ColumnRef.from_dict(normalized["ref"]),
                )
            elif kind == "asymmetric_ref":
                self._set_ref(
                    self.asymmetric_minus_input,
                    ColumnRef.from_dict(normalized["minus_ref"]),
                )
                self._set_ref(
                    self.asymmetric_plus_input,
                    ColumnRef.from_dict(normalized["plus_ref"]),
                )
        if emit:
            self.specChanged.emit()

    def connect_changed(self, callback) -> None:
        """Invoke the callback after any user-driven spec edit."""

        self.specChanged.connect(callback)

    def dispose(self) -> None:
        """Disconnect repository callbacks owned by this input."""

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
        """Dispose on close."""

        self.dispose()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _current_ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    @staticmethod
    def _set_ref(combo: QComboBox, ref: ColumnRef | None) -> None:
        if ref is not None:
            for index in range(combo.count()):
                if combo.itemData(index, Qt.UserRole) == ref:
                    combo.setCurrentIndex(index)
                    return
        combo.setCurrentIndex(-1)

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
            self._refresh_columns()

    def _refresh_columns(self) -> None:
        if self.project_id is None:
            refs: list[ColumnRef] = []
        else:
            refs = list(
                self.repository.iter_column_refs(
                    self.project_id,
                    {ColumnType.NUMBER},
                )
            )
        for combo in (
            self.symmetric_input,
            self.asymmetric_minus_input,
            self.asymmetric_plus_input,
        ):
            blocker = QSignalBlocker(combo)
            # Preserve the raw draft reference across structure refreshes;
            # a deleted reference leaves the combo empty so the draft stays
            # visibly incomplete instead of silently switching columns.
            selected = self._current_ref(combo)
            combo.clear()
            for ref in refs:
                combo.addItem(self.repository.ref_label(ref), ref)
            self._set_ref(combo, selected)
            del blocker

    def _sync_mode_pages(self) -> None:
        mode = self.mode_input.currentData()
        page = {
            self._MODE_NONE: self.none_page,
            self._MODE_CONSTANT: self.constant_page,
            self._MODE_SYMMETRIC: self.symmetric_page,
            self._MODE_ASYMMETRIC: self.asymmetric_page,
        }.get(mode, self.none_page)
        self.page_stack.setCurrentWidget(page)

    def _mode_changed(self, *_args) -> None:
        self._sync_mode_pages()
        self.specChanged.emit()

    def _value_changed(self, *_args) -> None:
        self.specChanged.emit()


class ErrorBarDataInput(QFrame):
    """Controller-free composite X/Y/error-spec creation input."""

    specChanged = Signal()

    def __init__(
        self,
        repository: TableRepository,
        project_id: str | None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.data_choice_widget = DataReferenceInput(
            repository,
            project_id,
            parent=self,
        )
        self.x_error_input = ErrorSpecInput(
            repository,
            project_id,
            label="X Error",
            parent=self,
        )
        self.y_error_input = ErrorSpecInput(
            repository,
            project_id,
            label="Y Error",
            parent=self,
        )
        layout.addWidget(self.data_choice_widget)
        layout.addWidget(self.x_error_input)
        layout.addWidget(self.y_error_input)
        self.x_error_input.connect_changed(self._emit_spec_changed)
        self.y_error_input.connect_changed(self._emit_spec_changed)

    @property
    def x_data_input(self):
        """Expose the X column combo for tests and dialog focus."""

        return self.data_choice_widget.x_data_input

    @property
    def y_data_input(self):
        """Expose the Y column combo for tests and dialog focus."""

        return self.data_choice_widget.y_data_input

    def get_x_ref(self):
        """Return the selected X reference."""

        return self.data_choice_widget.get_x_ref()

    def get_y_ref(self):
        """Return the selected Y reference."""

        return self.data_choice_widget.get_y_ref()

    def spec_error(self) -> str | None:
        """Return why the composite draft is incomplete, or ``None``."""

        if self.get_x_ref() is None or self.get_y_ref() is None:
            return "Select X Data and Y Data."
        return (
            self.x_error_input.spec_error()
            or self.y_error_input.spec_error()
        )

    def xerr_spec(self) -> dict:
        """Return the normalized X error spec, raising on an incomplete draft."""

        return self.x_error_input.value()

    def yerr_spec(self) -> dict:
        """Return the normalized Y error spec, raising on an incomplete draft."""

        return self.y_error_input.value()

    def preprocess_values(self) -> dict[str, str]:
        """Return the unvalidated preprocessing expressions."""

        return self.data_choice_widget.preprocess_values()

    def get_preprocess_spec(self):
        """Return the validated preprocessing specification."""

        return self.data_choice_widget.get_preprocess_spec()

    def set_refs(self, x_ref, y_ref) -> None:
        """Synchronize the X/Y selectors."""

        self.data_choice_widget.set_refs(x_ref, y_ref)

    def set_error_specs(self, xerr: dict | None, yerr: dict | None) -> None:
        """Synchronize both error-spec controls."""

        self.x_error_input.set_value(xerr)
        self.y_error_input.set_value(yerr)

    def set_preprocess(self, preprocess) -> None:
        """Synchronize the preprocessing expressions."""

        self.data_choice_widget.set_preprocess(preprocess)

    def refs_connect(self, x_callback, y_callback) -> None:
        """Forward the data reference callbacks."""

        self.data_choice_widget.refs_connect(x_callback, y_callback)

    def expressions_connect(self, x_callback, y_callback) -> None:
        """Forward the preprocessing callbacks."""

        self.data_choice_widget.expressions_connect(x_callback, y_callback)

    def dispose(self) -> None:
        """Dispose owned repository-bound inputs."""

        self.data_choice_widget.dispose()
        self.x_error_input.dispose()
        self.y_error_input.dispose()

    def _emit_spec_changed(self, *_args) -> None:
        self.specChanged.emit()
