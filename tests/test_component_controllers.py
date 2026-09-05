from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from matplotlib.ticker import (
    AsinhLocator,
    AutoLocator,
    AutoMinorLocator,
    FormatStrFormatter,
    IndexLocator,
    LogitLocator,
    LogLocator,
    SymmetricalLogLocator,
)

from mygui.figuremodify.components import (
    CONTROLLER_TYPES,
    ROLES_BY_KIND,
    AxesController,
    ChangeStatus,
    ComponentEventKind,
    ComponentKind,
    ComponentLocator,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    DataPlotController,
    EditorKind,
    GridController,
    LegendController,
    PropertySpec,
    ReferenceMarksController,
    ScatterController,
    SpineController,
    TickGroupController,
    TickLabelGroupController,
    UpdateImpact,
    create_controller,
    register_figure_components,
)
from mygui.figuremodify.components.property_values import (
    DEFAULT_MINOR_LOCATOR,
    build_formatter,
    build_locator,
    default_minor_locator_for_scale,
    default_scale_for_name,
    formatter_from_axis,
    locator_from_axis,
    normalize_formatter,
)
from mygui.figuremodify.component_services import (
    AxisTickPreviewRenderer,
    AxisTickSettingsService,
)


def state(
    component_id: str,
    kind: ComponentKind | str,
    role: ComponentRole | str,
    parent_id: str | None = None,
    *,
    order: int = 0,
    selector: dict | None = None,
    properties: dict | None = None,
    data: dict | None = None,
) -> ComponentState:
    return ComponentState(
        id=component_id,
        kind=kind,
        role=role,
        parent_id=parent_id,
        order=order,
        selector=selector or {},
        properties=properties or {},
        data=data or {},
    )


