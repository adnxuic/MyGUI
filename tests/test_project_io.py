import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication

from code.database import ColumnRef, ColumnType
from code.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from main import MainWindow


class ProjectIoV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "project.mygui.json"
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def build_project(self):
        self.window.figure_window.add_figure(
            width=4, height=3, dpi=100, style="default", canva_name="ProjectA"
        )
        canvas = self.window.figure_window.current_canva
        canvas.add_axes()
        sheet = self.window.table.current_subtable().get_table(0).table_model.sheet
        sheet.set_block(0, 0, [
            [1, "alpha", "2026-07-10", "true", 10],
            ["", "", "", "", ""],
            [3, "beta", "2026-07-12", "false", 30],
        ])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[4].id)
        pair = self.window.repository.line_pair(x_ref, y_ref)
        canvas.add_plot(pair.x, pair.y, "-", 2, "black", "plot", x_ref, y_ref)
        return canvas, sheet

    def test_v4_roundtrip_preserves_types_missing_rows_and_refs(self):
        canvas, sheet = self.build_project()
        sheet.columns[0].width = 144
        save_project_snapshot(self.path, self.window.figure_window)
        raw = load_project_file(self.path)

        self.assertEqual(raw["schema_version"], PROJECT_SCHEMA_VERSION)
        columns = raw["table"]["sheets"][0]["columns"]
        self.assertEqual(
            [column["type"] for column in columns],
            ["number", "text", "datetime", "boolean", "number"],
        )
        self.assertIsNone(columns[0]["values"][1])
        self.assertEqual(columns[0]["width"], 144)
        self.assertEqual(raw["figure"]["plots"][0]["x_ref"]["column_id"], sheet.columns[0].id)

        loaded = MainWindow()
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            loaded_sheet = loaded.table.current_subtable().get_table(0).table_model.sheet
            self.assertEqual(loaded_sheet.columns[2].type, ColumnType.DATETIME)
            self.assertEqual(loaded_sheet.columns[0].width, 144)
            self.assertEqual(len(loaded.figure_window.current_canva.project_plots), 1)
            self.assertEqual(len(loaded.figure_window.current_canva.fig.axes[0].lines), 1)
        finally:
            loaded.close()
            self.app.processEvents()

    def test_schema_v3_is_rejected_without_migration(self):
        self.path.write_text(json.dumps({
            "schema": "mygui-project",
            "schema_version": 3,
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only schema v4"):
            load_project_file(self.path)

    def test_missing_column_reference_is_rejected(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["figure"]["plots"][0]["x_ref"]["column_id"] = "missing"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid data reference"):
            load_project_file(self.path)

    def test_text_y_reference_is_rejected(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        text_column_id = raw["table"]["sheets"][0]["columns"][1]["id"]
        raw["figure"]["plots"][0]["y_ref"]["column_id"] = text_column_id
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Incompatible column type"):
            load_project_file(self.path)


if __name__ == "__main__":
    unittest.main()
