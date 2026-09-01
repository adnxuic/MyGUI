"""Investigate snapshot-read fallback without promoting a new CORE rule.

Classification: insufficient_evidence for a new CORE-COMPONENT-STATE rule.
Hidden Legend without a live artist is already a declared semantic contract.
Toolbar pan/zoom is project view history under CORE-PROJECT-HISTORY.
Generic missing-artist and property-getter failures still return cached
Controller state when ``strict=False``; this plan does not change that path.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure

from mygui.figuremodify.components import (
    CONTROLLER_TYPES,
    ComponentKind,
    ComponentNotFoundError,
    ComponentRole,
    ComponentState,
    LineController,
    register_figure_components,
)
from mygui.figuremodify.components import serialization as schema
from mygui.figuremodify.components._delete_transaction import (
    apply_delete_transaction,
    prepare_delete_transaction,
    publish_delete_transaction,
    rollback_delete_transaction,
    verify_delete_transaction,
)


ROOT = Path(__file__).resolve().parents[1]


class SchemaValidatorRegistryTests(unittest.TestCase):
    def test_parent_and_selector_validators_are_closed_over_controller_keys(self):
        keys = set(CONTROLLER_TYPES)
        self.assertEqual(set(schema._PARENT_KINDS), keys)
        self.assertEqual(set(schema._SELECTOR_VALIDATORS), keys)

    def test_selector_and_parent_validators_reject_invalid_payloads(self):
        figure = ComponentState(
            id="figure",
            kind=ComponentKind.FIGURE,
            role=ComponentRole.FIGURE,
            selector={"scope": "figure"},
        )
        axes = ComponentState(
            id="axes",
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
            parent_id="figure",
            selector={"index": True},
        )
        x_axis = ComponentState(
            id="x-axis",
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
            parent_id="axes",
            selector={"axis": "y"},
        )
        y_axis = ComponentState(
            id="y-axis",
            kind=ComponentKind.AXIS,
            role=ComponentRole.Y_AXIS,
            parent_id="axes",
            selector={"axis": "x"},
        )
        tick = ComponentState(
            id="tick",
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MAJOR_TICK,
            parent_id="x-axis",
            selector={"axis": "z", "level": "major"},
        )
        matched_tick = ComponentState(
            id="tick-match",
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MINOR_TICK,
            parent_id="x-axis",
            selector={"axis": "x", "level": "major"},
        )
        tick_label = ComponentState(
            id="tick-label",
            kind=ComponentKind.TICK_LABEL_GROUP,
            role=ComponentRole.MAJOR_TICK_LABEL,
            parent_id="tick",
            selector={"axis": "x", "level": "major"},
        )
        label = ComponentState(
            id="xlabel",
            kind=ComponentKind.TEXT,
            role=ComponentRole.X_LABEL,
            parent_id="x-axis",
            selector={"axis": "y"},
        )
        spine = ComponentState(
            id="spine",
            kind=ComponentKind.SPINE,
            role=ComponentRole.SPINE,
            parent_id="axes",
            selector={"name": "diagonal"},
        )
        line = ComponentState(
            id="line",
            kind=ComponentKind.LINE,
            role=ComponentRole.LINE,
            parent_id="axes",
            selector={"object_id": "other"},
        )
        annotation = ComponentState(
            id="ann",
            kind=ComponentKind.ANNOTATION,
            role=ComponentRole.ANNOTATION,
            parent_id="axes",
            selector={"object_id": "ann", "extra": 1},
        )
        parent_axis = ComponentState(
            id="x-axis",
            kind=ComponentKind.AXIS,
            role=ComponentRole.X_AXIS,
            parent_id="axes",
            selector={"axis": "x"},
        )
        parent_tick = ComponentState(
            id="tick",
            kind=ComponentKind.TICK_GROUP,
            role=ComponentRole.MAJOR_TICK,
            parent_id="x-axis",
            selector={"axis": "x", "level": "minor"},
        )

        with self.assertRaises(ValueError):
            schema.deterministic_component_id("", "figure/axes")
        with self.assertRaises(ValueError):
            schema.deterministic_component_id("project", "")
        with self.assertRaises(ValueError):
            schema._expect_dict([], "figure")
        with self.assertRaises(ValueError):
            schema._validate_axes_selector(axes, figure, "p")
        with self.assertRaises(ValueError):
            schema._validate_axis_selector(x_axis, axes, "p")
        with self.assertRaises(ValueError):
            schema._validate_axis_selector(y_axis, axes, "p")
        with self.assertRaises(ValueError):
            schema._validate_tick_or_grid_selector(tick, parent_axis, "p")
        tick.selector["axis"] = "y"
        with self.assertRaises(ValueError):
            schema._validate_tick_or_grid_selector(tick, parent_axis, "p")
        with self.assertRaises(ValueError):
            schema._validate_tick_or_grid_selector(matched_tick, parent_axis, "p")
        with self.assertRaises(ValueError):
            schema._validate_tick_or_grid_selector(tick_label, parent_tick, "p")
        tick_label.selector["level"] = "minor"
        parent_tick.selector["level"] = "minor"
        with self.assertRaises(ValueError):
            schema._validate_tick_or_grid_selector(tick_label, parent_tick, "p")
        with self.assertRaises(ValueError):
            schema._validate_axis_label_selector(label, parent_axis, "p")
        with self.assertRaises(ValueError):
            schema._validate_spine_selector(spine, axes, "p")
        with self.assertRaises(ValueError):
            schema._validate_object_id_selector(line, axes, "p")
        with self.assertRaises(ValueError):
            schema._validate_annotation_selector(annotation, axes, "p")
        with self.assertRaises(ValueError):
            schema._validate_parent(axes, None, "p")
        with self.assertRaises(ValueError):
            schema._validate_parent(axes, figure.clone(kind=ComponentKind.AXES), "p")
        figure.selector["scope"] = "project"
        with self.assertRaises(ValueError):
            schema._validate_parent(figure, None, "p")
        missing = schema._PARENT_KINDS.pop((ComponentKind.LINE, ComponentRole.LINE))
        try:
            with self.assertRaises(ValueError):
                schema._validate_parent(line, axes, "p")
        finally:
            schema._PARENT_KINDS[(ComponentKind.LINE, ComponentRole.LINE)] = missing



class DeleteTransactionPhaseTests(unittest.TestCase):
    def test_registry_delete_transaction_delegates_to_five_internal_phases(self):
        source = (
            ROOT / "mygui/figuremodify/components/_delete_transaction.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(
            names,
            {
                "prepare_delete_transaction",
                "apply_delete_transaction",
                "verify_delete_transaction",
                "rollback_delete_transaction",
                "publish_delete_transaction",
                "run_delete_transaction",
                "_failed_prepare",
            },
        )
        self.assertTrue(callable(prepare_delete_transaction))
        self.assertTrue(callable(apply_delete_transaction))
        self.assertTrue(callable(verify_delete_transaction))
        self.assertTrue(callable(rollback_delete_transaction))
        self.assertTrue(callable(publish_delete_transaction))


class SnapshotReadFallbackInvestigationTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.line, = self.axes.plot([0.0, 1.0], [1.0, 2.0], label="line")
        self.registry = register_figure_components(
            self.figure,
            id_factory=lambda path: path,
            include_artists=True,
        )

    def _line(self) -> LineController:
        return next(
            controller
            for controller in self.registry.query(kind=ComponentKind.LINE)
        )

    def test_hidden_legend_read_state_uses_cached_semantic_state(self):
        legend = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.LEGEND)
        )
        self.assertIsNone(self.axes.get_legend())
        cached = legend.state
        restored = legend.read_state(strict=False)
        self.assertEqual(restored.id, cached.id)
        self.assertEqual(restored.properties, cached.properties)
        with self.assertRaises(ComponentNotFoundError):
            legend.read_state(strict=True)

    def test_missing_line_artist_raises_and_callers_keep_cached_state(self):
        line = self._line()
        cached = line.state
        line.resolve_target().remove()
        self.registry.locator.unbind(line.component_id)
        with self.assertRaises(Exception):
            line.read_state(strict=False)
        try:
            restored = line.read_state()
        except Exception:
            restored = line.state
        self.assertEqual(restored.id, cached.id)
        self.assertEqual(restored.properties, cached.properties)

    def test_property_getter_failure_keeps_cached_state_unless_strict(self):
        line = self._line()
        cached = dict(line.state.properties)
        with patch.object(
            type(line),
            "_read_property",
            side_effect=RuntimeError("getter failed"),
        ):
            restored = line.read_state(strict=False)
            self.assertEqual(restored.properties, cached)
            with self.assertRaises(RuntimeError):
                line.read_state(strict=True)


class RefactoredHotspotComplexityTests(unittest.TestCase):
    def test_delete_transaction_wrapper_stays_a_thin_facade(self):
        source = (
            ROOT / "mygui/figuremodify/components/registry.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        registry = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ComponentRegistry"
        )
        method = next(
            node
            for node in registry.body
            if isinstance(node, ast.FunctionDef) and node.name == "delete_transaction"
        )
        self.assertLessEqual(method.end_lineno - method.lineno + 1, 30)
        calls = [
            node.func.id
            for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("run_delete_transaction", calls)
