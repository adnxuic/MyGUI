"""Host the interchangeable Table and Components explorer pages."""

from __future__ import annotations

from enum import Enum

from Qt_core import *


class ExplorerMode(str, Enum):
    """Identify the selected page in the left Explorer."""

    TABLE = "table"
    COMPONENTS = "components"


class LeftExplorerHost(QFrame):
    """Own the Table/Components page stack without visibility policy."""

    def __init__(self, table, component_tree, parent=None):
        super().__init__(parent)
        self.setObjectName("left_explorer_host")
        self.table = table
        self.component_tree = component_tree
        self._mode = ExplorerMode.TABLE

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("left_explorer_stack")
        self.stack.addWidget(table)
        self.stack.addWidget(component_tree)
        self.stack.setCurrentWidget(table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack)

    @property
    def mode(self) -> ExplorerMode:
        """Return the selected Explorer page."""

        return self._mode

    def set_mode(self, mode: ExplorerMode | str) -> None:
        """Select the requested Explorer page."""

        mode = ExplorerMode(mode)
        self._mode = mode
        self.stack.setCurrentWidget(
            self.table
            if mode is ExplorerMode.TABLE
            else self.component_tree
        )
