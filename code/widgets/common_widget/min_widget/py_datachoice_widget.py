"""Select project table columns for chart data references."""

from __future__ import annotations

from Qt_core import *

from code.database import ColumnRef, ColumnType, TableChangeSet, TableRepository


class PyDataChoiceWidget(QFrame):
    """Provide the py data choice widget Qt widget."""

    def __init__(self, repository: TableRepository, project_id: str):
        super().__init__()
        self.repository = repository
        self.project_id = project_id

        layout = QVBoxLayout(self)
        self.x_layout = QHBoxLayout()
        self.y_layout = QHBoxLayout()
        self.x_data_input = QComboBox(self)
        self.y_data_input = QComboBox(self)
        self.x_layout.addWidget(QLabel("X Data:"))
        self.x_layout.addWidget(self.x_data_input)
        self.y_layout.addWidget(QLabel("Y Data:"))
        self.y_layout.addWidget(self.y_data_input)
        layout.addLayout(self.x_layout)
        layout.addLayout(self.y_layout)

        self.repository.transaction_committed.connect(self._repository_changed)
        self.update_data()

    def _repository_changed(self, changes: TableChangeSet):
        if changes.project_id == self.project_id and (changes.metadata_changed or changes.structure_changed):
            self.update_data()

    @staticmethod
    def _current_ref(combo: QComboBox) -> ColumnRef | None:
        value = combo.currentData(Qt.UserRole)
        return value if isinstance(value, ColumnRef) else None

    def update_data(self):
        """Update data."""

        current_x = self.get_x_ref()
        current_y = self.get_y_ref()
        numeric = {ColumnType.NUMBER, ColumnType.DATETIME}
        x_refs = list(self.repository.iter_column_refs(self.project_id, numeric))
        y_refs = list(self.repository.iter_column_refs(self.project_id, {ColumnType.NUMBER}))
        self._populate(self.x_data_input, x_refs, current_x)
        self._populate(self.y_data_input, y_refs, current_y)

    def _populate(self, combo: QComboBox, refs: list[ColumnRef], current: ColumnRef | None):
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
    def _set_ref(combo: QComboBox, ref: ColumnRef | None):
        if ref is None:
            combo.setCurrentIndex(-1)
            return
        for index in range(combo.count()):
            if combo.itemData(index, Qt.UserRole) == ref:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(-1)

    def set_x_ref(self, ref: ColumnRef | None):
        """Set x ref."""

        self._set_ref(self.x_data_input, ref)

    def set_y_ref(self, ref: ColumnRef | None):
        """Set y ref."""

        self._set_ref(self.y_data_input, ref)

    def refs_connect(self, x_callback, y_callback):
        """Refresh selectors after their data-reference source changes."""

        self.x_data_input.currentIndexChanged.connect(x_callback)
        self.y_data_input.currentIndexChanged.connect(y_callback)
