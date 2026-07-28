import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QCheckBox, QComboBox, QLineEdit
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from code import status_messages
from code.database import ColumnRef, TableRepository
from code.figuremodify.component_services import (
    AxesCommandService,
    ChartDataService,
    FitService,
    FunctionCurveService,
    InterpolationService,
    TextRenderService,
)
from code.figuremodify.components import (
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FunctionCurveController,
    ScatterController,
    register_figure_components,
)
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from code.widgets.fig_control_window.component_editors import (
    ComponentEditorBase,
    ComponentEditorManager,
    DebouncedTextBinding,
    EditorContext,
    EditorRegistry,
    LineStyleEditor,
    NullableDoubleEditor,
    NumericTupleEditor,
    RangeEditor,
    ScatterStyleEditor,
    SpinePositionEditor,
    MessagePresenter,
    register_production_profiles,
)


class _FakeController:
    kind = "line"

    def __init__(self):
        self.state = {
            "properties": {
                "visible": True,
                "linewidth": 2.0,
                "style": "--",
                "label": "before",
                "color": "#112233",
            }
        }
        self.property_specs = {
            "visible": {"editor": "bool"},
            "linewidth": {
                "editor": "number",
                "minimum": 0.0,
                "maximum": 10.0,
                "step": 0.5,
            },
            "style": {
                "editor": "enum",
                "choices": {"Solid": "-", "Dashed": "--"},
            },
            "label": {"editor": "text", "debounce_ms": 1},
            "color": {"editor": "auto"},
        }
        self.calls = []

    def set_property(self, key, value):
        self.calls.append((key, value))
        if key == "label" and value == "reject":
            return False
        self.state["properties"][key] = value
        return True


def _editor_context(registry, repository, library):
    interpolation = InterpolationService(repository, registry)
    chart_data = ChartDataService(repository, registry)
    chart_data.interpolation_service = interpolation
    editor_registry = EditorRegistry()
    register_production_profiles(editor_registry)
    manager = ComponentEditorManager(registry, editor_registry)
    return EditorContext(
        registry=registry,
        color_library=library,
        messages=MessagePresenter(),
        editor_manager=manager,
        axes_commands=AxesCommandService(registry),
        function_curves=FunctionCurveService(registry),
        chart_data=chart_data,
        interpolation=interpolation,
        fitting=FitService(repository, registry),
        text_rendering=TextRenderService(registry),
    )


def _register_chart(
    registry,
    controller_type,
    component_id,
    role,
    artist,
    data,
):
    state = ComponentState(
        id=component_id,
        kind=(
            ComponentKind.SCATTER
            if role is ComponentRole.SCATTER
            else ComponentKind.LINE
        ),
        role=role,
        order=0,
        selector={"object_id": component_id},
        properties={},
        data=data,
    )
    return registry.register(
        controller_type(state),
        target=artist,
        require_parent=False,
    )


class ComponentEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_line_style_editor_maps_names_and_symbols(self):
        editor = LineStyleEditor("dashed")
        try:
            self.assertEqual(editor.style(), "--")
            editor.set_style("dashdot")
            self.assertEqual(editor.style(), "-.")
            editor.set_style(":")
            self.assertEqual(editor.style(), ":")
        finally:
            editor.close()

    def test_range_and_scatter_editors_sync_without_emitting(self):
        range_editor = RangeEditor(-1.0, 2.0)
        scatter_editor = ScatterStyleEditor("D", 15.0)
        range_calls = []
        marker_calls = []
        range_editor.rangeChanged.connect(lambda low, high: range_calls.append((low, high)))
        scatter_editor.markerChanged.connect(marker_calls.append)
        try:
            range_editor.set_range(3.0, 4.0)
            scatter_editor.set_marker("s")
            scatter_editor.set_size(25.0)
            self.assertEqual(range_editor.values(), (3.0, 4.0))
            self.assertEqual(scatter_editor.marker(), "s")
            self.assertEqual(scatter_editor.size(), 25.0)
            self.assertEqual(range_calls, [])
            self.assertEqual(marker_calls, [])
        finally:
            range_editor.close()
            scatter_editor.close()

    def test_debounced_binding_rolls_back_rejected_text(self):
        editor = QLineEdit("accepted")
        values = []

        def apply(value):
            values.append(value)
            return value != "bad"

        binding = DebouncedTextBinding(editor, apply, delay_ms=1)
        try:
            editor.setText("good")
            self.assertTrue(binding.flush())
            self.assertEqual(binding.last_valid_text, "good")
            editor.setText("bad")
            self.assertFalse(binding.flush())
            self.assertEqual(editor.text(), "good")
            self.assertEqual(values, ["good", "bad"])
        finally:
            editor.close()

    def test_success_messages_skip_noop_changes(self):
        editor = QLineEdit("before")
        events = []
        handler = lambda message, level: events.append((message, level))
        status_messages.set_status_handler(handler)
        results = iter(
            (
                SimpleNamespace(status="applied", message=""),
                SimpleNamespace(status="noop", message=""),
            )
        )
        binding = DebouncedTextBinding(
            editor,
            lambda _value: next(results),
            delay_ms=1,
        )
        try:
            editor.setText("applied")
            self.assertTrue(binding.flush())
            editor.setText("noop")
            self.assertTrue(binding.flush())
            self.assertEqual(events, [("Text updated.", "success")])
        finally:
            status_messages.clear_status_handler(handler)
            editor.close()

    def test_component_editor_generates_supported_property_widgets(self):
        controller = _FakeController()
        library = ColorLibrary()
        editor = ComponentEditorBase(controller, color_library=library)
        try:
            self.assertIsInstance(editor.editor("visible"), QCheckBox)
            self.assertIsInstance(editor.editor("style"), QComboBox)
            self.assertIsInstance(editor.editor("label"), QLineEdit)
            self.assertIsInstance(editor.editor("color"), ColorChoiceWidget)
            self.assertIs(editor.editor("color").color_library, library)

            editor.editor("visible").setChecked(False)
            editor.editor("linewidth").setValue(3.5)
            self.assertFalse(controller.state["properties"]["visible"])
            self.assertEqual(controller.state["properties"]["linewidth"], 3.5)

            label = editor.editor("label")
            label.setText("accepted")
            self.assertTrue(editor._text_bindings["label"].flush())
            label.setText("reject")
            self.assertFalse(editor._text_bindings["label"].flush())
            self.assertEqual(label.text(), "accepted")
        finally:
            editor.close()

    def test_component_editor_reports_applied_but_not_noop(self):
        controller = _FakeController()
        editor = ComponentEditorBase(controller, color_library=ColorLibrary())
        events = []
        handler = lambda message, level: events.append((message, level))
        status_messages.set_status_handler(handler)
        try:
            self.assertTrue(editor.apply_property("linewidth", 4.0))
            controller.set_property = lambda _key, _value: SimpleNamespace(
                status="noop",
                message="",
            )
            self.assertTrue(editor.apply_property("linewidth", 4.0))
            self.assertEqual(events, [("Linewidth updated.", "success")])
        finally:
            status_messages.clear_status_handler(handler)
            editor.close()

    def test_color_property_requires_injected_library(self):
        with self.assertRaisesRegex(ValueError, "ColorLibrary"):
            ComponentEditorBase(_FakeController())

    def test_editor_registry_uses_kind_and_fallback(self):
        class CustomEditor(ComponentEditorBase):
            pass

        registry = EditorRegistry()
        registry.register(ComponentKind.LINE, CustomEditor)
        controller = _FakeController()
        editor = registry.create(controller, color_library=ColorLibrary())
        try:
            self.assertIsInstance(editor, CustomEditor)
        finally:
            editor.close()

    def test_editor_registry_prefers_role_specific_registration(self):
        class KindEditor(ComponentEditorBase):
            pass

        class FitEditor(ComponentEditorBase):
            pass

        registry = EditorRegistry()
        registry.register(ComponentKind.LINE, KindEditor)
        registry.register(
            ComponentKind.LINE,
            FitEditor,
            role=ComponentRole.FIT_CURVE,
        )
        controller = _FakeController()
        controller.role = ComponentRole.FIT_CURVE
        editor = registry.create(
            controller,
            color_library=ColorLibrary(),
        )
        try:
            self.assertIsInstance(editor, FitEditor)
        finally:
            editor.close()

        registry.unregister(
            ComponentKind.LINE,
            role=ComponentRole.FIT_CURVE,
        )
        fallback_editor = registry.create(
            controller,
            color_library=ColorLibrary(),
        )
        try:
            self.assertIsInstance(fallback_editor, KindEditor)
        finally:
            fallback_editor.close()

    def test_editor_registry_requires_shared_color_library(self):
        with self.assertRaisesRegex(ValueError, "ColorLibrary"):
            EditorRegistry().create(_FakeController())

    def test_curve_panel_uses_controller_for_range_and_rolls_back_bad_expression(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [0.0, 1.0], label="curve")
        repository = TableRepository()
        registry = ComponentRegistry()
        controller = _register_chart(
            registry,
            FunctionCurveController,
            "curve",
            ComponentRole.FUNCTION_CURVE,
            line,
            {"expression": "x", "x_start": 0.0, "x_stop": 1.0},
        )
        library = ColorLibrary()
        context = _editor_context(registry, repository, library)
        editor = context.editor_manager.create(
            controller,
            context=context,
        )
        try:
            definition = editor.section("definition")
            appearance = editor.section("appearance")
            definition.x_start_input.setValue(-1.0)
            self.assertEqual(controller.state.data["x_start"], -1.0)

            definition.expression_input.setText("__import__('os')")
            self.assertFalse(definition.expression_change())
            self.assertEqual(definition.expression_input.text(), "x")

            style_combo = appearance.editor("linestyle")
            dashed_index = style_combo.findData("--")
            style_combo.setCurrentIndex(dashed_index)
            self.assertEqual(line.get_linestyle(), "--")
            self.assertEqual(
                controller.state.properties["linestyle"],
                "--",
            )
        finally:
            editor.close()
            context.editor_manager.close()

    def test_plot_and_scatter_panels_apply_reusable_style_controls(self):
        repository = TableRepository()
        project = repository.create_project("Data")
        sheet = next(iter(project.sheets.values()))
        sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0]])
        x_ref = ColumnRef(project.id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(project.id, sheet.id, sheet.columns[1].id)
        pair = repository.valid_pair(x_ref, y_ref)

        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot(pair.x, pair.y, "-", markersize=2.0, label="plot")
        scatter = axes.scatter(pair.x, pair.y, s=20.0, marker="o", label="scatter")
        registry = ComponentRegistry()
        refs = {"x_ref": x_ref.to_dict(), "y_ref": y_ref.to_dict()}
        plot_controller = _register_chart(
            registry,
            DataPlotController,
            "plot",
            ComponentRole.DATA_PLOT,
            line,
            refs,
        )
        scatter_controller = _register_chart(
            registry,
            ScatterController,
            "scatter",
            ComponentRole.SCATTER,
            scatter,
            refs,
        )
        library = ColorLibrary()
        context = _editor_context(registry, repository, library)
        plot_editor = context.editor_manager.create(
            plot_controller,
            context=context,
        )
        scatter_editor = context.editor_manager.create(
            scatter_controller,
            context=context,
        )
        try:
            plot_appearance = plot_editor.section("appearance")
            scatter_appearance = scatter_editor.section("appearance")
            plot_style = plot_appearance.editor("linestyle")
            plot_style.setCurrentIndex(
                plot_style.findData(":")
            )
            plot_appearance.editor("markersize").setValue(7.5)
            scatter_appearance.editor("marker").setCurrentText("s")
            scatter_appearance.editor("size").setValue(42.0)

            self.assertEqual(
                plot_controller.state.properties["linestyle"],
                ":",
            )
            self.assertEqual(
                plot_controller.state.properties["markersize"],
                7.5,
            )
            self.assertEqual(
                scatter_controller.state.properties["marker"],
                "s",
            )
            self.assertEqual(
                scatter_controller.state.properties["size"],
                42.0,
            )
        finally:
            plot_editor.close()
            scatter_editor.close()
            context.editor_manager.close()

    def test_all_first_party_controller_metadata_can_build_an_editor(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [1.0, 2.0], label="line")
        axes.scatter([0.0, 1.0], [2.0, 3.0], label="scatter")
        axes.legend()
        registry = register_figure_components(figure)
        library = ColorLibrary()
        editors = []
        try:
            editors = [
                ComponentEditorBase(controller, color_library=library)
                for controller in registry
            ]
            self.assertEqual(len(editors), len(registry))
            self.assertTrue(all(editor.editors() for editor in editors))
        finally:
            for editor in editors:
                editor.close()

    def test_first_party_structured_and_nullable_editors_apply_typed_values(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [1.0, 2.0], label="line")
        registry = register_figure_components(figure)
        library = ColorLibrary()

        axes_controller = next(
            controller
            for controller in registry
            if controller.state.role is ComponentRole.AXES
        )
        left_spine = next(
            controller
            for controller in registry
            if controller.state.role is ComponentRole.SPINE
            and controller.state.selector.get("name") == "left"
        )
        line_controller = next(
            controller
            for controller in registry
            if controller.state.kind is ComponentKind.LINE
        )
        axes_editor = ComponentEditorBase(
            axes_controller,
            color_library=library,
        )
        spine_editor = ComponentEditorBase(
            left_spine,
            color_library=library,
        )
        line_editor = ComponentEditorBase(
            line_controller,
            color_library=library,
        )
        try:
            position = axes_editor.editor("position")
            self.assertIsInstance(position, NumericTupleEditor)
            position.set_value((0.2, 0.2, 0.5, 0.5), emit=True)
            self.assertEqual(
                tuple(
                    round(float(value), 6)
                    for value in axes_controller.read_state().properties[
                        "position"
                    ]
                ),
                (0.2, 0.2, 0.5, 0.5),
            )

            aspect = axes_editor.editor("aspect")
            self.assertIsInstance(aspect, QLineEdit)
            aspect.setText("2.0")
            self.assertTrue(axes_editor._text_bindings["aspect"].flush())
            self.assertEqual(
                axes_controller.read_state().properties["aspect"],
                2.0,
            )

            spine_position = spine_editor.editor("position")
            self.assertIsInstance(spine_position, SpinePositionEditor)
            spine_position.set_value(("axes", 0.25), emit=True)
            self.assertEqual(
                left_spine.read_state().properties["position"],
                ("axes", 0.25),
            )

            bounds = spine_editor.editor("bounds")
            self.assertIsInstance(bounds, NumericTupleEditor)
            self.assertIsNone(bounds.value())
            bounds.set_value((0.0, 1.0), emit=True)
            self.assertEqual(
                left_spine.read_state().properties["bounds"],
                (0.0, 1.0),
            )
            bounds.set_value(None, emit=True)
            self.assertIsNone(
                left_spine.read_state().properties["bounds"]
            )

            alpha = line_editor.editor("alpha")
            self.assertIsInstance(alpha, NullableDoubleEditor)
            self.assertIsNone(alpha.value())
            alpha.set_value(0.5, emit=True)
            self.assertEqual(
                line_controller.read_state().properties["alpha"],
                0.5,
            )
            alpha.set_value(None, emit=True)
            self.assertIsNone(
                line_controller.read_state().properties["alpha"]
            )
        finally:
            axes_editor.close()
            spine_editor.close()
            line_editor.close()

    def test_chart_panels_use_the_context_color_library(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [0.0, 1.0], label="curve")
        registry = ComponentRegistry()
        controller = _register_chart(
            registry,
            FunctionCurveController,
            "curve",
            ComponentRole.FUNCTION_CURVE,
            line,
            {"expression": "x", "x_start": 0.0, "x_stop": 1.0},
        )
        library = ColorLibrary()
        context = _editor_context(registry, TableRepository(), library)
        editor = context.editor_manager.create(
            controller,
            context=context,
        )
        try:
            color = editor.section("appearance").editor("color")
            self.assertIs(color.color_library, library)
        finally:
            editor.close()
            context.editor_manager.close()


if __name__ == "__main__":
    unittest.main()
