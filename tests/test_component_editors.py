import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QTextCursor, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from mygui import status_messages
from mygui.database import ColumnRef, TableRepository
from mygui.figuremodify.component_services import (
    AxesCommandService,
    AxisTickSettingsService,
    ChartDataService,
    FitService,
    FunctionCurveService,
    InterpolationService,
    TextRenderService,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    ComponentValidationError,
    DataPlotController,
    FunctionCurveController,
    PropertySpec,
    ScatterController,
    register_figure_components,
)
from mygui.widgets.fig_control_window.component_editors.common import (
    FocusAwareDoubleSpinBox,
    FocusAwareSpinBox,
)
from mygui.figuremodify.style_base.color_models import PaletteDefinition
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorChoiceWidget
from mygui.widgets.fig_control_window.component_editors import (
    AxesAnchorEditor,
    AxisFormatterEditor,
    AxisLocatorEditor,
    AxisScaleEditor,
    AxisTickSettingsDialog,
    ComponentEditorBase,
    ComponentEditorManager,
    DebouncedTextBinding,
    EditorContext,
    EditorRegistry,
    FigureLayoutEditor,
    FontSpecEditor,
    InlineValueEditor,
    LegendAnchorEditor,
    LinePatternEditor,
    LineStyleEditor,
    MarkEveryEditor,
    MarkerSpecEditor,
    NamedNumberEditor,
    NullableDoubleEditor,
    NumberSequenceEditor,
    NumericTupleEditor,
    OptionalColorEditor,
    RangeEditor,
    ScatterColorMapEditor,
    ScatterSizeMapEditor,
    ScatterStyleEditor,
    SpinePositionEditor,
    StringListEditor,
    StructuredValueEditor,
    TextBoxEditor,
    ZoomConnectorsEditor,
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
            "color": {"editor": "color"},
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

    def test_identical_plain_text_sync_preserves_editing_session(self):
        editor = QPlainTextEdit()
        editor.setPlainText("abcdef")
        binding = DebouncedTextBinding(editor, lambda _value: True)
        text_events = []
        editor.textChanged.connect(lambda: text_events.append(True))
        cursor = editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(4, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.document().setModified(True)
        try:
            binding.set_text("abcdef")

            current = editor.textCursor()
            self.assertEqual((current.anchor(), current.position()), (2, 4))
            self.assertEqual(current.selectedText(), "cd")
            self.assertEqual(text_events, [])
            self.assertFalse(editor.document().isModified())
            self.assertEqual(binding.last_valid_text, "abcdef")
        finally:
            editor.close()

    def test_generic_text_editor_identical_sync_preserves_selection(self):
        controller = _FakeController()
        component_editor = ComponentEditorBase(
            controller,
            color_library=ColorLibrary(),
        )
        editor = component_editor.editor("label")
        text_events = []
        editor.textChanged.connect(text_events.append)
        editor.setSelection(1, 3)
        editor.setModified(True)
        try:
            component_editor.sync_from_controller()

            self.assertEqual(editor.selectionStart(), 1)
            self.assertEqual(editor.selectedText(), "efo")
            self.assertEqual(editor.cursorPosition(), 4)
            self.assertEqual(text_events, [])
            self.assertFalse(editor.isModified())
            self.assertEqual(
                component_editor._text_bindings["label"].last_valid_text,
                "before",
            )
        finally:
            component_editor.close()

    def test_success_messages_skip_noop_changes(self):
        editor = QLineEdit("before")
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        results = iter(
            (
                ComponentChange(
                    "fake",
                    None,
                    None,
                    None,
                    ChangeStatus.APPLIED,
                ),
                ComponentChange(
                    "fake",
                    None,
                    None,
                    None,
                    ChangeStatus.NOOP,
                ),
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

    def test_property_labels_fall_back_and_drive_accessibility_and_messages(self):
        controller = _FakeController()
        controller.property_specs = {
            "visible": {
                "editor": "bool",
                "label": None,
                "tooltip": "Show this artist.",
            },
            "linewidth": {
                "editor": "number",
                "label": "Line width",
            },
            "style": {"editor": "enum", "choices": ("-",), "label": "  "},
            "label": PropertySpec(
                "label",
                str,
                "before",
                editor="text",
                label=None,
            ),
        }
        presenter = MessagePresenter()
        editor = ComponentEditorBase(
            controller,
            context=SimpleNamespace(messages=presenter),
        )
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        try:
            visible = editor.editor("visible")
            linewidth = editor.editor("linewidth")
            style = editor.editor("style")
            label_input = editor.editor("label")
            self.assertEqual(editor.form_layout.labelForField(visible).text(), "Visible")
            self.assertEqual(
                editor.form_layout.labelForField(linewidth).text(),
                "Line width",
            )
            self.assertEqual(editor.form_layout.labelForField(style).text(), "Style")
            self.assertEqual(editor.form_layout.labelForField(label_input).text(), "Label")
            self.assertEqual(visible.accessibleName(), "Visible")
            self.assertEqual(visible.accessibleDescription(), "Show this artist.")
            self.assertEqual(visible.toolTip(), "Show this artist.")

            linewidth.setValue(3.5)
            label_input.setText("after")
            self.assertTrue(editor._text_bindings["label"].flush())
            self.assertIn(("Line width updated.", "success"), events)
            self.assertIn(("Label updated.", "success"), events)
            self.assertNotIn(("None updated.", "success"), events)
        finally:
            status_messages.clear_status_handler(handler)
            presenter.close()
            editor.close()

    def test_focus_aware_spinboxes_ignore_wheel_until_focused(self):
        for spin_type in (FocusAwareSpinBox, FocusAwareDoubleSpinBox):
            with self.subTest(spin_type=spin_type.__name__):
                container = QWidget()
                layout = QVBoxLayout(container)
                focus_sink = QLineEdit(container)
                spin = spin_type(container)
                layout.addWidget(focus_sink)
                layout.addWidget(spin)
                try:
                    spin.setRange(-100, 100)
                    spin.setValue(5)
                    container.show()
                    focus_sink.setFocus(Qt.MouseFocusReason)
                    self.app.processEvents()
                    self.assertFalse(spin.hasFocus())
                    unfocused = QWheelEvent(
                        QPointF(4, 4),
                        QPointF(4, 4),
                        QPoint(0, 0),
                        QPoint(0, 120),
                        Qt.NoButton,
                        Qt.NoModifier,
                        Qt.ScrollUpdate,
                        False,
                    )
                    QApplication.sendEvent(spin, unfocused)
                    self.assertEqual(spin.value(), 5)
                    self.assertFalse(unfocused.isAccepted())

                    spin.setFocus(Qt.MouseFocusReason)
                    self.app.processEvents()
                    self.assertTrue(spin.hasFocus())
                    focused = QWheelEvent(
                        QPointF(4, 4),
                        QPointF(4, 4),
                        QPoint(0, 0),
                        QPoint(0, 120),
                        Qt.NoButton,
                        Qt.NoModifier,
                        Qt.ScrollUpdate,
                        False,
                    )
                    QApplication.sendEvent(spin, focused)
                    self.assertGreater(spin.value(), 5)
                finally:
                    container.close()

    def test_composite_numeric_editors_use_focus_aware_spinboxes(self):
        nullable = NullableDoubleEditor(1.0)
        numeric_tuple = NumericTupleEditor((1.0, 2.0), length=2)
        value_range = RangeEditor(1.0, 2.0)
        try:
            self.assertIsInstance(
                nullable.value_input,
                FocusAwareDoubleSpinBox,
            )
            self.assertTrue(
                all(
                    isinstance(item, FocusAwareDoubleSpinBox)
                    for item in numeric_tuple.inputs
                )
            )
            self.assertIsInstance(
                value_range.minimum_input,
                FocusAwareDoubleSpinBox,
            )
            self.assertIsInstance(
                value_range.maximum_input,
                FocusAwareDoubleSpinBox,
            )
        finally:
            nullable.close()
            numeric_tuple.close()
            value_range.close()

    def test_component_editor_reports_applied_but_not_noop(self):
        controller = _FakeController()
        editor = ComponentEditorBase(controller, color_library=ColorLibrary())
        events = []

        def handler(message, level):
            events.append((message, level))

        status_messages.set_status_handler(handler)
        try:
            self.assertTrue(editor.apply_property("linewidth", 4.0))
            controller.set_property = lambda _key, _value: ComponentChange(
                "fake",
                None,
                None,
                None,
                ChangeStatus.NOOP,
            )
            self.assertTrue(editor.apply_property("linewidth", 4.0))
            self.assertEqual(events, [("Linewidth updated.", "success")])
        finally:
            status_messages.clear_status_handler(handler)
            editor.close()

    def test_color_property_requires_injected_library(self):
        with self.assertRaisesRegex(ValueError, "ColorLibrary"):
            ComponentEditorBase(_FakeController())

    def test_editor_factories_cover_every_editor_kind_exactly(self):
        from mygui.figuremodify.components.models import EditorKind
        from mygui.widgets.fig_control_window.component_editors.editor_factories import (
            EDITOR_FACTORIES,
            create_editor_widget,
            register_editor_factory,
            validate_editor_factories,
        )

        self.assertEqual(set(EDITOR_FACTORIES), set(EditorKind))
        validate_editor_factories()
        table = dict(EDITOR_FACTORIES)
        with self.assertRaises(RuntimeError):
            register_editor_factory(
                EditorKind.BOOL,
                table[EditorKind.BOOL],
                table,
            )
        with self.assertRaises(RuntimeError):
            validate_editor_factories({})
        broken = dict(EDITOR_FACTORIES)
        broken[EditorKind.BOOL] = object()
        with self.assertRaises(RuntimeError):
            validate_editor_factories(broken)
        with self.assertRaises(RuntimeError):
            EDITOR_FACTORIES[EditorKind.AUTO](object(), "visible", {}, True)

        controller = _FakeController()
        editor = ComponentEditorBase(controller, color_library=ColorLibrary())
        try:
            with patch.dict(EDITOR_FACTORIES, {}, clear=True):
                with self.assertRaisesRegex(
                    ComponentValidationError,
                    "unsupported editor",
                ):
                    create_editor_widget(
                        editor,
                        "label",
                        {"editor": "text"},
                        "value",
                    )
        finally:
            editor.close()

    def test_editor_registry_generic_entry_uses_explicit_kind_registration(self):
        class CustomEditor(ComponentEditorBase):
            pass

        registry = EditorRegistry()
        registry.register(ComponentKind.LINE, CustomEditor)
        controller = _FakeController()
        editor = registry.create_generic(
            controller,
            color_library=ColorLibrary(),
        )
        try:
            self.assertIsInstance(editor, CustomEditor)
        finally:
            editor.close()

    def test_generic_entry_prefers_role_specific_registration(self):
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
        editor = registry.create_generic(
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
        fallback_editor = registry.create_generic(
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

    def test_unknown_modification_result_fails_closed(self):
        editor = QLineEdit("before")
        binding = DebouncedTextBinding(
            editor,
            lambda _value: object(),
            delay_ms=1,
        )
        try:
            editor.setText("after")
            self.assertFalse(binding.flush())
            self.assertEqual(editor.text(), "before")
        finally:
            editor.close()

    def test_message_presenter_rejects_unknown_result_type(self):
        events = []
        status_messages.set_status_handler(
            lambda message, level: events.append((message, level))
        )
        try:
            self.assertFalse(MessagePresenter().present(object()))
            self.assertEqual(len(events), 1)
            self.assertIn("Unsupported component result type", events[0][0])
            self.assertEqual(events[0][1], "error")
        finally:
            status_messages.clear_status_handler()

    def test_unified_axis_tick_dialog_uses_fixed_row_editor_without_side_effects(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        axis = next(
            controller
            for controller in registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = registry.get(axis.state.parent_id)
        context = _editor_context(registry, TableRepository(), ColorLibrary())
        context.axis_ticks = AxisTickSettingsService(
            registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        inspector = context.editor_manager.create(axis, context=context)
        dialog = None
        try:
            section = inspector.section("ticks_labels")
            self.assertTrue(section.configure_button.isEnabled())
            self.assertNotIn("major_locator", inspector.section("properties").editors())
            opening = context.axis_ticks.snapshot(axis.component_id)
            dialog = AxisTickSettingsDialog(opening, context=context)
            dialog.major_page.locator_editor.set_value(
                {
                    "kind": "fixed",
                    "params": {"locations": [0.0, 1.0], "nbins": None},
                },
                emit=True,
            )
            dialog.major_page.formatter_editor.set_value(
                {
                    "kind": "fixed",
                    "params": {"labels": ["zero", "one"]},
                },
                emit=True,
            )
            self.assertEqual(dialog.major_page.fixed_table.rowCount(), 2)
            dialog.major_page.fixed_table.item(0, 0).setText("abc")
            self.assertFalse(dialog.error_label.isHidden())
            self.assertFalse(
                dialog.buttons.button(
                    QDialogButtonBox.StandardButton.Ok
                ).isEnabled()
            )
            with self.assertRaisesRegex(ValueError, "valid numeric values"):
                dialog.current_draft()
            dialog.major_page.fixed_table.item(0, 0).setText("0")
            self.assertTrue(dialog.error_label.isHidden())
            self.assertTrue(
                dialog.buttons.button(
                    QDialogButtonBox.StandardButton.Ok
                ).isEnabled()
            )
            dialog.major_page.fixed_table.item(1, 1).setText("ONE")
            candidate = context.axis_ticks.validate(dialog.current_draft())
            self.assertEqual(
                candidate.major.formatter["params"]["labels"],
                ["zero", "ONE"],
            )
            dialog._copy(dialog.major_page, dialog.minor_page)
            self.assertEqual(
                dialog.minor_page.level().locator,
                dialog.major_page.level().locator,
            )
            dialog._restore_scale_defaults()
            self.assertEqual(
                dialog.current_draft().major.locator["kind"], "auto"
            )
            self.assertEqual(axis.state, opening.expected_states[0])
        finally:
            if dialog is not None:
                dialog.reject()
                dialog.deleteLater()
            inspector.close()
            context.editor_manager.close()

    def test_axis_tick_dialog_accepts_without_message_presenter(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(
            figure,
            id_factory=lambda path: path,
            include_artists=False,
        )
        axis = next(
            controller
            for controller in registry.query(kind=ComponentKind.AXIS)
            if controller.state.selector == {"axis": "x"}
        )
        owner = registry.get(axis.state.parent_id)
        context = _editor_context(registry, TableRepository(), ColorLibrary())
        context.axis_ticks = AxisTickSettingsService(
            registry,
            linked_axes=lambda _axes_id, _dimension: (owner,),
        )
        context.messages = None
        dialog = AxisTickSettingsDialog(
            context.axis_ticks.snapshot(axis.component_id),
            context=context,
        )
        try:
            fontsize = dialog.major_page.level().label_properties["fontsize"]
            dialog.major_page.label_form.apply_property(
                "fontsize", fontsize + 1.0
            )
            result = SimpleNamespace(ok=True, message="Tick settings updated.")
            with (
                patch(
                    "mygui.widgets.fig_control_window.component_editors.sections."
                    "axis_ticks.perform_editor_action",
                    return_value=result,
                ),
                patch.object(status_messages, "show_success") as show_success,
            ):
                dialog._accept_settings()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            show_success.assert_called_once_with("Tick settings updated.")
        finally:
            dialog.dispose()
            dialog.close()
            context.editor_manager.close()

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

            style_input = appearance.editor("linestyle")
            self.assertIsInstance(style_input, LinePatternEditor)
            style_input.set_value({"kind": "preset", "value": "--"}, emit=True)
            self.assertEqual(line.get_linestyle(), "--")
            self.assertEqual(
                controller.state.properties["linestyle"],
                {"kind": "preset", "value": "--"},
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
            plot_style.set_value({"kind": "preset", "value": ":"}, emit=True)
            plot_appearance.editor("markersize").setValue(7.5)
            scatter_marker = scatter_appearance.editor("marker")
            self.assertIsInstance(scatter_marker, MarkerSpecEditor)
            scatter_marker.set_value({"kind": "symbol", "value": "s"}, emit=True)
            scatter_appearance.editor("size").setValue(42.0)

            self.assertEqual(
                plot_controller.state.properties["linestyle"],
                {"kind": "preset", "value": ":"},
            )
            self.assertEqual(
                plot_controller.state.properties["markersize"],
                7.5,
            )
            self.assertEqual(
                scatter_controller.state.properties["marker"],
                {"kind": "symbol", "value": "s"},
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

    def test_axis_compound_properties_use_structured_summary_editors(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        axis_controller = next(
            controller
            for controller in registry
            if controller.state.role is ComponentRole.X_AXIS
        )
        editor = ComponentEditorBase(
            axis_controller,
            color_library=ColorLibrary(),
        )
        try:
            scale = editor.editor("scale")
            major_locator = editor.editor("major_locator")
            major_formatter = editor.editor("major_formatter")
            minor_locator = editor.editor("minor_locator")
            minor_formatter = editor.editor("minor_formatter")
            offset_font = editor.editor("offset_font")

            self.assertIsInstance(scale, AxisScaleEditor)
            self.assertIsInstance(major_locator, AxisLocatorEditor)
            self.assertIsInstance(major_formatter, AxisFormatterEditor)
            self.assertIsInstance(minor_locator, AxisLocatorEditor)
            self.assertIsInstance(minor_formatter, AxisFormatterEditor)
            self.assertIsInstance(offset_font, FontSpecEditor)
            self.assertEqual(scale.summary.text(), "Linear")
            self.assertEqual(major_locator.summary.text(), "Auto")
            self.assertEqual(major_formatter.summary.text(), "Scalar")
            self.assertEqual(minor_locator.summary.text(), "None")
            self.assertEqual(minor_formatter.summary.text(), "None")
            self.assertIn("sans-serif", offset_font.summary.text())
            self.assertTrue(
                all(
                    "{" not in compound.summary.text()
                    for compound in (
                        scale,
                        major_locator,
                        major_formatter,
                        minor_locator,
                        minor_formatter,
                        offset_font,
                    )
                )
            )

            scale.set_value(
                {
                    "kind": "log",
                    "params": {
                        "base": 10.0,
                        "subs": None,
                        "nonpositive": "clip",
                    },
                },
                emit=True,
            )
            self.assertEqual(axis_controller.state.properties["scale"]["kind"], "log")
            self.assertEqual(scale.summary.text(), "Log")

            offset_font.set_value(
                {
                    **offset_font.value(),
                    "family": ["serif"],
                    "size": 12.0,
                },
                emit=True,
            )
            self.assertEqual(
                axis_controller.state.properties["offset_font"]["family"],
                ["serif"],
            )
            self.assertEqual(offset_font.summary.text(), "serif · 12 pt · normal")
        finally:
            editor.close()

    def test_axis_structured_dialog_selects_current_variant_and_validates(self):
        locator = AxisLocatorEditor(
            {"kind": "null", "params": {}},
        )
        formatter = AxisFormatterEditor(
            {
                "kind": "percent",
                "params": {
                    "xmax": 100.0,
                    "decimals": 1,
                    "symbol": "%",
                    "is_latex": False,
                },
            },
        )
        try:
            locator_dialog = locator._dialog()
            formatter_dialog = formatter._dialog()
            try:
                self.assertEqual(locator_dialog.kind_input.currentData(), "null")
                self.assertIs(
                    locator_dialog.form_stack.currentWidget(),
                    locator_dialog._forms["null"],
                )
                self.assertEqual(
                    formatter_dialog.kind_input.currentData(),
                    "percent",
                )
                self.assertIs(
                    formatter_dialog.form_stack.currentWidget(),
                    formatter_dialog._forms["percent"],
                )
                formatter_dialog._validate_and_accept()
                self.assertEqual(formatter_dialog.value(), formatter.value())
            finally:
                locator_dialog.close()
                formatter_dialog.close()
        finally:
            locator.close()
            formatter.close()

    def test_axis_structured_dialog_defaults_cover_every_supported_kind(self):
        editors = (
            AxisScaleEditor({"kind": "linear", "params": {}}),
            AxisLocatorEditor({"kind": "auto", "params": {}}),
            AxisFormatterEditor(
                {
                    "kind": "scalar",
                    "params": {
                        "use_offset": True,
                        "use_math_text": False,
                        "use_locale": False,
                        "scientific": True,
                        "powerlimits": [-5, 6],
                    },
                }
            ),
        )
        try:
            for editor in editors:
                probe = editor._dialog()
                kinds = [
                    probe.kind_input.itemData(index)
                    for index in range(probe.kind_input.count())
                ]
                probe.close()
                for kind in kinds:
                    with self.subTest(editor=type(editor).__name__, kind=kind):
                        dialog = editor._dialog()
                        try:
                            dialog.kind_input.setCurrentIndex(
                                dialog.kind_input.findData(kind)
                            )
                            dialog._validate_and_accept()
                            self.assertFalse(dialog.error_label.isVisible())
                            self.assertEqual(dialog.value()["kind"], kind)
                        finally:
                            dialog.close()
        finally:
            for editor in editors:
                editor.close()

    def test_logit_locator_editor_roundtrips_automatic_bin_count(self):
        value = {
            "kind": "logit",
            "params": {"minor": True, "nbins": "auto"},
        }
        editor = AxisLocatorEditor(value)
        try:
            dialog = editor._dialog()
            try:
                self.assertEqual(dialog.kind_input.currentData(), "logit")
                dialog._validate_and_accept()
                self.assertEqual(dialog.value(), value)
            finally:
                dialog.close()
        finally:
            editor.close()

    def test_rejected_structured_value_restores_summary_and_value(self):
        controller = _FakeController()
        controller.state["properties"] = {
            "scale": {"kind": "linear", "params": {}},
        }
        controller.property_specs = {
            "scale": {"editor": "scale_spec"},
        }
        controller.set_property = lambda _key, _value: False
        editor = ComponentEditorBase(controller)
        try:
            scale = editor.editor("scale")
            scale.set_value(
                {
                    "kind": "log",
                    "params": {
                        "base": 10.0,
                        "subs": None,
                        "nonpositive": "clip",
                    },
                },
                emit=True,
            )
            self.assertEqual(scale.value(), {"kind": "linear", "params": {}})
            self.assertEqual(scale.summary.text(), "Linear")
        finally:
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

    def test_tick_label_font_combobox_syncs_from_string_state(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [0.0, 1.0])
        registry = register_figure_components(figure)
        controller = next(
            item
            for item in registry
            if item.state.kind is ComponentKind.TICK_LABEL_GROUP
            and item.state.selector == {"axis": "x", "level": "major"}
        )
        context = _editor_context(
            registry,
            TableRepository(),
            ColorLibrary(),
        )
        editor = context.editor_manager.create(controller, context=context)
        try:
            section = editor.section("properties")
            font = section.editor("fontfamily")
            family = font.currentFont().family()
            self.assertTrue(controller.set_property("fontfamily", [family]).ok)

            section.sync_from_controller()

            self.assertIsInstance(
                controller.state.properties["fontfamily"],
                str,
            )
            self.assertEqual(
                controller.state.properties["fontfamily"],
                family,
            )
            self.assertEqual(font.currentFont().family(), family)
            self.assertTrue(
                all(
                    tick.label1.get_fontfamily()[0] == family
                    for tick in axes.xaxis.get_major_ticks()
                )
            )
        finally:
            editor.close()
            context.editor_manager.close()

    def test_legend_numeric_locations_sync_to_all_presets_without_submit(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [0.0, 1.0], label="line")
        axes.legend(loc=0)
        registry = register_figure_components(figure)
        controller = next(
            item
            for item in registry
            if item.state.role is ComponentRole.LEGEND
        )
        context = _editor_context(
            registry,
            TableRepository(),
            ColorLibrary(),
        )
        editor = context.editor_manager.create(controller, context=context)
        section = editor.section("layout")
        try:
            for code, preset in enumerate(section.PRESETS):
                with self.subTest(code=code, preset=preset):
                    self.assertTrue(
                        controller.set_property(
                            "location",
                            {"kind": "code", "value": code},
                        ).ok
                    )
                    with patch.object(
                        controller,
                        "set_property",
                        wraps=controller.set_property,
                    ) as setter:
                        section.sync_from_controller()
                    setter.assert_not_called()
                    self.assertEqual(
                        section.legend_position_combobox.currentText(),
                        preset,
                    )
        finally:
            editor.close()
            context.editor_manager.close()

    def test_axes_palette_section_shows_and_switches_palette_source(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [0.0, 1.0], label="curve")
        registry = register_figure_components(figure)
        axes_controller = next(
            controller
            for controller in registry
            if controller.state.role is ComponentRole.AXES
        )
        figure_controller = registry.get(
            axes_controller.state.parent_id
        )
        library = ColorLibrary()
        context = _editor_context(registry, TableRepository(), library)
        editor = context.editor_manager.create(
            axes_controller,
            context=context,
        )
        section = editor.section("palette")
        custom = PaletteDefinition(
            "custom:test",
            "Lab colors",
            tuple(f"#{index:06X}" for index in range(1, 13)),
            category="Custom",
            source="custom",
        )
        try:
            self.assertEqual(section.source_input.currentData(), "style")
            self.assertIn(
                "Style default · default",
                section.current_palette_label.text(),
            )
            initial_status = context.axes_commands.palette_status(
                axes_controller.component_id
            )
            self.assertEqual(
                section.palette_preview.colors(),
                initial_status.palette.colors,
            )
            self.assertFalse(section.button.isEnabled())

            with patch(
                "mygui.widgets.fig_control_window.component_editors."
                "sections.palette.choose_palette",
                return_value=None,
            ):
                section.source_input.setCurrentIndex(
                    section.source_input.findData("user")
                )
            self.assertEqual(section.source_input.currentData(), "style")
            self.assertFalse(section.button.isEnabled())

            with patch(
                "mygui.widgets.fig_control_window.component_editors."
                "sections.palette.choose_palette",
                return_value=custom,
            ):
                section.source_input.setCurrentIndex(
                    section.source_input.findData("user")
                )

            self.assertEqual(section.source_input.currentData(), "user")
            self.assertTrue(section.button.isEnabled())
            self.assertEqual(
                section.current_palette_label.text(),
                "Custom palette · Lab colors",
            )
            self.assertEqual(
                section.palette_preview.colors(),
                custom.colors,
            )
            self.assertGreater(
                section.palette_preview.heightForWidth(140),
                section.palette_preview.heightForWidth(800),
            )
            self.assertEqual(
                section.palette_preview.row_count_for_width(800),
                1,
            )
            self.assertEqual(line.get_color(), custom.colors[0])
            self.assertEqual(
                context.axes_commands.cycle_state(
                    axes_controller.component_id
                ).active_palette,
                custom,
            )

            figure_controller.set_property(
                "style",
                "fivethirtyeight",
            )
            self.assertEqual(section.source_input.currentData(), "user")
            self.assertIn(
                "Lab colors",
                section.current_palette_label.text(),
            )

            section.source_input.setCurrentIndex(
                section.source_input.findData("style")
            )
            style_status = context.axes_commands.palette_status(
                axes_controller.component_id
            )
            self.assertTrue(style_status.uses_style_default)
            self.assertEqual(
                section.current_palette_label.text(),
                "Style default · fivethirtyeight",
            )
            self.assertEqual(
                section.palette_preview.colors(),
                style_status.palette.colors,
            )
            self.assertEqual(
                line.get_color().casefold(),
                style_status.palette.colors[0].casefold(),
            )
        finally:
            editor.close()
            context.editor_manager.close()


class ComponentSpecEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _figure_registry(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [1.0, 2.0], label="line")
        axes.scatter([0.0, 1.0], [2.0, 3.0], label="scatter")
        axes.set_title("title")
        axes.legend()
        return figure, register_figure_components(figure)

    @staticmethod
    def _controller(registry, kind, role=None, **selector):
        return next(
            controller
            for controller in registry
            if controller.state.kind is kind
            and (role is None or controller.state.role is role)
            and all(
                controller.state.selector.get(key) == value
                for key, value in selector.items()
            )
        )

    def test_generated_controls_never_display_raw_json(self):
        _figure, registry = self._figure_registry()
        library = ColorLibrary()
        editors = [
            ComponentEditorBase(controller, color_library=library)
            for controller in registry
        ]
        try:
            for editor in editors:
                for key, widget in editor.editors().items():
                    if isinstance(widget, QLineEdit):
                        with self.subTest(component=editor.controller.state.id, key=key):
                            self.assertFalse(
                                widget.text().startswith(("{", "[")),
                                f"{key} still renders a raw JSON document",
                            )
        finally:
            for editor in editors:
                editor.close()

    def test_every_compound_property_uses_its_dedicated_control(self):
        _figure, registry = self._figure_registry()
        library = ColorLibrary()
        expected = {
            (ComponentKind.FIGURE, "layout_engine"): FigureLayoutEditor,
            (ComponentKind.AXES, "anchor"): AxesAnchorEditor,
            (ComponentKind.SPINE, "linestyle"): LinePatternEditor,
            (ComponentKind.GRID, "linestyle"): LinePatternEditor,
            (ComponentKind.GRID, "gapcolor"): OptionalColorEditor,
            (ComponentKind.TICK_LABEL_GROUP, "fontweight"): NamedNumberEditor,
            (ComponentKind.TICK_LABEL_GROUP, "bbox"): TextBoxEditor,
            (ComponentKind.TEXT, "bbox"): TextBoxEditor,
            (ComponentKind.TEXT, "fontstretch"): NamedNumberEditor,
            (ComponentKind.LEGEND, "bbox_to_anchor"): LegendAnchorEditor,
            (ComponentKind.LEGEND, "label_font"): FontSpecEditor,
            (ComponentKind.LEGEND, "scatteryoffsets"): NumberSequenceEditor,
            (ComponentKind.LEGEND, "frame_linestyle"): LinePatternEditor,
            (ComponentKind.LINE, "marker"): MarkerSpecEditor,
            (ComponentKind.LINE, "markevery"): MarkEveryEditor,
            (ComponentKind.LINE, "markerfacecoloralt"): OptionalColorEditor,
            (ComponentKind.LINE, "sketch_params"): NumericTupleEditor,
            (ComponentKind.SCATTER, "marker"): MarkerSpecEditor,
            (ComponentKind.SCATTER, "urls"): StringListEditor,
            (ComponentKind.SCATTER, "color_mapping"): ScatterColorMapEditor,
            (ComponentKind.SCATTER, "size_mapping"): ScatterSizeMapEditor,
        }
        editors = []
        try:
            for (kind, key), editor_type in expected.items():
                controller = self._controller(registry, kind)
                editor = ComponentEditorBase(controller, color_library=library)
                editors.append(editor)
                with self.subTest(kind=kind, key=key):
                    self.assertIsInstance(editor.editor(key), editor_type)
        finally:
            for editor in editors:
                editor.close()

    def test_line_pattern_editor_round_trips_presets_and_custom_dashes(self):
        editor = LinePatternEditor({"kind": "preset", "value": "--"})
        emitted = []
        editor.valueChanged.connect(emitted.append)
        try:
            self.assertEqual(editor.value(), {"kind": "preset", "value": "--"})
            self.assertFalse(editor.dashes_input.isVisibleTo(editor))

            editor.set_value(
                {"kind": "custom", "offset": 1.0, "dashes": [4.0, 2.0]}
            )
            self.assertEqual(
                editor.value(),
                {"kind": "custom", "offset": 1.0, "dashes": [4.0, 2.0]},
            )
            self.assertEqual(editor.dashes_input.text(), "4, 2")
            self.assertEqual(emitted, [])

            editor.kind_input.setCurrentIndex(editor.kind_input.findData("-"))
            self.assertEqual(emitted, [{"kind": "preset", "value": "-"}])
        finally:
            editor.close()

    def test_line_pattern_editor_prefills_custom_dashes_once(self):
        editor = LinePatternEditor({"kind": "preset", "value": "-"})
        emitted = []
        editor.valueChanged.connect(emitted.append)
        try:
            editor.kind_input.setCurrentIndex(editor.kind_input.count() - 1)
            self.assertEqual(
                emitted,
                [{"kind": "custom", "offset": 0.0, "dashes": [6.0, 2.0]}],
            )
            self.assertTrue(editor.dashes_input.isVisibleTo(editor))
        finally:
            editor.close()

    def test_marker_spec_editor_round_trips_symbol_and_polygon(self):
        editor = MarkerSpecEditor({"kind": "symbol", "value": "o"})
        emitted = []
        editor.valueChanged.connect(emitted.append)
        try:
            self.assertEqual(editor.value(), {"kind": "symbol", "value": "o"})
            polygon = {
                "kind": "regular_polygon",
                "sides": 5,
                "style": 1,
                "angle": 30.0,
            }
            editor.set_value(polygon)
            self.assertEqual(editor.value(), polygon)
            self.assertTrue(editor.sides_input.isVisibleTo(editor))
            self.assertEqual(emitted, [])

            editor.set_value({"kind": "symbol", "value": 4}, emit=True)
            self.assertEqual(emitted, [{"kind": "symbol", "value": 4}])
            self.assertFalse(editor.sides_input.isVisibleTo(editor))
        finally:
            editor.close()

    def test_optional_color_editor_uses_the_declared_unset_value(self):
        _figure, registry = self._figure_registry()
        line = self._controller(registry, ComponentKind.LINE)
        editor = ComponentEditorBase(line, color_library=ColorLibrary())
        try:
            gapcolor = editor.editor("gapcolor")
            alternate = editor.editor("markerfacecoloralt")
            self.assertIsNone(gapcolor.value())
            self.assertEqual(alternate.value(), "none")

            gapcolor.set_value("#ff0000", emit=True)
            self.assertEqual(
                str(line.read_state().properties["gapcolor"]).casefold(),
                "#ff0000",
            )
            gapcolor.set_value(None, emit=True)
            self.assertIsNone(line.read_state().properties["gapcolor"])

            alternate.set_value("#00ff00", emit=True)
            self.assertEqual(
                str(line.read_state().properties["markerfacecoloralt"]).casefold(),
                "#00ff00",
            )
            alternate.set_value("none", emit=True)
            self.assertEqual(
                line.read_state().properties["markerfacecoloralt"],
                "none",
            )
        finally:
            editor.close()

    def test_named_number_editor_accepts_keywords_and_numbers(self):
        editor = NamedNumberEditor("normal", names=("light", "normal", "bold"))
        try:
            self.assertEqual(editor.value(), "normal")
            editor.value_input.setCurrentText("bold")
            self.assertEqual(editor.value(), "bold")
            editor.value_input.setCurrentText("650")
            self.assertEqual(editor.value(), 650)
            editor.set_value(300)
            self.assertEqual(editor.value(), 300)
        finally:
            editor.close()

    def test_sequence_editors_emit_tuples_from_readable_text(self):
        numbers = NumberSequenceEditor((0.375, 0.5, 0.3125))
        strings = StringListEditor(("https://a", "https://b"))
        try:
            self.assertEqual(numbers.value_input.text(), "0.375, 0.5, 0.3125")
            numbers.value_input.setText("0.25 0.5")
            self.assertEqual(numbers.value(), (0.25, 0.5))

            self.assertEqual(
                strings.value_input.toPlainText(),
                "https://a\nhttps://b",
            )
            strings.set_plain_text("https://c\n\nhttps://d")
            self.assertEqual(strings.value(), ("https://c", "https://d"))
        finally:
            numbers.close()
            strings.close()

    def test_axes_and_legend_anchor_editors_switch_variants(self):
        anchor = AxesAnchorEditor("C")
        legend_anchor = LegendAnchorEditor({"kind": "none"})
        try:
            self.assertEqual(anchor.value(), "C")
            anchor.set_value((0.25, 0.75))
            self.assertEqual(anchor.value(), (0.25, 0.75))
            self.assertTrue(anchor.x_input.isVisibleTo(anchor))

            self.assertEqual(legend_anchor.value(), {"kind": "none"})
            legend_anchor.set_value({"kind": "point", "x": 0.5, "y": 0.25})
            self.assertEqual(
                legend_anchor.value(),
                {"kind": "point", "x": 0.5, "y": 0.25},
            )
            self.assertFalse(
                legend_anchor.field_inputs["width"].isVisibleTo(legend_anchor)
            )
            legend_anchor.set_value(
                {
                    "kind": "bounds",
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 0.5,
                }
            )
            self.assertTrue(
                legend_anchor.field_inputs["height"].isVisibleTo(legend_anchor)
            )
        finally:
            anchor.close()
            legend_anchor.close()

    def test_markevery_dialog_writes_every_supported_variant(self):
        editor = MarkEveryEditor({"kind": "all"})
        try:
            self.assertEqual(editor.summary.text(), "Every point")
            probe = editor._dialog()
            kinds = [
                probe.kind_input.itemData(index)
                for index in range(probe.kind_input.count())
            ]
            probe.close()
            for kind in kinds:
                with self.subTest(kind=kind):
                    dialog = editor._dialog()
                    try:
                        dialog.kind_input.setCurrentIndex(
                            dialog.kind_input.findData(kind)
                        )
                        dialog._validate_and_accept()
                        self.assertFalse(dialog.error_label.isVisible())
                        self.assertEqual(dialog.value()["kind"], kind)
                        self.assertNotIn("params", dialog.value())
                    finally:
                        dialog.close()
        finally:
            editor.close()

    def test_figure_layout_dialog_writes_every_supported_variant(self):
        editor = FigureLayoutEditor({"kind": "none", "params": {}})
        try:
            self.assertEqual(editor.summary.text(), "None")
            probe = editor._dialog()
            kinds = [
                probe.kind_input.itemData(index)
                for index in range(probe.kind_input.count())
            ]
            probe.close()
            for kind in kinds:
                with self.subTest(kind=kind):
                    dialog = editor._dialog()
                    try:
                        dialog.kind_input.setCurrentIndex(
                            dialog.kind_input.findData(kind)
                        )
                        dialog._validate_and_accept()
                        self.assertFalse(dialog.error_label.isVisible())
                        self.assertEqual(dialog.value()["kind"], kind)
                    finally:
                        dialog.close()
        finally:
            editor.close()

    def test_text_box_dialog_writes_a_complete_or_disabled_record(self):
        editor = TextBoxEditor({"enabled": False}, color_library=ColorLibrary())
        try:
            self.assertEqual(editor.summary.text(), "No box")
            dialog = editor._dialog()
            try:
                dialog.enabled_input.setChecked(True)
                dialog.boxstyle_input.setCurrentText("square")
                dialog.pad_input.setValue(0.5)
                dialog._validate_and_accept()
                self.assertFalse(dialog.error_label.isVisible())
                value = dialog.value()
            finally:
                dialog.close()
            self.assertEqual(
                set(value),
                {
                    "enabled",
                    "boxstyle",
                    "facecolor",
                    "edgecolor",
                    "linewidth",
                    "line_pattern",
                    "alpha",
                    "fill",
                    "hatch",
                    "pad",
                },
            )
            editor.set_value(value)
            self.assertEqual(editor.summary.text().split(" \u00b7 ")[0], "Square")

            disabled = editor._dialog()
            try:
                disabled.enabled_input.setChecked(False)
                disabled._validate_and_accept()
                self.assertEqual(disabled.value(), {"enabled": False})
            finally:
                disabled.close()
        finally:
            editor.close()

    def test_scatter_mapping_dialogs_write_complete_records(self):
        library = ColorLibrary()
        color_map = ScatterColorMapEditor(
            {
                "enabled": False,
                "cmap": "viridis",
                "norm": {
                    "kind": "linear",
                    "params": {"vmin": None, "vmax": None, "clip": False},
                },
                "bad": "#00000000",
                "under": None,
                "over": None,
                "nonfinite": "drop",
            },
            color_library=library,
        )
        size_map = ScatterSizeMapEditor(
            {
                "enabled": False,
                "input": None,
                "output": [12.0, 120.0],
                "clamp": True,
            }
        )
        try:
            self.assertEqual(color_map.summary.text(), "Uniform color")
            self.assertEqual(size_map.summary.text(), "Uniform size")

            color_dialog = color_map._dialog()
            try:
                color_dialog.enabled_input.setChecked(True)
                color_dialog.cmap_input.setCurrentText("plasma")
                color_dialog.norm_input.set_value(
                    {
                        "kind": "log",
                        "params": {"vmin": 1.0, "vmax": 10.0, "clip": False},
                    }
                )
                color_dialog._validate_and_accept()
                self.assertFalse(color_dialog.error_label.isVisible())
                color_value = color_dialog.value()
            finally:
                color_dialog.close()
            self.assertTrue(color_value["enabled"])
            self.assertEqual(color_value["cmap"], "plasma")
            self.assertEqual(color_value["norm"]["kind"], "log")
            color_map.set_value(color_value)
            self.assertEqual(color_map.summary.text(), "plasma \u00b7 Log")

            size_dialog = size_map._dialog()
            try:
                size_dialog.enabled_input.setChecked(True)
                size_dialog.output_range_input.set_value((6.0, 60.0))
                size_dialog._validate_and_accept()
                self.assertFalse(size_dialog.error_label.isVisible())
                size_value = size_dialog.value()
            finally:
                size_dialog.close()
            self.assertEqual(size_value["output"], [6.0, 60.0])
            size_map.set_value(size_value)
            self.assertEqual(size_map.summary.text(), "6\u201360 pt\u00b2")
        finally:
            color_map.close()
            size_map.close()

    def test_zoom_connector_dialog_writes_four_complete_records(self):
        connectors = tuple(
            {
                "visible": True,
                "color": "#808080",
                "line_pattern": {"kind": "preset", "value": "-"},
                "linewidth": 1.0,
                "alpha": 0.5,
                "zorder": 4.99,
            }
            for _index in range(4)
        )
        editor = ZoomConnectorsEditor(connectors, color_library=ColorLibrary())
        try:
            self.assertEqual(editor.summary.text(), "4 of 4 connectors visible")
            dialog = editor._dialog()
            try:
                self.assertEqual(len(dialog.pages), 4)
                dialog.pages[0].visible_input.setChecked(False)
                dialog.pages[1].line_pattern_input.set_value(
                    {"kind": "preset", "value": ":"}
                )
                dialog._validate_and_accept()
                self.assertFalse(dialog.error_label.isVisible())
                value = dialog.value()
            finally:
                dialog.close()
            self.assertEqual(len(value), 4)
            self.assertFalse(value[0]["visible"])
            self.assertEqual(
                value[1]["line_pattern"],
                {"kind": "preset", "value": ":"},
            )
            editor.set_value(value)
            self.assertEqual(editor.summary.text(), "3 of 4 connectors visible")
        finally:
            editor.close()

    def test_cancelled_structured_dialog_leaves_the_value_unchanged(self):
        editor = TextBoxEditor({"enabled": False}, color_library=ColorLibrary())
        emitted = []
        editor.valueChanged.connect(emitted.append)
        try:
            dialog = editor._dialog()
            dialog.enabled_input.setChecked(True)
            with patch.object(
                dialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ), patch.object(editor, "_dialog", return_value=dialog):
                editor._open_dialog()
            self.assertEqual(editor.value(), {"enabled": False})
            self.assertEqual(editor.summary.text(), "No box")
            self.assertEqual(emitted, [])
        finally:
            editor.close()

    def test_rejected_compound_value_restores_control_and_state(self):
        controller = _FakeController()
        controller.state["properties"] = {
            "linestyle": {"kind": "preset", "value": "-"},
            "markevery": {"kind": "all"},
        }
        controller.property_specs = {
            "linestyle": {"editor": "line_pattern"},
            "markevery": {"editor": "markevery"},
        }
        controller.set_property = lambda _key, _value: False
        editor = ComponentEditorBase(controller)
        try:
            pattern = editor.editor("linestyle")
            marks = editor.editor("markevery")
            pattern.set_value({"kind": "preset", "value": ":"}, emit=True)
            marks.set_value({"kind": "stride", "start": None, "step": 3}, emit=True)
            self.assertEqual(pattern.value(), {"kind": "preset", "value": "-"})
            self.assertEqual(marks.value(), {"kind": "all"})
            self.assertEqual(marks.summary.text(), "Every point")
        finally:
            editor.close()

    def test_tick_level_page_preserves_bbox_and_common_properties_without_overwriting(self):
        from mygui.figuremodify.components import (
            TickGroupController,
            TickLabelGroupController,
        )
        from mygui.figuremodify.components.property_values import (
            DEFAULT_FORMATTER,
            DEFAULT_MAJOR_LOCATOR,
        )
        from mygui.figuremodify.services.axis_ticks import TickLevelSettings
        from mygui.widgets.fig_control_window.component_editors.sections.axis_ticks import (
            _TickLevelPage,
        )

        tick_defaults = {
            k: v.default
            for k, v in TickGroupController.property_specs().items()
            if v.persistent
        }
        label_defaults = {
            k: v.default
            for k, v in TickLabelGroupController.property_specs().items()
            if v.persistent
        }
        level = TickLevelSettings(
            DEFAULT_MAJOR_LOCATOR,
            DEFAULT_FORMATTER,
            tick_defaults,
            label_defaults,
        )
        page = _TickLevelPage(level, color_library=ColorLibrary())
        try:
            # 1. Modify common property
            page.label_form.apply_property("fontsize", 22.0)
            self.assertEqual(page.level().label_properties["fontsize"], 22.0)

            # 2. Modify bbox to enabled
            bbox_enabled = {
                "enabled": True,
                "boxstyle": "round",
                "facecolor": "#FFFFFF",
                "edgecolor": "#000000",
                "linewidth": 1.0,
                "line_pattern": {"kind": "preset", "value": "-"},
                "alpha": None,
                "fill": True,
                "hatch": None,
                "pad": 0.3,
            }
            page.label_form.apply_property("bbox", bbox_enabled)
            self.assertTrue(page.level().label_properties["bbox"]["enabled"])

            # 3. Modify bbox to disabled
            page.label_form.apply_property("bbox", {"enabled": False})
            self.assertFalse(page.level().label_properties["bbox"]["enabled"])

            # 4. Modify advanced property and verify common property is retained
            page.label_advanced_form.apply_property("antialiased", False)
            self.assertFalse(page.level().label_properties["antialiased"])
            self.assertEqual(page.level().label_properties["fontsize"], 22.0)
        finally:
            page.dispose()
            page.close()

    def test_tick_level_page_blocks_recursive_table_rebuilds_and_row_signals(self):
        from mygui.figuremodify.components import (
            TickGroupController,
            TickLabelGroupController,
        )
        from mygui.figuremodify.components.property_values import (
            DEFAULT_FORMATTER,
            DEFAULT_MAJOR_LOCATOR,
        )
        from mygui.figuremodify.services.axis_ticks import TickLevelSettings
        from mygui.widgets.fig_control_window.component_editors.sections.axis_ticks import (
            _TickLevelPage,
        )

        level = TickLevelSettings(
            DEFAULT_MAJOR_LOCATOR,
            DEFAULT_FORMATTER,
            {
                key: spec.default
                for key, spec in TickGroupController.property_specs().items()
                if spec.persistent
            },
            {
                key: spec.default
                for key, spec in TickLabelGroupController.property_specs().items()
                if spec.persistent
            },
        )
        page = _TickLevelPage(level, color_library=ColorLibrary())
        try:
            page.locator_editor.set_value(
                {
                    "kind": "fixed",
                    "params": {"locations": [0.0, 1.0], "nbins": None},
                },
                emit=True,
            )
            page.formatter_editor.set_value(
                {
                    "kind": "fixed",
                    "params": {"labels": []},
                },
                emit=True,
            )
            self.assertEqual(
                page.formatter_editor.value()["params"]["labels"],
                ["", ""],
            )
            self.assertEqual(
                page.level().formatter["params"]["labels"],
                ["", ""],
            )
            changed_items = []
            page.fixed_table.itemChanged.connect(changed_items.append)
            original_set_value = page.locator_editor.set_value

            def emitting_set_value(value, *, emit=False):
                del emit
                original_set_value(value, emit=True)

            edited_item = page.fixed_table.item(0, 0)
            with (
                patch.object(
                    page.locator_editor,
                    "set_value",
                    side_effect=emitting_set_value,
                ),
                patch.object(page, "_sync_table", wraps=page._sync_table) as sync,
            ):
                edited_item.setText("0.25")
            self.assertEqual(sync.call_count, 0)
            self.assertIs(page.fixed_table.item(0, 0), edited_item)

            changed_items.clear()
            page._add_row()
            page._move_row(-1)
            page._remove_row()
            self.assertEqual(changed_items, [])
        finally:
            page.dispose()
            page.close()

    def test_sync_from_controller_does_not_reapply_compound_values(self):
        _figure, registry = self._figure_registry()
        line = self._controller(registry, ComponentKind.LINE)
        editor = ComponentEditorBase(line, color_library=ColorLibrary())
        applied = []
        editor.propertyChanged.connect(
            lambda key, value: applied.append((key, value))
        )
        try:
            editor.sync_from_controller()
            self.assertEqual(applied, [])
            for key in ("linestyle", "marker", "markevery", "gapcolor"):
                widget = editor.editor(key)
                self.assertIsInstance(
                    widget,
                    (InlineValueEditor, StructuredValueEditor),
                )
                self.assertEqual(
                    widget.value(),
                    line.read_state().properties[key],
                )
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
