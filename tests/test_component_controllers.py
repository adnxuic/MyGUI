from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from matplotlib.ticker import (
    AsinhLocator,
    AutoLocator,
    AutoMinorLocator,
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
    build_locator,
    default_minor_locator_for_scale,
    default_scale_for_name,
    locator_from_axis,
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
        with self.assertRaisesRegex(
            ComponentValidationError,
            "Chart component order values must be unique",
        ):
            chart_registry.validate_tree()


if __name__ == "__main__":
    unittest.main()
