import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.axes_helpers import create_regular_axes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from mygui.database import ColumnRef
from mygui.figuremodify.axes_layout import (
    AxesCellSpec,
    AxesLayoutSpec,
    AxesViewSpec,
    ShareMode,
)
from mygui.figuremodify.components import ComponentKind, ComponentRole
from mygui.figuremodify.components.serialization import (
    validate_v9_figure,
)
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from mygui.widgets.title_bar.titlebar_dialog.axes_layout_input import (
    AxesLayoutInput,
    axes_layout_presets,
)
from mygui.widgets.title_bar.titlebar_dialog.py_title_bar_dialog import (
    PyLayoutDialog,
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
        validate_v9_figure(
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
        validate_v9_figure(
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
        self.assertEqual(self.canvas._axes_component_ids, {})
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


if __name__ == "__main__":
    unittest.main()
