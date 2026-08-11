import json
import os
import tempfile
import unittest
from unittest import mock
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from PySide6.QtWidgets import QApplication

from mygui import status_messages
from mygui.database import ColumnRef, ColumnType, TableChangeSet
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.components.serialization import validate_v9_figure
from mygui.figuremodify.style_base.color_models import PaletteDefinition
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from main import MainWindow


class ComponentRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name="RuntimeComponents",
        )
        self.canvas = self.window.figure_window.current_canva
        self.canvas.add_axes()
        self.sheet = (
            self.window.table.current_subtable()
            .get_table(0)
            .table_model.sheet
        )
        self.x_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[0].id,
        )
        self.y_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[1].id,
        )

    def tearDown(self):
        status_messages.clear_status_handler()
        self.window.close()
        self.app.processEvents()

    def _set_source_data(self):
        self.sheet.set_block(
            0,
            0,
            [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0], [3.0, 8.0]],
        )
        return (
            self.window.repository.line_pair(self.x_ref, self.y_ref),
            self.window.repository.valid_pair(self.x_ref, self.y_ref),
        )

    def _available_refs(self, canvas=None):
        canvas = canvas or self.canvas
        project = canvas.repository.project(canvas.project_id)
        return {
            ColumnRef(project.id, sheet.id, column.id): column.type
            for sheet in project.sheets.values()
            for column in sheet.columns
        }

    def _add_all_runtime_components(self):
        line_pair, valid_pair = self._set_source_data()
        method = list(interpolate_dict)[2]
        ids = {
            "curve": "runtime-curve",
            "plot": "runtime-plot",
            "scatter": "runtime-scatter",
            "fit": "runtime-fit",
            "interpolation": "runtime-interpolation",
            "axes_text": "runtime-axes-text",
            "figure_text": "runtime-figure-text",
        }
        self.canvas.add_curve(
            "x**2",
            0.0,
            3.0,
            "-",
            "#112233",
            "curve",
            object_id=ids["curve"],
        )
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "--",
            3.0,
            "#223344",
            "plot",
            self.x_ref,
            self.y_ref,
            object_id=ids["plot"],
        )
        self.canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            20.0,
            "#334455",
            "o",
            "scatter",
            self.x_ref,
            self.y_ref,
            object_id=ids["scatter"],
        )
        self.canvas.add_fit_curve(
            valid_pair.x,
            valid_pair.y,
            "#445566",
            "fit",
            self.x_ref,
            self.y_ref,
            expression="x**2",
            x_start=0.0,
            x_stop=3.0,
            object_id=ids["fit"],
        )
        self.canvas.add_interpolate_curve(
            valid_pair.x,
            valid_pair.y,
            self.x_ref,
            self.y_ref,
            method,
            color="#556677",
            label="interpolation",
            object_id=ids["interpolation"],
        )
        self.canvas.add_text(
            0.25,
            0.75,
            "axes text",
            "DejaVu Sans",
            12,
            object_id=ids["axes_text"],
        )
        self.canvas.add_global_text(
            0.5,
            0.5,
            "figure text",
            "DejaVu Sans",
            14,
            object_id=ids["figure_text"],
        )
        self.canvas.current_axes.legend()
        return ids

    def test_canvas_registers_complete_component_tree_and_valid_v8_snapshot(self):
        ids = self._add_all_runtime_components()
        registry = self.canvas.component_registry
        registry.validate_tree()

        roles = Counter(controller.state.role for controller in registry)
        expected_roles = {
            ComponentRole.FIGURE: 1,
            ComponentRole.AXES: 1,
            ComponentRole.X_AXIS: 1,
            ComponentRole.Y_AXIS: 1,
            ComponentRole.SPINE: 4,
            ComponentRole.MAJOR_TICK: 2,
            ComponentRole.MINOR_TICK: 2,
            ComponentRole.MAJOR_TICK_LABEL: 2,
            ComponentRole.MINOR_TICK_LABEL: 2,
            ComponentRole.GRID: 4,
            ComponentRole.TITLE: 1,
            ComponentRole.X_LABEL: 1,
            ComponentRole.Y_LABEL: 1,
            ComponentRole.LEGEND: 1,
            ComponentRole.FUNCTION_CURVE: 1,
            ComponentRole.DATA_PLOT: 1,
            ComponentRole.SCATTER: 1,
            ComponentRole.FIT_CURVE: 1,
            ComponentRole.INTERPOLATION: 1,
            ComponentRole.TEXT: 2,
        }
        for role, count in expected_roles.items():
            self.assertEqual(roles[role], count, role.value)
        self.assertEqual(len(registry), sum(expected_roles.values()))
        self.assertEqual(
            len(registry.descendants(self.canvas.root_component_id)),
            len(registry) - 1,
        )
        for component_id in ids.values():
            self.assertIn(component_id, registry)
            self.assertIsNotNone(registry.resolve_target(component_id))

        snapshot = self.canvas.component_snapshot()
        validate_v9_figure(
            snapshot,
            self._available_refs(),
            self.canvas.project_id,
            self.canvas.project_name,
        )
        self.assertEqual(snapshot["root_component_id"], self.canvas.root_component_id)
        self.assertEqual(len(snapshot["components"]), len(registry))

    def test_chart_panel_updates_live_controller_state(self):
        line_pair, _valid_pair = self._set_source_data()
        object_id = "panel-plot"
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "before",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
        )
        controller = self.canvas.component_registry.get(object_id)
        widget = self.canvas.component_editor_manager.editor(object_id)
        appearance = widget.section("appearance")

        style_combo = appearance.editor("linestyle")
        style_combo.setCurrentIndex(style_combo.findData("--"))
        appearance.editor("markersize").setValue(7.5)
        appearance.editor("label").setText("after")
        self.assertTrue(appearance.flush_text("label"))

        state = controller.read_state()
        self.assertEqual(state.properties["linestyle"], "--")
        self.assertEqual(state.properties["markersize"], 7.5)
        self.assertEqual(state.properties["label"], "after")

    def test_first_curve_autoscale_syncs_axes_controller_and_common_editor(self):
        axes = self.canvas.current_axes
        controller = self.canvas.current_axes_controller
        common = self.canvas.figure_inspector.axes_inspector(
            controller.component_id
        ).inspector(
            controller.component_id
        )

        self.canvas.add_curve(
            "x**2",
            10.0,
            20.0,
            "-",
            "#123456",
            "curve",
            object_id="autoscale-curve",
        )
        self.app.processEvents()

        xlim = tuple(float(value) for value in axes.get_xlim())
        ylim = tuple(float(value) for value in axes.get_ylim())
        np.testing.assert_allclose(
            controller.state.properties["xlim"],
            xlim,
        )
        np.testing.assert_allclose(
            controller.state.properties["ylim"],
            ylim,
        )
        np.testing.assert_allclose(
            controller.read_state().properties["xlim"],
            xlim,
        )
        np.testing.assert_allclose(
            controller.read_state().properties["ylim"],
            ylim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in common.editor("xlim").inputs
            ],
            xlim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in common.editor("ylim").inputs
            ],
            ylim,
        )

    def test_first_scatter_autoscale_keeps_collection_limits(self):
        axes = self.canvas.current_axes
        controller = self.canvas.current_axes_controller
        common = self.canvas.figure_inspector.axes_inspector(
            controller.component_id
        ).inspector(
            controller.component_id
        )

        self.sheet.set_block(
            0,
            0,
            [[10.0, 100.0], [20.0, 200.0]],
        )

        self.canvas.add_scatter(
            np.asarray([10.0, 20.0]),
            np.asarray([100.0, 200.0]),
            20.0,
            "#123456",
            "o",
            "scatter",
            self.x_ref,
            self.y_ref,
            object_id="autoscale-scatter",
        )
        self.app.processEvents()

        xlim = tuple(float(value) for value in axes.get_xlim())
        ylim = tuple(float(value) for value in axes.get_ylim())
        self.assertLess(xlim[0], 10.0)
        self.assertGreater(xlim[1], 20.0)
        self.assertLess(ylim[0], 100.0)
        self.assertGreater(ylim[1], 200.0)
        np.testing.assert_allclose(
            controller.state.properties["xlim"],
            xlim,
        )
        np.testing.assert_allclose(
            controller.state.properties["ylim"],
            ylim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in common.editor("xlim").inputs
            ],
            xlim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in common.editor("ylim").inputs
            ],
            ylim,
        )

    def test_data_refresh_updates_only_the_affected_axes_inspector(self):
        line_pair, _valid_pair = self._set_source_data()
        first_axes = self.canvas.current_axes
        first_controller = self.canvas.current_axes_controller
        first_common = self.canvas.figure_inspector.axes_inspector(
            first_controller.component_id
        ).inspector(
            first_controller.component_id
        )
        first_limits = (
            tuple(first_axes.get_xlim()),
            tuple(first_axes.get_ylim()),
        )

        self.canvas.add_axes()
        second_axes = self.canvas.current_axes
        second_controller = self.canvas.current_axes_controller
        second_common = self.canvas.figure_inspector.axes_inspector(
            second_controller.component_id
        ).inspector(
            second_controller.component_id
        )
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "plot",
            self.x_ref,
            self.y_ref,
            object_id="second-axes-plot",
        )

        with self.window.repository.mutate(
            TableChangeSet(
                self.canvas.project_id,
                {self.x_ref, self.y_ref},
                reason="test-multi-axes-refresh",
            )
        ):
            self.sheet.set_block(
                0,
                0,
                [
                    [100.0, 1000.0],
                    [200.0, 2000.0],
                    [300.0, 3000.0],
                    [400.0, 4000.0],
                ],
            )
        self.app.processEvents()

        self.assertEqual(tuple(first_axes.get_xlim()), first_limits[0])
        self.assertEqual(tuple(first_axes.get_ylim()), first_limits[1])
        np.testing.assert_allclose(
            first_controller.state.properties["xlim"],
            first_limits[0],
        )
        np.testing.assert_allclose(
            first_controller.state.properties["ylim"],
            first_limits[1],
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in first_common.editor("xlim").inputs
            ],
            first_limits[0],
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in first_common.editor("ylim").inputs
            ],
            first_limits[1],
        )

        second_xlim = tuple(second_axes.get_xlim())
        second_ylim = tuple(second_axes.get_ylim())
        self.assertGreater(second_xlim[1], 400.0)
        self.assertGreater(second_ylim[1], 4000.0)
        np.testing.assert_allclose(
            second_controller.state.properties["xlim"],
            second_xlim,
        )
        np.testing.assert_allclose(
            second_controller.state.properties["ylim"],
            second_ylim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in second_common.editor("xlim").inputs
            ],
            second_xlim,
        )
        np.testing.assert_allclose(
            [
                value.value()
                for value in second_common.editor("ylim").inputs
            ],
            second_ylim,
        )

    def test_spine_feedback_fallback_and_explicit_presenter_are_deduplicated(self):
        events = []

        def handler(message, level):
            events.append((message, level))
            self.window.bottom_bar.show_message(message, level)

        status_messages.set_status_handler(handler)
        status_messages.show_warning("stale message")
        events.clear()

        result = self.canvas.axes_commands.set_spine_visible(
            self.canvas.current_axes_component_id,
            "bottom",
            False,
        )
        self.assertTrue(result.ok)
        self.app.processEvents()
        self.assertEqual(
            events,
            [("Bottom spine visibility updated.", "success")],
        )
        self.assertEqual(
            self.window.bottom_bar.message_bar.message_label.text(),
            "Bottom spine visibility updated.",
        )
        self.assertEqual(
            self.window.bottom_bar.message_bar.property("level"),
            "success",
        )

        events.clear()
        bottom_spine = self.canvas.component_registry.find_one(
            parent_id=self.canvas.current_axes_component_id,
            kind=ComponentKind.SPINE,
            selector={"name": "bottom"},
        )
        self.assertTrue(self.canvas.select_component(bottom_spine.component_id))
        bottom = self.canvas.component_editor_manager.editor(
            bottom_spine.component_id
        )
        bottom.editor("visible").setChecked(True)
        self.app.processEvents()
        self.assertEqual(
            events,
            [("Bottom spine visibility updated.", "success")],
        )

        schema_editor = self.canvas.create_component_editor(
            bottom_spine.component_id
        )
        try:
            events.clear()
            schema_editor.editor("visible").setChecked(False)
            self.app.processEvents()
            self.assertEqual(
                events,
                [("Bottom spine visibility updated.", "success")],
            )
        finally:
            schema_editor.close()

    def test_registry_color_query_and_palette_use_component_order(self):
        line_pair, valid_pair = self._set_source_data()
        self.canvas.add_curve(
            "x",
            0.0,
            3.0,
            "-",
            "#101010",
            "curve",
            color_order=8,
            object_id="ordered-curve",
        )
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#202020",
            "plot",
            self.x_ref,
            self.y_ref,
            color_order=2,
            object_id="ordered-plot",
        )
        self.canvas.add_scatter(
            valid_pair.x,
            valid_pair.y,
            20.0,
            "#303030",
            "o",
            "scatter",
            self.x_ref,
            self.y_ref,
            color_order=5,
            object_id="ordered-scatter",
        )
        self.canvas.add_component_line(
            [0.0, 1.0],
            [3.0, 4.0],
            color="#404040",
            label="generic",
            color_order=6,
            object_id="ordered-generic",
        )

        axes_id = self.canvas._axes_component_ids[self.canvas.current_axes]
        queried = self.canvas.component_registry.query(
            capabilities={"color", "data"},
            parent_id=axes_id,
            recursive=True,
        )
        self.assertEqual(
            [controller.component_id for controller in queried],
            [
                "ordered-plot",
                "ordered-scatter",
                "ordered-generic",
                "ordered-curve",
            ],
        )
        palette = PaletteDefinition(
            "test:runtime-order",
            "Runtime order",
            ("#AA0000", "#00AA00", "#0000AA", "#AAAA00"),
        )
        result = self.canvas.axes_commands.apply_palette(
            axes_id,
            palette,
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            [
                controller.read_state().properties["color"].casefold()
                for controller in queried
            ],
            ["#aa0000", "#00aa00", "#0000aa", "#aaaa00"],
        )

    def test_delete_cleans_registry_editor_artist_and_legend(self):
        line_pair, _valid_pair = self._set_source_data()
        object_id = "delete-plot"
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "delete me",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
        )
        line = self.canvas.component_registry.resolve_target(object_id)
        widget = self.canvas.component_editor_manager.editor(object_id)
        self.canvas.current_axes.legend()
        self.assertIsNotNone(self.canvas.current_axes.get_legend())

        widget.delete_object()

        self.assertNotIn(object_id, self.canvas.component_registry)
        self.assertNotIn(line, self.canvas.current_axes.lines)
        self.assertFalse(
            any(
                controller.component_id == object_id
                for controller in self.canvas.component_registry.query(
                    capabilities={"color", "data"}
                )
            )
        )
        self.assertIsNone(self.canvas.current_axes.get_legend())

    def test_registry_delete_removes_specialized_and_schema_editors(self):
        line_pair, _valid_pair = self._set_source_data()
        object_id = "delete-editor-plot"
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "delete editor",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
        )
        axes_inspector = self.canvas.figure_inspector.axes_inspector(
            self.canvas.current_axes_component_id
        )
        toolbox = axes_inspector.component_toolbox(
            (ComponentKind.LINE, ComponentRole.DATA_PLOT),
        )
        self.assertEqual(toolbox.count(), 1)

        schema_editor = self.canvas.create_component_editor(object_id)
        self.assertIs(
            schema_editor.editor("color").color_library,
            self.window.color_library,
        )
        change = self.canvas.component_registry.delete(object_id)

        self.assertTrue(change.ok)
        self.assertEqual(toolbox.count(), 0)
        self.assertFalse(schema_editor.isEnabled())
        self.assertNotIn(object_id, self.canvas.component_registry)

    def test_failed_interpolation_data_source_change_rolls_back_combo(self):
        self.sheet.set_block(
            0,
            0,
            [
                [0.0, 1.0, 5.0],
                [1.0, 2.0, 5.0],
                [2.0, 4.0, 5.0],
                [3.0, 8.0, 5.0],
            ],
        )
        bad_x_ref = ColumnRef(
            self.canvas.project_id,
            self.sheet.id,
            self.sheet.columns[2].id,
        )
        pair = self.window.repository.valid_pair(self.x_ref, self.y_ref)
        object_id = "rollback-interpolation-ref"
        self.canvas.add_interpolate_curve(
            pair.x,
            pair.y,
            self.x_ref,
            self.y_ref,
            list(interpolate_dict)[2],
            object_id=object_id,
        )
        widget = self.canvas.component_editor_manager.editor(object_id)
        controller = self.canvas.component_registry.get(object_id)
        data_section = widget.section("data")
        combo = data_section.data_choice_widget.x_data_input
        bad_index = next(
            index
            for index in range(combo.count())
            if combo.itemData(index) == bad_x_ref
        )

        combo.setCurrentIndex(bad_index)

        self.assertEqual(
            ColumnRef.from_dict(controller.state.data["x_ref"]),
            self.x_ref,
        )
        self.assertEqual(
            data_section.data_choice_widget.get_x_ref(),
            self.x_ref,
        )

    def test_plot_preprocessing_editor_applies_and_rolls_back_atomically(self):
        line_pair, _valid_pair = self._set_source_data()
        object_id = "preprocessing-editor-plot"
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "preprocessed",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
        )
        controller = self.canvas.component_registry.get(object_id)
        line = controller.resolve_target()
        widget = self.canvas.component_editor_manager.editor(object_id)
        data_section = widget.section("data")
        x_expression = data_section.data_choice_widget.x_expression_input

        x_expression.setText("1/x")
        self.assertTrue(data_section.x_expression_change())
        self.assertEqual(
            controller.state.data["preprocess"]["x_expression"],
            "1/x",
        )
        self.assertTrue(np.isnan(float(line.get_xdata()[0])))
        valid_x = np.asarray(line.get_xdata(), dtype=float)[1:]
        np.testing.assert_allclose(valid_x, [1.0, 0.5, 1.0 / 3.0])
        before_x = np.asarray(line.get_xdata()).copy()
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        try:
            x_expression.setText("__import__('os')")
            self.assertFalse(data_section.x_expression_change())
            self.assertEqual(x_expression.text(), "1/x")
            self.assertEqual(
                controller.state.data["preprocess"]["x_expression"],
                "1/x",
            )
            np.testing.assert_array_equal(line.get_xdata(), before_x)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][1], "error")
        finally:
            status_messages.clear_status_handler(handler)

    def test_failed_color_change_rolls_back_widget_and_success_is_green(self):
        line_pair, _valid_pair = self._set_source_data()
        object_id = "rollback-color-plot"
        self.canvas.add_plot(
            line_pair.x,
            line_pair.y,
            "-",
            2.0,
            "#123456",
            "color",
            self.x_ref,
            self.y_ref,
            object_id=object_id,
        )
        widget = self.canvas.component_editor_manager.editor(object_id)
        appearance = widget.section("appearance")
        controller = self.canvas.component_registry.get(object_id)
        line = self.canvas.component_registry.resolve_target(object_id)
        original_set_property = controller.set_property
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        try:
            controller.set_property = lambda _key, _value: SimpleNamespace(
                ok=False,
                message="rejected color",
            )
            color_choice = appearance.editor("color")
            color_choice.set_color("#ABCDEF", emit=True)
            self.assertEqual(
                color_choice.color().casefold(),
                "#123456",
            )
            self.assertEqual(
                line.get_color().casefold(),
                "#123456",
            )
            self.assertIn(("rejected color", "error"), events)

            controller.set_property = original_set_property
            events.clear()
            style_combo = appearance.editor("linestyle")
            style_combo.setCurrentIndex(
                style_combo.findData("--")
            )
            self.assertTrue(
                any(level == "success" for _message, level in events)
            )
        finally:
            controller.set_property = original_set_property
            status_messages.clear_status_handler(handler)

    def test_empty_data_components_survive_project_roundtrip(self):
        self.sheet.convert_column(self.x_ref.column_id, ColumnType.NUMBER)
        self.sheet.convert_column(self.y_ref.column_id, ColumnType.NUMBER)
        method = list(interpolate_dict)[2]
        object_ids = {
            "plot": "empty-plot",
            "scatter": "empty-scatter",
            "interpolation": "empty-interpolation",
            "fit": "empty-fit",
        }
        self.canvas.add_plot(
            np.asarray([]),
            np.asarray([]),
            "-",
            2.0,
            "#112233",
            "plot",
            self.x_ref,
            self.y_ref,
            object_id=object_ids["plot"],
        )
        self.canvas.add_scatter(
            np.asarray([]),
            np.asarray([]),
            20.0,
            "#223344",
            "o",
            "scatter",
            self.x_ref,
            self.y_ref,
            object_id=object_ids["scatter"],
        )
        self.canvas.add_interpolate_curve(
            np.asarray([]),
            np.asarray([]),
            self.x_ref,
            self.y_ref,
            method,
            color="#334455",
            object_id=object_ids["interpolation"],
            allow_empty=True,
        )
        self.canvas.add_fit_curve(
            np.asarray([]),
            np.asarray([]),
            "#445566",
            "fit",
            self.x_ref,
            self.y_ref,
            object_id=object_ids["fit"],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-components.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                self.assertEqual(
                    {
                        controller.component_id
                        for controller in restored.component_registry.query(
                            capabilities={"data_reference"}
                        )
                    },
                    set(object_ids.values()),
                )
                for component_id in object_ids.values():
                    self.assertIn(component_id, restored.component_registry)
                    target = restored.component_registry.resolve_target(component_id)
                    self.assertIsNotNone(target)
                    if component_id == object_ids["scatter"]:
                        self.assertEqual(target.get_offsets().shape, (0, 2))
                    else:
                        self.assertEqual(len(target.get_xdata()), 0)

                for role in (
                    ComponentRole.DATA_PLOT,
                    ComponentRole.SCATTER,
                    ComponentRole.INTERPOLATION,
                    ComponentRole.FIT_CURVE,
                ):
                    self.assertEqual(
                        len(
                            restored.component_registry.query(role=role)
                        ),
                        1,
                    )
                validate_v9_figure(
                    restored.component_snapshot(),
                    self._available_refs(restored),
                    restored.project_id,
                    restored.project_name,
                )
            finally:
                loaded.close()
                self.app.processEvents()

    def test_native_v6_ids_and_full_component_properties_roundtrip(self):
        self._add_all_runtime_components()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native-components.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            payload = json.loads(path.read_text(encoding="utf-8"))
            figure = payload["figure"]

            id_map = {
                component["id"]: f"native-component-{index:02d}"
                for index, component in enumerate(figure["components"])
            }
            figure["root_component_id"] = id_map[figure["root_component_id"]]
            for component in figure["components"]:
                old_id = component["id"]
                component["id"] = id_map[old_id]
                if component["parent_id"] is not None:
                    component["parent_id"] = id_map[component["parent_id"]]
                if component["selector"].get("object_id") == old_id:
                    component["selector"]["object_id"] = component["id"]

            def component(role, **selector):
                return next(
                    item
                    for item in figure["components"]
                    if item["role"] == role
                    and all(
                        item["selector"].get(key) == value
                        for key, value in selector.items()
                    )
                )

            component("figure")["properties"]["facecolor"] = "#102030"
            axes = component("axes")
            axes["properties"].update(
                xlim=[-2.0, 5.0],
                ylim=[-3.0, 10.0],
                facecolor="#203040",
            )
            component("spine", name="left")["properties"].update(
                color="#304050",
                linewidth=2.5,
                linestyle="--",
                alpha=0.7,
            )
            component("major_tick", axis="x", level="major")[
                "properties"
            ].update(
                direction="inout",
                length=9.0,
                width=2.0,
                color="#405060",
                pad=6.0,
            )
            component(
                "major_tick_label", axis="x", level="major"
            )["properties"].update(
                color="#506070",
                fontsize=13.0,
                rotation=25.0,
                pad=6.0,
            )
            component("grid", axis="x", level="major")[
                "properties"
            ].update(
                visible=True,
                color="#607080",
                linestyle=":",
                linewidth=1.7,
                alpha=0.6,
            )
            component("title")["properties"].update(
                text="Native title",
                color="#708090",
                fontsize=17.0,
                rotation=3.0,
            )
            component("x_label")["properties"].update(
                text="Native X",
                color="#8090A0",
                fontsize=14.0,
            )
            plot = component("data_plot")
            plot["data"]["preprocess"] = {
                "x_expression": "1/(x+1)",
                "y_expression": "y",
            }
            plot["properties"].update(
                linewidth=4.25,
                marker="s",
                markerfacecolor="#90A0B0",
                markeredgecolor="#A0B0C0",
                markeredgewidth=1.75,
                alpha=0.55,
                zorder=9.0,
            )
            scatter = component("scatter")
            scatter["properties"].update(
                edgecolor="#B0C0D0",
                size=73.0,
                marker="^",
                linewidth=2.25,
                alpha=0.65,
                zorder=8.0,
            )
            component("text", scope="axes")["properties"].update(
                color="#C0D0E0",
                rotation=31.0,
                horizontalalignment="right",
            )
            component("legend")["properties"].update(
                visible=True,
                location="upper left",
                ncols=2,
                fontsize=11.0,
                facecolor="#D0E0F0",
                edgecolor="#102030",
                framealpha=0.75,
                title="Native legend",
            )
            validate_v9_figure(
                figure,
                self._available_refs(),
                self.canvas.project_id,
                self.canvas.project_name,
            )
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                restored_figure = restored.component_snapshot()
                self.assertEqual(
                    restored_figure["root_component_id"],
                    figure["root_component_id"],
                )
                self.assertEqual(
                    {item["id"] for item in restored_figure["components"]},
                    {item["id"] for item in figure["components"]},
                )
                restored_by_id = {
                    item["id"]: item
                    for item in restored_figure["components"]
                }
                self.assertEqual(
                    restored_by_id[plot["id"]]["data"]["preprocess"],
                    plot["data"]["preprocess"],
                )
                restored_plot = restored.component_registry.resolve_target(
                    plot["id"]
                )
                np.testing.assert_allclose(
                    np.asarray(restored_plot.get_xdata(), dtype=float),
                    [1.0, 0.5, 1.0 / 3.0, 0.25],
                )
                restored_axes_controller = (
                    restored.component_registry.get(axes["id"])
                )
                restored_axes = restored_axes_controller.resolve_target()
                restored_common = restored.figure_inspector.axes_inspector(
                    restored_axes_controller.component_id
                ).inspector(
                    restored_axes_controller.component_id
                )
                np.testing.assert_allclose(
                    restored_axes_controller.state.properties["xlim"],
                    axes["properties"]["xlim"],
                )
                np.testing.assert_allclose(
                    restored_axes_controller.state.properties["ylim"],
                    axes["properties"]["ylim"],
                )
                np.testing.assert_allclose(
                    restored_axes.get_xlim(),
                    axes["properties"]["xlim"],
                )
                np.testing.assert_allclose(
                    restored_axes.get_ylim(),
                    axes["properties"]["ylim"],
                )
                np.testing.assert_allclose(
                    [
                        value.value()
                        for value in restored_common.editor("xlim").inputs
                    ],
                    axes["properties"]["xlim"],
                )
                np.testing.assert_allclose(
                    [
                        value.value()
                        for value in restored_common.editor("ylim").inputs
                    ],
                    axes["properties"]["ylim"],
                )
                for source, keys in (
                    (axes, ("xlim", "ylim", "facecolor")),
                    (
                        plot,
                        (
                            "linewidth",
                            "marker",
                            "markerfacecolor",
                            "markeredgecolor",
                            "markeredgewidth",
                            "alpha",
                            "zorder",
                        ),
                    ),
                    (
                        scatter,
                        (
                            "edgecolor",
                            "size",
                            "marker",
                            "linewidth",
                            "alpha",
                            "zorder",
                        ),
                    ),
                    (
                        component("legend"),
                        (
                            "visible",
                            "location",
                            "ncols",
                            "fontsize",
                            "facecolor",
                            "edgecolor",
                            "framealpha",
                            "title",
                        ),
                    ),
                ):
                    restored_properties = restored_by_id[source["id"]][
                        "properties"
                    ]
                    for key in keys:
                        self.assertEqual(
                            restored_properties[key],
                            source["properties"][key],
                            (source["role"], key),
                        )
            finally:
                loaded.close()
                self.app.processEvents()

    def test_generic_line_component_restores_without_a_specialized_panel(self):
        component_id = "generic-line-runtime"
        self.canvas.add_component_line(
            [0.0, 1.0, 2.0],
            [2.0, -1.0, 3.0],
            style="--",
            color="#123456",
            label="generic",
            object_id=component_id,
            color_order=4,
        )
        controller = self.canvas.component_registry.get(component_id)
        self.assertTrue(controller.set_property("linewidth", 3.5).ok)
        self.assertTrue(controller.set_property("marker", "D").ok)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generic-line.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                restored_controller = restored.component_registry.get(
                    component_id
                )
                self.assertIs(
                    restored_controller.state.role,
                    ComponentRole.LINE,
                )
                line = restored_controller.resolve_target()
                np.testing.assert_allclose(
                    line.get_xdata(),
                    [0.0, 1.0, 2.0],
                )
                np.testing.assert_allclose(
                    line.get_ydata(),
                    [2.0, -1.0, 3.0],
                )
                self.assertEqual(line.get_linestyle(), "--")
                self.assertEqual(line.get_marker(), "D")
                self.assertEqual(line.get_linewidth(), 3.5)
            finally:
                loaded.close()
                self.app.processEvents()

    def test_figure_controller_updates_host_name_dpi_and_canvas_size(self):
        controller = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )

        self.assertTrue(
            controller.set_property("size_inches", (5.0, 4.0)).ok
        )
        self.assertTrue(controller.set_property("dpi", 120.0).ok)
        metadata_events = []
        self.window.repository.transaction_committed.connect(
            metadata_events.append
        )
        self.assertTrue(
            controller.set_property("name", "RenamedRuntime").ok
        )

        self.assertEqual(self.canvas.document_dpi, 120.0)
        self.assertEqual(self.canvas.canva.width(), 600)
        self.assertEqual(self.canvas.canva.height(), 480)
        self.assertEqual(self.canvas.project_name, "RenamedRuntime")
        self.assertEqual(
            self.window.repository.project(self.canvas.project_id).name,
            "RenamedRuntime",
        )
        self.assertEqual(len(metadata_events), 1)
        self.assertEqual(metadata_events[0].reason, "rename-project")
        self.assertEqual(
            self.window.figure_window.tabwindow.tabText(
                self.window.figure_window.tabwindow.indexOf(self.canvas)
            ),
            "RenamedRuntime",
        )

    def test_project_rename_failure_restores_repository_root_and_tab(self):
        project_id = self.canvas.project_id
        controller = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        before_state = controller.state
        before_name = self.canvas.project_name
        index = self.window.figure_window.tabwindow.indexOf(self.canvas)
        before_tab = self.window.figure_window.tabwindow.tabText(index)
        events = []
        self.window.repository.transaction_committed.connect(events.append)

        with mock.patch.object(
            self.window.figure_window.tabwindow,
            "setTabText",
            side_effect=RuntimeError("injected Tab rename failure"),
        ):
            with self.assertRaisesRegex(ValueError, "Tab rename"):
                self.window.figure_window.rename_project(
                    project_id,
                    "RejectedRename",
                )

        self.assertEqual(controller.state, before_state)
        self.assertEqual(self.canvas.project_name, before_name)
        self.assertEqual(
            self.window.repository.project(project_id).name,
            before_name,
        )
        self.assertEqual(
            self.window.figure_window.tabwindow.tabText(index),
            before_tab,
        )
        self.assertEqual(events, [])

    def test_project_id_name_collision_never_changes_internal_routing(self):
        first_id = self.canvas.project_id
        self.window.figure_window.add_figure(
            width=4,
            height=3,
            dpi=100,
            style="default",
            canva_name=first_id,
        )
        second = self.window.figure_window.current_canva
        self.assertNotEqual(second.project_id, first_id)
        self.assertEqual(second.project_name, first_id)

        self.window.table.switch_to_table(first_id)

        self.assertEqual(self.window.table.current_project_id, first_id)
        self.assertIs(
            self.window.table.current_subtable(),
            self.window.table._subtables[first_id],
        )

    def test_refresh_reference_failure_is_one_structured_warning(self):
        self._set_source_data()
        pair = self.window.repository.line_pair(self.x_ref, self.y_ref)
        self.canvas.add_plot(
            pair.x,
            pair.y,
            "-",
            2.0,
            "#123456",
            "observer",
            self.x_ref,
            self.y_ref,
            object_id="observer-refresh",
        )
        messages = []
        status_messages.set_status_handler(
            lambda text, level: messages.append((text, level))
        )
        with mock.patch.object(
            self.canvas.chart_data_service,
            "refs_for",
            side_effect=ValueError("injected bad reference"),
        ):
            with self.window.repository.mutate(
                TableChangeSet(
                    self.canvas.project_id,
                    changed_columns={self.x_ref},
                    reason="observer-failure",
                )
            ):
                self.sheet.set_cell(0, self.x_ref.column_id, 42.0)

        self.app.processEvents()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0][1], "warning")
        self.assertIn("ChartDataService data-reference", messages[0][0])

    def test_invalid_interpolation_source_restores_as_empty_component(self):
        self.sheet.set_block(0, 0, [[1.0, 2.0]])
        component_id = "one-point-interpolation"
        method = next(iter(interpolate_dict))
        line = self.canvas.add_interpolate_curve(
            np.asarray([1.0]),
            np.asarray([2.0]),
            self.x_ref,
            self.y_ref,
            method,
            object_id=component_id,
            allow_empty=True,
        )
        self.assertIsNotNone(line)
        self.assertEqual(len(line.get_xdata()), 0)
        self.assertIn(component_id, self.canvas.component_registry)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-interpolation.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored = loaded.figure_window.current_canva
                controller = restored.component_registry.get(component_id)
                self.assertEqual(
                    len(controller.resolve_target().get_xdata()),
                    0,
                )
            finally:
                loaded.close()
                self.app.processEvents()

    def test_new_axes_uses_a_distinct_persisted_layout_id(self):
        first = next(
            controller
            for controller in self.canvas.component_registry.query(
                kind=ComponentKind.AXES
            )
            if controller.state.selector["index"] == 0
        )
        first_layout_id = first.state.data["subplot"]["layout_id"]

        self.canvas.add_axes()

        second = next(
            controller
            for controller in self.canvas.component_registry.query(
                kind=ComponentKind.AXES
            )
            if controller.state.selector["index"] == 1
        )
        second_layout_id = second.state.data["subplot"]["layout_id"]
        self.assertNotEqual(second_layout_id, first_layout_id)
        figure = self.canvas.component_registry.get(self.canvas.root_component_id)
        self.assertEqual(
            {item["id"] for item in figure.state.data["layouts"]},
            {first_layout_id, second_layout_id},
        )
        validate_v9_figure(
            self.canvas.component_snapshot(),
            self._available_refs(),
            self.canvas.project_id,
            self.canvas.project_name,
        )


if __name__ == "__main__":
    unittest.main()
