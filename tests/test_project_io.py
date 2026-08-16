import json
import os
import tempfile
from copy import deepcopy
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mygui import status_messages
from mygui.database import ColumnRef, ColumnType, TableRepository, scipy_fit_adapter
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    project_snapshot,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.figuremodify.components import ComponentRole
from mygui.figuremodify.style_base.color_models import PaletteDefinition
from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas
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
        create_regular_axes(canvas)
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

    def test_v10_roundtrip_preserves_types_missing_rows_and_refs(self):
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

    def test_open_project_has_one_final_message_and_stays_clean_after_ui_only_changes(self):
        canvas, sheet = self.build_project()
        sheet.set_block(2, 0, [[None]])
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[4].id)
        pair = self.window.repository.valid_pair(x_ref, y_ref)
        canvas.add_scatter(
            pair.x,
            pair.y,
            36.0,
            "#1f77b4",
            "o",
            "mapped scatter",
            x_ref,
            y_ref,
            color_ref=y_ref,
            color_mapping={
                "enabled": True,
                "cmap": "viridis",
                "norm": {
                    "kind": "linear",
                    "params": {"vmin": None, "vmax": None, "clip": False},
                },
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
        )
        scatter_id = canvas.component_registry.query(
            role=ComponentRole.SCATTER
        )[0].component_id
        axes_controller = canvas.component_registry.get(
            canvas.current_axes_component_id
        )
        self.assertTrue(axes_controller.set_property("ylim", (0.0, 0.4)).ok)
        save_project_snapshot(self.path, self.window.figure_window)
        canvas.message_presenter.discard_pending()
        opened = MainWindow()
        second_path = Path(self.directory.name) / "project-second.mygui.json"
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        try:
            with mock.patch(
                "mygui.widgets.title_bar.py_title_menu.QFileDialog.getOpenFileName",
                return_value=(str(self.path), ""),
            ):
                opened.title_bar.menu_bar.open_project()
            self.app.processEvents()
            self.app.processEvents()

            self.assertEqual(
                events,
                [(f"Project opened: {self.path.name}", "success")],
            )
            restored = opened.figure_window.current_canva
            figure_window = opened.figure_window
            self.assertFalse(figure_window.is_canvas_dirty(restored))
            before = project_snapshot(figure_window, canvas=restored)
            restored_scatter = restored.component_registry.query(
                role=ComponentRole.SCATTER
            )[0]
            self.assertEqual(
                restored_scatter.state.data["color_ref"],
                y_ref.to_dict(),
            )
            self.assertEqual(
                len(restored_scatter.resolve_target().get_offsets()),
                1,
            )
            self.assertEqual(
                tuple(
                    restored.component_registry.get(
                        restored.current_axes_component_id
                    ).state.properties["ylim"]
                ),
                (0.0, 0.4),
            )

            title_id = restored.component_registry.query(
                role=ComponentRole.TITLE
            )[0].component_id
            self.assertTrue(restored.select_component(title_id))
            self.assertTrue(restored.select_component(scatter_id))
            opened.component_tree_host.search_input.setText("Title")
            self.app.processEvents()
            opened.component_tree_host.search_input.clear()
            opened.component_tree_host.tree.expandAll()
            self.app.processEvents()

            self.assertEqual(
                project_snapshot(figure_window, canvas=restored),
                before,
            )
            self.assertFalse(figure_window.is_canvas_dirty(restored))

            save_project_snapshot(
                second_path,
                figure_window,
                canvas=restored,
            )
            self.assertEqual(self.path.read_bytes(), second_path.read_bytes())
            self.assertFalse(figure_window.is_canvas_dirty(restored))

            opened.show()
            self.app.processEvents()
            with mock.patch.object(opened, "_project_close_choice") as choice:
                self.assertTrue(opened.close())
            choice.assert_not_called()
        finally:
            status_messages.clear_status_handler(handler)
            opened.close_without_prompt()
            self.app.processEvents()

    def test_unbounded_low_dof_fit_roundtrips_with_json_null(self):
        canvas, sheet = self.build_project()
        x_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(canvas.project_id, sheet.id, sheet.columns[4].id)
        pair = self.window.repository.valid_pair(x_ref, y_ref)
        fit_options = scipy_fit_adapter.default_fit_options("poly1")
        fit_result = scipy_fit_adapter.fit_curve(
            pair.x,
            pair.y,
            "poly1",
            fit_options,
        )
        canvas.add_fit_curve(
            pair.x,
            pair.y,
            "tab:red",
            "fit",
            x_ref,
            y_ref,
            fit_type="poly1",
            fit_options=fit_options,
            fit_result=fit_result,
            expression=fit_result["value_expression"],
        )

        save_project_snapshot(self.path, self.window.figure_window)
        raw_text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", raw_text)
        self.assertNotIn("Infinity", raw_text)
        loaded = load_project_file(self.path)
        fit = self.component(loaded, "fit_curve")
        self.assertEqual(fit["data"]["fit_options"]["Lower"], [None, None])
        self.assertEqual(fit["data"]["fit_options"]["Upper"], [None, None])
        self.assertIsNone(fit["data"]["fit_result"]["goodness"]["rmse"])
        self.assertIsNone(
            fit["data"]["fit_result"]["goodness"]["adjrsquare"]
        )

        reopened = MainWindow()
        try:
            restore_project_snapshot(self.path, reopened.table, reopened.figure_window)
            restored = reopened.figure_window.current_canva.component_snapshot()
            restored_fit = next(
                component
                for component in restored["components"]
                if component["role"] == "fit_curve"
            )
            self.assertEqual(restored_fit["data"]["fit_options"], fit["data"]["fit_options"])
            self.assertEqual(restored_fit["data"]["fit_result"], fit["data"]["fit_result"])
        finally:
            reopened.close()
            self.app.processEvents()

    def test_recorded_dpi_is_not_multiplied_on_later_saves(self):
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

    def test_only_exact_integer_schema_v10_is_accepted(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        valid = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(load_project_file(self.path)["schema_version"], 10)
        for version in (3, 4, 5, 6, 7, 8, 9, 10.0, "10", 11, True, None):
            with self.subTest(version=version):
                candidate = dict(valid)
                candidate["schema_version"] = version
                self.path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "only schema v10 is supported"):
                    load_project_file(self.path)

    def test_v10_wrapper_rejects_retired_figure_and_axes_shapes(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        valid = json.loads(self.path.read_text(encoding="utf-8"))

        empty_figure = deepcopy(valid)
        self.component(empty_figure, "figure")["data"] = {}
        self.path.write_text(json.dumps(empty_figure), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "layouts"):
            load_project_file(self.path)

        old_subplot = deepcopy(valid)
        self.component(old_subplot, "axes")["data"]["subplot"] = {
            "layout_group": 0,
            "nrows": 1,
            "ncols": 1,
            "slot": 1,
        }
        self.path.write_text(json.dumps(old_subplot), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "subplot fields"):
            load_project_file(self.path)

    def test_v10_rejects_unsafe_preprocessing_before_restore(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.component(raw, "data_plot")["data"]["preprocess"][
            "x_expression"
        ] = "__import__('os')"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "preprocess"):
            load_project_file(self.path)

    def test_v10_rejects_non_identity_datetime_preprocessing_before_restore(self):
        _canvas, sheet = self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        plot_data = self.component(raw, "data_plot")["data"]
        plot_data["x_ref"] = ColumnRef(
            raw["project"]["id"],
            sheet.id,
            sheet.columns[2].id,
        ).to_dict()
        plot_data["preprocess"]["x_expression"] = "1/x"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Date/time X data"):
            load_project_file(self.path)

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
            "mygui.project_io.os.replace",
            side_effect=PermissionError("destination is locked"),
        ):
            with self.assertRaises(PermissionError):
                save_project_snapshot(self.path, self.window.figure_window)

        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "existing project",
        )
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_post_replace_clean_bookkeeping_cannot_report_save_failure(self):
        self.build_project()
        with mock.patch.object(
            self.window.figure_window,
            "mark_canvas_clean",
            side_effect=RuntimeError("injected bookkeeping failure"),
        ):
            snapshot = save_project_snapshot(self.path, self.window.figure_window)

        self.assertEqual(load_project_file(self.path), snapshot)

    def test_nonfinite_runtime_table_state_cannot_replace_existing_file(self):
        _canvas, sheet = self.build_project()
        self.path.write_text("preserve-me", encoding="utf-8")
        sheet.frame.at[0, sheet.columns[0].id] = float("inf")

        with self.assertRaisesRegex(ValueError, "finite"):
            save_project_snapshot(self.path, self.window.figure_window)

        self.assertEqual(self.path.read_text(encoding="utf-8"), "preserve-me")

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

    def test_table_widget_construction_failure_never_publishes_project(self):
        observed = []
        self.window.repository.transaction_committed.connect(observed.append)
        with mock.patch(
            "mygui.widgets.table.py_table.PySubTable",
            side_effect=RuntimeError("injected table widget failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "table widget failure"):
                self.window.figure_window.add_figure(
                    width=4,
                    height=3,
                    dpi=100,
                    style="default",
                    canva_name="FailedTable",
                )

        self.assertEqual(self.window.repository.projects, {})
        self.assertEqual(self.window.table._subtables, {})
        self.assertEqual(self.window.figure_window.tabwindow.count(), 0)
        self.assertEqual(observed, [])

    def test_restore_materialization_failure_is_clean_before_tab_publication(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        loaded = MainWindow()
        original_restore = PyFigureCanvas.restore_component_tree

        def restore_then_fail(canvas, component_tree=None):
            original_restore(canvas, component_tree)
            raise RuntimeError("injected post-materialization failure")

        try:
            with mock.patch.object(
                PyFigureCanvas,
                "restore_component_tree",
                new=restore_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "post-materialization"):
                    restore_project_snapshot(
                        self.path,
                        loaded.table,
                        loaded.figure_window,
                    )
            self.app.processEvents()
            self.assertEqual(loaded.repository.projects, {})
            self.assertEqual(loaded.table._subtables, {})
            self.assertEqual(loaded.figure_window.canvas, {})
            self.assertEqual(loaded.figure_window.tabwindow.count(), 0)
        finally:
            loaded.close()
            self.app.processEvents()

    def test_restore_rejects_different_table_and_figure_repositories(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        table = SimpleNamespace(repository=TableRepository())
        figure_window = SimpleNamespace(repository=TableRepository())

        with self.assertRaisesRegex(ValueError, "share one TableRepository"):
            restore_project_snapshot(self.path, table, figure_window)

    def test_cleanup_failure_does_not_mask_primary_restore_error(self):
        self.build_project()
        save_project_snapshot(self.path, self.window.figure_window)
        loaded = MainWindow()
        try:
            with (
                mock.patch.object(
                    loaded.figure_window,
                    "load_project_figure_snapshot",
                    side_effect=RuntimeError("primary restore failure"),
                ),
                mock.patch.object(
                    loaded.table,
                    "remove_project_table",
                    side_effect=RuntimeError("cleanup failure"),
                ),
                self.assertLogs("mygui.project_io", level="ERROR") as logs,
            ):
                with self.assertRaisesRegex(RuntimeError, "primary restore failure"):
                    restore_project_snapshot(
                        self.path,
                        loaded.table,
                        loaded.figure_window,
                    )
            self.assertIn("cleanup failure", "\n".join(logs.output))
        finally:
            project_ids = list(loaded.repository.projects)
            for project_id in project_ids:
                loaded.table.remove_project_table(project_id, publish=False)
            loaded.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
