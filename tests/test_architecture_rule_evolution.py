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
from mygui.figuremodify.components.controllers._helpers import (
    bind_closed_property_handlers,
    closed_handler_subset,
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


def _mccabe(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler),
        ):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.IfExp):
            score += 1
        elif isinstance(child, ast.comprehension):
            score += len(child.ifs)
    return score


def _named_functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    found[f"{node.name}.{child.name}"] = child
    return found


def _class_function(path: Path, class_name: str, function_name: str) -> ast.FunctionDef:
    return _named_functions(path)[f"{class_name}.{function_name}"]


def _module_function(path: Path, function_name: str) -> ast.FunctionDef:
    return _named_functions(path)[function_name]


CANVAS_COMPLEXITY_WARNING_MAX = 15
ADD_STAR_MCCABE_MAX = 2
REFACTORED_DISPATCH_MCCABE_MAX = 5
NEW_HOTSPOT_MCCABE_CEILINGS = {
    (
        ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
        "ChartCreationStager.create_errorbar",
    ): 27,
    (
        ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
        "ChartCreationStager.stage_scatter",
    ): 12,
    (
        ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
        "ChartCreationStager.normalize_batch_refs",
    ): 12,
    (
        ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
        "ChartCreationStager.commit_chart_batch",
    ): 11,
    (
        ROOT / "mygui/widgets/figure_canvas/chart_creation.py",
        "ChartCreationStager.create_interpolate_curve",
    ): 10,
    (
        ROOT / "mygui/widgets/figure_canvas/element_creation.py",
        "ElementCreationStager.create_field_2d",
    ): 20,
    (
        ROOT / "mygui/widgets/figure_canvas/element_creation.py",
        "ElementCreationStager.handle_mpl_button_press",
    ): 20,
    (
        ROOT / "mygui/widgets/figure_canvas/element_creation.py",
        "ElementCreationStager.create_annotation",
    ): 14,
    (
        ROOT / "mygui/widgets/figure_canvas/element_creation.py",
        "ElementCreationStager.create_in_axes",
    ): 13,
    (
        ROOT / "mygui/widgets/figure_canvas/element_creation.py",
        "ElementCreationStager.create_colorbar",
    ): 13,
    (
        ROOT / "mygui/figuremodify/components/_delete_transaction.py",
        "rollback_delete_transaction",
    ): 25,
    (
        ROOT / "mygui/figuremodify/components/_delete_transaction.py",
        "prepare_delete_transaction",
    ): 23,
    (
        ROOT / "mygui/figuremodify/components/_delete_transaction.py",
        "apply_delete_transaction",
    ): 12,
    (
        ROOT / "mygui/figuremodify/components/_delete_transaction.py",
        "publish_delete_transaction",
    ): 9,
    (
        ROOT
        / "mygui/widgets/fig_control_window/component_editors/editor_factories.py",
        "_create_enum_editor",
    ): 6,
    (
        ROOT
        / "mygui/widgets/fig_control_window/component_editors/editor_factories.py",
        "validate_editor_factories",
    ): 5,
    (
        ROOT
        / "mygui/widgets/fig_control_window/component_editors/editor_factories.py",
        "_create_number_editor",
    ): 4,
    (
        ROOT / "mygui/figuremodify/components/controllers/_helpers.py",
        "bind_closed_property_handlers",
    ): 3,
}


