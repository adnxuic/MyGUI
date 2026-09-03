import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from mygui import status_messages, tex_config
from mygui.database import matlab_adapter
from mygui.database import (
    ColumnRef,
    DataPreprocessSpec,
    TableChangeSet,
    TableRepository,
)
from mygui.database.interpolate_func import interpolate_dict
from mygui.figuremodify.component_services import (
    AxesCommandService,
    ChartDataService,
    ComponentDeletionService,
    DeletionRequest,
    FitService,
    FunctionCurveService,
    InterpolationService,
    ReferenceMarksService,
    TextRenderService,
)
from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRegistry,
    ComponentRole,
    ComponentState,
    DataPlotController,
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    LineController,
    ReferenceMarksController,
    register_figure_components,
)
from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
from mygui.widgets.common_widget.min_widget.py_colorchoice_widgets import (
    ColorChoiceWidget,
)
from mygui.widgets.fig_control_window.component_editors.cleanup import (
    CleanupFailure,
    drain_cleanup_failures,
    isolate_cleanup,
)
from mygui.widgets.fig_control_window.component_editors.containers import (
    AxesSemanticInspectorPanel,
    ChartInspectorStack,
    InspectorToolBox,
)
from mygui.widgets.fig_control_window.component_editors.fit_sections import (
    FitDomainSection,
)
from mygui.widgets.fig_control_window.component_editors.sections import (
    PaletteSection,
    TextRenderSection,
)
from mygui.widgets.fig_control_window.component_editors import (
    ComponentEditorManager,
    ComponentInspector,
    DataReferenceInput,
    EditorContext,
    EditorProfile,
    EditorPlacement,
    EditorRegistry,
    EditorSection,
    InterpolationOptionsInput,
    LineAppearanceSection,
    MessagePresenter,
    SectionSpec,
    TreePresentationSpec,
    register_production_profiles,
)
from mygui.widgets.fig_control_window.component_editors.profiles import (
    LEGEND_PROFILE,
    LINE_PROFILES,
    REFERENCE_MARKS_PROFILE,
    SEMANTIC_TEXT_PROFILE,
    TEXT_PROFILE,
)
from mygui.widgets.fig_control_window.figure_inspector import AxesInspectorPanel


def _context(
    registry: ComponentRegistry,
    repository: TableRepository,
    library: ColorLibrary,
) -> EditorContext:
    interpolation = InterpolationService(repository, registry)
    chart_data = ChartDataService(repository, registry)
    chart_data.interpolation_service = interpolation
    editor_registry = EditorRegistry()
    register_production_profiles(editor_registry)
    return EditorContext(
        registry=registry,
        color_library=library,
        messages=MessagePresenter(),
        editor_manager=ComponentEditorManager(
            registry,
            editor_registry,
        ),
        axes_commands=AxesCommandService(registry),
        function_curves=FunctionCurveService(registry),
        chart_data=chart_data,
        interpolation=interpolation,
        fitting=FitService(repository, registry),
        text_rendering=TextRenderService(registry),
        reference_marks=ReferenceMarksService(registry, repository),
    )


def _managed_text_inspector(content: str = "abc"):
    figure = Figure()
    FigureCanvasAgg(figure)
    figure.subplots()
    figure.text(0.5, 0.5, content)
    registry = register_figure_components(figure)
    controller = registry.find_one(
        kind=ComponentKind.TEXT,
        role=ComponentRole.TEXT,
    )
    context = _context(registry, TableRepository(), ColorLibrary())
    inspector = context.editor_manager.create(controller, context=context)
    return controller, context, inspector


class ComponentInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        status_messages.clear_status_handler()
        drain_cleanup_failures()
        QApplication.processEvents()

    def tearDown(self):
        status_messages.clear_status_handler()
        QApplication.processEvents()

    def test_text_content_commit_preserves_cursor_at_end(self):
        controller, context, inspector = _managed_text_inspector("abc")
        try:
            section = inspector.section("content")
            editor = section.text_content
            editor.moveCursor(QTextCursor.End)
            editor.insertPlainText("d")

            self.assertEqual(editor.textCursor().position(), 4)
            self.assertTrue(section.set_text_content())
            self.assertEqual(
                controller.read_state().properties["text"],
                "abcd",
            )
            self.assertEqual(editor.toPlainText(), "abcd")
            self.assertEqual(editor.textCursor().position(), 4)
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_text_content_commit_preserves_cursor_after_middle_insert(self):
        controller, context, inspector = _managed_text_inspector("abcd")
        try:
            section = inspector.section("content")
            editor = section.text_content
            cursor = editor.textCursor()
            cursor.setPosition(2)
            editor.setTextCursor(cursor)
            editor.insertPlainText("X")

            self.assertEqual(editor.textCursor().position(), 3)
            self.assertTrue(section.set_text_content())
            self.assertEqual(
                controller.read_state().properties["text"],
                "abXcd",
            )
            self.assertEqual(editor.toPlainText(), "abXcd")
            self.assertEqual(editor.textCursor().position(), 3)
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_external_text_change_updates_editor_and_accepted_baseline(self):
        controller, context, inspector = _managed_text_inspector("abc")
        try:
            section = inspector.section("content")

            result = controller.set_property("text", "external")

            self.assertTrue(result.ok)
            self.assertEqual(
                controller.read_state().properties["text"],
                "external",
            )
            self.assertEqual(section.text_content.toPlainText(), "external")
            self.assertEqual(
                section._text_binding.last_valid_text,
                "external",
            )
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_unrelated_change_does_not_clobber_pending_text_content(self):
        controller, context, inspector = _managed_text_inspector("abc")
        try:
            content = inspector.section("content")
            editor = content.text_content
            editor.moveCursor(QTextCursor.End)
            editor.insertPlainText("d")

            result = controller.set_property("fontsize", 18.0)

            self.assertTrue(result.ok)
            self.assertEqual(editor.toPlainText(), "abcd")
            self.assertEqual(editor.textCursor().position(), 4)
            self.assertEqual(
                controller.read_state().properties["text"],
                "abc",
            )
            typography = inspector.section("typography")
            self.assertEqual(typography.editor("fontsize").value(), 18.0)

            self.assertTrue(content.set_text_content())
            self.assertEqual(
                controller.read_state().properties["text"],
                "abcd",
            )
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_line_roles_share_one_appearance_factory_and_field_order(self):
        roles = (
            ComponentRole.FUNCTION_CURVE,
            ComponentRole.DATA_PLOT,
            ComponentRole.FIT_CURVE,
            ComponentRole.INTERPOLATION,
        )
        appearance_specs = []
        for role in roles:
            specs = {
                section.key: section
                for section in LINE_PROFILES[role].sections
            }
            appearance_specs.append(specs["appearance"])

        self.assertTrue(
            all(
                spec.factory is appearance_specs[0].factory
                for spec in appearance_specs
            )
        )
        self.assertEqual(
            set(LineAppearanceSection.PRIMARY_KEYS)
            | set(LineAppearanceSection.ADVANCED_KEYS),
            {spec.key for spec in LineController.PROPERTY_SPECS},
        )
        self.assertEqual(
            len(LineAppearanceSection.PROPERTY_KEYS),
            len(LineController.PROPERTY_SPECS),
        )
        self.assertEqual(
            tuple(
                section.key
                for section in LINE_PROFILES[
                    ComponentRole.FIT_CURVE
                ].sections
            ),
            ("data", "actions", "result", "range", "appearance", "advanced"),
        )

    def test_reference_marks_exact_profile_data_edit_sync_and_rejection(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        registry = register_figure_components(figure)
        axes_controller = registry.find_one(
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
        )
        component_id = "inspector-reference-marks"
        artist = LineCollection(
            [],
            transform=axes.get_xaxis_transform(),
        )
        axes.add_collection(artist, autolim=False)
        controller = ReferenceMarksController(
            ComponentState(
                id=component_id,
                kind=ComponentKind.REFERENCE_MARKS,
                role=ComponentRole.REFLECTION_POSITIONS,
                parent_id=axes_controller.component_id,
                order=max(
                    child.state.order
                    for child in registry.children(axes_controller.component_id)
                ) + 1,
                selector={"object_id": component_id},
                properties=ReferenceMarksController.default_properties(),
                data={
                    "positions": [15.2, 22.9],
                    "position_ref": None,
                    "placement": {"kind": "fixed"},
                },
            ),
            target=artist,
        )
        self.assertTrue(controller.apply_state(controller.state).ok)
        registry.register(controller, target=artist)
        context = _context(registry, TableRepository(), ColorLibrary())
        inspector = context.editor_manager.create(controller, context=context)
        try:
            self.assertIs(
                context.editor_manager.editor(component_id),
                inspector,
            )
            self.assertEqual(
                tuple(section.key for section in REFERENCE_MARKS_PROFILE.sections),
                ("general", "position", "line", "advanced", "data"),
            )
            self.assertEqual(
                {
                    key
                    for section in REFERENCE_MARKS_PROFILE.sections
                    for key in section.property_keys
                },
                set(ReferenceMarksController.default_properties()),
            )
            self.assertEqual(REFERENCE_MARKS_PROFILE.placement, EditorPlacement.ELEMENT)
            self.assertEqual(
                REFERENCE_MARKS_PROFILE.tree.label,
                "Reflection Positions",
            )

            data = inspector.section("data")
            data.positions_input.setText("22.9, 15.2, 15.2")
            self.assertTrue(data.apply_data())
            self.assertEqual(
                controller.state.data["positions"],
                [22.9, 15.2, 15.2],
            )
            self.assertIsNone(controller.state.data["position_ref"])
            self.assertEqual(len(artist.get_segments()), 3)

            self.assertTrue(
                context.reference_marks.update_positions(
                    controller,
                    [],
                ).ok
            )
            self.assertEqual(data.positions_input.text(), "")

            with patch("mygui.status_messages.show_error") as show_error:
                data.positions_input.setText("15.2 nan")
                self.assertFalse(data.apply_data())
                show_error.assert_called_once()
            self.assertEqual(
                controller.state.data,
                {
                    "positions": [],
                    "position_ref": None,
                    "placement": {"kind": "fixed"},
                },
            )
            self.assertEqual(data.positions_input.text(), "")
            self.assertEqual(len(artist.get_segments()), 0)
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_profile_registry_builds_inspector_and_updates_snapshot(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [1.0, 2.0])
        registry = register_figure_components(figure)
        controller = registry.find_one(
            kind=ComponentKind.LINE,
            role=ComponentRole.LINE,
        )
        library = ColorLibrary()
        context = _context(registry, TableRepository(), library)
        editors = EditorRegistry()
        editors.register_profile(
            ComponentKind.LINE,
            LINE_PROFILES[ComponentRole.LINE],
            role=ComponentRole.LINE,
        )
        inspector = editors.create(controller, context=context)
        try:
            self.assertIsInstance(inspector, ComponentInspector)
            appearance = inspector.section("appearance")
            self.assertEqual(
                tuple(appearance.editors()),
                LineAppearanceSection.PRIMARY_KEYS,
            )

            appearance.editor("linewidth").setValue(4.25)

            self.assertEqual(line.get_linewidth(), 4.25)
            self.assertEqual(
                controller.read_state().properties["linewidth"],
                4.25,
            )
            self.assertEqual(
                registry.snapshot()[controller.component_id].properties[
                    "linewidth"
                ],
                4.25,
            )
        finally:
            inspector.close()
            context.editor_manager.close()

    def test_production_registration_builds_exact_inspectors_for_first_party_components(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.text(0.5, 0.5, "note")
        registry = register_figure_components(figure)
        context = _context(
            registry,
            TableRepository(),
            ColorLibrary(),
        )
        inspectors = []
        try:
            for controller in registry:
                inspector = context.editor_manager.create(
                    controller,
                    context=context,
                )
                inspectors.append(inspector)
                self.assertIs(type(inspector), ComponentInspector)
            first = inspectors[0]
            first_id = first.controller.component_id
            first.close()
            self.assertIsNone(context.editor_manager.editor(first_id))
        finally:
            for inspector in inspectors:
                inspector.close()
            context.editor_manager.close()

    def test_color_inspectors_create_and_switch_without_negative_sizes(self):
        captured: list[str] = []

        def handler(mode, context, message):
            text = str(message)
            if "Negative sizes" in text:
                captured.append(text)
            if callable(previous):
                previous(mode, context, message)

        previous = qInstallMessageHandler(handler)
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [1.0, 2.0])
        figure.text(0.5, 0.5, "note")
        registry = register_figure_components(figure)
        extra, = axes.plot([0.0, 1.0], [0.0, 1.0])
        registry.register(
            FunctionCurveController(
                ComponentState(
                    id="func-curve",
                    kind=ComponentKind.LINE,
                    role=ComponentRole.FUNCTION_CURVE,
                    order=99,
                    selector={"object_id": "func-curve"},
                    properties={},
                    data={
                        "expression": "x",
                        "x_start": 0.0,
                        "x_stop": 1.0,
                    },
                )
            ),
            target=extra,
            require_parent=False,
        )
        context = _context(registry, TableRepository(), ColorLibrary())
        inspectors = []
        host = QWidget()
        layout = QVBoxLayout(host)
        try:
            targets = (
                registry.find_one(kind=ComponentKind.FIGURE),
                registry.find_one(kind=ComponentKind.AXES),
                registry.find_one(
                    kind=ComponentKind.LINE,
                    role=ComponentRole.LINE,
                ),
                registry.find_one(
                    kind=ComponentKind.TEXT,
                    role=ComponentRole.TEXT,
                ),
                registry.find_one(
                    kind=ComponentKind.LINE,
                    role=ComponentRole.FUNCTION_CURVE,
                ),
            )
            for controller in targets:
                inspector = context.editor_manager.create(
                    controller,
                    context=context,
                )
                inspectors.append(inspector)
                layout.addWidget(inspector)
                inspector.hide()
            host.resize(240, 900)
            self.app.processEvents()
            seen = []
            for inspector in inspectors:
                inspector.show()
                inspector.resize(240, 700)
                self.app.processEvents()
                widgets = list(inspector.findChildren(ColorChoiceWidget))
                seen.extend(widgets)
                for widget in widgets:
                    self.assertGreaterEqual(widget._swatch_host.minimumHeight(), 52)
                inspector.resize(480, 700)
                self.app.processEvents()
                for widget in inspector.findChildren(ColorChoiceWidget):
                    self.assertGreaterEqual(widget._swatch_host.minimumHeight(), 52)
                inspector.hide()
                self.app.processEvents()
            for inspector in inspectors:
                inspector.show()
                self.app.processEvents()
                inspector.hide()
            self.assertTrue(seen)
            curve = inspectors[-1]
            self.assertTrue(curve.findChildren(ColorChoiceWidget))
            self.assertEqual(captured, [])
        finally:
            qInstallMessageHandler(previous)
            host.close()
            host.deleteLater()
            for inspector in inspectors:
                inspector.close()
            context.editor_manager.close()

    def test_manager_removal_disposes_text_listener_and_is_idempotent(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.text(0.5, 0.5, "note")
        registry = register_figure_components(figure)
        controller = registry.find_one(
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
        )
        context = _context(
            registry,
            TableRepository(),
            ColorLibrary(),
        )
        inspector = context.editor_manager.create(
            controller,
            context=context,
        )
        render = inspector.section("render")
        self.assertIn(
            render._listener,
            tex_config._TEX_AVAILABILITY_LISTENERS,
        )

        outcome = ComponentDeletionService(registry).delete(
            DeletionRequest((controller.component_id,))
        )

        self.assertTrue(outcome.committed)
        self.assertTrue(inspector._disposed)
        self.assertTrue(render._disposed)
        self.assertNotIn(
            render._listener,
            tex_config._TEX_AVAILABILITY_LISTENERS,
        )
        self.assertIsNone(
            context.editor_manager.editor(controller.component_id)
        )
        inspector.dispose()
        context.editor_manager.close()
        context.editor_manager.close()

    def test_all_specialized_line_roles_apply_the_same_common_property(self):
        repository = TableRepository()
        project = repository.create_project("Data")
        sheet = next(iter(project.sheets.values()))
        sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0]])
        x_ref = ColumnRef(project.id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(project.id, sheet.id, sheet.columns[1].id)
        refs = {"x_ref": x_ref.to_dict(), "y_ref": y_ref.to_dict()}

        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        registry = ComponentRegistry()
        definitions = (
            (
                FunctionCurveController,
                ComponentRole.FUNCTION_CURVE,
                {
                    "expression": "x",
                    "x_start": 0.0,
                    "x_stop": 1.0,
                },
            ),
            (DataPlotController, ComponentRole.DATA_PLOT, refs),
            (
                FitCurveController,
                ComponentRole.FIT_CURVE,
                {
                    **refs,
                    "engine": "Python",
                    "fit_type": None,
                    "fit_options": None,
                    "fit_result": None,
                    "expression": "",
                    "x_start": 0.0,
                    "x_stop": 1.0,
                },
            ),
            (
                InterpolationController,
                ComponentRole.INTERPOLATION,
                {
                    **refs,
                    "method": tuple(interpolate_dict)[0],
                    "k": 3,
                    "samples": 100,
                    "lam": None,
                    "lam_auto": True,
                },
            ),
        )
        controllers = []
        lines = []
        for order, (controller_type, role, data) in enumerate(definitions):
            component_id = f"line-{order}"
            line, = axes.plot([0.0, 1.0], [1.0, 2.0])
            controller = controller_type(
                ComponentState(
                    id=component_id,
                    kind=ComponentKind.LINE,
                    role=role,
                    order=order,
                    selector={"object_id": component_id},
                    properties={},
                    data=data,
                )
            )
            registry.register(
                controller,
                target=line,
                require_parent=False,
            )
            controllers.append(controller)
            lines.append(line)

        context = _context(registry, repository, ColorLibrary())
        inspectors = []
        try:
            for index, (controller, line) in enumerate(
                zip(controllers, lines, strict=False)
            ):
                inspector = ComponentInspector(
                    controller,
                    context=context,
                    profile=LINE_PROFILES[controller.state.role],
                )
                inspectors.append(inspector)
                appearance = inspector.section("appearance")
                self.assertEqual(
                    tuple(appearance.editors()),
                    LineAppearanceSection.PRIMARY_KEYS,
                )
                linewidth = 2.5 + index
                appearance.editor("linewidth").setValue(linewidth)
                self.assertEqual(line.get_linewidth(), linewidth)
                self.assertEqual(
                    controller.read_state().properties["linewidth"],
                    linewidth,
                )
                self.assertEqual(
                    registry.snapshot()[
                        controller.component_id
                    ].properties["linewidth"],
                    linewidth,
                )
        finally:
            for inspector in inspectors:
                inspector.close()
            context.editor_manager.close()

    def test_text_and_legend_profiles_preserve_role_differences(self):
        self.assertIsNot(
            SEMANTIC_TEXT_PROFILE.sections,
            TEXT_PROFILE.sections,
        )
        self.assertIs(TEXT_PROFILE.placement, EditorPlacement.ELEMENT)
        self.assertIs(
            SEMANTIC_TEXT_PROFILE.placement,
            EditorPlacement.SEMANTIC,
        )
        self.assertEqual(
            tuple(section.key for section in TEXT_PROFILE.sections),
            (
                "content", "typography", "transform", "position",
                "render", "advanced",
            ),
        )
        self.assertEqual(
            tuple(section.key for section in LEGEND_PROFILE.sections),
            (
                "content", "typography", "layout", "layout_details",
                "frame", "advanced",
            ),
        )

    def test_data_and_interpolation_inputs_sync_without_recursive_signals(self):
        repository = TableRepository()
        project = repository.create_project("Data")
        sheet = next(iter(project.sheets.values()))
        sheet.set_block(0, 0, [[0.0, 1.0], [1.0, 2.0]])
        first = ColumnRef(project.id, sheet.id, sheet.columns[0].id)
        second = ColumnRef(project.id, sheet.id, sheet.columns[1].id)

        references = DataReferenceInput(repository, project.id)
        options = InterpolationOptionsInput()
        ref_events = []
        option_events = []
        references.refsChanged.connect(
            lambda x_ref, y_ref: ref_events.append((x_ref, y_ref))
        )
        options.optionsChanged.connect(lambda: option_events.append(True))
        method = tuple(interpolate_dict)[-1]
        try:
            references.set_refs(second, first)
            references.set_preprocess(
                DataPreprocessSpec("1/x", "y/x")
            )
            options.set_options(
                method=method,
                samples=80,
                k=2,
                lam=None,
                lam_auto=True,
            )

            self.assertEqual(references.get_x_ref(), second)
            self.assertEqual(references.get_y_ref(), first)
            self.assertEqual(ref_events, [])
            self.assertEqual(
                references.get_preprocess_spec(),
                DataPreprocessSpec("1/x", "y/x"),
            )
            self.assertEqual(option_events, [])
            self.assertEqual(
                options.options(),
                {
                    "method": method,
                    "samples": 80,
                    "k": 2,
                    "lam": None,
                    "lam_auto": True,
                },
            )
        finally:
            references.close()
            options.close()

    def test_data_reference_input_dispose_disconnects_repository(self):
        class TrackingDataReferenceInput(DataReferenceInput):
            def __init__(self, *args, **kwargs):
                self.repository_events = 0
                super().__init__(*args, **kwargs)

            def _repository_changed(self, changes):
                self.repository_events += 1
                super()._repository_changed(changes)

        repository = TableRepository()
        project = repository.create_project("Data")
        references = TrackingDataReferenceInput(
            repository,
            project.id,
        )
        references.dispose()
        references.dispose()

        with repository.mutate(
            TableChangeSet(
                project.id,
                metadata_changed=True,
                reason="disposed-input",
            )
        ):
            pass

        self.assertEqual(references.repository_events, 0)
        references.close()

    def test_text_apply_many_commits_and_render_failure_rolls_back_all(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.set_title("Old title")
        axes.set_xlabel("Old X")
        registry = register_figure_components(figure)
        title = registry.find_one(role=ComponentRole.TITLE)
        x_label = registry.find_one(role=ComponentRole.X_LABEL)
        service = TextRenderService(registry)
        figure.canvas.draw_idle = Mock()
        original_draw = figure.canvas.draw
        figure.canvas.draw = Mock(wraps=original_draw)

        committed = service.apply_many(
            (
                (title, {"text": "New title"}),
                (x_label, {"text": "New X"}),
            )
        )

        self.assertTrue(committed.committed)
        self.assertEqual(figure.canvas.draw.call_count, 1)
        self.assertEqual(title.resolve_target().get_text(), "New title")
        self.assertEqual(x_label.resolve_target().get_text(), "New X")

        with patch.object(
            figure.canvas,
            "draw",
            side_effect=RuntimeError("synthetic render failure"),
        ):
            rejected = service.apply_many(
                (
                    (title, {"text": "Broken title"}),
                    (x_label, {"text": "Broken X"}),
                )
            )

        self.assertFalse(rejected.committed)
        self.assertEqual(title.resolve_target().get_text(), "New title")
        self.assertEqual(x_label.resolve_target().get_text(), "New X")
        self.assertEqual(
            title.read_state().properties["text"],
            "New title",
        )
        self.assertEqual(
            x_label.read_state().properties["text"],
            "New X",
        )

    def test_axes_panel_lazily_caches_semantic_component_inspectors(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [1.0, 2.0], label="line")
        registry = register_figure_components(figure)
        controller = registry.find_one(
            kind=ComponentKind.AXES,
            role=ComponentRole.AXES,
        )
        context = _context(
            registry,
            TableRepository(),
            ColorLibrary(),
        )
        panel = AxesSemanticInspectorPanel(controller, context)
        try:
            semantic = [
                item
                for item in registry.descendants(
                    controller.component_id
                )
                if item.state.kind not in {
                    ComponentKind.LINE,
                    ComponentKind.SCATTER,
                }
                and not (
                    item.state.kind is ComponentKind.TEXT
                    and item.state.role is ComponentRole.TEXT
                )
            ]
            self.assertEqual(panel.component_ids(), ())
            expected_ids = {controller.component_id}
            expected_ids.update(item.component_id for item in semantic)
            for component_id in expected_ids:
                self.assertTrue(panel.show_component(component_id))
                self.assertEqual(
                    panel.current_component_id(),
                    component_id,
                )
                self.assertIsInstance(
                    panel.inspector(component_id),
                    ComponentInspector,
                )
            self.assertEqual(set(panel.component_ids()), expected_ids)
        finally:
            panel.close()
            context.editor_manager.close()

    def test_profile_validation_rejects_ambiguous_registration(self):
        profile = EditorProfile(
            "test",
            "Test",
            (SectionSpec("properties", "Properties", lambda *_args: QWidget()),),
            placement=EditorPlacement.FIGURE,
            tree=TreePresentationSpec("Test"),
        )
        editor_registry = EditorRegistry()
        editor_registry.register_profile(
            ComponentKind.FIGURE,
            profile,
            role=ComponentRole.FIGURE,
        )
        with self.assertRaisesRegex(ValueError, "Duplicate Editor profile"):
            editor_registry.register_profile(
                ComponentKind.FIGURE,
                profile,
                role=ComponentRole.FIGURE,
            )
        with self.assertRaisesRegex(ValueError, "missing"):
            editor_registry.validate_production_profiles()
        with self.assertRaisesRegex(ValueError, "unique"):
            EditorProfile(
                "invalid",
                "Invalid",
                (
                    SectionSpec("same", "One", lambda *_args: QWidget()),
                    SectionSpec("same", "Two", lambda *_args: QWidget()),
                ),
                placement=EditorPlacement.SEMANTIC,
                tree=TreePresentationSpec("Invalid"),
            )

    def test_production_registry_freezes_and_missing_profile_fails_closed(self):
        registry = EditorRegistry()
        register_production_profiles(registry)
        registry.freeze()
        self.assertTrue(registry.frozen)
        with self.assertRaisesRegex(RuntimeError, "frozen"):
            registry.unregister(
                ComponentKind.LINE,
                role=ComponentRole.LINE,
            )

        missing = EditorRegistry()
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        component_registry = register_figure_components(figure)
        controller = component_registry.find_one(kind=ComponentKind.FIGURE)
        context = _context(
            component_registry,
            TableRepository(),
            ColorLibrary(),
        )
        with self.assertRaisesRegex(LookupError, "No exact Editor profile"):
            missing.create(controller, context=context)
        context.editor_manager.close()

    def test_production_inspectors_expand_at_most_eight_properties(self):
        registry = EditorRegistry()
        register_production_profiles(registry)
        for kind, role in sorted(
            registry.profile_keys,
            key=lambda item: (item[0].value, item[1].value),
        ):
            profile = registry.profile_for(kind, role)
            expanded = sum(
                len(section.property_keys or ())
                for section in profile.sections
                if not section.collapsed
            )
            self.assertLessEqual(
                expanded,
                8,
                f"{kind.value}/{role.value} expands {expanded} properties",
            )
            for section in profile.sections:
                if section.title == "Advanced":
                    self.assertTrue(
                        section.collapsed,
                        f"{kind.value}/{role.value} Advanced must start collapsed",
                    )

    def test_section_factory_failure_disposes_prior_subscriptions(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        controller = registry.find_one(kind=ComponentKind.FIGURE)
        context = _context(registry, TableRepository(), ColorLibrary())
        baseline = len(registry._event_subscribers)

        class TrackingSection(QWidget, EditorSection):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._unsubscribe = registry.subscribe(lambda _event: None)

            def dispose(self):
                if self._unsubscribe is not None:
                    self._unsubscribe()
                    self._unsubscribe = None

        profile = EditorProfile(
            "failure",
            "Failure",
            (
                SectionSpec(
                    "tracking",
                    "Tracking",
                    lambda _controller, _context, parent: TrackingSection(parent),
                ),
                SectionSpec(
                    "failure",
                    "Failure",
                    lambda *_args: (_ for _ in ()).throw(
                        RuntimeError("injected section failure")
                    ),
                ),
            ),
            placement=EditorPlacement.FIGURE,
            tree=TreePresentationSpec("Failure"),
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "section failure"):
                ComponentInspector(
                    controller,
                    context=context,
                    profile=profile,
                )
            self.assertEqual(len(registry._event_subscribers), baseline)
        finally:
            context.editor_manager.close()

    def test_external_section_constructor_failures_release_listeners(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        figure.text(0.5, 0.5, "note")
        registry = register_figure_components(figure)
        repository = TableRepository()
        context = _context(registry, repository, ColorLibrary())

        text = registry.find_one(
            kind=ComponentKind.TEXT,
            role=ComponentRole.TEXT,
        )
        tex_before = tuple(tex_config._TEX_AVAILABILITY_LISTENERS)
        with patch.object(
            TextRenderSection,
            "_sync_tex_button",
            side_effect=RuntimeError("injected TeX Section failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "TeX Section"):
                TextRenderSection(text, context=context)
        self.assertEqual(
            tuple(tex_config._TEX_AVAILABILITY_LISTENERS),
            tex_before,
        )

        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        registry_before = tuple(registry._event_subscribers)
        with patch.object(
            PaletteSection,
            "sync_from_controller",
            side_effect=RuntimeError("injected Palette Section failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Palette Section"):
                PaletteSection(axes_controller, context=context)
        self.assertEqual(tuple(registry._event_subscribers), registry_before)
        context.editor_manager.close()

    def test_fit_section_and_toolbox_construction_failure_leave_no_cache(self):
        repository = TableRepository()
        project = repository.create_project("Fit construction")
        sheet = next(iter(project.sheets.values()))
        x_ref = ColumnRef(project.id, sheet.id, sheet.columns[0].id)
        y_ref = ColumnRef(project.id, sheet.id, sheet.columns[1].id)
        figure = Figure()
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        line, = axes.plot([0.0, 1.0], [1.0, 2.0])
        registry = ComponentRegistry()
        controller = FitCurveController(
            ComponentState(
                id="fit-construction",
                kind=ComponentKind.LINE,
                role=ComponentRole.FIT_CURVE,
                selector={"object_id": "fit-construction"},
                properties={},
                data={
                    "x_ref": x_ref.to_dict(),
                    "y_ref": y_ref.to_dict(),
                    "preprocess": DataPreprocessSpec().to_dict(),
                    "engine": "Python",
                    "fit_type": None,
                    "fit_options": None,
                    "fit_result": None,
                    "expression": "",
                    "x_start": 0.0,
                    "x_stop": 1.0,
                },
            )
        )
        registry.register(controller, target=line, require_parent=False)
        context = _context(registry, repository, ColorLibrary())
        matlab_before = tuple(matlab_adapter._MATLAB_STATE_LISTENERS)
        with patch.object(
            FitDomainSection,
            "_matlab_enabled_changed",
            side_effect=RuntimeError("injected MATLAB Section failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "MATLAB Section"):
                FitDomainSection(controller, context=context)
        self.assertEqual(
            tuple(matlab_adapter._MATLAB_STATE_LISTENERS),
            matlab_before,
        )

        stack = ChartInspectorStack()
        original_count = stack.toolbox_stack.count()
        original_add = stack.toolbox_stack.addWidget

        def fail_after_add(widget):
            original_add(widget)
            raise RuntimeError("injected Toolbox insertion failure")

        with patch.object(
            stack.toolbox_stack,
            "addWidget",
            side_effect=fail_after_add,
        ):
            with self.assertRaisesRegex(RuntimeError, "Toolbox insertion"):
                stack.ensure_toolbox(
                    (ComponentKind.LINE, ComponentRole.FIT_CURVE)
                )
        self.assertIsNone(
            stack.toolbox(
                (ComponentKind.LINE, ComponentRole.FIT_CURVE)
            )
        )
        self.assertEqual(stack.toolbox_stack.count(), original_count)
        stack.dispose()
        context.editor_manager.close()

    def test_axes_panel_construction_failure_disposes_partial_inspectors(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        subscribers_before = tuple(registry._event_subscribers)

        with patch(
            "mygui.widgets.fig_control_window.figure_inspector."
            "ChartInspectorStack",
            side_effect=RuntimeError("injected Axes Panel failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Axes Panel"):
                AxesInspectorPanel(axes_controller, context)

        self.assertEqual(tuple(registry._event_subscribers), subscribers_before)
        self.assertEqual(context.editor_manager._editors, {})
        context.editor_manager.close()


class InspectorCleanupFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        status_messages.clear_status_handler()
        drain_cleanup_failures()
        QApplication.processEvents()

    def tearDown(self):
        status_messages.clear_status_handler()
        drain_cleanup_failures()
        QApplication.processEvents()

    def test_isolate_cleanup_records_and_does_not_raise(self):
        def boom():
            raise RuntimeError("injected isolate failure")

        with self.assertLogs(
            "mygui.widgets.fig_control_window.component_editors.cleanup",
            level="ERROR",
        ):
            failure = isolate_cleanup(
                boom,
                owner="Owner",
                target="target",
                operation="dispose",
            )
        self.assertIsInstance(failure, CleanupFailure)
        self.assertEqual(failure.owner, "Owner")
        self.assertEqual(failure.target, "target")
        self.assertEqual(failure.operation, "dispose")
        self.assertEqual(failure.error_type, "RuntimeError")
        recorded = drain_cleanup_failures()
        self.assertEqual(recorded, (failure,))
        self.assertEqual(drain_cleanup_failures(), ())

    def test_section_dispose_failure_continues_and_stays_idempotent(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        controller = registry.find_one(kind=ComponentKind.FIGURE)
        context = _context(registry, TableRepository(), ColorLibrary())
        baseline = len(registry._event_subscribers)
        tracked = []

        class TrackingSection(QWidget, EditorSection):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.disposed = False
                self._unsubscribe = registry.subscribe(lambda _event: None)
                self._timer = QTimer(self)
                self._timer.start(10_000)
                tracked.append(self)

            def dispose(self):
                self.disposed = True
                if self._unsubscribe is not None:
                    self._unsubscribe()
                    self._unsubscribe = None
                self._timer.stop()

        class FailingSection(QWidget, EditorSection):
            def dispose(self):
                raise RuntimeError("injected section dispose failure")

        profile = EditorProfile(
            "cleanup",
            "Cleanup",
            (
                SectionSpec(
                    "tracking",
                    "Tracking",
                    lambda _controller, _context, parent: TrackingSection(parent),
                ),
                SectionSpec(
                    "failure",
                    "Failure",
                    lambda _controller, _context, parent: FailingSection(parent),
                ),
            ),
            placement=EditorPlacement.FIGURE,
            tree=TreePresentationSpec("Cleanup"),
        )
        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        inspector = ComponentInspector(
            controller,
            context=context,
            profile=profile,
        )
        tracking = tracked[0]
        self.assertTrue(tracking._timer.isActive())
        inspector.dispose()
        inspector.dispose()
        failures = drain_cleanup_failures()
        self.assertTrue(inspector._disposed)
        self.assertTrue(tracking.disposed)
        self.assertFalse(tracking._timer.isActive())
        self.assertIsNone(tracking._unsubscribe)
        self.assertEqual(len(registry._event_subscribers), baseline)
        self.assertEqual(seen, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].operation, "dispose")
        self.assertEqual(failures[0].error_type, "RuntimeError")
        self.assertEqual(failures[0].target, "failure")
        context.editor_manager.close()

    def test_manager_close_isolates_partial_dispose_failure(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        figure.text(0.5, 0.5, "note")
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        root = registry.find_one(kind=ComponentKind.FIGURE)
        text = registry.find_one(kind=ComponentKind.TEXT, role=ComponentRole.TEXT)
        first = context.editor_manager.create(root, context=context)
        second = context.editor_manager.create(text, context=context)
        render = second.section("render")
        first.dispose = lambda: (_ for _ in ()).throw(
            RuntimeError("injected manager dispose failure")
        )
        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        context.editor_manager.close()
        context.editor_manager.close()
        failures = drain_cleanup_failures()
        self.assertTrue(second._disposed)
        self.assertTrue(render._disposed)
        self.assertNotIn(render._listener, tex_config._TEX_AVAILABILITY_LISTENERS)
        self.assertEqual(context.editor_manager._editors, {})
        self.assertEqual(seen, [])
        self.assertTrue(
            any(
                failure.operation == "dispose"
                and failure.error_type == "RuntimeError"
                for failure in failures
            )
        )

    def test_toolbox_remove_isolates_dispose_and_empty_callback_failures(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        controller = registry.find_one(kind=ComponentKind.FIGURE)
        toolbox = InspectorToolBox()
        toolbox.editor_manager = context.editor_manager
        inspector = context.editor_manager.create(
            controller,
            context=context,
            parent=toolbox,
            remover=toolbox.remove_inspector,
        )
        toolbox.add_inspector(inspector)
        toolbox.set_empty_callback(
            lambda: (_ for _ in ()).throw(
                RuntimeError("injected empty callback failure")
            )
        )
        inspector.dispose = lambda: (_ for _ in ()).throw(
            RuntimeError("injected toolbox dispose failure")
        )
        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        self.assertTrue(toolbox.remove_inspector(inspector))
        self.assertTrue(toolbox.remove_inspector(inspector) is False)
        failures = drain_cleanup_failures()
        self.assertEqual(toolbox.count(), 0)
        self.assertEqual(seen, [])
        operations = {failure.operation for failure in failures}
        self.assertIn("dispose", operations)
        self.assertIn("empty_callback", operations)
        toolbox.dispose()
        context.editor_manager.close()

    def test_axes_panel_construction_failure_isolates_partial_dispose(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        subscribers_before = tuple(registry._event_subscribers)

        def exploding_dispose(_self):
            raise RuntimeError("injected semantic dispose failure")

        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        with patch(
            "mygui.widgets.fig_control_window.figure_inspector."
            "ChartInspectorStack",
            side_effect=RuntimeError("injected Axes Panel failure"),
        ), patch.object(
            AxesSemanticInspectorPanel,
            "dispose",
            exploding_dispose,
        ):
            with self.assertRaisesRegex(RuntimeError, "Axes Panel"):
                AxesInspectorPanel(axes_controller, context)

        failures = drain_cleanup_failures()
        self.assertEqual(tuple(registry._event_subscribers), subscribers_before)
        self.assertEqual(context.editor_manager._editors, {})
        self.assertEqual(seen, [])
        self.assertTrue(
            any(
                failure.operation == "dispose"
                and failure.error_type == "RuntimeError"
                for failure in failures
            )
        )
        context.editor_manager.close()

    def test_toolbox_construction_rollback_isolates_dispose_failure(self):
        stack = ChartInspectorStack()
        original_count = stack.toolbox_stack.count()
        original_add = stack.toolbox_stack.addWidget

        def fail_after_add(widget):
            original_add(widget)
            raise RuntimeError("injected Toolbox insertion failure")

        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        with patch.object(
            stack.toolbox_stack,
            "addWidget",
            side_effect=fail_after_add,
        ), patch(
            "mygui.widgets.fig_control_window.component_editors.containers."
            "InspectorToolBox.dispose",
            side_effect=RuntimeError("injected toolbox dispose failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Toolbox insertion"):
                stack.ensure_toolbox((ComponentKind.LINE, ComponentRole.LINE))
        failures = drain_cleanup_failures()
        self.assertIsNone(stack.toolbox((ComponentKind.LINE, ComponentRole.LINE)))
        self.assertEqual(stack.toolbox_stack.count(), original_count)
        self.assertEqual(seen, [])
        self.assertTrue(
            any(
                failure.operation == "dispose"
                and failure.error_type == "RuntimeError"
                for failure in failures
            )
        )
        stack.dispose()

    def test_semantic_construction_rollback_isolates_dispose_failure(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        panel = AxesSemanticInspectorPanel(axes_controller, context)
        controller = registry.find_one(kind=ComponentKind.AXIS, role=ComponentRole.X_AXIS)
        original_add = panel.inspector_stack.addWidget

        def fail_after_add(widget):
            original_add(widget)
            raise RuntimeError("injected semantic insertion failure")

        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )
        with patch.object(
            panel.inspector_stack,
            "addWidget",
            side_effect=fail_after_add,
        ), patch(
            "mygui.widgets.fig_control_window.component_editors.inspector."
            "ComponentInspector.dispose",
            side_effect=RuntimeError("injected inspector dispose failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "semantic insertion"):
                panel.ensure_inspector(controller.component_id)
        failures = drain_cleanup_failures()
        self.assertIsNone(panel.inspector(controller.component_id))
        self.assertEqual(seen, [])
        self.assertTrue(
            any(
                failure.operation == "dispose"
                and failure.error_type == "RuntimeError"
                for failure in failures
            )
        )
        panel.dispose()
        context.editor_manager.close()

    def test_manager_and_presenter_isolate_unsubscribe_failures(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        presenter = MessagePresenter(registry)
        baseline = len(registry._event_subscribers)
        seen = []
        status_messages.set_status_handler(
            lambda message, level: seen.append((message, level))
        )

        def boom_then(original):
            def boom():
                if original is not None:
                    original()
                raise RuntimeError("injected unsubscribe failure")

            return boom

        context.editor_manager._unsubscribe = boom_then(
            context.editor_manager._unsubscribe
        )
        presenter._unsubscribe = boom_then(presenter._unsubscribe)
        context.editor_manager.close()
        context.editor_manager.close()
        presenter.close()
        presenter.close()
        failures = drain_cleanup_failures()
        self.assertEqual(seen, [])
        self.assertEqual(len(registry._event_subscribers), baseline - 2)
        self.assertTrue(
            any(
                failure.operation == "unsubscribe"
                and failure.error_type == "RuntimeError"
                for failure in failures
            )
        )

    def test_semantic_panel_and_toolbox_lifecycle_paths(self):
        figure = Figure()
        FigureCanvasAgg(figure)
        figure.subplots()
        registry = register_figure_components(figure)
        context = _context(registry, TableRepository(), ColorLibrary())
        axes_controller = registry.find_one(kind=ComponentKind.AXES)
        panel = AxesSemanticInspectorPanel(axes_controller, context)
        x_axis = registry.find_one(kind=ComponentKind.AXIS, role=ComponentRole.X_AXIS)
        inspector = panel.ensure_inspector(x_axis.component_id)
        self.assertIs(panel.inspector(x_axis.component_id), inspector)
        self.assertTrue(panel.show_component(x_axis.component_id))
        self.assertEqual(panel.current_component_id(), x_axis.component_id)
        self.assertIn(x_axis.component_id, panel.component_ids())
        handle = panel.take_inspector(inspector)
        self.assertIsNotNone(handle)
        self.assertIsNone(panel.inspector(x_axis.component_id))
        self.assertIsNone(panel.take_inspector(inspector))
        panel.restore_inspector(handle)
        panel.restore_inspector(handle)
        self.assertFalse(panel.show_component("missing"))
        self.assertFalse(panel.remove_component("missing"))
        panel.dispose()
        panel.dispose()

        stack = ChartInspectorStack()
        key = (ComponentKind.LINE, ComponentRole.LINE)
        toolbox = stack.ensure_toolbox(key)
        toolbox.editor_manager = context.editor_manager
        figure_controller = registry.find_one(kind=ComponentKind.FIGURE)
        hosted = context.editor_manager.create(
            figure_controller,
            context=context,
            parent=toolbox,
            remover=toolbox.remove_inspector,
        )
        toolbox.add_inspector(hosted)
        self.assertTrue(stack.show_component(figure_controller.component_id))
        self.assertEqual(stack.current_component_id(), figure_controller.component_id)
        self.assertIs(stack.inspector(figure_controller.component_id), hosted)
        self.assertIs(
            stack.toolbox_for_component(figure_controller.component_id),
            toolbox,
        )
        detached = toolbox.take_inspector(hosted)
        self.assertIsNotNone(detached)
        toolbox.restore_inspector(detached)
        toolbox.restore_inspector(detached)
        with self.assertRaises(ValueError):
            toolbox.add_inspector(hosted)
        with self.assertRaises(ValueError):
            toolbox.add_inspector(QWidget())
        self.assertTrue(stack.remove_component(figure_controller.component_id))
        self.assertFalse(stack.remove_component(figure_controller.component_id))
        self.assertFalse(stack.show_toolbox(("missing", "missing")))
        stack.dispose()
        stack.dispose()
        context.editor_manager.close()


if __name__ == "__main__":
    unittest.main()
