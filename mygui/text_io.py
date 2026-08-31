"""Detect and import delimited text data into table documents."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from mygui.application_theme import bind_widget_qss
from mygui.excel_io import (
    EXCEL_PREVIEW_ROWS,
    ExcelColumnSpec,
    ExcelSheetData,
    ExcelSheetPreview,
    ExcelSheetSpec,
    import_sheet_specs_into_table,
)
from mygui.resource_limits import load_resource_limits


TEXT_DELIMITERS = {
    "Whitespace": None,
    "Tab": "\t",
    "Comma": ",",
    "Semicolon": ";",
}
TEXT_PREVIEW_TYPE_ROWS = max(200, EXCEL_PREVIEW_ROWS)


@dataclass(frozen=True)
class TextDataSource:
    """Represent the application's text data source."""

    path: Path
    encoding: str
    lines: list[str]


@dataclass(frozen=True)
class TextTableDetection:
    """Represent the application's text table detection."""

    delimiter: str
    data_start_line: int
    data_end_line: int
    header_line: int | None
    column_count: int
    row_count: int


def read_text_source(file_name: str | Path) -> TextDataSource:
    """Read text source."""

    path = Path(file_name)
    if not path.is_file():
        raise ValueError(f"Text data file does not exist: {path}")
    limits = load_resource_limits()
    if path.stat().st_size > limits.max_text_bytes:
        raise ValueError("The text data file exceeds the configured byte budget.")
    raw = path.read_bytes()
    if len(raw) > limits.max_text_bytes:
        raise ValueError("The text data file exceeds the configured byte budget.")
    if not raw:
        raise ValueError("The text data file is empty.")

    candidates = ["utf-8-sig", "utf-8", "gb18030", "cp1252"]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.insert(0, "utf-16")

    decoded = None
    encoding = None
    for candidate in candidates:
        try:
            decoded = raw.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if decoded is None or encoding is None:
        raise ValueError("Unable to decode the file as UTF-8, GB18030, UTF-16, or Windows text.")

    control_count = sum(
        1 for char in decoded
        if ord(char) < 32 and char not in "\t\r\n\f"
    )
    if control_count > max(2, len(decoded) // 100):
        raise ValueError("The dropped file appears to be binary rather than text data.")

    lines = decoded.splitlines()
    if not any(line.strip() for line in lines):
        raise ValueError("The text data file contains no readable content.")
    return TextDataSource(path, encoding, lines)


def split_text_fields(line: str, delimiter: str) -> list[str]:
    """Split text fields."""

    separator = TEXT_DELIMITERS[delimiter]
    if separator is None:
        return re.split(r"\s+", line.strip()) if line.strip() else []
    return [field.strip() for field in next(csv.reader([line], delimiter=separator))]


def _number_value(token: str):
    normalized = token.strip().replace("−", "-")
    if not normalized:
        raise ValueError
    return float(re.sub(r"(?<=\d)[dD](?=[+-]?\d)", "E", normalized))


def _numeric_ratio(fields: list[str]) -> float:
    nonempty = [field for field in fields if field.strip()]
    if not nonempty:
        return 0.0
    numeric = 0
    for field in nonempty:
        try:
            _number_value(field)
            numeric += 1
        except ValueError:
            if field.casefold() in {"true", "false", "yes", "no"}:
                numeric += 1
                continue
            value = field.strip().removesuffix("Z")
            for parser in (datetime.fromisoformat, date.fromisoformat, time.fromisoformat):
                try:
                    parser(value)
                    numeric += 1
                    break
                except ValueError:
                    continue
    return numeric / len(nonempty)


def _is_data_row(fields: list[str]) -> bool:
    if not fields:
        return False
    required = 1 if len(fields) == 1 else max(2, math.ceil(len(fields) * 0.5))
    return _numeric_ratio(fields) * len([field for field in fields if field.strip()]) >= required


def _best_run(source: TextDataSource, delimiter: str):
    best = None
    run_start = None
    run_end = None
    run_width = 0
    run_count = 0

    def finish_run():
        nonlocal best, run_start, run_end, run_width, run_count
        if run_start is None or run_end is None or run_count == 0:
            return
        score = (run_count, run_width, -run_start)
        if best is None or score > best[0]:
            best = (score, run_start, run_end + 1, run_width, run_count)

    for index, line in enumerate(source.lines):
        if not line.strip():
            continue
        fields = split_text_fields(line, delimiter)
        is_data = _is_data_row(fields)
        if is_data and run_start is not None and len(fields) == run_width:
            run_end = index
            run_count += 1
            continue

        finish_run()
        if is_data:
            run_start = index
            run_end = index
            run_width = len(fields)
            run_count = 1
        else:
            run_start = None
            run_end = None
            run_width = 0
            run_count = 0

    finish_run()
    return best


def detect_text_table(source: TextDataSource, delimiter: str | None = None) -> TextTableDetection:
    """Detect delimiter, encoding, and tabular structure in text data."""

    candidates = [delimiter] if delimiter is not None else list(TEXT_DELIMITERS)
    best = None
    for candidate in candidates:
        run = _best_run(source, candidate)
        if run is None:
            continue
        score, start, end, width, row_count = run
        ranked = (score, candidate, start, end, width, row_count)
        if best is None or ranked[0] > best[0]:
            best = ranked
    if best is None:
        raise ValueError(
            "No consistent numeric data block was found. Adjust the source file or delimiter."
        )

    _, selected, start, end, width, row_count = best
    header_line = None
    fallback = None
    for index in range(start - 1, -1, -1):
        if not source.lines[index].strip():
            continue
        fields = split_text_fields(source.lines[index], selected)
        if _is_data_row(fields):
            break
        if fallback is None and len(fields) >= max(1, math.ceil(width * 0.5)):
            fallback = index
        if len(fields) == width:
            header_line = index
            break
    if header_line is None:
        header_line = fallback

    return TextTableDetection(
        delimiter=selected,
        data_start_line=start + 1,
        data_end_line=end,
        header_line=None if header_line is None else header_line + 1,
        column_count=width,
        row_count=row_count,
    )


def _convert_text_value(token: str):
    value = token.strip()
    if value == "":
        return None
    lowered = value.casefold()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    try:
        return _number_value(value)
    except ValueError:
        return value


def build_text_sheet(source: TextDataSource, delimiter: str, data_start_line: int,
                     header_line: int | None, row_limit: int | None = None
                     ) -> tuple[ExcelSheetData, bool, int]:
    """Build text sheet."""

    start = data_start_line - 1
    if start < 0 or start >= len(source.lines):
        raise ValueError("First data line is outside the source file.")
    if header_line is not None and header_line > 0 and header_line >= data_start_line:
        raise ValueError("The column-name line must be before the first data line.")

    first_fields = split_text_fields(source.lines[start], delimiter)
    if not first_fields:
        raise ValueError("The selected first data line is empty.")
    width = len(first_fields)
    numeric_mode = _numeric_ratio(first_fields) >= 0.5
    data_rows = []
    total_rows = 0
    for line in source.lines[start:]:
        if not line.strip():
            continue
        fields = split_text_fields(line, delimiter)
        if len(fields) != width:
            if data_rows:
                break
            raise ValueError("The selected first data line has an inconsistent column count.")
        if numeric_mode and _numeric_ratio(fields) < 0.5:
            break
        total_rows += 1
        if row_limit is None or len(data_rows) < row_limit:
            data_rows.append([_convert_text_value(field) for field in fields])
    if total_rows == 0:
        raise ValueError("No data rows were found from the selected first data line.")

    use_header = header_line is not None and header_line > 0
    rows = []
    if use_header:
        header_fields = split_text_fields(source.lines[header_line - 1], delimiter)
        names = [
            header_fields[column] if column < len(header_fields) and header_fields[column] else f"Column {column + 1}"
            for column in range(width)
        ]
        rows.append(names)
    rows.extend(data_rows)
    sheet_name = source.path.stem or source.path.name or "Imported Data"
    return ExcelSheetData(sheet_name, rows), use_header, total_rows


class TextImportDialog(QDialog):
    """Provide the text import dialog Qt widget."""

    def __init__(self, source: TextDataSource, parent=None):
        super().__init__(parent)
        self.source = source
        self.preview: ExcelSheetPreview | None = None
        self._accepted_specs: list[ExcelSheetSpec] | None = None
        self.setWindowTitle("Import Text Data")
        bind_widget_qss(
            self,
            "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss",
        )
        self.resize(960, 680)
        self.setMinimumSize(760, 520)

        detection = detect_text_table(source)
        self.encoding_label = QLabel(source.encoding, self)
        self.delimiter_combo = QComboBox(self)
        self.delimiter_combo.addItems(list(TEXT_DELIMITERS))
        self.delimiter_combo.setCurrentText(detection.delimiter)
        self.data_start_spin = QSpinBox(self)
        self.data_start_spin.setRange(1, len(source.lines))
        self.data_start_spin.setValue(detection.data_start_line)
        self.header_line_spin = QSpinBox(self)
        self.header_line_spin.setSpecialValueText("Generate column names")
        self.header_line_spin.setRange(0, max(0, detection.data_start_line - 1))
        self.header_line_spin.setValue(detection.header_line or 0)

        form = QFormLayout()
        form.addRow("Detected encoding:", self.encoding_label)
        form.addRow("Separator:", self.delimiter_combo)
        form.addRow("First data line:", self.data_start_spin)
        form.addRow("Column-name line:", self.header_line_spin)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("import_summary_label")
        self.preview_layout = QVBoxLayout()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary_label)
        layout.addLayout(self.preview_layout, stretch=1)
        layout.addWidget(self.buttons)

        self.delimiter_combo.currentTextChanged.connect(self._redetect_delimiter)
        self.data_start_spin.valueChanged.connect(self._source_lines_changed)
        self.header_line_spin.valueChanged.connect(self._rebuild_preview)
        self._rebuild_preview()

    def _set_summary_level(self, level: str) -> None:
        self.summary_label.setProperty("level", level)
        style = self.summary_label.style()
        if style is not None:
            style.unpolish(self.summary_label)
            style.polish(self.summary_label)

    def _redetect_delimiter(self, delimiter: str):
        try:
            detection = detect_text_table(self.source, delimiter)
        except ValueError as exc:
            self._show_error(exc)
            return
        data_blocker = QSignalBlocker(self.data_start_spin)
        header_blocker = QSignalBlocker(self.header_line_spin)
        self.data_start_spin.setValue(detection.data_start_line)
        self.header_line_spin.setRange(0, max(0, detection.data_start_line - 1))
        self.header_line_spin.setValue(detection.header_line or 0)
        del data_blocker, header_blocker
        self._rebuild_preview()

    def _source_lines_changed(self, data_start_line: int):
        blocker = QSignalBlocker(self.header_line_spin)
        current_header = self.header_line_spin.value()
        self.header_line_spin.setRange(0, max(0, data_start_line - 1))
        self.header_line_spin.setValue(min(current_header, max(0, data_start_line - 1)))
        del blocker
        self._rebuild_preview()

    def _show_error(self, error: Exception):
        self.summary_label.setText(str(error))
        self._set_summary_level("error")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)

    def _rebuild_preview(self):
        try:
            sheet, use_header, row_count = build_text_sheet(
                self.source,
                self.delimiter_combo.currentText(),
                self.data_start_spin.value(),
                self.header_line_spin.value() or None,
                row_limit=TEXT_PREVIEW_TYPE_ROWS,
            )
        except ValueError as exc:
            self._show_error(exc)
            return

        if self.preview is not None:
            self.preview_layout.removeWidget(self.preview)
            self.preview.deleteLater()
        self.preview = ExcelSheetPreview(sheet, self, use_header=use_header)
        self.preview.include.hide()
        self.preview.header.hide()
        self.preview_layout.addWidget(self.preview)
        self._accepted_specs = None
        skipped = self.data_start_spin.value() - 1
        self.summary_label.setText(
            f"Detected {row_count} data rows × {self.preview.columns.columnCount()} columns; "
            f"removed {skipped} leading lines."
        )
        self._set_summary_level("success")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def specs(self) -> list[ExcelSheetSpec]:
        """Return the current specs."""

        if self._accepted_specs is not None:
            return self._accepted_specs
        if self.preview is None:
            raise ValueError("The text preview is not valid.")
        preview_spec = self.preview.spec()
        if preview_spec is None:
            return []

        full_sheet, use_header, _ = build_text_sheet(
            self.source,
            self.delimiter_combo.currentText(),
            self.data_start_spin.value(),
            self.header_line_spin.value() or None,
        )
        value_start = 1 if use_header else 0
        selected_indices = [
            column for column in range(self.preview.columns.columnCount())
            if self.preview.column_include_checkbox(column).isChecked()
        ]
        full_columns = []
        for source_column, schema in zip(selected_indices, preview_spec.columns, strict=True):
            values = [
                row[source_column] if source_column < len(row) else None
                for row in full_sheet.rows[value_start:]
            ]
            full_columns.append(ExcelColumnSpec(schema.name, schema.type, values))
        return [ExcelSheetSpec(
            preview_spec.source_name,
            preview_spec.target_name,
            full_columns,
        )]

    def _validate_and_accept(self):
        self.summary_label.setText("Preparing full data for import...")
        self._set_summary_level("info")
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            specs = self.specs()
            if not specs:
                raise ValueError("Select at least one column to import.")
        except ValueError as exc:
            QMessageBox.warning(self, "Import Text Data", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._accepted_specs = specs
        self.accept()


def _default_text_specs(source: TextDataSource) -> list[ExcelSheetSpec]:
    detection = detect_text_table(source)
    sheet, use_header, _ = build_text_sheet(
        source, detection.delimiter, detection.data_start_line, detection.header_line
    )
    preview = ExcelSheetPreview(sheet, use_header=use_header)
    try:
        spec = preview.spec()
    finally:
        preview.deleteLater()
    return [] if spec is None else [spec]


def import_text_into_table(
    file_name: str,
    table,
    parent=None,
    show_preview: bool = True,
    *,
    publish_new_project: bool = True,
):
    """Import text into table."""

    source = read_text_source(file_name)
    if show_preview:
        dialog = TextImportDialog(source, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        specs = dialog.specs()
    else:
        specs = _default_text_specs(source)
    return import_sheet_specs_into_table(
        str(source.path), specs, table,
        command_text="Import Text Data", reason="text-import",
        publish_new_project=publish_new_project,
    )


def import_text_into_workspace(file_name: str, table, figure_window=None, parent=None,
                               show_preview: bool = True):
    """Import text into workspace."""

    create_canvas = figure_window is not None and figure_window.current_canva is None
    stage_new_project = create_canvas and table.current_subtable() is None
    subtable = import_text_into_table(
        file_name,
        table,
        parent=parent or table,
        show_preview=show_preview,
        publish_new_project=not stage_new_project,
    )
    if subtable is None:
        return None
    if create_canvas:
        try:
            width, height, dpi = figure_window.creation_figure_size()
            figure_window.add_figure(
                width=width,
                height=height,
                dpi=dpi,
                style="default",
                canva_name=subtable.project.name,
                create_table=False,
            )
        except Exception:
            if stage_new_project:
                table.remove_project_table(
                    subtable.project.id,
                    publish=False,
                )
            raise
        if stage_new_project:
            table.repository.publish_project_added(subtable.project.id)
    return subtable