class RefactoredHotspotComplexityTests(unittest.TestCase):
    def test_delete_transaction_wrapper_stays_a_thin_facade(self):
        method = _class_function(
            ROOT / "mygui/figuremodify/components/registry.py",
            "ComponentRegistry",
            "delete_transaction",
        )
        self.assertLessEqual(method.end_lineno - method.lineno + 1, 30)
        calls = [
            node.func.id
            for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("run_delete_transaction", calls)

    def test_canvas_complexity_warnings_stay_within_the_first_round_cap(self):
        functions = _named_functions(
            ROOT / "mygui/widgets/figure_canvas/py_figure_canves.py"
        )
        warnings = [
            (name, _mccabe(node))
            for name, node in functions.items()
            if name.startswith("PyFigureCanvas.") and _mccabe(node) > 10
        ]
        self.assertLessEqual(len(warnings), CANVAS_COMPLEXITY_WARNING_MAX, warnings)
        add_star = [
            (name, _mccabe(node))
            for name, node in functions.items()
            if name.startswith("PyFigureCanvas.add_")
        ]
        self.assertTrue(add_star)
        for name, score in add_star:
            with self.subTest(name=name):
                self.assertLessEqual(score, ADD_STAR_MCCABE_MAX)

    def test_new_hotspot_complexity_does_not_worsen(self):
        for (path, qualname), ceiling in NEW_HOTSPOT_MCCABE_CEILINGS.items():
            with self.subTest(path=path.name, function=qualname):
                score = _mccabe(_named_functions(path)[qualname])
                self.assertLessEqual(score, ceiling)


class RefactoredDispatchComplexityTests(unittest.TestCase):
    def test_editor_and_property_dispatch_stay_below_complexity_cap(self):
        cases = (
            (
                ROOT / "mygui/widgets/fig_control_window/component_editors/base.py",
                "ComponentEditorBase",
                "_create_editor",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/legend.py",
                "LegendController",
                "_read_property",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/legend.py",
                "LegendController",
                "_write_property",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/in_axes.py",
                "InAxesController",
                "_read_property",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/in_axes.py",
                "InAxesController",
                "_write_property",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/secondary_axis.py",
                "SecondaryAxisController",
                "_read_property",
            ),
            (
                ROOT / "mygui/figuremodify/components/controllers/secondary_axis.py",
                "SecondaryAxisController",
                "_write_property",
            ),
        )
        for path, class_name, function_name in cases:
            with self.subTest(path=path.name, function=function_name):
                function = _class_function(path, class_name, function_name)
                self.assertLessEqual(_mccabe(function), REFACTORED_DISPATCH_MCCABE_MAX)

        factory = _module_function(
            ROOT
            / "mygui/widgets/fig_control_window/component_editors/editor_factories.py",
            "create_editor_widget",
        )
        self.assertLessEqual(_mccabe(factory), REFACTORED_DISPATCH_MCCABE_MAX)


class ClosedPropertyHandlerTests(unittest.TestCase):
    def test_legend_in_axes_and_secondary_axis_handlers_are_closed(self):
        from mygui.figuremodify.components.controllers import (
            ImageInAxesController,
            LegendController,
            SecondaryAxisController,
            ZoomInAxesController,
        )
        from mygui.figuremodify.components.controllers import in_axes
        from mygui.figuremodify.components.controllers import legend
        from mygui.figuremodify.components.controllers import secondary_axis
        from mygui.figuremodify.components.errors import ComponentValidationError
        from mygui.figuremodify.components.models import PropertySpec

        bind_closed_property_handlers(
            specs=LegendController.PROPERTY_SPECS,
            readers=legend._LEGEND_READERS,
            writers=legend._LEGEND_WRITERS,
            owner="LegendController",
        )
        bind_closed_property_handlers(
            specs=SecondaryAxisController.PROPERTY_SPECS,
            readers=secondary_axis._SECONDARY_AXIS_READERS,
            writers=secondary_axis._SECONDARY_AXIS_WRITERS,
            owner="SecondaryAxisController",
        )
        for controller_type in (ZoomInAxesController, ImageInAxesController):
            bind_closed_property_handlers(
                specs=controller_type.PROPERTY_SPECS,
                readers=closed_handler_subset(
                    in_axes._IN_AXES_READERS,
                    controller_type.PROPERTY_SPECS,
                    owner=controller_type.__name__,
                ),
                writers=closed_handler_subset(
                    in_axes._IN_AXES_WRITERS,
                    controller_type.PROPERTY_SPECS,
                    owner=controller_type.__name__,
                ),
                owner=controller_type.__name__,
            )

        unknown = PropertySpec("not_a_real_property", bool, False, editor="check")
        legend_controller = LegendController.__new__(LegendController)
        with self.assertRaises(ComponentValidationError):
            legend_controller._read_property(object(), unknown)
        with self.assertRaises(ComponentValidationError):
            legend_controller._write_property(object(), unknown, False)

    def test_missing_handler_tables_fail_at_bind_time(self):
        from mygui.figuremodify.components.models import PropertySpec

        specs = (PropertySpec("visible", bool, True, editor="check"),)
        with self.assertRaises(RuntimeError):
            bind_closed_property_handlers(
                specs=specs,
                readers={},
                writers={"visible": lambda *_args: None},
                owner="MissingReader",
            )
        with self.assertRaises(RuntimeError):
            closed_handler_subset(
                {},
                specs,
                owner="MissingSubset",
            )

