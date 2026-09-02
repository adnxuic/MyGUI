"""Dialogs and orchestration for extracting and applying chart templates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mygui import status_messages
from mygui.application_theme import bind_widget_qss, subscribe_theme_window
from mygui.widgets.english_buttons import apply_english_dialog_buttons
from mygui.excel_io import (
    EXCEL_FILE_FILTER,
    ExcelImportDialog,
    ExcelSheetSpec,
    read_excel_workbook,
)
from mygui.text_io import TextImportDialog, read_text_source
from mygui.template_library import (
    ChartTemplate,
    TemplateApplyService,
    TemplateExtractor,
    TemplateLibrary,
    TemplateMatcher,
    template_content_summary,
    validate_template,
)
from mygui.template_library.schema import allowed_tokens, validate_template_name
from mygui.template_library.storage import utc_now_text
from mygui.widgets.fig_control_window.background_task import (
    cancel_background_tasks,
    start_background_task,
)


_DIALOG_QSS = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"


def _display_error(parent, title: str, error: Exception | str) -> None:
    message = str(error)
    status_messages.show_error(message)
    QMessageBox.warning(parent, title, message)


class TemplateExtractDialog(QDialog):
    """Collect metadata and editable dynamic text for one extracted blueprint."""

    TEXT_FIELDS = frozenset({"text", "label"})

    def __init__(
        self,
        template: ChartTemplate,
        parent=None,
        *,
        update_existing: bool = False,
    ):
        super().__init__(parent)
        self._template = template
        self._update_existing = bool(update_existing)
        self.setWindowTitle(
            "Update Chart Template" if update_existing else "Change to Template"
        )
        self.setModal(True)
        self.resize(820, 640)
        bind_widget_qss(self, _DIALOG_QSS)

        self.name_edit = QLineEdit(template.metadata.name, self)
        self.name_edit.setMaxLength(80)
        self.name_edit.setReadOnly(update_existing)
        self.notes_edit = QPlainTextEdit(template.metadata.notes, self)
        self.notes_edit.setMaximumBlockCount(2000)
        self.notes_edit.setReadOnly(update_existing)
        form = QFormLayout()
        form.addRow("Template name:", self.name_edit)
        form.addRow("Notes:", self.notes_edit)

        summary = template_content_summary(template)
        self.contract_label = QLabel(
            f"Requires {summary['sheets']} Sheet(s) and {summary['columns']} referenced "
            f"column(s); stores {summary['components']} Figure component(s) and "
            f"will rerun {summary['fits']} Fit task(s).",
            self,
        )
        self.contract_label.setWordWrap(True)

        self.warning_label = QLabel(self)
        self.warning_label.setWordWrap(True)
        if summary["contains_embedded_content"]:
            self.warning_label.setText(
                "Warning: manual XY values, manual reflection positions, or embedded "
                "images may contain source data and will be stored in this template."
            )
            self.warning_label.setProperty("level", "warning")

        self.text_table = QTableWidget(self)
        self.text_table.setObjectName("template_dynamic_text_table")
        self.text_table.setColumnCount(3)
        self.text_table.setHorizontalHeaderLabels(["Component", "Field", "Template text"])
        self.text_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.text_table.setAlternatingRowColors(True)
        self._text_targets: list[tuple[str, str]] = []
        self._populate_text_rows()
        self.text_table.horizontalHeader().setStretchLastSection(True)

        self.token_combo = QComboBox(self)
        self.token_combo.setObjectName("template_variable_combo")
        for token in sorted(allowed_tokens(template.data_contract)):
            self.token_combo.addItem(f"{{{{{token}}}}}", token)
        insert_button = QPushButton("Insert variable", self)
        insert_button.clicked.connect(self._insert_token)
        token_row = QHBoxLayout()
        token_row.addWidget(self.token_combo, 1)
        token_row.addWidget(insert_button)

        self.buttons = apply_english_dialog_buttons(
            QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.contract_label)
        if self.warning_label.text():
            layout.addWidget(self.warning_label)
        layout.addWidget(QLabel("Dynamic text (static unless a variable is inserted):", self))
        layout.addWidget(self.text_table, 1)
        layout.addLayout(token_row)
        layout.addWidget(self.buttons)
        subscribe_theme_window(self)

    def _populate_text_rows(self) -> None:
        root_id = self._template.figure["root_component_id"]
        rows = []
        for component in self._template.figure["components"]:
            for field in self.TEXT_FIELDS:
                value = component["properties"].get(field)
                if not isinstance(value, str):
                    continue
                rows.append((component, field, value))
        self.text_table.setRowCount(len(rows))
        for row, (component, field, value) in enumerate(rows):
            label = component["role"].replace("_", " ").title()
            component_item = QTableWidgetItem(label)
            component_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            field_item = QTableWidgetItem(field)
            field_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.text_table.setItem(row, 0, component_item)
            self.text_table.setItem(row, 1, field_item)
            self.text_table.setItem(row, 2, QTableWidgetItem(value))
            self._text_targets.append((component["id"], field))
        _ = root_id

    def _insert_token(self) -> None:
        row = self.text_table.currentRow()
        if row < 0:
            return
        item = self.text_table.item(row, 2)
        if item is None:
            item = QTableWidgetItem("")
            self.text_table.setItem(row, 2, item)
        item.setText(item.text() + self.token_combo.currentText())

    def _validate_and_accept(self) -> None:
        try:
            self.result_template()
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return
        self.accept()

    def result_template(self) -> ChartTemplate:
        """Return the edited template after strict schema validation."""

        figure = deepcopy(self._template.figure)
        by_id = {item["id"]: item for item in figure["components"]}
        for row, (component_id, field) in enumerate(self._text_targets):
            by_id[component_id]["properties"][field] = self.text_table.item(row, 2).text()
        now = utc_now_text()
        metadata = replace(
            self._template.metadata,
            name=validate_template_name(self.name_edit.text()),
            notes=self.notes_edit.toPlainText(),
            updated_at=now,
        )
        result = replace(self._template, metadata=metadata, figure=figure)
        validate_template(result)
        return result


class TemplateApplyDialog(QDialog):
    """Four-step template selection, preview, mapping, and processing workflow."""

    def __init__(self, workflow: "TemplateWorkflow", parent=None, *, template_id=None):
        super().__init__(parent)
        self.workflow = workflow
        self._template_id = template_id
        self._template: ChartTemplate | None = None
        self._source_file: Path | None = None
        self._specs: list[ExcelSheetSpec] = []
        self._sheet_combos: dict[str, QComboBox] = {}
        self._cancelled = threading.Event()
        self._processing = False
        self.setWindowTitle("Apply Template")
        self.setModal(True)
        self.resize(880, 650)
        bind_widget_qss(self, _DIALOG_QSS)

        self.steps = QStackedWidget(self)
        self.steps.addWidget(self._template_page())
        self.steps.addWidget(self._data_page())
        self.steps.addWidget(self._mapping_page())
        self.steps.addWidget(self._progress_page())

        self.back_button = QPushButton("Back", self)
        self.next_button = QPushButton("Next", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.steps, 1)
        layout.addLayout(buttons)
        self._populate_templates()
        self._sync_buttons()
        subscribe_theme_window(self)

    def _template_page(self) -> QWidget:
        page = QWidget(self)
        self.template_search = QLineEdit(page)
        self.template_search.setPlaceholderText("Search name, notes, or required header")
        self.template_list = QListWidget(page)
        self.template_summary = QLabel(page)
        self.template_summary.setWordWrap(True)
        self.template_search.textChanged.connect(self._filter_templates)
        self.template_list.currentItemChanged.connect(self._template_selected)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("1. Select a template", page))
        layout.addWidget(self.template_search)
        layout.addWidget(self.template_list, 1)
        layout.addWidget(self.template_summary)
        return page

    def _data_page(self) -> QWidget:
        page = QWidget(self)
        self.source_edit = QLineEdit(page)
        self.source_edit.setReadOnly(True)
        browse = QPushButton("Choose and preview data…", page)
        browse.clicked.connect(self._choose_data)
        row = QHBoxLayout()
        row.addWidget(self.source_edit, 1)
        row.addWidget(browse)
        self.data_summary = QLabel("No data selected.", page)
        self.data_summary.setWordWrap(True)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("2. Select one Excel workbook or text file", page))
        layout.addLayout(row)
        layout.addWidget(self.data_summary)
        layout.addStretch()
        return page

    def _mapping_page(self) -> QWidget:
        page = QWidget(self)
        self.project_name_edit = QLineEdit(page)
        self.mapping_form = QFormLayout()
        self.mapping_table = QTableWidget(page)
        self.mapping_table.setColumnCount(4)
        self.mapping_table.setHorizontalHeaderLabels(
            ["Template column", "Imported column", "Type", "Target Sheet"]
        )
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("3. Confirm mapping and project name", page))
        layout.addWidget(self.project_name_edit)
        layout.addLayout(self.mapping_form)
        layout.addWidget(self.mapping_table, 1)
        return page

    def _progress_page(self) -> QWidget:
        page = QWidget(self)
        self.progress_label = QLabel("Ready to validate, preprocess, fit, and create.", page)
        self.progress_label.setWordWrap(True)
        self.progress_bar = QProgressBar(page)
        self.progress_bar.setRange(0, 0)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("4. Processing", page))
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
        return page

    def _populate_templates(self) -> None:
        self.template_list.clear()
        for template in self.workflow.library.templates():
            item = QListWidgetItem(template.metadata.name)
            item.setData(Qt.UserRole, template.metadata.id)
            searchable = " ".join(
                [template.metadata.name, template.metadata.notes]
                + [column.name for sheet in template.data_contract.sheets for column in sheet.columns]
            )
            item.setData(Qt.UserRole + 1, searchable.casefold())
            self.template_list.addItem(item)
            if template.metadata.id == self._template_id:
                self.template_list.setCurrentItem(item)
        if self.template_list.currentItem() is None and self.template_list.count():
            self.template_list.setCurrentRow(0)

    def _filter_templates(self, text: str) -> None:
        query = text.strip().casefold()
        for index in range(self.template_list.count()):
            item = self.template_list.item(index)
            item.setHidden(query not in item.data(Qt.UserRole + 1))

    def _template_selected(self, item, _previous=None) -> None:
        self._template = None if item is None else self.workflow.library.get(item.data(Qt.UserRole))
        if self._template is None:
            self.template_summary.clear()
            return
        summary = template_content_summary(self._template)
        headers = ", ".join(
            column.name for sheet in self._template.data_contract.sheets for column in sheet.columns
        ) or "none"
        self.template_summary.setText(
            f"{self._template.metadata.notes}\nRequired headers: {headers}\n"
            f"{summary['components']} components; {summary['fits']} automatic Fit task(s)."
        )

    def _choose_data(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Template Data",
            "",
            f"Supported data (*.xlsx *.xlsm *.csv *.txt *.dat);;{EXCEL_FILE_FILTER};;All Files (*)",
        )
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.casefold() in {".xlsx", ".xlsm"}:
                preview = ExcelImportDialog(read_excel_workbook(filename), self)
            else:
                preview = TextImportDialog(read_text_source(filename), self)
            if preview.exec() != QDialog.Accepted:
                return
            specs = preview.specs()
            if not specs:
                raise ValueError("Select at least one Sheet and column.")
        except Exception as exc:
            _display_error(self, "Apply Template", exc)
            return
        self._source_file = path
        self._specs = list(specs)
        self.source_edit.setText(str(path))
        self.project_name_edit.setText(path.stem)
        self.data_summary.setText(
            f"{len(specs)} Sheet(s), {sum(len(sheet.columns) for sheet in specs)} column(s) selected."
        )

    def _clear_mapping_form(self) -> None:
        while self.mapping_form.rowCount():
            self.mapping_form.removeRow(0)
        self._sheet_combos.clear()

    def _prepare_mapping(self) -> bool:
        if self._template is None or self._source_file is None or not self._specs:
            return False
        self._clear_mapping_form()
        matcher = TemplateMatcher()
        candidates = matcher.candidate_sheet_indices(self._template, self._specs)
        for slot in self._template.data_contract.sheets:
            combo = QComboBox(self)
            for index in candidates[slot.id]:
                combo.addItem(self._specs[index].target_name, index)
            if combo.count() == 0:
                combo.addItem("No compatible Sheet", -1)
            combo.currentIndexChanged.connect(self._refresh_mapping_table)
            self.mapping_form.addRow(f"{slot.name} →", combo)
            self._sheet_combos[slot.id] = combo
        self._refresh_mapping_table()
        return True

    def _explicit_mapping(self) -> dict[str, int]:
        return {
            slot_id: int(combo.currentData())
            for slot_id, combo in self._sheet_combos.items()
            if combo.currentData() is not None and int(combo.currentData()) >= 0
        }

    def _refresh_mapping_table(self) -> None:
        if self._template is None:
            return
        plan = TemplateMatcher().match(
            self._template,
            self._specs,
            explicit_sheet_mapping=self._explicit_mapping(),
        )
        rows = [
            (sheet, column)
            for sheet in plan.sheets
            for column in sheet.columns
        ]
        slot_columns = {
            column.id: (sheet.name, column.name)
            for sheet in self._template.data_contract.sheets
            for column in sheet.columns
        }
        self.mapping_table.setRowCount(len(rows))
        for row, (sheet, column) in enumerate(rows):
            logical_sheet, logical_column = slot_columns[column.slot_id]
            values = (
                f"{logical_sheet}/{logical_column}",
                column.imported_name,
                column.type.value,
                sheet.imported_name,
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.mapping_table.setItem(row, col, item)

    def _back(self) -> None:
        if self._processing:
            return
        self.steps.setCurrentIndex(max(0, self.steps.currentIndex() - 1))
        self._sync_buttons()

    def _next(self) -> None:
        index = self.steps.currentIndex()
        if index == 0:
            if self._template is None:
                QMessageBox.warning(self, "Apply Template", "Select a valid template.")
                return
        elif index == 1:
            if not self._prepare_mapping():
                QMessageBox.warning(self, "Apply Template", "Choose and preview one data file.")
                return
        elif index == 2:
            self._start_processing()
            return
        self.steps.setCurrentIndex(index + 1)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        index = self.steps.currentIndex()
        self.back_button.setEnabled(index > 0 and not self._processing)
        self.next_button.setVisible(index < 3)
        self.next_button.setText("Create Project" if index == 2 else "Next")
        self.cancel_button.setText("Cancel")

    def _start_processing(self) -> None:
        assert self._template is not None and self._source_file is not None
        project_name = self.project_name_edit.text().strip()
        if not project_name:
            QMessageBox.warning(self, "Apply Template", "Project name must not be empty.")
            return
        mapping = self._explicit_mapping()
        try:
            preview = TemplateMatcher().match(
                self._template, self._specs, explicit_sheet_mapping=mapping
            )
            if not preview.valid:
                raise ValueError(
                    "; ".join(preview.diagnostics)
                    or "Each template Sheet requires a distinct compatible imported Sheet."
                )
        except Exception as exc:
            QMessageBox.warning(self, "Apply Template", str(exc))
            return
        self._processing = True
        self._cancelled.clear()
        self.steps.setCurrentIndex(3)
        self._sync_buttons()
        self.progress_label.setText(
            "Validating data, applying preprocessing, and running automatic fits…"
        )
        start_background_task(
            self,
            self.workflow.apply_service.prepare,
            self._prepared,
            self._prepare_failed,
            self._template,
            self._specs,
            source_file=self._source_file,
            project_name=project_name,
            explicit_sheet_mapping=mapping,
            cancelled=self._cancelled.is_set,
            task_log_prefix="Template application",
        )

    def _prepared(self, plan) -> None:
        if self._cancelled.is_set():
            return
        try:
            self.workflow.apply_service.publish(
                plan,
                table=self.workflow.table,
                figure_window=self.workflow.figure_window,
            )
        except Exception as exc:
            self._prepare_failed(str(exc))
            return
        self._processing = False
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_label.setText("Template applied successfully.")
        status_messages.show_success(
            f"Template applied: {self._template.metadata.name}"
        )
        self.accept()

    def _prepare_failed(self, message: str) -> None:
        if self._cancelled.is_set():
            return
        self._processing = False
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label.setText(message)
        self.back_button.setEnabled(True)
        self.cancel_button.setText("Close")
        status_messages.show_error(message)

    def reject(self) -> None:
        self._cancelled.set()
        cancel_background_tasks(self)
        self._processing = False
        super().reject()


class TemplateWorkflow:
    """One application-scoped UI facade over the template domain services."""

    def __init__(self, *, table, figure_window, library: TemplateLibrary | None = None):
        self.table = table
        self.figure_window = figure_window
        self.library = library or TemplateLibrary()
        self.extractor = TemplateExtractor(table.repository)
        self.apply_service = TemplateApplyService(table.repository)

    def current_canvas(self):
        return getattr(self.figure_window, "current_canva", None)

    def create_apply_dialog(self, parent=None, *, template_id=None) -> TemplateApplyDialog:
        return TemplateApplyDialog(self, parent, template_id=template_id)

    def open_apply(self, parent=None, *, template_id=None) -> int:
        return int(self.create_apply_dialog(parent, template_id=template_id).exec())

    def open_extract(self, parent=None, *, existing: ChartTemplate | None = None) -> ChartTemplate | None:
        canvas = self.current_canvas()
        if canvas is None:
            _display_error(parent, "Change to Template", "Select a Figure first.")
            return None
        try:
            if existing is None:
                project_name = self.table.repository.project(canvas.project_id).name
                draft = self.extractor.extract(
                    canvas,
                    name=f"{project_name} Template",
                )
            else:
                draft = self.extractor.update(existing, canvas)
        except Exception as exc:
            _display_error(parent, "Change to Template", exc)
            return None
        dialog = TemplateExtractDialog(
            draft,
            parent,
            update_existing=existing is not None,
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        try:
            template = dialog.result_template()
            self.library.save(template, replace_existing=existing is not None)
        except Exception as exc:
            _display_error(parent, "Change to Template", exc)
            return None
        status_messages.show_success(
            ("Template updated: " if existing is not None else "Template created: ")
            + template.metadata.name
        )
        return template
