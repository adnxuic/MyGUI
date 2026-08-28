"""Comprehensive tests for individual Axes geometry control (AxesGeometryService)."""

from __future__ import annotations

import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import MainWindow
from mygui.figuremodify.axes_layout import AxesLayoutSpec, ShareMode
from mygui.figuremodify.axes_geometry import (
    AxesGeometryMode,
    AxesGeometrySpec,
    normalize_geometry_bounds,
    validate_geometry_record,
)
from mygui.figuremodify.components import ChangeStatus, ComponentKind
from mygui.figuremodify.services.axes_geometry import AxesGeometryService
from mygui.project_io import restore_project_snapshot, save_project_snapshot
from tests.axes_helpers import create_regular_axes, create_twin_axes_pair


class AxesGeometryWireContractTests(unittest.TestCase):
    """Wire contract validation for AxesGeometrySpec and schema v19 Axes geometry."""

    def test_grid_mode_spec(self):
        spec = AxesGeometrySpec.from_dict({"mode": "grid"})
        self.assertEqual(spec.mode, AxesGeometryMode.GRID)
        self.assertIsNone(spec.bounds)
        self.assertEqual(spec.to_dict(), {"mode": "grid"})

    def test_manual_mode_spec(self):
        spec = AxesGeometrySpec.from_dict({
            "mode": "manual",
            "bounds": [0.123456, 0.234567, 0.5, 0.4],
        })
        self.assertEqual(spec.mode, AxesGeometryMode.MANUAL)
        self.assertEqual(spec.bounds, (0.123456, 0.234567, 0.5, 0.4))
        self.assertEqual(
            spec.to_dict(),
            {"mode": "manual", "bounds": [0.123456, 0.234567, 0.5, 0.4]},
        )

    def test_spec_rejections(self):
        invalid_cases = [
            ({}, "Axes geometry"),
            ({"mode": "unknown"}, "Unknown Axes geometry mode"),
            ({"mode": "grid", "bounds": [0.1, 0.1, 0.5, 0.5]}, "only mode"),
            ({"mode": "grid", "extra": 1}, "only mode"),
            ({"mode": "manual"}, "only mode and bounds"),
            ({"mode": "manual", "bounds": [0.1, 0.1, 0.5]}, "four values"),
            ({"mode": "manual", "bounds": [0.1, 0.1, 0.5, 0.5, 0.1]}, "four values"),
            ({"mode": "manual", "bounds": [-0.1, 0.1, 0.5, 0.5]}, "left and bottom"),
            ({"mode": "manual", "bounds": [0.1, -0.1, 0.5, 0.5]}, "left and bottom"),
            ({"mode": "manual", "bounds": [0.1, 0.1, 0.0, 0.5]}, "width and height"),
            ({"mode": "manual", "bounds": [0.1, 0.1, 0.5, 0.0]}, "width and height"),
            ({"mode": "manual", "bounds": [0.8, 0.1, 0.5, 0.5]}, "unit Figure"),
            ({"mode": "manual", "bounds": [0.1, 0.8, 0.5, 0.5]}, "unit Figure"),
            ({"mode": "manual", "bounds": [float("nan"), 0.1, 0.5, 0.5]}, "finite"),
            ({"mode": "manual", "bounds": [0.1, float("inf"), 0.5, 0.5]}, "finite"),
        ]
        for data, message in invalid_cases:
            with self.subTest(data=data):
                with self.assertRaisesRegex((ValueError, TypeError), message):
                    validate_geometry_record(data, "test.path")

    def test_normalize_bounds_precision(self):
        raw = [0.123456789, 0.234567891, 0.345678912, 0.456789123]
        normalized = normalize_geometry_bounds(raw)
        self.assertEqual(normalized, (0.123457, 0.234568, 0.345679, 0.456789))


