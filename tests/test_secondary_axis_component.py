import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from matplotlib import ticker

from main import MainWindow
from mygui.figuremodify.component_services import SecondaryAxisCreateSpec
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentValidationError,
    RestorePhase,
    normalize_unit_transform,
    parent_scale_domain_samples,
    validate_unit_transform_domain,
)
from mygui.project_io import (
    PROJECT_SCHEMA_VERSION,
    project_snapshot,
    restore_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
)
from tests.axes_helpers import create_regular_axes


class SecondaryAxisValueTests(unittest.TestCase):
    def test_safe_transform_contracts_reject_invalid_mappings(self):
        self.assertEqual(
            normalize_unit_transform({"kind": "affine", "scale": 2, "offset": 3}),
            {"kind": "affine", "scale": 2.0, "offset": 3.0},
        )
        validate_unit_transform_domain(
            {"kind": "custom", "forward": "x * 2 + 1", "inverse": "(x - 1) / 2"},
            -10,
            10,
        )
        with self.assertRaisesRegex(ComponentValidationError, "zero"):
            normalize_unit_transform({"kind": "affine", "scale": 0, "offset": 1})
        with self.assertRaisesRegex(ComponentValidationError, "round-trip"):
            validate_unit_transform_domain(
                {"kind": "custom", "forward": "x * 2", "inverse": "x / 3"},
                1,
                10,
            )
        with self.assertRaisesRegex(ComponentValidationError, "strictly monotonic"):
            validate_unit_transform_domain(
                {"kind": "custom", "forward": "x * x", "inverse": "sqrt(x)"},
                -2,
                2,
            )

    def test_parent_domain_samples_are_uniform_in_axis_scale_space(self):
        from matplotlib.figure import Figure

        axes = Figure().subplots()
        axes.set_xscale("log")
        axes.set_xlim(1.0, 1000.0)
        source = parent_scale_domain_samples(axes, "x")
        ratios = source[1:] / source[:-1]
        self.assertTrue((ratios > 1.0).all())
        self.assertAlmostEqual(float(ratios.min()), float(ratios.max()), places=12)


