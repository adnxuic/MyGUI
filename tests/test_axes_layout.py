import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from matplotlib import ticker

from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import (
    AxesCellSpec,
    AxesLayoutSpec,
    AxesViewSpec,
    ShareMode,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentValidationError,
)
from mygui.figuremodify.components.serialization import (
    validate_v15_figure,
)
from mygui.project_io import (
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
)
from mygui.widgets.title_bar.titlebar_dialog.axes_layout_input import (
    AxesLayoutInput,
    axes_layout_presets,
)
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
    PyLayoutDialog,
)
from mygui.widgets.fig_control_window.component_editors.sections import (
    AxesLimitsSection,
)
from main import MainWindow


class AxesLayoutIntegrationTests(unittest.TestCase):
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
            canva_name="AxesLayout",
        )
        self.canvas = self.window.figure_window.current_canva

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _available_refs(self, canvas=None):
        canvas = canvas or self.canvas
        project = canvas.repository.project(canvas.project_id)
        return {
            ColumnRef(project.id, sheet.id, column.id): column.type
            for sheet in project.sheets.values()
            for column in sheet.columns
        }

    def test_shared_x_creation_edit_and_roundtrip(self):
        view = AxesViewSpec(xlim=(1.0, 10.0), xscale="log")
        spec = AxesLayoutSpec(
            2,
            1,
            (
                AxesCellSpec(0, 0, primary=view),
                AxesCellSpec(1, 0, primary=view),
            ),
            height_ratios=(3.0, 1.0),
            share_x=ShareMode.ALL,
            outer_x_labels=True,
        )
        ids = self.canvas.create_axes_layout(spec)
        self.assertEqual(len(ids), 2)
        controllers = [self.canvas.component_registry.get(item) for item in ids]
        first, second = (item.resolve_target() for item in controllers)
        self.assertTrue(first.get_shared_x_axes().joined(first, second))
        self.assertEqual(
            controllers[0].state.data["subplot"]["share_x_group"],
            controllers[1].state.data["subplot"]["share_x_group"],
        )

        result = self.canvas.axes_layout_service.apply_linked_axis(
            ids[0],
            "x",
            limits=(2.0, 20.0),
            autoscale=False,
        )
        self.assertTrue(result.ok)
        for controller in controllers:
            state = controller.read_state()
            self.assertEqual(tuple(state.properties["xlim"]), (2.0, 20.0))
            self.assertFalse(state.properties["autoscalex_on"])

        snapshot = self.canvas.component_snapshot()
        validate_v15_figure(
            snapshot,
            self._available_refs(),
            self.canvas.project_id,
            self.canvas.project_name,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared-x.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            restored = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    restored.table,
                    restored.figure_window,
                )
                canvas = restored.figure_window.current_canva
                restored_axes = sorted(
                    canvas.component_registry.query(kind=ComponentKind.AXES),
                    key=lambda item: item.state.selector["index"],
                )
                left, right = (item.resolve_target() for item in restored_axes)
                self.assertTrue(left.get_shared_x_axes().joined(left, right))
                self.assertEqual(tuple(left.get_xlim()), (2.0, 20.0))
            finally:
                restored.close()
                self.app.processEvents()

    def test_shared_axes_reenable_autoscale_and_sync_limits(self):
        ids = self.canvas.create_axes_layout(
            AxesLayoutSpec(
                2,
                1,
                (
                    AxesCellSpec(0, 0),
                    AxesCellSpec(1, 0),
                ),
                share_x=ShareMode.ALL,
            )
        )
        controllers = [self.canvas.component_registry.get(item) for item in ids]
        for controller in controllers:
            controller.resolve_target().plot([0.0, 20.0], [0.0, 1.0])
        disabled = self.canvas.axes_layout_service.apply_linked_axis(
            ids[0],
            "x",
            limits=(0.0, 10.0),
            autoscale=False,
        )
        self.assertTrue(disabled.ok)

        enabled = self.canvas.axes_layout_service.apply_linked_axis(
            ids[0],
            "x",
            autoscale=True,
        )

        self.assertTrue(enabled.ok)
        for controller in controllers:
            target = controller.resolve_target()
            self.assertTrue(controller.state.properties["autoscalex_on"])
            self.assertAlmostEqual(target.get_xlim()[0], -1.0)
            self.assertAlmostEqual(target.get_xlim()[1], 21.0)
            self.assertEqual(
                tuple(controller.state.properties["xlim"]),
                tuple(target.get_xlim()),
            )

    def test_minor_visibility_service_enables_locator_and_preserves_custom_one(self):
        axes_id, = create_regular_axes(self.canvas)
        axes = self.canvas.component_registry.resolve_target(axes_id)
        x_axis = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
        )
        y_axis = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.Y_AXIS,
        )

        def minor(kind):
            return self.canvas.component_registry.find_one(
                parent_id=(
                    x_axis.component_id
                    if kind is not ComponentKind.TICK_LABEL_GROUP
                    else tick.component_id
                ),
                kind=kind,
                selector={"axis": "x", "level": "minor"},
                recursive=False,
            )

        grid = minor(ComponentKind.GRID)
        tick = minor(ComponentKind.TICK_GROUP)
        label = minor(ComponentKind.TICK_LABEL_GROUP)

        result = self.canvas.axes_layout_service.apply_minor_component_properties(
            grid,
            {"visible": True},
        )
        self.assertTrue(result.ok)
        self.assertEqual(x_axis.state.properties["minor_locator"]["kind"], "auto_minor")
        self.assertEqual(y_axis.state.properties["minor_locator"]["kind"], "null")
        self.assertTrue(grid.state.properties["visible"])
        self.assertTrue(axes.xaxis.get_minor_ticks())
        self.assertTrue(
            all(tick.gridline.get_visible() for tick in axes.xaxis.get_minor_ticks())
        )

        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                grid,
                {"visible": False},
            ).ok
        )
        self.assertEqual(x_axis.state.properties["minor_locator"]["kind"], "auto_minor")
        self.assertTrue(x_axis.set_property("minor_locator", {"kind": "null", "params": {}}).ok)
        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                tick,
                {"secondary_visible": True},
            ).ok
        )
        self.assertTrue(any(item.tick2line.get_visible() for item in axes.xaxis.get_minor_ticks()))

        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                tick,
                {"secondary_visible": False},
            ).ok
        )
        self.assertTrue(x_axis.set_property("minor_locator", {"kind": "null", "params": {}}).ok)
        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                label,
                {"secondary_visible": True},
            ).ok
        )
        self.assertTrue(any(item.label2.get_visible() for item in axes.xaxis.get_minor_ticks()))

        custom = {
            "kind": "fixed",
            "params": {"locations": [0.25, 0.75], "nbins": None},
        }
        self.assertTrue(x_axis.set_property("minor_locator", custom).ok)
        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                grid,
                {"visible": True},
            ).ok
        )
        self.assertEqual(x_axis.state.properties["minor_locator"], custom)

        y_grid = self.canvas.component_registry.find_one(
            parent_id=y_axis.component_id,
            kind=ComponentKind.GRID,
            selector={"axis": "y", "level": "minor"},
        )
        self.assertTrue(
            self.canvas.axes_layout_service.apply_minor_component_properties(
                y_grid,
                {"visible": True},
            ).ok
        )
        self.assertEqual(y_axis.state.properties["minor_locator"]["kind"], "auto_minor")
        self.assertTrue(any(item.gridline.get_visible() for item in axes.yaxis.get_minor_ticks()))

    def test_minor_visibility_transaction_rolls_back_locator_and_tick_state(self):
        axes_id, = create_regular_axes(self.canvas)
        axes = self.canvas.component_registry.resolve_target(axes_id)
        axis = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
        )
        grid = self.canvas.component_registry.find_one(
            parent_id=axis.component_id,
            kind=ComponentKind.GRID,
            selector={"axis": "x", "level": "minor"},
        )
        original_write = grid._write_property
        failed = False

        def fail_once(target, spec, value):
            nonlocal failed
            if spec.key == "visible" and value is True and not failed:
                failed = True
                raise RuntimeError("injected minor visibility failure")
            return original_write(target, spec, value)

        with mock.patch.object(grid, "_write_property", side_effect=fail_once):
            result = self.canvas.axes_layout_service.apply_minor_component_properties(
                grid,
                {"visible": True},
            )

        self.assertFalse(result.ok)
        self.assertIn("injected minor visibility failure", result.message)
        self.assertEqual(axis.state.properties["minor_locator"]["kind"], "null")
        self.assertFalse(grid.state.properties["visible"])
        self.assertFalse(axes.xaxis._minor_tick_kw["gridOn"])
        self.assertEqual(axes.xaxis.get_minor_ticks(), [])

    def test_minor_grid_creation_state_and_save_open_save_are_consistent(self):
        spec = AxesLayoutSpec(
            1,
            1,
            (
                AxesCellSpec(
                    0,
                    0,
                    primary=AxesViewSpec(x_minor_grid=True),
                ),
            ),
        )
        axes_id, = self.canvas.create_axes_layout(spec)
        axis = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
        )
        grid = self.canvas.component_registry.find_one(
            parent_id=axis.component_id,
            kind=ComponentKind.GRID,
            selector={"axis": "x", "level": "minor"},
        )
        snapshot = self.canvas.component_snapshot()
        saved_axis = next(item for item in snapshot["components"] if item["id"] == axis.component_id)
        saved_grid = next(item for item in snapshot["components"] if item["id"] == grid.component_id)
        self.assertEqual(axis.state.properties["minor_locator"]["kind"], "auto_minor")
        self.assertTrue(grid.state.properties["visible"])
        self.assertEqual(saved_axis["properties"], axis.state.properties)
        self.assertEqual(
            saved_grid["properties"]["visible"],
            grid.state.properties["visible"],
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "minor-grid.mygui.json"
            second_path = Path(directory) / "minor-grid-resaved.mygui.json"
            save_project_snapshot(first_path, self.window.figure_window)
            restored = MainWindow()
            try:
                restore_project_snapshot(first_path, restored.table, restored.figure_window)
                canvas = restored.figure_window.current_canva
                restored_axis = canvas.component_registry.get(axis.component_id)
                restored_grid = canvas.component_registry.get(grid.component_id)
                restored_axes = canvas.component_registry.resolve_target(axes_id)
                self.assertEqual(restored_axis.state.properties["minor_locator"]["kind"], "auto_minor")
                self.assertTrue(restored_grid.state.properties["visible"])
                self.assertTrue(
                    any(item.gridline.get_visible() for item in restored_axes.xaxis.get_minor_ticks())
                )
                save_project_snapshot(second_path, restored.figure_window)
                second = load_project_file(second_path)
                second_axis = next(
                    item for item in second["figure"]["components"]
                    if item["id"] == axis.component_id
                )
                second_grid = next(
                    item for item in second["figure"]["components"]
                    if item["id"] == grid.component_id
                )
                self.assertEqual(second_axis["properties"]["minor_locator"], restored_axis.state.properties["minor_locator"])
                self.assertTrue(second_grid["properties"]["visible"])
            finally:
                restored.close()
                self.app.processEvents()

    def test_legacy_minor_grid_is_repaired_but_default_primary_intent_is_not(self):
        axes_id, = create_regular_axes(self.canvas)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-minor-grid.mygui.json"
            snapshot = save_project_snapshot(path, self.window.figure_window)
            components = snapshot["figure"]["components"]
            axis = next(
                item for item in components
                if item["parent_id"] == axes_id
                and item["role"] == ComponentRole.X_AXIS.value
            )
            grid = next(
                item for item in components
                if item["parent_id"] == axis["id"]
                and item["kind"] == ComponentKind.GRID.value
                and item["selector"].get("level") == "minor"
            )
            grid["properties"]["visible"] = True
            axis["properties"]["minor_locator"] = {"kind": "null", "params": {}}
            path.write_text(json.dumps(snapshot), encoding="utf-8")

            restored = MainWindow()
            try:
                restore_project_snapshot(path, restored.table, restored.figure_window)
                canvas = restored.figure_window.current_canva
                repaired_axis = canvas.component_registry.get(axis["id"])
                repaired_grid = canvas.component_registry.get(grid["id"])
                axes = canvas.component_registry.resolve_target(axes_id)
                self.assertNotEqual(repaired_axis.state.properties["minor_locator"]["kind"], "null")
                self.assertTrue(repaired_grid.state.properties["visible"])
                self.assertTrue(any(item.gridline.get_visible() for item in axes.xaxis.get_minor_ticks()))
                self.assertFalse(restored.figure_window.is_canvas_dirty(canvas))
            finally:
                restored.close()
                self.app.processEvents()

        states = tuple(self.canvas.component_registry.states())
        unchanged = self.canvas.axes_layout_service.repair_legacy_minor_locator_states(states)
        default_axis = next(state for state in unchanged if state.id == axis["id"])
        self.assertEqual(default_axis.properties["minor_locator"]["kind"], "null")

    def test_legacy_secondary_minor_intent_repairs_locator(self):
        axes_id, = create_regular_axes(self.canvas)
        states = tuple(self.canvas.component_registry.states())
        axis = next(
            state for state in states
            if state.parent_id == axes_id and state.role is ComponentRole.X_AXIS
        )
        tick = next(
            state for state in states
            if state.parent_id == axis.id
            and state.kind is ComponentKind.TICK_GROUP
            and state.selector.get("level") == "minor"
        )
        label = next(
            state for state in states
            if state.parent_id == tick.id
            and state.kind is ComponentKind.TICK_LABEL_GROUP
        )
        for intended in (tick, label):
            with self.subTest(kind=intended.kind.value):
                properties = dict(intended.properties)
                properties["secondary_visible"] = True
                source = tuple(
                    state.clone(properties=properties)
                    if state.id == intended.id
                    else state
                    for state in states
                )
                repaired = (
                    self.canvas.axes_layout_service.repair_legacy_minor_locator_states(
                        source
                    )
                )
                repaired_axis = next(state for state in repaired if state.id == axis.id)
                self.assertNotEqual(
                    repaired_axis.properties["minor_locator"]["kind"],
                    "null",
                )

    def test_twin_legend_and_directional_delete_contract(self):
        ids = self.canvas.create_axes_layout(
            AxesLayoutSpec(
                1,
                1,
                (
                    AxesCellSpec(
                        0,
                        0,
                        right_y=AxesViewSpec(yscale="log"),
                        merge_legend=True,
                    ),
                ),
            )
        )
        primary_id, secondary_id = ids
        primary = self.canvas.component_registry.get(primary_id).resolve_target()
        secondary = self.canvas.component_registry.get(secondary_id).resolve_target()
        primary.plot([0, 1], [1, 2], label="left")
        secondary.plot([0, 1], [2, 4], label="right")
        _controller, legend = self.canvas.axes_commands.ensure_legend(primary_id)
        self.assertEqual(
            [text.get_text() for text in legend.get_texts()],
            ["left", "right"],
        )

        self.assertTrue(self.canvas.delete_axes(secondary_id))
        self.assertIn(primary_id, self.canvas.component_registry)
        self.assertNotIn(secondary_id, self.canvas.component_registry)
        legend_controller = self.canvas.component_registry.find_one(
            parent_id=primary_id,
            kind=ComponentKind.LEGEND,
            role=ComponentRole.LEGEND,
            recursive=False,
        )
        self.assertEqual(legend_controller.state.properties["entry_scope"], "axes")
        validate_v15_figure(
            self.canvas.component_snapshot(),
            self._available_refs(),
            self.canvas.project_id,
            self.canvas.project_name,
        )

        new_primary, new_secondary = self.canvas.create_axes_layout(
            AxesLayoutSpec(
                1,
                1,
                (AxesCellSpec(0, 0, right_y=AxesViewSpec()),),
            )
        )
        self.assertTrue(self.canvas.delete_axes(new_primary))
        self.assertNotIn(new_primary, self.canvas.component_registry)
        self.assertNotIn(new_secondary, self.canvas.component_registry)

    def test_fixed_layout_presets_have_expected_structure(self):
        expected = {
            "single": (1, 1, 1, ShareMode.NONE, ShareMode.NONE, False),
            "horizontal_compare": (1, 2, 2, ShareMode.NONE, ShareMode.ALL, False),
            "vertical_stack": (2, 1, 2, ShareMode.ALL, ShareMode.NONE, False),
            "grid_2x2": (2, 2, 4, ShareMode.NONE, ShareMode.NONE, False),
            "grid_3x3": (3, 3, 9, ShareMode.NONE, ShareMode.NONE, False),
            "primary_right_y": (1, 1, 1, ShareMode.NONE, ShareMode.NONE, True),
            "main_residual": (2, 1, 2, ShareMode.ALL, ShareMode.NONE, False),
        }
        self.assertEqual(
            tuple(item.key for item in axes_layout_presets()),
            tuple(expected),
        )
        inputs = []
        try:
            for preset_key, values in expected.items():
                layout_input = AxesLayoutInput(
                    color_library=self.window.figure_window.color_library,
                    preset_key=preset_key,
                )
                inputs.append(layout_input)
                spec = layout_input.spec()
                rows, columns, count, share_x, share_y, right_y = values
                self.assertEqual((spec.nrows, spec.ncols), (rows, columns))
                self.assertEqual(len(spec.cells), count)
                self.assertEqual(spec.share_x, share_x)
                self.assertEqual(spec.share_y, share_y)
                self.assertEqual(
                    any(cell.right_y is not None for cell in spec.cells),
                    right_y,
                )
                self.assertEqual(
                    hasattr(layout_input, "right_auto_y_input"),
                    right_y,
                )
                self.assertFalse(hasattr(layout_input, "preset_input"))
                self.assertFalse(hasattr(layout_input, "rows_input"))
                self.assertFalse(hasattr(layout_input, "columns_input"))
                self.assertFalse(hasattr(layout_input, "cell_inputs"))
                self.assertFalse(hasattr(layout_input, "share_x_input"))
                self.assertFalse(hasattr(layout_input, "share_y_input"))

            residual = inputs[-1].spec()
            self.assertEqual(residual.height_ratios, (3.0, 1.0))
            self.assertTrue(residual.outer_x_labels)
            self.assertIsNone(inputs[3].share_toggle_input)
            self.assertIsNone(inputs[4].share_toggle_input)
        finally:
            for layout_input in inputs:
                layout_input.deleteLater()

    def test_comparison_share_toggles_update_relationship_and_labels(self):
        horizontal = AxesLayoutInput(
            color_library=self.window.figure_window.color_library,
            preset_key="horizontal_compare",
        )
        vertical = AxesLayoutInput(
            color_library=self.window.figure_window.color_library,
            preset_key="vertical_stack",
        )
        try:
            self.assertTrue(horizontal.share_toggle_input.isChecked())
            self.assertEqual(horizontal.spec().share_y, ShareMode.ALL)
            self.assertTrue(horizontal.spec().outer_y_labels)
            horizontal.share_toggle_input.setChecked(False)
            self.assertEqual(horizontal.spec().share_y, ShareMode.NONE)
            self.assertFalse(horizontal.spec().outer_y_labels)
            self.assertIn("independent Axes", horizontal.summary_label.text())
            horizontal.share_toggle_input.setChecked(True)
            self.assertEqual(horizontal.spec().share_y, ShareMode.ALL)
            self.assertTrue(horizontal.spec().outer_y_labels)

            self.assertTrue(vertical.share_toggle_input.isChecked())
            self.assertEqual(vertical.spec().share_x, ShareMode.ALL)
            self.assertTrue(vertical.spec().outer_x_labels)
            vertical.share_toggle_input.setChecked(False)
            self.assertEqual(vertical.spec().share_x, ShareMode.NONE)
            self.assertFalse(vertical.spec().outer_x_labels)
            self.assertIn("independent Axes", vertical.summary_label.text())
        finally:
            horizontal.deleteLater()
            vertical.deleteLater()

    def test_layout_dialog_disables_submission_for_invalid_geometry(self):
        dialog = PyLayoutDialog(
            figure_window=self.window.figure_window,
            preset_key="single",
        )
        try:
            self.assertTrue(dialog.ok_button.isEnabled())
            dialog.input.width_ratios_input.setText("1, 1")
            self.app.processEvents()
            self.assertFalse(dialog.ok_button.isEnabled())
            self.assertTrue(dialog.input.validation_label.isVisibleTo(dialog.input))

            dialog.input.width_ratios_input.setText("1")
            self.app.processEvents()
            self.assertTrue(dialog.ok_button.isEnabled())
            self.assertFalse(dialog.input.validation_label.isVisibleTo(dialog.input))
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_layout_input_safe_geometry_edit(self):
        layout_input = AxesLayoutInput(
            color_library=self.window.figure_window.color_library,
            preset_key="main_residual",
        )
        spec = layout_input.spec()
        self.assertEqual((spec.nrows, spec.ncols), (2, 1))
        self.assertEqual(spec.height_ratios, (3.0, 1.0))
        self.assertEqual(spec.share_x, ShareMode.ALL)
        self.assertTrue(spec.outer_x_labels)

        ids = self.canvas.create_axes_layout(spec)
        targets = {
            component_id: self.canvas.component_registry.resolve_target(component_id)
            for component_id in ids
        }
        layout_id = self.canvas.component_registry.get(ids[0]).state.data[
            "subplot"
        ]["layout_id"]
        definition = self.canvas.axes_layout_service.layout_definition(layout_id)
        editor = AxesLayoutInput(
            color_library=self.window.figure_window.color_library,
            preset_key=None,
            edit_definition=definition,
            occupied_cells={(0, 0), (1, 0)},
            relationship_summary="2 × 1 · 2 primary Axes · shared X",
        )
        self.assertIsNone(editor.tabs)
        self.assertFalse(hasattr(editor, "auto_x_input"))
        icon_label = editor.findChild(QLabel, "layout_template_icon")
        self.assertIsNotNone(icon_label)
        icon_image = icon_label.pixmap().toImage()
        visible_colors = [
            icon_image.pixelColor(x, y)
            for y in range(icon_image.height())
            for x in range(icon_image.width())
            if icon_image.pixelColor(x, y).alpha() > 0
        ]
        self.assertTrue(visible_colors)
        self.assertTrue(any(color.lightness() < 245 for color in visible_colors))
        editor.height_ratios_input.setText("4, 1")
        editor.left_input.setValue(0.2)
        editor.right_input.setValue(0.85)
        editor.bottom_input.setValue(0.15)
        editor.top_input.setValue(0.9)
        editor.hspace_input.setValue(0.1)
        edited = editor.spec()
        self.assertEqual(edited.layout_id, layout_id)
        self.assertEqual(set(self.canvas.update_axes_layout(edited)), set(ids))
        for component_id, target in targets.items():
            self.assertIs(
                self.canvas.component_registry.resolve_target(component_id),
                target,
            )
        self.assertEqual(
            self.canvas.axes_layout_service.layout_definition(layout_id)[
                "height_ratios"
            ],
            [4.0, 1.0],
        )
        for component_id in ids:
            self.assertTrue(
                self.canvas.component_registry.get(component_id).state.data[
                    "subplot"
                ]["share_x_group"]
            )
        layout_input.deleteLater()
        editor.deleteLater()

    def test_creation_failure_rolls_back_root_axes_and_allocated_ids(self):
        before_ids = set(self.canvas._allocated_component_ids)
        before_grids = dict(self.canvas.axes_layout_service._grids)
        original = self.canvas._register_axes_components
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected registration failure")
            return original(*args, **kwargs)

        with mock.patch.object(
            self.canvas,
            "_register_axes_components",
            side_effect=fail_second,
        ):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.canvas.create_axes_layout(AxesLayoutSpec.grid(2, 1))

        self.assertEqual(self.canvas.fig.axes, [])
        self.assertEqual(
            self.canvas.component_registry.get(
                self.canvas.root_component_id
            ).state.data,
            {"layouts": []},
        )
        self.assertEqual(self.canvas._allocated_component_ids, before_ids)
        self.assertEqual(self.canvas.axes_layout_service._grids, before_grids)
        self.assertEqual(len(self.canvas.component_registry), 1)

    def test_semantic_sync_failure_rolls_back_complete_axes_subtree(self):
        before_ids = set(self.canvas._allocated_component_ids)
        before_grids = dict(self.canvas.axes_layout_service._grids)

        with mock.patch(
            "mygui.figuremodify.components.factory.TextController.sync_from_target",
            side_effect=RuntimeError("injected semantic sync failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "semantic sync"):
                self.canvas.create_axes_layout(AxesLayoutSpec.grid(1, 1))

        self.assertEqual(self.canvas.fig.axes, [])
        self.assertEqual(len(self.canvas.component_registry), 1)
        self.canvas.component_registry.validate_axes_targets()
        self.assertEqual(self.canvas._allocated_component_ids, before_ids)
        self.assertEqual(self.canvas.axes_layout_service._grids, before_grids)

    def test_runtime_target_validation_failure_rolls_back_axes_creation(self):
        before_ids = set(self.canvas._allocated_component_ids)
        before_grids = dict(self.canvas.axes_layout_service._grids)

        with mock.patch.object(
            self.canvas.component_registry,
            "validate_axes_targets",
            side_effect=ComponentValidationError("injected target failure"),
        ):
            with self.assertRaisesRegex(
                ComponentValidationError,
                "injected target failure",
            ):
                create_regular_axes(self.canvas)

        self.assertEqual(self.canvas.fig.axes, [])
        self.assertEqual(len(self.canvas.component_registry), 1)
        self.assertEqual(self.canvas._allocated_component_ids, before_ids)
        self.assertEqual(self.canvas.axes_layout_service._grids, before_grids)

    def test_regular_grid_helper_uses_current_figure_style_defaults(self):
        figure = self.canvas.component_registry.get(
            self.canvas.root_component_id
        )
        self.assertTrue(figure.set_property("style", "ggplot").ok)
        defaults = self.canvas.axes_layout_service.creation_view_defaults()
        self.assertTrue(defaults.x_major_grid)
        self.assertTrue(defaults.y_major_grid)

        axes_id, = create_regular_axes(self.canvas)
        axes = self.canvas.component_registry.resolve_target(axes_id)
        self.assertTrue(any(line.get_visible() for line in axes.get_xgridlines()))
        self.assertTrue(any(line.get_visible() for line in axes.get_ygridlines()))

    def test_layout_service_reads_constrained_state_from_figure_controller(self):
        root = self.canvas.component_registry.get(self.canvas.root_component_id)
        self.assertTrue(
            root.set_property(
                "layout_engine",
                {
                    "kind": "constrained",
                    "params": {
                        "w_pad": None,
                        "h_pad": None,
                        "wspace": None,
                        "hspace": None,
                        "rect": None,
                    },
                },
            ).ok
        )
        self.assertTrue(
            self.canvas.axes_layout_service.constrained_layout_enabled()
        )

    def test_registry_rejects_duplicate_live_axes_targets(self):
        create_regular_axes(self.canvas, nrows=1, ncols=2)
        controllers = self.canvas.component_registry.query(
            kind=ComponentKind.AXES
        )
        first_target = controllers[0].resolve_target()

        with mock.patch.object(
            controllers[1],
            "resolve_target",
            return_value=first_target,
        ):
            with self.assertRaisesRegex(
                ComponentValidationError,
                "same artist",
            ):
                self.canvas.component_registry.validate_axes_targets()

    def test_limit_inversion_proxy_reverses_only_authoritative_limits(self):
        axes_id, = create_regular_axes(self.canvas)
        controller = self.canvas.component_registry.get(axes_id)
        section = AxesLimitsSection(
            controller,
            context=self.canvas.editor_context,
        )
        try:
            before = tuple(controller.state.properties["xlim"])
            section.x_inverted.setChecked(True)
            after = tuple(controller.state.properties["xlim"])
            self.assertEqual(after, tuple(reversed(before)))
            self.assertEqual(
                tuple(controller.resolve_target().get_xlim()),
                after,
            )
            self.assertNotIn("x_inverted", controller.state.properties)
        finally:
            section.dispose()
            section.deleteLater()

    def test_scale_change_reapplies_authoritative_fixed_tickers(self):
        axes_id, = create_regular_axes(self.canvas)
        axis = self.canvas.component_registry.find_one(
            parent_id=axes_id,
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
        )
        locator = {
            "kind": "fixed",
            "params": {"locations": [1.0, 10.0], "nbins": None},
        }
        formatter = {
            "kind": "fixed",
            "params": {"labels": ["one", "ten"]},
        }
        configured = self.canvas.component_registry.apply_transaction(
            (
                ComponentMutation(
                    axis.component_id,
                    properties={
                        "major_locator": locator,
                        "major_formatter": formatter,
                    },
                ),
            )
        )
        self.assertTrue(configured.ok)

        scaled = self.canvas.axes_layout_service.apply_linked_axis(
            axes_id,
            "x",
            scale={
                "kind": "asinh",
                "params": {
                    "linear_width": 1.0,
                    "base": 10.0,
                    "subs": [2.0, 5.0],
                },
            },
        )

        self.assertTrue(scaled.ok)
        target = axis.resolve_target()
        self.assertEqual(target.get_scale(), "asinh")
        self.assertIsInstance(target.get_major_locator(), ticker.FixedLocator)
        self.assertIsInstance(target.get_major_formatter(), ticker.FixedFormatter)
        self.assertEqual(axis.state.properties["major_locator"], locator)
        self.assertEqual(axis.state.properties["major_formatter"], formatter)


if __name__ == "__main__":
    unittest.main()
