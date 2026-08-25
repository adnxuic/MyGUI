"""Present a typed table document through Qt's model/view widgets."""

from __future__ import annotations



from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QInputDialog,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.database import (
    ColumnRef,
    TableChangeSet,
    TableMutationCommand,
    TableRepository,
    validate_component_name,
)
from .table_model import (
    DependencyHandler,
    TableModel,
    TypedItemDelegate,
    _same_value,
)
from .table_view import SheetTabWidget, TableView

class PySubTable(QFrame):
    """Provide the py sub table Qt widget."""

    def __init__(self, repository: TableRepository, project_id: str,
                 dependency_handler: DependencyHandler | None = None):
        super().__init__()
        self.repository = repository
        self.project_id = project_id
        self.dependency_handler = dependency_handler
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("table_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.tabWidget = SheetTabWidget(self)
        self.tabWidget.setTabPosition(QTabWidget.South)
        self.tabWidget.tabBarClicked.connect(self._plus_clicked)
        self._views: dict[str, TableView] = {}
        self._build_tabs()
        self._build_toolbar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.tabWidget)

    @property
    def project(self):
        """Return the project."""

        return self.repository.project(self.project_id)

    def _build_tabs(self):
        self._dispose_tabs()
        self._views.clear()
        for sheet in self.project.sheets.values():
            view = TableView(self.repository, self.project_id, sheet.id, self.dependency_handler)
            self._views[sheet.id] = view
            self.tabWidget.addTab(view, sheet.name)
        plus = QWidget()
        self.tabWidget.addTab(plus, "+")

    def sync_sheets_from_repository(self) -> None:
        """Rebuild the sheet projection from authoritative Repository state."""

        self._build_tabs()

    def _dispose_tabs(self):
        while self.tabWidget.count():
            widget = self.tabWidget.widget(0)
            if isinstance(widget, TableView):
                widget.dispose()
            self.tabWidget.removeTab(0)
            if widget is not None:
                widget.deleteLater()

    def dispose(self) -> None:
        """Detach repository listeners before the project is removed."""

        self._dispose_tabs()
        self._views.clear()

    def _build_toolbar(self):
        groups = (
            (("Undo", self.undo), ("Redo", self.redo)),
            (
                ("Rename Sheet", self.rename_current_sheet),
                ("Delete Sheet", self.delete_current_sheet),
            ),
            (
                ("Add Row", lambda: self.current_view().insert_row()),
                ("Delete Row", lambda: self.current_view().delete_row()),
                ("Move Row Up", lambda: self.current_view().move_row(-1)),
                ("Move Row Down", lambda: self.current_view().move_row(1)),
            ),
            (
                ("Add Column", lambda: self.current_view().add_column()),
                ("Delete Column", lambda: self.current_view().delete_column()),
            ),
        )
        for group_index, actions in enumerate(groups):
            if group_index:
                self.toolbar.addSeparator()
            for text, callback in actions:
                action = self.toolbar.addAction(text)
                action.setToolTip(text)
                action.setStatusTip(text)
                action.triggered.connect(callback)

    def current_view(self) -> TableView:
        """Return the current view."""

        widget = self.tabWidget.currentWidget()
        if not isinstance(widget, TableView):
            if not self._views:
                raise RuntimeError("Project has no sheets.")
            return next(iter(self._views.values()))
        return widget

    def get_table(self, index: int) -> TableView:
        """Return table."""

        widget = self.tabWidget.widget(index)
        if not isinstance(widget, TableView):
            raise IndexError("Sheet index does not refer to a table.")
        return widget

    def undo(self):
        """Reverse this table mutation."""

        self.repository.undo_stack(self.project_id).undo()

    def redo(self):
        """Reapply this table mutation."""

        self.repository.undo_stack(self.project_id).redo()

    def current_sheet_index(self) -> int:
        """Return the current sheet index."""

        index = self.tabWidget.currentIndex()
        if 0 <= index < self.tabWidget.count() - 1:
            return index
        return 0

    def rename_current_sheet(self):
        """Rename current sheet."""

        self.rename_sheet(self.current_sheet_index())

    def delete_current_sheet(self):
        """Delete current sheet."""

        self.delete_sheet(self.current_sheet_index())

    def _plus_clicked(self, index: int):
        if index == self.tabWidget.count() - 1:
            self.add_new_sheet()

    def add_new_sheet(self, sheet_name: str | None = None, sheet=None) -> TableView:
        """Add new sheet."""

        previous_index = self.tabWidget.currentIndex()
        view = None
        added_sheet = None
        changes = TableChangeSet(
            self.project_id,
            metadata_changed=True,
            structure_changed=True,
            reason="add-sheet",
        )
        try:
            with self.repository.mutate(changes):
                added_sheet = (
                    self.project.add_sheet(sheet_name)
                    if sheet is None
                    else self.project.add_sheet(sheet=sheet)
                )
                view = TableView(
                    self.repository,
                    self.project_id,
                    added_sheet.id,
                    self.dependency_handler,
                )
                index = self.tabWidget.count() - 1
                inserted = self.tabWidget.insertTab(
                    index,
                    view,
                    added_sheet.name,
                )
                if inserted < 0:
                    raise RuntimeError("Could not add the sheet tab.")
                self._views[added_sheet.id] = view
                self.tabWidget.setCurrentIndex(inserted)
        except Exception:
            if added_sheet is not None:
                self._views.pop(added_sheet.id, None)
            if view is not None:
                index = self.tabWidget.indexOf(view)
                if index >= 0:
                    self.tabWidget.removeTab(index)
                view.dispose()
                view.setParent(None)
                view.deleteLater()
            if self.tabWidget.count():
                self.tabWidget.setCurrentIndex(
                    max(0, min(previous_index, self.tabWidget.count() - 1))
                )
            raise
        return view

    def rename_sheet(self, index: int):
        """Rename sheet."""

        if index < 0 or index >= self.tabWidget.count() - 1:
            return
        view = self.get_table(index)
        sheet = self.repository.sheet(self.project_id, view.sheet_id)
        name, ok = QInputDialog.getText(self, "Rename Sheet", "Sheet name:", text=sheet.name)
        if not ok:
            return
        try:
            cleaned = validate_component_name(name, "Sheet name")
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return
        if any(other.id != sheet.id and other.name.casefold() == cleaned.casefold()
               for other in self.project.sheets.values()):
            status_messages.show_error(f"Sheet name already exists: {cleaned}")
            return
        old_name = sheet.name
        if old_name == cleaned:
            return

        def set_name(value: str):
            sheet.name = value
            for tab_index in range(self.tabWidget.count() - 1):
                tab_view = self.tabWidget.widget(tab_index)
                if isinstance(tab_view, TableView) and tab_view.sheet_id == sheet.id:
                    self.tabWidget.setTabText(tab_index, value)
                    break

        self.repository.push(self.project_id, TableMutationCommand(
            "Rename sheet", self.repository, self.project_id,
            lambda: set_name(cleaned), lambda: set_name(old_name),
            TableChangeSet(self.project_id, metadata_changed=True, reason="rename-sheet"),
        ))
        status_messages.show_success(f"Sheet renamed to {cleaned}.")

    def delete_sheet(self, index: int):
        """Delete sheet."""

        if index < 0 or index >= self.tabWidget.count() - 1:
            return
        if len(self.project.sheets) <= 1:
            status_messages.show_warning("A project must contain at least one sheet.")
            return
        view = self.get_table(index)
        sheet = self.repository.sheet(self.project_id, view.sheet_id)
        refs = [ColumnRef(self.project_id, sheet.id, column.id) for column in sheet.columns]
        dependency_actions = self.dependency_handler(refs, "delete-sheet") if self.dependency_handler else None
        if dependency_actions is False:
            return
        if dependency_actions is None:
            dependency_actions = (lambda: None, lambda: None)
        dependency_redo, dependency_undo = dependency_actions
        original_index = list(self.project.sheets).index(sheet.id)

        def select_nearest_sheet(preferred: int):
            if self.project.sheets:
                self.tabWidget.setCurrentIndex(min(preferred, len(self.project.sheets) - 1))

        def redo():
            if dependency_redo() is False:
                return False
            self.project.sheets.pop(sheet.id, None)
            self._build_tabs()
            select_nearest_sheet(original_index)
            return True

        def undo():
            items = list(self.project.sheets.items())
            items.insert(original_index, (sheet.id, sheet))
            self.project.sheets.clear()
            self.project.sheets.update(items)
            self._build_tabs()
            self.tabWidget.setCurrentIndex(original_index)
            if dependency_undo() is False:
                return False
            return True

        committed = self.repository.push(self.project_id, TableMutationCommand(
            "Delete sheet", self.repository, self.project_id, redo, undo,
            TableChangeSet(
                self.project_id, set(refs), metadata_changed=True,
                structure_changed=True, reason="delete-sheet",
            ),
            rollback_on_error=True,
        ))
        if committed:
            status_messages.show_success(f"Sheet deleted: {sheet.name}.")

__all__ = [
    "DependencyHandler",
    "PySubTable",
    "SheetTabWidget",
    "TableModel",
    "TableView",
    "TypedItemDelegate",
    "_same_value",
]
