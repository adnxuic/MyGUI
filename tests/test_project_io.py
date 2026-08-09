import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication

from code.database import ColumnRef, ColumnType
from code.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from code.figuremodify.components import ComponentKind, ComponentRole
from code.figuremodify.components.serialization import v6_figure_to_legacy
from code.figuremodify.style_base.color_models import PaletteDefinition
from main import MainWindow


class ProjectIoTests(unittest.TestCase):
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

    @staticmethod
    def component(snapshot, role):
        return next(
            component
            for component in snapshot["figure"]["components"]
            if component["role"] == role
        )

    def test_v6_roundtrip_preserves_types_missing_rows_and_refs(self):
        canvas, sheet = self.build_project()
        sheet.columns[0].width = 144
        canvas.canva._set_device_pixel_ratio(2)
        self.assertEqual(canvas.fig.dpi, 200)
        save_project_snapshot(self.path, self.window.figure_window)
        raw = load_project_file(self.path)

        self.assertEqual(raw["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(set(raw["figure"]), {"root_component_id", "components"})
        self.assertEqual(self.component(raw, "figure")["properties"]["dpi"], 100)
        self.assertEqual(self.component(raw, "figure")["properties"]["size_inches"], [4, 3])
        columns = raw["table"]["sheets"][0]["columns"]
        self.assertEqual(
            [column["type"] for column in columns],
            ["number", "text", "datetime", "boolean", "number"],
        )
        self.assertIsNone(columns[0]["values"][1])
        self.assertEqual(columns[0]["width"], 144)
        self.assertEqual(
            self.component(raw, "data_plot")["data"]["x_ref"]["column_id"],
            sheet.columns[0].id,
        )

        loaded = MainWindow()
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            loaded_sheet = loaded.table.current_subtable().get_table(0).table_model.sheet
            self.assertEqual(loaded_sheet.columns[2].type, ColumnType.DATETIME)
            self.assertEqual(loaded_sheet.columns[0].width, 144)
            self.assertEqual(
                len(
                    loaded.figure_window.current_canva.component_registry.query(
                        role=ComponentRole.DATA_PLOT
                    )
                ),
                1,
            )
            self.assertEqual(len(loaded.figure_window.current_canva.fig.axes[0].lines), 1)
            self.assertEqual(loaded.figure_window.current_canva.document_dpi, 100)
        finally:
            loaded.close()
            self.app.processEvents()

    def test_recorded_v4_dpi_is_not_multiplied_on_later_saves(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        figure_root = self.component(raw, "figure")
        figure_root["properties"]["dpi"] = 175.5
        figure_root["properties"]["size_inches"] = [4, 4]
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        loaded = MainWindow()
        second_path = Path(self.directory.name) / "project-second-save.mygui.json"
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            restored = loaded.figure_window.current_canva
            self.assertEqual(restored.document_dpi, 175.5)
            restored.canva._set_device_pixel_ratio(2)
            self.assertEqual(restored.fig.dpi, 351)

            save_project_snapshot(second_path, loaded.figure_window)
            second = load_project_file(second_path)
            self.assertEqual(second["schema_version"], PROJECT_SCHEMA_VERSION)
            second_root = self.component(second, "figure")
            self.assertEqual(second_root["properties"]["dpi"], 175.5)
            self.assertEqual(second_root["properties"]["size_inches"], [4, 4])
        finally:
            loaded.close()
            self.app.processEvents()

    def test_schema_v3_is_rejected_without_migration(self):
        self.path.write_text(json.dumps({
            "schema": "mygui-project",
            "schema_version": 3,
        }), encoding="utf-8")
        with self.assertRaisesRegex(
            ValueError,
            "supported versions are v4, v5, v6, and v7",
        ):
            load_project_file(self.path)

    def test_schema_v4_migrates_through_v5_v6_to_v7(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["figure"] = v6_figure_to_legacy(raw["figure"])
        raw["schema_version"] = 4
        raw["figure"]["plots"][0]["color"] = "tab:blue"
        for axes in raw["figure"]["axes"]:
            axes.pop("color_cycle", None)
        for collection in ("curves", "plots", "scatters", "interpolates", "fits"):
            for record in raw["figure"][collection]:
                record.pop("color_order", None)
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        migrated = load_project_file(self.path)
        migrated_legacy = v6_figure_to_legacy(migrated["figure"])
        self.assertEqual(migrated["schema_version"], 7)
        self.assertIsNone(migrated_legacy["axes"][0]["color_cycle"])
        self.assertEqual(migrated_legacy["plots"][0]["color_order"], 0)
        self.assertEqual(migrated_legacy["plots"][0]["color"], "#1F77B4")

    def test_rgba_and_custom_palette_cursor_roundtrip(self):
        canvas, _sheet = self.build_project()
        palette = PaletteDefinition(
            "custom:project-only", "Project only", ("#11223380", "#ABCDEF"), source="custom"
        )
        result = canvas.axes_commands.apply_palette(
            canvas.current_axes_component_id,
            palette,
        )
        self.assertTrue(result.ok)
        save_project_snapshot(self.path, self.window.figure_window)

        loaded = MainWindow()
        try:
            restore_project_snapshot(self.path, loaded.table, loaded.figure_window)
            restored = loaded.figure_window.current_canva
            state = restored.axes_commands.cycle_state(
                restored.current_axes_component_id
            )
            plot = restored.component_registry.query(
                role=ComponentRole.DATA_PLOT
            )[0]
            self.assertEqual(
                plot.state.properties["color"],
                "#11223380",
            )
            self.assertEqual(state.active_palette.id, "custom:project-only")
            self.assertEqual(state.active_palette.colors, ("#11223380", "#ABCDEF"))
            self.assertEqual(state.next_index, 1)
            status = restored.axes_commands.palette_status(
                restored.current_axes_component_id
            )
            self.assertFalse(status.uses_style_default)
            self.assertEqual(status.palette.name, "Project only")
        finally:
            loaded.close()
            self.app.processEvents()

    def test_style_palette_cursor_roundtrip_and_null_cycle_fallback(self):
        canvas, _sheet = self.build_project()
        root = canvas.component_registry.get(canvas.root_component_id)
        self.assertTrue(root.set_property("style", "ggplot").ok)
        self.assertIsNone(
            canvas.axes_commands.cycle_state(
                canvas.current_axes_component_id
            ).active_palette
        )

        preview = canvas.creation_color_cycle()
        selection = preview.peek()
        self.assertEqual(selection.color, "#348ABD")
        canvas.add_curve(
            "x",
            0.0,
            1.0,
            "-",
            selection.color,
            "curve",
        )
        result = canvas.axes_commands.commit_color_selection(
            canvas.current_axes_component_id,
            selection,
            preview_cycle=preview,
        )
        self.assertTrue(result.ok)
        save_project_snapshot(self.path, self.window.figure_window)
        saved = load_project_file(self.path)
        self.assertEqual(saved["schema_version"], PROJECT_SCHEMA_VERSION)

        loaded = MainWindow()
        try:
            restore_project_snapshot(
                self.path,
                loaded.table,
                loaded.figure_window,
            )
            restored = loaded.figure_window.current_canva
            restored_root = restored.component_registry.get(
                restored.root_component_id
            )
            self.assertEqual(
                restored_root.state.properties["style"],
                "ggplot",
            )
            cycle = restored.axes_commands.cycle_state(
                restored.current_axes_component_id
            )
            self.assertEqual(
                cycle.active_palette.source,
                "matplotlib-style",
            )
            self.assertEqual(cycle.next_index, 2)
            self.assertEqual(
                restored.creation_color_cycle().peek().color,
                "#988ED5",
            )
            status = restored.axes_commands.palette_status(
                restored.current_axes_component_id
            )
            self.assertTrue(status.uses_style_default)
            self.assertEqual(status.figure_style, "ggplot")
            self.assertEqual(
                status.palette.colors,
                cycle.active_palette.colors,
            )
        finally:
            loaded.close()
            self.app.processEvents()

    def test_invalid_color_is_rejected_before_restore(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.component(raw, "data_plot")["properties"]["color"] = "not-a-color"
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"properties.color"):
            load_project_file(self.path)

    def test_missing_column_reference_is_rejected(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.component(raw, "data_plot")["data"]["x_ref"]["column_id"] = "missing"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid data reference"):
            load_project_file(self.path)

    def test_text_y_reference_is_rejected(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        text_column_id = raw["table"]["sheets"][0]["columns"][1]["id"]
        self.component(raw, "data_plot")["data"]["y_ref"]["column_id"] = text_column_id
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Incompatible column type"):
            load_project_file(self.path)

    def test_replace_failure_preserves_existing_project_file(self):
        self.build_project()
        self.path.write_text("existing project", encoding="utf-8")

        with mock.patch(
            "code.project_io.os.replace",
            side_effect=PermissionError("destination is locked"),
        ):
            with self.assertRaises(PermissionError):
                save_project_snapshot(self.path, self.window.figure_window)

        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "existing project",
        )
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_restore_failure_detaches_table_views_before_repository_rollback(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        loaded = MainWindow()
        try:
            with mock.patch.object(
                loaded.figure_window,
                "load_project_figure_snapshot",
                side_effect=RuntimeError("simulated figure restore failure"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "simulated figure restore failure",
                ):
                    restore_project_snapshot(
                        self.path,
                        loaded.table,
                        loaded.figure_window,
                    )
            self.app.processEvents()
            self.assertEqual(loaded.repository.projects, {})
            self.assertEqual(loaded.table.table_names(), [])
        finally:
            loaded.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