class SecondaryAxisRuntimeTests(unittest.TestCase):
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
            canva_name="SecondaryAxisProject",
        )
        self.canvas = self.window.figure_window.current_canva
        create_regular_axes(self.canvas)

    def tearDown(self):
        self.window.close_without_prompt()
        self.app.processEvents()

    def add_secondary(self, *, object_id="secondary-x", **kwargs):
        self.canvas.add_secondary_axis(
            SecondaryAxisCreateSpec(
                "x",
                unit_transform={
                    "kind": "preset",
                    "name": "celsius_to_fahrenheit",
                },
                properties={"label": "°F"},
                **kwargs,
            ),
            object_id=object_id,
            announce=False,
        )
        return self.canvas.component_registry.get(object_id)

    def test_creation_is_a_leaf_child_axis_without_independent_data(self):
        controller = self.add_secondary()
        runtime = controller.resolve_target()
        owner = self.canvas.current_axes

        self.assertIs(controller.state.kind, ComponentKind.SECONDARY_AXIS)
        self.assertIs(controller.state.role, ComponentRole.SECONDARY_X_AXIS)
        self.assertIs(controller.RESTORE_PHASE, RestorePhase.SECONDARY_AXIS)
        self.assertEqual(controller.state.data, {})
        self.assertIn(runtime.axis, owner.child_axes)
        self.assertNotIn(runtime.axis, self.canvas.fig.axes)
        self.assertIs(runtime.parent_axes, owner)
        first_tick = runtime.axis.xaxis.get_major_ticks()[0]
        self.assertFalse(first_tick.tick1line.get_visible())
        self.assertTrue(first_tick.tick2line.get_visible())
        self.assertFalse(first_tick.label1.get_visible())
        self.assertTrue(first_tick.label2.get_visible())
        self.canvas.component_registry.validate_tree()
        self.canvas.component_registry.validate_axes_targets()

    def test_normalized_placement_is_unique_per_parent_and_orientation(self):
        self.add_secondary()
        with self.assertRaisesRegex(ComponentValidationError, "already occupies"):
            self.canvas.add_secondary_axis(
                SecondaryAxisCreateSpec(
                    "x",
                    placement={
                        "kind": "position",
                        "coordinate_system": "axes_fraction",
                        "value": 1.0,
                    },
                ),
                object_id="duplicate-top",
                announce=False,
            )
        self.canvas.add_secondary_axis(
            SecondaryAxisCreateSpec(
                "y",
                placement={"kind": "edge", "side": "right"},
            ),
            object_id="secondary-y",
            announce=False,
        )
        self.assertEqual(
            len(self.canvas.component_registry.query(kind=ComponentKind.SECONDARY_AXIS)),
            2,
        )

    def test_mapping_and_placement_edits_rebuild_only_the_child_axis(self):
        controller = self.add_secondary()
        runtime = controller.resolve_target()
        old_axis = runtime.axis
        owner = runtime.parent_axes
        result = self.canvas.secondary_axis_service.apply_properties(
            controller,
            {
                "unit_transform": {"kind": "affine", "scale": 0.5, "offset": 2},
                "placement": {
                    "kind": "position",
                    "coordinate_system": "data",
                    "value": 0.25,
                },
            },
        )
        self.assertTrue(result.ok, result.message)
        self.assertIs(controller.resolve_target(), runtime)
        self.assertIsNot(runtime.axis, old_axis)
        self.assertNotIn(old_axis, owner.child_axes)
        self.assertEqual(len(owner.child_axes), 1)
        self.assertEqual(controller.state.properties["unit_transform"]["kind"], "affine")
        self.assertEqual(controller.state.properties["placement"]["coordinate_system"], "data")

    def test_ticker_mode_switch_restores_matplotlib_automatic_tickers(self):
        controller = self.add_secondary()
        runtime = controller.resolve_target()
        result = self.canvas.secondary_axis_service.apply_properties(
            controller,
            {
                "ticker_mode": "custom",
                "major_locator": {
                    "kind": "fixed",
                    "params": {
                        "locations": [32.0, 50.0, 68.0],
                        "nbins": None,
                    },
                },
                "major_formatter": {
                    "kind": "fixed",
                    "params": {"labels": ["freezing", "cool", "warm"]},
                },
            },
        )
        self.assertTrue(result.ok, result.message)
        custom_axis = runtime.axis
        self.assertIsInstance(runtime.axis.xaxis.get_major_locator(), ticker.FixedLocator)
        self.assertIsInstance(runtime.axis.xaxis.get_major_formatter(), ticker.FixedFormatter)

        result = self.canvas.secondary_axis_service.apply_properties(
            controller,
            {"ticker_mode": "automatic"},
        )
        self.assertTrue(result.ok, result.message)
        self.assertIsNot(runtime.axis, custom_axis)
        self.assertNotIsInstance(runtime.axis.xaxis.get_major_locator(), ticker.FixedLocator)
        self.assertNotIsInstance(runtime.axis.xaxis.get_major_formatter(), ticker.FixedFormatter)
        self.assertEqual(controller.state.properties["ticker_mode"], "automatic")

        result = self.canvas.secondary_axis_service.apply_properties(
            controller,
            {"ticker_mode": "custom"},
        )
        self.assertTrue(result.ok, result.message)
        self.assertIsInstance(runtime.axis.xaxis.get_major_locator(), ticker.FixedLocator)
        self.assertIsInstance(runtime.axis.xaxis.get_major_formatter(), ticker.FixedFormatter)

    def test_invalid_pan_domain_hides_and_valid_domain_recovers(self):
        owner = self.canvas.current_axes
        owner.set_xlim(1.0, 2.0)
        self.canvas.add_secondary_axis(
            SecondaryAxisCreateSpec(
                "x",
                unit_transform={"kind": "preset", "name": "frequency_to_period"},
            ),
            object_id="period-axis",
            announce=False,
        )
        runtime = self.canvas.component_registry.get("period-axis").resolve_target()
        warnings = []
        runtime._warning_callback = warnings.append
        self.assertTrue(runtime.domain_valid)
        owner.set_xlim(-1.0, 1.0)
        self.assertFalse(runtime.domain_valid)
        self.assertFalse(runtime.axis.get_visible())
        owner.set_xlim(-2.0, 2.0)
        self.assertEqual(len(warnings), 1)
        owner.set_xlim(2.0, 4.0)
        self.assertTrue(runtime.domain_valid)
        self.assertTrue(runtime.axis.get_visible())
        owner.set_xlim(-3.0, 3.0)
        self.assertEqual(len(warnings), 2)

    def test_parent_scale_transition_revalidates_before_draw(self):
        owner = self.canvas.current_axes
        owner.set_xlim(1.0, 100.0)
        controller = self.add_secondary(object_id="scale-transition")
        runtime = controller.resolve_target()
        original_axis = runtime.axis

        owner.set_xscale("log")
        self.canvas.canva.draw()
        self.assertTrue(runtime.domain_valid)
        self.assertTrue(runtime.axis.get_visible())
        self.assertIs(runtime.axis, original_axis)

        owner.set_xscale("linear")
        self.canvas.canva.draw()
        self.assertTrue(runtime.domain_valid)
        self.assertTrue(runtime.axis.get_visible())

    def test_failed_rebuild_removes_replacement_and_restores_original(self):
        controller = self.add_secondary()
        runtime = controller.resolve_target()
        original_axis = runtime.axis
        original_transform = dict(runtime.unit_transform)

        def fail_reapply():
            raise RuntimeError("injected reapply failure")

        runtime.set_reapply(fail_reapply)
        try:
            with self.assertRaisesRegex(RuntimeError, "injected"):
                runtime.rebuild(unit_transform={"kind": "affine", "scale": 2, "offset": 1})
        finally:
            runtime.set_reapply(controller._apply_all)
        self.assertIs(runtime.axis, original_axis)
        self.assertEqual(runtime.unit_transform, original_transform)
        self.assertEqual(runtime.parent_axes.child_axes, [original_axis])

    def test_creation_preflight_failure_rolls_back_runtime_registry_and_history(self):
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()
        selected = self.canvas.current_component_id
        with mock.patch.object(
            self.canvas,
            "_prepare_created_component",
            side_effect=RuntimeError("injected Inspector preflight failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "preflight"):
                self.canvas.add_secondary_axis(
                    SecondaryAxisCreateSpec("x"),
                    object_id="secondary-preflight-failure",
                    announce=False,
                )
        self.assertNotIn("secondary-preflight-failure", self.canvas.component_registry)
        self.assertEqual(self.canvas.current_axes.child_axes, [])
        self.assertEqual(self.canvas.current_component_id, selected)
        self.assertEqual(stack.count(), 0)

    def test_delete_and_schema_v23_project_round_trip(self):
        controller = self.add_secondary()
        source_runtime = controller.resolve_target()
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "secondary.mygui.json"
            snapshot = save_project_snapshot(path, self.window.figure_window)
            self.assertEqual(snapshot["schema_version"], PROJECT_SCHEMA_VERSION)
            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                target = restored.component_registry.get(controller.component_id).resolve_target()
                self.assertIn(target.axis, restored.current_axes.child_axes)
                self.assertNotIn(target.axis, restored.fig.axes)
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

        self.assertTrue(self.canvas.delete_component_group((controller.component_id,)))
        self.assertNotIn(controller.component_id, self.canvas.component_registry)
        self.assertEqual(self.canvas.current_axes.child_axes, [])
        self.assertIsNone(source_runtime.axis.figure)

    def test_project_restores_saved_invalid_domain_hidden_then_recovers(self):
        owner = self.canvas.current_axes
        owner.set_xlim(1.0, 2.0)
        self.canvas.add_secondary_axis(
            SecondaryAxisCreateSpec(
                "x",
                unit_transform={"kind": "preset", "name": "frequency_to_period"},
            ),
            object_id="saved-invalid-period",
            announce=False,
        )
        owner.set_xlim(-1.0, 1.0)
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "invalid-domain.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            loaded = MainWindow()
            try:
                restore_project_snapshot(path, loaded.table, loaded.figure_window)
                restored = loaded.figure_window.current_canva
                runtime = restored.component_registry.get("saved-invalid-period").resolve_target()
                self.assertFalse(runtime.domain_valid)
                self.assertFalse(runtime.axis.get_visible())
                runtime.parent_axes.set_xlim(2.0, 4.0)
                self.assertTrue(runtime.domain_valid)
                self.assertTrue(runtime.axis.get_visible())
            finally:
                loaded.close_without_prompt()
                self.app.processEvents()

    def test_create_edit_delete_share_project_undo_redo(self):
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()
        controller = self.add_secondary(object_id="secondary-history")
        self.assertEqual(stack.count(), 1)

        stack.undo()
        self.assertNotIn("secondary-history", self.canvas.component_registry)
        stack.redo()
        controller = self.canvas.component_registry.get("secondary-history")
        runtime = controller.resolve_target()
        self.assertIn(runtime.axis, runtime.parent_axes.child_axes)

        result = self.canvas.editor_context.perform(
            "Change Secondary Axis label",
            lambda: self.canvas.secondary_axis_service.apply_properties(
                controller, {"label": "Converted"}
            ),
            merge_key=("property", controller.component_id, "label"),
        )
        self.assertTrue(result.ok, result.message)
        self.assertEqual(controller.state.properties["label"], "Converted")
        stack.undo()
        self.assertEqual(
            self.canvas.component_registry.get("secondary-history").state.properties["label"],
            "°F",
        )
        stack.redo()
        self.assertEqual(
            self.canvas.component_registry.get("secondary-history").state.properties["label"],
            "Converted",
        )

        self.assertTrue(self.canvas.delete_component_group(("secondary-history",)))
        self.assertNotIn("secondary-history", self.canvas.component_registry)
        stack.undo()
        restored = self.canvas.component_registry.get("secondary-history")
        self.assertIn(
            restored.resolve_target().axis,
            restored.resolve_target().parent_axes.child_axes,
        )
        stack.redo()
        self.assertNotIn("secondary-history", self.canvas.component_registry)

    def test_parent_axes_deletion_cascades_and_undo_restores_child(self):
        axes_id = self.canvas.current_axes_component_id
        self.add_secondary(object_id="secondary-cascade")
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        stack.clear()

        self.assertTrue(self.canvas.delete_axes(axes_id))
        self.assertNotIn(axes_id, self.canvas.component_registry)
        self.assertNotIn("secondary-cascade", self.canvas.component_registry)
        stack.undo()
        restored = self.canvas.component_registry.get("secondary-cascade")
        runtime = restored.resolve_target()
        self.assertIn(runtime.axis, runtime.parent_axes.child_axes)
        self.assertIn(axes_id, self.canvas.component_registry)

    def test_schema_v23_rejects_open_secondary_axis_contracts(self):
        self.add_secondary(object_id="secondary-schema")
        snapshot = project_snapshot(self.window.figure_window)

        def secondary(candidate):
            return next(
                item
                for item in candidate["figure"]["components"]
                if item["id"] == "secondary-schema"
            )

        candidates = []
        bad_data = deepcopy(snapshot)
        secondary(bad_data)["data"] = {"independent_data": [1, 2]}
        candidates.append(bad_data)
        bad_selector = deepcopy(snapshot)
        secondary(bad_selector)["selector"]["extra"] = True
        candidates.append(bad_selector)
        bad_parent = deepcopy(snapshot)
        secondary(bad_parent)["parent_id"] = bad_parent["figure"]["root_component_id"]
        candidates.append(bad_parent)
        bad_transform = deepcopy(snapshot)
        secondary(bad_transform)["properties"]["unit_transform"] = {
            "kind": "affine",
            "scale": 0,
            "offset": 0,
        }
        candidates.append(bad_transform)
        duplicate = deepcopy(snapshot)
        record = deepcopy(secondary(duplicate))
        record["id"] = "secondary-schema-duplicate"
        record["selector"] = {"object_id": record["id"]}
        record["order"] += 1
        duplicate["figure"]["components"].append(record)
        candidates.append(duplicate)

        for candidate in candidates:
            with self.subTest(candidate=secondary(candidate)):
                with self.assertRaises(ValueError):
                    validate_project_snapshot(candidate)

    def test_creation_input_and_inspector_are_orientation_aware(self):
        from mygui.widgets.fig_control_window.component_editors import (
            SecondaryAxisInput,
            SecondaryAxisPlacementEditor,
            UnitTransformEditor,
        )

        creation = SecondaryAxisInput()
        try:
            self.assertEqual(
                [
                    creation.placement_input.side_input.itemData(index)
                    for index in range(creation.placement_input.side_input.count())
                ],
                ["top", "bottom"],
            )
            creation.orientation_input.setCurrentIndex(creation.orientation_input.findData("y"))
            self.assertEqual(
                [
                    creation.placement_input.side_input.itemData(index)
                    for index in range(creation.placement_input.side_input.count())
                ],
                ["right", "left"],
            )
            self.assertEqual(creation.spec().orientation, "y")
        finally:
            creation.close()

        controller = self.add_secondary(object_id="secondary-inspector")
        inspector = self.canvas.component_editor_manager.create(
            controller,
            context=self.canvas.editor_context,
        )
        try:
            self.assertEqual(
                tuple(spec.key for spec in inspector.profile.sections),
                (
                    "general",
                    "unit_transform",
                    "placement",
                    "label",
                    "scale_ticks",
                    "tick_appearance",
                    "spine",
                    "advanced",
                ),
            )
            self.assertIsInstance(
                inspector.section("unit_transform").editor("unit_transform"),
                UnitTransformEditor,
            )
            placement = inspector.section("placement").editor("placement")
            self.assertIsInstance(placement, SecondaryAxisPlacementEditor)
            self.assertEqual(
                [
                    placement.side_input.itemData(index)
                    for index in range(placement.side_input.count())
                ],
                ["top", "bottom"],
            )
            stack = self.window.repository.undo_stack(self.canvas.project_id)
            stack.clear()
            label_section = inspector.section("label")
            self.assertTrue(label_section.apply_property("label", "Inspector unit"))
            self.assertEqual(stack.count(), 1)
            stack.undo()
            self.assertEqual(controller.state.properties["label"], "°F")
        finally:
            inspector.close()
