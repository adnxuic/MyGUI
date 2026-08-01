import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from Qt_core import QApplication, QWidget
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from code import tex_config
from code.database import ColumnRef, TableChangeSet, TableRepository
from code.database.interpolate_func import interpolate_dict
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
    FitCurveController,
    FunctionCurveController,
    InterpolationController,
    register_figure_components,
)
from code.widgets.common_widget.min_widget.color_library import ColorLibrary
from code.widgets.fig_control_window.component_editors.containers import (
    AxesSemanticInspectorPanel,
)
from code.widgets.fig_control_window.component_editors import (
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
from code.widgets.fig_control_window.component_editors.profiles import (
    LEGEND_PROFILE,
    LINE_PROFILES,
    SEMANTIC_TEXT_PROFILE,
    TEXT_PROFILE,
)


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
    )


class ComponentInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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
            LineAppearanceSection.PROPERTY_KEYS,
            (
                "label",
                "visible",
                "color",
                "linestyle",
                "linewidth",
                "marker",
                "markersize",
                "markerfacecolor",
                "markeredgecolor",
                "markeredgewidth",
                "alpha",
                "zorder",
            ),
        )
        self.assertEqual(
            tuple(
                section.key
                for section in LINE_PROFILES[
                    ComponentRole.FIT_CURVE
                ].sections
            ),
            ("data", "actions", "result", "range", "appearance"),
        )

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
                LineAppearanceSection.PROPERTY_KEYS,
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
        self.assertIn(render._listener, tex_config._TEX_STATE_LISTENERS)

        change = registry.delete(controller.component_id)

        self.assertTrue(change.ok)
        self.assertTrue(inspector._disposed)
        self.assertTrue(render._disposed)
        self.assertNotIn(render._listener, tex_config._TEX_STATE_LISTENERS)
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
                zip(controllers, lines)
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
                    LineAppearanceSection.PROPERTY_KEYS,
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
        self.assertIs(
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
            ("content", "typography", "transform", "position", "render"),
        )
        self.assertEqual(
            tuple(section.key for section in LEGEND_PROFILE.sections),
            ("content", "typography", "layout", "frame"),
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

        repository.record_change(
            TableChangeSet(
                project.id,
                metadata_changed=True,
                reason="disposed-input",
            )
        )

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
            expected_ids = {controller.component_id}
            self.assertEqual(set(panel.component_ids()), expected_ids)
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


if __name__ == "__main__":
    unittest.main()