class AxesGeometryServiceTests(unittest.TestCase):
    """Runtime service tests for AxesGeometryService."""

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
            canva_name="GeomTest",
        )
        self.canvas = self.window.figure_window.current_canva
        self.axes_id = create_regular_axes(self.canvas)[0]
        self.service: AxesGeometryService = self.canvas.axes_geometry_service

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _state(self, component_id: str):
        return self.canvas.component_registry.get(component_id).state

    def _target(self, component_id: str):
        return self.canvas.component_registry.get(component_id).resolve_target()

    def test_initial_axes_is_grid_mode(self):
        state = self._state(self.axes_id)
        self.assertEqual(state.data.get("geometry"), {"mode": "grid"})
        self.assertNotIn("in_layout", state.properties)
        target = self._target(self.axes_id)
        self.assertTrue(target.get_in_layout())
        self.assertIsNotNone(target.get_subplotspec())

    def test_in_layout_is_derived_and_not_independently_persistent(self):
        controller = self.canvas.component_registry.get(self.axes_id)
        target = controller.resolve_target()

        rejected = controller.set_property("in_layout", False)

        self.assertIs(rejected.status, ChangeStatus.REJECTED)
        self.assertNotIn("in_layout", controller.state.properties)
        self.assertTrue(target.get_in_layout())

        self.assertTrue(self.service.switch_to_manual(self.axes_id).ok)
        self.assertNotIn("in_layout", controller.state.properties)
        self.assertFalse(target.get_in_layout())

    def test_switch_to_manual_and_return_to_grid(self):
        # Switch to manual with default current visual bounds
        res = self.service.switch_to_manual(self.axes_id)
        self.assertTrue(res.ok)

        state = self._state(self.axes_id)
        geom = state.data.get("geometry", {})
        self.assertEqual(geom.get("mode"), "manual")
        self.assertEqual(len(geom.get("bounds", [])), 4)

        target = self._target(self.axes_id)
        self.assertFalse(target.get_in_layout())
        self.assertIsNone(target.get_subplotspec())

        # Set specific manual bounds
        new_bounds = [0.15, 0.2, 0.65, 0.55]
        res = self.service.set_manual_bounds(self.axes_id, new_bounds)
        self.assertTrue(res.ok)

        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["bounds"], new_bounds)
        pos = target.get_position()
        self.assertAlmostEqual(pos.x0, 0.15, places=5)
        self.assertAlmostEqual(pos.y0, 0.2, places=5)
        self.assertAlmostEqual(pos.width, 0.65, places=5)
        self.assertAlmostEqual(pos.height, 0.55, places=5)

        # Return to grid
        res = self.service.return_to_grid(self.axes_id)
        self.assertTrue(res.ok)

        state = self._state(self.axes_id)
        self.assertEqual(state.data.get("geometry"), {"mode": "grid"})
        self.assertTrue(target.get_in_layout())
        self.assertIsNotNone(target.get_subplotspec())

    def test_reset_to_grid_bounds(self):
        # Switch to manual and change bounds
        self.service.switch_to_manual(self.axes_id)
        self.service.set_manual_bounds(self.axes_id, [0.1, 0.1, 0.3, 0.3])
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["bounds"], [0.1, 0.1, 0.3, 0.3])

        # Reset to grid bounds
        res = self.service.reset_to_grid_bounds(self.axes_id)
        self.assertTrue(res.ok)

        state = self._state(self.axes_id)
        # Mode is still manual, but bounds match grid cell calculation
        self.assertEqual(state.data["geometry"]["mode"], "manual")
        bounds = state.data["geometry"]["bounds"]
        self.assertNotEqual(bounds, [0.1, 0.1, 0.3, 0.3])
        self.assertTrue(0 < bounds[0] < 1)
        self.assertTrue(0 < bounds[1] < 1)
        self.assertTrue(0 < bounds[2] < 1)
        self.assertTrue(0 < bounds[3] < 1)

    def test_twin_axes_coupling(self):
        primary_id, twin_id = create_twin_axes_pair(self.canvas)

        # Initial state both grid
        p_state = self._state(primary_id)
        t_state = self._state(twin_id)
        self.assertEqual(p_state.data["geometry"], {"mode": "grid"})
        self.assertEqual(t_state.data["geometry"], {"mode": "grid"})

        # Switch to manual on primary updates twin atomically
        res = self.service.switch_to_manual(primary_id)
        self.assertTrue(res.ok)

        p_state = self._state(primary_id)
        t_state = self._state(twin_id)
        self.assertEqual(p_state.data["geometry"]["mode"], "manual")
        self.assertEqual(t_state.data["geometry"]["mode"], "manual")
        self.assertEqual(
            p_state.data["geometry"]["bounds"],
            t_state.data["geometry"]["bounds"],
        )

        # Setting bounds on twin also syncs to primary
        res = self.service.set_manual_bounds(twin_id, [0.15, 0.2, 0.65, 0.55])
        self.assertTrue(res.ok)

        p_state = self._state(primary_id)
        t_state = self._state(twin_id)
        self.assertEqual(p_state.data["geometry"]["bounds"], [0.15, 0.2, 0.65, 0.55])
        self.assertEqual(t_state.data["geometry"]["bounds"], [0.15, 0.2, 0.65, 0.55])

        # Return to grid returns both
        res = self.service.return_to_grid(primary_id)
        self.assertTrue(res.ok)

        p_state = self._state(primary_id)
        t_state = self._state(twin_id)
        self.assertEqual(p_state.data["geometry"], {"mode": "grid"})
        self.assertEqual(t_state.data["geometry"], {"mode": "grid"})

    def test_auto_layout_engine_neutrality(self):
        # Switch to manual
        self.service.switch_to_manual(self.axes_id)
        self.service.set_manual_bounds(self.axes_id, [0.15, 0.2, 0.6, 0.5])

        # Set figure layout engine to constrained
        fig_ctrl = self.canvas.component_registry.get(self.canvas.root_component_id)
        res = fig_ctrl.set_property(
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
        )
        self.assertTrue(res.ok)

        # Manual axes remains detached and pinned
        target = self._target(self.axes_id)
        self.assertFalse(target.get_in_layout())
        self.assertIsNone(target.get_subplotspec())
        pos = target.get_position()
        self.assertAlmostEqual(pos.x0, 0.15, places=5)
        self.assertAlmostEqual(pos.y0, 0.2, places=5)

        # Switch engine to tight
        res = fig_ctrl.set_property(
            "layout_engine",
            {
                "kind": "tight",
                "params": {
                    "pad": None,
                    "w_pad": None,
                    "h_pad": None,
                    "rect": None,
                },
            },
        )
        self.assertTrue(res.ok)
        self.assertFalse(target.get_in_layout())

    def test_undo_redo_grid_and_manual_transitions(self):
        stack = self.window.repository.undo_stack(self.canvas.project_id)
        base_count = stack.count()

        # 1. Switch to manual
        res = self.canvas.editor_context.perform(
            "Switch to manual",
            lambda: self.service.switch_to_manual(self.axes_id),
        )
        self.assertTrue(res.ok)
        self.assertEqual(stack.count(), base_count + 1)
        initial_bounds = self._state(self.axes_id).data["geometry"]["bounds"]

        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["mode"], "manual")
        target = self._target(self.axes_id)
        self.assertFalse(target.get_in_layout())

        # 2. Change bounds
        res = self.canvas.editor_context.perform(
            "Change manual bounds",
            lambda: self.service.set_manual_bounds(self.axes_id, [0.15, 0.2, 0.6, 0.5]),
            merge_key=("axes_geometry", self.axes_id),
        )
        self.assertTrue(res.ok)
        self.assertEqual(stack.count(), base_count + 2)

        # Undo bounds change
        stack.undo()
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["bounds"], initial_bounds)
        pos = target.get_position()
        self.assertAlmostEqual(pos.x0, initial_bounds[0], places=5)

        # Undo manual switch (returns to grid)
        stack.undo()
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["mode"], "grid")
        self.assertTrue(target.get_in_layout())
        self.assertIsNotNone(target.get_subplotspec())

        # Redo manual switch
        stack.redo()
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["mode"], "manual")
        self.assertEqual(state.data["geometry"]["bounds"], initial_bounds)
        self.assertFalse(target.get_in_layout())

        # Redo bounds change
        stack.redo()
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"]["bounds"], [0.15, 0.2, 0.6, 0.5])

    def test_fault_injection_rollback(self):
        # Initial grid state
        initial_state = self._state(self.axes_id)
        self.assertEqual(initial_state.data["geometry"], {"mode": "grid"})

        # Injected error during mutation
        with patch.object(
            self.canvas.component_registry.get(self.axes_id),
            "apply_mutation",
            side_effect=RuntimeError("injected fault"),
        ):
            res = self.service.switch_to_manual(self.axes_id)
            self.assertEqual(res.status, ChangeStatus.REJECTED)

        # State and target remain untouched
        state = self._state(self.axes_id)
        self.assertEqual(state.data["geometry"], {"mode": "grid"})
        target = self._target(self.axes_id)
        self.assertTrue(target.get_in_layout())
        self.assertIsNotNone(target.get_subplotspec())

    def test_post_state_validation_failure_restores_state_and_runtime(self):
        target = self._target(self.axes_id)
        before = self.service.capture_runtime((target,))[0]

        with patch.object(
            self.canvas,
            "validate_component_snapshot",
            side_effect=RuntimeError("post-state fault"),
        ):
            result = self.service.switch_to_manual(self.axes_id)

        self.assertIs(result.status, ChangeStatus.REJECTED)
        self.assertIn("post-state fault", result.message)
        self.assertEqual(self._state(self.axes_id).data["geometry"], {"mode": "grid"})
        self.assertIs(target.get_subplotspec(), before.subplotspec)
        self.assertEqual(target.get_in_layout(), before.in_layout)
        self.assertEqual(
            tuple(target.get_position().bounds),
            tuple(before.active_position.bounds),
        )

    def test_manual_geometry_save_restore_projects_runtime(self):
        bounds = [0.17, 0.21, 0.58, 0.49]
        self.assertTrue(self.service.switch_to_manual(self.axes_id).ok)
        self.assertTrue(self.service.set_manual_bounds(self.axes_id, bounds).ok)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual-geometry.mygui.json"
            save_project_snapshot(path, self.window.figure_window)
            restored = MainWindow()
            try:
                restore_project_snapshot(
                    path,
                    restored.table,
                    restored.figure_window,
                )
                canvas = restored.figure_window.current_canva
                controller = canvas.component_registry.query(
                    kind=ComponentKind.AXES
                )[0]
                target = controller.resolve_target()
                self.assertEqual(
                    controller.state.data["geometry"],
                    {"mode": "manual", "bounds": bounds},
                )
                self.assertIsNone(target.get_subplotspec())
                self.assertFalse(target.get_in_layout())
                for actual, expected in zip(target.get_position().bounds, bounds):
                    self.assertAlmostEqual(actual, expected, places=6)
            finally:
                restored.close_without_prompt()
                self.app.processEvents()

    def test_shared_axes_remain_independently_positionable(self):
        first_id, second_id = self.canvas.create_axes_layout(
            AxesLayoutSpec.grid(
                1,
                2,
                share_x=ShareMode.ALL,
                share_y=ShareMode.ALL,
            )
        )
        first = self._target(first_id)
        second = self._target(second_id)
        self.assertTrue(first.get_shared_x_axes().joined(first, second))
        self.assertTrue(first.get_shared_y_axes().joined(first, second))

        self.assertTrue(self.service.switch_to_manual(first_id).ok)
        self.assertTrue(
            self.service.set_manual_bounds(first_id, [0.08, 0.12, 0.36, 0.72]).ok
        )

        self.assertEqual(self._state(first_id).data["geometry"]["mode"], "manual")
        self.assertEqual(self._state(second_id).data["geometry"], {"mode": "grid"})
        self.assertIsNone(first.get_subplotspec())
        self.assertFalse(first.get_in_layout())
        self.assertIsNotNone(second.get_subplotspec())
        self.assertTrue(second.get_in_layout())

    def test_layout_projection_failure_restores_grid_and_manual_axes(self):
        layout_id = self._state(self.axes_id).data["subplot"]["layout_id"]

        for mode in ("grid", "manual"):
            with self.subTest(mode=mode):
                if mode == "manual":
                    self.assertTrue(self.service.switch_to_manual(self.axes_id).ok)
                    self.assertTrue(
                        self.service.set_manual_bounds(
                            self.axes_id,
                            [0.18, 0.22, 0.54, 0.46],
                        ).ok
                    )
                before_definition = deepcopy(
                    self.canvas.axes_layout_service.layout_definition(layout_id)
                )
                target = self._target(self.axes_id)
                before_runtime = self.service.capture_runtime((target,))[0]
                spec = AxesLayoutSpec.grid(
                    1,
                    1,
                    left=0.2,
                    right=0.8,
                    layout_id=layout_id,
                )
                with patch.object(
                    self.canvas,
                    "validate_component_snapshot",
                    side_effect=RuntimeError("layout projection fault"),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "layout projection fault",
                    ):
                        self.canvas.axes_layout_service.update_geometry(spec)

                self.assertEqual(
                    self.canvas.axes_layout_service.layout_definition(layout_id),
                    before_definition,
                )
                self.assertIs(target.get_subplotspec(), before_runtime.subplotspec)
                self.assertEqual(target.get_in_layout(), before_runtime.in_layout)
                self.assertEqual(
                    tuple(target.get_position().bounds),
                    tuple(before_runtime.active_position.bounds),
                )
                if mode == "manual":
                    self.assertTrue(self.service.return_to_grid(self.axes_id).ok)


if __name__ == "__main__":
    unittest.main()
