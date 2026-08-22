import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

from mygui.database import ColumnType
from mygui.text_io import (
    TEXT_PREVIEW_TYPE_ROWS,
    TextDataSource,
    TextImportDialog,
    build_text_sheet,
    detect_text_table,
    import_text_into_workspace,
    read_text_source,
)
from main import MainWindow


class DropEventStub:
    def __init__(self, paths):
        self._mime_data = QMimeData()
        self._mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime_data

    def acceptProposedAction(self):
        self.accepted = True
        self.ignored = False

    def ignore(self):
        self.ignored = True
        self.accepted = False


class TextDataImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "SY001.instrument-output"
        self.path.write_text(
            "\n".join([
                "The data in this file is logged by the instrument program",
                "User: Guest",
                "Start Time: 20250726.154234",
                "(*-*)",
                "Wuhan_rotator_A_probe_SY001(*-*)",
                "",
                "Time T(K) P(Deg) B(Oe) L1_theta L1_freq L3_theta L3_freq",
                "1.000000E-3 3.000012E+2 -3.738E-4 1.081E-1 1.378E-2 4.797E-3 1.9194E+1 1.7777E+1",
                "3.240000E-1 3.000012E+2 -3.738E-4 1.081E-1 1.375E-2 4.806E-3 1.9260E+1 1.7777E+1",
                "6.010000D-1 2.999993E+2 -3.738E-4 9.617E-2 1.374E-2 4.781E-3 1.9188E+1 1.7777E+1",
            ]),
            encoding="utf-8",
        )
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def test_detects_header_delimiter_and_numeric_data_block(self):
        source = read_text_source(self.path)
        detection = detect_text_table(source)

        self.assertEqual(detection.delimiter, "Whitespace")
        self.assertEqual(detection.header_line, 7)
        self.assertEqual(detection.data_start_line, 8)
        self.assertEqual(detection.column_count, 8)
        self.assertEqual(detection.row_count, 3)

        sheet, use_header, row_count = build_text_sheet(
            source, detection.delimiter, detection.data_start_line, detection.header_line
        )
        self.assertTrue(use_header)
        self.assertEqual(row_count, 3)
        self.assertEqual(sheet.rows[0][:4], ["Time", "T(K)", "P(Deg)", "B(Oe)"])
        self.assertAlmostEqual(sheet.rows[3][0], 0.601)

    def test_detects_gb18030_and_comma_separated_data(self):
        path = Path(self.directory.name) / "没有固定后缀.001"
        path.write_bytes(
            "仪器说明\n温度,磁场,信号\n300.0,10.0,0.25\n301.0,11.0,0.30\n".encode("gb18030")
        )

        source = read_text_source(path)
        detection = detect_text_table(source)
        self.assertEqual(source.encoding, "gb18030")
        self.assertEqual(detection.delimiter, "Comma")
        self.assertEqual(detection.header_line, 2)
        self.assertEqual(detection.data_start_line, 3)

    def test_extensionless_text_file_is_detected_by_content(self):
        path = Path(self.directory.name) / "measurement"
        path.write_bytes(self.path.read_bytes())
        detection = detect_text_table(read_text_source(path))
        self.assertEqual(detection.column_count, 8)
        self.assertEqual(detection.data_start_line, 8)

    def test_preview_adjusts_header_and_selects_columns(self):
        dialog = TextImportDialog(read_text_source(self.path))
        try:
            self.assertEqual(dialog.data_start_spin.value(), 8)
            self.assertEqual(dialog.header_line_spin.value(), 7)
            self.assertEqual(dialog.preview.column_name_editor(0).text(), "Time")

            dialog.preview.column_include_checkbox(2).setChecked(False)
            self.assertNotIn("P(Deg)", [column.name for column in dialog.specs()[0].columns])

            dialog.header_line_spin.setValue(0)
            self.assertEqual(dialog.preview.column_name_editor(0).text(), "Column 1")
        finally:
            dialog.close()

    def test_import_custom_suffix_creates_typed_project_and_is_undoable(self):
        subtable = import_text_into_workspace(
            str(self.path),
            self.window.table,
            figure_window=self.window.figure_window,
            parent=self.window,
            show_preview=False,
        )
        project = subtable.project
        sheet = next(iter(project.sheets.values()))

        self.assertEqual(len(sheet.columns), 8)
        self.assertTrue(all(column.type == ColumnType.NUMBER for column in sheet.columns))
        self.assertEqual(self.window.figure_window.tabwindow.count(), 1)
        self.assertAlmostEqual(sheet.frame[sheet.columns[0].id].iloc[2], 0.601)

        self.window.repository.undo_stack(project.id).undo()
        self.assertEqual([item.name for item in project.sheets.values()], ["Sheet1"])

    def test_canvas_failure_rolls_back_new_text_workspace(self):
        with patch.object(
            self.window.figure_window,
            "add_figure",
            side_effect=RuntimeError("injected canvas failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "canvas failure"):
                import_text_into_workspace(
                    str(self.path),
                    self.window.table,
                    figure_window=self.window.figure_window,
                    show_preview=False,
                )
        self.assertEqual(self.window.repository.projects, {})
        self.assertEqual(self.window.table.table_names(), [])

    def test_arbitrary_suffix_drop_routes_to_text_import(self):
        enter_event = DropEventStub([self.path])
        self.window.dragEnterEvent(enter_event)
        self.assertTrue(enter_event.accepted)

        drop_event = DropEventStub([self.path])
        with patch.object(self.window, "import_text_file") as importer:
            self.window.dropEvent(drop_event)
        self.assertTrue(drop_event.accepted)
        importer.assert_called_once_with(str(self.path))

    def test_binary_file_is_rejected_by_text_reader(self):
        binary = Path(self.directory.name) / "binary.custom"
        binary.write_bytes(b"\x00\x01\x02\x03" * 20)
        with self.assertRaisesRegex(ValueError, "binary"):
            read_text_source(binary)

    def test_fifty_thousand_row_detection_and_preview_are_linear(self):
        # Guard against accidental quadratic blowup without a scheduler-sensitive
        # wall-clock bound: verification shards the suite across parallel
        # processes, so elapsed timings legitimately vary with CPU contention.
        # Compare the 50k-row cost against a 10k-row baseline measured in the
        # same process: linear behavior costs ~5x (plus fixed overhead),
        # quadratic behavior costs ~25x. The 30s CPU-time ceiling is a pathological
        # backstop that quadratic behavior (minutes) still violates.
        def detect_and_preview(row_total, name):
            lines = ["metadata", "X A B C D E F G"] + [
                f"{row} 1 2 3 4 5 6 7" for row in range(row_total)
            ]
            source = TextDataSource(Path(name), "utf-8", lines)
            started = time.process_time()
            detection = detect_text_table(source)
            preview_sheet, use_header, row_count = build_text_sheet(
                source,
                detection.delimiter,
                detection.data_start_line,
                detection.header_line,
                row_limit=TEXT_PREVIEW_TYPE_ROWS,
            )
            return (
                time.process_time() - started,
                detection,
                preview_sheet,
                use_header,
                row_count,
            )

        baseline_elapsed, *_ = detect_and_preview(10_000, "small.custom")
        elapsed, detection, preview_sheet, use_header, row_count = (
            detect_and_preview(50_000, "large.custom")
        )

        self.assertLess(elapsed, baseline_elapsed * 15 + 1.5)
        self.assertLess(elapsed, 30.0)
        self.assertTrue(use_header)
        self.assertEqual(row_count, 50_000)
        self.assertEqual(detection.column_count, 8)
        self.assertEqual(len(preview_sheet.rows), TEXT_PREVIEW_TYPE_ROWS + 1)

    def test_preview_limit_does_not_truncate_confirmed_import_specs(self):
        lines = ["X Y"] + [f"{row} {row * 2}" for row in range(350)]
        dialog = TextImportDialog(TextDataSource(Path("rows.raw"), "utf-8", lines))
        try:
            self.assertLessEqual(
                len(dialog.preview.sheet.rows),
                TEXT_PREVIEW_TYPE_ROWS + 1,
            )
            specs = dialog.specs()
            self.assertEqual(len(specs[0].columns[0].values), 350)
            self.assertEqual(len(specs[0].columns[1].values), 350)
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
