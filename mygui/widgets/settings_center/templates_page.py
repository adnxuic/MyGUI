"""Settings → Templates immediate-management page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mygui.application_settings.keys import PAGE_TEMPLATES
from mygui.template_library import TEMPLATE_FILE_SUFFIX, template_content_summary
from mygui.template_library.models import TemplateDataContract
from mygui.widgets.settings_center.pages import standard_page_spec
from mygui.widgets.ui_components import UiRole, UiVariant, apply_ui_style, ask_confirmation

TEMPLATES_PAGE_DESCRIPTION = (
    "Template files are written immediately under the repository-root template "
    "directory. They are not Settings preferences, and Cancel does not revert them."
)

TEMPLATES_EMPTY_DESCRIPTION = (
    "Extract a template from an open Figure via Edit → Change to Template…, "
    "or use Import… on the left to add an external template file."
)

TEMPLATES_MISS_DESCRIPTION = (
    "No template matches the search query. Clear the search box or try a "
    "different name, note, or required header."
)


def _format_timestamp(ts: str) -> str:
    """Format an ISO-8601 timestamp cleanly for display."""
    if not ts:
        return ""
    clean = ts.replace("T", " ").rstrip("Z")
    if "." in clean:
        clean = clean.split(".")[0]
    return clean[:16] if len(clean) >= 16 else clean


def _format_data_contract(contract: TemplateDataContract | None) -> str:
    """Format a TemplateDataContract into structured, readable text."""
    if not contract or not contract.sheets:
        return "No data-backed columns"
    sheet_blocks: list[str] = []
    for sheet in contract.sheets:
        if not sheet.columns:
            sheet_blocks.append(f"• Sheet: {sheet.name} (no columns)")
            continue
        cols_text = "\n".join(f"    - {col.name}  ({col.type.value})" for col in sheet.columns)
        sheet_blocks.append(f"• Sheet: {sheet.name}\n{cols_text}")
    return "\n\n".join(sheet_blocks)


class TemplatesSettingsPage(QWidget):
    """Manage external template files without joining the Settings draft."""

    PAGE_ID = PAGE_TEMPLATES

    def __init__(self, library, workflow, host, parent=None):
        super().__init__(parent)
        self.library = library
        self.workflow = workflow
        self.host = host
        self._entries = []

        # Hidden QLineEdit for backwards compatibility with tests / API
        self.name = QLineEdit(self)
        self.name.setVisible(False)

        left_pane = self._build_left_pane()
        right_pane = self._build_right_pane()

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("templates_splitter")
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(left_pane)
        splitter.addWidget(right_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([240, 720])
        self._splitter = splitter

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(splitter, 1)

        self.search.textChanged.connect(self._filter)
        self.list.currentRowChanged.connect(self._show_current)
        self.notes.textChanged.connect(self._on_notes_changed)

        self.apply_button.clicked.connect(self._apply)
        self.rename_button.clicked.connect(self._rename)
        self.notes_button.clicked.connect(self._save_notes)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.update_button.clicked.connect(self._update)
        self.import_button.clicked.connect(self._import)
        self.empty_import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.delete_button.clicked.connect(self._delete)
        self.folder_button.clicked.connect(self._open_folder)
        self.refresh_button.clicked.connect(self._manual_refresh)

        if self.host is not None and hasattr(self.host, "bind_draft_reloaded"):
            self.host.bind_draft_reloaded(
                lambda *_args: self.refresh(
                    select_id=(self._template().metadata.id if self._template() else None)
                )
            )

        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt
        super().showEvent(event)
        selected_id = None
        template = self._template()
        if template is not None:
            selected_id = template.metadata.id
        self.refresh(select_id=selected_id)

    def _manual_refresh(self) -> None:
        selected_id = None
        template = self._template()
        if template is not None:
            selected_id = template.metadata.id
        self.refresh(select_id=selected_id)
        if self.host is not None and hasattr(self.host, "emit_message"):
            self.host.emit_message("Template library refreshed", "info")

    def _build_left_pane(self) -> QWidget:
        left = QWidget(self)
        left.setObjectName("templates_left_pane")
        left.setMinimumWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(6)

        self.search = QLineEdit(left)
        self.search.setObjectName("templates_search")
        self.search.setPlaceholderText("Search templates...")
        self.search.setClearButtonEnabled(True)

        self.list = QListWidget(left)
        self.list.setObjectName("settings_template_list")
        apply_ui_style(self.list, role=UiRole.TREE)

        self.import_button = QPushButton("Import…", left)
        self.import_button.setObjectName("template_import_button")
        self.import_button.setAutoDefault(False)
        self.folder_button = QPushButton("Open Folder", left)
        self.folder_button.setObjectName("template_folder_button")
        self.folder_button.setAutoDefault(False)
        self.refresh_button = QPushButton("Refresh", left)
        self.refresh_button.setObjectName("template_refresh_button")
        self.refresh_button.setAutoDefault(False)
        for button in (self.import_button, self.folder_button, self.refresh_button):
            button.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
        apply_ui_style(self.search, role=UiRole.INPUT)

        buttons = QWidget(left)
        buttons.setObjectName("templates_library_buttons")
        grid = QGridLayout(buttons)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        grid.addWidget(self.import_button, 0, 0)
        grid.addWidget(self.folder_button, 0, 1)
        grid.addWidget(self.refresh_button, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        left_layout.addWidget(self.search)
        left_layout.addWidget(self.list, 1)
        left_layout.addWidget(buttons)
        return left

    def _build_right_pane(self) -> QWidget:
        right = QWidget(self)
        right.setObjectName("templates_right_pane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(12)

        self.header_card = self._build_header_card()
        right_layout.addWidget(self.header_card)

        self.empty_frame = self._build_empty_box()
        self.miss_frame = self._build_miss_box()
        self.error_frame = self._build_error_box()
        self.detail_page = self._build_detail_page()

        self.detail_stack = QStackedWidget(right)
        self.detail_stack.setObjectName("templates_detail_stack")
        self.detail_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.detail_stack.addWidget(self.empty_frame)
        self.detail_stack.addWidget(self.miss_frame)
        self.detail_stack.addWidget(self.error_frame)
        self.detail_stack.addWidget(self.detail_page)
        right_layout.addWidget(self.detail_stack, 1)
        return right

    def _build_header_card(self) -> QFrame:
        header_card = QFrame(self)
        header_card.setObjectName("template_header_card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.name_title = QLabel(header_card)
        self.name_title.setObjectName("template_detail_title")
        self.name_title.setWordWrap(True)
        title_font = QFont(self.name_title.font())
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.name_title.setFont(title_font)

        self.apply_button = QPushButton("Apply Template…", header_card)
        self.apply_button.setObjectName("template_apply_button")
        self.apply_button.setAutoDefault(False)
        self.apply_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        apply_ui_style(
            self.apply_button,
            role=UiRole.BUTTON,
            variant=UiVariant.PRIMARY,
        )

        title_row.addWidget(self.name_title, 1)
        title_row.addWidget(self.apply_button, 0, Qt.AlignTop)
        header_layout.addLayout(title_row)

        self.timestamps = QLabel(header_card)
        self.timestamps.setObjectName("template_detail_timestamps")
        self.timestamps.setWordWrap(True)
        header_layout.addWidget(self.timestamps)

        primary = QHBoxLayout()
        primary.setContentsMargins(0, 4, 0, 0)
        primary.setSpacing(6)

        self.update_button = QPushButton("Update from Figure…", header_card)
        self.update_button.setObjectName("template_update_button")
        self.update_button.setAutoDefault(False)

        self.rename_button = QPushButton("Rename…", header_card)
        self.rename_button.setObjectName("template_rename_button")
        self.rename_button.setAutoDefault(False)

        primary.addWidget(self.update_button)
        primary.addWidget(self.rename_button)
        primary.addStretch(1)
        header_layout.addLayout(primary)

        secondary = QHBoxLayout()
        secondary.setContentsMargins(0, 0, 0, 0)
        secondary.setSpacing(6)

        self.duplicate_button = QPushButton("Duplicate", header_card)
        self.duplicate_button.setObjectName("template_duplicate_button")
        self.duplicate_button.setAutoDefault(False)

        self.export_button = QPushButton("Export…", header_card)
        self.export_button.setObjectName("template_export_button")
        self.export_button.setAutoDefault(False)

        self.delete_button = QPushButton("Delete…", header_card)
        self.delete_button.setObjectName("template_delete_button")
        self.delete_button.setAutoDefault(False)
        apply_ui_style(self.update_button, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
        apply_ui_style(self.rename_button, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
        apply_ui_style(
            self.duplicate_button,
            role=UiRole.BUTTON,
            variant=UiVariant.OUTLINE,
        )
        apply_ui_style(
            self.export_button,
            role=UiRole.BUTTON,
            variant=UiVariant.OUTLINE,
        )
        apply_ui_style(
            self.delete_button,
            role=UiRole.BUTTON,
            variant=UiVariant.DESTRUCTIVE,
        )

        secondary.addWidget(self.duplicate_button)
        secondary.addWidget(self.export_button)
        secondary.addStretch(1)
        secondary.addWidget(self.delete_button)
        header_layout.addLayout(secondary)
        return header_card

    def _build_notes_section(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("template_notes_container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_label = QLabel("Notes", container)
        header_label.setObjectName("template_section_header")

        self.notes = QPlainTextEdit(container)
        self.notes.setObjectName("template_notes_edit")
        self.notes.setMinimumHeight(80)
        self.notes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.notes.setPlaceholderText("Optional notes describing this chart template…")

        notes_footer = QHBoxLayout()
        notes_footer.setContentsMargins(0, 2, 0, 0)
        notes_footer.setSpacing(6)

        self.notes_button = QPushButton("Save Notes", container)
        self.notes_button.setObjectName("template_notes_save_button")
        self.notes_button.setAutoDefault(False)
        self.notes_button.setEnabled(False)
        apply_ui_style(
            self.notes_button,
            role=UiRole.BUTTON,
            variant=UiVariant.OUTLINE,
        )
        apply_ui_style(self.notes, role=UiRole.TEXTAREA)

        notes_footer.addStretch(1)
        notes_footer.addWidget(self.notes_button)

        layout.addWidget(header_label)
        layout.addWidget(self.notes, 1)
        layout.addLayout(notes_footer)
        return container

    def _build_spec_card(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("template_spec_container")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_label = QLabel("Requirements & Blueprint", container)
        header_label.setObjectName("template_section_header")
        layout.addWidget(header_label)

        card = QFrame(container)
        card.setObjectName("template_spec_card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        req_title = QLabel("Required Data:", card)
        req_title.setObjectName("template_spec_subtitle")
        self.contract = QPlainTextEdit(card)
        self.contract.setObjectName("template_contract_label")
        self.contract.setReadOnly(True)
        self.contract.setUndoRedoEnabled(False)
        self.contract.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.contract.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.contract.setMinimumHeight(72)
        self.contract.setPlaceholderText("No data-backed columns")

        card_layout.addWidget(req_title)
        card_layout.addWidget(self.contract, 1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 4, 0, 0)
        meta_row.setSpacing(16)

        blueprint_box = QVBoxLayout()
        blueprint_box.setSpacing(2)
        blueprint_title = QLabel("Blueprint:", card)
        blueprint_title.setObjectName("template_spec_subtitle")
        self.stats = QLabel(card)
        self.stats.setObjectName("template_stats_label")
        self.stats.setWordWrap(True)
        blueprint_box.addWidget(blueprint_title)
        blueprint_box.addWidget(self.stats)

        content_box = QVBoxLayout()
        content_box.setSpacing(2)
        content_title = QLabel("Embedded Content:", card)
        content_title.setObjectName("template_spec_subtitle")
        self.warning = QLabel(card)
        self.warning.setObjectName("template_warning_label")
        self.warning.setWordWrap(True)
        content_box.addWidget(content_title)
        content_box.addWidget(self.warning)

        meta_row.addLayout(blueprint_box, 1)
        meta_row.addLayout(content_box, 1)
        card_layout.addLayout(meta_row)

        layout.addWidget(card, 1)
        return container

    def _build_detail_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("template_detail_page")
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.notes_section = self._build_notes_section()
        self.spec_card = self._build_spec_card()
        layout.addWidget(self.notes_section, 1)
        layout.addWidget(self.spec_card, 1)
        return page

    def _build_error_box(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("template_error_box")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.error_title = QLabel("Corrupted Template File", frame)
        self.error_title.setObjectName("template_error_title")
        self.error_detail = QLabel(frame)
        self.error_detail.setObjectName("template_error_detail")
        self.error_detail.setWordWrap(True)
        self.error_detail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self.error_title)
        layout.addWidget(self.error_detail)
        layout.addStretch(1)
        return frame

    def _build_empty_box(self) -> QFrame:
        frame, title, desc, button = self._build_status_box(
            "template_empty_box",
            "No chart templates found",
            TEMPLATES_EMPTY_DESCRIPTION,
            import_action=True,
        )
        self.empty_title = title
        self.empty_description = desc
        self.empty_import_button = button
        return frame

    def _build_miss_box(self) -> QFrame:
        frame, title, desc, _button = self._build_status_box(
            "template_miss_box",
            "No template matching search",
            TEMPLATES_MISS_DESCRIPTION,
        )
        self.miss_title = title
        self.miss_description = desc
        return frame

    def _build_status_box(
        self,
        object_name: str,
        title: str,
        description: str,
        *,
        import_action: bool = False,
    ) -> tuple[QFrame, QLabel, QLabel, QPushButton | None]:
        frame = QFrame(self)
        frame.setObjectName(object_name)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        title_name = (
            "template_empty_title" if object_name == "template_empty_box" else "template_miss_title"
        )
        desc_name = (
            "template_empty_description"
            if object_name == "template_empty_box"
            else "template_miss_description"
        )

        title_label = QLabel(title, frame)
        title_label.setObjectName(title_name)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        desc_label = QLabel(description, frame)
        desc_label.setObjectName(desc_name)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addStretch(1)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        button = None
        if import_action:
            button = QPushButton("Import…", frame)
            button.setObjectName("template_empty_import_button")
            button.setAutoDefault(False)
            apply_ui_style(button, role=UiRole.BUTTON, variant=UiVariant.OUTLINE)
            layout.addWidget(button, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        return frame, title_label, desc_label, button

    def _show_stack(self, page: QWidget, *, header: bool) -> None:
        self.header_card.setVisible(header)
        self.detail_stack.setCurrentWidget(page)

    def refresh(self, select_id: str | None = None) -> None:
        """Reload valid and corrupt library records."""

        self._entries = list(self.library.entries())
        self.list.clear()
        selected_row = -1
        for row, entry in enumerate(self._entries):
            if entry.valid:
                template = entry.template
                text = template.metadata.name
                template_id = template.metadata.id
                searchable = " ".join(
                    [template.metadata.name, template.metadata.notes]
                    + [
                        column.name
                        for sheet in template.data_contract.sheets
                        for column in sheet.columns
                    ]
                )
                item = QListWidgetItem(text)
                item.setToolTip(
                    f"Name: {template.metadata.name}\nNotes: {template.metadata.notes or '(none)'}"
                )
                if template_id == select_id:
                    selected_row = row
            else:
                text = f"⚠ {entry.path.name}"
                template_id = None
                searchable = f"{entry.path.name} {entry.error}"
                item = QListWidgetItem(text)
                item.setToolTip(f"Corrupted template file:\n{entry.error or 'Parse error'}")

            item.setData(Qt.UserRole, row)
            item.setData(Qt.UserRole + 1, searchable.casefold())
            item.setData(Qt.UserRole + 2, template_id)
            self.list.addItem(item)

        if selected_row >= 0:
            self.list.setCurrentRow(selected_row)
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._show_current(-1)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        query = text.strip().casefold()
        first_visible_row = -1
        for row in range(self.list.count()):
            item = self.list.item(row)
            is_match = query in item.data(Qt.UserRole + 1)
            item.setHidden(not is_match)
            if is_match and first_visible_row < 0:
                first_visible_row = row

        current = self.list.currentItem()
        if current is not None and current.isHidden():
            if first_visible_row >= 0:
                self.list.setCurrentRow(first_visible_row)
            else:
                self._show_current(-1)
        elif current is None and first_visible_row >= 0:
            self.list.setCurrentRow(first_visible_row)
        elif self.list.count() == 0 or first_visible_row < 0:
            self._show_current(-1)

    def _entry(self):
        item = self.list.currentItem()
        if item is None or item.isHidden():
            return None
        row_idx = item.data(Qt.UserRole)
        if row_idx is None or int(row_idx) >= len(self._entries):
            return None
        return self._entries[int(row_idx)]

    def _template(self):
        entry = self._entry()
        return None if entry is None else entry.template

    def _on_notes_changed(self) -> None:
        template = self._template()
        if template is None:
            self.notes_button.setEnabled(False)
            return
        is_dirty = self.notes.toPlainText() != template.metadata.notes
        self.notes_button.setEnabled(is_dirty)

    def _show_current(self, _row: int) -> None:
        entry = self._entry()
        valid = entry is not None and entry.valid
        template = entry.template if valid else None

        for button in (
            self.apply_button,
            self.rename_button,
            self.duplicate_button,
            self.export_button,
        ):
            button.setEnabled(valid)
        self.notes_button.setEnabled(False)
        self.update_button.setEnabled(valid and self.workflow.current_canvas() is not None)
        self.delete_button.setEnabled(entry is not None)

        if valid and template is not None:
            self._show_stack(self.detail_page, header=True)

            self.name_title.setText(template.metadata.name)
            self.name.setText(template.metadata.name)
            created_str = _format_timestamp(template.metadata.created_at)
            updated_str = _format_timestamp(template.metadata.updated_at)
            self.timestamps.setText(f"Created: {created_str}    •    Updated: {updated_str}")

            self.notes.blockSignals(True)
            self.notes.setPlainText(template.metadata.notes)
            self.notes.blockSignals(False)

            self.contract.setPlainText(_format_data_contract(template.data_contract))

            summary = template_content_summary(template)
            self.stats.setText(
                f"{summary['components']} components • {summary['fits']} automatic Fit task(s)"
            )
            self.warning.setText(
                "May contain source data in manual values or embedded images."
                if summary["contains_embedded_content"]
                else "None detected."
            )
        elif entry is not None and not valid:
            self._show_stack(self.error_frame, header=True)
            self.name_title.setText(f"⚠ {entry.path.name}")
            self.name.setText("")
            self.timestamps.setText("Corrupted or invalid template file.")
            self.error_title.setText(f"Corrupted File: {entry.path.name}")
            self.error_detail.setText(
                entry.error or "The file content cannot be parsed as a valid template."
            )

            self.notes.blockSignals(True)
            self.notes.setPlainText("")
            self.notes.blockSignals(False)

            self.contract.setPlainText(entry.error or "Could not parse template.")
            self.stats.clear()
            self.warning.clear()
        else:
            self.name.setText("")
            self.notes.blockSignals(True)
            self.notes.setPlainText("")
            self.notes.blockSignals(False)
            self.stats.clear()
            self.warning.clear()

            if len(self._entries) == 0:
                self._show_stack(self.empty_frame, header=False)
                self.contract.setPlainText("No templates saved in library.")
            else:
                self._show_stack(self.miss_frame, header=False)
                self.contract.setPlainText("No template matches the search query.")

    def _immediate(self, command_id, title, text, handler, *, confirm=False):
        self.host.request_immediate_command(
            command_id,
            title=title,
            text=text,
            handler=handler,
            confirm=confirm,
        )

    def _apply(self) -> None:
        template = self._template()
        if template is None:
            return
        window = self.window()
        if isinstance(window, QDialog):
            window.reject()
        QTimer.singleShot(
            0,
            lambda template_id=template.metadata.id: self.workflow.open_apply(
                self.workflow.figure_window.window(), template_id=template_id
            ),
        )

    def _rename(self) -> None:
        template = self._template()
        if template is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Template", "Template name:", text=template.metadata.name
        )
        if not ok:
            return
        def action():
            updated = self.library.rename(template.metadata.id, name)
            self.refresh(updated.metadata.id)
            self.host.emit_message(f"Template renamed: {updated.metadata.name}", "success")
        self._immediate("template.rename", "Rename Template", "", action)

    def _save_notes(self) -> None:
        template = self._template()
        if template is None:
            return
        def action():
            updated = self.library.save_notes(template.metadata.id, self.notes.toPlainText())
            self.refresh(updated.metadata.id)
            self.host.emit_message(f"Template notes saved: {updated.metadata.name}", "success")
        self._immediate("template.notes", "Save Template Notes", "", action)

    def _duplicate(self) -> None:
        template = self._template()
        if template is None:
            return
        name, ok = QInputDialog.getText(
            self, "Duplicate Template", "New template name:", text=f"{template.metadata.name} Copy"
        )
        if not ok:
            return
        def action():
            created = self.library.duplicate(template.metadata.id, name)
            self.refresh(created.metadata.id)
            self.host.emit_message(f"Template duplicated: {created.metadata.name}", "success")
        self._immediate("template.duplicate", "Duplicate Template", "", action)

    def _update(self) -> None:
        template = self._template()
        if template is None:
            return
        def action():
            updated = self.workflow.open_extract(self, existing=template)
            if updated is not None:
                self.refresh(updated.metadata.id)
        self._immediate(
            "template.update",
            "Update Template",
            "Replace this template's data contract and Figure blueprint with the current Figure?",
            action,
            confirm=True,
        )

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Template", "", f"MyGUI Templates (*{TEMPLATE_FILE_SUFFIX})"
        )
        if not filename:
            return
        def action():
            try:
                imported = self.library.import_template(filename)
            except FileExistsError:
                if not ask_confirmation(
                    self,
                    "Replace Template",
                    "A template with the same stable ID exists. Replace it?",
                    destructive=True,
                ):
                    return
                imported = self.library.import_template(filename, replace_same_id=True)
            self.refresh(imported.metadata.id)
            self.host.emit_message(f"Template imported: {imported.metadata.name}", "success")
        self._immediate("template.import", "Import Template", "", action)

    def _export(self) -> None:
        template = self._template()
        if template is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Template",
            f"{template.metadata.name}{TEMPLATE_FILE_SUFFIX}",
            f"MyGUI Templates (*{TEMPLATE_FILE_SUFFIX})",
        )
        if not filename:
            return
        def action():
            self.library.export_template(template.metadata.id, filename)
            self.host.emit_message(f"Template exported: {Path(filename).name}", "success")
        self._immediate("template.export", "Export Template", "", action)

    def _delete(self) -> None:
        entry = self._entry()
        if entry is None:
            return
        if entry.valid:
            template = entry.template
            def action():
                self.library.delete(template.metadata.id)
                self.refresh()
                self.host.emit_message(f"Template deleted: {template.metadata.name}", "success")
            self._immediate(
                "template.delete",
                "Delete Template",
                f"Delete template {template.metadata.name!r}? This cannot be undone.",
                action,
                confirm=True,
            )
        else:
            filename = entry.path.name
            def action():
                try:
                    if entry.path.exists():
                        entry.path.unlink()
                except OSError as err:
                    raise RuntimeError(f"Could not delete corrupt template file: {err}") from err
                self.refresh()
                self.host.emit_message(f"Corrupt template file deleted: {filename}", "success")
            self._immediate(
                "template.delete_corrupt",
                "Delete Corrupted Template",
                f"Delete corrupted template file {filename!r}? This cannot be undone.",
                action,
                confirm=True,
            )

    def _open_folder(self) -> None:
        def action():
            path = self.library.ensure_directory()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise RuntimeError(f"Could not open template folder: {path}")
        self._immediate("template.open_folder", "Open Template Folder", "", action)


def templates_page_spec(library, workflow):
    """Return the non-persistent Templates page specification."""

    return standard_page_spec(
        PAGE_TEMPLATES,
        lambda host: TemplatesSettingsPage(library, workflow, host),
        description=TEMPLATES_PAGE_DESCRIPTION,
    )
