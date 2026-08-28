"""Comprehensive tests for the Annotation (text + target + arrow) component."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from main import MainWindow
from mygui.database import ColumnType
from mygui.excel_io import ExcelColumnSpec, ExcelSheetSpec
from mygui.figuremodify.components import (
    AnnotationArrowStyle,
    AnnotationConnectionStyle,
    AnnotationController,
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    CoordinateSystem,
    DeletionPolicy,
    RestorePhase,
)
from mygui.figuremodify.services.annotation import (
    annotation_artist_kwargs,
)
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    load_project_file,
    restore_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
)
from mygui.template_library import (
    TemplateApplyService,
    TemplateExtractor,
    parse_template,
    template_to_dict,
)
from mygui.widgets.fig_control_window.component_editors import AnnotationInput
from mygui.widgets.fig_control_window.component_editors.profiles import (
    ANNOTATION_PROFILE,
)
from mygui.widgets.fig_control_window.component_editors.sections.annotation import (
    ANNOTATION_PLACEMENT_PRESETS,
)
from tests.axes_helpers import create_regular_axes


def _annotation_state(
    *,
    component_id: str = "annotation-1",
    parent_id: str = "axes-1",
    properties: dict | None = None,
) -> ComponentState:
    defaults = AnnotationController.default_properties()
    defaults.update(properties or {})
    return ComponentState(
        id=component_id,
        kind=ComponentKind.ANNOTATION,
        role=ComponentRole.ANNOTATION,
        parent_id=parent_id,
        order=1,
        selector={"object_id": component_id},
        properties=defaults,
        data={},
    )


class AnnotationControllerUnitTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()

    def _create_controller(self, **properties):
        state = _annotation_state(properties=properties)
        kwargs = annotation_artist_kwargs(state.properties)
        artist = self.axes.annotate(state.properties["text"], **kwargs)
        controller = AnnotationController(state, target=artist)
        initialized = controller.apply_state(state)
        self.assertTrue(initialized.ok)
        return controller, artist

    def test_controller_contract_and_enums(self):
        controller, artist = self._create_controller()
        self.assertEqual(controller.KIND, ComponentKind.ANNOTATION)
        self.assertEqual(controller.ROLES, frozenset({ComponentRole.ANNOTATION}))
        self.assertEqual(controller.RESTORE_PHASE, RestorePhase.DYNAMIC)
        self.assertEqual(controller.DELETION_POLICY, DeletionPolicy.REMOVE)
        self.assertEqual(controller.state.data, {})

        # Check Enums
        self.assertEqual(CoordinateSystem.DATA, "data")
        self.assertEqual(CoordinateSystem.AXES_FRACTION, "axes_fraction")
        self.assertEqual(CoordinateSystem.FIGURE_FRACTION, "figure_fraction")
        self.assertEqual(CoordinateSystem.OFFSET_POINTS, "offset_points")
        self.assertEqual(AnnotationArrowStyle.ARROW, "arrow")
        self.assertEqual(AnnotationConnectionStyle.STRAIGHT, "straight")

    def test_strict_read_and_xytext_get_position(self):
        controller, artist = self._create_controller(
            text="Peak A",
            xy=(1.5, 2.5),
            xytext=(15.0, 30.0),
        )
        state = controller.read_state(strict=True)
        self.assertEqual(state.properties["text"], "Peak A")
        self.assertEqual(state.properties["xy"], (1.5, 2.5))
        self.assertEqual(state.properties["xytext"], (15.0, 30.0))

    def test_invalid_coordinates_rejected(self):
        controller, artist = self._create_controller()
        change1 = controller.set_property("xy", (float("nan"), 1.0))
        self.assertFalse(change1.ok)
        self.assertEqual(change1.status, ChangeStatus.REJECTED)

        change2 = controller.set_property("xytext", (1.0, float("inf")))
        self.assertFalse(change2.ok)
        self.assertEqual(change2.status, ChangeStatus.REJECTED)

        change3 = controller.set_property("xycoords", "invalid_coord_sys")
        self.assertFalse(change3.ok)
        self.assertEqual(change3.status, ChangeStatus.REJECTED)

    def test_coordinate_system_conversion_preserves_display_position(self):
        self.axes.set_xlim(0, 10)
        self.axes.set_ylim(0, 20)
        self.figure.canvas.draw()

        controller, artist = self._create_controller(
            xy=(5.0, 10.0),
            xycoords="data",
        )
        disp_before = controller._display_target(artist)

        # Switch to axes_fraction
        change = controller.set_property("xycoords", "axes_fraction")
        self.assertTrue(change.ok)
        self.assertEqual(controller.state.properties["xycoords"], "axes_fraction")
        self.assertAlmostEqual(controller.state.properties["xy"][0], 0.5, places=3)
        self.assertAlmostEqual(controller.state.properties["xy"][1], 0.5, places=3)

        disp_after = controller._display_target(artist)
        self.assertAlmostEqual(disp_before[0], disp_after[0], places=2)
        self.assertAlmostEqual(disp_before[1], disp_after[1], places=2)

    def test_coordinate_conversions_preserve_target_and_text_on_log_inverted_axes(self):
        self.axes.set_xscale("log")
        self.axes.set_yscale("log")
        self.axes.set_xlim(100.0, 1.0)
        self.axes.set_ylim(10.0, 0.1)
        self.figure.canvas.draw()
        controller, artist = self._create_controller(
            xy=(10.0, 1.0),
            xycoords="data",
            xytext=(18.0, -12.0),
            textcoords="offset_points",
        )
        target_before = controller._display_target(artist)
        text_before = controller._display_text(artist)

        target_change = controller.set_property(
            "xycoords", "axes_fraction"
        )
        text_change = controller.set_property(
            "textcoords", "axes_fraction"
        )

        self.assertTrue(target_change.ok)
        self.assertTrue(text_change.ok)
        state = controller.read_state(strict=True)
        self.assertEqual(state.properties["xycoords"], "axes_fraction")
        self.assertEqual(state.properties["textcoords"], "axes_fraction")
        self.assertEqual(tuple(artist.xy), state.properties["xy"])
        self.assertEqual(artist.get_position(), state.properties["xytext"])
        for before, after in zip(
            target_before,
            controller._display_target(artist),
        ):
            self.assertAlmostEqual(before, after, places=6)
        for before, after in zip(text_before, controller._display_text(artist)):
            self.assertAlmostEqual(before, after, places=6)

    def test_explicit_coordinate_pairs_win_and_failed_pair_rolls_back(self):
        controller, artist = self._create_controller(
            xy=(2.0, 3.0),
            xytext=(12.0, 16.0),
        )
        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties={
                    "xycoords": "axes_fraction",
                    "xy": (0.25, 0.75),
                    "textcoords": "data",
                    "xytext": (4.0, 5.0),
                },
            )
        )
        self.assertTrue(change.ok)
        state = controller.read_state(strict=True)
        self.assertEqual(state.properties["xy"], (0.25, 0.75))
        self.assertEqual(state.properties["xytext"], (4.0, 5.0))

        before = controller.read_state(strict=True)
        display_before = controller._display_target(artist)
        original_write = controller._write_property

        def fail_xy(target, spec, value):
            if spec.key == "xy":
                raise RuntimeError("injected coordinate failure")
            return original_write(target, spec, value)

        with mock.patch.object(controller, "_write_property", side_effect=fail_xy):
            rejected = controller.set_property("xycoords", "data")
        self.assertFalse(rejected.ok)
        self.assertEqual(controller.read_state(strict=True), before)
        self.assertEqual(controller._display_target(artist), display_before)

    def test_arrow_and_alpha_clip_syncing(self):
        controller, artist = self._create_controller(
            arrow_enabled=True,
            arrow_style="filled_arrow",
            connection_style="arc",
            alpha=0.6,
            clip_on=True,
        )
        patch = artist.arrow_patch
        self.assertTrue(patch.get_visible())
        self.assertEqual(artist.get_alpha(), 0.6)
        self.assertEqual(patch.get_alpha(), 0.6)
        self.assertTrue(artist.get_clip_on())
        self.assertTrue(patch.get_clip_on())

        # Disable arrow
        controller.set_property("arrow_enabled", False)
        self.assertFalse(patch.get_visible())

        # Re-enable arrow
        controller.set_property("arrow_enabled", True)
        self.assertTrue(patch.get_visible())

        box_change = controller.set_property(
            "bbox",
            {
                "enabled": True,
                "style": "rounded",
                "facecolor": "#ffffff",
                "edgecolor": "#000000",
                "linewidth": 1.0,
                "alpha": 0.25,
                "padding": 0.4,
            },
        )
        self.assertTrue(box_change.ok)
        self.assertEqual(artist.get_alpha(), 0.6)
        self.assertEqual(artist.arrow_patch.get_alpha(), 0.6)
        self.assertEqual(artist.get_bbox_patch().get_alpha(), 0.25)

        hidden_controller, hidden_artist = self._create_controller(
            arrow_enabled=False,
            arrow_style="double_arrow",
        )
        self.assertIsNotNone(hidden_artist.arrow_patch)
        self.assertFalse(hidden_artist.arrow_patch.get_visible())
        self.assertTrue(
            hidden_controller.set_property("arrow_enabled", True).ok
        )
        self.assertTrue(hidden_artist.arrow_patch.get_visible())
        self.assertEqual(
            hidden_controller.read_state().properties["arrow_style"],
            "double_arrow",
        )

    def test_lower_right_preset_coordinates(self):
        presets_dict = dict(ANNOTATION_PLACEMENT_PRESETS)
        self.assertEqual(len(presets_dict), 8)
        self.assertEqual(presets_dict["Above"], (0.0, 20.0))
        self.assertEqual(presets_dict["Below"], (0.0, -20.0))
        self.assertEqual(presets_dict["Left"], (-20.0, 0.0))
        self.assertEqual(presets_dict["Right"], (20.0, 0.0))
        self.assertEqual(presets_dict["Lower Right"], (20.0, -20.0))
        self.assertEqual(presets_dict["Lower Left"], (-20.0, -20.0))
        self.assertEqual(presets_dict["Upper Right"], (20.0, 20.0))
        self.assertEqual(presets_dict["Upper Left"], (-20.0, 20.0))

    def test_tree_preview_prefers_name_and_truncates_collapsed_text(self):
        preview = ANNOTATION_PROFILE.tree.preview
        named = _annotation_state(
            properties={"label": "Named feature", "text": "ignored"}
        )
        self.assertEqual(preview(named), "Named feature")
        long_text = _annotation_state(
            properties={
                "label": "",
                "text": "  Strong\n field   induced transition around peak  ",
            }
        )
        result = preview(long_text)
        self.assertEqual(len(result), 32)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn("\n", result)


class AnnotationIntegrationAndHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.figure_window.add_figure(
            width=6,
            height=4,
            dpi=100,
            style="default",
            canva_name="AnnotationCanvas",
        )
        self.canvas = self.window.figure_window.current_canva
        self.axes_id, = create_regular_axes(self.canvas)
        self.canvas.select_component(self.axes_id)

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    def test_add_annotation_and_undo_redo(self):
        undo_stack = self.window.repository.undo_stack(self.canvas.project_id)
        initial_count = undo_stack.count()

        artist = self.canvas.add_annotation_from_input(
            {"text": "Integration Peak", "xy": [2.0, 3.0]},
            axes_id=self.axes_id,
        )
        component_id = artist.get_gid()
        self.assertIn(component_id, self.canvas.component_registry)
        self.assertEqual(undo_stack.count(), initial_count + 1)

        # Edit property via history
        controller = self.canvas.component_registry.get(component_id)
        self.canvas.editor_context.perform(
            "Change Annotation Text",
            lambda: self.canvas.editor_context.annotations.apply_properties(
                controller, {"text": "Updated Peak"}
            ),
        )
        self.assertEqual(controller.state.properties["text"], "Updated Peak")
        self.assertEqual(undo_stack.count(), initial_count + 2)

        # Undo edit
        undo_stack.undo()
        self.assertEqual(controller.state.properties["text"], "Integration Peak")

        # Undo create
        undo_stack.undo()
        self.assertNotIn(component_id, self.canvas.component_registry)

        # Redo create
        undo_stack.redo()
        self.assertIn(component_id, self.canvas.component_registry)

    def test_inspector_sections_labels_presets_and_rejected_rollback(self):
        artist = self.canvas.add_annotation(
            {"text": "Inspector Annotation"},
            axes_id=self.axes_id,
        )
        component_id = artist.get_gid()
        controller = self.canvas.component_registry.get(component_id)
        inspector = self.canvas.component_editor_manager.editor(component_id)
        self.assertIsNotNone(inspector)
        self.assertEqual(
            tuple(section.section_key for section in inspector.sections()),
            (
                "content",
                "target",
                "text_position",
                "arrow",
                "text_style",
                "transform",
                "box",
                "advanced",
            ),
        )
        target_coords = inspector.editor("xycoords")
        self.assertEqual(
            {
                target_coords.itemData(index): target_coords.itemText(index)
                for index in range(target_coords.count())
            },
            {"data": "Data", "axes_fraction": "Axes fraction"},
        )
        arrow_style = inspector.editor("arrow_style")
        self.assertEqual(
            {
                arrow_style.itemData(index): arrow_style.itemText(index)
                for index in range(arrow_style.count())
            }["filled_arrow"],
            "Filled Arrow",
        )
        box_dialog = inspector.editor("bbox")._dialog()
        try:
            self.assertEqual(
                {
                    box_dialog.style_input.itemData(index):
                    box_dialog.style_input.itemText(index)
                    for index in range(box_dialog.style_input.count())
                },
                {"square": "Square", "rounded": "Rounded"},
            )
        finally:
            box_dialog.close()
            box_dialog.deleteLater()

        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()
        placement = inspector.section("text_position")
        placement._apply_preset(8)
        self.assertEqual(
            controller.state.properties["textcoords"], "offset_points"
        )
        self.assertEqual(
            tuple(controller.state.properties["xytext"]),
            (20.0, -20.0),
        )
        self.assertEqual(placement.preset_input.currentIndex(), 0)
        self.assertEqual(stack.count(), 1)
        stack.undo()
        self.assertEqual(
            tuple(controller.read_state().properties["xytext"]),
            (20.0, 20.0),
        )
        stack.redo()
        self.assertEqual(
            tuple(controller.read_state().properties["xytext"]),
            (20.0, -20.0),
        )

        before = controller.read_state()
        rejected = ComponentChange(
            component_id,
            "visible",
            before,
            before,
            ChangeStatus.REJECTED,
            message="injected rejection",
        )
        content = inspector.section("content")
        with mock.patch.object(
            self.canvas.annotation_service,
            "apply_properties",
            return_value=rejected,
        ):
            content.visible_input.setChecked(False)
            self.assertTrue(content.visible_input.isChecked())
            content.text_content.setPlainText("rejected text")
            self.assertFalse(content.set_text_content())
            self.assertEqual(
                content.text_content.toPlainText(),
                before.properties["text"],
            )

    def test_coordinate_conversion_and_box_each_make_one_replayable_command(self):
        artist = self.canvas.add_annotation(
            {"text": "History", "xy": (2.0, 3.0)},
            axes_id=self.axes_id,
        )
        controller = self.canvas.component_registry.get(artist.get_gid())
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()

        before = controller.read_state(strict=True)
        converted = self.canvas.editor_context.perform(
            "Change Annotation Target Coordinates",
            lambda: self.canvas.annotation_service.apply_properties(
                controller,
                {"xycoords": "axes_fraction"},
            ),
        )
        self.assertTrue(converted.ok)
        converted_state = controller.read_state(strict=True)
        self.assertEqual(stack.count(), 1)
        self.assertEqual(converted_state.properties["xycoords"], "axes_fraction")
        stack.undo()
        self.assertEqual(controller.read_state(strict=True), before)
        stack.redo()
        self.assertEqual(controller.read_state(strict=True), converted_state)

        box = {
            "enabled": True,
            "style": "square",
            "facecolor": "#112233",
            "edgecolor": "#445566",
            "linewidth": 2.0,
            "alpha": 0.4,
            "padding": 0.5,
        }
        boxed = self.canvas.editor_context.perform(
            "Change Annotation Box",
            lambda: self.canvas.annotation_service.apply_properties(
                controller,
                {"bbox": box},
            ),
        )
        self.assertTrue(boxed.ok)
        self.assertEqual(stack.count(), 2)
        self.assertEqual(controller.read_state().properties["bbox"], box)
        stack.undo()
        self.assertFalse(
            controller.read_state().properties["bbox"]["enabled"]
        )
        stack.redo()
        self.assertEqual(controller.read_state().properties["bbox"], box)

    def test_creation_input_limits_follow_both_coordinate_systems(self):
        widget = AnnotationInput(default_xy=(3.0, 4.0))
        try:
            widget.xycoords_input.setCurrentIndex(
                widget.xycoords_input.findData("axes_fraction")
            )
            self.assertEqual(widget.x_input.minimum(), 0.0)
            self.assertEqual(widget.x_input.maximum(), 1.0)
            widget.textcoords_input.setCurrentIndex(
                widget.textcoords_input.findData("axes_fraction")
            )
            self.assertEqual(widget.xytext_x_input.minimum(), 0.0)
            self.assertEqual(widget.xytext_x_input.maximum(), 1.0)
            widget.textcoords_input.setCurrentIndex(
                widget.textcoords_input.findData("offset_points")
            )
            self.assertLess(widget.xytext_x_input.minimum(), -1e6)
            self.assertGreater(widget.xytext_x_input.maximum(), 1e6)
        finally:
            widget.deleteLater()

    def test_interactive_creation_uses_figure_style_without_palette_or_settings(self):
        defaults = self.canvas.component_creation_defaults()
        axes_controller = self.canvas.component_registry.get(self.axes_id)
        color_cycle_before = axes_controller.state.properties["color_cycle"]
        with mock.patch.object(
            self.canvas,
            "_read_component_defaults",
            side_effect=AssertionError("Annotation must not read Components Settings"),
        ):
            artist = self.canvas.add_annotation_from_input(
                {"text": "Styled"},
                axes_id=self.axes_id,
            )
        state = self.canvas.component_registry.get(
            artist.get_gid()
        ).read_state()
        self.assertEqual(state.properties["fontfamily"], defaults.text.fontfamily)
        self.assertEqual(state.properties["fontsize"], defaults.text.fontsize)
        self.assertEqual(state.properties["fontweight"], defaults.text.fontweight)
        self.assertEqual(state.properties["fontstyle"], defaults.text.fontstyle)
        self.assertEqual(state.properties["color"], defaults.text.color)
        self.assertEqual(state.properties["arrow_color"], defaults.text.color)
        self.assertEqual(
            state.properties["arrow_linewidth"],
            defaults.line.linewidth,
        )
        self.assertEqual(
            axes_controller.state.properties["color_cycle"],
            color_cycle_before,
        )

    def test_duplicate_annotation(self):
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        artist = self.canvas.add_annotation(
            {"text": "Duplicate Me", "xy": [1.0, 1.0], "label": "Original"},
            axes_id=self.axes_id,
        )
        original_id = artist.get_gid()
        count_before = stack.count()
        new_id = self.canvas.duplicate_annotation(original_id)
        self.assertIsNotNone(new_id)
        self.assertNotEqual(original_id, new_id)

        new_controller = self.canvas.component_registry.get(new_id)
        self.assertEqual(new_controller.state.properties["text"], "Duplicate Me")
        self.assertEqual(new_controller.state.properties["label"], "Original")
        self.assertEqual(stack.count(), count_before + 1)
        original = self.canvas.component_registry.get(original_id).state
        self.assertEqual(new_controller.state.order, original.order + 1)

        # Generic duplicate_component
        another_id = self.canvas.duplicate_component(new_id)
        self.assertIn(another_id, self.canvas.component_registry)

    def test_delete_annotation_via_deletion_coordinator(self):
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        artist = self.canvas.add_annotation(
            {"text": "Delete Me"},
            axes_id=self.axes_id,
        )
        component_id = artist.get_gid()
        self.assertIn(component_id, self.canvas.component_registry)
        count_before = stack.count()

        deleted = self.canvas.delete_components([component_id])
        self.assertTrue(deleted)
        self.assertNotIn(component_id, self.canvas.component_registry)
        self.assertEqual(stack.count(), count_before + 1)
        stack.undo()
        self.assertIn(component_id, self.canvas.component_registry)
        stack.redo()
        self.assertNotIn(component_id, self.canvas.component_registry)

    def test_schema_v17_save_open_round_trip(self):
        artist = self.canvas.add_annotation(
            {
                "text": "Saved Annotation",
                "xy": [4.0, 5.0],
                "xycoords": "data",
                "xytext": [30.0, 40.0],
                "textcoords": "offset_points",
                "arrow_style": "filled_arrow",
                "connection_style": "arc",
            },
            axes_id=self.axes_id,
        )
        component_id = artist.get_gid()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_annotation_v18.mygui.json"
            save_project_snapshot(path, self.window.figure_window)

            raw = load_project_file(path)
            self.assertEqual(raw["schema_version"], PROJECT_SCHEMA_VERSION)

            # Reopen in new MainWindow
            loaded = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    loaded.table,
                    loaded.figure_window,
                )
                restored_canvas = loaded.figure_window.current_canva
                self.assertIn(component_id, restored_canvas.component_registry)
                restored_controller = restored_canvas.component_registry.get(
                    component_id
                )
                self.assertEqual(
                    restored_controller.state.properties["text"],
                    "Saved Annotation",
                )
                self.assertEqual(
                    restored_controller.state.properties["arrow_style"],
                    "filled_arrow",
                )
            finally:
                loaded.close_without_prompt()

    def test_template_extraction_and_application(self):
        artist = self.canvas.add_annotation(
            {
                "text": "Peak {x}",
                "xy": [1.0, 2.0],
                "arrow_style": "double_arrow",
            },
            axes_id=self.axes_id,
        )
        extractor = TemplateExtractor(self.window.repository)
        template = extractor.extract(
            self.canvas,
            name="Annotation Template",
            dynamic_text_overrides={
                (artist.get_gid(), "text"): "{{project_name}} peak"
            },
        )
        template = parse_template(template_to_dict(template))
        has_annotation = any(
            c["kind"] == "annotation" for c in template.figure["components"]
        )
        self.assertTrue(has_annotation)
        plan = TemplateApplyService(self.window.repository).prepare(
            template,
            [
                ExcelSheetSpec(
                    "source",
                    "Data",
                    [
                        ExcelColumnSpec(
                            "X",
                            ColumnType.NUMBER,
                            [1.0, 2.0],
                        )
                    ],
                )
            ],
            source_file="sample.csv",
            project_name="Applied Annotation",
        )
        applied = next(
            component
            for component in plan.project_snapshot["figure"]["components"]
            if component["kind"] == "annotation"
        )
        self.assertEqual(applied["properties"]["text"], "Applied Annotation peak")
        self.assertEqual(applied["properties"]["arrow_style"], "double_arrow")

    def test_button_press_and_dispose_disconnect(self):
        self.assertIsNotNone(self.canvas._button_press_cid)
        self.canvas.dispose()
        self.assertIsNone(self.canvas._button_press_cid)

    def test_mpl_button_press_right_click_interactions(self):
        class DummyMplEvent:
            def __init__(self, button, inaxes, xdata, ydata):
                self.button = button
                self.inaxes = inaxes
                self.xdata = xdata
                self.ydata = ydata

        current_axes = self.canvas.current_axes

        # 1. Right click with menu accepted
        import mygui.widgets.figure_canvas.py_figure_canves as canvas_mod
        with mock.patch.object(canvas_mod, "QMenu") as mock_menu_cls:
            mock_menu = mock.MagicMock()
            mock_menu_cls.return_value = mock_menu
            fake_action = object()
            mock_menu.addAction.return_value = fake_action
            mock_menu.exec.return_value = fake_action
            with mock.patch.object(self.canvas, "add_annotation_from_input", wraps=self.canvas.add_annotation_from_input) as mock_add:
                event = DummyMplEvent(button=3, inaxes=current_axes, xdata=3.5, ydata=4.5)
                self.canvas._on_mpl_button_press(event)
                mock_add.assert_called_once()
                self.assertEqual(mock_add.call_args[0][0]["xy"], [3.5, 4.5])
                selected = self.canvas.component_registry.get(
                    self.canvas.current_component_id
                )
                self.assertEqual(selected.state.kind, ComponentKind.ANNOTATION)
                self.assertEqual(
                    selected.state.properties["text"], "New Annotation"
                )

        # 2. Pan/zoom active -> suppressed
        with mock.patch.object(self.canvas.navigation_toolbar, "mode", "pan/zoom"), \
             mock.patch.object(self.canvas, "add_annotation_from_input") as mock_add:
            event = DummyMplEvent(button=3, inaxes=current_axes, xdata=3.5, ydata=4.5)
            self.canvas._on_mpl_button_press(event)
            mock_add.assert_not_called()

        # 3. Left click -> ignored
        with mock.patch.object(self.canvas, "add_annotation_from_input") as mock_add:
            event = DummyMplEvent(button=1, inaxes=current_axes, xdata=3.5, ydata=4.5)
            self.canvas._on_mpl_button_press(event)
            mock_add.assert_not_called()

        # 4. Inaxes is None -> ignored
        with mock.patch.object(self.canvas, "add_annotation_from_input") as mock_add:
            event = DummyMplEvent(button=3, inaxes=None, xdata=3.5, ydata=4.5)
            self.canvas._on_mpl_button_press(event)
            mock_add.assert_not_called()

        # 5. An unregistered/auxiliary Axes and non-finite data are ignored.
        foreign_axes = self.canvas.fig.add_axes((0.8, 0.8, 0.1, 0.1))
        with mock.patch.object(self.canvas, "add_annotation_from_input") as mock_add:
            self.canvas._on_mpl_button_press(
                DummyMplEvent(3, foreign_axes, 1.0, 2.0)
            )
            self.canvas._on_mpl_button_press(
                DummyMplEvent(3, current_axes, float("nan"), 2.0)
            )
            mock_add.assert_not_called()
        foreign_axes.remove()

    def test_schema_v16_to_v19_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_v16.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            raw = json.loads(path.read_text(encoding="utf-8"))
            for comp in raw["figure"]["components"]:
                if comp["kind"] == "axes" and "geometry" in comp.get("data", {}):
                    del comp["data"]["geometry"]
                    comp["properties"]["in_layout"] = True
            raw["schema_version"] = 16
            path.write_text(json.dumps(raw), encoding="utf-8")
            migrated = load_project_file(path)
            self.assertEqual(migrated["schema_version"], 19)

    def test_schema_v17_annotation_contract_and_predecessor_rejection(self):
        self.canvas.add_annotation(
            {"text": "Strict Annotation"},
            axes_id=self.axes_id,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict-annotation.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        annotation = next(
            item
            for item in snapshot["figure"]["components"]
            if item["kind"] == "annotation"
        )
        self.assertEqual(annotation["selector"], {"object_id": annotation["id"]})
        self.assertEqual(annotation["data"], {})
        self.assertEqual(
            set(annotation["properties"]),
            set(AnnotationController.default_properties()),
        )

        bad_selector = json.loads(json.dumps(snapshot))
        bad_annotation = next(
            item
            for item in bad_selector["figure"]["components"]
            if item["kind"] == "annotation"
        )
        bad_annotation["selector"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "Annotation selector"):
            validate_project_snapshot(bad_selector)

        invalid_cases = {
            "data": ("data", {"opaque": True}),
            "coordinate": ("xycoords", "figure_fraction"),
            "color": ("arrow_color", "not-a-color"),
            "nonfinite": ("xy", [float("inf"), 0.0]),
            "box": (
                "bbox",
                {
                    **annotation["properties"]["bbox"],
                    "unexpected": True,
                },
            ),
        }
        for name, (key, value) in invalid_cases.items():
            with self.subTest(name=name):
                candidate = json.loads(json.dumps(snapshot))
                candidate_annotation = next(
                    item
                    for item in candidate["figure"]["components"]
                    if item["kind"] == "annotation"
                )
                if key == "data":
                    candidate_annotation["data"] = value
                else:
                    candidate_annotation["properties"][key] = value
                with self.assertRaises(ValueError):
                    validate_project_snapshot(candidate)

        bad_parent = json.loads(json.dumps(snapshot))
        bad_parent_annotation = next(
            item
            for item in bad_parent["figure"]["components"]
            if item["kind"] == "annotation"
        )
        bad_parent_annotation["parent_id"] = bad_parent["figure"][
            "root_component_id"
        ]
        with self.assertRaisesRegex(ValueError, "Invalid parent kind"):
            validate_project_snapshot(bad_parent)

        predecessor = json.loads(json.dumps(snapshot))
        for comp in predecessor["figure"]["components"]:
            if comp["kind"] == "axes" and "geometry" in comp.get("data", {}):
                del comp["data"]["geometry"]
                comp["properties"]["in_layout"] = True
        predecessor["schema_version"] = 16
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "illegal-v16.mygui.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Annotation is not part"):
                load_project_file(path)

    def test_render_failure_and_unavailable_tex_are_atomic_without_history(self):
        artist = self.canvas.add_annotation(
            {"text": "safe"},
            axes_id=self.axes_id,
        )
        controller = self.canvas.component_registry.get(artist.get_gid())
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()

        with mock.patch.object(
            self.canvas.fig.canvas,
            "draw",
            side_effect=RuntimeError("injected render failure"),
        ):
            failed = self.canvas.editor_context.perform(
                "Change Annotation Text",
                lambda: self.canvas.annotation_service.apply_properties(
                    controller,
                    {"text": "unsafe"},
                ),
            )
        self.assertFalse(failed.ok)
        self.assertEqual(controller.state.properties["text"], "safe")
        self.assertEqual(artist.get_text(), "safe")
        self.assertEqual(stack.count(), 0)

        self.canvas.text_render_service.tex_enabled = lambda: False
        rejected_tex = self.canvas.editor_context.perform(
            "Enable Annotation TeX",
            lambda: self.canvas.annotation_service.apply_properties(
                controller,
                {"usetex": True},
            ),
        )
        self.assertFalse(rejected_tex.ok)
        self.assertFalse(controller.state.properties["usetex"])
        self.assertFalse(artist.get_usetex())
        self.assertEqual(stack.count(), 0)

    def test_missing_glyph_warning_rolls_back_annotation_text(self):
        artist = self.canvas.add_annotation(
            {"text": "safe"},
            axes_id=self.axes_id,
        )
        controller = self.canvas.component_registry.get(artist.get_gid())
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()

        def draw_warning():
            warnings.warn(
                "Glyph 65509 missing from font(s) Times New Roman.",
                UserWarning,
            )

        with mock.patch.object(
            self.canvas.fig.canvas,
            "draw",
            side_effect=draw_warning,
        ):
            result = self.canvas.editor_context.perform(
                "Change Annotation Text",
                lambda: self.canvas.annotation_service.apply_properties(
                    controller,
                    {"text": "unsupported"},
                ),
            )
        self.assertFalse(result.ok)
        self.assertEqual(controller.state.properties["text"], "safe")
        self.assertEqual(artist.get_text(), "safe")
        self.assertEqual(stack.count(), 0)

    def test_registration_transaction_fault_injection(self):
        axes = self.canvas.current_axes
        initial_artists_count = len(axes.texts)
        initial_selection = self.canvas.current_component_id
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        initial_history = stack.count()
        with mock.patch.object(self.canvas.component_registry, "register", side_effect=RuntimeError("Simulated registration failure")):
            with self.assertRaises(RuntimeError):
                self.canvas.add_annotation({"text": "Fault Injection"}, axes_id=self.axes_id)
        # Verify artist was cleaned up
        self.assertEqual(len(axes.texts), initial_artists_count)
        self.assertEqual(self.canvas.current_component_id, initial_selection)
        self.assertEqual(stack.count(), initial_history)

    def test_creation_render_and_inspector_faults_leave_no_runtime_leaks(self):
        axes = self.canvas.current_axes
        initial_artists_count = len(axes.texts)
        initial_selection = self.canvas.current_component_id
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        initial_history = stack.count()

        cases = (
            (
                "render-fault-annotation",
                mock.patch.object(
                    self.canvas.text_render_service,
                    "apply",
                    side_effect=RuntimeError("injected render failure"),
                ),
            ),
            (
                "inspector-fault-annotation",
                mock.patch.object(
                    self.canvas.figure_inspector,
                    "show_component",
                    return_value=False,
                ),
            ),
        )
        for object_id, fault in cases:
            with self.subTest(object_id=object_id), fault:
                with self.assertRaises(RuntimeError):
                    self.canvas.add_annotation(
                        {"text": "Fault"},
                        axes_id=self.axes_id,
                        object_id=object_id,
                    )
                self.assertNotIn(object_id, self.canvas.component_registry)
                self.assertIsNone(
                    self.canvas.component_editor_manager.editor(object_id)
                )
                self.assertEqual(len(axes.texts), initial_artists_count)
                self.assertEqual(
                    self.canvas.current_component_id,
                    initial_selection,
                )
                self.assertEqual(stack.count(), initial_history)


if __name__ == "__main__":
    unittest.main()