class ComponentModelTests(unittest.TestCase):
    def test_locator_requires_v10_selectors_and_explicit_artist_bindings(self):
        figure = Figure()
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [0.0, 1.0])
        line.set_gid("line-id")
        parents = {"figure-id": figure, "axes-id": axes}
        locator = ComponentLocator(parents.get)

        old_axes = state(
            "axes-old",
            ComponentKind.AXES,
            ComponentRole.AXES,
            "figure-id",
            selector={"axes_index": 0},
        )
        old_axis = state(
            "axis-old",
            ComponentKind.AXIS,
            ComponentRole.X_AXIS,
            "axes-id",
            selector={},
        )
        unbound_line = state(
            "line-id",
            ComponentKind.LINE,
            ComponentRole.LINE,
            "axes-id",
            selector={"object_id": "line-id", "index": 0},
        )
        self.assertIsNone(locator.resolve(old_axes))
        self.assertIsNone(locator.resolve(old_axis))
        self.assertIsNone(locator.resolve(unbound_line))
        locator.bind("line-id", line)
        self.assertIs(locator.resolve(unbound_line), line)

    def test_state_round_trip_is_strict_and_json_friendly(self):
        original = state(
            "line-1",
            "line",
            "data_plot",
            "axes-1",
            selector={"object_id": "line-1"},
            properties={"range": (1.0, 2.0)},
            data={"values": (3, 4)},
        )
        encoded = original.to_dict()
        self.assertEqual(encoded["kind"], "line")
        self.assertEqual(encoded["properties"]["range"], [1.0, 2.0])
        self.assertEqual(encoded["data"]["values"], [3, 4])
        json.dumps(encoded)
        self.assertEqual(ComponentState.from_dict(encoded).to_dict(), encoded)

        invalid = dict(encoded)
        invalid["unexpected"] = True
        with self.assertRaises(ComponentValidationError):
            ComponentState.from_dict(invalid)
        invalid = dict(encoded)
        invalid["role"] = "legend"
        with self.assertRaises(ComponentValidationError):
            ComponentState.from_dict(invalid)

    def test_property_spec_normalizes_and_validates_values(self):
        spec = PropertySpec(
            "linewidth",
            float,
            1.0,
            validator=lambda value: value >= 0,
            impact=UpdateImpact.LEGEND | UpdateImpact.REDRAW,
        )
        self.assertEqual(spec.normalize(2), 2.0)
        self.assertEqual(spec.metadata()["impact"], ["legend", "redraw"])
        with self.assertRaises(ComponentValidationError):
            spec.normalize(-1)
        with self.assertRaises(ComponentValidationError):
            spec.normalize(True)

    def test_property_spec_editor_contract_rejects_typos(self):
        spec = PropertySpec("visible", bool, True, editor="check")
        self.assertIs(spec.editor, EditorKind.BOOL)
        self.assertEqual(spec.metadata()["editor"], "bool")
        with self.assertRaisesRegex(ComponentValidationError, "unknown editor"):
            PropertySpec("color", str, "black", editor="colro")

    def test_scale_defaults_produce_roundtrippable_minor_locators(self):
        expected_types = {
            "linear": AutoMinorLocator,
            "log": LogLocator,
            "symlog": SymmetricalLogLocator,
            "asinh": AsinhLocator,
            "logit": LogitLocator,
        }
        for scale_name, locator_type in expected_types.items():
            with self.subTest(scale=scale_name):
                scale = default_scale_for_name(scale_name)
                spec = default_minor_locator_for_scale(scale)
                locator = build_locator(spec)
                self.assertIsInstance(locator, locator_type)
                if isinstance(locator, AutoMinorLocator):
                    locator.ndivs = "auto"
                self.assertEqual(
                    locator_from_axis(
                        locator,
                        DEFAULT_MINOR_LOCATOR,
                        minor=True,
                        scale=scale,
                    ),
                    spec,
                )
        self.assertEqual(
            default_minor_locator_for_scale(
                default_scale_for_name("logit")
            )["params"]["nbins"],
            "auto",
        )

    def test_v22_index_locator_and_format_str_formatter_are_safe_round_trips(self):
        locator_spec = {
            "kind": "index",
            "params": {"base": 2.5, "offset": -1.0},
        }
        formatter_spec = {
            "kind": "format_str",
            "params": {"format": "value=%1.2f%%"},
        }
        locator = build_locator(locator_spec)
        formatter = build_formatter(formatter_spec)
        self.assertIsInstance(locator, IndexLocator)
        self.assertIsInstance(formatter, FormatStrFormatter)
        self.assertEqual(
            locator_from_axis(locator, {}, minor=False), locator_spec
        )
        self.assertEqual(
            formatter_from_axis(formatter, {}, minor=False), formatter_spec
        )
        for unsafe in ("%s %s", "%(x)f", "%*f", "%.*f", "%", "plain"):
            with self.subTest(format=unsafe), self.assertRaises(
                ComponentValidationError
            ):
                normalize_formatter(
                    {"kind": "format_str", "params": {"format": unsafe}}
                )

    def test_controller_mapping_covers_every_controlled_kind_and_role(self):
        expected = {
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        self.assertEqual(set(CONTROLLER_TYPES), expected)


class ComponentControllerContractTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.line, = self.axes.plot(
            [0.0, 1.0],
            [1.0, 2.0],
            label="line",
        )
        self.scatter = self.axes.scatter(
            [0.0, 1.0],
            [2.0, 3.0],
            label="scatter",
        )
        self.axes.legend(loc="upper right")
        self.registry = register_figure_components(
            self.figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        self.axes_id = "figure/axes/0"
        line_state = state(
            "plot-1",
            "line",
            "data_plot",
            self.axes_id,
            order=100,
            selector={"object_id": "plot-1"},
            properties=DataPlotController.default_properties(),
            data={
                "x_ref": {
                    "project_id": "project",
                    "sheet_id": "sheet",
                    "column_id": "x",
                },
                "y_ref": {
                    "project_id": "project",
                    "sheet_id": "sheet",
                    "column_id": "y",
                },
            },
        )
        scatter_state = state(
            "scatter-1",
            "scatter",
            "scatter",
            self.axes_id,
            order=101,
            selector={"object_id": "scatter-1"},
            properties=ScatterController.default_properties(),
        )
        self.line_controller = DataPlotController(
            line_state, target=self.line
        )
        self.scatter_controller = ScatterController(
            scatter_state, target=self.scatter
        )
        self.registry.register(self.line_controller, target=self.line)
        self.registry.register(self.scatter_controller, target=self.scatter)
        self.figure.canvas.draw_idle = Mock()

    def test_registry_ordering_uses_live_metadata_without_payload_clones(self):
        before = self.line_controller.state
        controllers = self.registry.query()
        expected = sorted(controllers, key=lambda item: (item.state.order, item.component_id))
        with patch.object(ComponentState, "clone", side_effect=AssertionError("metadata copied payload")):
            self.assertEqual(self.registry.query(), expected)
            self.assertEqual(self.line_controller.order, before.order)
        changed = before.clone(order=102)
        self.line_controller.restore(changed)
        self.assertEqual(self.line_controller.order, 102)
        ordered = self.registry.query(kind=ComponentKind.LINE)
        self.assertIn(self.line_controller, ordered)
        self.line_controller.restore(before)
        self.assertEqual(self.line_controller.state, before)
        self.registry.validate_tree()

    def test_tree_validation_reuses_one_snapshot_per_controller(self):
        before = [controller.state for controller in self.registry.query()]
        copied = []
        original_clone = ComponentState.clone

        def clone(state, **kwargs):
            copied.append(state.id)
            return original_clone(state, **kwargs)

        with patch.object(ComponentState, "clone", clone):
            self.registry.validate_tree()
        self.assertCountEqual(copied, [state.id for state in before])
        self.assertEqual([controller.state for controller in self.registry.query()], before)

    def test_line_property_change_snapshot_restore_and_invalid_rollback(self):
        change = self.line_controller.set_property("linestyle", "Dashed")
        self.assertEqual(change.status, ChangeStatus.APPLIED)
        self.assertEqual(self.line.get_linestyle(), "--")
        self.assertEqual(
            change.after.properties["linestyle"],
            {"kind": "preset", "value": "--"},
        )
        self.assertIn("linewidth", change.after.properties)

        snapshot = self.line_controller.snapshot()
        self.line_controller.set_property("color", "#ff0000")
        restored = self.line_controller.restore(snapshot)
        self.assertTrue(restored.ok)
        self.assertEqual(self.line.get_color(), snapshot.properties["color"])

        old_width = self.line.get_linewidth()
        rejected = self.line_controller.set_property("linewidth", -2)
        self.assertEqual(rejected.status, ChangeStatus.REJECTED)
        self.assertEqual(self.line.get_linewidth(), old_width)

    def test_multi_property_setter_failure_restores_previously_applied_values(self):
        snapshot = self.line_controller.snapshot()
        candidate = snapshot.clone(
            properties={
                **snapshot.properties,
                "color": "#ff0000",
                "linewidth": 3.0,
            }
        )
        original_set_linewidth = self.line.set_linewidth

        def fail_set_linewidth(_value):
            raise RuntimeError("simulated setter failure")

        self.line.set_linewidth = fail_set_linewidth
        try:
            change = self.line_controller.apply_state(candidate)
        finally:
            self.line.set_linewidth = original_set_linewidth

        self.assertEqual(change.status, ChangeStatus.REJECTED)
        self.assertEqual(
            self.line_controller.snapshot().properties["color"],
            snapshot.properties["color"],
        )
        self.assertEqual(self.line.get_color(), snapshot.properties["color"])

    def test_redraw_failure_rejects_and_rolls_back_artist_and_state(self):
        previous = self.line_controller.snapshot()
        self.figure.canvas.draw_idle = Mock(
            side_effect=RuntimeError("simulated render failure")
        )
        change = self.line_controller.set_property("color", "#ff0000")
        self.assertEqual(change.status, ChangeStatus.REJECTED)
        self.assertEqual(
            self.line_controller.snapshot().properties["color"],
            previous.properties["color"],
        )
        self.assertEqual(self.line.get_color(), previous.properties["color"])

    def test_empty_data_is_valid_and_mismatched_data_is_rejected(self):
        empty = self.line_controller.set_xy_data([], [])
        self.assertEqual(empty.status, ChangeStatus.EMPTY)
        self.assertEqual(len(self.line.get_xdata()), 0)

        rejected = self.line_controller.set_xy_data([1, 2], [3])
        self.assertEqual(rejected.status, ChangeStatus.REJECTED)
        self.assertEqual(len(self.line.get_xdata()), 0)

        scatter_empty = self.scatter_controller.set_xy_data([], [])
        self.assertEqual(scatter_empty.status, ChangeStatus.EMPTY)
        self.assertEqual(self.scatter.get_offsets().shape, (0, 2))

    def test_batched_autoscale_syncs_axes_state_and_emits_one_state_event(self):
        axes_controller = self.registry.get(self.axes_id)
        events = []
        unsubscribe = self.registry.subscribe(
            events.append,
            kinds=(ComponentEventKind.CHANGED,),
        )
        try:
            with self.registry.batch_updates():
                self.assertTrue(
                    self.line_controller.set_xy_data(
                        [10.0, 20.0],
                        [100.0, 200.0],
                    ).ok
                )
                self.assertTrue(
                    self.line_controller.set_xy_data(
                        [30.0, 40.0],
                        [300.0, 400.0],
                    ).ok
                )
        finally:
            unsubscribe()

        state_events = [
            event
            for event in events
            if event.component_id == self.axes_id
        ]
        self.assertEqual(len(state_events), 1)
        self.assertIsNone(state_events[0].change)
        self.assertNotEqual(state_events[0].before, state_events[0].after)
        self.assertEqual(
            tuple(axes_controller.state.properties["xlim"]),
            tuple(self.axes.get_xlim()),
        )
        self.assertEqual(
            tuple(axes_controller.state.properties["ylim"]),
            tuple(self.axes.get_ylim()),
        )

    def test_reenabling_autoscale_relimits_and_syncs_axes_state(self):
        controller = self.registry.get(self.axes_id)
        expected_impact = (
            UpdateImpact.RELIM
            | UpdateImpact.AUTOSCALE
            | UpdateImpact.REDRAW
        )
        self.assertEqual(
            controller.property_specs()["autoscalex_on"].impact,
            expected_impact,
        )
        self.assertEqual(
            controller.property_specs()["autoscaley_on"].impact,
            expected_impact,
        )
        self.assertTrue(controller.set_property("autoscalex_on", False).ok)
        self.assertTrue(controller.set_property("autoscaley_on", False).ok)
        self.assertTrue(controller.set_property("xlim", (0.0, 10.0)).ok)
        self.assertTrue(controller.set_property("ylim", (0.0, 10.0)).ok)
        self.line.set_data([0.0, 20.0], [0.0, 20.0])

        x_change = controller.set_property("autoscalex_on", True)
        self.assertTrue(x_change.ok)
        self.assertEqual(x_change.impacts, expected_impact)
        self.assertAlmostEqual(self.axes.get_xlim()[0], -1.0)
        self.assertAlmostEqual(self.axes.get_xlim()[1], 21.0)
        self.assertEqual(tuple(controller.state.properties["xlim"]), (-1.0, 21.0))
        self.assertEqual(tuple(self.axes.get_ylim()), (0.0, 10.0))

        y_change = controller.set_property("autoscaley_on", True)
        self.assertTrue(y_change.ok)
        self.assertEqual(y_change.impacts, expected_impact)
        self.assertAlmostEqual(self.axes.get_ylim()[0], -1.0)
        self.assertAlmostEqual(self.axes.get_ylim()[1], 21.0)
        self.assertEqual(tuple(controller.state.properties["ylim"]), (-1.0, 21.0))

    def test_complete_axes_state_preserves_explicit_limits_with_autoscale_on(self):
        controller = self.registry.get(self.axes_id)
        desired = controller.state.clone(
            properties={
                **controller.state.properties,
                "xlim": (2.0, 4.0),
                "ylim": (3.0, 5.0),
                "autoscalex_on": True,
                "autoscaley_on": True,
            }
        )

        change = controller.apply_state(desired)

        self.assertTrue(change.ok)
        self.assertEqual(tuple(self.axes.get_xlim()), (2.0, 4.0))
        self.assertEqual(tuple(self.axes.get_ylim()), (3.0, 5.0))
        self.assertTrue(self.axes.get_autoscalex_on())
        self.assertTrue(self.axes.get_autoscaley_on())
        self.assertEqual(change.impacts & UpdateImpact.AUTOSCALE, UpdateImpact.NONE)

    def test_scatter_marker_and_size_are_persistent_properties(self):
        marker_change = self.scatter_controller.set_property("marker", "^")
        size_change = self.scatter_controller.set_property("size", 64)
        self.assertTrue(marker_change.ok)
        self.assertTrue(size_change.ok)
        self.assertEqual(
            self.scatter_controller.snapshot().properties["marker"],
            {"kind": "symbol", "value": "^"},
        )
        self.assertEqual(float(self.scatter.get_sizes()[0]), 64.0)

    def test_scatter_color_and_global_alpha_remain_separate(self):
        self.assertTrue(
            self.scatter_controller.set_property(
                "edgecolor", "#123456"
            ).ok
        )
        self.assertTrue(
            self.scatter_controller.set_property("alpha", 0.5).ok
        )
        snapshot = self.scatter_controller.snapshot()
        self.assertEqual(snapshot.properties["edgecolor"], "#123456")
        self.assertEqual(snapshot.properties["alpha"], 0.5)

    def test_delete_is_idempotent_and_removes_registry_membership(self):
        self.figure.canvas.draw_idle.reset_mock()
        cleaned = []
        self.registry.add_cleanup_callback(
            "plot-1", lambda removed: cleaned.append(removed.id)
        )
        first = self.line_controller._delete_component()
        second = self.line_controller._delete_component()
        self.assertEqual(first.status, ChangeStatus.DELETED)
        self.assertEqual(second.status, ChangeStatus.NOOP)
        self.assertNotIn("plot-1", self.registry)
        self.assertNotIn(self.line, self.axes.lines)
        self.figure.canvas.draw_idle.assert_called_once()
        self.assertEqual(
            [text.get_text() for text in self.axes.get_legend().get_texts()],
            ["scatter"],
        )
        self.assertEqual(cleaned, ["plot-1"])

    def test_registry_query_batch_redraw_and_atomic_property_rollback(self):
        color_targets = self.registry.query(
            parent_id=self.axes_id,
            recursive=True,
            capabilities="color",
        )
        self.assertIn(self.line_controller, color_targets)
        self.assertIn(self.scatter_controller, color_targets)
        orders = [item.state.order for item in color_targets]
        self.assertEqual(orders, sorted(orders))

        self.figure.canvas.draw_idle.reset_mock()
        with self.registry.batch_updates():
            self.line_controller.set_property("color", "#ff0000")
            self.scatter_controller.set_property("color", "#00ff00")
        self.figure.canvas.draw_idle.assert_called_once()

        previous = self.line_controller.snapshot().properties["color"]
        changes = self.registry.set_properties(
            [
                ("plot-1", "color", "#0000ff"),
                ("scatter-1", "size", -1),
            ]
        )
        self.assertEqual(changes[-1].status, ChangeStatus.REJECTED)
        self.assertEqual(
            self.line_controller.snapshot().properties["color"], previous
        )


class ReferenceMarksControllerTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.artist = LineCollection(
            [],
            transform=self.axes.get_xaxis_transform(),
        )
        self.axes.add_collection(self.artist, autolim=False)
        self.component_state = state(
            "reference-marks-1",
            ComponentKind.REFERENCE_MARKS,
            ComponentRole.REFLECTION_POSITIONS,
            "axes-1",
            selector={"object_id": "reference-marks-1"},
            properties=ReferenceMarksController.default_properties(),
            data={
                "positions": [15.2, 15.2, 22.9],
                "position_ref": None,
                "placement": {"kind": "fixed"},
            },
        )
        self.controller = ReferenceMarksController(
            self.component_state,
            target=self.artist,
        )
        self.assertTrue(self.controller.apply_state(self.component_state).ok)

    def test_positions_preserve_order_duplicates_and_empty_data(self):
        self.assertEqual(
            self.controller.snapshot().data["positions"],
            [15.2, 15.2, 22.9],
        )
        self.assertEqual(len(self.artist.get_segments()), 3)
        first_segment = self.artist.get_segments()[0]
        self.assertEqual(first_segment[:, 0].tolist(), [15.2, 15.2])
        self.assertAlmostEqual(first_segment[0, 1], 0.08)
        self.assertAlmostEqual(first_segment[1, 1], 0.105)

        change = self.controller.apply_state(
            self.controller.state.clone(
                data={
                    "positions": [],
                    "position_ref": None,
                    "placement": {"kind": "fixed"},
                }
            )
        )
        self.assertEqual(change.status, ChangeStatus.EMPTY)
        self.assertEqual(
            self.controller.snapshot().data,
            {
                "positions": [],
                "position_ref": None,
                "placement": {"kind": "fixed"},
            },
        )
        self.assertEqual(len(self.artist.get_segments()), 0)

    def test_tiny_positive_height_is_valid_and_geometry_bounds_are_strict(self):
        self.assertTrue(self.controller.set_property("height", 1e-9).ok)
        self.assertEqual(
            self.controller.snapshot().properties["height"],
            1e-9,
        )
        self.assertEqual(
            self.controller.set_property("height", 0.0).status,
            ChangeStatus.REJECTED,
        )
        self.assertTrue(self.controller.set_property("baseline", 0.9).ok)
        self.assertTrue(self.controller.set_property("height", 0.1).ok)
        self.assertEqual(
            self.controller.set_property("height", 0.1001).status,
            ChangeStatus.REJECTED,
        )

    def test_malformed_nonfinite_and_unknown_data_are_rejected_atomically(self):
        before = self.controller.snapshot()
        before_segments = [item.copy() for item in self.artist.get_segments()]
        invalid_values = (
            "15.2, 22.9",
            [15.2, True],
            [15.2, float("nan")],
            [15.2, float("inf")],
            [[15.2]],
        )
        for positions in invalid_values:
            with self.subTest(positions=positions):
                change = self.controller.apply_state(
                    before.clone(data={"positions": positions})
                )
                self.assertEqual(change.status, ChangeStatus.REJECTED)
                self.assertEqual(self.controller.snapshot(), before)
                self.assertEqual(
                    [item.tolist() for item in self.artist.get_segments()],
                    [item.tolist() for item in before_segments],
                )

        change = self.controller.apply_state(
            before.clone(data={"positions": [], "unknown": 1})
        )
        self.assertEqual(change.status, ChangeStatus.REJECTED)
        self.assertEqual(self.controller.snapshot(), before)

    def test_selector_properties_and_target_type_are_exact(self):
        with self.assertRaises(ComponentValidationError):
            ReferenceMarksController(
                self.component_state.clone(
                    selector={"object_id": "reference-marks-1", "index": 0}
                ),
                target=self.artist,
            )
        with self.assertRaises(ComponentValidationError):
            ReferenceMarksController(
                self.component_state.clone(
                    properties={
                        **self.component_state.properties,
                        "unknown": True,
                    }
                ),
                target=self.artist,
            )

        wrong_target = ReferenceMarksController(
            self.component_state,
            target=self.axes.plot([0.0], [0.0])[0],
        )
        with self.assertRaises(ComponentValidationError):
            wrong_target.snapshot()

    def test_arbitrary_external_line_collection_is_not_discovered(self):
        figure = Figure()
        axes = figure.subplots()
        external = LineCollection([((1.0, 0.0), (1.0, 1.0))])
        external.set_gid("external-line-collection")
        axes.add_collection(external)

        registry = register_figure_components(figure)

        self.assertEqual(
            registry.query(kind=ComponentKind.REFERENCE_MARKS),
            [],
        )
        self.assertNotIn("external-line-collection", registry)


class SemanticControllerTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.subplots()
        self.axes.minorticks_on()
        self.line, = self.axes.plot([0, 1], [1, 2], label="old")
        self.axes.legend(loc="lower right", frameon=False)
        self.registry = register_figure_components(
            self.figure,
            id_factory=lambda path: path,
            include_artists=True,
        )
        self.figure.canvas.draw_idle = Mock()

    def _one(self, controller_type, **selector):
        matches = [
            controller
            for controller in self.registry.query()
            if isinstance(controller, controller_type)
            and all(
                controller.state.selector.get(key) == value
                for key, value in selector.items()
            )
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_axis_tick_settings_commit_is_atomic_and_preview_is_isolated(self):
        axis = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = self.registry.get(axis.state.parent_id)
        service = AxisTickSettingsService(
            self.registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        opening = service.snapshot(axis.component_id)
        with self.assertRaisesRegex(ValueError, "finite"):
            service.validate(replace(opening, limits=(0.0, float("nan"))))
        fixed = replace(
            opening,
            major=replace(
                opening.major,
                locator={
                    "kind": "fixed",
                    "params": {"locations": [0.0, 0.5, 1.0], "nbins": None},
                },
                formatter={
                    "kind": "fixed",
                    "params": {"labels": ["zero", "half", "one"]},
                },
                tick_properties={
                    **opening.major.tick_properties,
                    "direction": "in",
                },
            ),
        )
        preview = AxisTickPreviewRenderer().render(fixed)
        self.assertTrue(preview.png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(axis.state, opening.expected_states[0])

        result = service.apply(fixed)
        self.assertTrue(result.committed, result.message)
        self.assertEqual(axis.state.properties["major_locator"]["kind"], "fixed")
        self.assertEqual(axis.state.properties["major_formatter"]["kind"], "fixed")
        self.assertEqual(
            self._one(TickGroupController, axis="x", level="major")
            .state.properties["direction"],
            "in",
        )

        current = service.snapshot(axis.component_id)
        invalid = replace(
            current,
            major=replace(
                current.major,
                formatter={
                    "kind": "fixed",
                    "params": {"labels": ["only one"]},
                },
            ),
        )
        before = axis.state
        rejected = service.apply(invalid)
        self.assertFalse(rejected.committed)
        self.assertEqual(axis.state, before)

    def test_axis_tick_settings_reports_an_incomplete_appearance_subtree(self):
        axis = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = self.registry.get(axis.state.parent_id)
        service = AxisTickSettingsService(
            self.registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )

        with (
            patch.object(service.registry, "find_one", return_value=None),
            self.assertRaisesRegex(
                ValueError, "Axis tick component subtree is incomplete"
            ),
        ):
            service._appearance(axis.component_id, "major")

    def test_axis_tick_symlog_defaults_keep_minor_subs_independent(self):
        axis = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = self.registry.get(axis.state.parent_id)
        service = AxisTickSettingsService(
            self.registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        opening = service.snapshot(axis.component_id)

        defaults = service.scale_defaults(
            replace(
                opening,
                scale=default_scale_for_name("symlog"),
            )
        )

        self.assertEqual(defaults.major.locator["params"]["subs"], [1.0])
        self.assertIsNone(defaults.minor.locator["params"]["subs"])
        self.assertIsNot(defaults.major.locator, defaults.minor.locator)

    def test_axis_tick_preview_applies_multialignment(self):
        from matplotlib.text import Text

        axis = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = self.registry.get(axis.state.parent_id)
        service = AxisTickSettingsService(
            self.registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        opening = service.snapshot(axis.component_id)
        candidate = replace(
            opening,
            major=replace(
                opening.major,
                label_properties={
                    **opening.major.label_properties,
                    "multialignment": "left",
                },
            ),
        )
        alignments = []
        original = Text.set_multialignment

        def recording_set_multialignment(label, value):
            alignments.append(value)
            return original(label, value)

        with patch.object(
            Text,
            "set_multialignment",
            new=recording_set_multialignment,
        ):
            preview = AxisTickPreviewRenderer().render(candidate)

        self.assertTrue(preview.png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("left", alignments)

    def test_axis_tick_settings_rejects_stale_opening_snapshot(self):
        axis = next(
            controller
            for controller in self.registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = self.registry.get(axis.state.parent_id)
        service = AxisTickSettingsService(
            self.registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        opening = service.snapshot(axis.component_id)
        self.assertTrue(axis.set_property("offset_visible", False).ok)
        result = service.apply(opening)
        self.assertFalse(result.committed)
        self.assertIn("reopen", result.message)

    def test_axis_tick_settings_syncs_shared_tickers_and_rolls_back_mid_commit(self):
        figure = Figure()
        first_axes, second_axes = figure.subplots(2, 1, sharex=True)
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        owners = tuple(registry.query(kind=ComponentKind.AXES))
        selected_axis = next(
            controller
            for controller in registry.query(kind=ComponentKind.AXIS)
            if controller.state.parent_id == owners[0].component_id
            and controller.state.selector == {"axis": "x"}
        )
        service = AxisTickSettingsService(
            registry,
            linked_axes=lambda _axes_id, _dimension: owners,
        )
        opening = service.snapshot(selected_axis.component_id)
        candidate = replace(
            opening,
            major=replace(
                opening.major,
                locator={
                    "kind": "fixed",
                    "params": {"locations": [0.0, 1.0], "nbins": None},
                },
                formatter={
                    "kind": "fixed",
                    "params": {"labels": ["zero", "one"]},
                },
                tick_properties={
                    **opening.major.tick_properties,
                    "direction": "in",
                },
            ),
        )
        linked_axes = [
            next(
                controller
                for controller in registry.query(kind=ComponentKind.AXIS)
                if controller.state.parent_id == owner.component_id
                and controller.state.selector == {"axis": "x"}
            )
            for owner in owners
        ]
        selected_target = selected_axis.resolve_target()
        original_setter = selected_target.set_tick_params
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected shared-axis failure")
            return original_setter(*args, **kwargs)

        before = {item.component_id: item.state for item in linked_axes}
        with patch.object(
            selected_target,
            "set_tick_params",
            side_effect=fail_once,
        ):
            rejected = service.apply(candidate)
        self.assertFalse(rejected.committed)
        self.assertTrue(rejected.rollback_complete)
        for item in linked_axes:
            self.assertEqual(item.state, before[item.component_id], item.component_id)
        self.assertIs(
            first_axes.xaxis.get_major_locator(),
            second_axes.xaxis.get_major_locator(),
        )

        fresh = service.snapshot(selected_axis.component_id)
        committed = service.apply(replace(candidate, expected_states=fresh.expected_states))
        self.assertTrue(committed.committed, committed.message)
        self.assertTrue(
            all(
                item.state.properties["major_locator"]["kind"] == "fixed"
                for item in linked_axes
            )
        )

    def test_minor_visibility_roundtrips_through_pending_tick_parameters(self):
        figure = Figure()
        axes = figure.subplots()
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )

        def one(controller_type):
            return next(
                controller
                for controller in registry.query()
                if isinstance(controller, controller_type)
                and controller.state.selector
                == {"axis": "x", "level": "minor"}
            )

        ticks = one(TickGroupController)
        labels = one(TickLabelGroupController)
        grid = one(GridController)
        self.assertEqual(axes.xaxis.get_minor_ticks(), [])

        self.assertTrue(ticks.set_property("primary_visible", False).ok)
        self.assertFalse(ticks.state.properties["primary_visible"])
        self.assertFalse(axes.xaxis._minor_tick_kw["tick1On"])
        self.assertTrue(ticks.set_property("primary_visible", True).ok)
        self.assertTrue(ticks.state.properties["primary_visible"])
        self.assertTrue(axes.xaxis._minor_tick_kw["tick1On"])

        self.assertTrue(labels.set_property("primary_visible", False).ok)
        self.assertFalse(labels.state.properties["primary_visible"])
        self.assertFalse(axes.xaxis._minor_tick_kw["label1On"])
        self.assertTrue(labels.set_property("primary_visible", True).ok)
        self.assertTrue(labels.state.properties["primary_visible"])
        self.assertTrue(axes.xaxis._minor_tick_kw["label1On"])

        self.assertTrue(grid.set_property("visible", True).ok)
        self.assertTrue(grid.state.properties["visible"])
        self.assertTrue(axes.xaxis._minor_tick_kw["gridOn"])
        self.assertEqual(axes.xaxis.get_minor_ticks(), [])

    def test_tick_label_and_grid_styles_survive_tick_recreation(self):
        ticks = self._one(TickGroupController, axis="x", level="major")
        labels = self._one(
            TickLabelGroupController, axis="x", level="major"
        )
        grid = self._one(GridController, axis="x", level="major")

        self.assertTrue(ticks.set_property("direction", "in").ok)
        self.assertTrue(labels.set_property("rotation", 35).ok)
        self.assertTrue(grid.set_property("visible", True).ok)
        self.assertTrue(grid.set_property("linestyle", "Dashed").ok)

        self.axes.xaxis.set_major_locator(AutoLocator())
        self.axes.xaxis.reset_ticks()
        self.figure.canvas.draw()
        recreated = self.axes.xaxis.get_major_ticks()
        self.assertTrue(recreated)
        self.assertTrue(all(tick._tickdir == "in" for tick in recreated))
        self.assertTrue(
            all(tick.label1.get_rotation() == 35 for tick in recreated)
        )
        self.assertTrue(
            all(
                tick.gridline.get_linestyle() == "--"
                for tick in recreated
                if tick.gridline.get_visible()
            )
        )

    def test_tick_label_state_replay_restores_nonstandard_text_styles(self):
        labels = self._one(
            TickLabelGroupController, axis="x", level="major"
        )
        bbox = {
            "enabled": True,
            "boxstyle": "round",
            "facecolor": "#ffffff",
            "edgecolor": "#000000",
            "linewidth": 1.0,
            "line_pattern": {"kind": "preset", "value": "-"},
            "alpha": None,
            "fill": True,
            "hatch": None,
            "pad": 0.3,
        }
        self.assertTrue(labels.set_property("fontweight", "bold").ok)
        self.assertTrue(labels.set_property("fontstyle", "italic").ok)
        self.assertTrue(labels.set_property("bbox", bbox).ok)
        authoritative = labels.state

        self.axes.xaxis.reset_ticks()
        recreated = self.axes.xaxis.get_major_ticks()
        self.assertTrue(recreated)
        self.assertTrue(
            all(tick.label1.get_bbox_patch() is None for tick in recreated)
        )

        replayed = labels.apply_state(authoritative)

        self.assertTrue(replayed.ok, replayed.message)
        for tick in self.axes.xaxis.get_major_ticks():
            for label in (tick.label1, tick.label2):
                self.assertEqual(label.get_fontweight(), "bold")
                self.assertEqual(label.get_fontstyle(), "italic")
                self.assertIsNotNone(label.get_bbox_patch())

    def test_tick_label_fontfamily_is_one_string_in_state_and_artist(self):
        labels = self._one(
            TickLabelGroupController,
            axis="x",
            level="major",
        )

        result = labels.set_property(
            "fontfamily",
            ["DejaVu Sans", "sans-serif"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(labels.state.properties["fontfamily"], "DejaVu Sans")
        self.assertEqual(
            labels.read_state().properties["fontfamily"],
            "DejaVu Sans",
        )
        self.assertTrue(
            all(
                tick.label1.get_fontfamily()[0] == "DejaVu Sans"
                for tick in self.axes.xaxis.get_major_ticks()
            )
        )

    def test_axis_label_position_uses_axes_coordinates_after_resize(self):
        label = next(
            controller
            for controller in self.registry.query(role=ComponentRole.X_LABEL)
        )

        self.assertTrue(label.set_property("position", (0.5, -0.1)).ok)
        target = label.resolve_target()
        self.assertEqual(target.get_position(), (0.5, -0.1))
        self.assertIs(target.get_transform(), self.axes.transAxes)

        self.figure.canvas.draw()
        before = target.get_transform().transform(target.get_position())
        self.figure.set_size_inches(8.0, 6.0)
        self.figure.canvas.draw()
        after = target.get_transform().transform(target.get_position())

        self.assertIs(target.get_transform(), self.axes.transAxes)
        self.assertEqual(target.get_position(), (0.5, -0.1))
        self.assertNotEqual(tuple(before), tuple(after))
        self.assertEqual(
            tuple(after),
            tuple(self.axes.transAxes.transform((0.5, -0.1))),
        )

    def test_spine_axes_and_text_controllers_apply_real_artist_state(self):
        spine = self._one(SpineController, name="left")
        title = self.registry.get("figure/axes/0/title")
        axes_controller = next(
            item
            for item in self.registry.query(kind=ComponentKind.AXES)
        )
        self.assertIsInstance(axes_controller, AxesController)

        self.assertTrue(spine.set_property("linewidth", 2.5).ok)
        self.assertTrue(title.set_property("text", "Updated title").ok)
        self.assertTrue(axes_controller.set_property("xlim", (10, -10)).ok)
        self.assertEqual(
            self.axes.spines["left"].get_linewidth(), 2.5
        )
        self.assertEqual(self.axes.get_title(), "Updated title")
        self.assertEqual(self.axes.get_xlim(), (10.0, -10.0))

        figure_controller = self.registry.get("figure")
        self.assertTrue(
            figure_controller.set_property("size_inches", (8.0, 5.0)).ok
        )
        self.assertEqual(
            list(self.figure.get_size_inches()), [8.0, 5.0]
        )

    def test_spine_bounds_can_return_to_automatic_none_state(self):
        spine = self._one(SpineController, name="left")

        self.assertTrue(spine.set_property("bounds", (0.2, 0.8)).ok)
        self.assertEqual(self.axes.spines["left"].get_bounds(), (0.2, 0.8))
        self.assertTrue(spine.set_property("bounds", None).ok)
        self.assertIsNone(self.axes.spines["left"].get_bounds())
        self.assertIsNone(spine.snapshot().properties["bounds"])

    def test_legend_controller_resolves_rebuilt_legend_and_preserves_style(self):
        legend = self._one(LegendController)
        line = self.registry.get("figure/axes/0/line/0")
        self.assertTrue(legend.set_property("location", "upper left").ok)
        label_font = deepcopy(legend.state.properties["label_font"])
        label_font["size"] = 13.0
        self.assertTrue(legend.set_property("label_font", label_font).ok)
        self.assertTrue(legend.set_property("visible", False).ok)

        self.assertTrue(line.set_property("label", "new").ok)
        rebuilt = legend.resolve_target()
        self.assertIs(rebuilt, self.axes.get_legend())
        self.assertFalse(rebuilt.get_visible())
        self.assertEqual(rebuilt.get_texts()[0].get_fontsize(), 13)
        self.assertEqual(
            legend.snapshot().properties["location"],
            {"kind": "preset", "value": "upper left"},
        )

    def test_legend_frame_color_and_alpha_remain_separate(self):
        legend = self._one(LegendController)
        self.assertTrue(
            legend.set_property("facecolor", "#123456").ok
        )
        self.assertTrue(
            legend.set_property("framealpha", 0.5).ok
        )
        snapshot = legend.snapshot()
        self.assertEqual(snapshot.properties["facecolor"], "#123456")
        self.assertEqual(snapshot.properties["framealpha"], 0.5)

    def test_empty_legend_keeps_persisted_label_font(self):
        figure = Figure()
        axes = figure.subplots()
        axes.legend([], [])
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        legend = next(
            controller
            for controller in registry.query(kind=ComponentKind.LEGEND)
        )

        label_font = deepcopy(legend.state.properties["label_font"])
        label_font["size"] = 17.0
        change = legend.set_property("label_font", label_font)

        self.assertTrue(change.ok)
        self.assertEqual(
            legend.snapshot().properties["label_font"]["size"],
            17.0,
        )

    def test_fixed_semantic_delete_hides_without_removing_tree_node(self):
        title = self.registry.get("figure/axes/0/title")
        x_axis = self.registry.get("figure/axes/0/axis/x")
        legend = self._one(LegendController)

        for controller in (title, x_axis, legend):
            change = controller._delete_component()
            self.assertTrue(change.ok)
            self.assertIn(controller.component_id, self.registry)
            self.assertFalse(controller.state.properties["visible"])

        self.registry.validate_tree()

    def test_generic_line_data_updates_are_always_persisted(self):
        line = self.registry.get("figure/axes/0/line/0")

        change = line.set_xy_data([2.0, 3.0], [4.0, 5.0])

        self.assertTrue(change.ok)
        self.assertEqual(line.state.data["x"], [2.0, 3.0])
        self.assertEqual(line.state.data["y"], [4.0, 5.0])

    def test_hidden_legend_state_restores_without_a_live_artist(self):
        figure = Figure()
        axes = figure.subplots()
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        legend = next(
            controller
            for controller in registry.query(kind=ComponentKind.LEGEND)
        )
        self.assertIsNone(axes.get_legend())

        candidate = legend.state.clone(
            properties={
                **legend.state.properties,
                "visible": False,
                "location": [0.25, 0.75],
                "ncols": 2,
                "facecolor": "red",
            }
        )
        change = legend.apply_state(candidate)

        self.assertEqual(change.status, ChangeStatus.APPLIED)
        self.assertEqual(
            legend.state.properties["location"],
            {"kind": "point", "x": 0.25, "y": 0.75},
        )
        self.assertEqual(legend.state.properties["ncols"], 2)
        self.assertEqual(legend.state.properties["facecolor"], "#ff0000")
        self.assertEqual(
            legend.snapshot().properties,
            legend.state.properties,
        )

        previous = legend.state
        invalid = legend.apply_state(
            previous.clone(properties={**previous.properties, "ncols": 0})
        )
        self.assertEqual(invalid.status, ChangeStatus.REJECTED)
        self.assertEqual(legend.state, previous)

        visible = legend.apply_state(
            previous.clone(properties={**previous.properties, "visible": True})
        )
        self.assertEqual(visible.status, ChangeStatus.REJECTED)
        self.assertEqual(legend.state, previous)

    def test_factory_builds_required_v10_hierarchy_and_deterministic_paths(self):
        self.registry.validate_tree()
        x_axis = self.registry.get("figure/axes/0/axis/x")
        major_tick = self.registry.get(
            "figure/axes/0/axis/x/tick/major"
        )
        tick_label = self.registry.get(
            "figure/axes/0/axis/x/tick/major/label"
        )
        grid = self.registry.get(
            "figure/axes/0/axis/x/grid/major"
        )
        x_label = self.registry.get("figure/axes/0/axis/x/label")
        self.assertEqual(major_tick.state.parent_id, x_axis.component_id)
        self.assertEqual(tick_label.state.parent_id, major_tick.component_id)
        self.assertEqual(grid.state.parent_id, x_axis.component_id)
        self.assertEqual(x_label.state.parent_id, x_axis.component_id)
        self.assertEqual(
            self.registry.get("figure").state.selector,
            {"scope": "figure"},
        )

    def test_factory_and_create_controller_expose_reusable_templates(self):
        generic_line = self.registry.get("figure/axes/0/line/0")
        recreated = create_controller(
            generic_line.state,
            target=self.line,
        )
        self.assertEqual(
            recreated.property_specs(),
            generic_line.property_specs(),
        )
        copied = deepcopy(recreated.state.to_dict())
        self.assertEqual(copied["kind"], "line")
        self.assertEqual(copied["role"], "line")

    def test_factory_assigns_unique_chart_order_across_multiple_axes(self):
        figure = Figure()
        left, right = figure.subplots(1, 2)
        left.plot([0, 1], [1, 2])
        right.plot([0, 1], [2, 3])
        left.scatter([0], [0])
        right.scatter([1], [1])

        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=True,
        )

        registry.validate_tree()
        orders = [
            controller.state.order
            for controller in registry.query()
            if controller.state.kind
            in {ComponentKind.LINE, ComponentKind.SCATTER}
        ]
        self.assertEqual(len(orders), len(set(orders)))

    def test_registry_rejects_invalid_parent_kind(self):
        source = self.registry.get("figure/axes/0/line/0").state
        invalid = source.clone(
            id="line-with-figure-parent",
            parent_id="figure",
            order=source.order + 100,
            selector={"object_id": "line-with-figure-parent"},
        )
        self.registry.register(
            create_controller(invalid, target=self.line),
            target=self.line,
        )

        with self.assertRaisesRegex(
            ComponentValidationError,
            "cannot have parent kind",
        ):
            self.registry.validate_tree()

    def test_registry_rejects_duplicate_fixed_semantic_selector(self):
        source = self.registry.get(
            "figure/axes/0/spine/left"
        ).state
        duplicate = source.clone(
            id="duplicate-left-spine",
            order=source.order + 100,
        )
        self.registry.register(
            create_controller(
                duplicate,
                target=self.axes.spines["left"],
            ),
            target=self.axes.spines["left"],
        )

        with self.assertRaisesRegex(
            ComponentValidationError,
            "Duplicate semantic selector",
        ):
            self.registry.validate_tree()

    def test_registry_requires_complete_fixed_axes_semantics(self):
        registry = register_figure_components(
            self.figure,
            id_factory=lambda path: f"incomplete/{path}",
            include_artists=False,
        )
        registry._forget_subtree(
            "incomplete/figure/axes/0/legend"
        )

        with self.assertRaisesRegex(
            ComponentValidationError,
            "exactly one Legend",
        ):
            registry.validate_tree()

    def test_registry_rejects_axes_index_and_chart_order_conflicts(self):
        figure = Figure()
        figure.subplots(2, 1)
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        second_axes = registry.get("figure/axes/1")
        moved = second_axes.apply_state(
            second_axes.snapshot().clone(selector={"index": 3})
        )
        self.assertTrue(moved.ok)
        with self.assertRaisesRegex(
            ComponentValidationError,
            "contiguous from zero",
        ):
            registry.validate_tree()

        chart_registry = register_figure_components(
            self.figure,
            id_factory=lambda path: f"orders/{path}",
            include_artists=True,
        )
        source = chart_registry.get(
            "orders/figure/axes/0/line/0"
        ).state
        duplicate_order = source.clone(
            id="duplicate-chart-order",
            selector={"object_id": "duplicate-chart-order"},
        )
        chart_registry.register(
            create_controller(duplicate_order, target=self.line),
            target=self.line,
        )
class ControllerValidationTests(unittest.TestCase):
    def test_controller_validators_and_normalizers_edge_cases(self):
        from mygui.figuremodify.components.controllers import (
            _anchor,
            _connectors,
            _in_axes_range,
            _in_axes_rectangle,
            _legend_anchor,
            _line_pattern,
            _marker_spec,
            _normalize_color,
            _optional_extent,
            _optional_sketch,
            _pair,
            _primary_font_family,
            _rectangle,
            _url_sequence,
        )

        # _primary_font_family
        self.assertEqual(_primary_font_family("Arial"), "Arial")
        self.assertEqual(_primary_font_family(["Helvetica", "Arial"]), "Helvetica")
        with self.assertRaises(ComponentValidationError):
            _primary_font_family("")
        with self.assertRaises(ComponentValidationError):
            _primary_font_family([])
        with self.assertRaises(ComponentValidationError):
            _primary_font_family([""])
        with self.assertRaises(ComponentValidationError):
            _primary_font_family(123)

        # _url_sequence
        self.assertEqual(_url_sequence(["http://a", None]), ("http://a", None))
        with self.assertRaises(ComponentValidationError):
            _url_sequence("http://not-an-array")
        with self.assertRaises(ComponentValidationError):
            _url_sequence(123)

        # _line_pattern & _marker_spec
        self.assertIsNotNone(_line_pattern("--"))
        self.assertIsNotNone(_line_pattern((0, (2, 2))))
        self.assertIsNotNone(_marker_spec((5, 0, 45)))
        self.assertIsNotNone(_marker_spec("o"))

        # _connectors
        with self.assertRaises(ComponentValidationError):
            _connectors([1, 2])

        # _optional_sketch
        self.assertIsNone(_optional_sketch(None))
        self.assertEqual(_optional_sketch((1.0, 2.0, 3.0)), (1.0, 2.0, 3.0))
        with self.assertRaises(ComponentValidationError):
            _optional_sketch((1, 2))
        with self.assertRaises(ComponentValidationError):
            _optional_sketch((float("nan"), 1, 1))
        with self.assertRaises(ComponentValidationError):
            _optional_sketch((-1, 1, 1))

        # _normalize_color
        self.assertEqual(_normalize_color("#FF0000"), "#ff0000")
        with self.assertRaises(ComponentValidationError):
            _normalize_color("invalid_color_xyz")

        # _pair & _rectangle
        self.assertEqual(_pair((1, 2)), (1.0, 2.0))
        with self.assertRaises(ComponentValidationError):
            _pair((1,))
        self.assertEqual(_rectangle((0, 0, 1, 2)), (0.0, 0.0, 1.0, 2.0))
        with self.assertRaises(ComponentValidationError):
            _rectangle((0, 0, -1, 1))

        # _anchor & _legend_anchor
        self.assertEqual(_anchor("NW"), "NW")
        self.assertEqual(_anchor((0.2, 0.8)), (0.2, 0.8))
        with self.assertRaises(ComponentValidationError):
            _anchor("INVALID")
        with self.assertRaises(ComponentValidationError):
            _anchor((1.5, 0.5))

        self.assertIsNone(_legend_anchor(None))
        self.assertEqual(_legend_anchor((0.5, 0.5)), (0.5, 0.5))
        self.assertEqual(_legend_anchor((0.0, 0.0, 1.0, 1.0)), (0.0, 0.0, 1.0, 1.0))
        with self.assertRaises(ComponentValidationError):
            _legend_anchor((1,))
        with self.assertRaises(ComponentValidationError):
            _legend_anchor((float("inf"), 0.5))

        # _in_axes_range & _in_axes_rectangle & _optional_extent
        self.assertEqual(_in_axes_range((1, 2)), (1.0, 2.0))
        with self.assertRaises(ComponentValidationError):
            _in_axes_range((1, 1))
        with self.assertRaises(ComponentValidationError):
            _in_axes_range((float("inf"), 2))
        with self.assertRaises(ComponentValidationError):
            _in_axes_rectangle((0, 0, float("nan"), 1))

        self.assertIsNone(_optional_extent(None))
        self.assertEqual(_optional_extent((0, 1, 0, 1)), (0.0, 1.0, 0.0, 1.0))
        with self.assertRaises(ComponentValidationError):
            _optional_extent((0, 1, 0))
        with self.assertRaises(ComponentValidationError):
            _optional_extent((1, 1, 2, 3))

    def test_in_axes_image_validation_and_decoding_errors(self):
        import base64
        import io
        from PIL import Image
        from mygui.figuremodify.components.controllers import (
            _validate_in_axes_image_data,
            decode_in_axes_image,
        )

        # Missing fields
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({})

        # Empty filename
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({
                "filename": "",
                "mime_type": "image/png",
                "payload_base64": "AA==",
            })

        # Directory path in filename
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({
                "filename": "subdir/test.png",
                "mime_type": "image/png",
                "payload_base64": "AA==",
            })

        # Unsupported MIME
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({
                "filename": "test.gif",
                "mime_type": "image/gif",
                "payload_base64": "AA==",
            })

        # Empty payload
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({
                "filename": "test.png",
                "mime_type": "image/png",
                "payload_base64": "",
            })

        # Invalid base64
        with self.assertRaises(ComponentValidationError):
            _validate_in_axes_image_data({
                "filename": "test.png",
                "mime_type": "image/png",
                "payload_base64": "not_base64!!!",
            })

        # Corrupted payload decode
        with self.assertRaises(ComponentValidationError):
            decode_in_axes_image({
                "filename": "test.png",
                "mime_type": "image/png",
                "payload_base64": base64.b64encode(b"not_an_image").decode("ascii"),
            })

        # Valid 2x2 PNG decode
        img = Image.new("RGBA", (2, 2), color=(255, 0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        payload = base64.b64encode(buf.getvalue()).decode("ascii")

        # MIME mismatch
        with self.assertRaises(ComponentValidationError):
            decode_in_axes_image({
                "filename": "test.png",
                "mime_type": "image/jpeg",
                "payload_base64": payload,
            })

        # Valid decode
        array = decode_in_axes_image({
            "filename": "test.png",
            "mime_type": "image/png",
            "payload_base64": payload,
        })
        self.assertEqual(array.shape, (2, 2, 4))

    def test_axes_spine_tick_legend_controllers_extended_properties(self):
        figure = Figure()
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [0.0, 1.0], label="line1")
        registry = register_figure_components(figure, id_factory=lambda path: path)

        axes_ctrl = registry.get("figure/axes/0")
        self.assertIsNotNone(axes_ctrl)
        axes_ctrl.set_property("aspect", "equal")
        axes_ctrl.set_property("box_aspect", 1.0)
        axes_ctrl.set_property("xlim", (0.0, 10.0))
        axes_ctrl.set_property("ylim", (0.0, 10.0))

        # SpineController
        for spine_ctrl in [c for c in registry._controllers.values() if c.state.role == ComponentRole.SPINE]:
            spine_ctrl.set_property("visible", True)
            spine_ctrl.set_property("linewidth", 2.0)
            spine_ctrl.set_property("position", {"kind": "outward", "value": 5.0})

        # TickGroupController
        for tick_ctrl in [c for c in registry._controllers.values() if c.state.role == ComponentRole.MAJOR_TICK]:
            tick_ctrl.set_property("direction", "inout")


        # LegendController
        for legend_ctrl in [c for c in registry._controllers.values() if c.state.role == ComponentRole.LEGEND]:
            legend_ctrl.set_property("ncols", 2)
            legend_ctrl.set_property("frameon", True)
            legend_ctrl.set_property("framealpha", 0.8)
            legend_ctrl.set_property("shadow", True)
            legend_ctrl.set_property("fancybox", True)






if __name__ == "__main__":
    unittest.main()
